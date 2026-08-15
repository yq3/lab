mod db;
mod http_server;
mod runtime;
mod session_state;
mod tray;
mod windows;

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use tauri::{Emitter, Manager, RunEvent, WindowEvent};

use session_state::SessionStateMachine;

/// 瞬态超时兜底（DESIGN §3.1 ③，默认 30s，可配）：无新事件 → 回退 working。
fn transient_timeout() -> Duration {
    std::env::var("PULSEPET_TRANSIENT_TIMEOUT_MS")
        .ok()
        .and_then(|s| s.parse().ok())
        .map(Duration::from_millis)
        .unwrap_or(Duration::from_secs(30))
}

/// 无事件 idle 回收（DESIGN §3.3，30s）。
fn idle_timeout() -> Duration {
    std::env::var("PULSEPET_IDLE_TIMEOUT_MS")
        .ok()
        .and_then(|s| s.parse().ok())
        .map(Duration::from_millis)
        .unwrap_or(Duration::from_secs(30))
}

/// 返回当前多 session 合并后的显示状态（前端 http-bridge 初始化时查询用）。
#[tauri::command]
fn get_display_state(state: tauri::State<'_, Arc<Mutex<SessionStateMachine>>>) -> String {
    let kind = state
        .lock()
        .map(|s| s.display().as_str().to_string())
        .unwrap_or_else(|_| "idle".to_string());
    kind
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            // 第二实例启动：唤起已运行实例的 panel 窗口（TC-APP-02）
            eprintln!("[pulsepet] second instance detected, showing panel");
            windows::show_panel(app);
        }))
        .setup(|app| {
            let conn = db::init(app.handle())?;
            app.manage(Mutex::new(conn));

            // ---- M2 事件链路：runtime 目录 + token + HTTP server + 状态机 ----
            runtime::ensure_runtime_dir().map_err(|e| format!("runtime dir: {e}"))?;
            let token = runtime::generate_token();
            runtime::write_token(&token).map_err(|e| format!("write token: {e}"))?;

            let state = Arc::new(Mutex::new(SessionStateMachine::new()));
            // 显示状态变化 → Tauri event 推给前端（http-bridge → petStore）
            let emit_handle = app.handle().clone();
            let notifier = Arc::new(http_server::DisplayNotifier::new(Arc::new(move |kind| {
                let _ = emit_handle.emit(
                    "pulsepet://state",
                    serde_json::json!({ "kind": kind.as_str() }),
                );
            })));

            let server = http_server::start(
                state.clone(),
                notifier.clone(),
                token,
                http_server::HttpConfig::default(),
            )
            .map_err(|e| format!("start http server: {e}"))?;
            let shutdown = server.shutdown_flag();
            eprintln!("[pulsepet] http server listening on 127.0.0.1:{}", server.port);

            // 后台回收线程：瞬态超时回退 + idle 回收（TC-EV-06 / TC-EV-17）
            {
                let state = state.clone();
                let notifier = notifier.clone();
                let shutdown = shutdown.clone();
                std::thread::spawn(move || loop {
                    if shutdown.load(Ordering::SeqCst) {
                        break;
                    }
                    std::thread::sleep(Duration::from_secs(1));
                    {
                        let mut st = state.lock().unwrap_or_else(|p| p.into_inner());
                        st.tick(Instant::now(), transient_timeout(), idle_timeout());
                    }
                    notifier.notify(&state);
                });
            }

            app.manage(state);
            app.manage(shutdown);
            // Moved 防抖保存器（P2-5）
            app.manage(windows::PositionSaver::new(app.handle().clone()));

            windows::restore_pet_position(app.handle());
            tray::build_tray(app.handle())?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_display_state])
        .on_window_event(|window, event| match event {
            // 关闭控制面板 / 宠物窗口时隐藏而非销毁，托盘可再次唤起（P2-2：pet 也防护）
            WindowEvent::CloseRequested { api, .. }
                if window.label() == "panel" || window.label() == "pet" =>
            {
                api.prevent_close();
                let _ = window.hide();
            }
            WindowEvent::Moved(_) if window.label() == "pet" => {
                if let Some(saver) = window.app_handle().try_state::<windows::PositionSaver>() {
                    saver.request_save();
                }
            }
            _ => {}
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            // 退出时兜底保存位置（正常拖拽期间已由防抖线程持续保存）
            windows::save_pet_position(app_handle);
            // 清除运行时文件：token 每次会话轮换、endpoint 不再指向已退出实例
            runtime::clear_token();
            runtime::clear_endpoint();
            if let Some(shutdown) = app_handle.try_state::<Arc<AtomicBool>>() {
                shutdown.store(true, Ordering::SeqCst);
            }
        }
    });
}
