//! 系统托盘（DESIGN §7.2）。
//!
//! M1 菜单项 3 项：显示/隐藏宠物、打开控制面板、退出。
//! M4 补全："暂停所有提醒"（勾选态开关，TC-RM-08，持久化 app_state
//! `reminders.paused`，暂停期间调度器不触发任何提醒，取消即恢复）。
//! （"切换交互模式" 随 M6 补全。）
//!
//! 左键单击切换 pet 可见性：`TrayIconEvent::Click` 在 Down/Up 各触发一次，
//! 因此必须判断 `button_state`（只处理 Down），否则一次单击会连切两次（todo-lite 同坑）。

use std::sync::{Arc, Mutex};

use rusqlite::Connection;
use tauri::{
    menu::{CheckMenuItem, Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager,
};

use crate::reminder_scheduler::{self, RemindersState};
use crate::windows;

pub fn build_tray(app: &tauri::AppHandle) -> tauri::Result<()> {
    let toggle = MenuItem::with_id(app, "toggle", "显示/隐藏宠物", true, None::<&str>)?;
    let panel = MenuItem::with_id(app, "panel", "打开控制面板", true, None::<&str>)?;
    // TC-RM-08：初始勾选态从 app_state 恢复（重启保持勿扰状态）
    let paused = app
        .try_state::<Mutex<Connection>>()
        .map(|db| {
            db.lock()
                .ok()
                .map(|conn| reminder_scheduler::is_paused(&conn))
                .unwrap_or(false)
        })
        .unwrap_or(false);
    let pause_reminders =
        CheckMenuItem::with_id(app, "pause_reminders", "暂停所有提醒", true, paused, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&toggle, &panel, &pause_reminders, &quit])?;
    let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/32x32.png"))?;

    TrayIconBuilder::with_id("pulsepet-tray")
        .icon(icon)
        .tooltip("PulsePet")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "toggle" => windows::toggle_pet(app),
            "panel" => windows::show_panel(app),
            "pause_reminders" => toggle_pause_reminders(app),
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Down,
                ..
            } = event
            {
                windows::toggle_pet(tray.app_handle());
            }
        })
        .build(app)?;

    eprintln!("[pulsepet] tray built (pause_reminders checked={paused})");
    Ok(())
}

/// 托盘"暂停所有提醒"：翻转调度器 paused + 持久化 app_state + 同步菜单勾选态。
fn toggle_pause_reminders(app: &tauri::AppHandle) {
    let next = {
        let Some(state) = app.try_state::<Arc<Mutex<RemindersState>>>() else {
            return;
        };
        let Ok(mut st) = state.lock() else {
            return;
        };
        st.paused = !st.paused;
        st.paused
    };
    if let Some(db) = app.try_state::<Mutex<Connection>>() {
        if let Ok(conn) = db.lock() {
            reminder_scheduler::set_paused(&conn, next);
        }
    }
    if let Some(item) = app
        .menu()
        .and_then(|m| m.get("pause_reminders"))
        .and_then(|kind| kind.as_check_menuitem().cloned())
    {
        let _ = item.set_checked(next);
    }
    eprintln!("[pulsepet] reminders paused = {next} (tray)");
}
