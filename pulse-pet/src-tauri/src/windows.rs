//! pet / panel / fireworks 窗口管理（DESIGN §7.1）。
//! M1 只负责：panel 唤起、pet 可见性切换、pet 位置保存/恢复。

use std::sync::Mutex;

use rusqlite::Connection;
use tauri::{Manager, PhysicalPosition};

const KEY_X: &str = "pet.position.x";
const KEY_Y: &str = "pet.position.y";

/// 唤起控制面板窗口（托盘菜单 / 单实例锁第二实例触发）。
pub fn show_panel(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("panel") {
        let _ = win.show();
        let _ = win.set_focus();
    }
}

/// 切换 pet 窗口可见性（托盘左键 / 托盘菜单项）。
pub fn toggle_pet(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("pet") {
        if win.is_visible().unwrap_or(false) {
            let _ = win.hide();
        } else {
            let _ = win.show();
            let _ = win.set_focus();
        }
    }
}

/// 启动时从 app_state 恢复 pet 位置（M1 单显示器基础实现）。
pub fn restore_pet_position(app: &tauri::AppHandle) {
    let Some(win) = app.get_webview_window("pet") else {
        return;
    };
    let Some(state) = app.try_state::<Mutex<Connection>>() else {
        return;
    };
    let Ok(conn) = state.lock() else {
        return;
    };
    let x = crate::db::get_state(&conn, KEY_X).and_then(|s| s.parse::<i32>().ok());
    let y = crate::db::get_state(&conn, KEY_Y).and_then(|s| s.parse::<i32>().ok());
    if let (Some(x), Some(y)) = (x, y) {
        let _ = win.set_position(PhysicalPosition::new(x, y));
        eprintln!("[pulsepet] restored pet position: ({x}, {y})");
    } else {
        eprintln!("[pulsepet] no saved pet position");
    }
}

/// 把 pet 当前位置写入 app_state（Moved 事件 + 退出时调用）。
pub fn save_pet_position(app: &tauri::AppHandle) {
    let Some(win) = app.get_webview_window("pet") else {
        return;
    };
    let Ok(pos) = win.outer_position() else {
        return;
    };
    let Some(state) = app.try_state::<Mutex<Connection>>() else {
        return;
    };
    let Ok(conn) = state.lock() else {
        return;
    };
    let _ = crate::db::set_state(&conn, KEY_X, &pos.x.to_string());
    let _ = crate::db::set_state(&conn, KEY_Y, &pos.y.to_string());
    eprintln!("[pulsepet] saved pet position: ({}, {})", pos.x, pos.y);
}
