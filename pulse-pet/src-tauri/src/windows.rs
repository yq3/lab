//! pet / panel / fireworks 窗口管理（DESIGN §7.1）。
//! M1：panel 唤起、pet 可见性切换、pet 位置保存/恢复。
//! M2：pet 位置保存 ~150ms trailing 防抖（P2-5）、恢复位置 clamp 到可视范围（P2-6）。

use std::sync::mpsc::{self, RecvTimeoutError};
use std::sync::Mutex;
use std::time::Duration;

use rusqlite::Connection;
use tauri::{Manager, PhysicalPosition};

const KEY_X: &str = "pet.position.x";
const KEY_Y: &str = "pet.position.y";

/// Moved 事件防抖时长（P2-5：避免拖拽过程每次同步写 2 条 SQL）。
const MOVE_DEBOUNCE_MS: u64 = 150;

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

/// 纯函数：把窗口左上角 clamp 到给定显示器可视范围（P2-6，可单测）。
///
/// `(mon_x, mon_y, mon_w, mon_h)` 为显示器物理坐标与尺寸，`(win_w, win_h)` 为窗口
/// 物理尺寸。窗口尺寸大于显示器时退化为贴左上角（`max(mon_x)` 保证下界不越上界）。
pub fn clamp_position(
    x: i32,
    y: i32,
    win_w: i32,
    win_h: i32,
    mon_x: i32,
    mon_y: i32,
    mon_w: i32,
    mon_h: i32,
) -> (i32, i32) {
    let max_x = (mon_x + mon_w - win_w).max(mon_x);
    let max_y = (mon_y + mon_h - win_h).max(mon_y);
    (x.clamp(mon_x, max_x), y.clamp(mon_y, max_y))
}

/// 启动时从 app_state 恢复 pet 位置，并 clamp 到 current_monitor 可视范围（P2-6）。
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
        let (cx, cy) = clamp_to_current_monitor(&win, x, y);
        let _ = win.set_position(PhysicalPosition::new(cx, cy));
        eprintln!("[pulsepet] restored pet position: ({cx}, {cy})");
    } else {
        eprintln!("[pulsepet] no saved pet position");
    }
}

/// 把给定坐标 clamp 到窗口当前所在显示器（取不到显示器则原样返回）。
fn clamp_to_current_monitor(
    win: &tauri::WebviewWindow,
    x: i32,
    y: i32,
) -> (i32, i32) {
    let Ok(Some(mon)) = win.current_monitor() else {
        return (x, y);
    };
    let Ok(out) = win.outer_size() else {
        return (x, y);
    };
    let pos = mon.position();
    let size = mon.size();
    clamp_position(
        x,
        y,
        out.width as i32,
        out.height as i32,
        pos.x,
        pos.y,
        size.width as i32,
        size.height as i32,
    )
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

/// Moved 事件的 trailing 防抖保存器（P2-5）。
///
/// 后台线程合并 150ms 内的连续 Moved 事件：静默窗口结束才真正落库，避免拖拽时
/// 每次 Moved 同步写 2 条 SQL。
pub struct PositionSaver {
    tx: mpsc::Sender<()>,
}

impl PositionSaver {
    pub fn new(app: tauri::AppHandle) -> Self {
        let (tx, rx) = mpsc::channel::<()>();
        std::thread::spawn(move || {
            loop {
                // 等待首个保存请求
                if rx.recv().is_err() {
                    break;
                }
                // trailing 防抖：继续等待，直到 150ms 内无新事件才落库
                loop {
                    match rx.recv_timeout(Duration::from_millis(MOVE_DEBOUNCE_MS)) {
                        Ok(()) => continue,
                        Err(RecvTimeoutError::Timeout) => break,
                        Err(RecvTimeoutError::Disconnected) => return,
                    }
                }
                save_pet_position(&app);
            }
        });
        Self { tx }
    }

    /// 通知保存器「发生了一次移动」（防抖合并）。
    pub fn request_save(&self) {
        let _ = self.tx.send(());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clamp_keeps_position_inside_monitor() {
        // 显示器 0,0 → 1920×1080，窗口 220×220，位置 (100,150) 完全在内部 → 不变
        assert_eq!(clamp_position(100, 150, 220, 220, 0, 0, 1920, 1080), (100, 150));
    }

    #[test]
    fn clamp_pulls_offscreen_position_back() {
        // 位置超出右下角 → clamp 到可完全显示的右下角
        assert_eq!(clamp_position(2000, 2000, 220, 220, 0, 0, 1920, 1080), (1700, 860));
        // 位置为负（左上角越界）→ clamp 到 0
        assert_eq!(clamp_position(-100, -50, 220, 220, 0, 0, 1920, 1080), (0, 0));
    }

    #[test]
    fn clamp_on_secondary_monitor_coordinates() {
        // 次显示器从 x=1920 起
        assert_eq!(clamp_position(1900, 100, 220, 220, 1920, 0, 1920, 1080), (1920, 100));
    }

    #[test]
    fn clamp_window_larger_than_monitor_degrades_to_top_left() {
        // 窗口比显示器还大 → 退化贴左上角，不 panic
        assert_eq!(clamp_position(500, 500, 4000, 4000, 0, 0, 1920, 1080), (0, 0));
    }
}
