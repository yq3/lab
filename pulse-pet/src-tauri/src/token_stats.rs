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

use std::collections::HashMap;
use std::fmt;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use rusqlite::{Connection, OpenFlags};
use serde::{Deserialize, Serialize};

use crate::transcript::{self, TranscriptCache};

/// agent 常量（v2 M5，V2-DESIGN §5.3）：opencode 恒单值；CC 行由 transcript 解析注入。
pub const AGENT_OPENCODE: &str = "opencode";
pub const AGENT_CLAUDE_CODE: &str = "claude-code";

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
/// M3（V2-DESIGN §3.2）：+model_id（仅按 id 归并）/project_name（basename）/
/// title（by-session 独有，聚合行 None）。
/// M5（V2-DESIGN §5.3）：+agent（opencode 恒 `"opencode"`；CC 行 `"claude-code"`）。
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
    /// `json_extract(model,'$.id')`；NULL/JSON 损坏 → None（前端「未知模型」合并）。
    pub model_id: Option<String>,
    /// `basename(project.worktree)`；`/`（global）或 JOIN 未命中 → None（前端回退标签）。
    pub project_name: Option<String>,
    /// 会话标题（by-session 独有；day/week/range 聚合行 None）。
    pub title: Option<String>,
    /// v2 M5：来源 agent（`opencode` / `claude-code`）。
    pub agent: String,
}

/// 今日 token 聚合（M3 §3.2 `token_stats_today`；三层快捷查看共享单一数据源）。
/// reasoning 不计（SCOPE D 裁定，与 GLM 官方展示同口径）。
///
/// v2 M6（V2-DESIGN §6.2）：+`by_agent`——今日 agent 分布行（落 TodayStats
/// 结构内、随 `{today, degraded}` 包装返回，P3-3）；`total` 口径 = 今日总量
/// 同口径（in+out+cache_read、不含 reasoning、mock 过滤）——三层数值交叉
/// 断言由此成立；有数据的 agent 按 total 降序，零数据 agent 省略（空 vec）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TodayStats {
    pub input: i64,
    pub output: i64,
    pub cache_read: i64,
    pub cost: f64,
    /// v2 M6：agent 分布行（单 agent 一行；`#[serde(default)]` 兼容旧序列化
    /// 数据的单测夹具）。
    #[serde(default)]
    pub by_agent: Vec<AgentTodayTotal>,
}

/// v2 M6：`by_agent` 的行类型（agent 归属 + 今日同口径总量）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AgentTodayTotal {
    pub agent: String,
    pub total: i64,
}

/// M5 双源查询返回体（C1/N-4 承载定案）：
/// `degraded=Some` 仅在 opencode 源报错而 CC 源有数据时出现（原始错误
/// "code: message" 供前端 title 提示）；CC 缺席时 rows 与 M3 原样一致、
/// degraded=None（单源场景行为不变）。
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct QueryResponse {
    pub rows: Vec<TokenRow>,
    pub degraded: Option<String>,
}

/// M5 今日聚合返回体（同上语义）。
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct TodayResponse {
    pub today: TodayStats,
    pub degraded: Option<String>,
}

/// S4 裁定（2026-08-23）：`providerID='mock'` 的探测行（probe-model，token 全 0）
/// 在**全部查询**中过滤——统计零影响、模型列表更干净、口径统一防漂移。
///
/// 注（R1 实测修正）：SQLite `json_extract` 对**非 JSON 文本**抛 "malformed JSON"
/// 错（仅路径缺失才返回 NULL）——设计 R1「天然降级」需 `json_valid` 守卫：
/// model 为 NULL / 损坏 JSON 时 providerID 视为空串 ≠ 'mock'（保留行）。
pub const MOCK_FILTER_SQL: &str =
    "COALESCE(CASE WHEN json_valid(model) THEN json_extract(model,'$.providerID') END,'') <> 'mock'";

/// `model -> $.id`（仅按 id 归并，S2）；NULL / 损坏 JSON → NULL（「未知模型」合并）。
/// 同 MOCK_FILTER_SQL 的 json_valid 守卫理由。
pub const MODEL_ID_SQL: &str =
    "CASE WHEN json_valid(model) THEN json_extract(model,'$.id') END";

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
/// M3：+`model`（model_id 提取）/`title`（首列标题，S1/S5）。
pub const SESSION_REQUIRED_COLUMNS: &[&str] = &[
    "id",
    "project_id",
    "model",
    "title",
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

/// by-session 列集（M3 §3.2：+model_id/title +LEFT JOIN project 取 worktree；
/// basename 在 Rust 侧切——`Path::file_name` 跨平台稳妥）。
fn session_columns() -> &'static str {
    "s.id AS session_id, s.project_id, s.cost, s.tokens_input, s.tokens_output, \
     s.tokens_reasoning, s.tokens_cache_read, s.tokens_cache_write, \
     s.time_created, s.time_updated"
}

/// worktree → basename（`/`（global）或 NULL → None；`Path::file_name` 对
/// `/`、`/tmp/` 等无文件名成分的路径天然返回 None）。
fn basename_of(worktree: Option<String>) -> Option<String> {
    let w = worktree?;
    Path::new(&w)
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
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
        model_id: row.get("model_id")?,
        project_name: basename_of(row.get("project_worktree")?),
        title: row.get("title")?,
        agent: row.get("agent")?,
    })
}

/// by session（原样语义，`WHERE time_updated` 范围 + `ORDER BY` 倒序；
/// M3：+model_id/title 列 + LEFT JOIN project + mock 过滤；
/// M5：+agent 列（opencode 恒单值）。
pub fn query_by_session(
    conn: &Connection,
    from_ms: i64,
    to_ms: i64,
) -> Result<Vec<TokenRow>, StatsError> {
    let sql = format!(
        "SELECT {cols}, {model_id} AS model_id, s.title, \
                p.worktree AS project_worktree, '{agent}' AS agent \
         FROM session s LEFT JOIN project p ON s.project_id = p.id \
         WHERE s.time_updated >= ?1 AND s.time_updated <= ?2 AND {mock} \
         ORDER BY s.time_updated DESC",
        cols = session_columns(),
        agent = AGENT_OPENCODE,
        model_id = MODEL_ID_SQL,
        mock = MOCK_FILTER_SQL,
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

/// by range（任意跨度的按模型聚合，day 为 None；from/to 由前端传；
/// M3 §3.2：GROUP BY model_id（口径与 day/week 统一），project_id 移除）。
pub fn query_by_range(
    conn: &Connection,
    from_ms: i64,
    to_ms: i64,
) -> Result<Vec<TokenRow>, StatsError> {
    query_grouped(conn, from_ms, to_ms, "NULL")
}

fn query_grouped(
    conn: &Connection,
    from_ms: i64,
    to_ms: i64,
    day_expr: &str,
) -> Result<Vec<TokenRow>, StatsError> {
    // M5：GROUP BY day, agent, model_id（agent 恒单值，列+分组保持形状统一，
    // 与 CC 侧内存聚合 day × agent × model_id 对齐——V2-DESIGN §5.3）
    let sql = format!(
        "SELECT {day_expr} AS day, {model_id} AS model_id, '{agent}' AS agent, \
                SUM(cost) AS cost, \
                SUM(tokens_input) AS tokens_input, SUM(tokens_output) AS tokens_output, \
                SUM(tokens_reasoning) AS tokens_reasoning, \
                SUM(tokens_cache_read) AS tokens_cache_read, \
                SUM(tokens_cache_write) AS tokens_cache_write \
         FROM session WHERE time_updated >= ?1 AND time_updated <= ?2 AND {mock} \
         GROUP BY day, agent, model_id ORDER BY day DESC",
        agent = AGENT_OPENCODE,
        model_id = MODEL_ID_SQL,
        mock = MOCK_FILTER_SQL,
    );
    let mut stmt = conn
        .prepare(&sql)
        .map_err(|e| StatsError::new(ERR_QUERY, format!("prepare 失败：{e}")))?;
    let rows = stmt
        .query_map([from_ms, to_ms], |row| {
            Ok(TokenRow {
                session_id: None,
                project_id: None, // 聚合行移除 project_id（M3：饼图已砍，按模型分组）
                day: row.get("day")?,
                cost: row.get("cost")?,
                tokens_input: row.get("tokens_input")?,
                tokens_output: row.get("tokens_output")?,
                tokens_reasoning: row.get("tokens_reasoning")?,
                tokens_cache_read: row.get("tokens_cache_read")?,
                tokens_cache_write: row.get("tokens_cache_write")?,
                time_created: None,
                time_updated: None,
                model_id: row.get("model_id")?,
                project_name: None,
                title: None,
                agent: row.get("agent")?,
            })
        })
        .map_err(|e| StatsError::new(ERR_QUERY, format!("查询失败：{e}")))?;
    let mut out = Vec::new();
    for r in rows {
        out.push(r.map_err(|e| StatsError::new(ERR_QUERY, format!("读取失败：{e}")))?);
    }
    Ok(out)
}

/// 当前会话行（TC-TK-12：无记录返回 `Ok(None)`，由调用方决定不出气泡；
/// M3：+JOIN/model_id/title 列 + mock 过滤——仅加过滤，无 JOIN 外的分组变化）。
pub fn query_current_session(
    conn: &Connection,
    session_id: &str,
) -> Result<Option<TokenRow>, StatsError> {
    let sql = format!(
        "SELECT {cols}, {model_id} AS model_id, s.title, \
                p.worktree AS project_worktree, '{agent}' AS agent \
         FROM session s LEFT JOIN project p ON s.project_id = p.id \
         WHERE s.id = ?1 AND {mock}",
        cols = session_columns(),
        agent = AGENT_OPENCODE,
        model_id = MODEL_ID_SQL,
        mock = MOCK_FILTER_SQL,
    );
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
    let conn = open_checked(data_dir)?;
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

/// 探测 → 只读连接 → schema 白名单（M3 抽出供 query_stats/today/current 复用；
/// 数据库不存在时区分 no-database / legacy-storage）。
pub fn open_checked(data_dir: &Path) -> Result<Connection, StatsError> {
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
    Ok(conn)
}

/// 当前会话查询编排（命令层用）。
pub fn current_session(
    data_dir: &Path,
    session_id: &str,
) -> Result<Option<TokenRow>, StatsError> {
    let conn = open_checked(data_dir)?;
    query_current_session(&conn, session_id)
}

// ---------------------------------------------------------------------------
// M3：今日聚合（V2-DESIGN §3.2 `token_stats_today`；三层快捷查看单一数据源）
// ---------------------------------------------------------------------------

/// 本地今天 0 点（chrono::Local；注入 now_ms 供边界单测）。
pub fn local_today_start_ms(now_ms: i64) -> i64 {
    use chrono::TimeZone;
    let Some(local_now) = chrono::Local.timestamp_millis_opt(now_ms).single() else {
        return now_ms; // 防御（不发生）：保持窗口非空
    };
    let midnight = local_now
        .date_naive()
        .and_hms_opt(0, 0, 0)
        .unwrap_or(local_now.naive_local());
    chrono::Local
        .from_local_datetime(&midnight)
        .single()
        .map(|d| d.timestamp_millis())
        .unwrap_or(now_ms) // DST 空缺等极端边界：退化为 now（窗口最小化，不崩）
}

/// 今日聚合核心（已开连接上执行；含 mock 过滤）。
/// v2 M6（§6.2）：`by_agent` 填 opencode 单行（total>0 才有行；CC 行由
/// `today_stats_dual` 合并时追加——opencode 源在 SQL 里 agent 恒单值）。
pub fn query_today_on(
    conn: &Connection,
    from_ms: i64,
    to_ms: i64,
) -> Result<TodayStats, StatsError> {
    let sql = format!(
        "SELECT IFNULL(SUM(tokens_input),0), IFNULL(SUM(tokens_output),0), \
                IFNULL(SUM(tokens_cache_read),0), IFNULL(SUM(cost),0.0) \
         FROM session WHERE time_updated >= ?1 AND time_updated <= ?2 AND {mock}",
        mock = MOCK_FILTER_SQL,
    );
    conn.query_row(&sql, [from_ms, to_ms], |r| {
        Ok(TodayStats {
            input: r.get(0)?,
            output: r.get(1)?,
            cache_read: r.get(2)?,
            cost: r.get(3)?,
            by_agent: Vec::new(),
        })
    })
    .map_err(|e| StatsError::new(ERR_QUERY, format!("查询失败：{e}")))
    .map(|mut t| {
        t.by_agent = agent_today_rows(AGENT_OPENCODE, &t);
        t
    })
}

/// by_agent 行构造（v2 M6 §6.2）：total = in+out+cache_read（今日总量同口径），
/// **>0 才有行**（零数据 agent 省略——「单项不显示」的数据面基础）。
fn agent_today_rows(agent: &str, t: &TodayStats) -> Vec<AgentTodayTotal> {
    let total = t.input + t.output + t.cache_read;
    if total > 0 {
        vec![AgentTodayTotal {
            agent: agent.to_string(),
            total,
        }]
    } else {
        Vec::new()
    }
}

/// 双源 by_agent 合并（v2 M6 §6.2）：opencode 行 + CC 行拼接后按 total 降序
///（平局按 agent 名稳定序）。
fn merge_by_agent(
    mut rows: Vec<AgentTodayTotal>,
    extra: Vec<AgentTodayTotal>,
) -> Vec<AgentTodayTotal> {
    rows.extend(extra);
    rows.sort_by(|a, b| b.total.cmp(&a.total).then(a.agent.cmp(&b.agent)));
    rows
}

/// 今日聚合编排：from = 本地今天 0 点、to = now；全套错误处理原样透传
/// （no-database / legacy-storage / schema-mismatch）。
pub fn today_stats(data_dir: &Path, now_ms: i64) -> Result<TodayStats, StatsError> {
    let conn = open_checked(data_dir)?;
    query_today_on(&conn, local_today_start_ms(now_ms), now_ms)
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

// §十二 F1（2026-08-28）：format_cost_usd 随气泡 cost 段去除清退——
// 气泡侧唯一生产消费方（format_session_report）已改单总量；面板 cost
// 展示走前端自有 formatCost（token-stats.ts），Rust 侧不再需要。

/// 气泡文案（白名单模板：仅由数字格式化生成，不含任何原始 prompt/路径/URL；
/// 长度恒 <140、单行，前端 `sanitizeBubbleText` 再兜底一次）。
/// §十二 F1（2026-08-28）：**单总量口径**——total = in + out + cache_read
/// （与今日段/面板 KPI sumRows 同口径，reasoning 不计）；原 input/output/cost
/// 明细与 CC 无 cost 双模板收敛为统一总量模板（M8 i18n 随全局语言位）。
pub fn format_session_report(row: &TokenRow) -> String {
    let total = row.tokens_input + row.tokens_output + row.tokens_cache_read;
    crate::i18n::current().token_report(&format_tokens_k(total))
}

/// 是否出气泡：有真实用量（token 或 cost > 0）且 `time_updated` 新鲜（TC-TK-11/12）。
/// 审查 P3-7 钉住口径差（有意为之，勿"统一"）：**判定口径宽于显示口径**——
/// cost/reasoning/cache_write 任一非零即触发气泡，但 F1 后显示总量只含
/// in+out+cache_read，故可能出现「气泡 token 0」（如纯 cache_write 会话）；
/// 显示为 0 仍出气泡是为了让用户感知"这次会话有活动"（TC-TK-12 只静默全零）。
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

/// v2 M3 §3.2：idle 汇报（本期文案）+ 今日累计总量——**同连接一次查询**
/// （本期行查完后，同一只读连接上顺带 SUM 当日聚合；取代 v1 `build_idle_report`
/// 的单行查询路径，本期数字逻辑不变：should_report / format_session_report 均复用）。
///
/// 返回 `(本期文案, 今日总量)`；今日总量 = in + out + cache_read（reasoning
/// 不计）；今日聚合失败（如跨午夜边界竞态、SQL 报错）→ `None`（静默省略
/// 追加段，本期文案照常——拼接与 i18n 渲染在 lib.rs idle hook，TC-M3-09-3）。
pub fn build_idle_report_with_today(
    data_dir: &Path,
    session_id: &str,
    now_ms: i64,
    max_lag_ms: i64,
) -> Option<(String, Option<i64>)> {
    let conn = open_checked(data_dir).ok()?;
    let row = query_current_session(&conn, session_id).ok()??;
    if !should_report(&row, now_ms, max_lag_ms) {
        return None;
    }
    let text = format_session_report(&row);
    let today = query_today_on(&conn, local_today_start_ms(now_ms), now_ms)
        .ok()
        .map(|t| t.input + t.output + t.cache_read);
    Some((text, today))
}

/// 气泡新鲜度阈值（默认 60s，`PULSEPET_TOKEN_REPORT_MAX_LAG_MS` 可配）。
pub fn report_max_lag_ms() -> i64 {
    std::env::var("PULSEPET_TOKEN_REPORT_MAX_LAG_MS")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(60_000)
}

// ---------------------------------------------------------------------------
// M5：双源查询（V2-DESIGN §5.3/§5.4，TC-M5-03/05/09）
// ---------------------------------------------------------------------------

/// CC 会话行 → TokenRow（agent=`claude-code`、cost 恒 0.0——S4 口径）。
pub fn cc_to_token_row(r: &transcript::CcSessionRow) -> TokenRow {
    TokenRow {
        session_id: Some(r.session_id.clone()),
        project_id: None,
        day: None,
        cost: r.cost,
        tokens_input: r.tokens_input,
        tokens_output: r.tokens_output,
        tokens_reasoning: r.tokens_reasoning,
        tokens_cache_read: r.tokens_cache_read,
        tokens_cache_write: r.tokens_cache_write,
        time_created: r.time_created,
        time_updated: r.time_updated,
        model_id: r.model_id.clone(),
        project_name: r.project_name.clone(),
        title: Some(r.title.clone()),
        agent: AGENT_CLAUDE_CODE.to_string(),
    }
}

/// CC 行窗口过滤 + 按 group_by 聚合（Rust 内存侧）：
/// - session：完整行（时间倒序，与 opencode 统一排序在调用方）；
/// - day/week：按 `day × agent × model_id` 聚合（本地日/周标签 = transcript
///   纯函数，与 SQLite 'localtime' 同口径——S5/P2-4）；
/// - range：按 `agent × model_id` 聚合（无 day 维，P3-6）。
fn cc_group_rows(rows: &[TokenRow], group_by: &str, from_ms: i64, to_ms: i64) -> Vec<TokenRow> {
    let in_win: Vec<&TokenRow> = rows
        .iter()
        .filter(|r| r.time_updated.is_some_and(|t| t >= from_ms && t <= to_ms))
        .collect();
    match group_by {
        "session" => {
            let mut v: Vec<TokenRow> = in_win.into_iter().cloned().collect();
            v.sort_by(|a, b| b.time_updated.cmp(&a.time_updated));
            v
        }
        "day" | "week" => {
            let mut map: HashMap<(Option<String>, Option<String>), (i64, i64, i64, i64, i64, f64)> =
                HashMap::new();
            for r in in_win {
                let Some(t) = r.time_updated else { continue };
                let label = if group_by == "day" {
                    transcript::local_day_label(t)
                } else {
                    transcript::sqlite_week_label(t)
                };
                let e = map.entry((label, r.model_id.clone())).or_insert((0, 0, 0, 0, 0, 0.0));
                e.0 += r.tokens_input;
                e.1 += r.tokens_output;
                e.2 += r.tokens_reasoning;
                e.3 += r.tokens_cache_read;
                e.4 += r.tokens_cache_write;
                e.5 += r.cost;
            }
            let mut out: Vec<TokenRow> = map
                .into_iter()
                .map(|((day, model), (i, o, rs, cr, cw, cost))| TokenRow {
                    session_id: None,
                    project_id: None,
                    day,
                    cost,
                    tokens_input: i,
                    tokens_output: o,
                    tokens_reasoning: rs,
                    tokens_cache_read: cr,
                    tokens_cache_write: cw,
                    time_created: None,
                    time_updated: None,
                    model_id: model,
                    project_name: None,
                    title: None,
                    agent: AGENT_CLAUDE_CODE.to_string(),
                })
                .collect();
            out.sort_by(|a, b| b.day.cmp(&a.day)); // day DESC 与 opencode 同序
            out
        }
        _ => {
            // range：agent × model_id
            let mut map: HashMap<Option<String>, (i64, i64, i64, i64, i64, f64)> = HashMap::new();
            for r in in_win {
                let e = map.entry(r.model_id.clone()).or_insert((0, 0, 0, 0, 0, 0.0));
                e.0 += r.tokens_input;
                e.1 += r.tokens_output;
                e.2 += r.tokens_reasoning;
                e.3 += r.tokens_cache_read;
                e.4 += r.tokens_cache_write;
                e.5 += r.cost;
            }
            let mut out: Vec<TokenRow> = map
                .into_iter()
                .map(|(model, (i, o, rs, cr, cw, cost))| TokenRow {
                    session_id: None,
                    project_id: None,
                    day: None,
                    cost,
                    tokens_input: i,
                    tokens_output: o,
                    tokens_reasoning: rs,
                    tokens_cache_read: cr,
                    tokens_cache_write: cw,
                    time_created: None,
                    time_updated: None,
                    model_id: model,
                    project_name: None,
                    title: None,
                    agent: AGENT_CLAUDE_CODE.to_string(),
                })
                .collect();
            out.sort_by(|a, b| a.model_id.cmp(&b.model_id));
            out
        }
    }
}

/// 双源查询编排（C1/N-4 容错）：
/// - opencode 正常 → 双源合并（session 维时间倒序统一排序；day/week/range 两源
///   concat）+ degraded=None；
/// - opencode 报错 × CC 有数据 → 降级返回 CC-only + degraded=Some（部分源错误
///   不整体遮蔽）；
/// - 双源全缺（opencode 错 × CC 无数据）→ 既有错误路径透传（M3「无库→—」语义
///   保留给全缺态）；
/// - CC 缺席 → rows 与 M3 单测钉住的原样一致 + degraded=None（单源场景行为不变）。
pub fn query_stats_dual(
    data_dir: &Path,
    cc_dir: &Path,
    cache: &Arc<Mutex<TranscriptCache>>,
    from_ms: i64,
    to_ms: i64,
    group_by: &str,
) -> Result<QueryResponse, StatsError> {
    if !matches!(group_by, "session" | "day" | "week" | "range") {
        return Err(StatsError::new(
            ERR_QUERY,
            format!("invalid group_by: {group_by}（应为 session/day/week/range）"),
        ));
    }
    // 方案 α（task-pulsepet-v2-polish #11）：锁内只做轻量判定与写回，I/O 与
    // 解析（增量：append 只读尾部）在锁外——不再于 Mutex 持有期全量解析。
    let cc_rows_all = transcript::refresh_unlocked(cc_dir, cache);
    let cc_has_data = !cc_rows_all.is_empty();
    let cc_tokens: Vec<TokenRow> = cc_rows_all.iter().map(cc_to_token_row).collect();
    let cc_grouped = cc_group_rows(&cc_tokens, group_by, from_ms, to_ms);

    match query_stats(data_dir, from_ms, to_ms, group_by) {
        Ok(mut rows) => {
            rows.extend(cc_grouped);
            if group_by == "session" {
                // 双源统一时间倒序（TC-M5-03-5）
                rows.sort_by(|a, b| b.time_updated.cmp(&a.time_updated));
            }
            Ok(QueryResponse {
                rows,
                degraded: None,
            })
        }
        Err(e) => {
            if cc_has_data {
                Ok(QueryResponse {
                    rows: cc_grouped,
                    degraded: Some(e.to_string()),
                })
            } else {
                Err(e)
            }
        }
    }
}

/// 今日双源聚合（M3 三层快捷查看自动覆盖 CC，TC-M5-03-6）：
/// opencode SQL 当日聚合 + CC 缓存当日过滤求和；容错语义同 query_stats_dual。
pub fn today_stats_dual(
    data_dir: &Path,
    cc_dir: &Path,
    cache: &Arc<Mutex<TranscriptCache>>,
    now_ms: i64,
) -> Result<TodayResponse, StatsError> {
    let from = local_today_start_ms(now_ms);
    // 方案 α：锁外增量刷新（同 query_stats_dual）
    let cc_rows_all = transcript::refresh_unlocked(cc_dir, cache);
    let cc_has_data = !cc_rows_all.is_empty();
    let mut cc_today = TodayStats {
        input: 0,
        output: 0,
        cache_read: 0,
        cost: 0.0,
        by_agent: Vec::new(),
    };
    for r in cc_rows_all.iter() {
        if let Some(t) = r.time_updated {
            if t >= from && t <= now_ms {
                cc_today.input += r.tokens_input;
                cc_today.output += r.tokens_output;
                cc_today.cache_read += r.tokens_cache_read;
                // cost 恒 0（S4）
            }
        }
    }
    // v2 M6（§6.2）：CC 分布行（今日同口径；>0 才有行）
    let cc_by_agent = agent_today_rows(AGENT_CLAUDE_CODE, &cc_today);
    match today_stats(data_dir, now_ms) {
        Ok(mut t) => {
            t.input += cc_today.input;
            t.output += cc_today.output;
            t.cache_read += cc_today.cache_read;
            // v2 M6：by_agent = opencode 行 + CC 行，按 total 降序（query_today_on
            // 已填 opencode 行；degraded 场景下同理仅 CC 行）
            t.by_agent = merge_by_agent(std::mem::take(&mut t.by_agent), cc_by_agent);
            Ok(TodayResponse {
                today: t,
                degraded: None,
            })
        }
        Err(e) => {
            if cc_has_data {
                cc_today.by_agent = cc_by_agent;
                Ok(TodayResponse {
                    today: cc_today,
                    degraded: Some(e.to_string()),
                })
            } else {
                Err(e)
            }
        }
    }
}

/// M5 CC 会话汇报（V2-DESIGN §5.4，TC-M5-05）：
/// - 经 TranscriptCache sessionId 索引定位文件（缓存缺失由 find_session 内
///   refresh 补建——idle 先于查询；方案 α：定位/校验锁内轻量，I/O 与解析锁外）；
/// - 新鲜度护栏：**last_assistant_ts** 距 now < max_lag（N-1 专用口径，对齐
///   opencode「最后 message 写入时间」语义）；
/// - 五维有非零用量才出气泡（全零静默，TC-TK-12 口径）；
/// - 文案 = 单总量模板（§十二 F1；原 S4「CC 无 cost 段」双模板已收敛）；
///   今日段 = today_stats_dual 双源合计（失败 → None 静默省略，同 opencode）。
pub fn build_cc_idle_report(
    cache: &Arc<Mutex<TranscriptCache>>,
    data_dir: &Path,
    cc_dir: &Path,
    session_id: &str,
    now_ms: i64,
    max_lag_ms: i64,
) -> Option<(String, Option<i64>)> {
    let row = transcript::find_session_unlocked(cc_dir, cache, session_id)?;
    let fresh = row
        .last_assistant_ts
        .is_some_and(|t| (now_ms - t).abs() <= max_lag_ms);
    if !fresh {
        return None;
    }
    let has_usage = row.tokens_input > 0
        || row.tokens_output > 0
        || row.tokens_reasoning > 0
        || row.tokens_cache_read > 0
        || row.tokens_cache_write > 0;
    if !has_usage {
        return None;
    }
    // §十二 F1：单总量口径（与 opencode 同模板；in + out + cache_read，
    // reasoning 不计）——原 CC 无 cost 双模板（S4）随统一收敛退役
    let total = row.tokens_input + row.tokens_output + row.tokens_cache_read;
    let text = crate::i18n::current().token_report(&format_tokens_k(total));
    let today = today_stats_dual(data_dir, cc_dir, cache, now_ms)
        .ok()
        .map(|t| t.today.input + t.today.output + t.today.cache_read);
    Some((text, today))
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
/// M5：双源化（opencode SQL + CC transcript 缓存）→ 返回体 `{rows, degraded}`
/// （C1/N-4）；async fn + spawn_blocking（扫描/解析与 SQL 均不承主线程，
/// IPC 契约不变——同命令名同参数）。
#[tauri::command]
pub async fn token_stats_query(
    from_ms: i64,
    to_ms: i64,
    group_by: String,
    cache: tauri::State<'_, Arc<Mutex<TranscriptCache>>>,
) -> Result<QueryResponse, String> {
    let data_dir = opencode_data_dir();
    let cc_dir = transcript::cc_projects_dir();
    let cache = cache.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        query_stats_dual(&data_dir, &cc_dir, &cache, from_ms, to_ms, &group_by)
    })
    .await
    .map_err(|e| format!("join: {e}"))?
    .map_err(|e| e.to_string())
}

/// 当前会话行（TC-TK-10/12）。
#[tauri::command]
pub fn token_stats_current_session(session_id: String) -> Result<Option<TokenRow>, String> {
    current_session(&opencode_data_dir(), &session_id).map_err(|e| e.to_string())
}

/// 今日 token 聚合（M3 §3.2；悬停卡/右键菜单/面板今日 preset 三层共享）。
/// M5：双源合计（opencode SQL 当日聚合 + CC 缓存当日过滤求和）→ 返回体
/// `{today, degraded}`；async fn + spawn_blocking（沿 M1 §1.5 线程纪律）；
/// 错误序列化 "code: message"（双源全缺时 no-database/legacy-storage/
/// schema-mismatch 原样透传）。
#[tauri::command]
pub async fn token_stats_today(
    cache: tauri::State<'_, Arc<Mutex<TranscriptCache>>>,
) -> Result<TodayResponse, String> {
    let data_dir = opencode_data_dir();
    let cc_dir = transcript::cc_projects_dir();
    let cache = cache.inner().clone();
    tauri::async_runtime::spawn_blocking(move || today_stats_dual(&data_dir, &cc_dir, &cache, now_ms()))
        .await
        .map_err(|e| format!("join: {e}"))?
        .map_err(|e| e.to_string())
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
    use crate::plog;
    use std::time::{SystemTime, UNIX_EPOCH};

    /// 与真实 opencode.db 一致的 session 表建表语句（白名单列 + 少量真实存在的
    /// 其它列，模拟 opencode 1.18.x schema；M3 起 model 列入白名单，S1/S2）。
    const CREATE_SESSION: &str = "\
        CREATE TABLE session (\
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, directory TEXT NOT NULL, \
            title TEXT NOT NULL, model TEXT, cost REAL NOT NULL DEFAULT 0, \
            tokens_input INTEGER NOT NULL DEFAULT 0, \
            tokens_output INTEGER NOT NULL DEFAULT 0, \
            tokens_reasoning INTEGER NOT NULL DEFAULT 0, \
            tokens_cache_read INTEGER NOT NULL DEFAULT 0, \
            tokens_cache_write INTEGER NOT NULL DEFAULT 0, \
            time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL)";

    /// project 表（S1：路径列名 = worktree；global 行 id='global'、worktree='/'）。
    const CREATE_PROJECT: &str = "CREATE TABLE project (id TEXT PRIMARY KEY, worktree TEXT NOT NULL)";

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

    /// 建一个临时 opencode 数据目录 + 指定 schema 的 opencode.db（含 project 表）。
    fn make_db(tag: &str, create_sql: &str) -> PathBuf {
        let dir = temp_dir(tag);
        let db = dir.join("opencode.db");
        let conn = Connection::open(&db).unwrap();
        conn.execute_batch(create_sql).unwrap();
        conn.execute_batch(CREATE_PROJECT).unwrap();
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
        insert_session_model(dir, id, project, cost, tokens, created, updated, None, None);
    }

    /// M3 扩展插数：可带 model JSON / title 覆盖（默认 title='t'）。
    #[allow(clippy::too_many_arguments)]
    fn insert_session_model(
        dir: &Path,
        id: &str,
        project: &str,
        cost: f64,
        tokens: (i64, i64, i64, i64, i64),
        created: i64,
        updated: i64,
        model: Option<&str>,
        title: Option<&str>,
    ) {
        let conn = open_readonly_unchecked(dir);
        conn.execute(
            "INSERT INTO session (id, project_id, directory, title, model, cost, tokens_input, \
             tokens_output, tokens_reasoning, tokens_cache_read, tokens_cache_write, \
             time_created, time_updated) VALUES (?1,?2,'/tmp',?3,?4,?5,?6,?7,?8,?9,?10,?11,?12)",
            rusqlite::params![
                id,
                project,
                title.unwrap_or("t"),
                model,
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

    /// 插一行 project（id → worktree）。
    fn insert_project(dir: &Path, id: &str, worktree: &str) {
        let conn = open_readonly_unchecked(dir);
        conn.execute(
            "INSERT INTO project (id, worktree) VALUES (?1, ?2)",
            [id, worktree],
        )
        .unwrap();
    }

    /// model JSON（{id, providerID}）。
    fn model_json(id: &str, provider: &str) -> String {
        format!(r#"{{"id":"{id}","providerID":"{provider}","variant":null}}"#)
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
    fn query_by_day_groups_by_local_day_and_model() {
        let dir = make_db("day", CREATE_SESSION);
        // 同一天两个 session 同模型 → SUM 聚合；另一天另一模型 → 分组
        // （M3 §3.2：GROUP BY day, model_id——取代 v1 的 day, project_id）
        let day0 = chrono_local_midnight(2026, 8, 16);
        insert_session_model(&dir, "s1", "p1", 0.10, (100, 20, 0, 0, 0), day0, day0 + ms(3600),
            Some(&model_json("glm-5.3", "zhipuai")), None);
        insert_session_model(&dir, "s2", "p1", 0.20, (200, 30, 0, 0, 0), day0, day0 + ms(7200),
            Some(&model_json("glm-5.3", "zhipuai")), None);
        let day1 = chrono_local_midnight(2026, 8, 15);
        insert_session_model(&dir, "s3", "p2", 0.40, (400, 60, 0, 0, 0), day1, day1 + ms(3600),
            Some(&model_json("kimi-k2", "moonshot")), None);
        let conn = open_readonly(&dir.join("opencode.db")).unwrap();
        let rows = query_by_day(&conn, 0, day0 + ms(86_400)).unwrap();
        assert_eq!(rows.len(), 2, "两个 (day, model) 分组");
        // ORDER BY day DESC：首行是 2026-08-16 的 glm-5.3 聚合
        let r = &rows[0];
        assert_eq!(r.day.as_deref(), Some("2026-08-16"));
        assert_eq!(r.model_id.as_deref(), Some("glm-5.3"));
        assert!((r.cost - 0.30).abs() < 1e-9); // 浮点 SUM 用近似比较
        assert_eq!(r.tokens_input, 300);
        assert_eq!(r.tokens_output, 50);
        assert_eq!(rows[1].day.as_deref(), Some("2026-08-15"));
        assert_eq!(rows[1].model_id.as_deref(), Some("kimi-k2"));
    }

    #[test]
    fn query_by_week_labels_and_aggregates() {
        let dir = make_db("week", CREATE_SESSION);
        let d = chrono_local_midnight(2026, 8, 11); // 周一（2026-08-10 为 ISO 周一）
        insert_session_model(&dir, "s1", "p1", 0.1, (10, 1, 0, 0, 0), d, d + ms(3600),
            Some(&model_json("glm-5.3", "zhipuai")), None);
        let d2 = chrono_local_midnight(2026, 8, 13);
        insert_session_model(&dir, "s2", "p1", 0.2, (20, 2, 0, 0, 0), d2, d2 + ms(3600),
            Some(&model_json("glm-5.3", "zhipuai")), None);
        let conn = open_readonly(&dir.join("opencode.db")).unwrap();
        let rows = query_by_week(&conn, 0, d2 + ms(86_400)).unwrap();
        assert_eq!(rows.len(), 1, "同一周同模型 → 单行聚合");
        assert_eq!(rows[0].day.as_deref(), Some("2026-W32"));
        assert!((rows[0].cost - 0.30).abs() < 1e-9);
        assert_eq!(rows[0].tokens_input, 30);
    }

    #[test]
    fn query_by_range_aggregates_per_model_without_day() {
        let dir = make_db("range", CREATE_SESSION);
        let d = chrono_local_midnight(2026, 8, 16);
        // p1 两行同模型 → 单组；p2 一行另一模型 → 另一组（M3：GROUP BY model_id）
        insert_session_model(&dir, "s1", "p1", 0.1, (10, 1, 0, 0, 0), d, d + ms(1),
            Some(&model_json("glm-5.3", "zhipuai")), None);
        insert_session_model(&dir, "s2", "p1", 0.2, (20, 2, 0, 0, 0), d, d + ms(2),
            Some(&model_json("glm-5.3", "zhipuai")), None);
        insert_session_model(&dir, "s3", "p2", 0.4, (40, 4, 0, 0, 0), d, d + ms(3),
            Some(&model_json("kimi-k2", "moonshot")), None);
        let conn = open_readonly(&dir.join("opencode.db")).unwrap();
        let mut rows = query_by_range(&conn, 0, d + ms(10)).unwrap();
        rows.sort_by(|a, b| a.model_id.cmp(&b.model_id));
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].model_id.as_deref(), Some("glm-5.3"));
        assert!((rows[0].cost - 0.30).abs() < 1e-9);
        assert_eq!(rows[0].day, None);
        assert_eq!(rows[0].session_id, None);
        assert_eq!(rows[0].project_id, None, "range 聚合行不含 project_id");
        assert_eq!(rows[1].model_id.as_deref(), Some("kimi-k2"));
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
        assert_eq!(format_tokens_k(59_173), "59.2k"); // §十二 F1：会话总量钉子
        // §十二 F1：format_cost_usd 断言随函数清退删除
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
            model_id: None,
            project_name: None,
            title: None,
            agent: AGENT_OPENCODE.into(),
        };
        let text = format_session_report(&row);
        // §十二 F1：单总量——total = 58263 + 910 + 0 = 59173 → "59.2k"
        assert_eq!(text, "本次会话消耗 token 59.2k");
        assert!(!text.contains('$'), "F1：cost 段去除");
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
            model_id: None,
            project_name: None,
            title: None,
            agent: AGENT_OPENCODE.into(),
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
        // v2 M3：v1 build_idle_report 场景由 with_today 全覆盖（陈旧/无记录分支
        // 在 m3_build_idle_report_with_today_silent_on_no_report；此处保留核心
        // e2e：新鲜 + 有用量 → 文案）
        let dir = make_db("report", CREATE_SESSION);
        let now = ms(1_000_000);
        insert_session(
            &dir,
            "ses_live",
            "p1",
            0.05,
            (58_263, 910, 0, 0, 0),
            now - ms(600),
            now - ms(2),
        );
        let (text, today) = build_idle_report_with_today(&dir, "ses_live", now, 60_000).unwrap();
        assert_eq!(text, "本次会话消耗 token 59.2k");
        assert_eq!(today, Some(58_263 + 910), "今日 = 本会话行（窗口内唯一）");
        // 数据库不存在 → None（静默，不崩）
        let nodir = temp_dir("report-nodb");
        assert_eq!(build_idle_report_with_today(&nodir, "ses_x", now, 60_000), None);
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

    /// 指定本地日期零点（chrono 语义——与 `local_today_start_ms` 同一时区口径；
    /// M3 测试用：SQLite 版是 UTC 零点，与 chrono 本地零点在非零时区相差时区偏移）。
    fn chrono_local_midnight(y: i32, m: u32, d: u32) -> i64 {
        use chrono::TimeZone;
        chrono::Local
            .with_ymd_and_hms(y, m, d, 0, 0, 0)
            .single()
            .map(|dt| dt.timestamp_millis())
            .unwrap_or(0)
    }

    // ---- M3：数据层字段扩展（V2-DESIGN §3.2，TC-M3-01） ----

    #[test]
    fn m3_by_session_row_has_model_id_title_project_name() {
        let dir = make_db("m3-sess", CREATE_SESSION);
        insert_project(&dir, "p1", "/Users/youqi/develop/lab");
        insert_project(&dir, "global", "/");
        let d = chrono_local_midnight(2026, 8, 25);
        // 普通行：model JSON → id；JOIN 命中 → basename(lab)；title 原样
        insert_session_model(
            &dir, "s1", "p1", 0.1, (10, 1, 0, 0, 0), d, d + ms(1),
            Some(&model_json("glm-5.3", "zhipuai")), Some("修个 bug"),
        );
        // global 行：worktree='/' → project_name None
        insert_session_model(
            &dir, "s2", "global", 0.0, (5, 0, 0, 0, 0), d, d + ms(2),
            Some(&model_json("deepseek-v4-flash@max", "deepseek")), None, // title 缺省 't'
        );
        // JOIN 未命中（无 project 行）→ project_name None；model NULL → None
        insert_session(&dir, "s3", "p-missing", 0.0, (7, 0, 0, 0, 0), d, d + ms(3));
        // JSON 损坏 → model_id None（json_extract 返回 NULL，天然降级不崩，R1）
        insert_session_model(
            &dir, "s4", "p1", 0.0, (8, 0, 0, 0, 0), d, d + ms(4),
            Some("not-json"), None,
        );

        let conn = open_readonly(&dir.join("opencode.db")).unwrap();
        let rows = query_by_session(&conn, 0, d + ms(10)).unwrap();
        let by_id = |k: &str| rows.iter().find(|r| r.session_id.as_deref() == Some(k)).unwrap();

        let s1 = by_id("s1");
        assert_eq!(s1.model_id.as_deref(), Some("glm-5.3"));
        assert_eq!(s1.project_name.as_deref(), Some("lab"));
        assert_eq!(s1.title.as_deref(), Some("修个 bug"));
        assert_eq!(s1.project_id.as_deref(), Some("p1")); // project_id 保留（前端 global 判定）

        // 带后缀 id 原样归并（S2 裁定）；global → project_name None
        let s2 = by_id("s2");
        assert_eq!(s2.model_id.as_deref(), Some("deepseek-v4-flash@max"));
        assert_eq!(s2.project_name, None, "worktree='/' → None（global 回退标签）");
        assert_eq!(s2.title.as_deref(), Some("t"));

        // 未命中 + model NULL → 双 None
        let s3 = by_id("s3");
        assert_eq!(s3.model_id, None);
        assert_eq!(s3.project_name, None, "JOIN 未命中 → None（unknown 回退标签）");

        // JSON 损坏 → model_id None
        assert_eq!(by_id("s4").model_id, None);
    }

    #[test]
    fn m3_grouped_rows_have_model_id_without_project_id() {
        let dir = make_db("m3-grouped", CREATE_SESSION);
        let d = chrono_local_midnight(2026, 8, 25);
        // 同日同模型两行 → 单 (day, model_id) 分组聚合；另一模型 → 另一分组
        insert_session_model(&dir, "s1", "p1", 0.10, (100, 20, 0, 30, 0), d, d + ms(3600),
            Some(&model_json("glm-5.3", "zhipuai")), None);
        insert_session_model(&dir, "s2", "p2", 0.20, (200, 30, 0, 40, 0), d, d + ms(7200),
            Some(&model_json("glm-5.3", "zhipuai")), None);
        insert_session_model(&dir, "s3", "p1", 0.40, (400, 60, 0, 50, 0), d, d + ms(8000),
            Some(&model_json("kimi-k2", "moonshot")), None);
        let conn = open_readonly(&dir.join("opencode.db")).unwrap();

        let mut rows = query_by_day(&conn, 0, d + ms(86_400)).unwrap();
        rows.sort_by(|a, b| a.model_id.cmp(&b.model_id));
        assert_eq!(rows.len(), 2, "GROUP BY day, model_id → 两行");
        for r in &rows {
            assert_eq!(r.project_id, None, "聚合行不含 project_id");
            assert_eq!(r.project_name, None);
            assert_eq!(r.title, None, "title 为 by-session 独有");
            assert_eq!(r.day.as_deref(), Some("2026-08-25"));
        }
        let glm = rows.iter().find(|r| r.model_id.as_deref() == Some("glm-5.3")).unwrap();
        assert_eq!(glm.tokens_input, 300);
        assert_eq!(glm.tokens_cache_read, 70);
        assert!((glm.cost - 0.30).abs() < 1e-9);
        let kimi = rows.iter().find(|r| r.model_id.as_deref() == Some("kimi-k2")).unwrap();
        assert_eq!(kimi.tokens_input, 400);

        // week 维同口径
        let rows = query_by_week(&conn, 0, d + ms(86_400)).unwrap();
        assert!(rows.iter().all(|r| r.project_id.is_none() && r.model_id.is_some()));

        // range 维：GROUP BY model_id（口径统一），project_id 移除
        let mut rows = query_by_range(&conn, 0, d + ms(86_400)).unwrap();
        rows.sort_by(|a, b| a.model_id.cmp(&b.model_id));
        assert_eq!(rows.len(), 2);
        for r in &rows {
            assert_eq!(r.project_id, None, "range 聚合同口径不含 project_id");
        }
    }

    #[test]
    fn m3_grouped_null_model_buckets_into_unknown_group() {
        // model NULL/损坏 → model_id NULL 自成一组（前端「未知模型」合并，S3 防御）
        let dir = make_db("m3-nullmodel", CREATE_SESSION);
        let d = chrono_local_midnight(2026, 8, 25);
        insert_session(&dir, "s1", "p1", 0.1, (10, 1, 0, 0, 0), d, d + ms(1));
        insert_session(&dir, "s2", "p1", 0.1, (20, 2, 0, 0, 0), d, d + ms(2));
        insert_session_model(&dir, "s3", "p1", 0.1, (30, 3, 0, 0, 0), d, d + ms(3),
            Some("broken"), None);
        let conn = open_readonly(&dir.join("opencode.db")).unwrap();
        let rows = query_by_day(&conn, 0, d + ms(10)).unwrap();
        assert_eq!(rows.len(), 1, "NULL model_id 单组聚合");
        assert_eq!(rows[0].model_id, None);
        assert_eq!(rows[0].tokens_input, 60);
    }

    #[test]
    fn m3_schema_whitelist_requires_model_and_title() {
        // 白名单 +model+title：缺任一 → schema-mismatch（TC-M3-01-4）
        let sql_no_title = "CREATE TABLE session (\
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, directory TEXT NOT NULL, \
            model TEXT, cost REAL NOT NULL DEFAULT 0, \
            tokens_input INTEGER NOT NULL DEFAULT 0, tokens_output INTEGER NOT NULL DEFAULT 0, \
            tokens_reasoning INTEGER NOT NULL DEFAULT 0, tokens_cache_read INTEGER NOT NULL DEFAULT 0, \
            tokens_cache_write INTEGER NOT NULL DEFAULT 0, time_created INTEGER NOT NULL, \
            time_updated INTEGER NOT NULL)";
        let dir = make_db("m3-schema", sql_no_title);
        let err = query_stats(&dir, 0, i64::MAX, "session").unwrap_err();
        assert_eq!(err.code, ERR_SCHEMA_MISMATCH);
        assert!(err.message.contains("title"), "缺列提示点名 title：{}", err.message);
    }

    // ---- M3：mock 过滤口径（S4 裁定，TC-M3-02） ----

    #[test]
    fn m3_mock_provider_rows_filtered_everywhere() {
        let dir = make_db("m3-mock", CREATE_SESSION);
        insert_project(&dir, "p1", "/tmp/proj");
        let d = chrono_local_midnight(2026, 8, 25);
        let mock = model_json("probe-model", "mock");
        insert_session_model(&dir, "s_mock", "p1", 0.0, (999, 999, 0, 999, 0), d, d + ms(1), Some(&mock), None);
        insert_session_model(&dir, "s_real", "p1", 0.1, (100, 20, 0, 30, 0), d, d + ms(2),
            Some(&model_json("glm-5.3", "zhipuai")), None);
        let conn = open_readonly(&dir.join("opencode.db")).unwrap();

        // by-session：mock 行不出现
        let rows = query_by_session(&conn, 0, d + ms(10)).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].session_id.as_deref(), Some("s_real"));

        // day/week/range：统计零影响
        for rows in [
            query_by_day(&conn, 0, d + ms(10)).unwrap(),
            query_by_week(&conn, 0, d + ms(10)).unwrap(),
            query_by_range(&conn, 0, d + ms(10)).unwrap(),
        ] {
            assert_eq!(rows.len(), 1);
            assert_eq!(rows[0].model_id.as_deref(), Some("glm-5.3"));
            assert_eq!(rows[0].tokens_input, 100);
        }

        // current_session：mock 会话查不到（Ok(None)，口径统一防漂移）
        assert!(query_current_session(&conn, "s_mock").unwrap().is_none());
        assert!(query_current_session(&conn, "s_real").unwrap().is_some());

        // token_stats_today：mock 的 999 不计入
        let stats = query_today_on(&conn, d, d + ms(10)).unwrap();
        assert_eq!(stats.input, 100);
        assert_eq!(stats.output, 20);
        assert_eq!(stats.cache_read, 30);
        assert!((stats.cost - 0.1).abs() < 1e-9);
    }

    // ---- M3：token_stats_today（TC-M3-03） ----

    #[test]
    fn m3_local_today_start_is_midnight() {
        // 注入固定时刻：0 点边界（无论中午还是午夜前 1ms，起点都是当天 00:00）
        let noon = chrono_local_midnight(2026, 8, 25) + 12 * 3600 * 1000;
        assert_eq!(local_today_start_ms(noon), chrono_local_midnight(2026, 8, 25));
        let before_midnight = chrono_local_midnight(2026, 8, 26) - 1; // 23:59:59.999
        assert_eq!(local_today_start_ms(before_midnight), chrono_local_midnight(2026, 8, 25));
        // 跨午夜后：起点翻到次日 0 点
        let next_day = chrono_local_midnight(2026, 8, 26);
        assert_eq!(local_today_start_ms(next_day), next_day);
    }

    #[test]
    fn m3_today_stats_window_and_error_paths() {
        // 无库 → no-database 原样透传
        let nodir = temp_dir("m3-today-nodb");
        let err = today_stats(&nodir, ms(1000)).unwrap_err();
        assert_eq!(err.code, ERR_NO_DATABASE);
        // legacy → legacy-storage
        let dir = temp_dir("m3-today-legacy");
        let s = dir.join("storage").join("session");
        std::fs::create_dir_all(&s).unwrap();
        std::fs::write(s.join("x.json"), b"{}").unwrap();
        let err = today_stats(&dir, ms(1000)).unwrap_err();
        assert_eq!(err.code, ERR_LEGACY_STORAGE);
        // schema 缺列 → schema-mismatch
        let dir = make_db("m3-today-schema", CREATE_SESSION_OLD);
        let err = today_stats(&dir, ms(1000)).unwrap_err();
        assert_eq!(err.code, ERR_SCHEMA_MISMATCH);

        // 窗口：只聚合今天 0 点起的行（昨天的行不计）
        let dir = make_db("m3-today", CREATE_SESSION);
        let d = chrono_local_midnight(2026, 8, 25);
        let now = d + 10 * 3600 * 1000;
        insert_session_model(&dir, "s_today", "p1", 0.2, (1000, 200, 50, 3000, 0), now - ms(10), now - ms(5),
            Some(&model_json("glm-5.3", "zhipuai")), None);
        insert_session_model(&dir, "s_yesterday", "p1", 9.9, (90000, 900, 0, 0, 0),
            d - ms(3600), d - ms(1800), Some(&model_json("glm-5.3", "zhipuai")), None);
        let stats = today_stats(&dir, now).unwrap();
        assert_eq!(stats.input, 1000);
        assert_eq!(stats.output, 200);
        assert_eq!(stats.cache_read, 3000);
        assert!((stats.cost - 0.2).abs() < 1e-9);
    }

    // ---- M3：idle 汇报追加今日累计（TC-M3-09 Rust 侧数据） ----

    #[test]
    fn m3_build_idle_report_with_today_appends_total() {
        let dir = make_db("m3-idle", CREATE_SESSION);
        let d = chrono_local_midnight(2026, 8, 25);
        let now = d + 9 * 3600 * 1000;
        // 本会话（新鲜有用量）
        insert_session_model(&dir, "ses_live", "p1", 0.05, (58_263, 910, 0, 0, 0), now - ms(600), now - ms(2),
            Some(&model_json("glm-5.3", "zhipuai")), None);
        // 今日另一会话（计入今日累计：in 1M + out 40k + cache 2M）
        insert_session_model(&dir, "ses_other", "p1", 0.1, (1_000_000, 40_000, 0, 2_000_000, 0),
            now - ms(7200), now - ms(3600), Some(&model_json("glm-5.3", "zhipuai")), None);
        let (text, today) = build_idle_report_with_today(&dir, "ses_live", now, 60_000).unwrap();
        assert_eq!(text, "本次会话消耗 token 59.2k");
        // total = in + out + cache_read（reasoning 不计）：1058263 + 40910 + 2000000
        assert_eq!(today, Some(1_058_263 + 40_910 + 2_000_000));
    }

    #[test]
    fn m3_build_idle_report_with_today_silent_on_no_report() {
        let dir = make_db("m3-idle2", CREATE_SESSION);
        let now = chrono_local_midnight(2026, 8, 25) + ms(1000);
        // 无记录 → None
        assert_eq!(build_idle_report_with_today(&dir, "ses_none", now, 60_000), None);
        // 陈旧（time_updated 落后 > 60s 护栏）→ None（护栏沿用，TC-M3-09-2）
        insert_session_model(&dir, "ses_stale", "p1", 0.05, (1000, 100, 0, 0, 0),
            now - ms(3600), now - ms(3600), Some(&model_json("glm-5.3", "zhipuai")), None);
        assert_eq!(build_idle_report_with_today(&dir, "ses_stale", now, 60_000), None);
        // 数据库不存在 → None（静默，不崩）
        let nodir = temp_dir("m3-idle-nodb");
        assert_eq!(build_idle_report_with_today(&nodir, "x", now, 60_000), None);
    }

    // ---- M5：双源查询与容错（TC-M5-03/05/09） ----

    /// 写一个 CC transcript 会话文件（双源测试 fixture；model=deepseek-v4-pro）。
    fn write_cc_session(cc_root: &Path, sid: &str, ts_ms: i64, tokens: (i64, i64)) {
        use chrono::TimeZone;
        let proj = cc_root.join("munged-proj");
        std::fs::create_dir_all(&proj).unwrap();
        let ts = chrono::Utc
            .timestamp_millis_opt(ts_ms)
            .single()
            .unwrap()
            .to_rfc3339_opts(chrono::SecondsFormat::Millis, true);
        let user = serde_json::json!({
            "type": "user", "timestamp": ts, "cwd": "/Users/youqi/develop/lab",
            "message": {"role": "user", "content": "hi"}
        });
        let assistant = serde_json::json!({
            "type": "assistant", "timestamp": ts, "uuid": "u-1",
            "message": {
                "id": "m-1", "model": "deepseek-v4-pro",
                "usage": {
                    "input_tokens": tokens.0, "output_tokens": tokens.1,
                    "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
                    "output_tokens_details": {"thinking_tokens": 0}
                }
            }
        });
        std::fs::write(
            proj.join(format!("{sid}.jsonl")),
            format!("{user}\n{assistant}\n"),
        )
        .unwrap();
    }

    #[test]
    fn m5_degraded_opencode_error_with_cc_data_degrades() {
        // opencode 源缺失（无 db）× CC 有数据 → Ok(CC-only) + degraded=Some
        let cc_dir = temp_dir("m5-cc");
        let d = chrono_local_midnight(2026, 8, 25);
        write_cc_session(&cc_dir, "cc-ses-1", d + ms(3600), (1000, 200));
        let nodb = temp_dir("m5-nodb");
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        let res = query_stats_dual(&nodb, &cc_dir, &cache, 0, d + ms(86_400), "session").unwrap();
        assert!(res.degraded.is_some(), "opencode 错 × CC 有数据 → degraded=Some");
        assert_eq!(res.rows.len(), 1);
        assert_eq!(res.rows[0].agent, AGENT_CLAUDE_CODE);
        assert_eq!(res.rows[0].tokens_input, 1000);
        assert_eq!(res.rows[0].cost, 0.0, "CC cost 恒 0（S4）");
        // today 同语义（pet 侧静默消费 CC-only 数值）
        let now = d + 9 * 3600 * 1000;
        let t = today_stats_dual(&nodb, &cc_dir, &cache, now).unwrap();
        assert!(t.degraded.is_some());
        assert_eq!(t.today.input, 1000);
        assert_eq!(t.today.output, 200);
        assert_eq!(t.today.cost, 0.0);
    }

    #[test]
    fn m5_degraded_cc_absent_rows_unchanged_m3_regression() {
        // CC 目录缺席 × opencode 正常 → rows 原样 + degraded=None（N-4 兼容口径回归）
        let dir = make_db("m5-nocc", CREATE_SESSION);
        let d = chrono_local_midnight(2026, 8, 25);
        insert_session_model(
            &dir, "s1", "p1", 0.1, (100, 20, 0, 30, 0), d, d + ms(1),
            Some(&model_json("glm-5.3", "zhipuai")), None,
        );
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        let no_cc = temp_dir("m5-nocc-cc").join("missing"); // 不存在的目录
        let expect = query_stats(&dir, 0, d + ms(10), "session").unwrap();
        let res = query_stats_dual(&dir, &no_cc, &cache, 0, d + ms(10), "session").unwrap();
        assert_eq!(res.degraded, None, "CC 缺席 → 无 degraded（M3 行为原样）");
        assert_eq!(res.rows, expect, "CC 缺席 → rows 与 M3 钉住的原样一致");
        // today 同语义
        let now = d + 9 * 3600 * 1000;
        let t = today_stats_dual(&dir, &no_cc, &cache, now).unwrap();
        assert_eq!(t.degraded, None);
        assert_eq!(t.today, today_stats(&dir, now).unwrap());
    }

    #[test]
    fn m5_degraded_both_missing_error_passthrough() {
        // 双源全缺 → 既有错误码透传（M3「无库→—」语义保留给全缺态）
        let nodb = temp_dir("m5-both-nodb");
        let no_cc = temp_dir("m5-both-nocc").join("missing");
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        let err = query_stats_dual(&nodb, &no_cc, &cache, 0, 1, "session").unwrap_err();
        assert_eq!(err.code, ERR_NO_DATABASE);
        let err = today_stats_dual(&nodb, &no_cc, &cache, ms(1000)).unwrap_err();
        assert_eq!(err.code, ERR_NO_DATABASE);
    }

    #[test]
    fn m5_dual_query_merges_by_agent_dimension() {
        let dir = make_db("m5-merge", CREATE_SESSION);
        let d = chrono_local_midnight(2026, 8, 25);
        insert_session_model(
            &dir, "s-oc", "p1", 0.1, (100, 10, 0, 0, 0), d, d + ms(100),
            Some(&model_json("glm-5.3", "zhipuai")), None,
        );
        let cc_dir = temp_dir("m5-merge-cc");
        write_cc_session(&cc_dir, "cc-ses-1", d + ms(200), (50, 5));
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        // day 维：两源各一行（agent 维度拆分），同日不拆柱
        let res = query_stats_dual(&dir, &cc_dir, &cache, 0, d + ms(86_400), "day").unwrap();
        assert_eq!(res.degraded, None);
        assert_eq!(res.rows.len(), 2);
        let oc = res.rows.iter().find(|r| r.agent == AGENT_OPENCODE).unwrap();
        let cc = res.rows.iter().find(|r| r.agent == AGENT_CLAUDE_CODE).unwrap();
        assert_eq!(oc.day.as_deref(), Some("2026-08-25"));
        assert_eq!(cc.day.as_deref(), Some("2026-08-25"), "双源同日不拆柱（本地日对齐）");
        assert_eq!(cc.tokens_input, 50);
        assert_eq!(cc.model_id.as_deref(), Some("deepseek-v4-pro"));
        // session 维：CC 行 time_updated 更晚 → 时间倒序统一排序（CC 在前）
        let res = query_stats_dual(&dir, &cc_dir, &cache, 0, d + ms(86_400), "session").unwrap();
        assert_eq!(res.rows[0].session_id.as_deref(), Some("cc-ses-1"));
        assert_eq!(res.rows[1].session_id.as_deref(), Some("s-oc"));
        assert_eq!(res.rows[1].agent, AGENT_OPENCODE);
        // range 维：CC 按 agent×model_id 聚合（day=None）
        let res = query_stats_dual(&dir, &cc_dir, &cache, 0, d + ms(86_400), "range").unwrap();
        assert_eq!(res.rows.len(), 2);
        for r in &res.rows {
            assert_eq!(r.day, None, "range 行无 day 维");
        }
    }

    #[test]
    fn m5_cc_week_grouping_uses_sqlite_week_semantics() {
        // CC 内存聚合 week 标签与 opencode SQL %Y-W%W 同语义（P2-4：双源同周不拆柱）
        let dir = make_db("m5-week", CREATE_SESSION);
        let d = chrono_local_midnight(2026, 8, 11); // 2026-W32
        insert_session_model(
            &dir, "s-oc", "p1", 0.1, (10, 1, 0, 0, 0), d, d + ms(1),
            Some(&model_json("glm-5.3", "zhipuai")), None,
        );
        let cc_dir = temp_dir("m5-week-cc");
        write_cc_session(&cc_dir, "cc-1", d + 12 * 3600 * 1000, (20, 2)); // 本地午间（防 UTC 跨日）
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        let res = query_stats_dual(&dir, &cc_dir, &cache, 0, d + ms(86_400), "week").unwrap();
        let oc = res.rows.iter().find(|r| r.agent == AGENT_OPENCODE).unwrap();
        let cc = res.rows.iter().find(|r| r.agent == AGENT_CLAUDE_CODE).unwrap();
        assert_eq!(oc.day.as_deref(), Some("2026-W32"));
        assert_eq!(cc.day.as_deref(), oc.day.as_deref(), "双源同周标签一致");
    }

    #[test]
    fn m5_today_dual_sums_both_sources() {
        // 双源齐全 → 合计 + degraded=None（三层快捷查看自动覆盖 CC）
        let dir = make_db("m5-today", CREATE_SESSION);
        let d = chrono_local_midnight(2026, 8, 25);
        let now = d + 9 * 3600 * 1000;
        insert_session_model(
            &dir, "s-oc", "p1", 0.1, (1000, 100, 0, 3000, 0), now - ms(10), now - ms(5),
            Some(&model_json("glm-5.3", "zhipuai")), None,
        );
        let cc_dir = temp_dir("m5-today-cc");
        write_cc_session(&cc_dir, "cc-1", now - ms(60), (500, 50));
        write_cc_session(&cc_dir, "cc-old", d - ms(3600), (99_999, 0)); // 昨天的行不计
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        let t = today_stats_dual(&dir, &cc_dir, &cache, now).unwrap();
        assert_eq!(t.degraded, None);
        assert_eq!(t.today.input, 1500);
        assert_eq!(t.today.output, 150);
        assert_eq!(t.today.cache_read, 3000);
        assert!((t.today.cost - 0.1).abs() < 1e-9, "CC cost 恒 0 不影响费用合计");
    }

    #[test]
    fn m5_build_cc_idle_report_guardrail_and_single_total() {
        // §十二 F1：CC 汇报改单总量口径（原无 cost 段双模板收敛）
        let cc_dir = temp_dir("m5-idle-cc");
        let nodb = temp_dir("m5-idle-nodb"); // opencode 无库 → 今日段降级 CC-only
        let now = chrono_local_midnight(2026, 8, 25) + 9 * 3600 * 1000;
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        // 新鲜 + 有用量 → 文案 + 今日段（双源合计）
        write_cc_session(&cc_dir, "cc-live", now - ms(2), (58_263, 910));
        let (text, today) =
            build_cc_idle_report(&cache, &nodb, &cc_dir, "cc-live", now, 60_000).unwrap();
        assert_eq!(text, "本次会话消耗 token 59.2k");
        assert!(!text.contains('$'), "F1：cost 段去除（S4 口径延续）");
        assert_eq!(today, Some(58_263 + 910), "今日段 = in+out+cache_read 双源合计");
        // 全零 → None（静默，TC-TK-12 口径）
        write_cc_session(&cc_dir, "cc-zero", now - ms(2), (0, 0));
        assert_eq!(build_cc_idle_report(&cache, &nodb, &cc_dir, "cc-zero", now, 60_000), None);
        // 陈旧（last_assistant_ts 落后 >60s）→ None（N-1 护栏消费 last_assistant_ts）
        write_cc_session(&cc_dir, "cc-stale", now - ms(120_000), (1000, 10));
        assert_eq!(build_cc_idle_report(&cache, &nodb, &cc_dir, "cc-stale", now, 60_000), None);
        // 文件缺席 → None
        assert_eq!(build_cc_idle_report(&cache, &nodb, &cc_dir, "cc-nope", now, 60_000), None);
    }

    // ---- v2 M6（V2-DESIGN §6.2，TC-M6-04-4）：today by_agent 分组 ----

    #[test]
    fn m6_today_by_agent_single_source_one_row() {
        // 单源（仅 opencode）→ 单行 {opencode, total}；total = in+out+cache_read
        //（今日总量同口径：reasoning 999 不计）——三层数值交叉断言的基础
        let dir = make_db("m6-oc", CREATE_SESSION);
        let d = chrono_local_midnight(2026, 8, 27);
        insert_session_model(
            &dir, "s1", "p1", 0.1, (100, 20, 999, 30, 0), d, d + ms(1),
            Some(&model_json("glm-5.3", "zhipuai")), None,
        );
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        let no_cc = temp_dir("m6-oc-cc").join("missing");
        let now = d + 9 * 3600 * 1000;
        let t = today_stats_dual(&dir, &no_cc, &cache, now).unwrap();
        assert_eq!(
            t.today.by_agent,
            vec![AgentTodayTotal { agent: AGENT_OPENCODE.into(), total: 150 }],
            "单源单行：opencode in100+out20+cache_read30（reasoning 不计）"
        );
        // 交叉断言：分布行总和 == 今日总量同口径（TC-M6-04-2）
        let total = t.today.input + t.today.output + t.today.cache_read;
        assert_eq!(t.today.by_agent.iter().map(|r| r.total).sum::<i64>(), total);
    }

    #[test]
    fn m6_today_by_agent_dual_source_two_rows_desc() {
        // 双源 → 两行、按 total 降序（cc 6000 > oc 150）
        let dir = make_db("m6-oc2", CREATE_SESSION);
        let d = chrono_local_midnight(2026, 8, 27);
        insert_session_model(
            &dir, "s1", "p1", 0.1, (100, 20, 0, 30, 0), d, d + ms(1),
            Some(&model_json("glm-5.3", "zhipuai")), None,
        );
        let cc_dir = temp_dir("m6-cc");
        write_cc_session(&cc_dir, "cc-1", d + ms(3600), (5000, 1000)); // cc total 6000
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        let now = d + 9 * 3600 * 1000;
        let t = today_stats_dual(&dir, &cc_dir, &cache, now).unwrap();
        assert_eq!(
            t.today.by_agent,
            vec![
                AgentTodayTotal { agent: AGENT_CLAUDE_CODE.into(), total: 6000 },
                AgentTodayTotal { agent: AGENT_OPENCODE.into(), total: 150 },
            ],
            "双源双行、有数据的 agent 按 total 降序"
        );
    }

    #[test]
    fn m6_today_by_agent_zero_data_omitted() {
        // 零数据（空 db + 无 CC）→ by_agent 省略（空 vec——前端不显示分布行）
        let dir = make_db("m6-zero", CREATE_SESSION);
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        let no_cc = temp_dir("m6-zero-cc").join("missing");
        let d = chrono_local_midnight(2026, 8, 27);
        let t = today_stats_dual(&dir, &no_cc, &cache, d + 9 * 3600 * 1000).unwrap();
        assert!(t.today.by_agent.is_empty(), "零数据 → by_agent 省略");
    }

    #[test]
    fn m6_today_by_agent_mock_filtered() {
        // mock 过滤：providerID='mock' 探测行的 token 不计入 by_agent
        //（与今日总量同口径——mock 行在全部查询中过滤，S4）
        let dir = make_db("m6-mock", CREATE_SESSION);
        let d = chrono_local_midnight(2026, 8, 27);
        insert_session_model(
            &dir, "s-mock", "p1", 0.0, (700, 0, 0, 0, 0), d, d + ms(1),
            Some(&model_json("probe-model", "mock")), None,
        );
        insert_session_model(
            &dir, "s-real", "p1", 0.1, (100, 20, 0, 30, 0), d, d + ms(2),
            Some(&model_json("glm-5.3", "zhipuai")), None,
        );
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        let no_cc = temp_dir("m6-mock-cc").join("missing");
        let t = today_stats_dual(&dir, &no_cc, &cache, d + 9 * 3600 * 1000).unwrap();
        assert_eq!(
            t.today.by_agent,
            vec![AgentTodayTotal { agent: AGENT_OPENCODE.into(), total: 150 }],
            "mock 行 700 token 不计入 by_agent"
        );
    }

    #[test]
    fn m6_today_by_agent_degraded_cc_only_single_row() {
        // degraded（opencode 源错误 × CC 有数据）→ by_agent 仅 cc 单行
        //（降级返回 CC-only 的分布也一致；pet 侧静默消费）
        let cc_dir = temp_dir("m6-deg-cc");
        let d = chrono_local_midnight(2026, 8, 27);
        write_cc_session(&cc_dir, "cc-1", d + ms(3600), (1000, 200)); // 1200
        let nodb = temp_dir("m6-deg-nodb");
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        let t = today_stats_dual(&nodb, &cc_dir, &cache, d + 9 * 3600 * 1000).unwrap();
        assert!(t.degraded.is_some());
        assert_eq!(
            t.today.by_agent,
            vec![AgentTodayTotal { agent: AGENT_CLAUDE_CODE.into(), total: 1200 }],
            "degraded CC-only → 单行 cc"
        );
    }

    // ---- 真实库对账（TC-TK-06；手动跑：--ignored --nocapture） ----

    /// v2 M5 真实双源对账（手动）：本机 opencode.db + ~/.claude/projects。
    #[test]
    #[ignore = "manual: 需本机真实 opencode.db + CC transcripts（冒烟证据用）"]
    fn real_dual_query_manual() {
        let dir = opencode_data_dir();
        let cc_dir = transcript::cc_projects_dir();
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        let now = now_ms();
        let from = now - 7 * 24 * 3600 * 1000;
        for g in ["session", "day", "week", "range"] {
            let res = query_stats_dual(&dir, &cc_dir, &cache, from, now, g).unwrap();
            let cc = res
                .rows
                .iter()
                .filter(|r| r.agent == AGENT_CLAUDE_CODE)
                .count();
            println!(
                "[dual] {g}: {} 行（cc={cc}）degraded={:?}",
                res.rows.len(),
                res.degraded
            );
            for r in res.rows.iter().filter(|r| r.agent == AGENT_CLAUDE_CODE).take(3) {
                println!(
                    "       cc 行: day={:?} model={:?} in={} out={} title={:?}",
                    r.day, r.model_id, r.tokens_input, r.tokens_output, r.title
                );
            }
        }
        let t = today_stats_dual(&dir, &cc_dir, &cache, now).unwrap();
        println!(
            "[dual] today: input={} output={} cache_read={} cost={:.4} degraded={:?}",
            t.today.input, t.today.output, t.today.cache_read, t.today.cost, t.degraded
        );
        // v2 M6：by_agent 分布（冒烟可见）
        for r in &t.today.by_agent {
            println!("       agent {} = {}", r.agent, r.total);
        }
    }    #[test]
    #[ignore = "manual: 需本机真实 opencode.db（对账证据用）"]
    fn real_db_reconciliation_manual() {
        let dir = opencode_data_dir();
        let Some(path) = detect_db_path(&dir) else {
            plog!("[reconcile] 本机无 opencode.db，跳过");
            return;
        };
        println!("[reconcile] db = {}", path.display());
        let to = now_ms();
        let from = to - 30 * 24 * 3600 * 1000;
        // ours：by day / by session
        let day_rows = query_stats(&dir, from, to, "day").unwrap();
        let sess_rows = query_stats(&dir, from, to, "session").unwrap();
        // reference：直接执行与 M5 实现同口径的原始 SQL（另一条只读连接）——
        // GROUP BY day, agent, model_id（agent 恒单值 'opencode'，列+分组保持
        // 形状统一）+ mock 过滤（S4：providerID='mock' 探测行全查询过滤）。
        //〔v2-m5 移交 TEST_BUG，M6 顺手修：原参考 SQL 仍 DESIGN §4.1 旧口径
        //   （GROUP BY day,project_id + 全量 session），与 M5 实现不对账。〕
        let conn = open_readonly(&path).unwrap();
        let (ref_day_cost, ref_day_cnt): (f64, i64) = conn
            .query_row(
                "SELECT IFNULL(SUM(cost),0), IFNULL(COUNT(*),0) FROM (\
                 SELECT strftime('%Y-%m-%d', time_updated/1000,'unixepoch','localtime') AS day, \
                 'opencode' AS agent, \
                 CASE WHEN json_valid(model) THEN json_extract(model,'$.id') END AS model_id, \
                 SUM(cost) AS cost FROM session \
                 WHERE time_updated >= ?1 AND time_updated <= ?2 \
                 AND COALESCE(CASE WHEN json_valid(model) THEN json_extract(model,'$.providerID') END,'') <> 'mock' \
                 GROUP BY day, agent, model_id)",
                [from, to],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .unwrap();
        let (ref_sess_cost, ref_sess_cnt): (f64, i64) = conn
            .query_row(
                "SELECT IFNULL(SUM(cost),0), COUNT(*) FROM session \
                 WHERE time_updated >= ?1 AND time_updated <= ?2 \
                 AND COALESCE(CASE WHEN json_valid(model) THEN json_extract(model,'$.providerID') END,'') <> 'mock'",
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
