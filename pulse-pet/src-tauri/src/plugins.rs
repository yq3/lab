//! M7 插件机制骨架（DESIGN §8.1，TC-TD-01/09）。
//!
//! v1 实现"机制 + 仅挂 todo 一个内置插件"：
//! - manifest 物化在 `~/.pulsepet/plugins/todo/plugin.json`（Windows 为
//!   `%LOCALAPPDATA%\pulsepet\plugins\todo\`），启动时缺失则写入；
//! - `plugins` 表登记元数据（id/name/version/manifest_version/enabled）；
//! - 权限面**仅声明**（manifest 内 permissions），无运行时复检、无沙箱、
//!   不存在第三方安装入口（TC-TD-09）；
//! - `plugins_list` 返回 manifest + 表数据合并视图（面板展示/验收核对用）。
//!
//! 纯逻辑以可注入根目录的 `*_at` 函数实现（tempdir 单测），Tauri command
//! 薄封装。

use std::path::{Path, PathBuf};

use rusqlite::{params, Connection};
use serde::Serialize;
use tauri::Manager;

/// 内置 todo 插件 id（manifest `id` 字段）。
pub const BUILTIN_TODO_ID: &str = "built-in-todo";

/// 内置 todo 插件 manifest（写入 `plugins/todo/plugin.json` 的原文件内容；
/// 字段约定见 DESIGN §8.1：id/name/version/manifestVersion/permissions/
/// configSchema/panelTab）。
pub const TODO_MANIFEST: &str = r#"{
  "id": "built-in-todo",
  "name": "Todo",
  "version": "0.1.0",
  "manifestVersion": 1,
  "permissions": ["schedule", "notify", "ui:panel-tab", "todo:*"],
  "configSchema": {
    "type": "object",
    "properties": {
      "defaultRemindBeforeMinutes": {
        "type": "number",
        "default": 5,
        "title": "新任务默认提前提醒（分钟）"
      }
    }
  },
  "panelTab": { "title": "Todo", "icon": "check-square" }
}"#;

/// 插件根目录（POSIX `~/.pulsepet/plugins`；Windows `%LOCALAPPDATA%\pulsepet\plugins`；
/// 与 runtime.rs 的平台区分一致）。
pub fn plugins_root() -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        let base = std::env::var("LOCALAPPDATA").unwrap_or_else(|_| ".".to_string());
        PathBuf::from(base).join("pulsepet").join("plugins")
    }
    #[cfg(not(target_os = "windows"))]
    {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        PathBuf::from(home).join(".pulsepet").join("plugins")
    }
}

/// 启动注册（幂等）：manifest 缺失则物化 + plugins 表 upsert 元数据。
pub fn ensure_builtin_plugins(conn: &Connection) -> Result<(), String> {
    ensure_builtin_plugins_at(&plugins_root(), conn)
}

pub fn ensure_builtin_plugins_at(root: &Path, conn: &Connection) -> Result<(), String> {
    let dir = root.join("todo");
    let manifest = dir.join("plugin.json");
    if !manifest.is_file() {
        std::fs::create_dir_all(&dir).map_err(|e| format!("create plugin dir: {e}"))?;
        std::fs::write(&manifest, TODO_MANIFEST)
            .map_err(|e| format!("write plugin.json: {e}"))?;
    }
    conn.execute(
        "INSERT INTO plugins (id, name, version, manifest_version, enabled) \
         VALUES (?1, ?2, ?3, ?4, 1) \
         ON CONFLICT(id) DO UPDATE SET name = excluded.name, version = excluded.version, \
         manifest_version = excluded.manifest_version",
        params![BUILTIN_TODO_ID, "Todo", "0.1.0", 1],
    )
    .map_err(|e| format!("upsert plugins row: {e}"))?;
    Ok(())
}

/// 面板/验收视图（manifest 声明 + 表登记状态合并）。
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct PluginInfo {
    pub id: String,
    pub name: String,
    pub version: String,
    pub manifest_version: i64,
    pub enabled: bool,
    /// 声明级权限面（TC-TD-09：无运行时复检）。
    pub permissions: Vec<String>,
    /// manifest panelTab 原样透传（v1 前端 Todo tab 为内置实现，不消费此字段渲染）。
    pub panel_tab: Option<serde_json::Value>,
    pub manifest_path: String,
}

/// 扫描根目录 manifest + plugins 表合并（manifest 损坏/缺失时 permissions 空，
/// 表数据仍返回——不因文件损坏让面板崩）。
pub fn list_plugins_at(root: &Path, conn: &Connection) -> Result<Vec<PluginInfo>, String> {
    let mut stmt = conn
        .prepare("SELECT id, name, version, manifest_version, enabled FROM plugins ORDER BY id")
        .map_err(|e| format!("list plugins: {e}"))?;
    let rows: Vec<(String, String, String, i64, bool)> = stmt
        .query_map([], |r| {
            Ok((
                r.get(0)?,
                r.get(1)?,
                r.get(2)?,
                r.get(3)?,
                r.get::<_, i64>(4)? != 0,
            ))
        })
        .map_err(|e| format!("list plugins: {e}"))?
        .filter_map(|r| r.ok())
        .collect();

    Ok(rows
        .into_iter()
        .map(|(id, name, version, mv, enabled)| {
            // v1 目录名映射：built-in-todo → todo（无第三方安装入口）
            let dir = if id == BUILTIN_TODO_ID { "todo" } else { &id };
            let manifest_path = root.join(dir).join("plugin.json");
            let (permissions, panel_tab) = std::fs::read_to_string(&manifest_path)
                .ok()
                .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
                .map(|v| {
                    let permissions = v
                        .get("permissions")
                        .and_then(|p| p.as_array())
                        .map(|a| {
                            a.iter()
                                .filter_map(|x| x.as_str().map(String::from))
                                .collect()
                        })
                        .unwrap_or_default();
                    (permissions, v.get("panelTab").cloned())
                })
                .unwrap_or_default();
            PluginInfo {
                id,
                name,
                version,
                manifest_version: mv,
                enabled,
                permissions,
                panel_tab,
                manifest_path: manifest_path.display().to_string(),
            }
        })
        .collect())
}

/// 面板展示（TC-TD-01：manifest 字段核对入口）。
#[tauri::command]
pub fn plugins_list<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
) -> Result<Vec<PluginInfo>, String> {
    let db = app.state::<std::sync::Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    list_plugins_at(&plugins_root(), &conn)
}

// ---------------------------------------------------------------------------
// 测试
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn conn() -> Connection {
        let c = Connection::open_in_memory().unwrap();
        crate::db::migrate(&c).unwrap();
        c
    }

    fn tempdir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "pulsepet-plugins-test-{}-{}",
            tag,
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn manifest_has_all_required_fields_tc_td_01() {
        let v: serde_json::Value = serde_json::from_str(TODO_MANIFEST).unwrap();
        assert_eq!(v["id"], "built-in-todo");
        assert_eq!(v["name"], "Todo");
        assert_eq!(v["version"], "0.1.0");
        assert_eq!(v["manifestVersion"], 1);
        let perms = v["permissions"].as_array().unwrap();
        for p in ["schedule", "notify", "ui:panel-tab", "todo:*"] {
            assert!(perms.iter().any(|x| x == p), "missing permission {p}");
        }
        assert_eq!(perms.len(), 4);
        assert!(v["configSchema"].is_object());
        assert_eq!(v["panelTab"]["title"], "Todo");
        assert_eq!(v["panelTab"]["icon"], "check-square");
    }

    #[test]
    fn ensure_creates_manifest_and_row_idempotently() {
        let root = tempdir("ensure");
        let c = conn();
        ensure_builtin_plugins_at(&root, &c).unwrap();
        let path = root.join("todo").join("plugin.json");
        assert!(path.is_file());
        // manifest 内容 = TODO_MANIFEST（含全部声明字段）
        let written = std::fs::read_to_string(&path).unwrap();
        assert_eq!(written, TODO_MANIFEST);
        let (name, version, mv, enabled): (String, String, i64, i64) = c
            .query_row(
                "SELECT name, version, manifest_version, enabled FROM plugins WHERE id = ?1",
                [BUILTIN_TODO_ID],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
            )
            .unwrap();
        assert_eq!(name, "Todo");
        assert_eq!(version, "0.1.0");
        assert_eq!(mv, 1);
        assert_eq!(enabled, 1);

        // 幂等：再跑一次不报错、不重复登记、不覆盖已存在的 manifest
        std::fs::write(&path, "// user-touched").unwrap();
        ensure_builtin_plugins_at(&root, &c).unwrap();
        let count: i64 = c
            .query_row("SELECT COUNT(*) FROM plugins", [], |r| r.get(0))
            .unwrap();
        assert_eq!(count, 1);
        assert_eq!(std::fs::read_to_string(&path).unwrap(), "// user-touched");

        std::fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn list_plugins_merges_manifest_and_db() {
        let root = tempdir("list");
        let c = conn();
        ensure_builtin_plugins_at(&root, &c).unwrap();
        let list = list_plugins_at(&root, &c).unwrap();
        assert_eq!(list.len(), 1);
        let p = &list[0];
        assert_eq!(p.id, "built-in-todo");
        assert_eq!(p.name, "Todo");
        assert!(p.enabled);
        assert_eq!(
            p.permissions,
            vec![
                "schedule".to_string(),
                "notify".to_string(),
                "ui:panel-tab".to_string(),
                "todo:*".to_string()
            ]
        );
        assert_eq!(p.panel_tab.as_ref().unwrap()["title"], "Todo");
        assert!(p.manifest_path.ends_with("todo/plugin.json"));

        // manifest 损坏 → permissions 空、表数据仍返回（不崩）
        std::fs::write(root.join("todo").join("plugin.json"), "not json").unwrap();
        let list2 = list_plugins_at(&root, &c).unwrap();
        assert_eq!(list2.len(), 1);
        assert!(list2[0].permissions.is_empty());
        assert_eq!(list2[0].name, "Todo");

        std::fs::remove_dir_all(&root).ok();
    }
}
