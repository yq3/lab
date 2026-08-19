//! Token 统计（DESIGN §4，TC-TK-01~13）。
//!
//! - 路径探测：macOS/Linux `~/.local/share/opencode/opencode.db` → `opencode-canary.db`；
//!   Windows `%LOCALAPPDATA%\opencode\opencode.db` → canary（TC-TK-01/02）。
//! - 旧版本兜底：仅存在 `storage/session/*.json` 时报告 legacy-storage（"请升级 opencode"），
//!   不做完整解析、不崩溃（TC-TK-04）。
//! - 连接模式：`SQLITE_OPEN_READ_ONLY | SQLITE_OPEN_NO_MUTEX`，不用 WAL 不写 journal；
//!   **每次查询新建只读连接即开即关**（NO_MUTEX 不可跨线程共享，Tauri command 跑在
//!   tokio 线程池；TC-TK-05）。
//! - 聚合查询：by session / by day 严格按 DESIGN §4.1 SQL（session 表主键列为 `id`，
//!   设计 SQL 中的 `session_id` 以 `id AS session_id` 落地）；week/range 由前端传
//!   from/to 计算，后端不写死维度（TC-TK-07）。
//! - schema 白名单：查询前 `PRAGMA table_info(session)` 校验 tokens_*/cost 列白名单，
//!   缺失 → schema-mismatch（"请升级 pulse-pet"），不崩溃不查错列（TC-TK-13）。
//! - WAL 缺失：只读打开报错时映射为 no-database（"数据库未运行/未初始化"，TC-TK-03）。
//!
//! ## TC-TK-11 写入时机实测结论（2026-08-16，opencode 1.18.18 + 本机真实 opencode.db）
//!
//! `session` 表的 `cost`/`tokens_*` 为**逐 message 增量写入**，非 session 结束聚合写：
//! 观测一个进行中的会话（本机 2026-08-16 09:03），两次采样间隔 5s，`tokens_input` 从
//! 58263 → 58748、`time_updated` 跟随最近一次写入推进（滞后秒级）；session 结束时无
//! 额外的聚合写入动作。注意 `cost` 可能为 0（订阅/plan 模式无按量计费数据，观测到
//! 多个大 token 用量会话 cost=0.0）。
//! 据此气泡汇报只需新鲜度护栏：`time_updated` 与 `session.status=idle` 事件时间的
//! 差值 < 阈值（默认 60s，`PULSEPET_TOKEN_REPORT_MAX_LAG_MS` 可配）才显示，避免
//! 陈旧数字（TC-TK-11/12）。

use std::fmt;
use std::path::{Path, PathBuf};

use rusqlite::{Connection, OpenFlags};
use serde::{Deserialize, Serialize};

/// 错误码：数据库未运行/未初始化（TC-TK-03，含 WAL 缺失回退）。
pub const ERR_NO_DATABASE: &str = "no-database";
/// 错误码：旧版 opencode 纯文件存储（TC-TK-04）。
pub const ERR_LEGACY_STORAGE: &str = "legacy-storage";
/// 错误码：session 表缺 tokens_*/cost 列（TC-TK-13）。
pub const ERR_SCHEMA_MISMATCH: &str = "schema-mismatch";
/// 错误码：其它查询错误（非法 group_by、SQL 失败等）。
pub const ERR_QUERY: &str = "query";

/// 结构化错误：`Display` 为 `"code: message"`，前端 `parseStatsError` 按此拆分。
#[derive(Debug, Clone, PartialEq)]
pub struct StatsError {
    pub code: &'static str,
    pub message: String,
}

impl StatsError {
    pub fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
}

impl fmt::Display for StatsError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}

impl std::error::Error for StatsError {}

/// token 统计行（by session 为完整行；day/week/range 聚合行无 session_id/时间列）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TokenRow {
    pub session_id: Option<String>,
    pub project_id: Option<String>,
    /// 分组标签：day=`2026-08-16`，week=`2026-W33`，range/session 为 None。
    pub day: Option<String>,
    pub cost: f64,
    pub tokens_input: i64,
    pub tokens_output: i64,
    pub tokens_reasoning: i64,
    pub tokens_cache_read: i64,
    pub tokens_cache_write: i64,
    pub time_created: Option<i64>,
    pub time_updated: Option<i64>,
}

/// opencode 数据目录（平台区分；测试传自定义目录走 `detect_*` 纯函数）。
pub fn opencode_data_dir() -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        let base = std::env::var("LOCALAPPDATA").unwrap_or_else(|_| ".".to_string());
        PathBuf::from(base).join("opencode")
    }
    #[cfg(not(target_os = "windows"))]
    {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        PathBuf::from(home).join(".local").join("share").join("opencode")
    }
}

/// 按优先级探测数据库文件：`opencode.db` → `opencode-canary.db`（TC-TK-01/02）。
pub fn detect_db_path(data_dir: &Path) -> Option<PathBuf> {
    for name in ["opencode.db", "opencode-canary.db"] {
        let p = data_dir.join(name);
        if p.is_file() {
            return Some(p);
        }
    }
    None
}

/// 旧版本纯文件存储探测：`storage/session/` 目录存在且含任意条目（TC-TK-04）。
pub fn detect_legacy_storage(data_dir: &Path) -> bool {
    let dir = data_dir.join("storage").join("session");
    std::fs::read_dir(&dir)
        .map(|mut it| it.next().is_some())
        .unwrap_or(false)
}

/// session 表字段白名单（DESIGN §4.1 查询涉及的全部列；缺任一 → schema-mismatch）。
pub const SESSION_REQUIRED_COLUMNS: &[&str] = &[
    "id",
    "project_id",
    "cost",
    "tokens_input",
    "tokens_output",
    "tokens_reasoning",
    "tokens_cache_read",
    "tokens_cache_write",
    "time_created",
    "time_updated",
];

/// `PRAGMA table_info(session)` 白名单检测（TC-TK-13）。
pub fn check_session_schema(conn: &Connection) -> Result<(), StatsError> {
    let mut stmt = conn
        .prepare("PRAGMA table_info(session)")
        .map_err(|e| StatsError::new(ERR_SCHEMA_MISMATCH, format!("读取 schema 失败：{e}")))?;
    let columns: Vec<String> = stmt
        .query_map([], |row| row.get::<_, String>(1))
        .map_err(|e| StatsError::new(ERR_SCHEMA_MISMATCH, format!("读取 schema 失败：{e}")))?
        .filter_map(|r| r.ok())
        .collect();
    if columns.is_empty() {
        return Err(StatsError::new(
            ERR_SCHEMA_MISMATCH,
            "session 表不存在，请升级 pulse-pet",
        ));
    }
    let missing: Vec<&str> = SESSION_REQUIRED_COLUMNS
        .iter()
        .filter(|c| !columns.iter().any(|x| x == *c))
        .copied()
        .collect();
    if !missing.is_empty() {
        return Err(StatsError::new(
            ERR_SCHEMA_MISMATCH,
            format!("session 表缺少列 {missing:?}，请升级 pulse-pet"),
        ));
    }
    Ok(())
}

/// 每次查询新建只读连接（即开即关；NO_MUTEX 不跨线程共享，TC-TK-05）。
/// 打开失败（含 WAL 缺失的 `unable to open database file`）→ no-database（DESIGN §12）。
pub fn open_readonly(path: &Path) -> Result<Connection, StatsError> {
    Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .map_err(|e| StatsError::new(ERR_NO_DATABASE, format!("数据库未运行/未初始化（{e}）")))
}

fn session_columns() -> &'static str {
    "id AS session_id, project_id, cost, tokens_input, tokens_output, \
     tokens_reasoning, tokens_cache_read, tokens_cache_write, time_created, time_updated"
}

fn read_session_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<TokenRow> {
    Ok(TokenRow {
        session_id: row.get("session_id")?,
        project_id: row.get("project_id")?,
        day: None,
        cost: row.get("cost")?,
        tokens_input: row.get("tokens_input")?,
        tokens_output: row.get("tokens_output")?,
        tokens_reasoning: row.get("tokens_reasoning")?,
        tokens_cache_read: row.get("tokens_cache_read")?,
        tokens_cache_write: row.get("tokens_cache_write")?,
        time_created: row.get("time_created")?,
        time_updated: row.get("time_updated")?,
    })
}

/// by session（DESIGN §4.1 原样语义，`WHERE time_updated` 范围 + `ORDER BY` 倒序）。
pub fn query_by_session(
    conn: &Connection,
    from_ms: i64,
    to_ms: i64,
) -> Result<Vec<TokenRow>, StatsError> {
    let sql = format!(
        "SELECT {} FROM session WHERE time_updated >= ?1 AND time_updated <= ?2 \
         ORDER BY time_updated DESC",
        session_columns()
    );
    let mut stmt = conn
        .prepare(&sql)
        .map_err(|e| StatsError::new(ERR_QUERY, format!("prepare 失败：{e}")))?;
    let rows = stmt
        .query_map([from_ms, to_ms], read_session_row)
        .map_err(|e| StatsError::new(ERR_QUERY, format!("查询失败：{e}")))?;
    let mut out = Vec::new();
    for r in rows {
        out.push(r.map_err(|e| StatsError::new(ERR_QUERY, format!("读取失败：{e}")))?);
    }
    Ok(out)
}

/// by day（DESIGN §4.1 原样：strftime 天维度 + SUM + GROUP BY day, project_id）。
pub fn query_by_day(
    conn: &Connection,
    from_ms: i64,
    to_ms: i64,
) -> Result<Vec<TokenRow>, StatsError> {
    query_grouped(
        conn,
        from_ms,
        to_ms,
        "strftime('%Y-%m-%d', time_updated/1000, 'unixepoch', 'localtime')",
    )
}

/// by week（周标签 `%Y-W%W`，同 day 聚合形状；from/to 由前端传，不写死维度）。
pub fn query_by_week(
    conn: &Connection,
    from_ms: i64,
    to_ms: i64,
) -> Result<Vec<TokenRow>, StatsError> {
    query_grouped(
        conn,
        from_ms,
        to_ms,
        "strftime('%Y-W%W', time_updated/1000, 'unixepoch', 'localtime')",
    )
}

/// by range（任意跨度的按项目聚合，day 为 None；from/to 由前端传）。
pub fn query_by_range(
    conn: &Connection,
    from_ms: i64,
    to_ms: i64,
) -> Result<Vec<TokenRow>, StatsError> {
    let sql = "\
        SELECT NULL AS day, project_id, \
               SUM(cost) AS cost, \
               SUM(tokens_input) AS tokens_input, SUM(tokens_output) AS tokens_output, \
               SUM(tokens_reasoning) AS tokens_reasoning, \
               SUM(tokens_cache_read) AS tokens_cache_read, \
               SUM(tokens_cache_write) AS tokens_cache_write \
        FROM session WHERE time_updated >= ?1 AND time_updated <= ?2 \
        GROUP BY project_id";
    let mut stmt = conn
        .prepare(sql)
        .map_err(|e| StatsError::new(ERR_QUERY, format!("prepare 失败：{e}")))?;
    let rows = stmt
        .query_map([from_ms, to_ms], |row| {
            Ok(TokenRow {
                session_id: None,
                project_id: row.get("project_id")?,
                day: None,
                cost: row.get("cost")?,
                tokens_input: row.get("tokens_input")?,
                tokens_output: row.get("tokens_output")?,
                tokens_reasoning: row.get("tokens_reasoning")?,
                tokens_cache_read: row.get("tokens_cache_read")?,
                tokens_cache_write: row.get("tokens_cache_write")?,
                time_created: None,
                time_updated: None,
            })
        })
        .map_err(|e| StatsError::new(ERR_QUERY, format!("查询失败：{e}")))?;
    let mut out = Vec::new();
    for r in rows {
        out.push(r.map_err(|e| StatsError::new(ERR_QUERY, format!("读取失败：{e}")))?);
    }
    Ok(out)
}

fn query_grouped(
    conn: &Connection,
    from_ms: i64,
    to_ms: i64,
    day_expr: &str,
) -> Result<Vec<TokenRow>, StatsError> {
    let sql = format!(
        "SELECT {day_expr} AS day, project_id, \
                SUM(cost) AS cost, \
                SUM(tokens_input) AS tokens_input, SUM(tokens_output) AS tokens_output, \
                SUM(tokens_reasoning) AS tokens_reasoning, \
                SUM(tokens_cache_read) AS tokens_cache_read, \
                SUM(tokens_cache_write) AS tokens_cache_write \
         FROM session WHERE time_updated >= ?1 AND time_updated <= ?2 \
         GROUP BY day, project_id ORDER BY day DESC"
    );
    let mut stmt = conn
        .prepare(&sql)
        .map_err(|e| StatsError::new(ERR_QUERY, format!("prepare 失败：{e}")))?;
    let rows = stmt
        .query_map([from_ms, to_ms], |row| {
            Ok(TokenRow {
                session_id: None,
                project_id: row.get("project_id")?,
                day: row.get("day")?,
                cost: row.get("cost")?,
                tokens_input: row.get("tokens_input")?,
                tokens_output: row.get("tokens_output")?,
                tokens_reasoning: row.get("tokens_reasoning")?,
                tokens_cache_read: row.get("tokens_cache_read")?,
                tokens_cache_write: row.get("tokens_cache_write")?,
                time_created: None,
                time_updated: None,
            })
        })
        .map_err(|e| StatsError::new(ERR_QUERY, format!("查询失败：{e}")))?;
    let mut out = Vec::new();
    for r in rows {
        out.push(r.map_err(|e| StatsError::new(ERR_QUERY, format!("读取失败：{e}")))?);
    }
    Ok(out)
}

/// 当前会话行（TC-TK-12：无记录返回 `Ok(None)`，由调用方决定不出气泡）。
pub fn query_current_session(
    conn: &Connection,
    session_id: &str,
) -> Result<Option<TokenRow>, StatsError> {
    let sql = format!("SELECT {} FROM session WHERE id = ?1", session_columns());
    let mut stmt = conn
        .prepare(&sql)
        .map_err(|e| StatsError::new(ERR_QUERY, format!("prepare 失败：{e}")))?;
    let mut rows = stmt
        .query_map([session_id], read_session_row)
        .map_err(|e| StatsError::new(ERR_QUERY, format!("查询失败：{e}")))?;
    match rows.next() {
        Some(row) => Ok(Some(row.map_err(|e| {
            StatsError::new(ERR_QUERY, format!("读取失败：{e}"))
        })?)),
        None => Ok(None),
    }
}

/// 查询编排：路径探测 → legacy 兜底 → 只读连接 → schema 白名单 → 聚合。
/// 数据库不存在时区分 no-database / legacy-storage（TC-TK-03/04）。
pub fn query_stats(
    data_dir: &Path,
    from_ms: i64,
    to_ms: i64,
    group_by: &str,
) -> Result<Vec<TokenRow>, StatsError> {
    let path = match detect_db_path(data_dir) {
        Some(p) => p,
        None => {
            return Err(if detect_legacy_storage(data_dir) {
                StatsError::new(
                    ERR_LEGACY_STORAGE,
                    "检测到旧版 opencode 存储格式（storage/session/*.json），请升级 opencode",
                )
            } else {
                StatsError::new(ERR_NO_DATABASE, "数据库未运行/未初始化")
            })
        }
    };
    let conn = open_readonly(&path)?;
    check_session_schema(&conn)?;
    match group_by {
        "session" => query_by_session(&conn, from_ms, to_ms),
        "day" => query_by_day(&conn, from_ms, to_ms),
        "week" => query_by_week(&conn, from_ms, to_ms),
        "range" => query_by_range(&conn, from_ms, to_ms),
        other => Err(StatsError::new(
            ERR_QUERY,
            format!("invalid group_by: {other}（应为 session/day/week/range）"),
        )),
    }
}

/// 当前会话查询编排（命令层用）。
pub fn current_session(
    data_dir: &Path,
    session_id: &str,
) -> Result<Option<TokenRow>, StatsError> {
    let path = detect_db_path(data_dir).ok_or_else(|| {
        StatsError::new(ERR_NO_DATABASE, "数据库未运行/未初始化")
    })?;
    let conn = open_readonly(&path)?;
    check_session_schema(&conn)?;
    query_current_session(&conn, session_id)
}

// ---------------------------------------------------------------------------
// 当前会话气泡汇报（DESIGN §4.3 末条，TC-TK-10/11/12）
// ---------------------------------------------------------------------------

/// token 数字格式化：`58263` → `58.3k`；`1234567` → `1.2M`；`910` → `910`。
pub fn format_tokens_k(n: i64) -> String {
    let a = n.unsigned_abs();
    if a >= 1_000_000 {
        format!("{:.1}M", n as f64 / 1_000_000.0)
    } else if a >= 1_000 {
        format!("{:.1}k", n as f64 / 1_000.0)
    } else {
        n.to_string()
    }
}

/// cost 格式化：`0` → `$0`；`<0.01` 用 4 位小数（2 位会显示成 $0.00）；其余 2 位。
pub fn format_cost_usd(c: f64) -> String {
    if c <= 0.0 {
        "$0".to_string()
    } else if c < 0.01 {
        format!("${c:.4}")
    } else {
        format!("${c:.2}")
    }
}

/// 气泡文案（白名单模板：仅由数字格式化生成，不含任何原始 prompt/路径/URL；
/// 长度恒 <140、单行，前端 `sanitizeBubbleText` 再兜底一次）。
/// M8 i18n：文案模板随全局语言位切换（zh 与 M3 定案逐字一致）。
pub fn format_session_report(row: &TokenRow) -> String {
    crate::i18n::current().token_report(
        &format_tokens_k(row.tokens_input),
        &format_tokens_k(row.tokens_output),
        &format_cost_usd(row.cost),
    )
}

/// 是否出气泡：有真实用量（token 或 cost > 0）且 `time_updated` 新鲜（TC-TK-11/12）。
pub fn should_report(row: &TokenRow, now_ms: i64, max_lag_ms: i64) -> bool {
    let has_usage = row.cost > 0.0
        || row.tokens_input > 0
        || row.tokens_output > 0
        || row.tokens_reasoning > 0
        || row.tokens_cache_read > 0
        || row.tokens_cache_write > 0;
    let fresh = row
        .time_updated
        .is_some_and(|t| (now_ms - t).abs() <= max_lag_ms);
    has_usage && fresh
}

/// idle 事件 → 气泡文案（任一环节不满足/出错都返回 `None` = 不出气泡，静默不崩）。
pub fn build_idle_report(
    data_dir: &Path,
    session_id: &str,
    now_ms: i64,
    max_lag_ms: i64,
) -> Option<String> {
    let row = current_session(data_dir, session_id).ok()??;
    if !should_report(&row, now_ms, max_lag_ms) {
        return None;
    }
    Some(format_session_report(&row))
}

/// 气泡新鲜度阈值（默认 60s，`PULSEPET_TOKEN_REPORT_MAX_LAG_MS` 可配）。
pub fn report_max_lag_ms() -> i64 {
    std::env::var("PULSEPET_TOKEN_REPORT_MAX_LAG_MS")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(60_000)
}

// ---------------------------------------------------------------------------
// Tauri 命令（DESIGN §4.2；在 lib.rs 注册）
// ---------------------------------------------------------------------------

/// 探测 opencode 数据库路径（TC-TK-01/02；无 → None，TC-TK-03）。
/// 返回 `Result<Option<PathBuf>, String>` 与 DESIGN §4.2 签名对齐（M3 P3-④；
/// 该命令无失败路径，恒为 `Ok`）。
#[tauri::command]
pub fn token_stats_opencode_path() -> Result<Option<PathBuf>, String> {
    Ok(detect_db_path(&opencode_data_dir()))
}

/// 聚合查询（group_by: session/day/week/range；错误序列化为 "code: message"）。
#[tauri::command]
pub fn token_stats_query(
    from_ms: i64,
    to_ms: i64,
    group_by: String,
) -> Result<Vec<TokenRow>, String> {
    query_stats(&opencode_data_dir(), from_ms, to_ms, &group_by)
        .map_err(|e| e.to_string())
}

/// 当前会话行（TC-TK-10/12）。
#[tauri::command]
pub fn token_stats_current_session(session_id: String) -> Result<Option<TokenRow>, String> {
    current_session(&opencode_data_dir(), &session_id).map_err(|e| e.to_string())
}

/// 当前系统毫秒时间戳（气泡新鲜度比较用）。
pub fn now_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

// ---------------------------------------------------------------------------
// 测试
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    /// 与真实 opencode.db 一致的 session 表建表语句（白名单列 + 少量真实存在的
    /// 其它列，模拟 opencode 1.18.x schema）。
    const CREATE_SESSION: &str = "\
        CREATE TABLE session (\
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, directory TEXT NOT NULL, \
            title TEXT NOT NULL, cost REAL NOT NULL DEFAULT 0, \
            tokens_input INTEGER NOT NULL DEFAULT 0, \
            tokens_output INTEGER NOT NULL DEFAULT 0, \
            tokens_reasoning INTEGER NOT NULL DEFAULT 0, \
            tokens_cache_read INTEGER NOT NULL DEFAULT 0, \
            tokens_cache_write INTEGER NOT NULL DEFAULT 0, \
            time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL)";

    /// 旧 schema（缺 tokens_* 列）建表语句（TC-TK-13）。
    const CREATE_SESSION_OLD: &str = "\
        CREATE TABLE session (\
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, cost REAL NOT NULL DEFAULT 0, \
            time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL)";

    fn ms(secs: i64) -> i64 {
        secs * 1000
    }

    fn temp_dir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "pulsepet-tk-{}-{}-{tag}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    /// 建一个临时 opencode 数据目录 + 指定 schema 的 opencode.db。
    fn make_db(tag: &str, create_sql: &str) -> PathBuf {
        let dir = temp_dir(tag);
        let db = dir.join("opencode.db");
        let conn = Connection::open(&db).unwrap();
        conn.execute_batch(create_sql).unwrap();
        conn.execute_batch("PRAGMA journal_mode=WAL;").unwrap();
        conn.close().unwrap();
        dir
    }

    fn insert_session(
        dir: &Path,
        id: &str,
        project: &str,
        cost: f64,
        tokens: (i64, i64, i64, i64, i64),
        created: i64,
        updated: i64,
    ) {
        let conn = open_readonly_unchecked(dir);
        conn.execute(
            "INSERT INTO session (id, project_id, directory, title, cost, tokens_input, \
             tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write, \
             time_created, time_updated) VALUES (?1,?2,'/tmp','t',?3,?4,?5,?6,?7,?8,?9,?10)",
            rusqlite::params![
                id,
                project,
                cost,
                tokens.0,
                tokens.1,
                tokens.2,
                tokens.3,
                tokens.4,
                created,
                updated
            ],
        )
        .unwrap();
    }

    /// 测试插数用的读写连接（业务代码本身仍走 open_readonly）。
    fn open_readonly_unchecked(dir: &Path) -> Connection {
        Connection::open(dir.join("opencode.db")).unwrap()
    }

    // ---- 路径探测（TC-TK-01/02/03） ----

    #[test]
    fn detect_prefers_main_db_then_canary() {
        let dir = temp_dir("detect");
        assert_eq!(detect_db_path(&dir), None); // 都不存在 → None
        std::fs::write(dir.join("opencode-canary.db"), b"").unwrap();
        assert_eq!(
            detect_db_path(&dir),
            Some(dir.join("opencode-canary.db"))
        ); // 仅 canary → canary
        std::fs::write(dir.join("opencode.db"), b"").unwrap();
        assert_eq!(
            detect_db_path(&dir),
            Some(dir.join("opencode.db"))
        ); // 主库优先
    }

    #[test]
    fn detect_legacy_storage_requires_session_entries() {
        let dir = temp_dir("legacy");
        assert!(!detect_legacy_storage(&dir)); // 目录不存在
        let s = dir.join("storage").join("session");
        std::fs::create_dir_all(&s).unwrap();
        assert!(!detect_legacy_storage(&dir)); // 空目录不算
        std::fs::write(s.join("ses_abc.json"), b"{}").unwrap();
        assert!(detect_legacy_storage(&dir)); // 有 json 条目
    }

    #[test]
    fn query_stats_no_db_maps_to_no_database() {
        let dir = temp_dir("nodb");
        let err = query_stats(&dir, 0, 1, "day").unwrap_err();
        assert_eq!(err.code, ERR_NO_DATABASE);
        assert!(err.message.contains("未运行"));
    }

    #[test]
    fn query_stats_legacy_storage_maps_to_upgrade_hint() {
        // TC-TK-04：仅存在旧格式 → legacy-storage（"请升级 opencode"），不崩溃
        let dir = temp_dir("legacy2");
        let s = dir.join("storage").join("session");
        std::fs::create_dir_all(&s).unwrap();
        std::fs::write(s.join("ses_x.json"), b"{}").unwrap();
        let err = query_stats(&dir, 0, 1, "day").unwrap_err();
        assert_eq!(err.code, ERR_LEGACY_STORAGE);
        assert!(err.message.contains("升级 opencode"));
    }

    // ---- schema 白名单（TC-TK-13） ----

    #[test]
    fn schema_missing_token_columns_rejected() {
        let dir = make_db("schema", CREATE_SESSION_OLD);
        let conn = open_readonly(&dir.join("opencode.db")).unwrap();
        let err = check_session_schema(&conn).unwrap_err();
        assert_eq!(err.code, ERR_SCHEMA_MISMATCH);
        assert!(err.message.contains("升级 pulse-pet"));
        // 全链路：query_stats 也在查询前拦截（不查错列）
        let err = query_stats(&dir, 0, i64::MAX, "session").unwrap_err();
        assert_eq!(err.code, ERR_SCHEMA_MISMATCH);
    }

    #[test]
    fn schema_complete_passes() {
        let dir = make_db("schema-ok", CREATE_SESSION);
        let conn = open_readonly(&dir.join("opencode.db")).unwrap();
        assert!(check_session_schema(&conn).is_ok());
    }

    // ---- 聚合查询（TC-TK-06/07） ----

    #[test]
    fn query_by_session_rows_and_order() {
        let dir = make_db("sess", CREATE_SESSION);
        insert_session(&dir, "s1", "p1", 0.5, (100, 20, 3, 400, 50), ms(1000), ms(2000));
        insert_session(&dir, "s2", "p2", 1.25, (2000, 300, 0, 0, 0), ms(1000), ms(9000));
        let conn = open_readonly(&dir.join("opencode.db")).unwrap();
        let rows = query_by_session(&conn, 0, ms(10_000)).unwrap();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].session_id.as_deref(), Some("s2")); // time_updated 倒序
        assert_eq!(rows[1].session_id.as_deref(), Some("s1"));
        assert_eq!(rows[0].cost, 1.25);
        assert_eq!(rows[0].tokens_input, 2000);
        assert_eq!(rows[1].tokens_cache_read, 400);
        // 时间范围过滤
        let rows = query_by_session(&conn, ms(1500), ms(3000)).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].session_id.as_deref(), Some("s1"));
    }

    #[test]
    fn query_by_day_groups_by_local_day_and_project() {
        let dir = make_db("day", CREATE_SESSION);
        // 同一天两个 session 同项目 → SUM 聚合；另一天另一项目 → 分组
        // 2026-08-16 00:00:00 本地时间的毫秒时间戳（测试环境时区无关地取当天零点）
        let day0 = local_midnight_ms(2026, 8, 16);
        insert_session(&dir, "s1", "p1", 0.10, (100, 20, 0, 0, 0), day0, day0 + ms(3600));
        insert_session(&dir, "s2", "p1", 0.20, (200, 30, 0, 0, 0), day0, day0 + ms(7200));
        let day1 = local_midnight_ms(2026, 8, 15);
        insert_session(&dir, "s3", "p2", 0.40, (400, 60, 0, 0, 0), day1, day1 + ms(3600));
        let conn = open_readonly(&dir.join("opencode.db")).unwrap();
        let rows = query_by_day(&conn, 0, day0 + ms(86_400)).unwrap();
        assert_eq!(rows.len(), 2, "两个 (day, project) 分组");
        // ORDER BY day DESC：首行是 2026-08-16 的 p1 聚合
        let r = &rows[0];
        assert_eq!(r.day.as_deref(), Some("2026-08-16"));
        assert_eq!(r.project_id.as_deref(), Some("p1"));
        assert!((r.cost - 0.30).abs() < 1e-9); // 浮点 SUM 用近似比较
        assert_eq!(r.tokens_input, 300);
        assert_eq!(r.tokens_output, 50);
        assert_eq!(rows[1].day.as_deref(), Some("2026-08-15"));
        assert_eq!(rows[1].project_id.as_deref(), Some("p2"));
    }

    #[test]
    fn query_by_week_labels_and_aggregates() {
        let dir = make_db("week", CREATE_SESSION);
        let d = local_midnight_ms(2026, 8, 11); // 周一（2026-08-10 为 ISO 周一）
        insert_session(&dir, "s1", "p1", 0.1, (10, 1, 0, 0, 0), d, d + ms(3600));
        let d2 = local_midnight_ms(2026, 8, 13);
        insert_session(&dir, "s2", "p1", 0.2, (20, 2, 0, 0, 0), d2, d2 + ms(3600));
        let conn = open_readonly(&dir.join("opencode.db")).unwrap();
        let rows = query_by_week(&conn, 0, d2 + ms(86_400)).unwrap();
        assert_eq!(rows.len(), 1, "同一周同项目 → 单行聚合");
        assert_eq!(rows[0].day.as_deref(), Some("2026-W32"));
        assert!((rows[0].cost - 0.30).abs() < 1e-9);
        assert_eq!(rows[0].tokens_input, 30);
    }

    #[test]
    fn query_by_range_aggregates_per_project_without_day() {
        let dir = make_db("range", CREATE_SESSION);
        let d = local_midnight_ms(2026, 8, 16);
        insert_session(&dir, "s1", "p1", 0.1, (10, 1, 0, 0, 0), d, d + ms(1));
        insert_session(&dir, "s2", "p1", 0.2, (20, 2, 0, 0, 0), d, d + ms(2));
        insert_session(&dir, "s3", "p2", 0.4, (40, 4, 0, 0, 0), d, d + ms(3));
        let conn = open_readonly(&dir.join("opencode.db")).unwrap();
        let mut rows = query_by_range(&conn, 0, d + ms(10)).unwrap();
        rows.sort_by(|a, b| a.project_id.cmp(&b.project_id));
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].project_id.as_deref(), Some("p1"));
        assert!((rows[0].cost - 0.30).abs() < 1e-9);
        assert_eq!(rows[0].day, None);
        assert_eq!(rows[0].session_id, None);
        assert_eq!(rows[1].project_id.as_deref(), Some("p2"));
    }

    #[test]
    fn query_stats_dispatches_group_by_and_rejects_unknown() {
        let dir = make_db("dispatch", CREATE_SESSION);
        let d = local_midnight_ms(2026, 8, 16);
        insert_session(&dir, "s1", "p1", 0.5, (100, 10, 0, 0, 0), d, d + ms(1));
        for g in ["session", "day", "week", "range"] {
            let rows = query_stats(&dir, 0, d + ms(10), g).unwrap();
            assert_eq!(rows.len(), 1, "group_by={g} 应返回 1 行");
        }
        let err = query_stats(&dir, 0, d + ms(10), "month").unwrap_err();
        assert_eq!(err.code, ERR_QUERY);
        assert!(err.message.contains("invalid group_by"));
    }

    // ---- 当前会话（TC-TK-10/12） ----

    #[test]
    fn current_session_found_and_missing() {
        let dir = make_db("cur", CREATE_SESSION);
        let d = local_midnight_ms(2026, 8, 16);
        insert_session(&dir, "ses_1", "p1", 0.01, (1000, 200, 0, 0, 0), d, d + ms(60));
        let row = current_session(&dir, "ses_1").unwrap().expect("应有记录");
        assert_eq!(row.tokens_input, 1000);
        assert_eq!(row.cost, 0.01);
        // TC-TK-12：无记录 → Ok(None)
        assert!(current_session(&dir, "ses_nope").unwrap().is_none());
    }

    // ---- 只读连接（TC-TK-05） ----

    #[test]
    fn readonly_connection_rejects_writes() {
        let dir = make_db("ro", CREATE_SESSION);
        let conn = open_readonly(&dir.join("opencode.db")).unwrap();
        let err = conn.execute("DELETE FROM session", []).unwrap_err();
        assert!(
            err.to_string().to_lowercase().contains("readonly")
                || err.to_string().to_lowercase().contains("read-only"),
            "只读连接不允许写入：{err}"
        );
    }

    #[test]
    fn concurrent_reads_while_writer_active() {
        // TC-TK-05：WAL 写入进行中，反复开只读连接查询 → 不锁冲突
        let dir = make_db("conc", CREATE_SESSION);
        let d = local_midnight_ms(2026, 8, 16);
        insert_session(&dir, "s1", "p1", 0.0, (10, 1, 0, 0, 0), d, d + ms(1));
        let writer = Connection::open(dir.join("opencode.db")).unwrap();
        writer.execute_batch("PRAGMA journal_mode=WAL;").unwrap();
        // 写事务持有期间并发读
        writer.execute("INSERT INTO session (id, project_id, directory, title, cost, tokens_input, tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write, time_created, time_updated) VALUES ('s2','p1','/t','t',0.1,5,5,0,0,0,?1,?1)", [d + ms(2)]).unwrap();
        for _ in 0..10 {
            let conn = open_readonly(&dir.join("opencode.db")).unwrap();
            let rows = query_by_session(&conn, 0, d + ms(10)).unwrap();
            assert_eq!(rows.len(), 2);
        }
    }

    // ---- 气泡汇报（TC-TK-10/11/12） ----

    #[test]
    fn format_tokens_and_cost() {
        assert_eq!(format_tokens_k(910), "910");
        assert_eq!(format_tokens_k(1000), "1.0k");
        assert_eq!(format_tokens_k(58263), "58.3k");
        assert_eq!(format_tokens_k(1234567), "1.2M");
        assert_eq!(format_cost_usd(0.0), "$0");
        assert_eq!(format_cost_usd(0.0103), "$0.01"); // ≥0.01 用 2 位小数
        assert_eq!(format_cost_usd(0.0031), "$0.0031"); // <0.01 用 4 位（避免显示 $0.00）
        assert_eq!(format_cost_usd(0.526), "$0.53");
        assert_eq!(format_cost_usd(12.3), "$12.30");
    }

    #[test]
    fn format_session_report_is_short_single_line() {
        let row = TokenRow {
            session_id: Some("s".into()),
            project_id: None,
            day: None,
            cost: 0.0526,
            tokens_input: 58263,
            tokens_output: 910,
            tokens_reasoning: 0,
            tokens_cache_read: 0,
            tokens_cache_write: 0,
            time_created: None,
            time_updated: None,
        };
        let text = format_session_report(&row);
        assert_eq!(text, "本期用了 58.3k input / 910 output / $0.05");
        assert!(!text.contains('\n'));
        assert!(text.chars().count() <= 140);
    }

    #[test]
    fn should_report_requires_usage_and_freshness() {
        let base = |cost: f64, tokens: i64, updated: i64| TokenRow {
            session_id: None,
            project_id: None,
            day: None,
            cost,
            tokens_input: tokens,
            tokens_output: 0,
            tokens_reasoning: 0,
            tokens_cache_read: 0,
            tokens_cache_write: 0,
            time_created: None,
            time_updated: Some(updated),
        };
        let now = ms(10_000);
        let lag = 60_000;
        // 有用量 + 新鲜 → 报告
        assert!(should_report(&base(0.0, 100, now - 5_000), now, lag));
        // TC-TK-12：无用量（全 0）→ 不报告（不出 0 气泡）
        assert!(!should_report(&base(0.0, 0, now), now, lag));
        // 有用量但数字陈旧（time_updated 落后 > 阈值）→ 不报告（TC-TK-11）
        assert!(!should_report(&base(0.0, 100, now - lag - 1), now, lag));
        // cost>0 但 token 全 0 也算有用量
        assert!(should_report(&base(0.01, 0, now), now, lag));
        // 无 time_updated → 不报告
        let mut r = base(1.0, 100, now);
        r.time_updated = None;
        assert!(!should_report(&r, now, lag));
    }

    #[test]
    fn build_idle_report_end_to_end() {
        let dir = make_db("report", CREATE_SESSION);
        let now = ms(1_000_000);
        // 新鲜 + 有用量 → Some(文案)
        insert_session(
            &dir,
            "ses_live",
            "p1",
            0.05,
            (58_263, 910, 0, 0, 0),
            now - ms(600),
            now - ms(2),
        );
        assert_eq!(
            build_idle_report(&dir, "ses_live", now, 60_000),
            Some("本期用了 58.3k input / 910 output / $0.05".to_string())
        );
        // 陈旧 → None
        insert_session(
            &dir,
            "ses_stale",
            "p1",
            0.05,
            (1000, 100, 0, 0, 0),
            now - ms(3600),
            now - ms(3600),
        );
        assert_eq!(build_idle_report(&dir, "ses_stale", now, 60_000), None);
        // TC-TK-12：无记录 → None（不出气泡、不显示 0/陈旧数字）
        assert_eq!(build_idle_report(&dir, "ses_none", now, 60_000), None);
        // 数据库不存在 → None（静默，不崩）
        let nodir = temp_dir("report-nodb");
        assert_eq!(build_idle_report(&nodir, "ses_x", now, 60_000), None);
    }

    /// 指定本地日期零点的毫秒时间戳（时区无关地构造，供 day/week 分组测试）。
    fn local_midnight_ms(y: i64, m: i64, d: i64) -> i64 {
        // 用 SQLite 自己算（与被测 SQL 的 localtime 语义一致）
        let conn = Connection::open_in_memory().unwrap();
        conn.query_row(
            "SELECT CAST(strftime('%s', ?1, 'start of day') AS INTEGER) * 1000",
            [format!("{y:04}-{m:02}-{d:02}")],
            |r| r.get::<_, i64>(0),
        )
        .unwrap()
    }

    // ---- 真实库对账（TC-TK-06；手动跑：--ignored --nocapture） ----

    #[test]
    #[ignore = "manual: 需本机真实 opencode.db（对账证据用）"]
    fn real_db_reconciliation_manual() {
        let dir = opencode_data_dir();
        let Some(path) = detect_db_path(&dir) else {
            eprintln!("[reconcile] 本机无 opencode.db，跳过");
            return;
        };
        println!("[reconcile] db = {}", path.display());
        let to = now_ms();
        let from = to - 30 * 24 * 3600 * 1000;
        // ours：by day / by session
        let day_rows = query_stats(&dir, from, to, "day").unwrap();
        let sess_rows = query_stats(&dir, from, to, "session").unwrap();
        // reference：直接执行 DESIGN §4.1 原始 SQL（另一条只读连接）
        let conn = open_readonly(&path).unwrap();
        let (ref_day_cost, ref_day_cnt): (f64, i64) = conn
            .query_row(
                "SELECT IFNULL(SUM(cost),0), COUNT(*) FROM (\
                 SELECT strftime('%Y-%m-%d', time_updated/1000,'unixepoch','localtime') AS day, \
                 project_id, SUM(cost) AS cost FROM session \
                 WHERE time_updated >= ?1 AND time_updated <= ?2 GROUP BY day, project_id)",
                [from, to],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .unwrap();
        let (ref_sess_cost, ref_sess_cnt): (f64, i64) = conn
            .query_row(
                "SELECT IFNULL(SUM(cost),0), COUNT(*) FROM session \
                 WHERE time_updated >= ?1 AND time_updated <= ?2",
                [from, to],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .unwrap();
        let our_day_cost: f64 = day_rows.iter().map(|r| r.cost).sum();
        let our_sess_cost: f64 = sess_rows.iter().map(|r| r.cost).sum();
        println!(
            "[reconcile] by day: rows {} vs {} | cost {:.6} vs {:.6} | diff {:.8}",
            day_rows.len(),
            ref_day_cnt,
            our_day_cost,
            ref_day_cost,
            (our_day_cost - ref_day_cost).abs()
        );
        println!(
            "[reconcile] by session: rows {} vs {} | cost {:.6} vs {:.6} | diff {:.8}",
            sess_rows.len(),
            ref_sess_cnt,
            our_sess_cost,
            ref_sess_cost,
            (our_sess_cost - ref_sess_cost).abs()
        );
        assert_eq!(day_rows.len() as i64, ref_day_cnt);
        assert_eq!(sess_rows.len() as i64, ref_sess_cnt);
        assert!((our_day_cost - ref_day_cost).abs() <= 0.01, "by day 对账误差 >0.01 USD");
        assert!(
            (our_sess_cost - ref_sess_cost).abs() <= 0.01,
            "by session 对账误差 >0.01 USD"
        );
        println!("[reconcile] 对账通过（误差 ≤0.01 USD）");
    }
}
