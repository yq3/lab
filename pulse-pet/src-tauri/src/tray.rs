//! 系统托盘（DESIGN §7.2）。
//!
//! M1 菜单项仅 3 项：显示/隐藏宠物、打开控制面板、退出。
//! （"切换交互模式" 随 M6、"暂停所有提醒" 随 M4 补全。）
//!
//! 左键单击切换 pet 可见性：`TrayIconEvent::Click` 在 Down/Up 各触发一次，
//! 因此必须判断 `button_state`（只处理 Down），否则一次单击会连切两次（todo-lite 同坑）。

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
};

use crate::windows;

pub fn build_tray(app: &tauri::AppHandle) -> tauri::Result<()> {
    let toggle = MenuItem::with_id(app, "toggle", "显示/隐藏宠物", true, None::<&str>)?;
    let panel = MenuItem::with_id(app, "panel", "打开控制面板", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&toggle, &panel, &quit])?;
    let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/32x32.png"))?;

    TrayIconBuilder::with_id("pulsepet-tray")
        .icon(icon)
        .tooltip("PulsePet")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "toggle" => windows::toggle_pet(app),
            "panel" => windows::show_panel(app),
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

    eprintln!("[pulsepet] tray built");
    Ok(())
}
