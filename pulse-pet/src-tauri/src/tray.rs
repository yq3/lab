//! 系统托盘（DESIGN §7.2）。
//!
//! M1 菜单项 3 项：显示/隐藏宠物、打开控制面板、退出。
//! M4 补全："暂停所有提醒"（勾选态开关，TC-RM-08，持久化 app_state
//! `reminders.paused`，暂停期间调度器不触发任何提醒，取消即恢复）。
//! M6 补全："切换交互模式（穿透开/关）"CheckMenuItem（TC-APP-04/05、
//! TC-WIN-04/05）——勾选 = 穿透开启；与全局热键共用 interaction::toggle，
//! 切换后勾选态经 TrayItems 同步（穿透态下托盘仍是系统级菜单，可切回）。
//! 完整五项：显示/隐藏宠物、切换交互模式、打开控制面板、暂停所有提醒、退出。
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

use crate::interaction::{self, InteractionState};
use crate::reminder_scheduler::{self, RemindersState};
use crate::windows;

/// 托盘 CheckMenuItem 句柄（供菜单外的通道——全局热键 / 设置页——同步勾选态；
/// Tauri 2 的 `app.menu()` 只取应用菜单栏，不含托盘菜单，必须自持句柄）。
#[derive(Default)]
pub struct TrayItems {
    pub pause_reminders: Mutex<Option<CheckMenuItem<tauri::Wry>>>,
    pub interaction: Mutex<Option<CheckMenuItem<tauri::Wry>>>,
}

pub fn build_tray(app: &tauri::AppHandle) -> tauri::Result<()> {
    let toggle = MenuItem::with_id(app, "toggle", "显示/隐藏宠物", true, None::<&str>)?;
    // M6：切换交互模式（穿透开/关）。初始勾选 = 持久化的穿透状态。
    let pass_through = app
        .try_state::<InteractionState>()
        .map(|s| s.get())
        .unwrap_or(false);
    let interaction_item = CheckMenuItem::with_id(
        app,
        "interaction",
        "切换交互模式（穿透开/关）",
        true,
        pass_through,
        None::<&str>,
    )?;
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
    // DESIGN §7.2 顺序：显示/隐藏宠物、切换交互模式、打开控制面板、暂停所有提醒、退出
    let menu = Menu::with_items(
        app,
        &[&toggle, &interaction_item, &panel, &pause_reminders, &quit],
    )?;
    let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/32x32.png"))?;

    // 句柄登记进 TrayItems（热键/设置通道切换后同步勾选态用）
    if let Some(items) = app.try_state::<TrayItems>() {
        *items.pause_reminders.lock().unwrap() = Some(pause_reminders.clone());
        *items.interaction.lock().unwrap() = Some(interaction_item.clone());
    }

    TrayIconBuilder::with_id("pulsepet-tray")
        .icon(icon)
        .tooltip("PulsePet")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "toggle" => windows::toggle_pet(app),
            "interaction" => {
                // CheckMenuItem 点击后系统自动翻转勾选；真正状态以 interaction
                // 权威翻转结果再同步一次（防 apply 失败时勾选错位）
                interaction::toggle(app);
            }
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

    eprintln!(
        "[pulsepet] tray built (pause_reminders checked={paused}, interaction checked={pass_through})"
    );
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
    // M6：句柄直连托盘菜单项（原 app.menu() 路径只覆盖应用菜单栏，托盘项取不到）
    if let Some(items) = app.try_state::<TrayItems>() {
        if let Ok(slot) = items.pause_reminders.lock() {
            if let Some(item) = slot.as_ref() {
                let _ = item.set_checked(next);
            }
        }
    }
    eprintln!("[pulsepet] reminders paused = {next} (tray)");
}
