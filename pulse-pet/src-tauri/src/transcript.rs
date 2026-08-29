//! M5：CC transcript 解析与文件级缓存（V2-DESIGN §5.2，TC-M5-01/02）。
//!
//! - 布局：`~/.claude/projects/<munged-cwd>/<sessionId>.jsonl`，一文件一会话
//!   （S1）；sessionId = 文件名 stem（与 CC hook input `session_id` 同源）。
//! - 解析（防御式，坏行/空文件/非 JSON 行跳过不崩）：
//!   - **message.id 去重（S3）**：assistant 行收集 (message.id, usage 快照)，
//!     按 message.id 去重、**按行序取最后一条**（勿按 timestamp——尾行可能无
//!     ts）；id 缺失的行按行级顶层 uuid 兜底去重、两者皆缺独立计入（P3-4）。
//!   - SUM 五维 usage：input/output/cache_write/cache_read/reasoning（S2）；
//!     §14 起同时产出 [`CcSessionRow::by_day`] 按消息时间归天的分桶明细
//!     （会话级总量 = 各桶之和，去重语义不变）。
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
//!  `entries: HashMap<PathBuf,CacheEntry>`（mtime/size/file_id 判定 + 已解析
//!  偏移 + 增量续算状态 + row/负缓存）+ `index: HashMap<String,PathBuf>`
//!  sessionId 二级索引（P2-2——idle hook 只有 (agent, session_id)）；查询时
//!  未变直接用缓存、append 增长走**增量偏移解析**（只读尾部新增行）、变小/
//!  换文件对象回退全量；无常驻 watcher（查询驱动懒解析）；缓存缺失（首查/
//!  idle 先于查询）由 refresh scan 补建。
//!  并发口径（task-pulsepet-v2-polish #11 方案 α）：锁内只做轻量判定与写回，
//!  I/O 与解析在锁外（[`refresh_unlocked`] / [`find_session_unlocked`]）；
//!  刷新进行中后来者用旧快照让路。跨重启仍全量一次（内存缓存固有）。

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
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
    /// §14（V2-OPEN-ITEMS）：按**消息时间**归天的用量明细（升序；去重后每条
    /// assistant usage 计入其行 timestamp 所在日）。day/week/range/today 聚合
    /// 消费它——跨天会话每天各得各的，不再整行归最后活跃日。会话级五维总量
    /// = by_day 各桶之和（去重口径不变，两者同源同时产出；例外：行 ts 与
    /// 会话 time_updated 皆无的条目计总量不进桶——防御口径，committer P3-1
    /// 括注，详见 finalize_state）。
    pub by_day: Vec<CcDayUsage>,
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

/// §14：单日用量桶（`CcSessionRow.by_day` 元素）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CcDayUsage {
    /// 本地日标签 `%Y-%m-%d`（[`local_day_label`] 同口径）。
    pub day: String,
    /// 桶内**最早**消息时刻（epoch ms；tester P3-1：取最小值，与 HashMap
    /// 迭代序/文件行序无关）——week/range 窗口过滤与周标签推导的代表时刻
    /// （custom 窗口双侧天对齐故任意同日时刻等价；preset to=now 下桶内时刻
    /// 不可能晚于已落盘解析时刻，同样精确）。
    pub first_ts: i64,
    pub tokens_input: i64,
    pub tokens_output: i64,
    pub tokens_reasoning: i64,
    pub tokens_cache_read: i64,
    pub tokens_cache_write: i64,
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

/// usage 五维映射（S2；缺字段按 0——防御式）。
type Usage5 = (i64, i64, i64, i64, i64); // input, output, reasoning, cache_read, cache_write

/// 会话增量解析器状态（task-pulsepet-v2-polish #11 方案 α）：一遍行扫描的
/// 全部累积态。跨多次 append 续算——「全量 = 从 offset 0 一口气 feed」与
/// 「增量 = 分多批 feed」对同一字节流逐字段等价（行级状态机，无跨行回看）。
#[derive(Debug, Default, Clone)]
pub struct SessionState {
    /// message.id → (末条 usage, 该行 timestamp)（S3 去重覆盖；§14 起值携带
    /// 行 ts——去重语义不变，末条覆盖时 ts 一并被末条替换，分桶用）。
    usage_by_key: HashMap<String, (Usage5, Option<i64>)>,
    /// id/uuid 皆缺的独立计入行序号（P3-4）。
    line_seq: u64,
    first_ts: Option<i64>,
    last_ts: Option<i64>,
    /// 末条 assistant 行 timestamp（N-1 护栏口径）。
    last_assistant_ts: Option<i64>,
    model_id: Option<String>,
    title: Option<String>,
    project_name: Option<String>,
    assistant_seen: bool,
}

/// 喂入一批**完整行**（不含换行符；半行由调用方截掉留到下次）。
/// 行为与原 parse_session 循环体逐字一致（增量等价性的根基）。
fn feed_lines(state: &mut SessionState, text: &str) {
    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let Ok(obj) = serde_json::from_str::<serde_json::Value>(line) else {
            continue; // 坏行/非 JSON：跳过不崩
        };
        // 时间戳：任何含 timestamp 的行（事件行；非事件行无 ts，P1-1）
        let line_ts = obj
            .get("timestamp")
            .and_then(|v| v.as_str())
            .and_then(parse_timestamp_ms);
        if let Some(ts) = line_ts {
            if state.first_ts.is_none() {
                state.first_ts = Some(ts);
            }
            state.last_ts = Some(ts);
        }
        // cwd：首条含非空 cwd 的行 → basename（P2-6）
        if state.project_name.is_none() {
            if let Some(cwd) = obj.get("cwd").and_then(|v| v.as_str()) {
                if !cwd.trim().is_empty() {
                    state.project_name = Path::new(cwd)
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
                        state.line_seq += 1;
                        format!("\u{0}line-{}", state.line_seq)
                    });
                // 按行序取末条：直接覆盖（S3）；ts 随 usage 同行同源携带（§14）
                let usage = usage5_of(message);
                state.usage_by_key.insert(key, (usage, line_ts));
                state.assistant_seen = true;
                // 末条 assistant 行 timestamp（N-1 护栏口径）
                if let Some(ts) = line_ts {
                    state.last_assistant_ts = Some(ts);
                }
                // model 取最后一条 message.model（纯字符串）
                if let Some(m) = message.and_then(|m| m.get("model")).and_then(|v| v.as_str()) {
                    if !m.is_empty() {
                        state.model_id = Some(m.to_string());
                    }
                }
            }
            "user" => {
                // 标题：首条 user 且 content 为 string 的行截断（chars 按字符，P3-13）
                if state.title.is_none() {
                    if let Some(content) = obj
                        .get("message")
                        .and_then(|m| m.get("content"))
                        .and_then(|v| v.as_str())
                    {
                        let trimmed = content.trim();
                        if !trimmed.is_empty() {
                            state.title = Some(trimmed.chars().take(60).collect());
                        }
                    }
                }
            }
            _ => {} // 未知行类型跳过（防御式）
        }
    }
}

/// 状态 → 会话行（assistant_seen=false → None）。
/// §14：求和循环同时按 `local_day_label(ts)` 分桶产出 by_day 明细（BTreeMap
/// 保 day 字典序 → 升序确定性）；HashMap 值迭代无序，但加法交换律保证五维
/// 总量与桶内和均确定，桶 `first_ts` 取**桶内最小消息时刻**（tester P3-1：
/// 取迭代首遇值会随 HashMap 实例随机序漂移——同日多消息时值级不确定）。
/// ts 缺失的条目兜底归会话 time_updated（last_ts）日——防御口径（真实
/// assistant 行均带 ts）；两者皆无则不进 by_day（仍计入会话总量，与 day
/// 视图跳过无 ts 行的现状一致）。
fn finalize_state(state: &SessionState, session_id: &str) -> Option<CcSessionRow> {
    if !state.assistant_seen {
        return None;
    }
    let mut sum = (0i64, 0i64, 0i64, 0i64, 0i64);
    // day → (first_ts=桶内最早消息时刻, 五维和)
    let mut buckets: std::collections::BTreeMap<String, (i64, i64, i64, i64, i64, i64)> =
        std::collections::BTreeMap::new();
    for (u, ts) in state.usage_by_key.values() {
        sum.0 += u.0;
        sum.1 += u.1;
        sum.2 += u.2;
        sum.3 += u.3;
        sum.4 += u.4;
        let effective_ts = ts.or(state.last_ts);
        if let Some(label) = effective_ts.and_then(local_day_label) {
            let t = effective_ts.unwrap();
            let e = buckets.entry(label).or_insert((t, 0, 0, 0, 0, 0));
            if t < e.0 {
                e.0 = t; // 同日多条消息 → 取最早（确定性，与 HashMap 迭代序无关）
            }
            e.1 += u.0;
            e.2 += u.1;
            e.3 += u.2;
            e.4 += u.3;
            e.5 += u.4;
        }
    }
    let by_day: Vec<CcDayUsage> = buckets
        .into_iter()
        .map(|(day, (first_ts, i, o, r, cr, cw))| CcDayUsage {
            day,
            first_ts,
            tokens_input: i,
            tokens_output: o,
            tokens_reasoning: r,
            tokens_cache_read: cr,
            tokens_cache_write: cw,
        })
        .collect();
    let title = state
        .title
        .clone()
        .unwrap_or_else(|| session_id.chars().take(8).collect());
    Some(CcSessionRow {
        session_id: session_id.to_string(),
        cost: 0.0,
        tokens_input: sum.0,
        tokens_output: sum.1,
        tokens_reasoning: sum.2,
        tokens_cache_read: sum.3,
        tokens_cache_write: sum.4,
        by_day,
        time_created: state.first_ts,
        time_updated: state.last_ts,
        model_id: state.model_id.clone(),
        project_name: state.project_name.clone(),
        title,
        last_assistant_ts: state.last_assistant_ts,
    })
}

/// 单文件解析（坏行/空文件/非 JSON 行跳过不崩；无 assistant 行 → None）。
/// 方案 α 起口径统一为「只解析以换行符结束的完整行」（与增量路径一致；
/// CC 正在写的半行不入账——jsonl 语义，逐字段等价的前提）。
/// 生产路径已全量走 CacheEntry 增量链路（parse_file_full/increment），
/// 本函数仅测试使用（task-pulsepet-v2-polish R1 追加：cfg(test) 清 release
/// 档 dead_code 警告）。
#[cfg(test)]
pub fn parse_session(path: &Path) -> Option<CcSessionRow> {
    let bytes = std::fs::read(path).ok()?;
    let session_id = session_id_of(path);
    let (state, _) = feed_complete_lines(SessionState::default(), &bytes)?;
    finalize_state(&state, &session_id)
}

/// 文件名 stem → sessionId。
fn session_id_of(path: &Path) -> String {
    path.file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_else(|| "unknown".into())
}

/// 完整行口径喂入：只处理到最后一个 `\n`（含），返回推进后的状态与新偏移。
/// 无任何完整行 → None（半行/空文件留到下次）。
fn feed_complete_lines(mut state: SessionState, bytes: &[u8]) -> Option<(SessionState, u64)> {
    let last_nl = bytes.iter().rposition(|&b| b == b'\n')?;
    let text = std::str::from_utf8(&bytes[..=last_nl]).ok()?; // 非 UTF-8 → None（回退防御）
    feed_lines(&mut state, text);
    Some((state, last_nl as u64 + 1))
}

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

/// 单文件缓存条目（方案 α）：`(mtime, size)` 失效判定 + 已解析字节偏移 +
/// 增量解析器状态 + 结果（row=None 为负缓存——解析过但无 assistant 行，
/// 不再每次重试；后续 append 出现 assistant 行可从状态续算转正）。
#[derive(Debug, Clone)]
pub struct CacheEntry {
    pub mtime: SystemTime,
    pub size: u64,
    /// 已解析到的字节偏移（只推进到最后一个完整换行符 +1；半行留到下次）。
    pub offset: u64,
    /// 文件对象身份（unix=inode / windows=creation_time；None=不可用）。
    /// append 不变、tmp+rename 重写必变——「变长但前缀已换」的重写文件
    /// 靠它识破并回退全量，防增量拼接出错误数据。
    pub file_id: u64,
    /// 增量续算状态（下次 append 从 offset 续）。
    pub state: SessionState,
    /// 解析结果（None = 负缓存）。
    pub row: Option<CcSessionRow>,
}

#[derive(Debug, Default)]
pub struct TranscriptCache {
    /// PathBuf → 缓存条目；mtime+size+file_id 未变直接复用（S7）。
    /// mtime 用 SystemTime 纳秒精度（CC 原子写 tmp+rename 可能落在同一毫秒内，
    /// 毫秒精度会漏失效——R4）。
    pub entries: HashMap<PathBuf, CacheEntry>,
    /// sessionId → PathBuf（P2-2：idle hook 只有 (agent, session_id)）。
    pub index: HashMap<String, PathBuf>,
    /// 方案 α：锁外刷新进行中标记（plan 置位 / commit 清除；后来者让路用旧
    /// 快照）。持有起始时刻：execute 线程 panic 残留的 stale 标记超过 TTL 由
    /// 后来者接管（写回幂等，双写无害）。
    pub refresh_in_flight: Option<std::time::Instant>,
}

/// in-flight 标记的 stale 判定窗口（execute 异常残留的兜底接管时限）。
const REFRESH_STALE_AFTER: std::time::Duration = std::time::Duration::from_secs(30);

fn mtime_of(meta: &std::fs::Metadata) -> SystemTime {
    meta.modified().unwrap_or(UNIX_EPOCH)
}

/// 文件对象身份（unix inode / windows creation_time 近似；拿不到 → 0）。
/// 同一文件 append 身份不变；tmp+rename 落位的新文件身份不同。
fn file_id_of(meta: &std::fs::Metadata) -> u64 {
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        meta.ino()
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        meta.creation_time()
    }
    #[cfg(not(any(unix, windows)))]
    {
        0
    }
}

/// 锁外解析任务（plan 阶段产出，execute 阶段锁外执行）。
#[derive(Debug)]
enum ParseTask {
    /// 全量（新文件 / 变小 / mtime 变而 size 未变 / 身份变了）。
    Full { path: PathBuf },
    /// 增量：从 offset 续算（append-only 增长）。
    /// `expect_file_id` = plan 时该文件的 inode/creation_time——execute 读尾
    /// 后复核，不符（plan→execute 窗口内被 tmp+rename 重写）则放弃增量回退
    /// 全量，防新文件尾部拼进旧状态（tester P3-2）。
    Incr {
        path: PathBuf,
        offset: u64,
        state: SessionState,
        expect_file_id: u64,
    },
}

/// 锁内判定的刷新计划（task-pulsepet-v2-polish #11 方案 α）。
pub struct RefreshPlan {
    tasks: Vec<ParseTask>,
}

/// 锁外解析产物：path → 新缓存条目（含解析后实测 mtime/size）。
pub struct ParsedFile {
    path: PathBuf,
    entry: CacheEntry,
}

impl RefreshPlan {
    /// 锁外执行全部解析任务（I/O + JSON 解析不持锁）。
    fn execute(self) -> Vec<ParsedFile> {
        self.tasks.into_iter().map(run_task).collect()
    }
}

/// 单任务执行：读文件 → 完整行口径解析 → 解析后实测 (mtime,size) 入条目。
/// 全量失败（读不了/非 UTF-8）→ 负缓存条目（mtime/size 用实测值，state 空）。
/// 增量执行中文件被截断（读后实测 size < 起始 offset）或 file_id 与 plan 时
/// 不符（窗口内被重写）→ 就地回退全量。
fn run_task(task: ParseTask) -> ParsedFile {
    match task {
        ParseTask::Full { path } => parse_file_full(&path),
        ParseTask::Incr {
            path,
            offset,
            state,
            expect_file_id,
        } => match parse_file_incr(&path, offset, state, expect_file_id) {
            Some(entry) => ParsedFile { path, entry },
            None => parse_file_full(&path),
        },
    }
}

/// 全量解析：从头读整个文件，只处理完整行。
fn parse_file_full(path: &Path) -> ParsedFile {
    let bytes = std::fs::read(path).unwrap_or_default();
    let session_id = session_id_of(path);
    let (state, offset) = feed_complete_lines(SessionState::default(), &bytes)
        .unwrap_or((SessionState::default(), 0));
    let row = finalize_state(&state, &session_id);
    let (mtime, size, file_id) = stat3(path);
    ParsedFile {
        path: path.to_path_buf(),
        entry: CacheEntry {
            mtime,
            size,
            offset,
            file_id,
            state,
            row,
        },
    }
}

/// 增量解析：seek 到 offset 只读尾部新增字节（旧字节不再读），喂完整行。
/// 返回 None 表示应回退全量，触发条件（tester P3-2）：
/// 读失败 / 非 UTF-8 / 读后实测文件已缩到 offset 之下（窗口内截断）/
/// 实测 file_id 与 plan 时的期望不符（窗口内 tmp+rename 重写——只查 size
/// 挡不住"重写且更长"，尾部会拼进旧状态）。
fn parse_file_incr(
    path: &Path,
    offset: u64,
    mut state: SessionState,
    expect_file_id: u64,
) -> Option<CacheEntry> {
    use std::io::{Read, Seek, SeekFrom};
    let mut f = std::fs::File::open(path).ok()?;
    f.seek(SeekFrom::Start(offset)).ok()?;
    let mut tail = Vec::new();
    f.read_to_end(&mut tail).ok()?;
    let (new_state, advanced) = feed_complete_lines(state, &tail)?;
    state = new_state;
    let new_offset = offset + advanced;
    let (mtime, size, file_id) = stat3(path);
    if size < new_offset {
        // 锁外期间文件被截断/重写 → 本次结果作废，交回全量
        return None;
    }
    if file_id != expect_file_id {
        // plan→execute 窗口内文件对象已被替换（tmp+rename 重写）→ 增量状态
        // 与新内容前缀无继承关系，作废交回全量（entry 由全量路径记新 file_id）
        return None;
    }
    let row = finalize_state(&state, &session_id_of(path));
    Some(CacheEntry {
        mtime,
        size,
        offset: new_offset,
        file_id,
        state,
        row,
    })
}

/// (mtime, size, file_id)；stat 失败 → (UNIX_EPOCH, 0, 0)。
fn stat3(path: &Path) -> (SystemTime, u64, u64) {
    match std::fs::metadata(path) {
        Ok(m) => (mtime_of(&m), m.len(), file_id_of(&m)),
        Err(_) => (UNIX_EPOCH, 0, 0),
    }
}

impl TranscriptCache {
    /// 全目录扫描 + 缓存刷新（单线程便捷路径：plan → execute → commit 一气呵成，
    /// 语义与 v2-m5 相同；并发场景用 [`refresh_unlocked`]）。
    /// 增量口径：append-only 增长的文件从已记录偏移只读尾部新增行；
    /// 变小 / mtime 变而 size 未变 / 文件身份变了 → 全量重解析。
    /// 生产调用方已全走 refresh_unlocked（token_stats 三入口）；本方法仅
    /// 测试使用（task-pulsepet-v2-polish R1 追加：cfg(test) 清 release 档
    /// dead_code 警告）。
    #[cfg(test)]
    pub fn refresh(&mut self, dir: &Path) -> Vec<CcSessionRow> {
        let Some(plan) = self.plan_refresh(dir) else {
            return self.snapshot_rows();
        };
        let parsed = plan.execute();
        self.commit_refresh(parsed)
    }

    /// 锁内①：扫描清单 + (mtime,size,file_id) 轻量对比 + in-flight 标记。
    /// Some(plan) → 调用方锁外 `execute` 后 `commit_refresh` 写回；
    /// None → 已有刷新进行中（调用方直接 `snapshot_rows` 用旧数据）。
    pub fn plan_refresh(&mut self, dir: &Path) -> Option<RefreshPlan> {
        if let Some(t0) = self.refresh_in_flight {
            if t0.elapsed() < REFRESH_STALE_AFTER {
                return None; // 进行中 → 让路（旧快照）
            }
            // stale（execute 线程 panic 残留）→ 接管（写回幂等，双写无害）
        }
        self.refresh_in_flight = Some(std::time::Instant::now());
        let files = transcript_scan(dir);
        let seen: std::collections::HashSet<PathBuf> = files.iter().cloned().collect();
        let mut tasks = Vec::new();
        for f in &files {
            let meta = std::fs::metadata(f).ok();
            let (mtime, size, file_id) = meta
                .as_ref()
                .map(|m| (mtime_of(m), m.len(), file_id_of(m)))
                .unwrap_or((UNIX_EPOCH, 0, 0));
            if let Some(e) = self.entries.get(f) {
                let unchanged = e.mtime == mtime && e.size == size && e.file_id == file_id;
                if unchanged {
                    continue; // 复用缓存
                }
                let grew = size > e.offset && file_id == e.file_id;
                if grew {
                    // append-only 增长 → 增量（只读尾部；携带 plan 时 file_id，
                    // execute 端复核防窗口内重写拼接）
                    tasks.push(ParseTask::Incr {
                        path: f.clone(),
                        offset: e.offset,
                        state: e.state.clone(),
                        expect_file_id: e.file_id,
                    });
                } else {
                    // 变小（截断/重写）、原地改写（mtime 变 size 未变）、
                    // tmp+rename 换了文件对象（更长也全量，防拼接错数据）
                    tasks.push(ParseTask::Full { path: f.clone() });
                }
            } else {
                tasks.push(ParseTask::Full { path: f.clone() });
            }
        }
        // 消失的文件移除缓存与索引（轻量，锁内完成）
        self.entries.retain(|p, _| seen.contains(p));
        self.index.retain(|_, p| seen.contains(p));
        Some(RefreshPlan { tasks })
    }

    /// 锁内③：写回解析结果 + 清 in-flight + 返回全部会话行（时间倒序）。
    pub fn commit_refresh(&mut self, parsed: Vec<ParsedFile>) -> Vec<CcSessionRow> {
        for pf in parsed {
            if let Some(row) = &pf.entry.row {
                self.index.insert(row.session_id.clone(), pf.path.clone());
            }
            self.entries.insert(pf.path, pf.entry);
        }
        self.refresh_in_flight = None;
        self.snapshot_rows()
    }

    /// 收集全部会话行快照（时间倒序；in-flight 让路路径共用）。
    pub fn snapshot_rows(&self) -> Vec<CcSessionRow> {
        let mut rows: Vec<CcSessionRow> = self
            .entries
            .values()
            .filter_map(|e| e.row.clone())
            .collect();
        rows.sort_by(|a, b| b.time_updated.cmp(&a.time_updated));
        rows
    }

    /// 经 sessionId 索引定位文件并取会话行（单线程便捷路径；并发场景用
    /// [`find_session_unlocked`]）。索引缺失（首查/idle 先于查询）→ refresh
    /// 补建后取。无 → None。
    /// 生产调用方（build_cc_idle_report）已走 find_session_unlocked；本方法
    /// 仅测试使用（task-pulsepet-v2-polish R1 追加：cfg(test) 清 release 档
    /// dead_code 警告）。
    #[cfg(test)]
    pub fn find_session(&mut self, dir: &Path, session_id: &str) -> Option<CcSessionRow> {
        let path = match self.index.get(session_id).cloned() {
            Some(p) => p,
            None => {
                self.refresh(dir);
                self.index.get(session_id).cloned()?
            }
        };
        // 命中文件单点校验（mtime,size,file_id 未变直接复用）
        let meta = std::fs::metadata(&path).ok();
        let (mtime, size, file_id) = meta
            .as_ref()
            .map(|m| (mtime_of(m), m.len(), file_id_of(m)))
            .unwrap_or((UNIX_EPOCH, 0, 0));
        if let Some(e) = self.entries.get(&path) {
            if e.mtime == mtime && e.size == size && e.file_id == file_id {
                return e.row.clone();
            }
        }
        let pf = run_task(ParseTask::Full { path });
        let row = pf.entry.row.clone();
        if let Some(r) = &row {
            self.index.insert(r.session_id.clone(), pf.path.clone());
        }
        self.entries.insert(pf.path, pf.entry);
        row
    }
}

/// 并发路径的锁获取（poison 容忍，与库内惯例一致）。
fn lock_cache(cache: &Arc<Mutex<TranscriptCache>>) -> std::sync::MutexGuard<'_, TranscriptCache> {
    cache.lock().unwrap_or_else(|p| p.into_inner())
}

/// 锁外刷新（方案 α 主入口，task-pulsepet-v2-polish #11）：
/// ① 锁内轻量判定（清单 + mtime/size/file_id 对比 + in-flight 标记）→
/// ② 锁外 I/O 与解析（增量：只读尾部新增行）→ ③ 锁内写回。
/// **并发策略**：刷新进行中（in-flight）时后来者不等待——直接用现有缓存
/// 快照返回（旧数据；查询驱动懒解析下，下一次查询自然拿到新数据）。
/// 全目录并行解析**不做**（全量仅启动一次发生，且本函数已在
/// spawn_blocking 后台线程，收益不抵复杂度——任务定案）。跨重启仍全量一次
/// （内存缓存固有；β 落库方案留作数据量真大时演进方向）。
/// 锁为 PulsePet 进程内内存锁，与 CC 写文件无任何相互影响。
pub fn refresh_unlocked(dir: &Path, cache: &Arc<Mutex<TranscriptCache>>) -> Vec<CcSessionRow> {
    let plan = {
        let mut c = lock_cache(cache);
        match c.plan_refresh(dir) {
            Some(p) => p,
            None => return c.snapshot_rows(), // in-flight → 旧快照让路
        }
    };
    let parsed = plan.execute(); // 锁外：I/O + 解析
    let mut c = lock_cache(cache);
    c.commit_refresh(parsed)
}

/// 并发路径的 sessionId 定位（idle 汇报用）：
/// 索引命中且未变 → 直接给行；命中但文件变化 → 单文件任务锁外解析；
/// 索引缺失 → [`refresh_unlocked`] 全目录补建后取。
pub fn find_session_unlocked(
    dir: &Path,
    cache: &Arc<Mutex<TranscriptCache>>,
    session_id: &str,
) -> Option<CcSessionRow> {
    // ① 锁内：索引定位 + 轻量判定
    enum Step {
        Hit(Option<CcSessionRow>),
        Task(ParseTask),
        Miss,
    }
    let step = {
        let c = lock_cache(cache);
        match c.index.get(session_id).cloned() {
            Some(path) => {
                let meta = std::fs::metadata(&path).ok();
                let (mtime, size, file_id) = meta
                    .as_ref()
                    .map(|m| (mtime_of(m), m.len(), file_id_of(m)))
                    .unwrap_or((UNIX_EPOCH, 0, 0));
                match c.entries.get(&path) {
                    Some(e) if e.mtime == mtime && e.size == size && e.file_id == file_id => {
                        Step::Hit(e.row.clone())
                    }
                    Some(e) if size > e.offset && file_id == e.file_id => Step::Task(ParseTask::Incr {
                        path,
                        offset: e.offset,
                        state: e.state.clone(),
                        expect_file_id: e.file_id,
                    }),
                    _ => Step::Task(ParseTask::Full { path }),
                }
            }
            None => Step::Miss,
        }
    };
    match step {
        Step::Hit(row) => row,
        Step::Task(task) => {
            // ② 锁外：单文件解析（增量或全量）
            let pf = run_task(task);
            // ③ 锁内：写回 + 返回
            let mut c = lock_cache(cache);
            let row = pf.entry.row.clone();
            if let Some(r) = &row {
                c.index.insert(r.session_id.clone(), pf.path.clone());
            }
            c.entries.insert(pf.path, pf.entry);
            row
        }
        Step::Miss => {
            refresh_unlocked(dir, cache);
            let c = lock_cache(cache);
            c.index
                .get(session_id)
                .and_then(|p| c.entries.get(p))
                .and_then(|e| e.row.clone())
        }
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
        // 本地口径断言：日标签 = chrono Local 日期（非零偏移时区下自然覆盖
        // 「与 UTC 日期跨日」转换路径——如 UTC+8 下 16:30Z = 次日 00:30）
        //
        // task-pulsepet-v2-polish #9：原「assert_ne!(本地日, UTC日)」硬假设
        // 本机时区非零偏移（TZ=UTC 环境必红）已移除——本地口径语义已由上方
        // Local/SQLite oracle 双侧对账钉住（label ≡ Local 日期 ≡ localtime）；
        // 不做 TZ 注入（chrono Local 与 SQLite localtime 对 TZ env 的重读
        // 行为均有平台差异，注入会引入新的不稳定）。
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

    // ---- 方案 α（task-pulsepet-v2-polish #11）：增量偏移解析 + 锁外解析钉子 ----

    use std::io::Write as _;
    use std::sync::{Arc, Mutex};

    fn append_line(path: &Path, line: &serde_json::Value) {
        let mut f = std::fs::OpenOptions::new()
            .append(true)
            .create(true)
            .open(path)
            .unwrap();
        f.write_all(serde_json::to_string(line).unwrap().as_bytes())
            .unwrap();
        f.write_all(b"\n").unwrap();
    }

    fn append_partial(path: &Path, bytes: &[u8]) {
        let mut f = std::fs::OpenOptions::new()
            .append(true)
            .create(true)
            .open(path)
            .unwrap();
        f.write_all(bytes).unwrap();
    }

    /// 钉子①：多文件多轮 append 后，增量缓存与「独立全新全量解析」逐字段一致
    ///（含 message.id 去重覆盖语义、负缓存文件转正、顶层散落文件）。
    #[test]
    fn alpha_incremental_matches_full_reparse() {
        let dir = temp_dir("alpha-eq");
        let proj = dir.join("proj");
        std::fs::create_dir_all(&proj).unwrap();
        let f1 = proj.join("11111111-1111-2222-3333-444444444444.jsonl");
        let f2 = dir.join("22222222-1111-2222-3333-444444444444.jsonl"); // 顶层散落
        let ts = "2026-08-24T07:03:35.156Z";
        let mut cache = TranscriptCache::default();
        // 轮 0：f1 含同 message.id 双行（覆盖语义）+ user 标题；f2 无 assistant 行（负缓存）
        write_lines(
            &f1,
            &[
                assistant_line(Some("m1"), Some("u1"), ts, usage5(100, 1, 0, 0, 0)),
                assistant_line(Some("m1"), Some("u1b"), ts, usage5(111, 2, 0, 0, 0)),
                json!({"type": "user", "timestamp": ts, "message": {"role": "user", "content": "标题甲"}}),
            ],
        );
        write_lines(
            &f2,
            &[json!({"type": "user", "message": {"content": "无 assistant 行"}})],
        );
        let _ = cache.refresh(&dir);
        // 轮 1~3：交替 append（增量路径）
        for i in 0..3 {
            append_line(
                &f1,
                &assistant_line(Some(&format!("mx{i}")), None, ts, usage5(10 + i, 0, 0, 1, 0)),
            );
            if i == 1 {
                // f2 后来才出现 assistant 行：负缓存 → 增量续算转正
                append_line(&f2, &assistant_line(Some("f2m"), None, ts, usage5(7, 0, 0, 0, 0)));
            }
            let _ = cache.refresh(&dir);
        }
        // 对账：独立全新缓存全量解析 vs 增量缓存
        //（两行同 time_updated 时 sort_by 稳定序受 HashMap 迭代序影响，
        // 对比前按 session_id 归一排序——逐字段对账不受快照顺序干扰）
        let mut fresh = TranscriptCache::default();
        let mut full = fresh.refresh(&dir);
        let mut incr = cache.refresh(&dir);
        full.sort_by(|a, b| a.session_id.cmp(&b.session_id));
        incr.sort_by(|a, b| a.session_id.cmp(&b.session_id));
        assert_eq!(incr.len(), 2);
        assert_eq!(incr, full, "增量结果与全量解析逐字段一致");
        // 去重覆盖语义抽查（m1 取末条 111）
        let f1_row = incr.iter().find(|r| r.session_id.starts_with("11111111")).unwrap();
        assert_eq!(f1_row.tokens_input, 111 + 10 + 11 + 12);
    }

    /// 钉子②：append 尾部新增行走增量（旧字节不再读），结果正确、偏移推进。
    #[test]
    fn alpha_append_tail_incremental_parse() {
        let dir = temp_dir("alpha-append");
        let f = dir.join("aaaaaaaa-3333-2222-3333-444444444444.jsonl");
        write_lines(
            &f,
            &[assistant_line(
                Some("m1"),
                Some("u1"),
                "2026-08-24T07:03:35.156Z",
                usage5(100, 0, 0, 0, 0),
            )],
        );
        let mut cache = TranscriptCache::default();
        let rows = cache.refresh(&dir);
        assert_eq!(rows[0].tokens_input, 100);
        assert_eq!(
            cache.entries[&f].offset,
            std::fs::metadata(&f).unwrap().len(),
            "全量解析后偏移 = 文件长度"
        );
        append_line(
            &f,
            &assistant_line(
                Some("m2"),
                None,
                "2026-08-24T07:04:35.156Z",
                usage5(50, 5, 0, 0, 0),
            ),
        );
        let rows2 = cache.refresh(&dir);
        assert_eq!(rows2[0].tokens_input, 150, "尾部增量入账");
        assert_eq!(rows2[0].tokens_output, 5);
        assert_eq!(
            rows2[0].time_updated,
            parse_timestamp_ms("2026-08-24T07:04:35.156Z")
        );
        assert_eq!(
            cache.entries[&f].offset,
            std::fs::metadata(&f).unwrap().len(),
            "增量后偏移推进到文件末"
        );
    }

    /// 钉子③：CC 正在写的半行不入账、偏移不推进；补完换行后下次补读。
    #[test]
    fn alpha_offset_advances_only_to_complete_line() {
        let dir = temp_dir("alpha-halfline");
        let f = dir.join("bbbbbbbb-3333-2222-3333-444444444444.jsonl");
        let ts = "2026-08-24T07:03:35.156Z";
        write_lines(&f, &[assistant_line(Some("m1"), Some("u1"), ts, usage5(100, 0, 0, 0, 0))]);
        let mut cache = TranscriptCache::default();
        cache.refresh(&dir);
        let offset0 = cache.entries[&f].offset;
        // 半行：合法 JSON 前缀、无换行（CC 正在写）
        let half = serde_json::to_string(&assistant_line(Some("m2"), None, ts, usage5(500, 0, 0, 0, 0)))
            .unwrap();
        append_partial(&f, half.as_bytes());
        let rows = cache.refresh(&dir);
        assert_eq!(rows[0].tokens_input, 100, "半行不入账");
        assert_eq!(cache.entries[&f].offset, offset0, "偏移不推进（无完整换行）");
        // 补完换行 → 下次补读
        append_partial(&f, b"\n");
        let rows2 = cache.refresh(&dir);
        assert_eq!(rows2[0].tokens_input, 600, "补完换行后整行入账");
        assert_eq!(cache.entries[&f].offset, std::fs::metadata(&f).unwrap().len());
    }

    /// 钉子④：文件变小（重写/截断，size < 已记录偏移）→ 回退全量重解析。
    #[test]
    fn alpha_shrunk_file_falls_back_to_full_reparse() {
        let dir = temp_dir("alpha-shrink");
        let f = dir.join("cccccccc-3333-2222-3333-444444444444.jsonl");
        let ts = "2026-08-24T07:03:35.156Z";
        write_lines(
            &f,
            &[
                assistant_line(Some("m1"), None, ts, usage5(300, 0, 0, 0, 0)),
                assistant_line(Some("m2"), None, ts, usage5(30, 0, 0, 0, 0)),
                assistant_line(Some("m3"), None, ts, usage5(3, 0, 0, 0, 0)),
            ],
        );
        let mut cache = TranscriptCache::default();
        assert_eq!(cache.refresh(&dir)[0].tokens_input, 333);
        // 重写为更短的不同内容（mtime/size 均变，size < offset）
        write_lines(&f, &[assistant_line(Some("m9"), None, ts, usage5(9, 0, 0, 0, 0))]);
        let rows = cache.refresh(&dir);
        assert_eq!(rows[0].tokens_input, 9, "变小回退全量（非增量拼接）");
        assert_eq!(rows[0].title, "cccccccc");
        assert_eq!(cache.entries[&f].offset, std::fs::metadata(&f).unwrap().len());
    }

    /// 钉子⑤：锁外解析不阻塞并发查询（P3-3 加固为确定性构造）——手动拆分
    /// plan/execute/commit：B 的让路查询被钉死在「plan 已置 in-flight、execute
    /// 未开始」的确定窗口，消除原 sleep(150ms) 依赖 A 未完成的竞速面
    ///（A 若先完成则 B 拿新快照，b==20_000 断言翻车——tester P3-3）。
    /// B 语义达标 = in-flight 让路拿旧快照 + 未被长时间阻塞；execute 锁外
    /// 由 plan 返回时锁 guard 已 drop 的结构保证（B 能在任意非持锁时刻拿锁）。
    #[test]
    fn alpha_unlocked_refresh_does_not_block_concurrent_query() {
        let dir = temp_dir("alpha-conc");
        let f = dir.join("dddddddd-3333-2222-3333-444444444444.jsonl");
        let ts = "2026-08-24T07:03:35.156Z";
        // 预热：2 万行（旧数据快照来源；无 id/uuid → 每行独立计入，和 = 行数）
        let line_text = serde_json::to_string(&assistant_line(None, None, ts, usage5(1, 0, 0, 0, 0)))
            .unwrap();
        {
            let mut w = std::fs::File::create(&f).unwrap();
            for _ in 0..20_000 {
                writeln!(w, "{line_text}").unwrap();
            }
        }
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        let warm = refresh_unlocked(&dir, &cache);
        assert_eq!(warm.len(), 1);
        assert_eq!(warm[0].tokens_input, 20_000);
        // 增量解析量拉大（10 万行，~20MB）：execute 真实耗时顺带覆盖
        {
            let mut w = std::fs::OpenOptions::new().append(true).open(&f).unwrap();
            for _ in 0..100_000 {
                writeln!(w, "{line_text}").unwrap();
            }
        }
        // A①：plan（锁内轻量判定 + in-flight 置位后即释放锁）
        let plan = {
            let mut c = lock_cache(&cache);
            c.plan_refresh(&dir)
                .expect("无并发刷新在途，plan 必成功")
        };
        // B：in-flight 期间并发查询 → 确定性让路（旧快照 20_000）+ 不阻塞
        let t0 = std::time::Instant::now();
        let b_rows = refresh_unlocked(&dir, &cache);
        let b_elapsed = t0.elapsed();
        assert_eq!(b_rows.len(), 1);
        assert_eq!(b_rows[0].tokens_input, 20_000, "in-flight 让路 → 旧快照（确定性）");
        assert!(
            b_elapsed < std::time::Duration::from_millis(300),
            "并发查询不应被长时间阻塞: {b_elapsed:?}"
        );
        // A②：execute（锁外，不持 Mutex）→ A③：commit（锁内写回）
        let parsed = plan.execute();
        let a_rows = {
            let mut c = lock_cache(&cache);
            c.commit_refresh(parsed)
        };
        assert_eq!(a_rows.len(), 1);
        assert_eq!(a_rows[0].tokens_input, 120_000, "A 增量入账");
    }

    /// 补充：rename 落位「更长但前缀完全不同」的文件（tmp+rename 重写）——
    /// unix 下 inode 变 → 全量重解析，防增量拼接出错误数据。
    #[test]
    fn alpha_rewritten_longer_file_full_reparse() {
        let dir = temp_dir("alpha-rename-longer");
        let f = dir.join("eeeeeeee-3333-2222-3333-444444444444.jsonl");
        let ts = "2026-08-24T07:03:35.156Z";
        write_lines(&f, &[assistant_line(Some("m1"), None, ts, usage5(100, 0, 0, 0, 0))]);
        let mut cache = TranscriptCache::default();
        assert_eq!(cache.refresh(&dir)[0].tokens_input, 100);
        // tmp：不同内容且更长（若无身份防御，增量会读 [offset,..) 只得 50）
        let tmp = dir.join(".tmp-session");
        write_lines(
            &tmp,
            &[
                assistant_line(Some("n1"), None, ts, usage5(900, 0, 0, 0, 0)),
                assistant_line(Some("n2"), None, ts, usage5(50, 0, 0, 0, 0)),
            ],
        );
        std::fs::rename(&tmp, &f).unwrap();
        assert_eq!(cache.refresh(&dir)[0].tokens_input, 950, "重写更长 → 全量重解析");
    }

    /// 补充：find_session_unlocked（锁外单文件路径）索引未命中 → refresh 补建；
    /// 命中且文件变化 → 增量更新。
    #[test]
    fn alpha_find_session_unlocked_paths() {
        let dir = temp_dir("alpha-find");
        let f = dir.join("ffffffff-3333-2222-3333-444444444444.jsonl");
        let ts = "2026-08-24T07:03:35.156Z";
        write_lines(&f, &[assistant_line(Some("m1"), None, ts, usage5(100, 0, 0, 0, 0))]);
        let cache = Arc::new(Mutex::new(TranscriptCache::default()));
        // 索引未命中 → refresh 补建
        let row = find_session_unlocked(&dir, &cache, "ffffffff-3333-2222-3333-444444444444")
            .expect("scan 补建后命中");
        assert_eq!(row.tokens_input, 100);
        // 未知 id → None
        assert!(find_session_unlocked(&dir, &cache, "nope-nope").is_none());
        // append → 索引命中的单文件增量（锁外）
        append_line(&f, &assistant_line(Some("m2"), None, ts, usage5(33, 0, 0, 0, 0)));
        let row2 = find_session_unlocked(&dir, &cache, "ffffffff-3333-2222-3333-444444444444")
            .expect("命中且增量更新");
        assert_eq!(row2.tokens_input, 133);
    }

    /// P3-2 补钉（task-pulsepet-v2-polish R1 追加，tester 白盒建议）：plan→execute
    /// 毫秒窗口内文件被 tmp+rename 重写且更长——Incr 任务携带的期望 file_id
    /// 与实际不符 → 放弃增量、回退全量（不把新文件尾部拼进旧状态），
    /// entry 记新 file_id（此后 unchanged 判定用新身份，不持久化错数据）。
    /// 与钉子⑥（alpha_rewritten_longer_file_full_reparse）的区分：⑥测 plan
    /// 时已见新文件（锁内判定直接走 Full）；本钉子白盒模拟 plan 已拿旧
    /// (offset, state, file_id) 之后文件才被重写的窗口。
    #[test]
    fn alpha_incr_file_id_mismatch_in_window_falls_back_to_full() {
        let dir = temp_dir("alpha-fid");
        let f = dir.join("aaaaaaaa-4444-2222-3333-444444444444.jsonl");
        let ts = "2026-08-24T07:03:35.156Z";
        // 旧文件（一行 m1=100）→ refresh 建立带旧 file_id 的缓存条目
        write_lines(&f, &[assistant_line(Some("m1"), None, ts, usage5(100, 0, 0, 0, 0))]);
        let mut cache = TranscriptCache::default();
        cache.refresh(&dir);
        let entry = cache.entries[&f].clone();

        // 窗口模拟：plan 已持有旧 (offset, state, file_id)；此后重写且更长
        let tmp = dir.join(".tmp-session");
        write_lines(
            &tmp,
            &[
                assistant_line(Some("n1"), None, ts, usage5(900, 0, 0, 0, 0)),
                assistant_line(Some("n2"), None, ts, usage5(50, 0, 0, 0, 0)),
            ],
        );
        std::fs::rename(&tmp, &f).unwrap();

        // execute：Incr 读尾后发现 file_id 不符 → 回退全量
        let pf = run_task(ParseTask::Incr {
            path: f.clone(),
            offset: entry.offset,
            state: entry.state.clone(),
            expect_file_id: entry.file_id,
        });
        let row = pf.entry.row.as_ref().expect("回退全量后应有行");
        assert_eq!(row.tokens_input, 950, "窗口内重写 → 全量重解析（非增量拼接）");
        assert_eq!(
            pf.entry.offset,
            std::fs::metadata(&f).unwrap().len(),
            "offset 重置为新文件全量长度"
        );
        assert_ne!(
            pf.entry.file_id, entry.file_id,
            "entry 记新 file_id（防错数据经 unchanged 判定持久化）"
        );
    }

    // ---- §14（V2-OPEN-ITEMS，2026-08-29）：by_day 按消息时间归天 ----

    /// §14 钉①：单 jsonl 跨天两行 assistant（不同 message.id）→ by_day 两桶
    /// 各得各的；会话级五维总量 = 各桶之和（去重口径不变）。
    #[test]
    fn s14_by_day_buckets_cross_day_session() {
        let dir = temp_dir("s14-byday");
        let f = dir.join("12345678-1111-2222-3333-444444444444.jsonl");
        // 本地日标签经 sqlite oracle 对账（与实现同口径，防时区假设）
        let d0 = sqlite_day(parse_timestamp_ms("2026-08-28T04:00:00.000Z").unwrap());
        let d1 = sqlite_day(parse_timestamp_ms("2026-08-29T04:00:00.000Z").unwrap());
        write_lines(
            &f,
            &[
                json!({"type": "user", "timestamp": "2026-08-28T04:00:00.000Z",
                       "message": {"role": "user", "content": "跨天会话"}}),
                assistant_line(Some("m1"), Some("u1"), "2026-08-28T04:00:00.000Z",
                    usage5(100, 10, 0, 5, 0)),
                assistant_line(Some("m2"), Some("u2"), "2026-08-29T04:00:00.000Z",
                    usage5(200, 20, 1, 6, 0)),
            ],
        );
        let row = parse_session(&f).expect("应有行");
        assert_eq!(row.tokens_input, 300, "会话累计不变");
        assert_eq!(row.by_day.len(), 2, "跨天会话两桶（升序）");
        assert_eq!(row.by_day[0].day, d0);
        assert_eq!(row.by_day[0].tokens_input, 100);
        assert_eq!(row.by_day[0].tokens_output, 10);
        assert_eq!(row.by_day[0].tokens_cache_read, 5);
        assert_eq!(
            row.by_day[0].first_ts,
            parse_timestamp_ms("2026-08-28T04:00:00.000Z").unwrap()
        );
        assert_eq!(row.by_day[1].day, d1);
        assert_eq!(row.by_day[1].tokens_input, 200);
        assert_eq!(row.by_day[1].tokens_reasoning, 1);
        // 总量 = 各桶之和（同源同时产出，防两套口径漂移）
        assert_eq!(row.by_day.iter().map(|b| b.tokens_input).sum::<i64>(), row.tokens_input);
        assert_eq!(row.by_day.iter().map(|b| b.tokens_cache_read).sum::<i64>(), row.tokens_cache_read);
    }

    /// §14 钉②：去重先于分桶——同 message.id 双行跨天 → 末条覆盖（ts 随行
    /// 替换），by_day 只计末条那天。
    #[test]
    fn s14_dedup_precedes_day_bucketing() {
        let dir = temp_dir("s14-dedup");
        let f = dir.join("22345678-1111-2222-3333-444444444444.jsonl");
        let d1 = sqlite_day(parse_timestamp_ms("2026-08-29T04:00:00.000Z").unwrap());
        write_lines(
            &f,
            &[
                assistant_line(Some("m1"), Some("u1a"), "2026-08-28T04:00:00.000Z",
                    usage5(100, 0, 0, 0, 0)),
                assistant_line(Some("m1"), Some("u1b"), "2026-08-29T04:00:00.000Z",
                    usage5(150, 0, 0, 0, 0)),
            ],
        );
        let row = parse_session(&f).expect("应有行");
        assert_eq!(row.tokens_input, 150, "末条覆盖（S3 不变）");
        assert_eq!(row.by_day.len(), 1, "只计末条那天");
        assert_eq!(row.by_day[0].day, d1);
        assert_eq!(row.by_day[0].tokens_input, 150);
    }

    /// §14 钉③：assistant 行缺 timestamp 的兜底（真实数据不出现；防御口径
    /// 钉住）——归会话 time_updated（last_ts）日；两者皆无则不进 by_day
    ///（仍计入会话总量，与 day 视图跳过无 ts 行的现状一致）。
    #[test]
    fn s14_missing_ts_falls_back_to_session_time_updated() {
        let dir = temp_dir("s14-nots");
        let f = dir.join("32345678-1111-2222-3333-444444444444.jsonl");
        let d0 = sqlite_day(parse_timestamp_ms("2026-08-28T04:00:00.000Z").unwrap());
        // m1 带 ts（day0）；m2 无 ts → 兜底归 last_ts（= m1 的 day0）
        let m2_no_ts = json!({
            "type": "assistant",
            "message": {"id": "m2", "model": "deepseek-v4-pro",
                        "usage": usage5(50, 0, 0, 0, 0)},
        });
        write_lines(
            &f,
            &[
                assistant_line(Some("m1"), Some("u1"), "2026-08-28T04:00:00.000Z",
                    usage5(100, 0, 0, 0, 0)),
                m2_no_ts,
            ],
        );
        let row = parse_session(&f).expect("应有行");
        assert_eq!(row.tokens_input, 150);
        assert_eq!(row.by_day.len(), 1, "无 ts 行兜底归 time_updated 日");
        assert_eq!(row.by_day[0].day, d0);
        assert_eq!(row.by_day[0].tokens_input, 150);
        // 全员无 ts：by_day 空（不崩），会话总量照常
        let f2 = dir.join("42345678-1111-2222-3333-444444444444.jsonl");
        write_lines(
            &f2,
            &[json!({
                "type": "assistant",
                "message": {"id": "m1", "model": "deepseek-v4-pro",
                            "usage": usage5(70, 0, 0, 0, 0)},
            })],
        );
        let row2 = parse_session(&f2).expect("应有行");
        assert_eq!(row2.tokens_input, 70);
        assert!(row2.by_day.is_empty(), "皆无 ts → 不进 by_day");
    }

    /// §14 钉④（tester P3-1）：同日桶多条消息时 `first_ts` 取**最早**消息
    /// 时刻——与 HashMap 迭代序/文件行序无关（修复前取迭代首遇值，值级
    /// 随机漂移）。构造：晚时刻行在文件前部、早时刻行在后部。
    #[test]
    fn s14_same_day_bucket_first_ts_is_earliest() {
        let dir = temp_dir("s14-firstts");
        let f = dir.join("52345678-1111-2222-3333-444444444444.jsonl");
        let early = parse_timestamp_ms("2026-08-28T02:00:00.000Z").unwrap();
        write_lines(
            &f,
            &[
                assistant_line(Some("m-late"), Some("u1"), "2026-08-28T04:00:00.000Z",
                    usage5(10, 0, 0, 0, 0)),
                assistant_line(Some("m-early"), Some("u2"), "2026-08-28T02:00:00.000Z",
                    usage5(5, 0, 0, 0, 0)),
            ],
        );
        let row = parse_session(&f).expect("应有行");
        assert_eq!(row.by_day.len(), 1, "同日单桶");
        assert_eq!(row.by_day[0].first_ts, early, "first_ts = 桶内最早消息时刻（非行序/迭代序首遇）");
        assert_eq!(row.by_day[0].tokens_input, 15);
    }
}
