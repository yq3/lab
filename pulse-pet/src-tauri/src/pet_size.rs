//! 宠物大小三档（V2-OPEN-ITEMS §十一，2026-08-28 设计定稿；docs/v2/pet-size.md）。
//!
//! 照 `ui.theme` 模式（theme.rs）：档位持久化在 app_state 键 `pet.size`
//! （"small"|"medium"|"large"，缺省 medium），`pet_set_size` 写库 → 应用窗口
//! （windows::apply_pet_size：set_size + 内容中心锚定 + 显示器 clamp）→
//! `pet://size` 广播 `{size, logical}`（pet 窗消费 canvas CSS 尺寸、panel 窗
//! 消费设置页选中态）。档位是**显式设置**，pet 窗口 `resizable:false` 不变
//! （TC-01「不可 resize」语义不受影响）。
//!
//! 档位 → 逻辑像素：small=184 / medium=220 / large=280（184 = 右键菜单实测
//! 外宽 176px 不裁剪的下限，§11.4；220 = 既有默认）。与前端
//! `src/lib/size-bridge.ts` 的 `PET_SIZES` 常量**锁步**：改这里必须同步改
//! 前端（两侧注释互钉）。

use crate::plog;
use std::sync::Mutex;

use rusqlite::Connection;
use tauri::{Emitter, Manager};

/// app_state key：宠物大小档位（"small"|"medium"|"large"；缺省 = medium）。
pub const KEY_SIZE: &str = "pet.size";

/// 档位变化广播事件名（`pet_set_size` 下发；pet/panel 窗订阅）。
pub const SIZE_EVENT: &str = "pet://size";

/// 档位 → pet 窗口逻辑尺寸（px）。与前端 size-bridge.ts 的 PET_SIZES 锁步。
pub fn logical_of(size: &str) -> Option<u32> {
    match size {
        "small" => Some(184),
        "medium" => Some(220),
        "large" => Some(280),
        _ => None,
    }
}

/// 解析并规范化档位（trim 容忍；非法 → None——与 theme.rs parse 同口径）。
pub fn parse_size(s: &str) -> Option<&'static str> {
    match s.trim() {
        "small" => Some("small"),
        "medium" => Some("medium"),
        "large" => Some("large"),
        _ => None,
    }
}

/// 读持久化档位（无值 / 非法值 → None，调用方回退 medium——非法值拒绝/回退口径）。
pub fn read_size(conn: &Connection) -> Option<String> {
    crate::db::get_state(conn, KEY_SIZE).and_then(|s| parse_size(&s).map(String::from))
}

/// 写入核心：持久化并返回规范化后的值（命令层组装事件 payload）。
pub fn write_size(conn: &Connection, size: &str) -> Result<String, String> {
    let v = parse_size(size)
        .ok_or_else(|| format!("size 非法：{size}（应为 small/medium/large）"))?;
    crate::db::set_state(conn, KEY_SIZE, v).map_err(|e| format!("persist pet size: {e}"))?;
    Ok(v.to_string())
}

/// 启动查询：持久化档位（None = 未设置 → medium / conf 默认 220）。
#[tauri::command]
pub fn pet_get_size<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
) -> Result<Option<String>, String> {
    let db = app.state::<Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    Ok(read_size(&conn))
}

/// 设置页切换档位：持久化 → 应用窗口（set_size + 锚定 + clamp）→ 广播。
/// mock runtime / pet 窗口不存在时窗口分支静默跳过（照 theme 命令测试口径）。
#[tauri::command]
pub fn pet_set_size<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    size: String,
) -> Result<(), String> {
    let value = {
        let db = app.state::<Mutex<Connection>>();
        let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
        write_size(&conn, &size)?
    };
    let logical = logical_of(&value);
    if let Some(px) = logical {
        crate::windows::apply_pet_size(&app, px);
    }
    let _ = app.emit(
        SIZE_EVENT,
        serde_json::json!({ "size": value, "logical": logical }),
    );
    plog!("[pulsepet] pet size set to {value} ({logical:?}px logical)");
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
    fn parse_size_accepts_three_values_and_trims() {
        assert_eq!(parse_size("small"), Some("small"));
        assert_eq!(parse_size("medium"), Some("medium"));
        assert_eq!(parse_size("large"), Some("large"));
        assert_eq!(parse_size(" large "), Some("large"));
        assert_eq!(parse_size("Large"), None, "大小写敏感");
        assert_eq!(parse_size("tiny"), None);
        assert_eq!(parse_size(""), None);
    }

    #[test]
    fn logical_of_matches_tiers() {
        // 与前端 PET_SIZES 锁步（§11.3-6）；184 = 菜单不裁剪下限（§11.4）
        assert_eq!(logical_of("small"), Some(184));
        assert_eq!(logical_of("medium"), Some(220));
        assert_eq!(logical_of("large"), Some(280));
        assert_eq!(logical_of("huge"), None);
    }

    #[test]
    fn read_size_missing_returns_none() {
        let c = conn();
        assert_eq!(read_size(&c), None, "缺省 = medium（conf 默认 220）");
    }

    #[test]
    fn read_size_illegal_value_falls_back_to_none() {
        let c = conn();
        crate::db::set_state(&c, KEY_SIZE, "giant").unwrap();
        assert_eq!(read_size(&c), None, "非法持久化值 → None（回退 medium）");
    }

    #[test]
    fn write_size_persists_and_returns_normalized() {
        let c = conn();
        assert_eq!(write_size(&c, " large "), Ok("large".to_string()));
        assert_eq!(read_size(&c).as_deref(), Some("large"));
    }

    #[test]
    fn write_size_rejects_illegal_value() {
        let c = conn();
        assert!(write_size(&c, "giant").is_err());
        assert_eq!(read_size(&c), None, "非法值不落库");
    }

    // ---- 命令级集成（mock runtime：managed db + 广播断言；窗口分支容忍
    //      mock 无 pet 窗口，照 theme.rs commands_roundtrip 口径）----

    #[test]
    fn commands_roundtrip_and_broadcast_via_mock_runtime() {
        use std::sync::mpsc;
        use tauri::Listener;
        let app = tauri::test::mock_app();
        let handle = app.handle();
        let c = conn();
        handle.manage(Mutex::new(c));

        // 缺省：get → None（前端回退 medium）
        assert_eq!(pet_get_size(handle.clone()).unwrap(), None);

        // set 持久化 + pet://size 广播（payload {size, logical}）
        let (tx, rx) = mpsc::channel::<serde_json::Value>();
        let tx = Mutex::new(tx);
        handle.listen(SIZE_EVENT, move |event| {
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(event.payload()) {
                let _ = tx.lock().unwrap().send(v);
            }
        });
        pet_set_size(handle.clone(), " large ".to_string()).unwrap();
        let payload = rx.recv_timeout(std::time::Duration::from_secs(2)).unwrap();
        assert_eq!(payload["size"], "large");
        assert_eq!(payload["logical"], 280);
        assert_eq!(
            pet_get_size(handle.clone()).unwrap().as_deref(),
            Some("large"),
            "写入后可回读（重启保留）"
        );

        // 非法值：命令拒绝（Err），持久化值不被破坏
        assert!(pet_set_size(handle.clone(), "giant".to_string()).is_err());
        assert_eq!(pet_get_size(handle.clone()).unwrap().as_deref(), Some("large"));
    }
}
