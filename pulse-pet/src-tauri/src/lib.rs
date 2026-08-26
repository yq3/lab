mod action_exec;
mod atlas;
mod db;
mod hotkeys;
mod http_server;
mod i18n;
mod integrations;
mod interaction;
mod logging;
mod plugins;
mod reminder_scheduler;
mod runtime;
mod session_state;
mod theme;
mod token_stats;
mod transcript;
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

/// 显示状态 DTO（v2 M2，TC-UI-03-3）：`{kind, agent}`——面板壳 agent 状态
/// 芯片初开即正确（M1 前置拉前，V2-DESIGN §1.6/§2.4）。
#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DisplayStateDto {
    pub kind: String,
    /// argmax 获胜 session 的归属 agent；无 session 时为空串（前端优雅降级）。
    pub agent: String,
}

/// get_display_state 核心纯逻辑（单测直接驱动；命令薄封装）。
fn display_state_dto(state: &Arc<Mutex<SessionStateMachine>>) -> DisplayStateDto {
    let d = state
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .display();
    DisplayStateDto {
        kind: d.kind.as_str().to_string(),
        agent: d.agent,
    }
}

/// 返回当前多 session 合并后的显示状态（前端 http-bridge / panelStore 初始化查询用）。
#[tauri::command]
fn get_display_state(state: tauri::State<'_, Arc<Mutex<SessionStateMachine>>>) -> DisplayStateDto {
    display_state_dto(&state)
}

/// M3 token 汇报 idle 钩子核心（v2 M1 起 agent 分流，TC-INT-11）：
/// `/state` 收到 `kind == idle` 时（DESIGN §4.3 末条，TC-TK-10/11/12）——
/// **仅 `agent == "opencode"`** 查 opencode.db 本会话 token 行（用 CC session_id
/// 查 opencode 库必然空转，且 M5 后口径正确）；满足「有用量 + 数字新鲜」时：
///   1. 注入 `success` 状态（token 会话汇报是 success 的驱动来源之一，
///      DESIGN §3.3 优先级链 success 定案位；仅当显示优先级更低时才抬升——
///      优先级合并天然如此，error/waiting-permission 等更高状态不受影响）；
///   2. 经 Tauri event `pulsepet://bubble` 下发气泡文案（前端 sanitize 后显示）。
/// 任一环节失败（无库/无记录/数字陈旧/全零）都静默跳过——不出气泡、不显示 0 或
/// 陈旧数字（TC-TK-12）。
///
/// v2 M3（V2-DESIGN §3.2）：气泡末尾追加「 · 今日 {format_tokens_k(total)}」——
/// total = in + out + cache_read（reasoning 不计，与 token_stats_today 同口径）；
/// 今日聚合失败（today=None）时静默省略追加段、本期文案照常（TC-M3-09-3）。
///
/// v2 M5（V2-DESIGN §5.4）：`agent == "claude-code"` 经 `cc_dispatch` 派发——
/// http 请求线程仅做派发，解析（缓存未命中 scan 补建）→ 护栏 → apply+emit
/// 全部在后台线程完成（不 join 回 http 线程，N-3）。
///
/// 查询与气泡下发以闭包注入（`idle_hook_body` 单测断言 CC idle 零 opencode 查询）。
fn idle_hook_body(
    state: &Arc<Mutex<SessionStateMachine>>,
    emit_bubble: &dyn Fn(String),
    query_report: &dyn Fn(&str, i64) -> Option<(String, Option<i64>)>,
    cc_dispatch: &dyn Fn(&str),
    agent: &str,
    session_id: &str,
) {
    match agent {
        "opencode" => {
            let now = token_stats::now_ms();
            if let Some((text, today)) = query_report(session_id, now) {
                let full = match today {
                    Some(total) => {
                        let seg = crate::i18n::current()
                            .token_report_today(&token_stats::format_tokens_k(total));
                        format!("{text}{seg}")
                    }
                    // 今日聚合失败（跨午夜竞态等）→ 静默省略追加段（TC-M3-09-3）
                    None => text,
                };
                {
                    let mut st = state.lock().unwrap_or_else(|p| p.into_inner());
                    st.apply_event("opencode", session_id, Kind::Success, Instant::now());
                }
                emit_bubble(full);
            }
        }
        "claude-code" => {
            // v2 M5：CC idle → 派发后台线程（解析/护栏/apply+emit 均在后台，
            // 本线程只派发——不阻塞 http 响应，N-3）。opencode.db 零查询。
            cc_dispatch(session_id);
        }
        other => {
            // 分流决策记录（低频：每 CC 轮次结束一条；排障时区分「CC idle 被
            // 正常分流跳过」与「事件没到达」）
            plog!("[pulsepet] idle hook: skip token report (agent={other}, unknown)");
        }
    }
}

fn make_idle_hook(
    state: &Arc<Mutex<SessionStateMachine>>,
    app: &tauri::AppHandle,
    cc_cache: &Arc<Mutex<transcript::TranscriptCache>>,
    notifier: &Arc<http_server::DisplayNotifier>,
) -> http_server::IdleHook {
    let state = state.clone();
    let app = app.clone();
    let cc_cache = cc_cache.clone();
    let notifier = notifier.clone();
    Arc::new(move |agent: &str, session_id: &str| {
        idle_hook_body(
            &state,
            &|text| {
                let _ = app.emit("pulsepet://bubble", serde_json::json!({ "text": text }));
            },
            &|sid, now| {
                let data_dir = token_stats::opencode_data_dir();
                // M3 §3.2：同连接一次查询（本期行 + 当日 SUM；失败时 today=None）
                token_stats::build_idle_report_with_today(
                    &data_dir,
                    sid,
                    now,
                    token_stats::report_max_lag_ms(),
                )
            },
            &|sid| {
                // v2 M5（§5.4，N-3）：后台线程内直接完成
                // 「解析（缓存未命中 scan 补建）→ 护栏判定 → apply + notify + emit」，
                // 不 join 回 http 线程（AppHandle/State 的 Arc 均 Send 可移入）。
                // 竞态诚实口径（P2-3）：护栏只防陈旧不防尾行未 flush——
                // Stop 先于 transcript 尾行落盘时可能欠计最后一条 message（接受）。
                let sid = sid.to_string();
                let state = state.clone();
                let app = app.clone();
                let cache = cc_cache.clone();
                let notifier = notifier.clone();
                std::thread::spawn(move || {
                    let now = token_stats::now_ms();
                    if let Some((text, today)) = token_stats::build_cc_idle_report(
                        &cache,
                        &token_stats::opencode_data_dir(),
                        &transcript::cc_projects_dir(),
                        &sid,
                        now,
                        token_stats::report_max_lag_ms(),
                    ) {
                        let full = match today {
                            Some(total) => {
                                let seg = crate::i18n::current()
                                    .token_report_today(&token_stats::format_tokens_k(total));
                                format!("{text}{seg}")
                            }
                            None => text,
                        };
                        {
                            let mut st = state.lock().unwrap_or_else(|p| p.into_inner());
                            // 复合键 claude-code:{sessionId}（P2-5）
                            st.apply_event("claude-code", &sid, Kind::Success, Instant::now());
                        }
                        // apply + notify 成对（后台线程内 apply 后立即推送，
                        // 不依赖 1s tick 兜底）
                        notifier.notify(&state);
                        let _ = app
                            .emit("pulsepet://bubble", serde_json::json!({ "text": full }));
                    }
                });
            },
            agent,
            session_id,
        )
    })
}

// ---------------------------------------------------------------------------
// v2 M3（V2-DESIGN §3.7.2）：工具播报开关——命令与持久化在 `interaction.rs`
// （跨窗口开关机制与穿透同款：app_state 键 + 定向广播；泛型命令需在子模块
// 定义，crate root 下 tauri::command 宏与 generate_handler 裸名冲突）。
// ---------------------------------------------------------------------------

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

            // ---- v2 M4（R5）：启动时幂等清理崩溃残留的 running 态 action_logs
            //      （正常退出走 RunEvent::Exit 补写；强杀路径无 Exit 在此结案）----
            {
                let db = app.state::<Mutex<Connection>>();
                let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
                let n = action_exec::cleanup_running_logs(&conn);
                if n > 0 {
                    plog!("[pulsepet] startup cleaned {n} stale running action log(s)");
                }
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
            // v2 M1 AgentActivity（V2-DESIGN §1.5 P2-3）：per-agent 最近事件时刻，
            // integrations_status 读取为 lastEventAt。与 state 同批 manage
            // （issue #9 铁律：窗口创建循环之前）。
            let activity = http_server::new_agent_activity();
            // v2 M5（V2-DESIGN §5.2，TC-M5-02）：CC transcript 文件级缓存
            // （managed state——查询命令与 CC idle hook 双方访问，P2-1；
            // issue #9 铁律：窗口创建循环之前 manage）。
            let cc_cache = Arc::new(Mutex::new(transcript::TranscriptCache::default()));
            // 显示状态变化 → Tauri event 推给前端（http-bridge → petStore）；
            // v2 M1 payload 携带归属 agent（前端只存不显示，向后兼容旧解析）
            let emit_handle = app.handle().clone();
            let notifier = Arc::new(http_server::DisplayNotifier::new(Arc::new(
                move |kind, agent| {
                    let _ = emit_handle.emit(
                        "pulsepet://state",
                        serde_json::json!({ "kind": kind.as_str(), "agent": agent }),
                    );
                },
            )));

            let server = http_server::start(
                state.clone(),
                notifier.clone(),
                make_idle_hook(&state, app.handle(), &cc_cache, &notifier),
                // v2 M3（§3.7.2，N8）：含非空 detail 的状态事件 → 定向 pet 窗
                // 透传字符串（不解析不判开关——App 侧过滤）
                {
                    let emit_handle = app.handle().clone();
                    Arc::new(move |detail: &str| {
                        let _ = emit_handle.emit_to(
                            "pet",
                            "pulsepet://tool-bubble",
                            serde_json::json!({ "detail": detail }),
                        );
                    })
                },
                token,
                activity.clone(),
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
            app.manage(activity);
            app.manage(cc_cache);
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

            // ---- v2 M4：exec 运行句柄登记表（RunEvent::Exit 退出处置用；
            //      issue #9 铁律：窗口创建循环之前 manage）----
            let running_tasks = Arc::new(Mutex::new(action_exec::RunningTasks::default()));
            app.manage(running_tasks);

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
            token_stats::token_stats_today,
            interaction::tool_broadcast_get,
            interaction::tool_broadcast_set,
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
            reminder_scheduler::reminders_snooze,
            reminder_scheduler::tasks_skip_once,
            reminder_scheduler::action_logs_list,
            reminder_scheduler::reminder_play_fireworks,
            reminder_scheduler::fireworks_ready,
            reminder_scheduler::fireworks_finished,
            plugins::plugins_list,
            plugins::plugins_set_enabled,
            i18n::ui_get_language,
            i18n::ui_set_language,
            theme::ui_get_theme,
            theme::ui_set_theme,
            integrations::integrations_status,
            integrations::integrations_install,
            integrations::integrations_uninstall,
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
            // v2 M4（P1-2）：退出处置——遍历运行句柄杀进程组 + action_logs 补写
            // failed「App 退出中断」（防孤儿进程继续执行副作用命令 + 重跑双份执行）
            action_exec::abort_all_on_exit(app_handle);
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

#[cfg(test)]
mod tests {
    //! v2 M1：idle hook 分流单测（TC-INT-11）——不依赖 Tauri AppHandle，
    //! 直接驱动 idle_hook_body（查询/下发以闭包注入）。

    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    // ---- v2 M2（TC-UI-03-3/TC-UI-06）：get_display_state 扩展返回 {kind, agent} ----

    #[test]
    fn get_display_state_returns_kind_and_agent() {
        let state = Arc::new(Mutex::new(SessionStateMachine::new()));
        // sessions 全空 → idle + 空 agent（前端优雅降级，TC-UI-03-4）
        let empty = display_state_dto(&state);
        assert_eq!(empty.kind, "idle");
        assert_eq!(empty.agent, "");

        // 注入事件后返回合并显示状态 + 归属 agent
        {
            let mut st = state.lock().unwrap_or_else(|p| p.into_inner());
            st.apply_event("claude-code", "cc-1", Kind::Working, Instant::now());
        }
        let dto = display_state_dto(&state);
        assert_eq!(dto.kind, "working");
        assert_eq!(dto.agent, "claude-code");
    }

    #[test]
    fn claude_code_idle_never_queries_opencode_db() {
        let state = Arc::new(Mutex::new(SessionStateMachine::new()));
        let queries = AtomicUsize::new(0);
        let emitted = AtomicUsize::new(0);
        let dispatched = AtomicUsize::new(0);
        idle_hook_body(
            &state,
            &|_| {
                emitted.fetch_add(1, Ordering::SeqCst);
            },
            &|_sid, _now| {
                queries.fetch_add(1, Ordering::SeqCst);
                Some(("本期用了 1k input / 0 output / $0".to_string(), None))
            },
            &|_sid| {
                dispatched.fetch_add(1, Ordering::SeqCst);
            },
            "claude-code",
            "cc-uuid-1",
        );
        assert_eq!(queries.load(Ordering::SeqCst), 0, "CC idle 不查 opencode.db");
        assert_eq!(emitted.load(Ordering::SeqCst), 0, "CC idle 无同步气泡/无 success 注入");
        assert_eq!(
            dispatched.load(Ordering::SeqCst),
            1,
            "CC idle → 派发后台线程（http 线程只派发，N-3）"
        );
        // 未知 agent 零查询零派发（白名单外值到不了这里，防御性钉住）
        idle_hook_body(
            &state,
            &|_| {},
            &|_sid, _now| {
                queries.fetch_add(1, Ordering::SeqCst);
                None
            },
            &|_sid| {
                dispatched.fetch_add(1, Ordering::SeqCst);
            },
            "codex",
            "x",
        );
        assert_eq!(queries.load(Ordering::SeqCst), 0);
        assert_eq!(dispatched.load(Ordering::SeqCst), 1, "未知 agent 不派发 CC 路径");
    }

    #[test]
    fn opencode_idle_reports_and_injects_success() {
        let state = Arc::new(Mutex::new(SessionStateMachine::new()));
        let bubbles = Mutex::new(Vec::<String>::new());
        let queries = AtomicUsize::new(0);
        let dispatched = AtomicUsize::new(0);
        idle_hook_body(
            &state,
            &|text| {
                bubbles.lock().unwrap().push(text);
            },
            &|sid, _now| {
                queries.fetch_add(1, Ordering::SeqCst);
                assert_eq!(sid, "ses_a");
                Some((
                    "本期用了 58.3k input / 910 output / $0.05".to_string(),
                    Some(42_000_000),
                ))
            },
            &|_sid| {
                dispatched.fetch_add(1, Ordering::SeqCst);
            },
            "opencode",
            "ses_a",
        );
        assert_eq!(queries.load(Ordering::SeqCst), 1, "opencode idle 查一次库");
        assert_eq!(dispatched.load(Ordering::SeqCst), 0, "opencode idle 不走 CC 派发");
        assert_eq!(
            bubbles.lock().unwrap().as_slice(),
            ["本期用了 58.3k input / 910 output / $0.05 · 今日 42.0M"],
            "M3：气泡末尾追加「 · 今日 42.0M」（format_tokens_k 同口径，TC-M3-09-1 逐字）"
        );
        // success 注入到状态机（复合键 opencode:ses_a）
        let st = state.lock().unwrap_or_else(|p| p.into_inner());
        let d = st.display();
        assert_eq!(d.kind, Kind::Success);
        assert_eq!(d.agent, "opencode");
    }

    #[test]
    fn opencode_idle_with_no_report_is_silent() {
        // 无记录/陈旧 → 静默跳过（不出气泡、不注入 success，TC-TK-12 不回归）
        let state = Arc::new(Mutex::new(SessionStateMachine::new()));
        let emitted = AtomicUsize::new(0);
        idle_hook_body(
            &state,
            &|_| {
                emitted.fetch_add(1, Ordering::SeqCst);
            },
            &|_sid, _now| None,
            &|_sid| {},
            "opencode",
            "ses_none",
        );
        assert_eq!(emitted.load(Ordering::SeqCst), 0);
        let st = state.lock().unwrap_or_else(|p| p.into_inner());
        assert_eq!(st.display().kind, Kind::Idle, "无汇报不注入 success");
    }

    #[test]
    fn opencode_idle_today_failure_omits_segment_silently() {
        // TC-M3-09-3（P2-6）：今日聚合失败（today=None，如跨午夜边界竞态）→
        // 静默省略追加段，本期数字照常显示
        let state = Arc::new(Mutex::new(SessionStateMachine::new()));
        let bubbles = Mutex::new(Vec::<String>::new());
        idle_hook_body(
            &state,
            &|text| bubbles.lock().unwrap().push(text),
            &|_sid, _now| {
                Some(("本期用了 58.3k input / 910 output / $0.05".to_string(), None))
            },
            &|_sid| {},
            "opencode",
            "ses_a",
        );
        assert_eq!(
            bubbles.lock().unwrap().as_slice(),
            ["本期用了 58.3k input / 910 output / $0.05"],
            "失败省略追加段——本期文案原样，无多余分隔符"
        );
    }

    #[test]
    fn opencode_idle_today_total_excludes_reasoning() {
        // 追加段 total = in + out + cache_read（reasoning 不计，SCOPE D 口径）；
        // 999_999_999 + 1 + 0 = 1000.0M
        let state = Arc::new(Mutex::new(SessionStateMachine::new()));
        let bubbles = Mutex::new(Vec::<String>::new());
        idle_hook_body(
            &state,
            &|text| bubbles.lock().unwrap().push(text),
            &|_sid, _now| Some(("本期用了 1 input / 0 output / $0".to_string(), Some(999_999_999 + 1))),
            &|_sid| {},
            "opencode",
            "ses_a",
        );
        let text = bubbles.lock().unwrap()[0].clone();
        assert!(text.ends_with(" · 今日 1000.0M"), "actual: {text}");
    }

    // ---- v2 M3：工具播报开关命令测试在 interaction.rs（命令随模块移驻） ----
}

#[cfg(test)]
mod order_nails {
    //! issue #9 铁律的源码级钉子（TC-INT-08-5）：AgentActivity 等 managed state
    //! 必须在窗口创建循环之前 app.manage()——「命令首次调用时惰性 manage」是
    //! Windows 闪退根因写法，禁止回归。

    #[test]
    fn agent_activity_managed_before_window_creation() {
        let src = include_str!("lib.rs");
        let manage_at = src
            .find("app.manage(activity)")
            .expect("lib.rs 须含 app.manage(activity)（issue #9）");
        let windows_at = src
            .find("for wc in app.config().app.windows.iter()")
            .expect("lib.rs 须含窗口创建循环");
        assert!(
            manage_at < windows_at,
            "AgentActivity 的 manage 必须在窗口创建循环之前（issue #9 铁律）"
        );
    }

    /// v2 M5（TC-M5-02-1）：TranscriptCache 的 manage 同样必须在窗口创建
    /// 循环之前（issue #9 铁律——查询命令/CC idle hook 双方访问的 managed
    /// state，Windows 上窗口先建会在 WebView 异步初始化期间派发 IPC 触发
    /// state() panic）。
    #[test]
    fn cc_transcript_cache_managed_before_window_creation() {
        let src = include_str!("lib.rs");
        let manage_at = src
            .find("app.manage(cc_cache)")
            .expect("lib.rs 须含 app.manage(cc_cache)（issue #9）");
        let windows_at = src
            .find("for wc in app.config().app.windows.iter()")
            .expect("lib.rs 须含窗口创建循环");
        assert!(
            manage_at < windows_at,
            "TranscriptCache 的 manage 必须在窗口创建循环之前（issue #9 铁律）"
        );
        // 状态构造也在窗口创建前（与 manage 同段）
        let construct_at = src
            .find("Arc::new(Mutex::new(transcript::TranscriptCache::default()))")
            .expect("lib.rs 须含 TranscriptCache 构造");
        assert!(construct_at < windows_at);
    }
}
