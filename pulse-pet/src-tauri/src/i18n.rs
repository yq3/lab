//! M8 i18n（Rust 侧，DESIGN §10 "国际化 en/zh"）。
//!
//! Rust 持有文案的面：托盘菜单五项、panel 窗口标题、token 会话汇报气泡、
//! atlas 回退提示。本模块是这些文案的唯一语言开关：
//! - 全局语言位 `static LANG`（进程内；setup 时从 app_state `ui.language`
//!   恢复，默认 zh）；
//! - `ui_set_language` command（设置页切换入口）：持久化 → 更新全局位 →
//!   重建托盘菜单（`tray::apply_language`）→ 同步 panel 标题 → 广播
//!   `ui://language` 三窗口（前端 store 跟随）；`ui_get_language` 供启动
//!   读取持久化值（无值时前端回退系统语言）。
//! - 取舍说明：Rust 侧 CRUD 校验错误串（reminders/todos validate_*）保持
//!   zh——前端同口径校验先行拦截，Rust 报错仅剩"前端放过 + Rust 拒绝"的
//!   边缘路径（A3 契约测试钉住该分工），v1 不做全量错误串双语。
//! - 不翻译项：宠物状态名（idle/working…技术词）、品牌名 PulsePet。

use crate::plog;
use std::sync::Mutex;

use rusqlite::Connection;
use tauri::{Emitter, Manager};

/// app_state key：界面语言（"zh"/"en"；缺省 = 跟随系统，由前端决定）。
pub const KEY_LANGUAGE: &str = "ui.language";

/// 前端语言变化广播事件名（`ui_set_language` 下发，三窗口订阅）。
pub const LANGUAGE_EVENT: &str = "ui://language";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Lang {
    Zh,
    En,
}

/// 进程级语言位（Mutex::new 为 const fn；poison 容忍与库内惯例一致）。
static LANG: Mutex<Lang> = Mutex::new(Lang::Zh);

pub fn current() -> Lang {
    *LANG.lock().unwrap_or_else(|p| p.into_inner())
}

pub fn set(lang: Lang) {
    *LANG.lock().unwrap_or_else(|p| p.into_inner()) = lang;
}

impl Lang {
    pub fn parse(s: &str) -> Option<Lang> {
        match s.trim() {
            "zh" => Some(Lang::Zh),
            "en" => Some(Lang::En),
            _ => None,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Lang::Zh => "zh",
            Lang::En => "en",
        }
    }

    // ---- 托盘菜单五项（DESIGN §7.2 顺序：显示/隐藏宠物、切换交互模式、
    //      打开控制面板、暂停所有提醒、退出）----

    pub fn tray_toggle(&self) -> &'static str {
        match self {
            Lang::Zh => "显示/隐藏宠物",
            Lang::En => "Show/Hide Pet",
        }
    }

    pub fn tray_interaction(&self) -> &'static str {
        match self {
            Lang::Zh => "切换交互模式（穿透开/关）",
            Lang::En => "Toggle Interaction Mode (pass-through on/off)",
        }
    }

    pub fn tray_panel(&self) -> &'static str {
        match self {
            Lang::Zh => "打开控制面板",
            Lang::En => "Open Control Panel",
        }
    }

    pub fn tray_pause(&self) -> &'static str {
        match self {
            Lang::Zh => "暂停所有提醒",
            Lang::En => "Pause All Reminders",
        }
    }

    pub fn tray_quit(&self) -> &'static str {
        match self {
            Lang::Zh => "退出",
            Lang::En => "Quit",
        }
    }

    // ---- panel 窗口标题 ----
    // R2 P3-2：与页内 h1（前端 panel.title）逐字一致——「PulsePet · 控制面板」。
    pub fn panel_title(&self) -> &'static str {
        match self {
            Lang::Zh => "PulsePet · 控制面板",
            Lang::En => "PulsePet · Control Panel",
        }
    }

    // ---- token 会话汇报气泡（TC-TK-10/11/12；i/o/c 为已格式化数字串）----

    pub fn token_report(&self, input: &str, output: &str, cost: &str) -> String {
        match self {
            Lang::Zh => format!("本期用了 {input} input / {output} output / {cost}"),
            Lang::En => format!("This session: {input} input / {output} output / {cost}"),
        }
    }

    // ---- atlas 回退提示（TC-SP-05/09 措辞；zh 与 M5 定案逐字一致）----

    pub fn atlas_notice_grid(&self, id: &str, width: u32, height: u32) -> String {
        match self {
            Lang::Zh => format!(
                "「{id}」该素材网格尺寸非标准（如 8×9 / 8×11 之外）：spritesheet 为 {width}×{height}，已回退内置占位 blinking-kitty"
            ),
            Lang::En => format!(
                "\"{id}\" non-standard grid (not 8×9 / 8×11): spritesheet is {width}×{height}, fell back to built-in blinking-kitty"
            ),
        }
    }

    pub fn atlas_notice_meta(&self, id: &str, reason: &str) -> String {
        match self {
            Lang::Zh => format!(
                "「{id}」素材加载失败（pet.json 损坏：{reason}），已回退内置占位 blinking-kitty"
            ),
            Lang::En => format!(
                "\"{id}\" failed to load (broken pet.json: {reason}), fell back to built-in blinking-kitty"
            ),
        }
    }

    pub fn atlas_notice_sheet(&self, id: &str, reason: &str) -> String {
        match self {
            Lang::Zh => format!(
                "「{id}」素材加载失败（spritesheet 缺失或无法解码：{reason}），已回退内置占位 blinking-kitty"
            ),
            Lang::En => format!(
                "\"{id}\" failed to load (spritesheet missing or undecodable: {reason}), fell back to built-in blinking-kitty"
            ),
        }
    }

    pub fn atlas_notice_io(&self, id: &str, reason: &str) -> String {
        match self {
            Lang::Zh => format!("「{id}」素材读取失败（{reason}），已回退内置占位 blinking-kitty"),
            Lang::En => {
                format!("\"{id}\" failed to read ({reason}), fell back to built-in blinking-kitty")
            }
        }
    }

    pub fn atlas_notice_not_found(&self, id: &str) -> String {
        match self {
            Lang::Zh => format!("「{id}」未找到宠物素材，已回退内置占位 blinking-kitty"),
            Lang::En => format!("\"{id}\" pet assets not found, fell back to built-in blinking-kitty"),
        }
    }

    /// load_pet_dir / probe_pet_dir 的固定 reason 串（嵌入 notice 模板）。
    pub fn atlas_meta_missing(&self) -> &'static str {
        match self {
            Lang::Zh => "pet.json 缺失",
            Lang::En => "pet.json missing",
        }
    }

    pub fn atlas_sheet_missing(&self) -> &'static str {
        match self {
            Lang::Zh => "spritesheet.webp / .png 均缺失",
            Lang::En => "both spritesheet.webp / .png missing",
        }
    }

    // ---- v2 M1 接入管理 doctor 文案（V2-DESIGN §1.7/§1.8；组装在 integrations.rs）----

    pub fn intg_installed(&self) -> String {
        match self {
            Lang::Zh => format!("已安装 · v{}", env!("CARGO_PKG_VERSION")),
            Lang::En => format!("Installed · v{}", env!("CARGO_PKG_VERSION")),
        }
    }

    pub fn intg_not_installed(&self) -> &'static str {
        match self {
            Lang::Zh => "未安装",
            Lang::En => "Not installed",
        }
    }

    pub fn intg_stale(&self) -> &'static str {
        match self {
            Lang::Zh => "需更新（一键重装修复）",
            Lang::En => "Needs update (reinstall to fix)",
        }
    }

    pub fn intg_error(&self, reason: &str) -> String {
        match self {
            Lang::Zh => format!("检测失败：{reason}"),
            Lang::En => format!("Check failed: {reason}"),
        }
    }

    pub fn intg_node_ready(&self) -> &'static str {
        match self {
            Lang::Zh => "node 已就绪",
            Lang::En => "node ready",
        }
    }

    pub fn intg_node_missing(&self) -> &'static str {
        match self {
            Lang::Zh => "未检测到 node（CC 接入需要）",
            Lang::En => "node not found (required for claude-code)",
        }
    }

    pub fn intg_last_event(&self) -> &'static str {
        match self {
            Lang::Zh => "事件正常",
            Lang::En => "Receiving events",
        }
    }

    pub fn intg_no_event(&self) -> &'static str {
        match self {
            Lang::Zh => "最近无事件",
            Lang::En => "No recent events",
        }
    }

    /// 卸载后建议新开 CC 会话（§1.4.4：Windows 字面路径无逐事件自愈，TC-INT-07-5）。
    pub fn intg_uninstall_hint(&self) -> &'static str {
        match self {
            Lang::Zh => "已卸载；如 CC 会话仍在运行，建议新开会话使其生效",
            Lang::En => "Uninstalled; restart your CC session for this to take effect",
        }
    }

    /// 安装后建议新开 CC 会话（v2 M2 L1/P2-1：安装路径的提示不再复用卸载
    /// 文案——修复「已安装…已卸载」措辞矛盾；一键级 i18n）。
    pub fn intg_install_hint(&self) -> &'static str {
        match self {
            Lang::Zh => "已安装；如 CC 会话已在运行，建议新开会话以启用",
            Lang::En => "Installed; restart your CC session to activate it",
        }
    }
}

/// setup 时恢复持久化语言（无值 / 非法值保持默认 zh，由前端按系统语言接管）。
pub fn restore_from_db(conn: &Connection) {
    if let Some(lang) = crate::db::get_state(conn, KEY_LANGUAGE)
        .and_then(|s| Lang::parse(&s))
    {
        set(lang);
    }
}

/// 启动查询：持久化语言（None = 未设置，前端回退系统语言）。
#[tauri::command]
pub fn ui_get_language(app: tauri::AppHandle) -> Result<Option<String>, String> {
    let db = app.state::<Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    Ok(crate::db::get_state(&conn, KEY_LANGUAGE))
}

/// 设置页切换：持久化 → 全局位 → 托盘菜单重建 + panel 标题 → 广播三窗口。
#[tauri::command]
pub fn ui_set_language(app: tauri::AppHandle, lang: String) -> Result<(), String> {
    let parsed = Lang::parse(&lang)
        .ok_or_else(|| format!("language 非法：{lang}（应为 zh/en）"))?;
    {
        let db = app.state::<Mutex<Connection>>();
        let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
        crate::db::set_state(&conn, KEY_LANGUAGE, parsed.as_str())
            .map_err(|e| format!("persist language: {e}"))?;
    }
    set(parsed);
    crate::tray::apply_language(&app).map_err(|e| format!("rebuild tray menu: {e}"))?;
    if let Some(win) = app.get_webview_window("panel") {
        let _ = win.set_title(parsed.panel_title());
    }
    let _ = app.emit(LANGUAGE_EVENT, serde_json::json!({ "lang": parsed.as_str() }));
    plog!("[pulsepet] ui language set to {}", parsed.as_str());
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lang_parse_and_roundtrip() {
        assert_eq!(Lang::parse("zh"), Some(Lang::Zh));
        assert_eq!(Lang::parse(" en "), Some(Lang::En));
        assert_eq!(Lang::parse("ja"), None);
        assert_eq!(Lang::parse(""), None);
        assert_eq!(Lang::Zh.as_str(), "zh");
        assert_eq!(Lang::En.as_str(), "en");
    }

    #[test]
    fn tray_texts_switch_with_lang() {
        assert_eq!(Lang::Zh.tray_toggle(), "显示/隐藏宠物");
        assert_eq!(Lang::En.tray_toggle(), "Show/Hide Pet");
        assert!(Lang::Zh.tray_quit().contains("退出"));
        assert_eq!(Lang::En.tray_quit(), "Quit");
        // R2 P3-2：窗口标题 zh/en 互异且含间隔点（与前端 panel.title 一致性钉子）
        assert_eq!(Lang::Zh.panel_title(), "PulsePet · 控制面板");
        assert_eq!(Lang::En.panel_title(), "PulsePet · Control Panel");
        // 全部五项在两种语言下互不相同（防"en 串误粘贴 zh"类回归）
        for (zh, en) in [
            (Lang::Zh.tray_toggle(), Lang::En.tray_toggle()),
            (Lang::Zh.tray_interaction(), Lang::En.tray_interaction()),
            (Lang::Zh.tray_panel(), Lang::En.tray_panel()),
            (Lang::Zh.tray_pause(), Lang::En.tray_pause()),
            (Lang::Zh.tray_quit(), Lang::En.tray_quit()),
        ] {
            assert_ne!(zh, en);
        }
    }

    #[test]
    fn token_report_follows_current_lang() {
        set(Lang::Zh);
        assert_eq!(
            current().token_report("58.3k", "910", "$0.05"),
            "本期用了 58.3k input / 910 output / $0.05"
        );
        set(Lang::En);
        assert_eq!(
            current().token_report("58.3k", "910", "$0.05"),
            "This session: 58.3k input / 910 output / $0.05"
        );
        set(Lang::Zh); // 恢复默认，避免影响其它测试
    }

    #[test]
    fn atlas_notice_zh_wording_matches_m5_spec() {
        // TC-SP-05 钉住措辞：zh 文案与 M5 定案逐字一致（语言化不得改动 zh）
        let s = Lang::Zh.atlas_notice_grid("bad-pet", 1536, 2080);
        assert!(s.contains("该素材网格尺寸非标准"));
        assert!(s.contains("1536×2080"));
        assert!(s.contains("已回退内置占位 blinking-kitty"));
        let en = Lang::En.atlas_notice_grid("bad-pet", 1536, 2080);
        assert!(en.contains("non-standard grid"));
        assert!(en.contains("1536×2080"));
    }

    #[test]
    fn restore_from_db_persists_and_ignores_bad_value() {
        let conn = Connection::open_in_memory().unwrap();
        crate::db::migrate(&conn).unwrap();
        // 非法值 → 保持默认 zh
        crate::db::set_state(&conn, KEY_LANGUAGE, "fr").unwrap();
        restore_from_db(&conn);
        assert_eq!(current(), Lang::Zh);
        // 合法值 → 恢复
        crate::db::set_state(&conn, KEY_LANGUAGE, "en").unwrap();
        restore_from_db(&conn);
        assert_eq!(current(), Lang::En);
        set(Lang::Zh); // 恢复默认
    }

    #[test]
    fn integration_texts_bilingual() {
        // v2 M1：doctor 文案 zh/en 均非空且互不相同（防粘贴错语言）
        for (zh, en) in [
            (Lang::Zh.intg_not_installed(), Lang::En.intg_not_installed()),
            (Lang::Zh.intg_stale(), Lang::En.intg_stale()),
            (Lang::Zh.intg_node_ready(), Lang::En.intg_node_ready()),
            (Lang::Zh.intg_node_missing(), Lang::En.intg_node_missing()),
            (Lang::Zh.intg_last_event(), Lang::En.intg_last_event()),
            (Lang::Zh.intg_no_event(), Lang::En.intg_no_event()),
            (Lang::Zh.intg_uninstall_hint(), Lang::En.intg_uninstall_hint()),
        ] {
            assert!(!zh.is_empty() && !en.is_empty());
            assert_ne!(zh, en);
        }
        // v2 M2 L1（P2-1）：安装提示独立成键——安装路径不再出现「已卸载」措辞
        for (zh, en) in [(
            Lang::Zh.intg_install_hint(),
            Lang::En.intg_install_hint(),
        )] {
            assert!(!zh.is_empty() && !en.is_empty());
            assert_ne!(zh, en);
            assert!(zh.contains("已安装"), "{zh}");
            assert!(!zh.contains("已卸载"), "安装文案不得复用卸载措辞：{zh}");
            assert!(en.to_lowercase().contains("installed"), "{en}");
            assert!(
                !en.to_lowercase().contains("uninstalled"),
                "install wording must not reuse uninstall text: {en}"
            );
        }
        assert!(Lang::Zh.intg_installed().contains("已安装"));
        assert!(Lang::En.intg_installed().contains("Installed"));
        assert!(Lang::Zh.intg_error("boom").contains("boom"));
        assert!(Lang::En.intg_error("boom").starts_with("Check failed"));
    }
}
