mod atlas;
mod db;
mod hotkeys;
mod http_server;
mod i18n;
mod interaction;
mod logging;
mod plugins;
mod reminder_scheduler;
mod runtime;
mod session_state;
mod token_stats;
mod todos;
mod tray;
mod windows;

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use rusqlite::Connection;
use tauri::{Emitter, Manager, RunEvent, WindowEvent};

use session_state::{Kind, SessionStateMachine};

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

/// M3 token 汇报 idle 钩子：`/state` 收到 `kind == idle` 时（DESIGN §4.3 末条，
/// TC-TK-10/11/12）查 opencode.db 本会话 token 行 → 满足「有用量 + 数字新鲜」时：
///   1. 注入 `success` 状态（token 会话汇报是 success 的驱动来源之一，
///      DESIGN §3.3 优先级链 success 定案位；仅当显示优先级更低时才抬升——
///      优先级合并天然如此，error/waiting-permission 等更高状态不受影响）；
///   2. 经 Tauri event `pulsepet://bubble` 下发气泡文案（前端 sanitize 后显示）。
/// 任一环节失败（无库/无记录/数字陈旧/全零）都静默跳过——不出气泡、不显示 0 或
/// 陈旧数字（TC-TK-12）。
fn make_idle_hook(
    state: &Arc<Mutex<SessionStateMachine>>,
    app: &tauri::AppHandle,
) -> http_server::IdleHook {
    let state = state.clone();
    let app = app.clone();
    Arc::new(move |session_id: &str| {
        let data_dir = token_stats::opencode_data_dir();
        let now = token_stats::now_ms();
        let max_lag = token_stats::report_max_lag_ms();
        if let Some(text) =
            token_stats::build_idle_report(&data_dir, session_id, now, max_lag)
        {
            {
                let mut st = state.lock().unwrap_or_else(|p| p.into_inner());
                st.apply_event(session_id, Kind::Success, Instant::now());
            }
            let _ = app.emit("pulsepet://bubble", serde_json::json!({ "text": text }));
        }
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // 日志先行（DESIGN §7.5）：早于 Builder::build() 与 App::run 阶段的
    // setup 执行（用户闭包与窗口创建都在 run 的事件循环起点，失败 panic
    // 由 hook 捕获），init 前置后全程在捕获范围。
    logging::init();
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            // 第二实例启动：唤起已运行实例的 panel 窗口（TC-APP-02）
            plog!("[pulsepet] second instance detected, showing panel");
            windows::show_panel(app);
        }))
        // M6 全局快捷键（DESIGN §7.3）：插件本体在 builder 注册，具体热键在
        // setup（state 就绪后）经 hotkeys::register_all 登记 + 分发
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(|app| {
            plog!("[pulsepet] setup begin");
            let conn = db::init(app.handle())?;
            app.manage(Mutex::new(conn));

            // ---- M7 插件机制骨架：物化内置 todo manifest + plugins 表登记（TC-TD-01）----
            {
                let db = app.state::<Mutex<Connection>>();
                let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
                plugins::ensure_builtin_plugins(&conn)
                    .map_err(|e| format!("ensure builtin plugins: {e}"))?;
            }

            // ---- M8 i18n：恢复持久化语言（托盘菜单/气泡文案在构建前就绪）----
            {
                let db = app.state::<Mutex<Connection>>();
                let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
                i18n::restore_from_db(&conn);
            }
            // panel 初始标题设置移至窗口创建之后（窗口尚不存在时 get 返回 None）

            // ---- M5 atlas：按加载顺序解析当前宠物（pet.selected → 内置 → codex → petdex）----
            let atlas_state = {
                let db = app.state::<Mutex<Connection>>();
                let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
                atlas::init_selection(&conn)?
            };
            app.manage(Mutex::new(atlas_state));

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
                make_idle_hook(&state, app.handle()),
                token,
                http_server::HttpConfig::default(),
            )
            .map_err(|e| format!("start http server: {e}"))?;
            let shutdown = server.shutdown_flag();
            plog!("[pulsepet] http server listening on 127.0.0.1:{}", server.port);

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

            // ---- M6 交互模式（穿透开/关，DESIGN §6.3）----
            // 状态从 app_state 恢复（TC-APP-12 重启保留）；持久化过"开"则在
            // 窗口创建后应用（apply 需要 pet 窗口存在；此处先 manage 状态）。
            let pass_through = {
                let db = app.state::<Mutex<Connection>>();
                let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
                interaction::read_persisted(&conn)
            };
            app.manage(interaction::InteractionState::new(pass_through));

            // ---- M4 提醒调度器：读表 → in-memory 倒计时 → tokio interval（Skip） ----
            let reminders_state = {
                let db = app.state::<Mutex<Connection>>();
                let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
                reminder_scheduler::RemindersState::load(&conn)
                    .map_err(|e| format!("load reminders: {e}"))?
            };
            let reminders_state = Arc::new(Mutex::new(reminders_state));
            app.manage(reminders_state.clone());
            reminder_scheduler::spawn_scheduler(app.handle().clone(), reminders_state);

            // ---- 窗口创建（issue #9 修复，DESIGN §7.1）：三窗口均 create:false。
            // config 窗口默认由 tauri 在用户 setup 闭包**之前**创建（App::run
            // 起点先遍历 app.windows 再跑闭包）；Windows 上 WebView2 环境创建
            // 异步、主线程泵消息期间页面已加载，前端启动 invoke 的 IPC 会在
            // 闭包 manage 状态之前被派发 → 命令内 state() panic → WndProc
            //（extern "C"）panic 不可展开 → abort 闪退（Windows 独有，macOS
            // 的 WKWebView 不会在此阶段派发 IPC）。改为全部状态 manage 完成
            // 后从 config 创建窗口——参数单一来源不变，时序竞态消除。
            for wc in app.config().app.windows.iter().filter(|w| !w.create) {
                tauri::WebviewWindowBuilder::from_config(app.handle(), wc)?.build()?;
                plog!("[pulsepet] window created: {}", wc.label);
            }

            // panel 初始标题按恢复的语言设置（tauri.conf.json 里是中性 "PulsePet"）
            if let Some(win) = app.get_webview_window("panel") {
                let _ = win.set_title(i18n::current().panel_title());
            }
            // 持久化过"开"则应用穿透（pet 窗口已存在；托盘勾选态由 build_tray
            // 从 InteractionState 读初值，无需提前）
            if pass_through {
                interaction::apply_pass_through(app.handle(), true);
            }

            windows::restore_pet_position(app.handle());
            // ---- M6 托盘（五项菜单 + 勾选句柄）与全局热键 ----
            app.manage(tray::TrayItems::default());
            tray::build_tray(app.handle())?;
            if let Err(e) = hotkeys::register_all(app.handle()) {
                // 热键注册失败（如组合被其它 App 占用）不阻断启动：面板/穿透
                // 仍有托盘菜单通道（TC-WIN-05 双通道互备）
                plog!("[pulsepet] global shortcut register failed: {e}");
            }
            plog!("[pulsepet] setup complete");
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_display_state,
            interaction::pet_get_pass_through,
            interaction::pet_set_pass_through,
            windows::pet_start_drag,
            windows::pet_toggle_visible,
            windows::panel_open,
            atlas::atlas_meta,
            atlas::atlas_pixels,
            atlas::atlas_list_pets,
            atlas::atlas_select,
            token_stats::token_stats_opencode_path,
            token_stats::token_stats_query,
            token_stats::token_stats_current_session,
            reminder_scheduler::reminders_list,
            reminder_scheduler::reminders_upsert,
            reminder_scheduler::reminders_delete,
            reminder_scheduler::reminders_reload,
            reminder_scheduler::reminders_get_fireworks_global,
            reminder_scheduler::reminders_set_fireworks_global,
            reminder_scheduler::reminders_get_paused,
            reminder_scheduler::reminders_stats,
            reminder_scheduler::reminders_trigger_now,
            reminder_scheduler::reminders_ack,
            reminder_scheduler::reminders_dismiss,
            reminder_scheduler::reminder_play_fireworks,
            reminder_scheduler::fireworks_ready,
            reminder_scheduler::fireworks_finished,
            plugins::plugins_list,
            i18n::ui_get_language,
            i18n::ui_set_language,
            todos::todo_list,
            todos::todo_upsert,
            todos::todo_delete,
            todos::todo_complete,
            todos::todo_reorder,
        ])
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
            // 有 exit 行 = 干净退出；无 exit 行 = 崩溃/被杀（与事件查看器
            // Application Error ID 1000 互为印证，DESIGN §7.5）
            plog!("[pulsepet] exit");
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
