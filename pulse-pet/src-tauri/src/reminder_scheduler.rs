//! 提醒调度器（DESIGN §5，TC-RM-01~16）。
//!
//! - **tokio interval + 显式 `MissedTickBehavior::Skip`**（§5.1，TC-RM-02）：每 1 分钟
//!   tick（`PULSEPET_REMINDER_TICK_MS` 可调短供实测），系统睡眠唤醒后错过的不补发。
//! - **in-memory 倒计时**（TC-RM-07）：启动/CRUD 后从 `reminders` 表读一次，之后每
//!   tick 只查内存的 `next_due_ms`，不重读表；改设置经 command 通知 reload。
//! - **到点发送 Tauri event `reminder://trigger`**（payload 含 id/kind/label/
//!   use_fireworks/fireworks_global/log_id），前端决定渲染气泡还是烟花（§5.2/§5.3）。
//! - **跨午夜窗口**（§5.2，TC-RM-06）：`start_time > end_time` 视为跨日窗口，当前
//!   时刻在 `[start, 24:00) ∪ [00:00, end)` 内才触发；非跨日规则不受影响。
//! - **同规则 3 分钟不重复**（TC-RM-05）：`last_triggered_at` 判断（DEDUP_WINDOW_MS）。
//! - **全局暂停**（TC-RM-08）：托盘"暂停所有提醒"勾选态，持久化在 app_state
//!   （`reminders.paused`）；暂停期间到期规则不触发，倒计时顺延（恢复后不瞬间补弹）。
//! - **kind='todo' 语义预留**（§5.4）：`interval_minutes=0` 非周期、仅触发一次
//!   （触发后 next_due=MAX，重启/reload 不重复触发）；todo→reminders upsert 本体在 M7。
//! - **触发即写 `reminder_logs`**（TC-RM-13）：triggered_at 触发时写；acked_at +
//!   dismissed_via='bubble' 由前端点击确认回报（`reminders_ack`）；自动消失回报
//!   `reminders_dismiss(via='auto')`；烟花播放结束回报 via='fireworks'
//!   （`fireworks_finished`）。
//! - 时间戳格式：RFC3339 本地时间字符串（chrono），去重/倒计时比较用解析后的
//!   epoch 毫秒（`parse_rfc3339_ms`）。
//!
//! ## 烟花窗口编排（TC-RM-09/10）
//!
//! pet 窗口收到 `reminder://trigger` 且判定放烟花时 invoke `reminder_play_fireworks`：
//! Rust 计算 pet 中心点在 fireworks 窗口坐标系中的发射原点（物理像素 → 逻辑像素），
//! `emit_to("fireworks", "fireworks://play")` + show 窗口；前端播完（约 3.8s，硬上限
//! 5s）invoke `fireworks_finished` → Rust hide 窗口 + 记 dismissed_via='fireworks'。
//! Rust 侧另有 6.5s watchdog 兜底 hide（前端崩溃时不留常驻窗口）。首播竞态用
//! ready/pending 握手：fireworks 窗口挂载后 invoke `fireworks_ready`，未 ready 时
//! 的 play 请求存 pending，ready 到达即补发。

use std::sync::{Arc, Mutex};

use chrono::{DateTime, Local, NaiveDate, NaiveDateTime, SecondsFormat, TimeZone, Timelike};
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use tauri::{Emitter, Manager};

use crate::windows;

/// app_state key：全局烟花开关（"1"/"0"，默认关；TC-RM-11）。
pub const KEY_FIREWORKS_GLOBAL: &str = "reminders.fireworks_global";
/// app_state key：全局暂停（"1"/"0"，默认关；TC-RM-08）。
pub const KEY_PAUSED: &str = "reminders.paused";
/// 同规则去重窗口（TC-RM-05：3 分钟内不重复）。
pub const DEDUP_WINDOW_MS: i64 = 3 * 60_000;
/// 调度器 tick 周期（默认 1 分钟；`PULSEPET_REMINDER_TICK_MS` 可调短供实测）。
pub const DEFAULT_TICK_MS: u64 = 60_000;
/// upsert 允许的最大间隔（分钟，24h）。
pub const MAX_INTERVAL_MINUTES: i64 = 1440;

/// 触发事件 payload（前端 parseReminderTrigger 按同名字段消费）。
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct TriggerPayload {
    pub id: i64,
    pub kind: String,
    pub label: String,
    pub use_fireworks: bool,
    pub fireworks_global: bool,
    pub log_id: i64,
    /// M7（TC-TD-03）：kind='todo' 时携带截止时刻 epoch ms，前端按触发时刻
    /// 计算"还有 X 分钟要完成「任务名」"；非 todo 为 None。
    pub todo_due_ms: Option<i64>,
}

/// 烟花播放指令 payload（物理→逻辑像素换算后的 CSS 坐标，前端 ×dpr 进 canvas）。
/// `target` = 宠物当前所处显示器中轴线 + 屏高 0.3 处（DESIGN §5.3 绽放点定案）。
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct PlayPayload {
    pub log_id: i64,
    pub origin_x: f64,
    pub origin_y: f64,
    pub target_x: f64,
    pub target_y: f64,
}

/// 提醒规则（reminders 表行，DESIGN §5.4；serde 字段与 TS `ReminderRule` 一致）。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ReminderRule {
    pub id: i64,
    pub kind: String,
    pub label: String,
    pub interval_minutes: i64,
    pub start_time: Option<String>,
    pub end_time: Option<String>,
    pub enabled: bool,
    pub use_fireworks: bool,
    pub last_triggered_at: Option<String>,
    pub source_todo_id: Option<i64>,
    /// M7：todo 派生提醒的截止时刻（"YYYY-MM-DDTHH:MM"，= todos.due_date）。
    pub todo_due_at: Option<String>,
    pub created_at: String,
}

/// CRUD 入参（id 由 command 参数单独传）。
#[derive(Debug, Clone, Deserialize)]
pub struct ReminderInput {
    pub kind: String,
    pub label: String,
    pub interval_minutes: i64,
    pub start_time: Option<String>,
    pub end_time: Option<String>,
    pub enabled: bool,
    pub use_fireworks: bool,
}

/// 历史统计（TC-RM-13：按 kind 聚合 reminder_logs）。
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct ReminderStat {
    pub kind: String,
    pub today: i64,
    pub total: i64,
}

// ---------------------------------------------------------------------------
// 纯函数核心（单测主战场）
// ---------------------------------------------------------------------------

/// "HH:MM" → 当日分钟数（0-1439）；非法输入 None。
pub fn parse_hhmm(s: &str) -> Option<i64> {
    let (h, m) = s.trim().split_once(':')?;
    let h: i64 = h.parse().ok()?;
    let m: i64 = m.parse().ok()?;
    if !(0..=23).contains(&h) || !(0..=59).contains(&m) {
        return None;
    }
    Some(h * 60 + m)
}

/// 当前时刻是否在规则活跃窗口内（TC-RM-06）：
/// - 双空 → 全天；
/// - 仅 start → [start, 24:00)；
/// - 仅 end → [00:00, end)；
/// - start <= end → [start, end)；
/// - start > end（跨午夜，如 22:00-06:00）→ [start, 24:00) ∪ [00:00, end)。
pub fn in_window(minute_of_day: i64, start: Option<i64>, end: Option<i64>) -> bool {
    match (start, end) {
        (None, None) => true,
        (Some(s), None) => minute_of_day >= s,
        (None, Some(e)) => minute_of_day < e,
        (Some(s), Some(e)) => {
            if s <= e {
                minute_of_day >= s && minute_of_day < e
            } else {
                minute_of_day >= s || minute_of_day < e
            }
        }
    }
}

/// RFC3339 → epoch 毫秒。
pub fn parse_rfc3339_ms(s: &str) -> Option<i64> {
    DateTime::parse_from_rfc3339(s)
        .ok()
        .map(|d| d.timestamp_millis())
}

/// M7：todo 侧绝对时间解析——"YYYY-MM-DDTHH:MM"（todos.due_date / 派生
/// start_time 同格式）按**用户本地时区**折算 epoch 毫秒；"YYYY-MM-DD" 按
/// 当日 00:00 本地。解析失败 → None。
pub fn parse_due_like_ms(s: &str) -> Option<i64> {
    let s = s.trim();
    // 形状预检（chrono 对 %m/%d 等填充宽容，这里强制零填充规范形；
    // 与 TS 侧 validateTodoInput 同口径）
    let b = s.as_bytes();
    let shape_ok = (s.len() == 16
        && b[4] == b'-'
        && b[7] == b'-'
        && b[10] == b'T'
        && b[13] == b':')
        || (s.len() == 10 && b[4] == b'-' && b[7] == b'-');
    if !shape_ok || !b.iter().all(|c| c.is_ascii_digit() || *c == b'-' || *c == b'T' || *c == b':')
    {
        return None;
    }
    let local = if let Ok(dt) = NaiveDateTime::parse_from_str(s, "%Y-%m-%dT%H:%M") {
        Local.from_local_datetime(&dt)
    } else if let Ok(d) = NaiveDate::parse_from_str(s, "%Y-%m-%d") {
        Local.from_local_datetime(&d.and_hms_opt(0, 0, 0)?)
    } else {
        return None;
    };
    // DST 间隙/歧义时取首个可行解释（提醒场景可接受）
    local
        .single()
        .or_else(|| local.earliest())
        .map(|d| d.timestamp_millis())
}

/// 当前本地时间戳（RFC3339 毫秒精度）。
pub fn now_rfc3339() -> String {
    Local::now().to_rfc3339_opts(SecondsFormat::Millis, true)
}

/// 当前本地时刻的当日分钟数（窗口判定用）。
pub fn now_minute_of_day() -> i64 {
    let l = Local::now();
    l.hour() as i64 * 60 + l.minute() as i64
}

/// epoch 毫秒（复用 M3 的系统时钟语义）。
pub fn now_ms() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

/// 计算规则的 next_due（加载/reload 后）：
/// - `interval <= 0`（todo 一次性，M7/TC-TD-03/06）：
///     从未触发 → `start_time`（绝对时刻，"YYYY-MM-DDTHH:MM"；已过期则下一 tick
///   补触发一次）；已触发 → `i64::MAX`（永不再触发，跨重启/reload 均以
///   `last_triggered_at` 为唯一防重来源，§5.4）；
/// - 周期规则：anchor = last_triggered_at（缺省 created_at）+ interval；错过不补发
///   （cand 已过期则顺延到 now + interval，避免重启/停机后瞬间补弹，TC-RM-02 精神）。
pub fn compute_next_due(rule: &ReminderRule, now_ms: i64) -> i64 {
    let interval = rule.interval_minutes;
    if interval <= 0 {
        if rule
            .last_triggered_at
            .as_deref()
            .and_then(parse_rfc3339_ms)
            .is_some()
        {
            return i64::MAX;
        }
        // start_time 缺失（手工建的 todo 规则）→ 立即到期一次兜底
        return rule
            .start_time
            .as_deref()
            .and_then(parse_due_like_ms)
            .unwrap_or(now_ms);
    }
    let anchor = rule
        .last_triggered_at
        .as_deref()
        .and_then(parse_rfc3339_ms)
        .or_else(|| parse_rfc3339_ms(&rule.created_at))
        .unwrap_or(now_ms);
    let cand = anchor.saturating_add(interval.saturating_mul(60_000));
    if cand > now_ms {
        cand
    } else {
        now_ms.saturating_add(interval * 60_000)
    }
}

/// 同规则去重（TC-RM-05）：距上次触发 ≥3 分钟才允许再次触发。
pub fn dedup_ok(last_ms: Option<i64>, now_ms: i64) -> bool {
    match last_ms {
        None => true,
        Some(l) => now_ms.saturating_sub(l) >= DEDUP_WINDOW_MS,
    }
}

// ---------------------------------------------------------------------------
// 内存状态 + tick 决策
// ---------------------------------------------------------------------------

/// 单条规则的内存倒计时状态。
#[derive(Debug, Clone)]
pub struct RuleState {
    pub rule: ReminderRule,
    pub next_due_ms: i64,
}

/// 调度器 + 烟花编排的共享状态（managed 为 `Arc<Mutex<RemindersState>>`）。
#[derive(Debug, Default)]
pub struct RemindersState {
    pub rules: Vec<RuleState>,
    pub paused: bool,
    /// fireworks 窗口是否已挂载并注册好监听（ready 握手）。
    pub fw_ready: bool,
    /// 未 ready 时暂存的 play 请求。
    pub fw_pending: Option<PlayPayload>,
    /// 播放代次（watchdog 防误 hide 后一场）。
    pub fw_gen: u64,
    /// M4 P2 ④（M7 清偿）：当前播放中的 log id——新一场顶替/超时时对未回报
    /// finished 的旧 log 补 dismissed_via='fireworks'，消除残留 NULL。
    pub fw_active_log: Option<i64>,
}

impl RemindersState {
    /// 从 db 构建（启动时）。
    pub fn load(conn: &Connection) -> Result<Self, String> {
        let mut st = Self::default();
        st.reload(conn)?;
        st.paused = crate::db::get_state(conn, KEY_PAUSED).is_some_and(|v| v == "1");
        Ok(st)
    }

    /// 重新读表并重建倒计时（保留 paused；TC-RM-07 改设置即时生效）。
    pub fn reload(&mut self, conn: &Connection) -> Result<(), String> {
        let rules = load_rules(conn)?;
        let now = now_ms();
        self.rules = rules
            .into_iter()
            .map(|rule| RuleState {
                next_due_ms: compute_next_due(&rule, now),
                rule,
            })
            .collect();
        Ok(())
    }

    /// 一次 tick 的到期决策（含暂停顺延、窗口、去重），返回本次触发的规则快照
    /// （内存中的 last_triggered_at / next_due 已同步推进，db 落库由调用方负责）。
    pub fn collect_due(&mut self, now_ms: i64, now_ts: &str, minute_of_day: i64) -> Vec<ReminderRule> {
        if self.paused {
            // TC-RM-08：暂停期间不触发；到期周期规则倒计时顺延（恢复后不瞬间补弹）。
            for rs in &mut self.rules {
                if rs.rule.interval_minutes > 0 && now_ms >= rs.next_due_ms {
                    rs.next_due_ms = now_ms.saturating_add(rs.rule.interval_minutes * 60_000);
                }
            }
            return Vec::new();
        }
        let mut fired = Vec::new();
        for rs in &mut self.rules {
            if !rs.rule.enabled || now_ms < rs.next_due_ms {
                continue;
            }
            // M7：todo 派生规则的 start_time 是绝对时刻（非 HH:MM 窗口），
            // 到期即触发，不走活跃窗口判定。
            if rs.rule.kind != "todo" {
                let start = rs.rule.start_time.as_deref().and_then(parse_hhmm);
                let end = rs.rule.end_time.as_deref().and_then(parse_hhmm);
                if !in_window(minute_of_day, start, end) {
                    continue;
                }
            }
            let last = rs.rule.last_triggered_at.as_deref().and_then(parse_rfc3339_ms);
            if !dedup_ok(last, now_ms) {
                continue; // 去重窗口内：不触发也不推进（到点后等去重窗口过去）
            }
            let mut rule = rs.rule.clone();
            rs.next_due_ms = if rule.interval_minutes > 0 {
                now_ms.saturating_add(rule.interval_minutes * 60_000)
            } else {
                i64::MAX
            };
            rule.last_triggered_at = Some(now_ts.to_string());
            rs.rule = rule.clone();
            fired.push(rule);
        }
        fired
    }

    /// 手动"试一试"（面板按钮）：跳过倒计时与窗口（预览语义），仍受暂停与
    /// 3 分钟去重约束；返回 (状态, 触发规则)。
    pub fn force_fire_one(
        &mut self,
        id: i64,
        now_ms: i64,
        now_ts: &str,
    ) -> Result<(&'static str, Option<ReminderRule>), String> {
        if self.paused {
            return Ok(("paused", None));
        }
        let Some(rs) = self.rules.iter_mut().find(|rs| rs.rule.id == id) else {
            return Err(format!("reminder #{id} 不存在"));
        };
        let last = rs.rule.last_triggered_at.as_deref().and_then(parse_rfc3339_ms);
        if !dedup_ok(last, now_ms) {
            return Ok(("dedup", None));
        }
        rs.next_due_ms = if rs.rule.interval_minutes > 0 {
            now_ms.saturating_add(rs.rule.interval_minutes * 60_000)
        } else {
            i64::MAX
        };
        rs.rule.last_triggered_at = Some(now_ts.to_string());
        Ok(("fired", Some(rs.rule.clone())))
    }
}

// ---------------------------------------------------------------------------
// db 读写
// ---------------------------------------------------------------------------

fn row_to_rule(row: &rusqlite::Row<'_>) -> rusqlite::Result<ReminderRule> {
    Ok(ReminderRule {
        id: row.get("id")?,
        kind: row.get("kind")?,
        label: row.get("label")?,
        interval_minutes: row.get("interval_minutes")?,
        start_time: row.get("start_time")?,
        end_time: row.get("end_time")?,
        enabled: row.get::<_, i64>("enabled")? != 0,
        use_fireworks: row.get::<_, i64>("use_fireworks")? != 0,
        last_triggered_at: row.get("last_triggered_at")?,
        source_todo_id: row.get("source_todo_id")?,
        todo_due_at: row.get("todo_due_at")?,
        created_at: row.get("created_at")?,
    })
}

pub fn load_rules(conn: &Connection) -> Result<Vec<ReminderRule>, String> {
    let mut stmt = conn
        .prepare(
            "SELECT id, kind, label, interval_minutes, start_time, end_time, enabled, \
             use_fireworks, last_triggered_at, source_todo_id, todo_due_at, created_at \
             FROM reminders ORDER BY id",
        )
        .map_err(|e| format!("load reminders: {e}"))?;
    let rows = stmt
        .query_map([], row_to_rule)
        .map_err(|e| format!("load reminders: {e}"))?;
    Ok(rows.filter_map(|r| r.ok()).collect())
}

fn rule_by_id(conn: &Connection, id: i64) -> Result<ReminderRule, String> {
    conn.query_row(
        "SELECT id, kind, label, interval_minutes, start_time, end_time, enabled, \
         use_fireworks, last_triggered_at, source_todo_id, todo_due_at, created_at \
         FROM reminders WHERE id = ?1",
        [id],
        row_to_rule,
    )
    .map_err(|e| format!("read reminder #{id}: {e}"))
}

/// upsert 校验（与前端 validateReminderInput 同口径）。
/// M4 P2 ③（M7 清偿）：todo kind 恒 interval=0（一次性，spec §5.4），
/// start/end 为绝对时刻 "YYYY-MM-DDTHH:MM"（派生规则）；非 todo kind 间隔
/// 1-1440、start/end 为 HH:MM 窗口。
pub fn validate_input(input: &ReminderInput) -> Result<String, String> {
    const KINDS: &[&str] = &["hydration", "rest", "custom", "todo"];
    if !KINDS.contains(&input.kind.as_str()) {
        return Err(format!("kind 非法：{}（应为 hydration/rest/custom/todo）", input.kind));
    }
    // 单行化 + trim（与展示端 sanitizeBubbleText 同口径）
    let label: String = input.label.split_whitespace().collect::<Vec<_>>().join(" ");
    if label.is_empty() {
        return Err("label 不能为空".into());
    }
    if label.chars().count() > 140 {
        return Err("label 超长（≤140 字符）".into());
    }
    if input.kind == "todo" {
        // M4 P2 ③：todo 恒 0（唯一例外区间，>0 一律拒绝）
        if input.interval_minutes != 0 {
            return Err(format!(
                "interval_minutes 非法：{}（todo kind 恒为 0，一次性提醒）",
                input.interval_minutes
            ));
        }
        let check_abs = |what: &str, s: &Option<String>| -> Result<(), String> {
            if let Some(s) = s.as_deref().filter(|s| !s.is_empty()) {
                if parse_due_like_ms(s).is_none() {
                    return Err(format!(
                        "{what} 非法：{s}（todo kind 应为 YYYY-MM-DDTHH:MM 绝对时刻）"
                    ));
                }
            }
            Ok(())
        };
        check_abs("start_time", &input.start_time)?;
        check_abs("end_time", &input.end_time)?;
        return Ok(label);
    }
    if !(1..=MAX_INTERVAL_MINUTES).contains(&input.interval_minutes) {
        return Err(format!(
            "interval_minutes 非法：{}（{} kind 应为 1-{}）",
            input.interval_minutes, input.kind, MAX_INTERVAL_MINUTES
        ));
    }
    if let Some(s) = &input.start_time {
        parse_hhmm(s).ok_or_else(|| format!("start_time 非法：{s}（应为 HH:MM）"))?;
    }
    if let Some(e) = &input.end_time {
        parse_hhmm(e).ok_or_else(|| format!("end_time 非法：{e}（应为 HH:MM）"))?;
    }
    Ok(label)
}

pub fn insert_rule(conn: &Connection, input: &ReminderInput) -> Result<ReminderRule, String> {
    let label = validate_input(input)?;
    let now = now_rfc3339();
    let start = input.start_time.as_deref().filter(|s| !s.is_empty());
    let end = input.end_time.as_deref().filter(|s| !s.is_empty());
    conn.execute(
        "INSERT INTO reminders (kind, label, interval_minutes, start_time, end_time, \
         enabled, use_fireworks, created_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)",
        params![
            input.kind,
            label,
            input.interval_minutes,
            start,
            end,
            input.enabled as i64,
            input.use_fireworks as i64,
            now
        ],
    )
    .map_err(|e| format!("insert reminder: {e}"))?;
    rule_by_id(conn, conn.last_insert_rowid())
}

pub fn update_rule(
    conn: &Connection,
    id: i64,
    input: &ReminderInput,
) -> Result<ReminderRule, String> {
    let label = validate_input(input)?;
    let start = input.start_time.as_deref().filter(|s| !s.is_empty());
    let end = input.end_time.as_deref().filter(|s| !s.is_empty());
    let n = conn
        .execute(
            "UPDATE reminders SET kind = ?1, label = ?2, interval_minutes = ?3, \
             start_time = ?4, end_time = ?5, enabled = ?6, use_fireworks = ?7 WHERE id = ?8",
            params![
                input.kind,
                label,
                input.interval_minutes,
                start,
                end,
                input.enabled as i64,
                input.use_fireworks as i64,
                id
            ],
        )
        .map_err(|e| format!("update reminder #{id}: {e}"))?;
    if n == 0 {
        return Err(format!("reminder #{id} 不存在"));
    }
    rule_by_id(conn, id)
}

pub fn delete_rule(conn: &Connection, id: i64) -> Result<(), String> {
    // 级联清 reminder_logs 由 schema ON DELETE CASCADE 保证（db.rs 已开外键）
    conn.execute("DELETE FROM reminders WHERE id = ?1", [id])
        .map_err(|e| format!("delete reminder #{id}: {e}"))?;
    Ok(())
}

/// 触发即写 reminder_logs（TC-RM-13），返回 log id。
pub fn insert_log(conn: &Connection, reminder_id: i64, triggered_at: &str) -> Result<i64, String> {
    conn.execute(
        "INSERT INTO reminder_logs (reminder_id, triggered_at) VALUES (?1, ?2)",
        params![reminder_id, triggered_at],
    )
    .map_err(|e| format!("insert reminder_log: {e}"))?;
    Ok(conn.last_insert_rowid())
}

/// 点击确认（TC-RM-04）：acked_at + dismissed_via='bubble'（已被 dismiss 的行不动）。
pub fn ack_log(conn: &Connection, log_id: i64, acked_at: &str) -> Result<(), String> {
    conn.execute(
        "UPDATE reminder_logs SET acked_at = ?2, dismissed_via = 'bubble' \
         WHERE id = ?1 AND dismissed_via IS NULL",
        params![log_id, acked_at],
    )
    .map_err(|e| format!("ack reminder_log {log_id}: {e}"))?;
    Ok(())
}

/// 自动消失 / 烟花结束回报（via = "auto" | "fireworks"；TC-RM-03/09）。
pub fn dismiss_log(conn: &Connection, log_id: i64, via: &str) -> Result<(), String> {
    if via != "auto" && via != "fireworks" {
        return Err(format!("dismissed_via 非法：{via}（应为 auto/fireworks）"));
    }
    conn.execute(
        "UPDATE reminder_logs SET dismissed_via = ?2 WHERE id = ?1 AND dismissed_via IS NULL",
        params![log_id, via],
    )
    .map_err(|e| format!("dismiss reminder_log {log_id}: {e}"))?;
    Ok(())
}

/// 按天更新 last_triggered_at（触发路径落库）。
pub fn mark_triggered(conn: &Connection, id: i64, ts: &str) -> Result<(), String> {
    conn.execute(
        "UPDATE reminders SET last_triggered_at = ?2 WHERE id = ?1",
        params![id, ts],
    )
    .map_err(|e| format!("mark triggered #{id}: {e}"))?;
    Ok(())
}

/// 历史统计（TC-RM-13）：按 kind 聚合（today = 本地当日触发数）。
pub fn stats(conn: &Connection) -> Result<Vec<ReminderStat>, String> {
    let mut stmt = conn
        .prepare(
            "SELECT r.kind AS kind, l.triggered_at AS triggered_at \
             FROM reminder_logs l JOIN reminders r ON r.id = l.reminder_id",
        )
        .map_err(|e| format!("stats prepare: {e}"))?;
    let rows = stmt
        .query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })
        .map_err(|e| format!("stats query: {e}"))?;
    let today = Local::now().date_naive();
    let mut out: Vec<ReminderStat> = Vec::new();
    for r in rows.flatten() {
        let (kind, ts) = r;
        let is_today = DateTime::parse_from_rfc3339(&ts)
            .map(|d| d.with_timezone(&Local).date_naive() == today)
            .unwrap_or(false);
        if let Some(st) = out.iter_mut().find(|s| s.kind == kind) {
            st.total += 1;
            if is_today {
                st.today += 1;
            }
        } else {
            out.push(ReminderStat {
                kind,
                today: is_today as i64,
                total: 1,
            });
        }
    }
    out.sort_by(|a, b| a.kind.cmp(&b.kind));
    Ok(out)
}

pub fn is_paused(conn: &Connection) -> bool {
    crate::db::get_state(conn, KEY_PAUSED).is_some_and(|v| v == "1")
}

pub fn set_paused(conn: &Connection, paused: bool) {
    let _ = crate::db::set_state(conn, KEY_PAUSED, if paused { "1" } else { "0" });
}

pub fn fireworks_global(conn: &Connection) -> bool {
    crate::db::get_state(conn, KEY_FIREWORKS_GLOBAL).is_some_and(|v| v == "1")
}

pub fn set_fireworks_global(conn: &Connection, on: bool) {
    let _ = crate::db::set_state(conn, KEY_FIREWORKS_GLOBAL, if on { "1" } else { "0" });
}

// ---------------------------------------------------------------------------
// 触发编排（tick 与 trigger_now 共用）
// ---------------------------------------------------------------------------

/// 触发落库 + 发事件（`reminder://trigger` 广播，pet 窗口消费）。
fn fire_and_notify(app: &tauri::AppHandle, fired: &[ReminderRule]) {
    let Some(db) = app.try_state::<Mutex<Connection>>() else {
        return;
    };
    let Ok(conn) = db.lock() else {
        return;
    };
    let fw_global = fireworks_global(&conn);
    for rule in fired {
        let ts = rule.last_triggered_at.clone().unwrap_or_default();
        let Ok(log_id) = insert_log(&conn, rule.id, &ts) else {
            eprintln!("[pulsepet] reminder #{} insert_log 失败，跳过事件", rule.id);
            continue;
        };
        let _ = mark_triggered(&conn, rule.id, &ts);
        let payload = TriggerPayload {
            id: rule.id,
            kind: rule.kind.clone(),
            label: rule.label.clone(),
            use_fireworks: rule.use_fireworks,
            fireworks_global: fw_global,
            log_id,
            // M7（TC-TD-03）：todo 派生携带截止时刻，前端算"还有 X 分钟"
            todo_due_ms: if rule.kind == "todo" {
                rule.todo_due_at.as_deref().and_then(parse_due_like_ms)
            } else {
                None
            },
        };
        let _ = app.emit("reminder://trigger", payload);
        eprintln!(
            "[pulsepet] reminder fired: #{} kind={} label={:?} fireworks={} log={} at {}",
            rule.id, rule.kind, rule.label, rule.use_fireworks, log_id, ts
        );
    }
}

/// 计算烟花 play payload（DESIGN §5.3 用户补充需求）：
/// - 发射点 = pet 窗口中心；
/// - **绽放点 = pet 当前所处显示器（monitor）的水平中轴 + 屏高 × 0.3**
///   （多显示器取宠物所在屏；单显示器即当前屏）；
/// - 坐标换算到 fireworks 窗口逻辑像素（payload 消费方 ×dpr 进 canvas）。
fn compute_play_payload(app: &tauri::AppHandle, log_id: i64) -> PlayPayload {
    let fw = app.get_webview_window("fireworks");
    let pet = app.get_webview_window("pet");

    // 1) 宠物当前所处显示器：pet.current_monitor()（窗口当前所在屏）；
    //    取不到时回退 fireworks 窗口所在屏（通常为主屏）。
    let mon = pet
        .as_ref()
        .and_then(|w| w.current_monitor().ok().flatten())
        .or_else(|| fw.as_ref().and_then(|w| w.current_monitor().ok().flatten()));

    // 2) 多显示器跟随：把 fireworks 窗口铺到该显示器（隐藏态移动，无视觉闪烁）。
    //    单显示器时窗口 bounds 已等于该屏 → no-op。
    if let (Some(fww), Some(m)) = (fw.as_ref(), mon.as_ref()) {
        cover_monitor(fww, m);
    }

    let sf = fw.as_ref().and_then(|w| w.scale_factor().ok()).unwrap_or(1.0);
    // 移动后重读 fireworks 窗口 bounds（物理像素）
    let (fw_x, fw_y, fw_w, fw_h) = match (
        fw.as_ref().and_then(|w| w.outer_position().ok()),
        fw.as_ref().and_then(|w| w.outer_size().ok()),
    ) {
        (Some(p), Some(s)) => (p.x as f64, p.y as f64, s.width as f64, s.height as f64),
        _ => (0.0, 0.0, 1280.0 * sf, 800.0 * sf),
    };

    // 3) 发射点 = pet 中心（物理 → fireworks 窗口逻辑坐标；取不到退化为窗口底部中间）
    let (ox, oy) = match (&pet, pet.as_ref().map(|w| (w.outer_position(), w.outer_size()))) {
        (Some(_), Some((Ok(p), Ok(s)))) => (
            (p.x as f64 + s.width as f64 / 2.0 - fw_x) / sf,
            (p.y as f64 + s.height as f64 / 2.0 - fw_y) / sf,
        ),
        _ => (fw_w / 2.0 / sf, fw_h * 0.85 / sf),
    };
    let origin_x = ox.clamp(20.0, (fw_w / sf - 20.0).max(20.0));
    let origin_y = oy.clamp(20.0, (fw_h / sf - 20.0).max(20.0));

    // 4) 绽放点 = 该显示器中轴线 + 屏高 0.3 处（物理 → fireworks 窗口逻辑坐标；
    //    cover 后窗口 bounds == 显示器 bounds；clamp 仅作安全兜底）
    let (tx, ty) = match mon.as_ref() {
        Some(m) => monitor_burst_point_in_window(
            m.position().x,
            m.position().y,
            m.size().width,
            m.size().height,
            fw_x as i32,
            fw_y as i32,
            sf,
        ),
        None => (fw_w / 2.0 / sf, fw_h * BURST_Y_RATIO / sf), // 兜底：窗口同比例点
    };
    let target_x = tx.clamp(20.0, (fw_w / sf - 20.0).max(20.0));
    let target_y = ty.clamp(20.0, (fw_h / sf - 20.0).max(20.0));
    eprintln!(
        "[pulsepet] fireworks target = monitor axis x center + y*{BURST_Y_RATIO} ({target_x:.0}, {target_y:.0}) logical, origin ({origin_x:.0}, {origin_y:.0})"
    );
    PlayPayload {
        log_id,
        origin_x,
        origin_y,
        target_x,
        target_y,
    }
}

/// 绽放点纵向比例（用户定案 2026-08-16：屏幕从上往下 0.3 倍处，中间偏上）。
pub const BURST_Y_RATIO: f64 = 0.3;

/// 绽放点 = 显示器水平中轴（x 居中）+ 屏高 × 0.3 → fireworks 窗口逻辑坐标
/// （纯函数，可单测）。`(mon_x, mon_y, mon_w, mon_h)` 为显示器物理 bounds，
/// `(win_x, win_y)` 为窗口物理左上角。
pub fn monitor_burst_point_in_window(
    mon_x: i32,
    mon_y: i32,
    mon_w: u32,
    mon_h: u32,
    win_x: i32,
    win_y: i32,
    sf: f64,
) -> (f64, f64) {
    let cx = mon_x as f64 + mon_w as f64 / 2.0;
    let cy = mon_y as f64 + mon_h as f64 * BURST_Y_RATIO;
    ((cx - win_x as f64) / sf, (cy - win_y as f64) / sf)
}

/// 把 fireworks 窗口铺满指定显示器（多显示器：绽放跟随宠物所在屏）。
/// 窗口隐藏时调用（play 流程 show 之前）→ 无视觉闪烁；bounds 已相符则 no-op。
fn cover_monitor(win: &tauri::WebviewWindow, mon: &tauri::Monitor) {
    let mpos = mon.position();
    let msize = mon.size();
    let already = win
        .outer_position()
        .map(|p| p == *mpos)
        .unwrap_or(false)
        && win.outer_size().map(|s| s == *msize).unwrap_or(false);
    if already {
        return;
    }
    // maximized 状态下 set_frame 可能被系统忽略 → 先退出再铺满（隐藏态无闪烁）
    if win.is_maximized().unwrap_or(false) {
        let _ = win.unmaximize();
    }
    let _ = win.set_position(*mpos);
    let _ = win.set_size(*msize);
    eprintln!(
        "[pulsepet] fireworks window moved to monitor {:?} ({},{} {}x{})",
        mon.name(),
        mpos.x,
        mpos.y,
        msize.width,
        msize.height
    );
}

// ---------------------------------------------------------------------------
// 调度循环
// ---------------------------------------------------------------------------

/// tick 周期（默认 60s；`PULSEPET_REMINDER_TICK_MS` 供运行时实测调短）。
pub fn tick_ms() -> u64 {
    std::env::var("PULSEPET_REMINDER_TICK_MS")
        .ok()
        .and_then(|s| s.parse().ok())
        .filter(|v| *v >= 100)
        .unwrap_or(DEFAULT_TICK_MS)
}

/// 启动调度循环：tokio interval + `MissedTickBehavior::Skip`（TC-RM-02）。
pub fn spawn_scheduler(app: tauri::AppHandle, state: Arc<Mutex<RemindersState>>) {
    tauri::async_runtime::spawn(async move {
        let mut interval =
            tokio::time::interval(std::time::Duration::from_millis(tick_ms()));
        // 睡眠恢复不补发：错过的 tick 直接跳过，等下一个整 tick（TC-RM-02/C10）
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        // interval 首个 tick 立即到期：跳过第 0 次避免启动瞬间扫一次（无害但省心）
        interval.tick().await;
        eprintln!("[pulsepet] reminder scheduler started (tick {}ms)", tick_ms());
        loop {
            interval.tick().await;
            run_tick(&app, &state);
        }
    });
}

fn run_tick(app: &tauri::AppHandle, state: &Arc<Mutex<RemindersState>>) {
    let now = now_ms();
    let ts = now_rfc3339();
    let minute = now_minute_of_day();
    let fired = {
        let Ok(mut st) = state.lock() else {
            return;
        };
        st.collect_due(now, &ts, minute)
    };
    if !fired.is_empty() {
        fire_and_notify(app, &fired);
    }
}

// ---------------------------------------------------------------------------
// Tauri 命令（在 lib.rs 注册）
// ---------------------------------------------------------------------------

fn reload_state<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> Result<(), String> {
    let state = app
        .state::<Arc<Mutex<RemindersState>>>()
        .inner()
        .clone();
    let db = app.state::<Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    let mut st = state.lock().map_err(|e| format!("state lock: {e}"))?;
    st.reload(&conn)
}

/// M7：todo CRUD 改动派生提醒后由 todos 命令调用（与 reminders CRUD 同口径）。
pub fn reload_from_app<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> Result<(), String> {
    reload_state(app)
}

/// 规则列表（panel 提醒页）。
#[tauri::command]
pub fn reminders_list(app: tauri::AppHandle) -> Result<Vec<ReminderRule>, String> {
    let db = app.state::<Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    load_rules(&conn)
}

/// 新建（id=None）或更新（id=Some）规则；写库后自动 reload 调度器（TC-RM-07）。
#[tauri::command]
pub fn reminders_upsert(
    app: tauri::AppHandle,
    id: Option<i64>,
    input: ReminderInput,
) -> Result<ReminderRule, String> {
    let db = app.state::<Mutex<Connection>>();
    let rule = {
        let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
        match id {
            Some(id) => update_rule(&conn, id, &input)?,
            None => insert_rule(&conn, &input)?,
        }
    };
    reload_state(&app)?;
    Ok(rule)
}

#[tauri::command]
pub fn reminders_delete(app: tauri::AppHandle, id: i64) -> Result<(), String> {
    {
        let db = app.state::<Mutex<Connection>>();
        let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
        delete_rule(&conn, id)?;
    }
    reload_state(&app)
}

/// 显式 reload（TC-RM-07；CRUD 命令已内置，此命令供外部/调试用）。
#[tauri::command]
pub fn reminders_reload(app: tauri::AppHandle) -> Result<(), String> {
    reload_state(&app)
}

#[tauri::command]
pub fn reminders_get_fireworks_global(app: tauri::AppHandle) -> Result<bool, String> {
    let db = app.state::<Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    Ok(fireworks_global(&conn))
}

/// 全局烟花开关（TC-RM-11：全局关 + 单条 use_fireworks=1 → 该条仍放烟花）。
#[tauri::command]
pub fn reminders_set_fireworks_global(app: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    {
        let db = app.state::<Mutex<Connection>>();
        let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
        set_fireworks_global(&conn, enabled);
    }
    Ok(())
}

/// 全局暂停状态（面板展示用；切换走托盘菜单，TC-RM-08）。
#[tauri::command]
pub fn reminders_get_paused(app: tauri::AppHandle) -> Result<bool, String> {
    let db = app.state::<Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    Ok(is_paused(&conn))
}

/// 历史统计（TC-RM-13）。
#[tauri::command]
pub fn reminders_stats(app: tauri::AppHandle) -> Result<Vec<ReminderStat>, String> {
    let db = app.state::<Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    stats(&conn)
}

/// 手动触发（面板"试一试"）：返回 "fired" | "dedup" | "paused"。
#[tauri::command]
pub fn reminders_trigger_now(
    app: tauri::AppHandle,
    state: tauri::State<'_, Arc<Mutex<RemindersState>>>,
    id: i64,
) -> Result<String, String> {
    let now = now_ms();
    let ts = now_rfc3339();
    let (status, rule) = state
        .lock()
        .map_err(|e| format!("state lock: {e}"))?
        .force_fire_one(id, now, &ts)?;
    if let Some(rule) = rule {
        fire_and_notify(&app, &[rule]);
    }
    Ok(status.to_string())
}

/// 气泡点击确认（TC-RM-04）：记 acked_at + dismissed_via='bubble'。
#[tauri::command]
pub fn reminders_ack(app: tauri::AppHandle, log_id: i64) -> Result<(), String> {
    let db = app.state::<Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    ack_log(&conn, log_id, &now_rfc3339())
}

/// 气泡 8s 自动消失（via='auto'）。
#[tauri::command]
pub fn reminders_dismiss(app: tauri::AppHandle, log_id: i64, via: String) -> Result<(), String> {
    let db = app.state::<Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    dismiss_log(&conn, log_id, &via)
}

/// pet 窗口请求放烟花（TC-RM-09）：定位发射点 → show fireworks 窗口 → 下发 play。
#[tauri::command]
pub fn reminder_play_fireworks(
    app: tauri::AppHandle,
    state: tauri::State<'_, Arc<Mutex<RemindersState>>>,
    log_id: i64,
) -> Result<(), String> {
    dispatch_play(&app, state.inner(), log_id);
    Ok(())
}

/// M6 调试烟花（TC-WIN-07，热键 ⌘/Ctrl+Shift+Alt+F 手动放一束）：复用 M4
/// 烟花链路（定位/ready 握手/watchdog 全同），log_id=-1 表示非提醒来源——
/// fireworks_finished 对 -1 记账是无害空更新（0 行）。仅 debug 构建的热键
/// 规格表会分发到本函数（hotkeys::hotkey_specs，release 不注册）。
pub fn play_debug_fireworks(app: &tauri::AppHandle) {
    let Some(state) = app.try_state::<Arc<Mutex<RemindersState>>>() else {
        return;
    };
    eprintln!("[pulsepet] debug fireworks (hotkey)");
    dispatch_play(app, &state, -1);
}

/// 烟花派发公共段（reminder_play_fireworks / play_debug_fireworks 共用）：
/// gen++（作废旧 watchdog）→ ready 直发 / 未 ready 挂 pending → show 窗口 → watchdog。
fn dispatch_play(app: &tauri::AppHandle, state: &Arc<Mutex<RemindersState>>, log_id: i64) {
    let payload = compute_play_payload(app, log_id);
    let gen;
    let superseded;
    {
        let mut st = state.lock().unwrap_or_else(|p| p.into_inner());
        st.fw_gen += 1;
        gen = st.fw_gen;
        // M4 P2 ④（M7 清偿）：新一场顶替未回报 finished 的旧场 → 旧 log 的
        // dismissed_via 残留 NULL，这里补报 'fireworks'（dismiss 只动 NULL 行，
        // 已结案的不覆盖）。
        superseded = st.fw_active_log.filter(|old| *old != log_id);
        st.fw_active_log = (log_id >= 0).then_some(log_id);
        if st.fw_ready {
            let _ = app.emit_to("fireworks", "fireworks://play", payload);
        } else {
            eprintln!(
                "[pulsepet] fireworks not ready, queueing play (log {log_id})"
            );
            st.fw_pending = Some(payload);
        }
    }
    if let Some(old) = superseded {
        if let Some(db) = app.try_state::<Mutex<Connection>>() {
            if let Ok(conn) = db.lock() {
                let _ = dismiss_log(&conn, old, "fireworks");
                eprintln!("[pulsepet] fireworks superseded: backfill log {old} via 'fireworks'");
            }
        }
    }
    windows::show_fireworks(app);
    // watchdog：6.5s 内前端未回报 finished 则强制 hide（防常驻窗口）。
    // 前端正常 finished 已 hide 过时窗口不可见 → 跳过，避免冗余 hide（E2E 实测修正）。
    // M4 P2 ④：超时同样对未结案 log 补 dismissed_via='fireworks'（前端崩溃时不再残留 NULL）。
    let state_for_wd = state.clone();
    let app_for_wd = app.clone();
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(std::time::Duration::from_millis(6500)).await;
        let cur = state_for_wd
            .lock()
            .map(|st| st.fw_gen)
            .unwrap_or(u64::MAX);
        if cur == gen {
            let still_active = state_for_wd
                .lock()
                .map(|mut st| {
                    if st.fw_active_log == Some(log_id) {
                        st.fw_active_log = None;
                        true
                    } else {
                        false
                    }
                })
                .unwrap_or(false);
            if still_active && log_id >= 0 {
                if let Some(db) = app_for_wd.try_state::<Mutex<Connection>>() {
                    if let Ok(conn) = db.lock() {
                        let _ = dismiss_log(&conn, log_id, "fireworks");
                        eprintln!("[pulsepet] fireworks watchdog: backfill log {log_id} via 'fireworks'");
                    }
                }
            }
            let visible = app_for_wd
                .get_webview_window("fireworks")
                .and_then(|w| w.is_visible().ok())
                .unwrap_or(false);
            if visible {
                windows::hide_fireworks(&app_for_wd);
                eprintln!("[pulsepet] fireworks watchdog hide (gen {gen})");
            }
        }
    });
}

/// fireworks 窗口挂载完成（ready 握手）：补发 pending 的 play。
#[tauri::command]
pub fn fireworks_ready(
    app: tauri::AppHandle,
    state: tauri::State<'_, Arc<Mutex<RemindersState>>>,
) -> Result<(), String> {
    let pending = {
        let mut st = state.lock().map_err(|e| format!("state lock: {e}"))?;
        st.fw_ready = true;
        st.fw_pending.take()
    };
    if let Some(p) = pending {
        let _ = app.emit_to("fireworks", "fireworks://play", p.clone());
        windows::show_fireworks(&app);
        eprintln!("[pulsepet] fireworks ready → replay pending (log {})", p.log_id);
    }
    Ok(())
}

/// 前端播完回报：hide 窗口 + 记 dismissed_via='fireworks'（TC-RM-09/13）。
#[tauri::command]
pub fn fireworks_finished(app: tauri::AppHandle, log_id: i64) -> Result<(), String> {
    windows::hide_fireworks(&app);
    {
        // M4 P2 ④：正常回报即清掉 active 标记（后续顶替补报不再误伤本 log）
        if let Some(state) = app.try_state::<Arc<Mutex<RemindersState>>>() {
            if let Ok(mut st) = state.lock() {
                if st.fw_active_log == Some(log_id) {
                    st.fw_active_log = None;
                }
            }
        }
    }
    let db = app.state::<Mutex<Connection>>();
    if let Ok(conn) = db.lock() {
        let _ = dismiss_log(&conn, log_id, "fireworks");
    }
    eprintln!("[pulsepet] fireworks finished: log {log_id} hidden");
    Ok(())
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

    fn input(kind: &str, label: &str, interval: i64) -> ReminderInput {
        ReminderInput {
            kind: kind.into(),
            label: label.into(),
            interval_minutes: interval,
            start_time: None,
            end_time: None,
            enabled: true,
            use_fireworks: false,
        }
    }

    fn rfc(ms: i64) -> String {
        DateTime::from_timestamp_millis(ms)
            .unwrap()
            .with_timezone(&Local)
            .to_rfc3339_opts(SecondsFormat::Millis, true)
    }

    // ---- parse_hhmm / in_window（TC-RM-06） ----

    #[test]
    fn parse_hhmm_valid_and_invalid() {
        assert_eq!(parse_hhmm("00:00"), Some(0));
        assert_eq!(parse_hhmm("09:05"), Some(545));
        assert_eq!(parse_hhmm("23:59"), Some(1439));
        assert_eq!(parse_hhmm("24:00"), None);
        assert_eq!(parse_hhmm("12:60"), None);
        assert_eq!(parse_hhmm("ab:cd"), None);
        assert_eq!(parse_hhmm("0900"), None);
        assert_eq!(parse_hhmm(""), None);
    }

    #[test]
    fn window_same_day_boundaries() {
        let (s, e) = (parse_hhmm("09:00"), parse_hhmm("18:00"));
        assert!(!in_window(8 * 60 + 59, s, e));
        assert!(in_window(9 * 60, s, e));
        assert!(in_window(17 * 60 + 59, s, e));
        assert!(!in_window(18 * 60, s, e)); // end 不含
    }

    #[test]
    fn window_cross_midnight_boundaries_tc_rm_06() {
        // 22:00-06:00：仅 [22:00,24:00) ∪ [00:00,06:00)
        let (s, e) = (parse_hhmm("22:00"), parse_hhmm("06:00"));
        assert!(!in_window(21 * 60 + 59, s, e)); // 21:59 ✗
        assert!(in_window(22 * 60, s, e)); // 22:00 ✓
        assert!(in_window(23 * 60 + 59, s, e)); // 23:59 ✓
        assert!(in_window(0, s, e)); // 00:00 ✓
        assert!(in_window(5 * 60 + 59, s, e)); // 05:59 ✓
        assert!(!in_window(6 * 60, s, e)); // 06:00 ✗
        assert!(!in_window(12 * 60, s, e)); // 12:00 ✗
    }

    #[test]
    fn window_partial_and_open() {
        assert!(in_window(300, None, None));
        assert!(in_window(23 * 60, parse_hhmm("22:00"), None)); // 仅 start
        assert!(!in_window(21 * 60, parse_hhmm("22:00"), None));
        assert!(in_window(3 * 60, None, parse_hhmm("06:00"))); // 仅 end
        assert!(!in_window(7 * 60, None, parse_hhmm("06:00")));
        // 非法时间串解析为 None → 视为无边界（宽容不 panic）
        assert!(in_window(0, parse_hhmm("bad"), parse_hhmm("bad")));
    }

    // ---- compute_next_due / dedup（TC-RM-01/02/05） ----

    #[test]
    fn next_due_never_triggered_anchors_at_created() {
        let rule = ReminderRule {
            id: 1,
            kind: "hydration".into(),
            label: "该喝水啦 💧".into(),
            interval_minutes: 30,
            start_time: None,
            end_time: None,
            enabled: true,
            use_fireworks: false,
            last_triggered_at: None,
            source_todo_id: None,
            todo_due_at: None,
            created_at: rfc(1000),
        };
        // created + 30min 在未来 → 保留；now=0 时 created(1000)+1800000 > 0
        assert_eq!(compute_next_due(&rule, 0), 1000 + 1_800_000);
        // created 很久以前（如停机错过）→ 顺延 now + interval（不补发，TC-RM-02 精神）
        assert_eq!(compute_next_due(&rule, 10_000_000), 10_000_000 + 1_800_000);
    }

    #[test]
    fn next_due_respects_last_triggered_anchor() {
        let mut rule = ReminderRule {
            id: 1,
            kind: "rest".into(),
            label: "休息".into(),
            interval_minutes: 30,
            start_time: None,
            end_time: None,
            enabled: true,
            use_fireworks: false,
            last_triggered_at: Some(rfc(1_000_000)),
            source_todo_id: None,
            todo_due_at: None,
            created_at: rfc(0),
        };
        // reload 于 last+10min：next_due = last+30min（不被 reload 重置，TC-RM-07）
        assert_eq!(compute_next_due(&rule, 1_000_000 + 600_000), 1_000_000 + 1_800_000);
        // reload 于 last+45min（已过期）→ now + interval
        assert_eq!(
            compute_next_due(&rule, 1_000_000 + 2_700_000),
            1_000_000 + 2_700_000 + 1_800_000
        );
        // interval 缩短到 5min：last+5min 已过 → now+5min（不回溯触发）
        rule.interval_minutes = 5;
        assert_eq!(
            compute_next_due(&rule, 1_000_000 + 600_000),
            1_000_000 + 600_000 + 300_000
        );
    }

    #[test]
    fn next_due_todo_kind_fires_once_only() {
        let mut rule = ReminderRule {
            id: 7,
            kind: "todo".into(),
            label: "交报告".into(),
            interval_minutes: 0,
            start_time: None,
            end_time: None,
            enabled: true,
            use_fireworks: false,
            last_triggered_at: None,
            source_todo_id: Some(42),
            todo_due_at: None,
            created_at: rfc(0),
        };
        // 从未触发 → 立即到期（进入窗口即触发一次）
        assert_eq!(compute_next_due(&rule, 5000), 5000);
        // 触发后 → 永不再触发（§5.4 todo 一次性语义）
        rule.last_triggered_at = Some(rfc(6000));
        assert_eq!(compute_next_due(&rule, 7000), i64::MAX);
        assert_eq!(compute_next_due(&rule, 10_000_000), i64::MAX);
    }

    #[test]
    fn dedup_window_three_minutes_tc_rm_05() {
        let now = 10_000_000;
        assert!(dedup_ok(None, now));
        assert!(!dedup_ok(Some(now - 2 * 60_000 - 1), now)); // 2:59 ✗
        assert!(dedup_ok(Some(now - 3 * 60_000), now)); // 3:00 ✓
    }

    // ---- collect_due 决策 ----

    fn state_with(rule: ReminderRule, now: i64) -> RemindersState {
        let next = compute_next_due(&rule, now);
        RemindersState {
            rules: vec![RuleState { rule, next_due_ms: next }],
            paused: false,
            fw_ready: false,
            fw_pending: None,
            fw_gen: 0,
            fw_active_log: None,
        }
    }

    fn base_rule(id: i64, interval: i64) -> ReminderRule {
        ReminderRule {
            id,
            kind: "hydration".into(),
            label: "该喝水啦 💧".into(),
            interval_minutes: interval,
            start_time: None,
            end_time: None,
            enabled: true,
            use_fireworks: false,
            last_triggered_at: None,
            source_todo_id: None,
            todo_due_at: None,
            created_at: rfc(0),
        }
    }

    #[test]
    fn collect_due_fires_when_due_and_advances() {
        let now = 1_000_000;
        let mut st = state_with(base_rule(1, 30), now);
        st.rules[0].next_due_ms = now; // 到期
        let fired = st.collect_due(now, &rfc(now), 600);
        assert_eq!(fired.len(), 1);
        assert_eq!(fired[0].id, 1);
        assert_eq!(fired[0].last_triggered_at.as_deref(), Some(rfc(now).as_str()));
        // 触发后 next_due 推进：同一时刻不再触发
        assert!(st.rules[0].next_due_ms > now);
        assert!(st.collect_due(now, &rfc(now), 600).is_empty());
    }

    #[test]
    fn collect_due_respects_window_tc_rm_06() {
        let now = 1_000_000;
        let mut rule = base_rule(1, 30);
        rule.start_time = Some("09:00".into());
        rule.end_time = Some("18:00".into());
        let mut st = state_with(rule, now);
        st.rules[0].next_due_ms = now;
        // 08:00（窗口外）不触发，倒计时保持到期（等窗口打开）
        assert!(st.collect_due(now, &rfc(now), 8 * 60).is_empty());
        assert_eq!(st.rules[0].next_due_ms, now);
        // 09:00 进入窗口 → 触发
        assert_eq!(st.collect_due(now, &rfc(now), 9 * 60).len(), 1);
        // 跨午夜窗口 22:00-06:00：12:00 不触发
        let mut rule2 = base_rule(2, 30);
        rule2.start_time = Some("22:00".into());
        rule2.end_time = Some("06:00".into());
        let mut st2 = state_with(rule2, now);
        st2.rules[0].next_due_ms = now;
        assert!(st2.collect_due(now, &rfc(now), 12 * 60).is_empty());
        assert_eq!(st2.collect_due(now, &rfc(now), 23 * 60).len(), 1);
    }

    #[test]
    fn collect_due_dedup_blocks_interval_below_three_minutes() {
        // interval=1min 的实测规则：触发后 1min 到期，但 3 分钟去重内不得重复（TC-RM-05）
        let now = 1_000_000;
        let mut st = state_with(base_rule(1, 1), now);
        st.rules[0].next_due_ms = now;
        assert_eq!(st.collect_due(now, &rfc(now), 600).len(), 1);
        // +2min：next_due（now+1min）已过，但去重拦截
        assert!(st.collect_due(now + 120_000, &rfc(now + 120_000), 600).is_empty());
        // +3min 整：去重窗口过去 → 再触发
        assert_eq!(
            st.collect_due(now + 180_000, &rfc(now + 180_000), 600).len(),
            1
        );
    }

    #[test]
    fn collect_due_disabled_rule_never_fires() {
        let now = 1_000_000;
        let mut rule = base_rule(1, 30);
        rule.enabled = false;
        let mut st = state_with(rule, now);
        st.rules[0].next_due_ms = now;
        assert!(st.collect_due(now, &rfc(now), 600).is_empty());
    }

    #[test]
    fn collect_due_paused_defers_and_resumes_tc_rm_08() {
        let now = 1_000_000;
        let mut st = state_with(base_rule(1, 30), now);
        st.rules[0].next_due_ms = now;
        // 暂停：到期不触发，倒计时顺延 now+30min
        st.paused = true;
        assert!(st.collect_due(now, &rfc(now), 600).is_empty());
        assert_eq!(st.rules[0].next_due_ms, now + 1_800_000);
        // 暂停期间每 tick 顺延：仅在再次到期的 tick 才继续顺延（1 分钟后未到期 → 保持）
        assert!(st.collect_due(now + 60_000, &rfc(now + 60_000), 600).is_empty());
        assert_eq!(st.rules[0].next_due_ms, now + 1_800_000);
        // 取消暂停：顺延点之前不触发
        st.paused = false;
        let due = st.rules[0].next_due_ms;
        assert!(st.collect_due(due - 1, &rfc(due - 1), 600).is_empty());
        // 到顺延点 → 恢复触发
        assert_eq!(st.collect_due(due, &rfc(due), 600).len(), 1);
    }

    #[test]
    fn collect_due_todo_kind_single_fire_no_repeat() {
        let now = 1_000_000;
        let mut rule = base_rule(9, 0);
        rule.kind = "todo".into();
        rule.source_todo_id = Some(3);
        let mut st = state_with(rule, now);
        st.rules[0].next_due_ms = now; // 从未触发 → 立即到期
        assert_eq!(st.collect_due(now, &rfc(now), 600).len(), 1);
        assert_eq!(st.rules[0].next_due_ms, i64::MAX);
        // 后续 tick / 更晚时刻均不再触发（不误重复）
        assert!(st.collect_due(now + 60_000, &rfc(now + 60_000), 600).is_empty());
        assert!(st.collect_due(now + 6_000_000, &rfc(now + 6_000_000), 600).is_empty());
    }

    #[test]
    fn force_fire_one_respects_pause_and_dedup() {
        let now = 1_000_000;
        let mut st = state_with(base_rule(1, 30), now);
        // 正常：fired + 推进
        let (status, rule) = st.force_fire_one(1, now, &rfc(now)).unwrap();
        assert_eq!(status, "fired");
        assert!(rule.is_some());
        // 立即再触发 → dedup
        let (status, rule) = st.force_fire_one(1, now + 1000, &rfc(now + 1000)).unwrap();
        assert_eq!(status, "dedup");
        assert!(rule.is_none());
        // +3min → 可再触发；但暂停时 → paused
        st.paused = true;
        let (status, _) = st.force_fire_one(1, now + 180_000, &rfc(now + 180_000)).unwrap();
        assert_eq!(status, "paused");
        st.paused = false;
        let (status, _) = st.force_fire_one(1, now + 180_000, &rfc(now + 180_000)).unwrap();
        assert_eq!(status, "fired");
        // 不存在的 id → Err
        assert!(st.force_fire_one(999, now, &rfc(now)).is_err());
    }

    // ---- db CRUD / logs / stats（TC-RM-07/13） ----

    #[test]
    fn upsert_list_delete_roundtrip_and_validation() {
        let c = conn();
        let r1 = insert_rule(&c, &input("hydration", "该喝水啦 💧", 30)).unwrap();
        assert_eq!(r1.kind, "hydration");
        assert_eq!(r1.interval_minutes, 30);
        assert!(r1.enabled);
        assert_eq!(load_rules(&c).unwrap().len(), 1);

        // 更新
        let mut upd = input("rest", "休息一下 ☕", 60);
        upd.start_time = Some("09:00".into());
        upd.end_time = Some("18:00".into());
        let r2 = update_rule(&c, r1.id, &upd).unwrap();
        assert_eq!(r2.label, "休息一下 ☕");
        assert_eq!(r2.start_time.as_deref(), Some("09:00"));
        assert_eq!(load_rules(&c).unwrap().len(), 1); // 仍是 1 条

        // 校验失败：kind / label / interval / HH:MM
        assert!(insert_rule(&c, &input("bogus", "x", 30)).is_err());
        assert!(insert_rule(&c, &input("custom", "  ", 30)).is_err());
        assert!(insert_rule(&c, &input("custom", &"x".repeat(141), 30)).is_err());
        assert!(insert_rule(&c, &input("custom", "x", 0)).is_err()); // 非 todo 至少 1
        assert!(insert_rule(&c, &input("custom", "x", 1441)).is_err());
        let mut bad = input("custom", "x", 30);
        bad.start_time = Some("25:00".into());
        assert!(insert_rule(&c, &bad).is_err());
        // todo kind 允许 interval=0
        assert!(insert_rule(&c, &input("todo", "交报告", 0)).is_ok());

        // 删除 + 不存在
        delete_rule(&c, r1.id).unwrap();
        assert!(load_rules(&c).unwrap().iter().all(|r| r.id != r1.id));
        assert!(update_rule(&c, r1.id, &upd).is_err());
        assert!(delete_rule(&c, r1.id).is_ok()); // 幂等
    }

    #[test]
    fn logs_trigger_ack_dismiss_and_stats_tc_rm_13() {
        let c = conn();
        let r1 = insert_rule(&c, &input("hydration", "该喝水啦 💧", 30)).unwrap();
        let r2 = insert_rule(&c, &input("rest", "休息一下 ☕", 60)).unwrap();

        // 触发 3 条：r1 两条（一条确认、一条自动）、r2 一条（烟花）
        let l1 = insert_log(&c, r1.id, &rfc(1000)).unwrap();
        let l2 = insert_log(&c, r1.id, &rfc(2000)).unwrap();
        let l3 = insert_log(&c, r2.id, &rfc(3000)).unwrap();

        // 点击确认：acked_at + dismissed_via='bubble'（TC-RM-04）
        ack_log(&c, l1, &rfc(1500)).unwrap();
        // 自动消失：dismissed_via='auto'（TC-RM-03）
        dismiss_log(&c, l2, "auto").unwrap();
        // 烟花结束：'fireworks'（TC-RM-09）
        dismiss_log(&c, l3, "fireworks").unwrap();
        // 非法 via 拒绝
        assert!(dismiss_log(&c, l1, "bogus").is_err());
        // 已 dismiss 的行不被覆盖（ack 晚到不覆盖 auto）
        ack_log(&c, l2, &rfc(9999)).unwrap();
        let (via, acked): (String, Option<String>) = c
            .query_row(
                "SELECT dismissed_via, acked_at FROM reminder_logs WHERE id = ?1",
                [l2],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .unwrap();
        assert_eq!(via, "auto");
        assert!(acked.is_none());

        let row = |id: i64| {
            c.query_row(
                "SELECT dismissed_via, acked_at FROM reminder_logs WHERE id = ?1",
                [id],
                |r| Ok((r.get::<_, String>(0)?, r.get::<_, Option<String>>(1)?)),
            )
            .unwrap()
        };
        assert_eq!(row(l1), ("bubble".to_string(), Some(rfc(1500))));
        assert_eq!(row(l3).0, "fireworks");

        // stats：hydration total=2、rest total=1；today 与时间戳同日（测试时间戳即当下时区）
        let mut s = stats(&c).unwrap();
        s.sort_by(|a, b| b.total.cmp(&a.total));
        assert_eq!(s.len(), 2);
        assert_eq!(s[0].kind, "hydration");
        assert_eq!(s[0].total, 2);
        assert!(s[0].today <= 2);
        assert_eq!(s[1].kind, "rest");
        assert_eq!(s[1].total, 1);
    }

    #[test]
    fn reload_rebuilds_from_db_and_keeps_pause() {
        let c = conn();
        let r1 = insert_rule(&c, &input("hydration", "水", 30)).unwrap();
        let mut st = RemindersState::load(&c).unwrap();
        assert_eq!(st.rules.len(), 1);
        assert!(!st.paused);

        // 模拟触发：db 写 last_triggered_at（取真实时钟 10 分钟前，保证锚点在未来侧）
        let t0 = now_ms();
        mark_triggered(&c, r1.id, &rfc(t0 - 600_000)).unwrap();
        st.reload(&c).unwrap();
        // reload 后 next_due 以 db 的 last_triggered_at 为锚（不被重置）
        assert_eq!(st.rules[0].next_due_ms, t0 - 600_000 + 1_800_000);

        // 暂停持久化
        set_paused(&c, true);
        let st2 = RemindersState::load(&c).unwrap();
        assert!(st2.paused);
        set_paused(&c, false);
        assert!(!is_paused(&c));

        // 全局烟花开关持久化
        assert!(!fireworks_global(&c));
        set_fireworks_global(&c, true);
        assert!(fireworks_global(&c));
    }

    #[test]
    fn rfc3339_roundtrip_and_minute_of_day() {
        let ms = 1_773_000_000_123i64;
        let s = rfc(ms);
        assert_eq!(parse_rfc3339_ms(&s), Some(ms));
        assert!(parse_rfc3339_ms("not a date").is_none());
        let m = now_minute_of_day();
        assert!((0..1440).contains(&m));
    }

    // ---- 绽放点 = 宠物所处显示器中轴 + 屏高 0.3（DESIGN §5.3 用户定案 2026-08-16） ----

    #[test]
    fn burst_point_single_display_dpr2() {
        // 本机实测配置：主屏 2940×1912 物理（dpr=2），fireworks 窗口铺满全屏
        // → 逻辑坐标 (735, 286.8) = 中轴 x=1470/2 + y=1912×0.3=573.6/2
        let (tx, ty) = monitor_burst_point_in_window(0, 0, 2940, 1912, 0, 0, 2.0);
        assert!((tx - 735.0).abs() < 1e-9);
        assert!((ty - 286.8).abs() < 1e-9);
    }

    #[test]
    fn burst_point_secondary_display_relative_to_window() {
        // 次屏从 x=2940 起（2940×1912 物理），fireworks 窗口已铺到次屏
        // → 绽放点在窗口坐标系内仍是该屏中轴 + 0.3 屏高 (735, 286.8)（与屏号无关）
        let (tx, ty) = monitor_burst_point_in_window(2940, 0, 2940, 1912, 2940, 0, 2.0);
        assert!((tx - 735.0).abs() < 1e-9);
        assert!((ty - 286.8).abs() < 1e-9);
        // 窗口未对齐显示器（窗口在主屏、宠物所在屏为次屏）：坐标带偏移，
        // 供 clamp 前的原始值（运行时 cover_monitor 会先对齐，此分支仅兜底语义）
        let (tx, ty) = monitor_burst_point_in_window(2940, 0, 2940, 1912, 0, 0, 1.0);
        assert!((tx - 4410.0).abs() < 1e-9);
        assert!((ty - 573.6).abs() < 1e-9);
    }

    // ---- M7：todo 派生一次性提醒（TC-TD-03/06/08；M4 P2 ③ validate 收紧） ----

    /// 本地时区基准："2026-08-18T15:30" → 当日本地 15:30 的 epoch ms。
    fn due_ms(y: i32, mo: u32, d: u32, h: u32, mi: u32) -> i64 {
        use chrono::TimeZone;
        Local
            .with_ymd_and_hms(y, mo, d, h, mi, 0)
            .unwrap()
            .timestamp_millis()
    }

    #[test]
    fn parse_due_like_ms_formats() {
        let expected = due_ms(2026, 8, 18, 15, 30);
        assert_eq!(parse_due_like_ms("2026-08-18T15:30"), Some(expected));
        // 纯日期 → 当日 00:00 本地
        assert_eq!(parse_due_like_ms("2026-08-18"), Some(due_ms(2026, 8, 18, 0, 0)));
        assert_eq!(parse_due_like_ms("  2026-08-18T15:30  "), Some(expected));
        assert_eq!(parse_due_like_ms("not a date"), None);
        assert_eq!(parse_due_like_ms("2026-8-18T15:30"), None); // 非零填充拒绝
        assert_eq!(parse_due_like_ms("2026-08-18T15:30:00"), None); // 带秒拒绝（格式恒 %H:%M）
    }

    #[test]
    fn todo_rule_next_due_follows_absolute_start_time() {
        // TC-TD-03：next_due = start_time（due_date - remind_before），不是"立即"
        let start_ms = due_ms(2026, 8, 18, 15, 25); // due 15:30 - before 5min
        let rule = ReminderRule {
            id: 11,
            kind: "todo".into(),
            label: "交报告".into(),
            interval_minutes: 0,
            start_time: Some("2026-08-18T15:25".into()),
            end_time: None,
            enabled: true,
            use_fireworks: false,
            last_triggered_at: None,
            source_todo_id: Some(3),
            todo_due_at: Some("2026-08-18T15:30".into()),
            created_at: rfc(0),
        };
        assert_eq!(compute_next_due(&rule, 0), start_ms);
        // start 已过（停机错过）→ 下一 tick 补触发一次（仍只一次）
        assert_eq!(compute_next_due(&rule, start_ms + 60_000), start_ms);
        // 触发后 → 永不再触发（TC-TD-06：last_triggered_at 唯一防重来源）
        let mut fired = rule.clone();
        fired.last_triggered_at = Some(rfc(start_ms));
        assert_eq!(compute_next_due(&fired, start_ms + 60_000), i64::MAX);
    }

    #[test]
    fn todo_rule_fires_once_at_start_time_in_collect_due() {
        let start_ms = due_ms(2026, 8, 18, 15, 25);
        let rule = ReminderRule {
            id: 12,
            kind: "todo".into(),
            label: "交报告".into(),
            interval_minutes: 0,
            start_time: Some("2026-08-18T15:25".into()),
            end_time: None,
            enabled: true,
            use_fireworks: false,
            last_triggered_at: None,
            source_todo_id: Some(4),
            todo_due_at: Some("2026-08-18T15:30".into()),
            created_at: rfc(0),
        };
        let mut st = state_with(rule, 0);
        // 未到点（含 start_time 是绝对时刻而非 HH:MM 窗口的判定）→ 不触发
        assert!(st.collect_due(start_ms - 1, &rfc(start_ms - 1), 0).is_empty());
        // 到点 → 触发一次；之后（即便再过很久）不再触发（TC-TD-06）
        let fired = st.collect_due(start_ms, &rfc(start_ms), 0);
        assert_eq!(fired.len(), 1);
        assert_eq!(fired[0].kind, "todo");
        assert_eq!(fired[0].todo_due_at.as_deref(), Some("2026-08-18T15:30"));
        assert_eq!(st.rules[0].next_due_ms, i64::MAX);
        assert!(st.collect_due(start_ms + 3_600_000, &rfc(start_ms + 3_600_000), 0).is_empty());
    }

    #[test]
    fn todo_rule_single_fire_survives_reload_from_db_tc_td_06() {
        // 触发落库（mark_triggered）后 reload → 不重复触发（跨重启同理由此保证）
        let c = conn();
        let mut input = input("todo", "交报告", 0);
        input.start_time = Some("2030-01-01T09:00".into());
        let r = insert_rule(&c, &input).unwrap();
        mark_triggered(&c, r.id, &rfc(now_ms() - 60_000)).unwrap();
        let st = RemindersState::load(&c).unwrap();
        assert_eq!(st.rules[0].next_due_ms, i64::MAX);
    }

    #[test]
    fn validate_input_todo_kind_forces_interval_zero_tc() {
        // M4 P2 ③（M7 清偿）：todo kind 恒 interval=0，>0 一律拒绝
        assert!(validate_input(&input("todo", "交报告", 0)).is_ok());
        assert!(validate_input(&input("todo", "交报告", 1)).is_err());
        assert!(validate_input(&input("todo", "交报告", 30)).is_err());
        // 派生规则的 start_time 是绝对时刻（非 HH:MM），必须被 upsert 入口接受
        let mut abs = input("todo", "交报告", 0);
        abs.start_time = Some("2026-08-18T15:25".into());
        assert!(validate_input(&abs).is_ok());
        let mut bad = input("todo", "交报告", 0);
        bad.start_time = Some("15:25".into()); // todo kind 不接受 HH:MM（语义为绝对时刻）
        assert!(validate_input(&bad).is_err());
        // 非 todo kind 间隔下限仍为 1（interval=0 拒绝）
        assert!(validate_input(&input("custom", "x", 0)).is_err());
        assert!(validate_input(&input("hydration", "x", 1)).is_ok());
    }
}
