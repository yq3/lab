//! M6 全局快捷键（DESIGN §7.3，TC-APP-06/07/08、TC-WIN-07）。
//!
//! | 热键 | macOS | Win/Linux | 动作 |
//! |---|---|---|---|
//! | 唤起控制面板 | ⌘+Shift+P | Ctrl+Shift+P | 切换 panel 可见（与托盘同一窗口，天然同步） |
//! | 切换宠物穿透 | ⌘+Shift+Alt+P | Ctrl+Shift+Alt+P | interaction::toggle（TC-APP-07） |
//! | 调试烟花 | ⌘+Shift+Alt+F | Ctrl+Shift+Alt+F | 手动放一束（**仅 debug 构建**，TC-WIN-07） |
//!
//! - 调试烟花热键 v1 release 构建移除：`hotkey_specs()` 内部以
//!   `cfg!(debug_assertions)` 编译期常量过滤——release 下该分支被常量折叠 +
//!   死代码消除，规格表里根本没有 Alt+F（可验证依据：①单测断言规格表与
//!   `cfg!(debug_assertions)` 一致，`cargo test --release` 同样成立；②release
//!   构建运行日志只注册前两枚热键）。
//! - 与 opencode 默认热键（Ctrl+O 等）不冲突（TC-APP-08）：全部热键都含
//!   Shift 修饰，与 Ctrl+O / Ctrl+C 等 opencode TUI 默认组合无一是相同组合，
//!   单测固化。
//! - 仅 Rust 侧使用插件 API（注册 + 分发），无 JS 插件包依赖。

use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

/// 热键动作（dispatch 用；DebugFireworks 仅 debug 构建出现在规格表）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HotkeyAction {
    /// 切换 panel 可见（TC-APP-06）。
    TogglePanel,
    /// 切换宠物穿透（TC-APP-07 / TC-WIN-05）。
    TogglePassThrough,
    /// 调试烟花：手动放一束（TC-WIN-07；release 不注册）。
    DebugFireworks,
}

/// 一枚热键的注册规格。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct HotkeySpec {
    pub action: HotkeyAction,
    /// global-hotkey 加速器字符串（CmdOrCtrl 跨平台映射 ⌘/Ctrl）。
    pub accel: &'static str,
}

/// opencode TUI 默认热键（文档口径"Ctrl+O 等"；代码级对照用，TC-APP-08）。
/// 仅单测引用（no_overlap_with_opencode_defaults），运行时不查表。
#[cfg_attr(not(test), allow(dead_code))]
const OPENCODE_DEFAULT_ACCELS: &[&str] = &[
    "Ctrl+O", "Ctrl+L", "Ctrl+C", "Ctrl+T", "Ctrl+B", "Ctrl+K", "Ctrl+G", "Ctrl+Y",
];

/// 全部热键规格。debug 构建 3 枚（含调试烟花），release 2 枚（TC-WIN-07）。
pub fn hotkey_specs() -> Vec<HotkeySpec> {
    let mut specs = vec![
        HotkeySpec {
            action: HotkeyAction::TogglePanel,
            accel: "CmdOrCtrl+Shift+P",
        },
        HotkeySpec {
            action: HotkeyAction::TogglePassThrough,
            accel: "CmdOrCtrl+Shift+Alt+P",
        },
    ];
    if cfg!(debug_assertions) {
        specs.push(HotkeySpec {
            action: HotkeyAction::DebugFireworks,
            accel: "CmdOrCtrl+Shift+Alt+F",
        });
    }
    specs
}

/// 归一化加速器串用于相等比较：CmdOrCtrl→Ctrl、小写、去空格（仅单测引用）。
#[cfg_attr(not(test), allow(dead_code))]
fn accel_normalized(accel: &str) -> String {
    accel
        .replace("CmdOrCtrl", "Ctrl")
        .replace(" ", "")
        .to_lowercase()
}

/// 热键分发（单点出口，运行时动作都走这里；日志作为实测证据链）。
fn dispatch(app: &tauri::AppHandle, action: HotkeyAction) {
    match action {
        HotkeyAction::TogglePanel => {
            eprintln!("[pulsepet] hotkey: toggle panel");
            crate::windows::toggle_panel(app);
        }
        HotkeyAction::TogglePassThrough => {
            eprintln!("[pulsepet] hotkey: toggle pass-through");
            crate::interaction::toggle(app);
        }
        HotkeyAction::DebugFireworks => {
            eprintln!("[pulsepet] hotkey: debug fireworks");
            crate::reminder_scheduler::play_debug_fireworks(app);
        }
    }
}

/// 注册全部热键（lib.rs setup 调用；重复注册同组合会报错，正常启动只调一次）。
pub fn register_all(app: &tauri::AppHandle) -> Result<(), tauri_plugin_global_shortcut::Error> {
    let gs = app.global_shortcut();
    for spec in hotkey_specs() {
        let action = spec.action;
        gs.on_shortcut(spec.accel, move |_app, _shortcut, event| {
            // 只响应按下（松开会再发一次 Released，翻转类动作必须去重）
            if event.state() == ShortcutState::Pressed {
                dispatch(_app, action);
            }
        })?;
        eprintln!("[pulsepet] hotkey registered: {}", spec.accel);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn debug_fireworks_only_in_debug_build() {
        // TC-WIN-07：调试烟花热键 release 构建移除。规格表与编译 profile 一致：
        // cargo test（debug）→ 3 枚含 Alt+F；cargo test --release → 2 枚无 Alt+F。
        let specs = hotkey_specs();
        let has_debug_fw = specs
            .iter()
            .any(|s| s.action == HotkeyAction::DebugFireworks);
        assert_eq!(has_debug_fw, cfg!(debug_assertions));
        assert_eq!(specs.len(), if cfg!(debug_assertions) { 3 } else { 2 });
    }

    #[test]
    fn base_two_hotkeys_always_present() {
        // 面板 / 穿透两枚热键在任何构建都注册（TC-APP-06/07）
        let specs = hotkey_specs();
        assert!(specs
            .iter()
            .any(|s| s.action == HotkeyAction::TogglePanel && s.accel == "CmdOrCtrl+Shift+P"));
        assert!(specs.iter().any(|s| s.action == HotkeyAction::TogglePassThrough
            && s.accel == "CmdOrCtrl+Shift+Alt+P"));
    }

    #[test]
    fn accels_unique() {
        let specs = hotkey_specs();
        let mut accels: Vec<_> = specs.iter().map(|s| s.accel).collect();
        accels.sort_unstable();
        accels.dedup();
        assert_eq!(accels.len(), specs.len(), "duplicate accel in {specs:?}");
    }

    #[test]
    fn no_overlap_with_opencode_defaults() {
        // TC-APP-08 代码级对照：与 opencode TUI 默认热键无一相同组合。
        let specs = hotkey_specs();
        for s in &specs {
            let mine = accel_normalized(s.accel);
            for d in OPENCODE_DEFAULT_ACCELS {
                assert_ne!(
                    mine,
                    accel_normalized(d),
                    "hotkey {} conflicts with opencode default {d}",
                    s.accel
                );
            }
            // 我们的热键全部含 Shift 修饰（opencode 单 Ctrl 系默认天然无交集）
            assert!(mine.contains("shift"), "unexpected accel {}", s.accel);
        }
    }

    #[test]
    fn accel_normalized_helper() {
        assert_eq!(accel_normalized("CmdOrCtrl+Shift+Alt+P"), "ctrl+shift+alt+p");
        assert_eq!(accel_normalized("Ctrl+O"), "ctrl+o");
    }
}
