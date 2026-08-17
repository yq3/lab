//! M7 Todo 插件（内置 built-in-todo）Rust 侧（DESIGN §8，TC-TD-01~09）。
//!
//! - **CRUD**（TC-TD-02）：`todos` + `todo_tags` 读写；tag 随 upsert 全量替换
//!   （增删即时反映），删除 todo 由 schema FK 级联清 todo_tags；列表按
//!   `sort_order` 排序（`todo_reorder` 重排立即生效）。
//! - **派生提醒（B16 定案通道，§8.3/§5.4，TC-TD-03/08）**：todo 写入/修改时，
//!   若 `due_date` 带时间（YYYY-MM-DDTHH:MM）且 `remind_before_minutes > 0`，
//!   同步 upsert 一行 `reminders`（kind='todo'、interval_minutes=0、
//!   start_time = due_date - remind_before、source_todo_id 反向引用、
//!   todo_due_at = due_date）；`remind_before_minutes = 0` 或纯日期 → 不派生
//!   （完全无提醒）；调度器统一消费 reminders 表，**不回查 todos**。
//!   due 变化 → last_triggered_at 清空（新日程新的一次性）。
//! - **完成联动**（TC-TD-04/05/07）：completed_at 写 RFC3339 本地时间；完成/
//!   删除 → 派生 reminder 行级联删除（reminder_logs 历史保留，见 002 迁移）；
//!   完成时广播 `todo://completed`（title/completed_today/all_today_done），
//!   pet 窗口播放 waving + 气泡。
//! - **今日全清**（TC-TD-05）："今日"按用户本地时区自然日（00:00 起）按
//!   completed_at 统计（与 token 聚合 localtime 语义一致）；完成的这条
//!   due 在今日且今日再无未完成项 → all_today_done。
//! - `todos.remind_last_triggered_at` 保留字段 v1 不写入不读取（防重唯一来源
//!   是 reminders.last_triggered_at，TC-TD-06）。

use chrono::{Duration, Local, NaiveDateTime};
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use tauri::{Emitter, Manager};

/// title 与派生 reminder label 同列，同 1-140 约束。
pub const MAX_TITLE_CHARS: usize = 140;
pub const MAX_NOTES_CHARS: usize = 2000;
/// 提前提醒上限（7 天，防 due - remind 溢出到epoch 前的荒谬值）。
pub const MAX_REMIND_BEFORE_MINUTES: i64 = 10_080;
pub const MAX_TAGS: usize = 20;
pub const MAX_TAG_CHARS: usize = 40;

/// todos 行（+聚合 tags；serde 字段与 TS `TodoItem` 一致，snake_case）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TodoItem {
    pub id: i64,
    pub title: String,
    pub notes: Option<String>,
    pub priority: i64,
    /// "YYYY-MM-DD" 或 "YYYY-MM-DDTHH:MM"（带时间才可派生提醒）。
    pub due_date: Option<String>,
    pub remind_before_minutes: i64,
    /// 保留字段 v1 不写入不读取（TC-TD-06；防重唯一来源在 reminders 侧）。
    pub remind_last_triggered_at: Option<String>,
    pub completed_at: Option<String>,
    pub sort_order: i64,
    pub tags: Vec<String>,
    pub created_at: String,
    pub updated_at: String,
}

/// CRUD 入参（id 由 command 参数单独传；tags 全量替换）。
#[derive(Debug, Clone, Deserialize, PartialEq)]
pub struct TodoInput {
    pub title: String,
    pub notes: Option<String>,
    pub priority: i64,
    pub due_date: Option<String>,
    pub remind_before_minutes: i64,
    pub sort_order: i64,
    pub tags: Vec<String>,
}

/// todo_complete 返回（panel 刷新用 + 事件 payload 素材）。
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct TodoCompleteResult {
    pub todo: TodoItem,
    /// 今日（本地自然日）已完成数（含本次）。
    pub completed_today: i64,
    /// 完成今日全部任务（本次 due 在今日且今日已无未完成项）。
    pub all_today_done: bool,
    /// 本次完成的 todo 是否 due 在今日。
    pub was_due_today: bool,
}

// ---------------------------------------------------------------------------
// 纯函数（单测主战场）
// ---------------------------------------------------------------------------

/// due_date 是否带时间（含 "T"）——派生提醒的前提之一。
pub fn due_has_time(s: &str) -> bool {
    s.contains('T')
}

/// 校验后的规范化入参。
#[derive(Debug, Clone, PartialEq)]
pub struct ValidatedTodo {
    pub title: String,
    pub notes: Option<String>,
    pub priority: i64,
    pub due_date: Option<String>,
    pub remind_before_minutes: i64,
    pub tags: Vec<String>,
}

/// 入参校验（与前端 validateTodoInput 同口径）。
pub fn validate_todo_input(input: &TodoInput) -> Result<ValidatedTodo, String> {
    let title: String = input.title.split_whitespace().collect::<Vec<_>>().join(" ");
    if title.is_empty() {
        return Err("title 不能为空".into());
    }
    if title.chars().count() > MAX_TITLE_CHARS {
        return Err(format!("title 超长（≤{MAX_TITLE_CHARS} 字符）"));
    }
    if !(0..=3).contains(&input.priority) {
        return Err(format!("priority 非法：{}（应为 0-3）", input.priority));
    }
    if !(0..=MAX_REMIND_BEFORE_MINUTES).contains(&input.remind_before_minutes) {
        return Err(format!(
            "remind_before_minutes 非法：{}（应为 0-{MAX_REMIND_BEFORE_MINUTES}）",
            input.remind_before_minutes
        ));
    }
    let due = input
        .due_date
        .as_deref()
        .map(str::trim)
        .filter(|s| !s.is_empty());
    if let Some(d) = due {
        if crate::reminder_scheduler::parse_due_like_ms(d).is_none() {
            return Err(format!(
                "due_date 非法：{d}（应为 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM）"
            ));
        }
    }
    let notes = input
        .notes
        .as_deref()
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string());
    if let Some(n) = &notes {
        if n.chars().count() > MAX_NOTES_CHARS {
            return Err(format!("notes 超长（≤{MAX_NOTES_CHARS} 字符）"));
        }
    }
    // tags：trim、去空、去重（保序）、限长
    let mut tags: Vec<String> = Vec::new();
    for t in &input.tags {
        let t = t.trim();
        if t.is_empty() {
            continue;
        }
        if t.chars().count() > MAX_TAG_CHARS {
            return Err(format!("tag 超长（≤{MAX_TAG_CHARS} 字符）：{t}"));
        }
        if !tags.iter().any(|x| x == t) {
            tags.push(t.to_string());
        }
    }
    if tags.len() > MAX_TAGS {
        return Err(format!("tag 数量超限（≤{MAX_TAGS} 个）"));
    }
    Ok(ValidatedTodo {
        title,
        notes,
        priority: input.priority,
        due_date: due.map(|s| s.to_string()),
        remind_before_minutes: input.remind_before_minutes,
        tags,
    })
}

/// 派生提醒 start_time = due_date - remind_before（"YYYY-MM-DDTHH:MM"）。
/// 仅对带时间的 due 有效；纯日期/解析失败 → None。
pub fn derive_start_time(due: &str, remind_before_minutes: i64) -> Option<String> {
    if !due_has_time(due) || remind_before_minutes <= 0 {
        return None;
    }
    let dt = NaiveDateTime::parse_from_str(due, "%Y-%m-%dT%H:%M").ok()?;
    let start = dt
        .checked_sub_signed(Duration::minutes(remind_before_minutes))
        // 负向溢出（due 早于 epoch 很久）不派生
        .filter(|s| s.and_utc().timestamp_millis() > 0)?;
    Some(start.format("%Y-%m-%dT%H:%M").to_string())
}

/// 今日（本地时区自然日）"YYYY-MM-DD"。
pub fn local_today() -> String {
    Local::now().format("%Y-%m-%d").to_string()
}

/// RFC3339 时间戳是否落在今日本地自然日（completed_at 统计口径，TC-TD-05）。
fn is_today_rfc3339(ts: &str, today: &str) -> bool {
    chrono::DateTime::parse_from_rfc3339(ts)
        .map(|d| {
            d.with_timezone(&Local).format("%Y-%m-%d").to_string() == today
        })
        .unwrap_or(false)
}

/// todo 是否"due 在今日"（due 日期部分 == 今日本地自然日）。
fn todo_due_today(todo: &TodoItem) -> bool {
    todo.due_date
        .as_deref()
        .map(|d| d.len() >= 10 && &d[..10] == local_today())
        .unwrap_or(false)
}

// ---------------------------------------------------------------------------
// db 读写
// ---------------------------------------------------------------------------

fn row_to_todo(row: &rusqlite::Row<'_>) -> rusqlite::Result<TodoItem> {
    Ok(TodoItem {
        id: row.get("id")?,
        title: row.get("title")?,
        notes: row.get("notes")?,
        priority: row.get("priority")?,
        due_date: row.get("due_date")?,
        remind_before_minutes: row.get("remind_before_minutes")?,
        remind_last_triggered_at: row.get("remind_last_triggered_at")?,
        completed_at: row.get("completed_at")?,
        sort_order: row.get("sort_order")?,
        // tags 由 load_tags 单独聚合
        tags: Vec::new(),
        created_at: row.get("created_at")?,
        updated_at: row.get("updated_at")?,
    })
}

const TODO_COLS: &str = "id, title, notes, priority, due_date, remind_before_minutes, \
     remind_last_triggered_at, completed_at, sort_order, created_at, updated_at";

fn load_tags(conn: &Connection, todo_id: i64) -> Result<Vec<String>, String> {
    let mut stmt = conn
        .prepare("SELECT tag FROM todo_tags WHERE todo_id = ?1 ORDER BY rowid")
        .map_err(|e| format!("load tags: {e}"))?;
    let rows = stmt
        .query_map([todo_id], |r| r.get::<_, String>(0))
        .map_err(|e| format!("load tags: {e}"))?;
    Ok(rows.filter_map(|r| r.ok()).collect())
}

/// 列表（TC-TD-02）：按 sort_order 排序（并列按 id 稳定）。
pub fn list_todos(conn: &Connection) -> Result<Vec<TodoItem>, String> {
    let sql = format!("SELECT {TODO_COLS} FROM todos ORDER BY sort_order, id");
    let mut stmt = conn
        .prepare(&sql)
        .map_err(|e| format!("list todos: {e}"))?;
    let ids: Vec<i64> = stmt
        .query_map([], |r| r.get::<_, i64>("id"))
        .map_err(|e| format!("list todos: {e}"))?
        .filter_map(|r| r.ok())
        .collect();
    ids.iter().map(|id| todo_by_id(conn, *id)).collect()
}

pub fn todo_by_id(conn: &Connection, id: i64) -> Result<TodoItem, String> {
    let sql = format!("SELECT {TODO_COLS} FROM todos WHERE id = ?1");
    let mut todo = conn
        .query_row(&sql, [id], row_to_todo)
        .map_err(|e| format!("read todo #{id}: {e}"))?;
    todo.tags = load_tags(conn, id)?;
    Ok(todo)
}

fn replace_tags(conn: &Connection, todo_id: i64, tags: &[String]) -> Result<(), String> {
    conn.execute("DELETE FROM todo_tags WHERE todo_id = ?1", [todo_id])
        .map_err(|e| format!("clear tags: {e}"))?;
    for t in tags {
        conn.execute(
            "INSERT INTO todo_tags (todo_id, tag) VALUES (?1, ?2)",
            params![todo_id, t],
        )
        .map_err(|e| format!("insert tag: {e}"))?;
    }
    Ok(())
}

pub fn insert_todo(conn: &Connection, input: &TodoInput) -> Result<TodoItem, String> {
    let v = validate_todo_input(input)?;
    let now = crate::reminder_scheduler::now_rfc3339();
    conn.execute(
        "INSERT INTO todos (title, notes, priority, due_date, remind_before_minutes, \
         sort_order, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
        params![
            v.title,
            v.notes,
            v.priority,
            v.due_date,
            v.remind_before_minutes,
            input.sort_order,
            now,
            now
        ],
    )
    .map_err(|e| format!("insert todo: {e}"))?;
    let id = conn.last_insert_rowid();
    replace_tags(conn, id, &v.tags)?;
    let todo = todo_by_id(conn, id)?;
    sync_derived_reminder(conn, &todo)?;
    Ok(todo)
}

pub fn update_todo(conn: &Connection, id: i64, input: &TodoInput) -> Result<TodoItem, String> {
    let v = validate_todo_input(input)?;
    let now = crate::reminder_scheduler::now_rfc3339();
    let n = conn
        .execute(
            "UPDATE todos SET title = ?1, notes = ?2, priority = ?3, due_date = ?4, \
             remind_before_minutes = ?5, sort_order = ?6, updated_at = ?7 WHERE id = ?8",
            params![
                v.title,
                v.notes,
                v.priority,
                v.due_date,
                v.remind_before_minutes,
                input.sort_order,
                now,
                id
            ],
        )
        .map_err(|e| format!("update todo #{id}: {e}"))?;
    if n == 0 {
        return Err(format!("todo #{id} 不存在"));
    }
    replace_tags(conn, id, &v.tags)?;
    let todo = todo_by_id(conn, id)?;
    sync_derived_reminder(conn, &todo)?;
    Ok(todo)
}

/// 删除 todo（TC-TD-07）：todo_tags 由 FK 级联清；派生 reminder 显式删
/// （reminder_logs 历史保留——002 迁移后无 FK 级联）。
pub fn delete_todo(conn: &Connection, id: i64) -> Result<(), String> {
    conn.execute("DELETE FROM reminders WHERE source_todo_id = ?1", [id])
        .map_err(|e| format!("delete derived reminder: {e}"))?;
    conn.execute("DELETE FROM todos WHERE id = ?1", [id])
        .map_err(|e| format!("delete todo #{id}: {e}"))?;
    Ok(())
}

/// 派生提醒同步（B16 通道，TC-TD-03/08）：todo 状态变化后调用。
/// - 可派生（未完成 + due 带时间 + before > 0）→ upsert kind='todo' 行；
///   start_time 变化时清 last_triggered_at（新日程获得新的一次性触发权）；
/// - 不可派生（before=0 / 纯日期 / 已完成）→ 删除派生行（0 = 完全无提醒）。
pub fn sync_derived_reminder(conn: &Connection, todo: &TodoItem) -> Result<(), String> {
    let derivable = todo.completed_at.is_none()
        && todo.remind_before_minutes > 0
        && todo
            .due_date
            .as_deref()
            .is_some_and(|d| derive_start_time(d, todo.remind_before_minutes).is_some());
    if !derivable {
        conn.execute("DELETE FROM reminders WHERE source_todo_id = ?1", [todo.id])
            .map_err(|e| format!("delete derived reminder: {e}"))?;
        return Ok(());
    }
    let due = todo.due_date.as_deref().unwrap();
    let start = derive_start_time(due, todo.remind_before_minutes).unwrap();
    let existing: Option<i64> = conn
        .query_row(
            "SELECT id FROM reminders WHERE source_todo_id = ?1",
            [todo.id],
            |r| r.get(0),
        )
        .ok();
    match existing {
        None => {
            conn.execute(
                "INSERT INTO reminders (kind, label, interval_minutes, start_time, end_time, \
                 enabled, use_fireworks, source_todo_id, todo_due_at, created_at) \
                 VALUES ('todo', ?1, 0, ?2, NULL, 1, 0, ?3, ?4, ?5)",
                params![
                    todo.title,
                    start,
                    todo.id,
                    due,
                    crate::reminder_scheduler::now_rfc3339()
                ],
            )
            .map_err(|e| format!("insert derived reminder: {e}"))?;
        }
        Some(rid) => {
            // label 随 title；start_time 变化 → 清 last_triggered_at（一次性重新武装）
            conn.execute(
                "UPDATE reminders SET label = ?1, start_time = ?2, todo_due_at = ?3, \
                 last_triggered_at = CASE WHEN start_time IS NOT ?2 THEN NULL \
                 ELSE last_triggered_at END WHERE id = ?4",
                params![todo.title, start, due, rid],
            )
            .map_err(|e| format!("update derived reminder: {e}"))?;
        }
    }
    Ok(())
}

/// 今日已完成数（completed_at 落今日本地自然日，TC-TD-05）。
pub fn count_completed_today(conn: &Connection) -> i64 {
    let today = local_today();
    let Ok(mut stmt) = conn.prepare("SELECT completed_at FROM todos WHERE completed_at IS NOT NULL")
    else {
        return 0;
    };
    let Ok(rows) = stmt.query_map([], |r| r.get::<_, String>(0)) else {
        return 0;
    };
    rows.filter_map(|r| r.ok())
        .filter(|ts| is_today_rfc3339(ts, &today))
        .count() as i64
}

/// 今日是否还有未完成且 due 在今日的 todo。
fn remaining_due_today(conn: &Connection) -> i64 {
    let today = local_today();
    let Ok(mut stmt) =
        conn.prepare("SELECT due_date FROM todos WHERE completed_at IS NULL AND due_date IS NOT NULL")
    else {
        return 0;
    };
    let Ok(rows) = stmt.query_map([], |r| r.get::<_, String>(0)) else {
        return 0;
    };
    rows.filter_map(|r| r.ok())
        .filter(|d| d.len() >= 10 && &d[..10] == today)
        .count() as i64
}

/// 完成 / 取消完成（TC-TD-04/05/07）。
pub fn complete_todo(
    conn: &Connection,
    id: i64,
    completed: bool,
) -> Result<TodoCompleteResult, String> {
    let before = todo_by_id(conn, id)?;
    let was_due_today = completed && todo_due_today(&before);
    let completed_at = if completed {
        Some(crate::reminder_scheduler::now_rfc3339())
    } else {
        None
    };
    conn.execute(
        "UPDATE todos SET completed_at = ?2, updated_at = ?3 WHERE id = ?1",
        params![id, completed_at, crate::reminder_scheduler::now_rfc3339()],
    )
    .map_err(|e| format!("complete todo #{id}: {e}"))?;
    let todo = todo_by_id(conn, id)?;
    // 完成 → 派生提醒级联删除；取消完成 → 恢复派生（若满足派生条件）
    sync_derived_reminder(conn, &todo)?;
    let all_today_done = was_due_today && remaining_due_today(conn) == 0;
    Ok(TodoCompleteResult {
        completed_today: count_completed_today(conn),
        all_today_done,
        was_due_today,
        todo,
    })
}

/// 重排（TC-TD-02）：按入参顺序重写 sort_order（0..n），返回新列表。
pub fn reorder_todos(conn: &Connection, ordered_ids: &[i64]) -> Result<Vec<TodoItem>, String> {
    for (idx, id) in ordered_ids.iter().enumerate() {
        conn.execute(
            "UPDATE todos SET sort_order = ?2 WHERE id = ?1",
            params![id, idx as i64],
        )
        .map_err(|e| format!("reorder todo #{id}: {e}"))?;
    }
    list_todos(conn)
}

// ---------------------------------------------------------------------------
// Tauri 命令（在 lib.rs 注册；写 reminders 后统一 reload 调度器）
// ---------------------------------------------------------------------------

#[tauri::command]
pub fn todo_list<R: tauri::Runtime>(app: tauri::AppHandle<R>) -> Result<Vec<TodoItem>, String> {
    let db = app.state::<std::sync::Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    list_todos(&conn)
}

/// 新建（id=None）/ 更新（id=Some）。
#[tauri::command]
pub fn todo_upsert<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    id: Option<i64>,
    input: TodoInput,
) -> Result<TodoItem, String> {
    let todo = {
        let db = app.state::<std::sync::Mutex<Connection>>();
        let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
        match id {
            Some(id) => update_todo(&conn, id, &input)?,
            None => insert_todo(&conn, &input)?,
        }
    };
    crate::reminder_scheduler::reload_from_app(&app)?;
    Ok(todo)
}

#[tauri::command]
pub fn todo_delete<R: tauri::Runtime>(app: tauri::AppHandle<R>, id: i64) -> Result<(), String> {
    {
        let db = app.state::<std::sync::Mutex<Connection>>();
        let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
        delete_todo(&conn, id)?;
    }
    crate::reminder_scheduler::reload_from_app(&app)
}

/// 完成/取消完成：返回庆祝信息，并广播 `todo://completed`（pet 窗口消费，
/// waving + 气泡；取消完成不广播）。
#[tauri::command]
pub fn todo_complete<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    id: i64,
    completed: bool,
) -> Result<TodoCompleteResult, String> {
    let result = {
        let db = app.state::<std::sync::Mutex<Connection>>();
        let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
        complete_todo(&conn, id, completed)?
    };
    crate::reminder_scheduler::reload_from_app(&app)?;
    if completed {
        let _ = app.emit(
            "todo://completed",
            serde_json::json!({
                "title": result.todo.title,
                "completed_today": result.completed_today,
                "all_today_done": result.all_today_done,
            }),
        );
    }
    Ok(result)
}

#[tauri::command]
pub fn todo_reorder<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    ordered_ids: Vec<i64>,
) -> Result<Vec<TodoItem>, String> {
    {
        let db = app.state::<std::sync::Mutex<Connection>>();
        let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
        reorder_todos(&conn, &ordered_ids)?;
    }
    // 排序不触碰 reminders；reload 无害（保持与 CRUD 同习惯）
    crate::reminder_scheduler::reload_from_app(&app)?;
    let db = app.state::<std::sync::Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    list_todos(&conn)
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

    fn input(title: &str) -> TodoInput {
        TodoInput {
            title: title.into(),
            notes: None,
            priority: 0,
            due_date: None,
            remind_before_minutes: 5,
            sort_order: 0,
            tags: vec![],
        }
    }

    fn derived_by_todo(c: &Connection, todo_id: i64) -> Option<(String, String, i64, String)> {
        c.query_row(
            "SELECT kind, start_time, interval_minutes, todo_due_at FROM reminders \
             WHERE source_todo_id = ?1",
            [todo_id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
        )
        .ok()
    }

    // ---- 校验（纯函数） ----

    #[test]
    fn validate_ok_and_failures() {
        let mut i = input("交报告");
        i.tags = vec!["work".into(), " work ".into(), "".into(), "urgent".into(), "work".into()];
        let v = validate_todo_input(&i).unwrap();
        assert_eq!(v.title, "交报告");
        assert_eq!(v.tags, vec!["work", "urgent"]); // trim + 去空 + 去重
        i.priority = 4;
        assert!(validate_todo_input(&i).is_err());
        i.priority = -1;
        assert!(validate_todo_input(&i).is_err());
        i.priority = 3;
        i.remind_before_minutes = -1;
        assert!(validate_todo_input(&i).is_err());
        i.remind_before_minutes = MAX_REMIND_BEFORE_MINUTES + 1;
        assert!(validate_todo_input(&i).is_err());
        i.remind_before_minutes = 0;
        // due 格式：合法两种 / 非法三种
        i.due_date = Some("2026-08-18".into());
        assert!(validate_todo_input(&i).is_ok());
        i.due_date = Some("2026-08-18T15:30".into());
        assert!(validate_todo_input(&i).is_ok());
        i.due_date = Some("2026-08-18 15:30".into()); // 空格分隔拒绝
        assert!(validate_todo_input(&i).is_err());
        i.due_date = Some("2026-8-18".into()); // 非零填充拒绝
        assert!(validate_todo_input(&i).is_err());
        i.due_date = Some("2026-08-18T25:00".into()); // 越界小时拒绝
        assert!(validate_todo_input(&i).is_err());
        i.due_date = None;
        // title
        i.title = "   ".into();
        assert!(validate_todo_input(&i).is_err());
        i.title = "x".repeat(141);
        assert!(validate_todo_input(&i).is_err());
    }

    #[test]
    fn derive_start_time_math() {
        assert_eq!(
            derive_start_time("2026-08-18T15:30", 5),
            Some("2026-08-18T15:25".into())
        );
        assert_eq!(
            derive_start_time("2026-08-18T00:03", 5),
            Some("2026-08-17T23:58".into()) // 跨日借位
        );
        assert_eq!(derive_start_time("2026-08-18T15:30", 0), None); // 0 = 不派生
        assert_eq!(derive_start_time("2026-08-18", 5), None); // 纯日期不派生
        assert_eq!(derive_start_time("bad", 5), None);
    }

    // ---- 派生提醒（TC-TD-03/08） ----

    #[test]
    fn upsert_derives_reminder_for_timed_due() {
        let c = conn();
        let mut i = input("交报告");
        i.due_date = Some("2026-08-18T15:30".into());
        i.remind_before_minutes = 5;
        i.tags = vec!["work".into()];
        let t = insert_todo(&c, &i).unwrap();
        let (kind, start, interval, due) = derived_by_todo(&c, t.id).unwrap();
        assert_eq!(kind, "todo");
        assert_eq!(start, "2026-08-18T15:25");
        assert_eq!(interval, 0);
        assert_eq!(due, "2026-08-18T15:30");
        // label = todo title（DESIGN §5.4）
        let label: String = c
            .query_row(
                "SELECT label FROM reminders WHERE source_todo_id = ?1",
                [t.id],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(label, "交报告");
        // tags 已写入
        assert_eq!(load_tags(&c, t.id).unwrap(), vec!["work"]);
    }

    #[test]
    fn remind_before_zero_derives_nothing_then_update_derives_tc_td_08() {
        let c = conn();
        let mut i = input("买猫粮");
        i.due_date = Some("2026-08-18T15:30".into());
        i.remind_before_minutes = 0;
        let t = insert_todo(&c, &i).unwrap();
        // 0 = 完全无提醒：reminders 表不出现该 todo 的行
        assert!(derived_by_todo(&c, t.id).is_none());
        let total: i64 = c
            .query_row("SELECT COUNT(*) FROM reminders", [], |r| r.get(0))
            .unwrap();
        assert_eq!(total, 0);
        // 随后修改 due 且 >0 → 才 upsert 派生
        i.remind_before_minutes = 10;
        i.due_date = Some("2026-08-19T09:00".into());
        let t2 = update_todo(&c, t.id, &i).unwrap();
        assert_eq!(t2.id, t.id);
        let (_, start, _, due) = derived_by_todo(&c, t.id).unwrap();
        assert_eq!(start, "2026-08-19T08:50");
        assert_eq!(due, "2026-08-19T09:00");
    }

    #[test]
    fn date_only_due_never_derives() {
        let c = conn();
        let mut i = input("周会");
        i.due_date = Some("2026-08-18".into());
        i.remind_before_minutes = 5;
        let t = insert_todo(&c, &i).unwrap();
        assert!(derived_by_todo(&c, t.id).is_none());
    }

    #[test]
    fn due_change_resets_last_triggered_and_title_syncs_label() {
        let c = conn();
        let mut i = input("交报告");
        i.due_date = Some("2026-08-18T15:30".into());
        let t = insert_todo(&c, &i).unwrap();
        // 模拟已触发（调度器写入）
        c.execute(
            "UPDATE reminders SET last_triggered_at = '2026-08-18T15:25:00.000+08:00' \
             WHERE source_todo_id = ?1",
            [t.id],
        )
        .unwrap();
        // 只改 title → label 跟随、last_triggered_at 保留
        i.title = "交年度报告".into();
        update_todo(&c, t.id, &i).unwrap();
        let (label, last): (String, Option<String>) = c
            .query_row(
                "SELECT label, last_triggered_at FROM reminders WHERE source_todo_id = ?1",
                [t.id],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .unwrap();
        assert_eq!(label, "交年度报告");
        assert!(last.is_some());
        // 改 due → start 变化 → last_triggered_at 清空（新日程重新武装一次性）
        i.due_date = Some("2026-08-20T10:00".into());
        update_todo(&c, t.id, &i).unwrap();
        let (start, last): (String, Option<String>) = c
            .query_row(
                "SELECT start_time, last_triggered_at FROM reminders WHERE source_todo_id = ?1",
                [t.id],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .unwrap();
        assert_eq!(start, "2026-08-20T09:55");
        assert!(last.is_none());
    }

    // ---- 完成联动（TC-TD-04/05） ----

    #[test]
    fn complete_writes_completed_at_deletes_derived_and_uncomplete_restores() {
        let c = conn();
        let mut i = input("交报告");
        i.due_date = Some("2026-08-18T15:30".into());
        let t = insert_todo(&c, &i).unwrap();
        let r = complete_todo(&c, t.id, true).unwrap();
        assert!(r.todo.completed_at.is_some());
        assert!(derived_by_todo(&c, t.id).is_none(), "完成即级联删派生行");
        // 取消完成 → 恢复派生
        let r2 = complete_todo(&c, t.id, false).unwrap();
        assert!(r2.todo.completed_at.is_none());
        assert!(derived_by_todo(&c, t.id).is_some());
    }

    #[test]
    fn today_counts_and_all_done_tc_td_05() {
        let c = conn();
        let mut a = input("A");
        a.due_date = Some(format!("{}T23:59", local_today()));
        let mut b = input("B");
        b.due_date = Some(format!("{}T23:59", local_today()));
        let mut other_day = input("C");
        other_day.due_date = Some("2030-01-01T09:00".into());
        let ta = insert_todo(&c, &a).unwrap();
        let tb = insert_todo(&c, &b).unwrap();
        let tc = insert_todo(&c, &other_day).unwrap();

        let r1 = complete_todo(&c, ta.id, true).unwrap();
        assert_eq!(r1.completed_today, 1);
        assert!(!r1.all_today_done, "今日还有 B 未完成");

        // 完成一个非今日 due 的 → 不算 all_today_done
        let rc = complete_todo(&c, tc.id, true).unwrap();
        assert!(!rc.all_today_done);
        assert_eq!(rc.completed_today, 2);

        let r2 = complete_todo(&c, tb.id, true).unwrap();
        assert!(r2.all_today_done, "最后一个今日任务完成 → 全清");
        assert_eq!(r2.completed_today, 3);
        assert!(r2.was_due_today);
    }

    // ---- 删除级联（TC-TD-07） ----

    #[test]
    fn delete_todo_cascades_tags_and_reminder_but_keeps_logs_tc_td_07() {
        let c = conn();
        let mut i = input("交报告");
        i.due_date = Some("2026-08-18T15:30".into());
        i.tags = vec!["work".into(), "报告".into()];
        let t = insert_todo(&c, &i).unwrap();
        // 派生提醒已触发过 → 有一条历史 log
        let rid: i64 = c
            .query_row(
                "SELECT id FROM reminders WHERE source_todo_id = ?1",
                [t.id],
                |r| r.get(0),
            )
            .unwrap();
        c.execute(
            "INSERT INTO reminder_logs (reminder_id, triggered_at) VALUES (?1, '2026-08-18T15:25:00.000+08:00')",
            [rid],
        )
        .unwrap();

        delete_todo(&c, t.id).unwrap();
        // todo / tags / 派生 reminder 全清
        let todos: i64 = c.query_row("SELECT COUNT(*) FROM todos", [], |r| r.get(0)).unwrap();
        assert_eq!(todos, 0);
        let tags: i64 = c
            .query_row("SELECT COUNT(*) FROM todo_tags", [], |r| r.get(0))
            .unwrap();
        assert_eq!(tags, 0);
        let reminders: i64 = c
            .query_row("SELECT COUNT(*) FROM reminders", [], |r| r.get(0))
            .unwrap();
        assert_eq!(reminders, 0);
        // reminder_logs 历史保留（002 迁移去掉了 FK 级联）
        let logs: i64 = c
            .query_row("SELECT COUNT(*) FROM reminder_logs", [], |r| r.get(0))
            .unwrap();
        assert_eq!(logs, 1, "reminder_logs history must survive");
    }

    // ---- 排序（TC-TD-02） ----

    #[test]
    fn list_orders_by_sort_order_and_reorder_applies_immediately() {
        let c = conn();
        let mut a = input("A");
        a.sort_order = 0;
        let mut b = input("B");
        b.sort_order = 1;
        let mut d = input("D");
        d.sort_order = 2;
        let ta = insert_todo(&c, &a).unwrap();
        let tb = insert_todo(&c, &b).unwrap();
        let td = insert_todo(&c, &d).unwrap();
        let titles = |v: &Vec<TodoItem>| v.iter().map(|t| t.title.clone()).collect::<Vec<_>>();
        assert_eq!(titles(&list_todos(&c).unwrap()), vec!["A", "B", "D"]);
        // 重排 D 到最前 → 顺序立即更新
        let out = reorder_todos(&c, &[td.id, ta.id, tb.id]).unwrap();
        assert_eq!(titles(&out), vec!["D", "A", "B"]);
        assert_eq!(titles(&list_todos(&c).unwrap()), vec!["D", "A", "B"]);
    }

    #[test]
    fn tags_replace_on_update_and_validation_rejects_bad() {
        let c = conn();
        let mut i = input("任务");
        i.tags = vec!["a".into(), "b".into()];
        let t = insert_todo(&c, &i).unwrap();
        assert_eq!(t.tags, vec!["a", "b"]);
        // 编辑时移除 a、新增 c → 全量替换语义（删除 tag 即时反映）
        i.tags = vec!["b".into(), "c".into()];
        let t2 = update_todo(&c, t.id, &i).unwrap();
        assert_eq!(t2.tags, vec!["b", "c"]);
        // 校验失败：tag 超长 / 超量
        i.tags = vec!["x".repeat(41)];
        assert!(update_todo(&c, t.id, &i).is_err());
        i.tags = (0..21).map(|n| format!("t{n}")).collect();
        assert!(update_todo(&c, t.id, &i).is_err());
    }

    // ---- 命令级集成（mock runtime：真实 command 函数 + managed state + emit） ----

    #[test]
    fn commands_end_to_end_via_mock_runtime() {
        // 手动构造最小状态面（与 lib.rs setup 同构）：db + RemindersState
        // （default 空态即可——命令内的 reload_from_app 会重读 db）。
        let app = tauri::test::mock_app();
        let handle = app.handle();
        let conn = Connection::open_in_memory().unwrap();
        crate::db::migrate(&conn).unwrap();
        handle.manage(std::sync::Mutex::new(conn));
        handle.manage(std::sync::Arc::new(std::sync::Mutex::new(
            crate::reminder_scheduler::RemindersState::default(),
        )));

        // 1) 新建带时间 due 的 todo → 派生提醒落库 + 调度器状态 reload 可见
        let mut i = input("集成测试任务");
        i.due_date = Some(format!("{}T23:59", local_today()));
        i.remind_before_minutes = 5;
        let t = todo_upsert(handle.clone(), None, i).unwrap();
        {
            let db = handle.state::<std::sync::Mutex<Connection>>();
            let c = db.lock().unwrap();
            let (kind, interval): (String, i64) = c
                .query_row(
                    "SELECT kind, interval_minutes FROM reminders WHERE source_todo_id = ?1",
                    [t.id],
                    |r| Ok((r.get(0)?, r.get(1)?)),
                )
                .unwrap();
            assert_eq!((kind.as_str(), interval), ("todo", 0));
        }
        let st = handle.state::<std::sync::Arc<
            std::sync::Mutex<crate::reminder_scheduler::RemindersState>,
        >>();
        assert_eq!(st.lock().unwrap().rules.len(), 1, "reload_from_app 已重读");

        // 2) 完成 → 派生行删 + completed_at 写入 + 返回庆祝信息
        let r = todo_complete(handle.clone(), t.id, true).unwrap();
        assert!(r.todo.completed_at.is_some());
        assert!(r.all_today_done, "今日唯一 due 任务完成 → 全清");
        {
            let db = handle.state::<std::sync::Mutex<Connection>>();
            let c = db.lock().unwrap();
            let n: i64 = c
                .query_row("SELECT COUNT(*) FROM reminders", [], |x| x.get(0))
                .unwrap();
            assert_eq!(n, 0);
        }

        // 3) 重排 / 列表 / 删除命令直调无 panic
        let list = todo_list(handle.clone()).unwrap();
        assert_eq!(list.len(), 1);
        let out = todo_reorder(handle.clone(), vec![t.id]).unwrap();
        assert_eq!(out.len(), 1);
        todo_delete(handle.clone(), t.id).unwrap();
        assert!(todo_list(handle.clone()).unwrap().is_empty());
    }
}
