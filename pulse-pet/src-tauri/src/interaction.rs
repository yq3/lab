//! M6 交互模式（穿透开/关，DESIGN §6.3/§7.1，TC-APP-07/12、TC-WIN-02/04/05）。
//!
//! 穿透状态唯一权威在本模块（managed `InteractionState`）：
//! - 持久化到 app_state `pet.pass_through`（重启保留，TC-APP-12；默认 false
//!   非穿透 = 运行时可拖拽/右键，DESIGN §7.1"运行时默认非穿透"）；
//! - 三条切换通道共用 `set_pass_through`：全局热键（hotkeys）、托盘菜单
//!   （tray CheckMenuItem）、设置页开关 / 宠物右键菜单（pet_set_pass_through
//!   命令）——切换后统一：应用 `set_ignore_cursor_events` → 持久化 → 广播
//!   `pulsepet://pass-through` 事件（前端 petStore 同步）→ 同步托盘勾选态。
//!
//! 穿透开 = 纯展示（鼠标事件全部透出：不可拖拽、右键菜单不可达，TC-WIN-02/04）；
//! 穿透关 = 可交互（可拖拽 / 右键，TC-WIN-01/03）。tauri.conf.json 无
//! `ignoreCursorEvents` 配置字段（Tauri 2 schema 无此项），仅运行时切换。

use crate::plog;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

use rusqlite::Connection;
use tauri::{Emitter, Manager};

/// app_state 键：穿透开关（"true"/"false"）。
pub const KEY_PASS_THROUGH: &str = "pet.pass_through";

/// 前端同步事件名（与 src/lib/interaction.ts 的 PASS_THROUGH_EVENT 一致）。
pub const PASS_THROUGH_EVENT: &str = "pulsepet://pass-through";

/// 穿透状态（进程内快照；持久化真值在 app_state）。
pub struct InteractionState {
    pass_through: AtomicBool,
}

impl InteractionState {
    pub fn new(initial: bool) -> Self {
        Self {
            pass_through: AtomicBool::new(initial),
        }
    }

    pub fn get(&self) -> bool {
        self.pass_through.load(Ordering::SeqCst)
    }

    fn set(&self, enabled: bool) {
        self.pass_through.store(enabled, Ordering::SeqCst);
    }
}

/// 从 app_state 解析持久化的穿透开关；缺失 / 非法值 → false（默认非穿透）。
pub fn read_persisted(conn: &Connection) -> bool {
    match crate::db::get_state(conn, KEY_PASS_THROUGH) {
        Some(v) => v == "true" || v == "1",
        None => false,
    }
}

/// 持久化穿透开关（写 app_state）。
pub fn persist(conn: &Connection, enabled: bool) {
    let _ = crate::db::set_state(conn, KEY_PASS_THROUGH, if enabled { "true" } else { "false" });
}

/// 应用穿透状态到 pet 窗口 + 持久化 + 广播前端 + 同步托盘勾选态。
///
/// 幂等：重复设置同值无副作用。托盘未建（启动早期）时勾选同步安全跳过
/// （build_tray 构造时按真值初始化勾选）。
pub fn apply_pass_through(app: &tauri::AppHandle, enabled: bool) {
    // 1) 窗口：穿透开 = 鼠标事件全部透出；关 = 恢复可交互并聚焦（实测 macOS
    //    setIgnoresMouseEvents(false) 后首次鼠标事件可能仍被丢弃，set_focus
    //    让 WKWebView 立即重建交互，热键切回后即可拖拽/右键）
    if let Some(win) = app.get_webview_window("pet") {
        if let Err(e) = win.set_ignore_cursor_events(enabled) {
            plog!("[pulsepet] set_ignore_cursor_events({enabled}) failed: {e}");
        }
        if !enabled {
            let _ = win.set_focus();
        }
    }
    // 2) 内存快照 + 持久化（TC-APP-12 重启保留）
    if let Some(state) = app.try_state::<InteractionState>() {
        state.set(enabled);
    }
    if let Some(db) = app.try_state::<std::sync::Mutex<Connection>>() {
        if let Ok(conn) = db.lock() {
            persist(&conn, enabled);
        }
    }
    // 3) 广播前端（pet 拖拽/右键守卫 + panel 设置开关同步，TC-WIN-05）
    if let Err(e) = app.emit(PASS_THROUGH_EVENT, serde_json::json!({ "enabled": enabled })) {
        plog!("[pulsepet] emit {PASS_THROUGH_EVENT} failed: {e}");
    }
    // 4) 托盘 CheckMenuItem 勾选态同步（热键通道切换后托盘可见）
    if let Some(items) = app.try_state::<crate::tray::TrayItems>() {
        if let Ok(item) = items.interaction.lock() {
            if let Some(item) = item.as_ref() {
                let _ = item.set_checked(enabled);
            }
        }
    }
    plog!("[pulsepet] pass-through = {enabled}");
}

/// 翻转穿透（热键 / 托盘 / 右键菜单共用）。返回翻转后的值。
pub fn toggle(app: &tauri::AppHandle) -> bool {
    let current = app
        .try_state::<InteractionState>()
        .map(|s| s.get())
        .unwrap_or(false);
    let next = !current;
    apply_pass_through(app, next);
    next
}

/// 查询当前穿透状态（前端 initInteractionBridge 启动查询用）。
#[tauri::command]
pub fn pet_get_pass_through(state: tauri::State<'_, InteractionState>) -> bool {
    state.get()
}

/// 设置穿透状态（panel 设置开关 / PetMenu「切换交互模式」）。
#[tauri::command]
pub fn pet_set_pass_through(
    app: tauri::AppHandle,
    enabled: bool,
) -> Result<bool, String> {
    apply_pass_through(&app, enabled);
    Ok(enabled)
}

// ---------------------------------------------------------------------------
// v2 M3（V2-DESIGN §3.7.2，P1-3）：工具播报开关——跨窗口机制照穿透模式
//（panel/pet 双 webview 不共享 store：app_state 持久化 + get 初始化 +
// `pulsepet://tool-broadcast` 定向 pet 窗广播 → pet 桥 store 即时静默/恢复）。
// ---------------------------------------------------------------------------

/// app_state 键：工具播报开关（"true"/"false"；缺省 true = 默认开）。
pub const KEY_TOOL_BROADCAST: &str = "bubble.toolBroadcast";

/// 工具播报广播事件名（`tool_broadcast_set` 后定向 pet 窗下发；与前端
/// tool-bubble-bridge.ts 的常量一致）。
pub const TOOL_BROADCAST_EVENT: &str = "pulsepet://tool-broadcast";

/// 读取持久化的工具播报开关：**缺省 true、非法值回退 true**（默认开；
/// 仅显式 "false"/"0" 视为关——与穿透的 false 缺省语义相反，§3.7.2）。
pub fn read_tool_broadcast(conn: &Connection) -> bool {
    !matches!(
        crate::db::get_state(conn, KEY_TOOL_BROADCAST).as_deref(),
        Some("false") | Some("0")
    )
}

/// 查询工具播报开关（pet 桥启动初始化 + panel 设置页初始显示值，N13）。
#[tauri::command]
pub fn tool_broadcast_get<R: tauri::Runtime>(app: tauri::AppHandle<R>) -> Result<bool, String> {
    let db = app.state::<Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    Ok(read_tool_broadcast(&conn))
}

/// 设置工具播报开关：持久化 → 定向 pet 窗广播（pet 桥 store 即时静默/恢复，
/// 无需重启——TC-M3-16-2）。panel 是唯一写入方，自身展示由调用方乐观更新。
#[tauri::command]
pub fn tool_broadcast_set<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    enabled: bool,
) -> Result<bool, String> {
    {
        let db = app.state::<Mutex<Connection>>();
        let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
        crate::db::set_state(&conn, KEY_TOOL_BROADCAST, if enabled { "true" } else { "false" })
            .map_err(|e| format!("persist tool broadcast: {e}"))?;
    }
    let _ = app.emit_to(
        "pet",
        TOOL_BROADCAST_EVENT,
        serde_json::json!({ "enabled": enabled }),
    );
    plog!("[pulsepet] tool broadcast = {enabled}");
    Ok(enabled)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn conn() -> Connection {
        let c = Connection::open_in_memory().unwrap();
        crate::db::migrate(&c).unwrap();
        c
    }

    #[test]
    fn persisted_default_is_interactive() {
        // 无记录 → false：运行时默认非穿透（DESIGN §7.1 / TC-APP-01②）
        assert!(!read_persisted(&conn()));
    }

    #[test]
    fn persist_round_trip_and_legal_values() {
        let c = conn();
        persist(&c, true);
        assert!(read_persisted(&c));
        persist(&c, false);
        assert!(!read_persisted(&c));
        // 历史值兼容："1" 视为 true；垃圾值 / "0" 视为 false（不 panic）
        crate::db::set_state(&c, KEY_PASS_THROUGH, "1").unwrap();
        assert!(read_persisted(&c));
        crate::db::set_state(&c, KEY_PASS_THROUGH, "0").unwrap();
        assert!(!read_persisted(&c));
        crate::db::set_state(&c, KEY_PASS_THROUGH, "garbage").unwrap();
        assert!(!read_persisted(&c));
    }

    #[test]
    fn interaction_state_get_set() {
        let s = InteractionState::new(false);
        assert!(!s.get());
        s.set(true);
        assert!(s.get());
        s.set(false);
        assert!(!s.get());
    }

    // ---- v2 M3：工具播报开关（§3.7.2，TC-M3-14-5 / TC-M3-16-1） ----

    #[test]
    fn tool_broadcast_read_defaults_true_and_falls_back_on_garbage() {
        let c = conn();
        assert!(read_tool_broadcast(&c), "缺省 true（默认开）");
        for v in ["garbage", "", "1", "true"] {
            crate::db::set_state(&c, KEY_TOOL_BROADCAST, v).unwrap();
            assert!(read_tool_broadcast(&c), "值 {v:?} → true（非法回退/显式开）");
        }
        for v in ["false", "0"] {
            crate::db::set_state(&c, KEY_TOOL_BROADCAST, v).unwrap();
            assert!(!read_tool_broadcast(&c), "值 {v:?} → false（显式关）");
        }
    }

    #[test]
    fn tool_broadcast_commands_roundtrip_and_broadcast() {
        // mock runtime：managed db + 事件广播断言（照 theme.rs 命令级模式）
        use std::sync::mpsc;
        use tauri::Listener;
        let app = tauri::test::mock_app();
        let handle = app.handle();
        handle.manage(Mutex::new(conn()));
        // emit_to 定向 pet 窗：mock runtime 建同 label 窗口 + 窗口级 listener
        //（emit_to 的 label 过滤只匹配 Window/Webview target，app-level listen
        //  的 Any target 收不到——与真实 pet 窗 JS listen 同语义）
        let pet = tauri::WebviewWindowBuilder::new(
            handle,
            "pet",
            tauri::WebviewUrl::default(),
        )
        .build()
        .unwrap();

        // 缺省 true（N13：panel 初始显示值经 get 初始化）
        assert!(tool_broadcast_get(handle.clone()).unwrap());

        // set → 持久化 + 定向 pet 窗广播 payload {enabled}
        let (tx, rx) = mpsc::channel::<bool>();
        let tx = Mutex::new(tx);
        pet.listen(TOOL_BROADCAST_EVENT, move |event| {
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(event.payload()) {
                if let Some(b) = v["enabled"].as_bool() {
                    let _ = tx.lock().unwrap().send(b);
                }
            }
        });
        tool_broadcast_set(handle.clone(), false).unwrap();
        assert_eq!(
            rx.recv_timeout(std::time::Duration::from_secs(2)).unwrap(),
            false,
            "set(false) → tool-broadcast 广播 enabled:false"
        );
        assert!(!tool_broadcast_get(handle.clone()).unwrap(), "写入后可回读");
        tool_broadcast_set(handle.clone(), true).unwrap();
        assert_eq!(
            rx.recv_timeout(std::time::Duration::from_secs(2)).unwrap(),
            true
        );
        assert!(tool_broadcast_get(handle.clone()).unwrap(), "重开恢复");
    }
}
