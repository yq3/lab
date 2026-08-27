//! M5：CC transcript 解析与文件级缓存（V2-DESIGN §5.2，TC-M5-01/02）。
//!
//! - 布局：`~/.claude/projects/<munged-cwd>/<sessionId>.jsonl`，一文件一会话
//!   （S1）；sessionId = 文件名 stem（与 CC hook input `session_id` 同源）。
//! - 解析（防御式，坏行/空文件/非 JSON 行跳过不崩）：
//!   - **message.id 去重（S3）**：assistant 行收集 (message.id, usage 快照)，
//!     按 message.id 去重、**按行序取最后一条**（勿按 timestamp——尾行可能无
//!     ts）；id 缺失的行按行级顶层 uuid 兜底去重、两者皆缺独立计入（P3-4）。
//!   - SUM 五维 usage：input/output/cache_write/cache_read/reasoning（S2）。
//!   - model 取最后一条 message.model；title = 首条 user string 行
//!     `chars().take(60)`（中文按字符，P3-13）；project = 首条含非空 cwd 行
//!     basename（P2-6）；time_created/time_updated = 首/末条含 timestamp 的
//!     事件行（P1-1——mode/last-prompt 等非事件行无 ts）；last_assistant_ts =
//!     末条 assistant 行 timestamp（N-1 护栏专用，与 time_updated 两口径分离）。
//! - timestamp 为 UTC ISO8601 带 Z（S5）→ epoch ms（时区无关的瞬时值；
//!   分组到本地日/周时经 chrono Local 转换——`local_day_label`/`sqlite_week_label`）。
//! - `sqlite_week_label`：复刻 SQLite `strftime('%Y-W%W',…,'localtime')` 语义
//!   （周一起始的日历年周号，**非 ISO 年周**——跨年边界分叉会致双源同周拆柱，P2-4）。
//! - `TranscriptCache`（managed state，`Arc<Mutex<…>>` 窗口创建前 manage）：
//!   `entries: HashMap<PathBuf,(mtime_ms,size,CcSessionRow)>` + `index:
//!   HashMap<String,PathBuf>` sessionId 二级索引（P2-2——idle hook 只有
//!   (agent, session_id)）；查询时 mtime+size 未变直接用缓存、变了重解析；
//!   无常驻 watcher（查询驱动懒解析）；缓存缺失（首查/idle 先于查询）由
//!   refresh scan 补建。

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

/// CC 会话行（与 TokenRow 同构；agent 恒 "claude-code"、cost 恒 0.0——S4 口径）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CcSessionRow {
    pub session_id: String,
    /// S4：CC 无 cost 字段（全文件零出现），数据层恒 0.0、展示层显示 `—`。
    pub cost: f64,
    pub tokens_input: i64,
    pub tokens_output: i64,
    pub tokens_reasoning: i64,
    pub tokens_cache_read: i64,
    pub tokens_cache_write: i64,
    /// 首条含 timestamp 的事件行（UTC ISO8601 → epoch ms）。
    pub time_created: Option<i64>,
    /// 末条含 timestamp 的事件行（P1-1：非事件行无 ts，按字面首末行会得 None）。
    pub time_updated: Option<i64>,
    pub model_id: Option<String>,
    pub project_name: Option<String>,
    /// 首条 user string 行截断 60 字符；无 → sessionId 前 8 位。
    pub title: String,
    /// N-1 护栏专用：末条 assistant 行 timestamp（分组/过滤用 time_updated；
    /// 实测末条 system 行可晚于末条 assistant 3 分钟，护栏若用 time_updated
    /// 会误判静置会话为新鲜）。
    pub last_assistant_ts: Option<i64>,
}

/// CC transcript 项目目录（Windows `%USERPROFILE%\.claude\projects`）。
pub fn cc_projects_dir() -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        let base = std::env::var("USERPROFILE").unwrap_or_else(|_| ".".to_string());
        PathBuf::from(base).join(".claude").join("projects")
    }
    #[cfg(not(target_os = "windows"))]
    {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        PathBuf::from(home).join(".claude").join("projects")
    }
}

/// 扫描 `projects/*/` 一层内的 `*.jsonl`（顶层散落文件防御性兼容）；
/// **排除 `memory/` 子目录**（CC 自有目录非会话数据，P3-5）；
/// 目录不存在 → 空结果（静默——CC 未安装是常态）。
pub fn transcript_scan(dir: &Path) -> Vec<PathBuf> {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for entry in rd.flatten() {
        let path = entry.path();
        if path.is_file() {
            if is_jsonl(&path) {
                out.push(path);
            }
        } else if path.is_dir() {
            let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
            if name == "memory" {
                continue;
            }
            if let Ok(sub) = std::fs::read_dir(&path) {
                for e in sub.flatten() {
                    let p = e.path();
                    if p.is_file() && is_jsonl(&p) {
                        out.push(p);
                    }
                }
            }
        }
    }
    out.sort();
    out
}

fn is_jsonl(p: &Path) -> bool {
    p.extension().and_then(|e| e.to_str()) == Some("jsonl")
}

/// UTC ISO8601（RFC3339，带 Z 或偏移）→ epoch ms；解析失败 → None。
pub fn parse_timestamp_ms(s: &str) -> Option<i64> {
    chrono::DateTime::parse_from_rfc3339(s.trim())
        .ok()
        .map(|dt| dt.timestamp_millis())
}

/// epoch ms → 本地日标签 `%Y-%m-%d`（与 SQLite `'localtime'` 同口径，S5）。
pub fn local_day_label(ms: i64) -> Option<String> {
    use chrono::{Datelike, TimeZone};
    let date = chrono::Local.timestamp_millis_opt(ms).single()?.date_naive();
    Some(format!(
        "{:04}-{:02}-{:02}",
        date.year(),
        date.month(),
        date.day()
    ))
}

/// 复刻 SQLite `strftime('%Y-W%W', ms/1000, 'unixepoch', 'localtime')`：
/// 周一起始的**日历年**周号（week 00 = 首个周一前的日子；**非 ISO 年周**，
/// ISO 在跨年边界与 %W 分叉会导致双源同周拆柱——P2-4）。
pub fn sqlite_week_label(ms: i64) -> Option<String> {
    use chrono::{Datelike, TimeZone};
    let date = chrono::Local.timestamp_millis_opt(ms).single()?.date_naive();
    let yday = date.ordinal0() as i64; // 0-based day of year
    let wday = date.weekday().num_days_from_monday() as i64; // Monday=0
    let week = (yday + 7 - wday) / 7;
    Some(format!("{}-W{:02}", date.year(), week))
}

/// 单文件解析（坏行/空文件/非 JSON 行跳过不崩；无 assistant 行 → None）。
pub fn parse_session(path: &Path) -> Option<CcSessionRow> {
    let Ok(text) = std::fs::read_to_string(path) else {
        return None;
    };
    let session_id = path
        .file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_else(|| "unknown".into());

    let mut usage_by_key: HashMap<String, (i64, i64, i64, i64, i64)> = HashMap::new();
    let mut line_seq = 0u64; // 独立计入行的唯一键（id/uuid 皆缺，P3-4）
    let mut first_ts: Option<i64> = None;
    let mut last_ts: Option<i64> = None;
    let mut last_assistant_ts: Option<i64> = None;
    let mut model_id: Option<String> = None;
    let mut title: Option<String> = None;
    let mut project_name: Option<String> = None;
    let mut assistant_seen = false;

    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let Ok(obj) = serde_json::from_str::<serde_json::Value>(line) else {
            continue; // 坏行/非 JSON：跳过不崩
        };
        // 时间戳：任何含 timestamp 的行（事件行；非事件行无 ts，P1-1）
        if let Some(ts) = obj
            .get("timestamp")
            .and_then(|v| v.as_str())
            .and_then(parse_timestamp_ms)
        {
            if first_ts.is_none() {
                first_ts = Some(ts);
            }
            last_ts = Some(ts);
        }
        // cwd：首条含非空 cwd 的行 → basename（P2-6）
        if project_name.is_none() {
            if let Some(cwd) = obj.get("cwd").and_then(|v| v.as_str()) {
                if !cwd.trim().is_empty() {
                    project_name = Path::new(cwd)
                        .file_name()
                        .map(|n| n.to_string_lossy().into_owned());
                }
            }
        }
        let typ = obj.get("type").and_then(|v| v.as_str()).unwrap_or("");
        match typ {
            "assistant" => {
                let message = obj.get("message");
                // 去重键：message.id → 顶层 uuid 兜底 → 独立计入（P3-4）
                let key = message
                    .and_then(|m| m.get("id"))
                    .and_then(|v| v.as_str())
                    .filter(|s| !s.is_empty())
                    .map(|s| s.to_string())
                    .or_else(|| {
                        obj.get("uuid")
                            .and_then(|v| v.as_str())
                            .filter(|s| !s.is_empty())
                            .map(|s| s.to_string())
                    })
                    .unwrap_or_else(|| {
                        line_seq += 1;
                        format!("\u{0}line-{line_seq}")
                    });
                // 按行序取末条：直接覆盖（S3）
                let usage = usage5_of(message);
                // 按行序取末条：直接覆盖（S3）
                usage_by_key.insert(key, usage);
                assistant_seen = true;
                // 末条 assistant 行 timestamp（N-1 护栏口径）
                if let Some(ts) = obj
                    .get("timestamp")
                    .and_then(|v| v.as_str())
                    .and_then(parse_timestamp_ms)
                {
                    last_assistant_ts = Some(ts);
                }
                // model 取最后一条 message.model（纯字符串）
                if let Some(m) = message.and_then(|m| m.get("model")).and_then(|v| v.as_str()) {
                    if !m.is_empty() {
                        model_id = Some(m.to_string());
                    }
                }
            }
            "user" => {
                // 标题：首条 user 且 content 为 string 的行截断（chars 按字符，P3-13）
                if title.is_none() {
                    if let Some(content) = obj
                        .get("message")
                        .and_then(|m| m.get("content"))
                        .and_then(|v| v.as_str())
                    {
                        let trimmed = content.trim();
                        if !trimmed.is_empty() {
                            title = Some(trimmed.chars().take(60).collect());
                        }
                    }
                }
            }
            _ => {} // 未知行类型跳过（防御式）
        }
    }

    if !assistant_seen {
        return None;
    }

    let mut sum = (0i64, 0i64, 0i64, 0i64, 0i64);
    for (_, u) in usage_by_key {
        sum.0 += u.0;
        sum.1 += u.1;
        sum.2 += u.2;
        sum.3 += u.3;
        sum.4 += u.4;
    }

    let title = title.unwrap_or_else(|| session_id.chars().take(8).collect());
    Some(CcSessionRow {
        session_id,
        cost: 0.0,
        tokens_input: sum.0,
        tokens_output: sum.1,
        tokens_reasoning: sum.2,
        tokens_cache_read: sum.3,
        tokens_cache_write: sum.4,
        time_created: first_ts,
        time_updated: last_ts,
        model_id,
        project_name,
        title,
        last_assistant_ts,
    })
}

/// usage 五维映射（S2；缺字段按 0——防御式）。
type Usage5 = (i64, i64, i64, i64, i64); // input, output, reasoning, cache_read, cache_write

fn usage5_of(message: Option<&serde_json::Value>) -> Usage5 {
    let usage = message.and_then(|m| m.get("usage"));
    let num = |k: &str| -> i64 {
        usage
            .and_then(|u| u.get(k))
            .and_then(|v| v.as_i64())
            .unwrap_or(0)
    };
    (
        num("input_tokens"),
        num("output_tokens"),
        usage
            .and_then(|u| u.get("output_tokens_details"))
            .and_then(|d| d.get("thinking_tokens"))
            .and_then(|v| v.as_i64())
            .unwrap_or(0),
        num("cache_read_input_tokens"),
        num("cache_creation_input_tokens"),
    )
}

// ---------------------------------------------------------------------------
// TranscriptCache：文件级缓存 + sessionId 二级索引（TC-M5-02）
// ---------------------------------------------------------------------------

#[derive(Debug, Default)]
pub struct TranscriptCache {
    /// PathBuf → (mtime, size, 解析行)；mtime+size 未变直接复用（S7）。
    /// mtime 用 SystemTime 纳秒精度（CC 原子写 tmp+rename 可能落在同一毫秒内，
    /// 毫秒精度会漏失效——R4）。
    pub entries: HashMap<PathBuf, (SystemTime, u64, CcSessionRow)>,
    /// sessionId → PathBuf（P2-2：idle hook 只有 (agent, session_id)）。
    pub index: HashMap<String, PathBuf>,
}

fn mtime_of(meta: &std::fs::Metadata) -> SystemTime {
    meta.modified().unwrap_or(UNIX_EPOCH)
}

impl TranscriptCache {
    /// 全目录扫描 + 缓存刷新：未变文件直接用缓存，变了重解析；新文件解析入缓存；
    /// 消失的文件移除缓存与索引。返回全部会话行（时间倒序）。
    pub fn refresh(&mut self, dir: &Path) -> Vec<CcSessionRow> {
        let files = transcript_scan(dir);
        let seen: std::collections::HashSet<PathBuf> = files.iter().cloned().collect();
        let mut rows = Vec::new();
        for f in &files {
            let meta = std::fs::metadata(f).ok();
            let (mtime, size) = meta
                .as_ref()
                .map(|m| (mtime_of(m), m.len()))
                .unwrap_or((UNIX_EPOCH, 0));
            if let Some((cm, cs, row)) = self.entries.get(f) {
                if *cm == mtime && *cs == size {
                    rows.push(row.clone());
                    continue;
                }
            }
            if let Some(row) = parse_session(f) {
                self.index.insert(row.session_id.clone(), f.clone());
                self.entries.insert(f.clone(), (mtime, size, row.clone()));
                rows.push(row);
            }
        }
        self.entries.retain(|p, _| seen.contains(p));
        self.index.retain(|_, p| seen.contains(p));
        rows.sort_by(|a, b| b.time_updated.cmp(&a.time_updated));
        rows
    }

    /// 经 sessionId 索引定位文件并取会话行：索引命中 → (mtime,size) 校验/
    /// 重解析；索引缺失（首查/idle 先于查询）→ refresh 补建后取。无 → None。
    pub fn find_session(&mut self, dir: &Path, session_id: &str) -> Option<CcSessionRow> {
        let path = match self.index.get(session_id).cloned() {
            Some(p) => p,
            None => {
                self.refresh(dir);
                self.index.get(session_id).cloned()?
            }
        };
        let meta = std::fs::metadata(&path).ok();
        let (mtime, size) = meta
            .as_ref()
            .map(|m| (mtime_of(m), m.len()))
            .unwrap_or((UNIX_EPOCH, 0));
        if let Some((cm, cs, row)) = self.entries.get(&path) {
            if *cm == mtime && *cs == size {
                return Some(row.clone());
            }
        }
        let row = parse_session(&path)?;
        self.index.insert(row.session_id.clone(), path.clone());
        self.entries.insert(path, (mtime, size, row.clone()));
        Some(row)
    }
}

// ---------------------------------------------------------------------------
// 测试（TC-M5-01/02）
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn temp_dir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "pulsepet-cc-{}-{}-{tag}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    fn write_lines(path: &Path, lines: &[serde_json::Value]) {
        let text: String = lines
            .iter()
            .map(|l| serde_json::to_string(l).unwrap())
            .collect::<Vec<_>>()
            .join("\n");
        std::fs::write(path, format!("{text}\n")).unwrap();
    }

    fn assistant_line(
        id: Option<&str>,
        uuid: Option<&str>,
        ts: &str,
        usage: serde_json::Value,
    ) -> serde_json::Value {
        let mut obj = json!({
            "type": "assistant",
            "timestamp": ts,
            "message": {
                "id": id.unwrap_or(""),
                "model": "deepseek-v4-pro",
                "usage": usage
            }
        });
        if let Some(id) = id {
            obj["message"]["id"] = json!(id);
        } else {
            obj["message"].as_object_mut().unwrap().remove("id");
        }
        if let Some(u) = uuid {
            obj["uuid"] = json!(u);
        }
        obj
    }

    /// 基线五维 usage（全字段齐备）。
    fn usage5(input: i64, output: i64, reasoning: i64, cache_read: i64, cache_write: i64) -> serde_json::Value {
        json!({
            "input_tokens": input,
            "output_tokens": output,
            "cache_creation_input_tokens": cache_write,
            "cache_read_input_tokens": cache_read,
            "output_tokens_details": { "thinking_tokens": reasoning }
        })
    }

    /// 与 SQLite 'localtime' 对账的本地日标签（测试 oracle）。
    fn sqlite_day(ms: i64) -> String {
        let conn = rusqlite::Connection::open_in_memory().unwrap();
        conn.query_row(
            "SELECT strftime('%Y-%m-%d', ?1/1000, 'unixepoch', 'localtime')",
            [ms],
            |r| r.get::<_, String>(0),
        )
        .unwrap()
    }

    fn sqlite_week(ms: i64) -> String {
        let conn = rusqlite::Connection::open_in_memory().unwrap();
        conn.query_row(
            "SELECT strftime('%Y-W%W', ?1/1000, 'unixepoch', 'localtime')",
            [ms],
            |r| r.get::<_, String>(0),
        )
        .unwrap()
    }

    // ---- TC-M5-01-1：S3 message.id 去重（回归钉子） ----

    #[test]
    fn m5_s3_dedup_by_message_id_last_line_wins() {
        let dir = temp_dir("s3");
        let f = dir.join("aaaaaaaa-1111-2222-3333-444444444444.jsonl");
        // 6 行 assistant：3 条 message，各写两次（thinking/text 双行陷阱）；
        // m1 两次 usage 不同 → 按行序取末条（第二次）
        let ts = "2026-08-24T07:03:35.156Z";
        write_lines(
            &f,
            &[
                assistant_line(Some("m1"), Some("u1a"), ts, usage5(100, 10, 0, 0, 0)),
                assistant_line(Some("m1"), Some("u1b"), ts, usage5(111, 11, 0, 0, 0)),
                assistant_line(Some("m2"), Some("u2a"), ts, usage5(200, 20, 1, 2, 3)),
                assistant_line(Some("m2"), Some("u2b"), ts, usage5(200, 20, 1, 2, 3)),
                assistant_line(Some("m3"), Some("u3a"), ts, usage5(300, 30, 0, 0, 0)),
                assistant_line(Some("m3"), Some("u3b"), ts, usage5(300, 30, 0, 0, 0)),
            ],
        );
        let row = parse_session(&f).expect("应有行");
        // 去重后 3 条 SUM：m1 取末条 (111,11) + m2 (200,20) + m3 (300,30)
        assert_eq!(row.tokens_input, 111 + 200 + 300, "不去重会得 1222（翻倍）");
        assert_eq!(row.tokens_output, 11 + 20 + 30);
        assert_eq!(row.tokens_reasoning, 1);
        assert_eq!(row.tokens_cache_read, 2);
        assert_eq!(row.tokens_cache_write, 3);
    }

    #[test]
    fn m5_s3_dedup_fallback_to_uuid_then_independent() {
        let dir = temp_dir("s3-fallback");
        let f = dir.join("bbbbbbbb-1111-2222-3333-444444444444.jsonl");
        let ts = "2026-08-24T07:03:35.156Z";
        write_lines(
            &f,
            &[
                // id 缺失 → uuid 兜底去重：同 uuid 两行 → 一条（取末条 50）
                assistant_line(None, Some("u-x"), ts, usage5(40, 0, 0, 0, 0)),
                assistant_line(None, Some("u-x"), ts, usage5(50, 0, 0, 0, 0)),
                // id/uuid 皆缺 → 独立计入：两行都算
                assistant_line(None, None, ts, usage5(7, 0, 0, 0, 0)),
                assistant_line(None, None, ts, usage5(8, 0, 0, 0, 0)),
            ],
        );
        let row = parse_session(&f).expect("应有行");
        assert_eq!(row.tokens_input, 50 + 7 + 8);
    }

    // ---- TC-M5-01-3：坏行/空文件/非 JSON 跳过不崩 ----

    #[test]
    fn m5_bad_lines_skipped_and_empty_file_none() {
        let dir = temp_dir("bad");
        let f = dir.join("cccccccc-1111-2222-3333-444444444444.jsonl");
        // 空文件 → None
        std::fs::write(&f, "").unwrap();
        assert_eq!(parse_session(&f), None);
        // 只有垃圾行 → None
        std::fs::write(&f, "not json\n{{{ garbage\n\n").unwrap();
        assert_eq!(parse_session(&f), None);
        // 垃圾行包夹合法行 → 正常解析
        let ts = "2026-08-24T07:03:35.156Z";
        let mut text = "not json\n".to_string();
        text.push_str(&serde_json::to_string(&assistant_line(Some("m1"), Some("u1"), ts, usage5(5, 0, 0, 0, 0))).unwrap());
        text.push_str("\n[1,2,3]\n");
        std::fs::write(&f, text).unwrap();
        let row = parse_session(&f).expect("垃圾行不影响合法行");
        assert_eq!(row.tokens_input, 5);
        // usage 缺字段 → 按 0
        let no_usage = json!({"type": "assistant", "timestamp": ts, "message": {"id": "m2", "model": "m"}});
        write_lines(&f, &[no_usage]);
        let row = parse_session(&f).expect("缺 usage 不崩");
        assert_eq!(
            (row.tokens_input, row.tokens_output, row.tokens_reasoning, row.tokens_cache_read, row.tokens_cache_write),
            (0, 0, 0, 0, 0)
        );
    }

    // ---- TC-M5-01-4：P1-1 时间戳钉子 + UTC→本地跨日 ----

    #[test]
    fn m5_p1_timestamps_from_first_last_event_rows() {
        let dir = temp_dir("p1");
        let f = dir.join("dddddddd-1111-2222-3333-444444444444.jsonl");
        // mode/permission-mode 无 ts 包夹首部；file-history-snapshot/last-prompt 无 ts 包夹尾部
        write_lines(
            &f,
            &[
                json!({"type": "mode", "mode": "normal"}),
                json!({"type": "permission-mode", "permissionMode": "default"}),
                assistant_line(Some("m1"), Some("u1"), "2026-08-24T07:03:35.156Z", usage5(1, 0, 0, 0, 0)),
                json!({"type": "file-history-snapshot", "snapshot": {}}),
                json!({"type": "last-prompt", "prompt": "x"}),
            ],
        );
        let row = parse_session(&f).expect("首末非事件行不影响");
        let expect = parse_timestamp_ms("2026-08-24T07:03:35.156Z").unwrap();
        assert_eq!(row.time_created, Some(expect));
        assert_eq!(row.time_updated, Some(expect));
        assert_eq!(row.last_assistant_ts, Some(expect));
    }

    #[test]
    fn m5_p1_two_timescale_separation() {
        // N-1：末条 system 行晚于末条 assistant 行 → time_updated ≠ last_assistant_ts
        let dir = temp_dir("p1-sep");
        let f = dir.join("eeeeeeee-1111-2222-3333-444444444444.jsonl");
        let t_a = "2026-08-24T07:03:35.156Z";
        let t_sys = "2026-08-24T07:06:35.156Z"; // 晚 3 分钟（spike 实测形态）
        write_lines(
            &f,
            &[
                assistant_line(Some("m1"), Some("u1"), t_a, usage5(1, 0, 0, 0, 0)),
                json!({"type": "system", "timestamp": t_sys, "subtype": "init"}),
            ],
        );
        let row = parse_session(&f).expect("应有行");
        assert_eq!(row.time_updated, parse_timestamp_ms(t_sys));
        assert_eq!(row.last_assistant_ts, parse_timestamp_ms(t_a), "护栏只看 assistant 行");
    }

    #[test]
    fn m5_utc_epoch_ms_is_tz_independent_instant() {
        // UTC ISO8601 → epoch ms = 时区无关瞬时值；本地日标签与 SQLite localtime 对账
        let ms = parse_timestamp_ms("2026-08-24T16:30:00.000Z").unwrap();
        let expect = chrono::DateTime::parse_from_rfc3339("2026-08-24T16:30:00.000Z")
            .unwrap()
            .timestamp_millis();
        assert_eq!(ms, expect);
        assert_eq!(local_day_label(ms).as_deref(), Some(sqlite_day(ms).as_str()));
        // 本地口径断言：日标签 = chrono Local 日期（本机 UTC+8 下为 08-25，
        // 与 UTC 日期 08-24 跨日——注入时区后由 Local/SQLite oracle 双侧钉住）
        use chrono::{Datelike, TimeZone};
        let local_date = chrono::Local.timestamp_millis_opt(ms).single().unwrap().date_naive();
        let label = local_day_label(ms).unwrap();
        assert_eq!(
            label,
            format!(
                "{:04}-{:02}-{:02}",
                local_date.year(),
                local_date.month(),
                local_date.day()
            )
        );
        let utc_date = chrono::Utc.timestamp_millis_opt(ms).single().unwrap().date_naive();
        assert_ne!(
            format!("{label}"),
            format!(
                "{:04}-{:02}-{:02}",
                utc_date.year(),
                utc_date.month(),
                utc_date.day()
            ),
            "本机时区非零偏移下 UTC 16:30 与 UTC 日期跨日（转换到本地口径生效）"
        );
    }

    // ---- TC-M5-01-5：%W 跨年对齐钉子（P2-4） ----

    #[test]
    fn m5_week_label_matches_sqlite_percent_w_across_years() {
        // 2026-12-28（周一）→ 2026-W52；2027-01-01（周五，首周一前）→ 2027-W00；
        // 2027-01-04（周一）→ 2027-W01（正午 UTC 保证 ±12 时区内日期稳定）
        for (s, expect) in [
            ("2026-12-28T12:00:00Z", "2026-W52"),
            ("2027-01-01T12:00:00Z", "2027-W00"),
            ("2027-01-04T12:00:00Z", "2027-W01"),
            ("2026-08-24T12:00:00Z", "2026-W34"),
        ] {
            let ms = parse_timestamp_ms(s).unwrap();
            assert_eq!(
                sqlite_week_label(ms).as_deref(),
                Some(expect),
                "{s} 应得 {expect}"
            );
            assert_eq!(
                sqlite_week_label(ms).as_deref(),
                Some(sqlite_week(ms).as_str()),
                "{s} 应与 SQLite localtime 对账一致"
            );
        }
        // ISO 年周 vs %W 分叉点：2027-01-01 是 ISO 2026-W53，%W 是 2027-W00
        assert_ne!(sqlite_week_label(parse_timestamp_ms("2027-01-01T12:00:00Z").unwrap()).as_deref(), Some("2026-W53"));
    }

    // ---- TC-M5-01-6：title 中文 60 字符 / 回退 sessionId 前 8 位 ----

    #[test]
    fn m5_title_chinese_60_chars_and_fallback() {
        let dir = temp_dir("title");
        let f = dir.join("ffffffff-1111-2222-3333-444444444444.jsonl");
        let ts = "2026-08-24T07:03:35.156Z";
        let long = "中".repeat(70);
        write_lines(
            &f,
            &[
                json!({"type": "user", "timestamp": ts, "message": {"role": "user", "content": long}}),
                assistant_line(Some("m1"), Some("u1"), ts, usage5(1, 0, 0, 0, 0)),
            ],
        );
        let row = parse_session(&f).unwrap();
        assert_eq!(row.title.chars().count(), 60, "中文按字符截断（非字节）");
        assert!(row.title.chars().all(|c| c == '中'));

        // 无 user string 行 → sessionId 前 8 位
        let f2 = dir.join("abcdefgh-1234-5678-9abc-def012345678.jsonl");
        write_lines(&f2, &[assistant_line(Some("m1"), Some("u1"), ts, usage5(1, 0, 0, 0, 0))]);
        let row2 = parse_session(&f2).unwrap();
        assert_eq!(row2.title, "abcdefgh");
    }

    // ---- TC-M5-01-7：首条含非空 cwd 行 basename（P2-6）/ 全无 → None ----

    #[test]
    fn m5_project_first_cwd_basename_with_snapshot_dilution() {
        let dir = temp_dir("project");
        let f = dir.join("01234567-89ab-cdef-0123-456789abcdef.jsonl");
        let ts = "2026-08-24T07:03:35.156Z";
        write_lines(
            &f,
            &[
                // 无 cwd 的 snapshot 行稀释在前（P2-6：非众数防御）
                json!({"type": "file-history-snapshot", "snapshot": {"trackedFileBackups": {}}}),
                json!({"type": "mode", "mode": "normal"}),
                json!({"type": "user", "timestamp": ts, "cwd": "/Users/youqi/develop/lab", "message": {"role": "user", "content": "hi"}}),
                assistant_line(Some("m1"), Some("u1"), ts, usage5(1, 0, 0, 0, 0)),
            ],
        );
        let row = parse_session(&f).unwrap();
        assert_eq!(row.project_name.as_deref(), Some("lab"));

        // 全无 cwd → None
        let f2 = dir.join("00000000-1111-2222-3333-444444444444.jsonl");
        write_lines(
            &f2,
            &[assistant_line(Some("m1"), Some("u1"), ts, usage5(1, 0, 0, 0, 0))],
        );
        assert_eq!(parse_session(&f2).unwrap().project_name, None);
    }

    // ---- TC-M5-01-9：memory/ 排除 + 目录缺失空结果 ----

    #[test]
    fn m5_scan_excludes_memory_and_missing_dir_is_empty() {
        let dir = temp_dir("scan");
        let proj = dir.join("projects");
        std::fs::create_dir_all(proj.join("munged-a").join("memory")).unwrap();
        std::fs::create_dir_all(proj.join("munged-b")).unwrap();
        std::fs::create_dir_all(proj.join("memory")).unwrap();
        std::fs::write(proj.join("munged-a").join("s1.jsonl"), b"{}\n").unwrap();
        std::fs::write(proj.join("munged-a").join("memory").join("x.jsonl"), b"{}\n").unwrap();
        std::fs::write(proj.join("munged-b").join("s2.jsonl"), b"{}\n").unwrap();
        std::fs::write(proj.join("memory").join("y.jsonl"), b"{}\n").unwrap();
        let files = transcript_scan(&proj);
        assert_eq!(files.len(), 2, "只收 s1/s2，memory/ 全部排除：{files:?}");
        // 目录不存在 → 空结果（静默）
        assert!(transcript_scan(&dir.join("nope")).is_empty());
    }

    // ---- TC-M5-02：缓存与索引 ----

    fn session_lines(usage: i64) -> Vec<serde_json::Value> {
        vec![
            assistant_line(
                Some("m1"),
                Some("u1"),
                "2026-08-24T07:03:35.156Z",
                usage5(usage, 0, 0, 0, 0),
            ),
        ]
    }

    #[test]
    fn m5_cache_hit_reuses_without_reparse() {
        let dir = temp_dir("cache-hit");
        let f = dir.join("abcabcab-1111-2222-3333-444444444444.jsonl");
        write_lines(&f, &session_lines(100));
        let orig_mtime = std::fs::metadata(&f).unwrap().modified().unwrap();
        let mut cache = TranscriptCache::default();
        let rows = cache.refresh(&dir);
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0].tokens_input, 100);

        // 同长度不同内容 + 还原 mtime → (mtime,size) 未变 → 命中缓存（不重解析）
        let old = std::fs::read_to_string(&f).unwrap();
        let new_text = format!(
            "{}\n",
            serde_json::to_string(&assistant_line(
                Some("m1"),
                Some("u1"),
                "2026-08-24T07:03:35.156Z",
                usage5(999, 0, 0, 0, 0)
            ))
            .unwrap()
        );
        assert_eq!(old.len(), new_text.len(), "同字节长度前置条件");
        std::fs::write(&f, new_text).unwrap();
        std::fs::OpenOptions::new()
            .write(true)
            .open(&f)
            .unwrap()
            .set_modified(orig_mtime)
            .unwrap();
        let rows2 = cache.refresh(&dir);
        assert_eq!(rows2[0].tokens_input, 100, "(mtime,size) 未变 → 缓存命中，内容变化不可见");

        // 变了（追加一行，size 变）→ 重解析
        let mut lines = session_lines(100);
        lines.push(assistant_line(Some("m2"), Some("u2"), "2026-08-24T07:04:00.000Z", usage5(50, 0, 0, 0, 0)));
        write_lines(&f, &lines);
        let rows3 = cache.refresh(&dir);
        assert_eq!(rows3[0].tokens_input, 150, "size 变化 → 重解析");
    }

    #[test]
    fn m5_cache_atomic_tmp_rename_invalidates() {
        // CC 原子写：tmp 文件写完 rename 落位 → 新文件 mtime → 缓存自动失效（R4）
        let dir = temp_dir("cache-rename");
        let f = dir.join("abcabcab-2222-3333-4444-555555555555.jsonl");
        write_lines(&f, &session_lines(10));
        let mut cache = TranscriptCache::default();
        assert_eq!(cache.refresh(&dir)[0].tokens_input, 10);
        let tmp = dir.join(".tmp-session");
        write_lines(&tmp, &session_lines(20));
        std::fs::rename(&tmp, &f).unwrap();
        assert_eq!(cache.refresh(&dir)[0].tokens_input, 20, "rename 落位新 mtime → 失效重解析");
    }

    #[test]
    fn m5_cache_session_index_locate_and_rebuild() {
        let dir = temp_dir("cache-index");
        let proj = dir.join("proj");
        std::fs::create_dir_all(&proj).unwrap();
        let f = proj.join("idx-idx-0000-0000-000000000001.jsonl");
        write_lines(&f, &session_lines(42));
        let mut cache = TranscriptCache::default();
        cache.refresh(&proj);
        // 索引定位（idle hook 只有 session_id）
        assert_eq!(
            cache.index.get("idx-idx-0000-0000-000000000001"),
            Some(&f)
        );
        assert_eq!(cache.find_session(&proj, "idx-idx-0000-0000-000000000001").unwrap().tokens_input, 42);
        // 空缓存直接 find（idle 先于查询）→ scan 补建
        let mut fresh = TranscriptCache::default();
        assert_eq!(fresh.find_session(&proj, "idx-idx-0000-0000-000000000001").unwrap().tokens_input, 42);
        // 未知 session → None
        assert_eq!(fresh.find_session(&proj, "nope-nope").is_none(), true);
        // 文件删除 → 缓存与索引清退
        std::fs::remove_file(&f).unwrap();
        cache.refresh(&proj);
        assert!(cache.entries.is_empty());
        assert!(cache.index.is_empty());
    }

    // ---- 真实 CC transcript 对账（手动跑：--ignored --nocapture） ----

    #[test]
    #[ignore = "manual: 需本机真实 ~/.claude/projects（冒烟对账证据用）"]
    fn real_cc_transcripts_manual() {
        let dir = cc_projects_dir();
        let files = transcript_scan(&dir);
        println!("[cc] 扫描文件数 = {}", files.len());
        assert!(!files.is_empty(), "本机应有 CC transcript 存量");
        let mut cache = TranscriptCache::default();
        let rows = cache.refresh(&dir);
        println!("[cc] 会话数 = {}", rows.len());
        for r in &rows {
            println!(
                "[cc] {} | in={} out={} cache_r={} cache_w={} reason={} | model={:?} | project={:?} | title={}",
                r.session_id,
                r.tokens_input,
                r.tokens_output,
                r.tokens_cache_read,
                r.tokens_cache_write,
                r.tokens_reasoning,
                r.model_id,
                r.project_name,
                r.title
            );
            println!(
                "     created={:?} updated={:?} last_assistant={:?}",
                r.time_created, r.time_updated, r.last_assistant_ts
            );
        }
        assert_eq!(rows.len(), files.len(), "一文件一会话（S1）");
        for r in &rows {
            assert!(
                r.time_created.is_some() && r.time_updated.is_some(),
                "时间戳取自含 timestamp 事件行（P1-1）——{}",
                r.session_id
            );
            assert_eq!(r.cost, 0.0, "cost 恒 0（S4）");
        }
    }
}
