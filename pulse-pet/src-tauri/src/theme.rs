//! v2 M2 主题机制（V2-DESIGN §2.3/§2.7，TC-UI-02）。
//!
//! 照 `ui.language` 模式（i18n.rs）：偏好持久化在 app_state 键 `ui.theme`
//! （"auto"|"light"|"dark"，缺省 auto），`ui_set_theme` 写库 + `ui://theme`
//! 广播（**仅 panel 窗消费**——主题只作用于 panel；pet 窗气泡/菜单走
//! `--pet-world-*` 固定色，fireworks 无文案）。Rust 自身无主题消费面
//! （托盘是原生的），不持有进程级主题位。
//!
//! 前端 `resolveTheme(preference, systemDark)` 负责 auto → 系统偏好的解析
//! 与 `prefers-color-scheme` 联动；Rust 只存/广播原始偏好值。

use crate::plog;
use std::sync::Mutex;

use rusqlite::Connection;
use tauri::{Emitter, Manager};

/// app_state key：主题偏好（"auto"|"light"|"dark"；缺省 = auto 跟随系统）。
pub const KEY_THEME: &str = "ui.theme";

/// 前端主题偏好变化广播事件名（`ui_set_theme` 下发，panel 窗订阅）。
pub const THEME_EVENT: &str = "ui://theme";

/// 解析并规范化主题偏好（trim 容忍；非法 → None）。
pub fn parse_theme(s: &str) -> Option<&'static str> {
    match s.trim() {
        "auto" => Some("auto"),
        "light" => Some("light"),
        "dark" => Some("dark"),
        _ => None,
    }
}

/// 读持久化偏好（无值 / 非法值 → None，前端回退 auto——非法值拒绝/回退口径）。
pub fn read_theme(conn: &Connection) -> Option<String> {
    crate::db::get_state(conn, KEY_THEME).and_then(|s| parse_theme(&s).map(String::from))
}

/// 写入核心：持久化并返回规范化后的值（命令层组装事件 payload）。
pub fn write_theme(conn: &Connection, theme: &str) -> Result<String, String> {
    let v = parse_theme(theme)
        .ok_or_else(|| format!("theme 非法：{theme}（应为 auto/light/dark）"))?;
    crate::db::set_state(conn, KEY_THEME, v).map_err(|e| format!("persist theme: {e}"))?;
    Ok(v.to_string())
}

/// 启动查询：持久化主题偏好（None = 未设置，前端回退 auto）。
#[tauri::command]
pub fn ui_get_theme<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
) -> Result<Option<String>, String> {
    let db = app.state::<Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    Ok(read_theme(&conn))
}

/// 设置页切换：持久化 + `ui://theme` 广播（仅 panel 窗消费）。
#[tauri::command]
pub fn ui_set_theme<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    theme: String,
) -> Result<(), String> {
    let value = {
        let db = app.state::<Mutex<Connection>>();
        let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
        write_theme(&conn, &theme)?
    };
    // 广播 payload {theme}（panel 窗 theme-bridge 订阅后应用 data-theme）
    let _ = app.emit(THEME_EVENT, serde_json::json!({ "theme": value }));
    plog!("[pulsepet] ui theme set to {value}");
    Ok(())
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
    fn parse_theme_accepts_three_values_and_trims() {
        assert_eq!(parse_theme("auto"), Some("auto"));
        assert_eq!(parse_theme("light"), Some("light"));
        assert_eq!(parse_theme("dark"), Some("dark"));
        assert_eq!(parse_theme(" dark "), Some("dark"));
        assert_eq!(parse_theme("Dark"), None, "大小写敏感");
        assert_eq!(parse_theme("blue"), None);
        assert_eq!(parse_theme(""), None);
    }

    #[test]
    fn read_theme_missing_returns_none() {
        let c = conn();
        assert_eq!(read_theme(&c), None, "缺省 = auto（前端跟随系统）");
    }

    #[test]
    fn read_theme_illegal_value_falls_back_to_none() {
        let c = conn();
        crate::db::set_state(&c, KEY_THEME, "solarized").unwrap();
        assert_eq!(read_theme(&c), None, "非法持久化值 → None（回退 auto）");
    }

    #[test]
    fn write_theme_persists_and_returns_normalized() {
        let c = conn();
        assert_eq!(write_theme(&c, " dark "), Ok("dark".to_string()));
        assert_eq!(read_theme(&c).as_deref(), Some("dark"));
    }

    #[test]
    fn write_theme_rejects_illegal_value() {
        let c = conn();
        assert!(write_theme(&c, "blue").is_err());
        assert_eq!(read_theme(&c), None, "非法值不落库");
    }

    // ---- 命令级集成（mock runtime：managed db + 事件广播断言，TC-UI-02-3） ----

    #[test]
    fn commands_roundtrip_and_broadcast_via_mock_runtime() {
        use std::sync::mpsc;
        use tauri::Listener;
        let app = tauri::test::mock_app();
        let handle = app.handle();
        let c = conn();
        handle.manage(Mutex::new(c));

        // 缺省：get → None（前端回退 auto）
        assert_eq!(ui_get_theme(handle.clone()).unwrap(), None);

        // set 持久化 + ui://theme 广播（panel 窗消费的 payload {theme}）
        let (tx, rx) = mpsc::channel::<String>();
        let tx = Mutex::new(tx);
        handle.listen(THEME_EVENT, move |event| {
            let v = serde_json::from_str::<serde_json::Value>(event.payload()).ok();
            if let Some(theme) = v.and_then(|j| j["theme"].as_str().map(String::from)) {
                let _ = tx.lock().unwrap().send(theme);
            }
        });
        ui_set_theme(handle.clone(), "dark".to_string()).unwrap();
        assert_eq!(rx.recv_timeout(std::time::Duration::from_secs(2)).unwrap(), "dark");
        assert_eq!(
            ui_get_theme(handle.clone()).unwrap().as_deref(),
            Some("dark"),
            "写入后可回读（重启保留）"
        );

        // 非法值：命令拒绝（Err），持久化值不被破坏
        assert!(ui_set_theme(handle.clone(), "neon".to_string()).is_err());
        assert_eq!(ui_get_theme(handle.clone()).unwrap().as_deref(), Some("dark"));
    }
}
