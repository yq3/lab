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

use std::sync::atomic::{AtomicBool, Ordering};

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
            eprintln!("[pulsepet] set_ignore_cursor_events({enabled}) failed: {e}");
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
        eprintln!("[pulsepet] emit {PASS_THROUGH_EVENT} failed: {e}");
    }
    // 4) 托盘 CheckMenuItem 勾选态同步（热键通道切换后托盘可见）
    if let Some(items) = app.try_state::<crate::tray::TrayItems>() {
        if let Ok(item) = items.interaction.lock() {
            if let Some(item) = item.as_ref() {
                let _ = item.set_checked(enabled);
            }
        }
    }
    eprintln!("[pulsepet] pass-through = {enabled}");
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
}
