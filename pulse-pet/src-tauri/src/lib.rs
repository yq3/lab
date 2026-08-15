mod db;
mod tray;
mod windows;

use std::sync::Mutex;

use tauri::{Manager, RunEvent, WindowEvent};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            // 第二实例启动：唤起已运行实例的 panel 窗口（TC-APP-02）
            eprintln!("[pulsepet] second instance detected, showing panel");
            windows::show_panel(app);
        }))
        .setup(|app| {
            let conn = db::init(app.handle())?;
            app.manage(Mutex::new(conn));
            windows::restore_pet_position(app.handle());
            tray::build_tray(app.handle())?;
            Ok(())
        })
        .on_window_event(|window, event| match event {
            WindowEvent::CloseRequested { api, .. } if window.label() == "panel" => {
                // 关闭控制面板时隐藏而非销毁，托盘可再次唤起
                api.prevent_close();
                let _ = window.hide();
            }
            WindowEvent::Moved(_) if window.label() == "pet" => {
                windows::save_pet_position(window.app_handle());
            }
            _ => {}
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            // 退出时兜底保存位置（正常拖拽期间已由 Moved 事件持续保存）
            windows::save_pet_position(app_handle);
        }
    });
}
