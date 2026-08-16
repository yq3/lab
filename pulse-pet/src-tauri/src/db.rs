//! 本地 SQLite（pulsepet.db）迁移与 app_state 读写（DESIGN §5.4/§8.2，TC-APP-13）。
//!
//! M1 用 rusqlite 直连：迁移 + 位置持久化都在 Rust 侧完成，无路径歧义。
//! 数据库文件位于 `app_config_dir()/pulsepet.db`（与 tauri-plugin-sql 的
//! `sqlite:pulsepet.db` 默认落盘位置一致，M4/M7 接入前端插件时无缝复用）。
//! 迁移幂等通过 `PRAGMA user_version` 实现：首启版本 0 → 建表并置 1，后续跳过。

use rusqlite::Connection;
use tauri::Manager;

const INIT_SQL: &str = include_str!("../migrations/001-init.sql");
const SCHEMA_VERSION: i64 = 1;

/// 打开（必要时创建）并迁移本地数据库。
pub fn init(app: &tauri::AppHandle) -> Result<Connection, String> {
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|e| format!("resolve app_config_dir: {e}"))?;
    std::fs::create_dir_all(&dir).map_err(|e| format!("create config dir: {e}"))?;
    let path = dir.join("pulsepet.db");
    let conn = Connection::open(&path).map_err(|e| format!("open db: {e}"))?;
    migrate(&conn)?;
    Ok(conn)
}

/// 幂等迁移：`PRAGMA user_version` 已到版本则跳过（后续启动无副作用）。
pub fn migrate(conn: &Connection) -> Result<(), String> {
    // P2-1：每次连接开启外键约束，否则 schema 里 `ON DELETE CASCADE` 不生效
    // （M4/M7 的 reminders/todos 级联删除会静默失败）。
    conn.execute_batch("PRAGMA foreign_keys=ON")
        .map_err(|e| format!("enable foreign_keys: {e}"))?;
    let version: i64 = conn
        .query_row("PRAGMA user_version", [], |r| r.get(0))
        .map_err(|e| format!("read user_version: {e}"))?;
    if version < SCHEMA_VERSION {
        conn.execute_batch(INIT_SQL)
            .map_err(|e| format!("run migration: {e}"))?;
        conn.execute_batch(&format!("PRAGMA user_version = {SCHEMA_VERSION}"))
            .map_err(|e| format!("set user_version: {e}"))?;
    }
    Ok(())
}

pub fn get_state(conn: &Connection, key: &str) -> Option<String> {
    conn.query_row(
        "SELECT value FROM app_state WHERE key = ?1",
        [key],
        |r| r.get(0),
    )
    .ok()
}

pub fn set_state(conn: &Connection, key: &str, value: &str) -> Result<(), String> {
    conn.execute(
        "INSERT INTO app_state (key, value) VALUES (?1, ?2)
         ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        [key, value],
    )
    .map_err(|e| format!("set_state {key}: {e}"))?;
    Ok(())
}

/// 删除一个 app_state 键（M5：atlas_select(None) 恢复自动选择时清 `pet.selected`）。
pub fn delete_state(conn: &Connection, key: &str) -> Result<(), String> {
    conn.execute("DELETE FROM app_state WHERE key = ?1", [key])
        .map_err(|e| format!("delete_state {key}: {e}"))?;
    Ok(())
}

#[allow(dead_code)] // 单测与运行时验证使用；后续里程碑查询用
pub fn list_tables(conn: &Connection) -> Vec<String> {
    let mut stmt = match conn.prepare(
        "SELECT name FROM sqlite_master
         WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
    ) {
        Ok(s) => s,
        Err(_) => return Vec::new(),
    };
    stmt.query_map([], |r| r.get::<_, String>(0))
        .map(|rows| rows.filter_map(|r| r.ok()).collect())
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn migration_creates_all_six_tables() {
        let conn = Connection::open_in_memory().unwrap();
        migrate(&conn).unwrap();
        let tables = list_tables(&conn);
        for t in [
            "app_state",
            "reminders",
            "reminder_logs",
            "todos",
            "todo_tags",
            "plugins",
        ] {
            assert!(tables.iter().any(|x| x == t), "missing table {t}");
        }
        assert_eq!(tables.len(), 6, "unexpected tables: {tables:?}");
    }

    #[test]
    fn migration_is_idempotent() {
        let conn = Connection::open_in_memory().unwrap();
        migrate(&conn).unwrap();
        // 二次迁移不应报错，且版本保持不变
        migrate(&conn).unwrap();
        let v: i64 = conn
            .query_row("PRAGMA user_version", [], |r| r.get(0))
            .unwrap();
        assert_eq!(v, SCHEMA_VERSION);
    }

    #[test]
    fn app_state_set_get_and_upsert() {
        let conn = Connection::open_in_memory().unwrap();
        migrate(&conn).unwrap();
        set_state(&conn, "pet.position.x", "123").unwrap();
        set_state(&conn, "pet.position.x", "456").unwrap();
        assert_eq!(get_state(&conn, "pet.position.x").as_deref(), Some("456"));
        assert_eq!(get_state(&conn, "pet.position.y"), None);
    }

    #[test]
    fn foreign_keys_enabled_cascade_works() {
        // P2-1：migrate 后外键约束开启，ON DELETE CASCADE 生效
        let conn = Connection::open_in_memory().unwrap();
        migrate(&conn).unwrap();
        let fk: i64 = conn
            .query_row("PRAGMA foreign_keys", [], |r| r.get(0))
            .unwrap();
        assert_eq!(fk, 1, "foreign_keys should be ON");

        conn.execute(
            "INSERT INTO reminders (kind, label, interval_minutes) VALUES ('hydration', '喝水', 30)",
            [],
        )
        .unwrap();
        let rid: i64 = conn.query_row("SELECT last_insert_rowid()", [], |r| r.get(0)).unwrap();
        conn.execute(
            "INSERT INTO reminder_logs (reminder_id, triggered_at) VALUES (?1, 'now')",
            [rid],
        )
        .unwrap();
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM reminder_logs", [], |r| r.get(0))
            .unwrap();
        assert_eq!(count, 1);
        conn.execute("DELETE FROM reminders WHERE id = ?1", [rid]).unwrap();
        let after: i64 = conn
            .query_row("SELECT COUNT(*) FROM reminder_logs", [], |r| r.get(0))
            .unwrap();
        assert_eq!(after, 0, "reminder_logs should cascade-delete with reminder");
    }
}
