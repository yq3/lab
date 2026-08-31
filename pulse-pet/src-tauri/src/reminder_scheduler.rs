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

use crate::plog;
use std::collections::VecDeque;
use std::sync::{Arc, Mutex};

use chrono::{DateTime, Datelike, Duration as ChronoDuration, Local, NaiveDate, NaiveDateTime, SecondsFormat, TimeZone, Timelike};
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
/// v2 M4（§4.3）：daily/once 补跑宽限窗（notify/exec 同窗——用户单一口径裁定；
/// interval 维持 v1 错过不补）。超窗 → skipped（exec 落 action_logs，notify 不落）。
pub const CATCHUP_WINDOW_MS: i64 = 15 * 60_000;
/// v2 M4（§4.3）：snooze「稍后 10 分钟」窗口。
pub const SNOOZE_MS: i64 = 10 * 60_000;

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

/// 提醒/任务规则（reminders 表行，DESIGN §5.4 / V2-DESIGN §4.2；serde 字段与
/// TS `ReminderRule` 一致）。v2 M4 +7 列（动作/调度泛化 + snooze/skipped 记账）。
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
    /// v2 M4：动作类型（'notify' 默认 | 'exec'）。
    pub action_type: String,
    /// v2 M4：动作参数 JSON 文本（exec = {"command","cwd?","timeout_minutes?","tpl_agent?","tpl_flags?"}——Part B 起；旧键 opencode_auto 读兼容，validate 均容忍）。
    pub action_params: Option<String>,
    /// v2 M4：调度类型（'interval' 默认 | 'daily' | 'once'；P2-6：daily/once 行
    /// interval_minutes 恒 0）。
    pub schedule_kind: String,
    /// v2 M4：定点时刻（daily → "HH:MM"；once → "YYYY-MM-DDTHH:MM"；interval → NULL）。
    pub schedule_at: Option<String>,
    /// v2 M4：daily 的星期过滤 JSON "[1,3,5]"（1=周一…7=周日；NULL/空 = 每天）。
    pub schedule_weekdays: Option<String>,
    /// v2 M4：snooze 顺延终点（RFC3339；触发时清空）。
    pub snooze_until: Option<String>,
    /// v2 M4：skipped 判定时刻（RFC3339；与 last_triggered_at 分离——P3-2，防
    /// skipped 写入使 3min dedup 拒绝手动补跑）。
    pub last_skipped_at: Option<String>,
}

/// CRUD 入参（id 由 command 参数单独传）。v2 M4 +5 字段（serde 缺省 → v1
/// 载荷不带新字段仍可反序列化，notify/interval 默认）。
#[derive(Debug, Clone, Deserialize)]
pub struct ReminderInput {
    pub kind: String,
    pub label: String,
    pub interval_minutes: i64,
    pub start_time: Option<String>,
    pub end_time: Option<String>,
    pub enabled: bool,
    pub use_fireworks: bool,
    /// v2 M4：'notify'（缺省）| 'exec'。
    #[serde(default)]
    pub action_type: String,
    /// v2 M4：动作参数 JSON 文本（exec 必填；notify 忽略存 NULL）。
    #[serde(default)]
    pub action_params: Option<String>,
    /// v2 M4：'interval'（缺省）| 'daily' | 'once'。
    #[serde(default)]
    pub schedule_kind: String,
    /// v2 M4：daily → "HH:MM"；once → "YYYY-MM-DDTHH:MM"。
    #[serde(default)]
    pub schedule_at: Option<String>,
    /// v2 M4：daily 的星期过滤 JSON 文本。
    #[serde(default)]
    pub schedule_weekdays: Option<String>,
}

/// normalize 后的规则字段（insert/update 写库的单一来源；kind 切换时无关
/// 字段在此重置——P2-6）。
pub struct NormalizedRule {
    pub kind: String,
    pub label: String,
    pub action_type: String,
    pub action_params: Option<String>,
    pub schedule_kind: String,
    pub schedule_at: Option<String>,
    pub schedule_weekdays: Option<String>,
    pub interval_minutes: i64,
    pub start_time: Option<String>,
    pub end_time: Option<String>,
    pub enabled: bool,
    pub use_fireworks: bool,
}

// §十二 F14（2026-08-28）：ReminderStat/stats()/reminders_stats 命令随面板
// 「历史统计」区移除一并清退——reminder_logs 记账写路径保留（排障/未来燃料）。

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

/// epoch 毫秒 → RFC3339 本地时间串（snooze/调度溯源写表用）。
pub fn ms_to_rfc3339(ms: i64) -> Option<String> {
    DateTime::from_timestamp_millis(ms).map(|d| {
        d.with_timezone(&Local)
            .to_rfc3339_opts(SecondsFormat::Millis, true)
    })
}

// ---------------------------------------------------------------------------
// v2 M4：daily/once 定点调度纯函数（§4.3）
// ---------------------------------------------------------------------------

/// 星期过滤 JSON "[1,3,5]" → 合法值集合（1=周一…7=周日）；NULL/空/解析失败
/// → 空 Vec（= 每天，宽容防 panic；写入口 validate 已拒绝非法 JSON）。
pub fn parse_weekdays(s: Option<&str>) -> Vec<u32> {
    s.and_then(|s| serde_json::from_str::<Vec<u32>>(s).ok())
        .unwrap_or_default()
        .into_iter()
        .filter(|d| (1..=7).contains(d))
        .collect()
}

fn weekday_matches(weekdays: &[u32], date: NaiveDate) -> bool {
    weekdays.is_empty()
        || weekdays.contains(&(date.weekday().num_days_from_monday() as u32 + 1))
}

/// 本地某日 minute_of_day 时刻的 epoch 毫秒（DST 间隙/歧义取首个可行解释）。
fn local_day_ms(date: NaiveDate, minute_of_day: i64) -> Option<i64> {
    let dt = date.and_hms_opt(
        (minute_of_day / 60) as u32,
        (minute_of_day % 60) as u32,
        0,
    )?;
    let local = Local.from_local_datetime(&dt);
    local
        .single()
        .or_else(|| local.earliest())
        .map(|d| d.timestamp_millis())
}

/// 下一个匹配日 HH:MM（严格 > now；最多向后找 8 天，防御性兜底 now）。
pub fn next_daily_occurrence(now_ms: i64, hhmm: i64, weekdays: &[u32]) -> i64 {
    let today = Local
        .timestamp_millis_opt(now_ms)
        .single()
        .map(|d| d.date_naive())
        .unwrap_or_else(|| Local::now().date_naive());
    for off in 0..=8i64 {
        let Some(day) = today.checked_add_signed(ChronoDuration::days(off)) else {
            break;
        };
        if !weekday_matches(weekdays, day) {
            continue;
        }
        if let Some(ms) = local_day_ms(day, hhmm) {
            if ms > now_ms {
                return ms;
            }
        }
    }
    now_ms
}

/// 最近一个 ≤ now 且 ≥ floor 的匹配日 HH:MM（"本周期"锚：floor 通常为
/// created_at——新规则的首次发生只算创建之后的）。
pub fn prev_daily_occurrence(
    now_ms: i64,
    hhmm: i64,
    weekdays: &[u32],
    floor_ms: i64,
) -> Option<i64> {
    let today = Local
        .timestamp_millis_opt(now_ms)
        .single()
        .map(|d| d.date_naive())
        .unwrap_or_else(|| Local::now().date_naive());
    for off in 0..=7i64 {
        let day = today.checked_sub_signed(ChronoDuration::days(off))?;
        if !weekday_matches(weekdays, day) {
            continue;
        }
        if let Some(ms) = local_day_ms(day, hhmm) {
            if ms <= now_ms && ms >= floor_ms {
                return Some(ms);
            }
        }
    }
    None
}

/// 已处理时刻（last_triggered / last_skipped 的较大者；都没有 → None）。
fn last_handled_ms(rule: &ReminderRule) -> Option<i64> {
    let t = rule.last_triggered_at.as_deref().and_then(parse_rfc3339_ms);
    let s = rule.last_skipped_at.as_deref().and_then(parse_rfc3339_ms);
    match (t, s) {
        (Some(t), Some(s)) => Some(t.max(s)),
        (t, s) => t.or(s),
    }
}

/// 触发/跳过/snooze 重发后的常规推进（§4.3；collect_due / force_fire_one /
/// tasks_skip_once 共用）。todo 派生行 → MAX（M7 一次性语义不变）。
pub fn advance_after_fire(rule: &ReminderRule, base_ms: i64) -> i64 {
    if rule.kind == "todo" {
        return i64::MAX;
    }
    match rule.schedule_kind.as_str() {
        "daily" => {
            let hhmm = rule
                .schedule_at
                .as_deref()
                .and_then(parse_hhmm)
                .unwrap_or(0);
            let wd = parse_weekdays(rule.schedule_weekdays.as_deref());
            next_daily_occurrence(base_ms, hhmm, &wd)
        }
        "once" => i64::MAX,
        // interval（v1 行为）：锚点顺延
        _ => base_ms.saturating_add(rule.interval_minutes * 60_000),
    }
}

/// 计算规则的 next_due（加载/reload 后；v2 M4 §4.3 按 schedule_kind 分派）：
/// - **snooze_until 未过期 → 优先于常规计算直接返回**（P1-1：重发本次；非
///   max——触发后常规 next_due 已是未来，max 会吞掉 snooze）；过期 → 静默
///   丢弃回落常规（N3 已知边界）；
/// - `kind == "todo"`（M7 派生行，不迁移）：v1 逻辑不变（interval=0 一次性：
///   未触发 → start_time 绝对时刻；已触发 → MAX）；
/// - `interval`：v1 逻辑不变（锚点 + interval；错过不补，TC-RM-02 精神）；
/// - `daily`：本周期 = 最近一个 ≥ created 且 ≤ now 的匹配日 HH:MM——未处理
///   （max(last_triggered, last_skipped) 早于它）→ 返回它（可能是过去 → 由
///   tick 的补跑窗判定：窗内触发 / 超窗 skipped，即 **reload 错过检测 P2-5**，
///   「今早跑了没」重启后仍可对账）；已处理 → 下一个匹配日；
/// - `once`：schedule_at 绝对时刻（过去同样交补跑窗判定）；已触发/已跳过
///   （last_handled ≥ schedule_at）→ `i64::MAX` 终态（跨重启成立，N1 ②）。
pub fn compute_next_due(rule: &ReminderRule, now_ms: i64) -> i64 {
    // snooze 优先（P1-1）
    if let Some(s) = rule.snooze_until.as_deref().and_then(parse_rfc3339_ms) {
        if s > now_ms {
            return s;
        }
        // 过期 → 静默丢弃（N3：notify 无害）
    }
    if rule.kind == "todo" {
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
    match rule.schedule_kind.as_str() {
        "daily" => {
            let Some(hhmm) = rule.schedule_at.as_deref().and_then(parse_hhmm) else {
                // 非法 daily 行（不应出现，validate 拦截）→ 保守按已完结处理
                return i64::MAX;
            };
            let wd = parse_weekdays(rule.schedule_weekdays.as_deref());
            let created = parse_rfc3339_ms(&rule.created_at).unwrap_or(now_ms);
            if let Some(prev) = prev_daily_occurrence(now_ms, hhmm, &wd, created) {
                let handled = last_handled_ms(rule);
                if handled.map_or(true, |h| h < prev) {
                    return prev; // 本周期未处理（可能已过 → tick 补跑窗判定）
                }
            }
            next_daily_occurrence(now_ms, hhmm, &wd)
        }
        "once" => {
            let Some(at) = rule.schedule_at.as_deref().and_then(parse_due_like_ms) else {
                return i64::MAX;
            };
            match last_handled_ms(rule) {
                Some(h) if h >= at => i64::MAX,
                _ => at,
            }
        }
        // interval：v1 逻辑不变（错过不补）
        _ => {
            let interval = rule.interval_minutes;
            if interval <= 0 {
                // 非 todo 的 0 间隔（不应出现，validate 拦截）→ 一次性处理
                return i64::MAX;
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
    /// v2 M4（§4.5）：exec 并发满 2 时的内存等待队列（不写 running 行——
    /// 排队中无进程无 running 行，App 退出/崩溃时自然消失无残留）。
    pub pending_execs: VecDeque<crate::action_exec::PendingExec>,
    /// v2 M4：完成回调 → 调度器 select 分支出队的通知通道（spawn_scheduler 注入）。
    pub slot_free_tx: Option<tokio::sync::mpsc::Sender<()>>,
    /// v2 M4 R4（committer P2-1）：**exec 槽位预留计数（同步化硬上限）**。
    /// dispatch/drain 在本 struct 的锁内判定并自增（与 collect_due 同一锁
    /// 序列化）——批量分派（run_tick 同步循环 / 多线程并发 dispatch）下第
    /// 3 个必入队不超发；run_task 完成回调锁内递减后经 slot_free 通知出队。
    /// 取代原 `RunningTasks.len()` 判定（登记表条目在 spawn 任务首个 poll 才
    /// 异步插入，同步循环里读不到刚分发的任务——竞态软上限）。reload 不重置
    /// （在飞任务的完成回调仍会递减，重置会破坏记账导致超发）。
    pub active_execs: usize,
}

/// 一次 tick 的触发决策（v2 M4：collect_due 返回 (fired, skipped)——skipped
/// 列表随 fired 一起返回调用方落库，N1）。
#[derive(Debug, Clone)]
pub struct FiredRule {
    pub rule: ReminderRule,
    /// 原定触发时刻（补跑窗内触发 = 错过的 next_due；准点触发 ≈ 触发时刻；
    /// exec 写 action_logs.scheduled_at 溯源）。
    pub scheduled_at_ms: i64,
}

/// skipped 判定记录（两来源：超窗 / 暂停；调用方写 last_skipped_at + 推进
/// 已在内存完成 + exec 落 action_logs(status='skipped')）。
/// 004：携 action_params 供 persist_skipped 提取 command 快照（判定时刻配置）。
#[derive(Debug, Clone)]
pub struct SkippedRule {
    pub id: i64,
    pub label: String,
    pub action_type: String,
    pub action_params: Option<String>,
    /// 错过的原定时刻。
    pub scheduled_at_ms: i64,
    pub reason: SkipReason,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SkipReason {
    /// 补跑窗外错过（15 分钟）。
    MissedWindow,
    /// 暂停期间到期（不跑不补、记 skipped）。
    Paused,
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
    /// v2 M2：走 `load_active_rules`（调度器专用过滤——禁用插件的 todo 派生
    /// 行不进内存，禁用期间到期不触发；重启用后 reload 恢复）。
    pub fn reload(&mut self, conn: &Connection) -> Result<(), String> {
        let rules = load_active_rules(conn)?;
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

    /// 一次 tick 的到期决策（v2 M4 §4.3）：
    /// - **暂停分支按 schedule_kind 分派**（P2-4/P2-6）：interval 类维持 v1
    ///   顺延；daily/once 到期**不顺延、不触发**，到期即记 skipped（记后推进
    ///   next_due 防每 tick 重复判定；同款清空未过期 snooze_until，P3-5）；
    ///   todo 派生行 v1 行为不变（暂停不处置）；
    /// - 常规分支：窗口（v1）→ **补跑窗**（daily/once：now − next_due ≤ 15min
    ///   正常触发（last_triggered 记实际时刻）；超窗 skipped + 推进 + 记
    ///   last_skipped_at）→ 去重 → 触发（next_due 按 kind 推进、清 snooze）。
    ///
    /// 返回 `(fired, skipped)`：内存的 last_triggered_at / last_skipped_at /
    /// next_due 已同步更新，db 落库由调用方（run_tick / persist_skipped）负责。
    pub fn collect_due(
        &mut self,
        now_ms: i64,
        now_ts: &str,
        minute_of_day: i64,
    ) -> (Vec<FiredRule>, Vec<SkippedRule>) {
        if self.paused {
            let mut skipped = Vec::new();
            for rs in &mut self.rules {
                if !rs.rule.enabled || rs.rule.kind == "todo" || now_ms < rs.next_due_ms {
                    continue;
                }
                match rs.rule.schedule_kind.as_str() {
                    "daily" | "once" => {
                        let sched = rs.next_due_ms;
                        let rule = rs.rule.clone();
                        rs.rule.last_skipped_at = Some(now_ts.to_string());
                        rs.rule.snooze_until = None; // P3-5
                        rs.next_due_ms = advance_after_fire(&rule, now_ms);
                        skipped.push(SkippedRule {
                            id: rule.id,
                            label: rule.label.clone(),
                            action_type: rule.action_type.clone(),
                            action_params: rule.action_params.clone(),
                            scheduled_at_ms: sched,
                            reason: SkipReason::Paused,
                        });
                    }
                    // interval：v1 顺延（恢复后不瞬间补弹，TC-RM-08）
                    _ => {
                        rs.next_due_ms = now_ms.saturating_add(rs.rule.interval_minutes * 60_000);
                    }
                }
            }
            return (Vec::new(), skipped);
        }
        let mut fired = Vec::new();
        let mut skipped = Vec::new();
        for rs in &mut self.rules {
            if !rs.rule.enabled || now_ms < rs.next_due_ms {
                continue;
            }
            // M7：todo 派生规则的 start_time 是绝对时刻（非 HH:MM 窗口），
            // 到期即触发，不走活跃窗口判定。daily/once 行 start/end 已被
            // validate 清空（P2-6），窗口判定天然放行。
            if rs.rule.kind != "todo" {
                let start = rs.rule.start_time.as_deref().and_then(parse_hhmm);
                let end = rs.rule.end_time.as_deref().and_then(parse_hhmm);
                if !in_window(minute_of_day, start, end) {
                    continue;
                }
            }
            let sched = rs.next_due_ms;
            // 补跑窗（§4.3：daily/once 两 kind、notify/exec 两动作同窗；interval
            // 维持 v1 错过不补）
            if rs.rule.kind != "todo"
                && matches!(rs.rule.schedule_kind.as_str(), "daily" | "once")
                && now_ms.saturating_sub(sched) > CATCHUP_WINDOW_MS
            {
                let rule = rs.rule.clone();
                rs.rule.last_skipped_at = Some(now_ts.to_string());
                rs.rule.snooze_until = None; // P3-5：skipped 判定清未过期 snooze
                rs.next_due_ms = advance_after_fire(&rule, now_ms);
                skipped.push(SkippedRule {
                    id: rule.id,
                    label: rule.label.clone(),
                    action_type: rule.action_type.clone(),
                    action_params: rule.action_params.clone(),
                    scheduled_at_ms: sched,
                    reason: SkipReason::MissedWindow,
                });
                continue;
            }
            let last = rs.rule.last_triggered_at.as_deref().and_then(parse_rfc3339_ms);
            if !dedup_ok(last, now_ms) {
                continue; // 去重窗口内：不触发也不推进（到点后等去重窗口过去）
            }
            let mut rule = rs.rule.clone();
            rs.next_due_ms = advance_after_fire(&rule, now_ms);
            rule.last_triggered_at = Some(now_ts.to_string());
            rule.snooze_until = None; // 触发清空 snooze（内存；db 由 mark_triggered 清）
            rs.rule = rule.clone();
            fired.push(FiredRule {
                rule,
                scheduled_at_ms: sched,
            });
        }
        (fired, skipped)
    }

    /// 手动"试一试"（面板按钮）：跳过倒计时与窗口（预览语义），仍受暂停与
    /// 3 分钟去重约束；返回 (状态, 触发规则)。v2 M4：推进按 schedule_kind
    /// 分派（P3-9：exec 行 = 真实执行一次，结果气泡同正常触发）。
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
        rs.next_due_ms = advance_after_fire(&rs.rule, now_ms);
        rs.rule.last_triggered_at = Some(now_ts.to_string());
        Ok(("fired", Some(rs.rule.clone())))
    }

    /// 「跳过本次」（§4.3）：内存 next_due 即时推进（interval → +interval；
    /// daily → 下个匹配日；once → MAX），不触发不记录；**snooze_until 未过期
    /// 则一并清空（N2：写表 + 内存同清——防 reload 因 snooze 优先级复活被
    /// 跳过的重发）**。返回是否清了 snooze（调用方据此写表）。
    pub fn skip_once(&mut self, id: i64, now_ms: i64) -> Result<bool, String> {
        let Some(rs) = self.rules.iter_mut().find(|rs| rs.rule.id == id) else {
            return Err(format!("task #{id} 不存在"));
        };
        let snooze_active = rs
            .rule
            .snooze_until
            .as_deref()
            .and_then(parse_rfc3339_ms)
            .is_some_and(|s| s > now_ms);
        // 跳过的对象是"下一个到期"：以 max(now, next_due) 为基推进
        let base = now_ms.max(rs.next_due_ms);
        rs.next_due_ms = advance_after_fire(&rs.rule, base);
        if snooze_active {
            rs.rule.snooze_until = None;
        }
        Ok(snooze_active)
    }
}

// ---------------------------------------------------------------------------
// db 读写
// ---------------------------------------------------------------------------

/// 全字段 SELECT（v2 M4 +7 列）。
const RULE_COLUMNS: &str = "id, kind, label, interval_minutes, start_time, end_time, enabled, \
     use_fireworks, last_triggered_at, source_todo_id, todo_due_at, created_at, \
     action_type, action_params, schedule_kind, schedule_at, schedule_weekdays, \
     snooze_until, last_skipped_at";

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
        action_type: row.get("action_type")?,
        action_params: row.get("action_params")?,
        schedule_kind: row.get("schedule_kind")?,
        schedule_at: row.get("schedule_at")?,
        schedule_weekdays: row.get("schedule_weekdays")?,
        snooze_until: row.get("snooze_until")?,
        last_skipped_at: row.get("last_skipped_at")?,
    })
}

pub fn load_rules(conn: &Connection) -> Result<Vec<ReminderRule>, String> {
    let mut stmt = conn
        .prepare(&format!(
            "SELECT {RULE_COLUMNS} FROM reminders ORDER BY id"
        ))
        .map_err(|e| format!("load reminders: {e}"))?;
    let rows = stmt
        .query_map([], row_to_rule)
        .map_err(|e| format!("load reminders: {e}"))?;
    Ok(rows.filter_map(|r| r.ok()).collect())
}

/// 调度器专用过滤查询（v2 M2，V2-DESIGN §2.5 / TC-UI-08）：在 `load_rules`
/// 基础上排除 `kind='todo'` 且源插件 `enabled=0` 的行（禁用插件停派生提醒）。
///
/// - 源插件：v2 唯一有派生能力的插件 = `built-in-todo`（kind='todo' 行全部
///   源于它）；plugins 表缺行时保守视为启用（不因元数据缺失丢提醒）。
/// - `reminders_list` 照旧走 `load_rules` 全量（列表「可见但惰性」+ 前端徽标）。
pub fn load_active_rules(conn: &Connection) -> Result<Vec<ReminderRule>, String> {
    let todo_plugin_enabled: bool = conn
        .query_row(
            "SELECT enabled FROM plugins WHERE id = ?1",
            [crate::plugins::BUILTIN_TODO_ID],
            |r| r.get::<_, i64>(0),
        )
        .map(|v| v != 0)
        .unwrap_or(true);
    Ok(load_rules(conn)?
        .into_iter()
        .filter(|r| !(r.kind == "todo" && !todo_plugin_enabled))
        .collect())
}

fn rule_by_id(conn: &Connection, id: i64) -> Result<ReminderRule, String> {
    conn.query_row(
        &format!("SELECT {RULE_COLUMNS} FROM reminders WHERE id = ?1"),
        [id],
        row_to_rule,
    )
    .map_err(|e| format!("read reminder #{id}: {e}"))
}

/// v2 M4 normalize + 校验（Rust 权威，前端同规则预检；§4.2 P2-6）：
/// - action_type ∈ {notify, exec}（缺省 notify）；schedule_kind ∈
///   {interval, daily, once}（缺省 interval）；
/// - exec：action_params 必填 JSON 对象且过 ExecExecutor::validate
///   （JSON 解析失败拒绝，TC-M4-01-4）；kind 强制 custom（notify-kind 仅对
///   notify 有意义）；清 start/end 窗口；
/// - **kind 切换重置无关字段**：interval 行清 schedule_at/weekdays；daily/once
///   行清 start_time/end_time 窗口（防遗留窗口使 in_window 判定卡住导致误
///   skipped）；
/// - daily/once 行 interval_minutes 恒 0（P2-6 存储约定）；daily 的
///   schedule_at = "HH:MM" + weekdays 可选 JSON [1-7]（空 = 每天）；once 的
///   schedule_at = "YYYY-MM-DDTHH:MM" 且**过去时刻拒绝**（防创建即意外执行）；
/// - todo 派生行：v1 校验不变（interval 恒 0、绝对时刻），锁定 notify/interval。
pub fn normalize_input(input: &ReminderInput) -> Result<NormalizedRule, String> {
    const KINDS: &[&str] = &["hydration", "rest", "custom", "todo"];
    let action_type = match input.action_type.as_str() {
        "" | "notify" => "notify",
        "exec" => "exec",
        other => return Err(format!("action_type 非法：{other}（应为 notify/exec）")),
    };
    let schedule_kind = match input.schedule_kind.as_str() {
        "" | "interval" => "interval",
        "daily" => "daily",
        "once" => "once",
        other => {
            return Err(format!(
                "schedule_kind 非法：{other}（应为 interval/daily/once）"
            ))
        }
    };
    if !KINDS.contains(&input.kind.as_str()) {
        return Err(format!(
            "kind 非法：{}（应为 hydration/rest/custom/todo）",
            input.kind
        ));
    }
    // 单行化 + trim（与展示端 sanitizeBubbleText 同口径）
    let label: String = input.label.split_whitespace().collect::<Vec<_>>().join(" ");
    if label.is_empty() {
        return Err("label 不能为空".into());
    }
    if label.chars().count() > 140 {
        return Err("label 超长（≤140 字符）".into());
    }

    // todo 派生行：M7 语义不变（锁定 notify / interval / 0）
    if input.kind == "todo" {
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
        return Ok(NormalizedRule {
            kind: "todo".into(),
            label,
            action_type: "notify".into(),
            action_params: None,
            schedule_kind: "interval".into(),
            schedule_at: None,
            schedule_weekdays: None,
            interval_minutes: 0,
            start_time: input.start_time.clone().filter(|s| !s.is_empty()),
            end_time: input.end_time.clone().filter(|s| !s.is_empty()),
            enabled: input.enabled,
            use_fireworks: input.use_fireworks,
        });
    }

    // exec：action_params JSON 解析 + 执行器校验（TC-M4-01-4/07）——经分派
    // 注册表走 trait validate（§4.4 注册表为唯一分派入口）
    let mut action_params = None;
    if action_type == "exec" {
        let text = input
            .action_params
            .as_deref()
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .ok_or_else(|| "exec 需要 action_params（JSON 对象：command 等）".to_string())?;
        let v = crate::action_exec::parse_exec_params(text)?;
        let executor = crate::action_exec::executor_for("exec")
            .ok_or_else(|| "未知动作类型：exec".to_string())?;
        executor.validate(&v)?;
        action_params = Some(text.to_string());
    }

    // 非 todo 的 kind：exec 行强制 custom
    let kind = if action_type == "exec" {
        "custom".to_string()
    } else {
        input.kind.clone()
    };

    match schedule_kind {
        "daily" => {
            let at = input
                .schedule_at
                .as_deref()
                .map(str::trim)
                .filter(|s| !s.is_empty())
                .ok_or_else(|| "schedule_at 不能为空（daily 应为 HH:MM）".to_string())?;
            if parse_hhmm(at).is_none() {
                return Err(format!("schedule_at 非法：{at}（daily 应为 HH:MM）"));
            }
            let weekdays = normalize_weekdays(input.schedule_weekdays.as_deref())?;
            Ok(NormalizedRule {
                kind,
                label,
                action_type: action_type.to_string(),
                action_params,
                schedule_kind: "daily".into(),
                schedule_at: Some(at.to_string()),
                schedule_weekdays: weekdays,
                interval_minutes: 0, // P2-6
                start_time: None,     // P2-6：清窗口
                end_time: None,
                enabled: input.enabled,
                use_fireworks: input.use_fireworks,
            })
        }
        "once" => {
            let at = input
                .schedule_at
                .as_deref()
                .map(str::trim)
                .filter(|s| !s.is_empty())
                .ok_or_else(|| "schedule_at 不能为空（once 应为 YYYY-MM-DDTHH:MM）".to_string())?;
            let at_ms = parse_due_like_ms(at)
                .ok_or_else(|| format!("schedule_at 非法：{at}（once 应为 YYYY-MM-DDTHH:MM）"))?;
            if at_ms <= now_ms() {
                return Err(format!(
                    "schedule_at 已是过去时刻：{at}（once 须为未来时刻，防创建即意外执行）"
                ));
            }
            Ok(NormalizedRule {
                kind,
                label,
                action_type: action_type.to_string(),
                action_params,
                schedule_kind: "once".into(),
                schedule_at: Some(at.to_string()),
                schedule_weekdays: None,
                interval_minutes: 0, // P2-6
                start_time: None,    // P2-6：清窗口
                end_time: None,
                enabled: input.enabled,
                use_fireworks: input.use_fireworks,
            })
        }
        // interval：v1 语义（1-1440；HH:MM 窗口；清 schedule_at/weekdays）
        _ => {
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
            // exec 行不消费时间窗（表单不提供）：清掉
            let (st, en) = if action_type == "exec" {
                (None, None)
            } else {
                (
                    input.start_time.clone().filter(|s| !s.is_empty()),
                    input.end_time.clone().filter(|s| !s.is_empty()),
                )
            };
            Ok(NormalizedRule {
                kind,
                label,
                action_type: action_type.to_string(),
                action_params,
                schedule_kind: "interval".into(),
                schedule_at: None,      // P2-6：interval 行清定点字段
                schedule_weekdays: None,
                interval_minutes: input.interval_minutes,
                start_time: st,
                end_time: en,
                enabled: input.enabled,
                use_fireworks: input.use_fireworks,
            })
        }
    }
}

/// weekdays JSON 文本 → 规范化（空数组/None → None = 每天；非法元素/格式拒绝）。
fn normalize_weekdays(s: Option<&str>) -> Result<Option<String>, String> {
    let Some(text) = s.map(str::trim).filter(|t| !t.is_empty()) else {
        return Ok(None);
    };
    let parsed: Vec<i64> = serde_json::from_str(text)
        .map_err(|e| format!("schedule_weekdays 非法：{e}（应为 JSON 数组如 [1,3,5]）"))?;
    let mut days: Vec<u32> = Vec::new();
    for d in parsed {
        if !(1..=7).contains(&d) {
            return Err(format!("schedule_weekdays 元素非法：{d}（应为 1-7，1=周一…7=周日）"));
        }
        let d = d as u32;
        if !days.contains(&d) {
            days.push(d);
        }
    }
    if days.is_empty() {
        return Ok(None); // 空 = 每天
    }
    days.sort_unstable();
    serde_json::to_string(&days)
        .map(Some)
        .map_err(|e| format!("serialize weekdays: {e}"))
}

/// upsert 校验（v1 兼容入口：返回 normalize 后的 label；insert/update 走
/// `normalize_input` 全字段；测试与外部校验入口保留）。
#[cfg_attr(not(test), allow(dead_code))]
pub fn validate_input(input: &ReminderInput) -> Result<String, String> {
    normalize_input(input).map(|n| n.label)
}

pub fn insert_rule(conn: &Connection, input: &ReminderInput) -> Result<ReminderRule, String> {
    let n = normalize_input(input)?;
    let now = now_rfc3339();
    conn.execute(
        "INSERT INTO reminders (kind, label, interval_minutes, start_time, end_time, \
         enabled, use_fireworks, created_at, action_type, action_params, schedule_kind, \
         schedule_at, schedule_weekdays) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, \
         ?11, ?12, ?13)",
        params![
            n.kind,
            n.label,
            n.interval_minutes,
            n.start_time,
            n.end_time,
            n.enabled as i64,
            n.use_fireworks as i64,
            now,
            n.action_type,
            n.action_params,
            n.schedule_kind,
            n.schedule_at,
            n.schedule_weekdays,
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
    let n = normalize_input(input)?;
    let rows = conn
        .execute(
            "UPDATE reminders SET kind = ?1, label = ?2, interval_minutes = ?3, \
             start_time = ?4, end_time = ?5, enabled = ?6, use_fireworks = ?7, \
             action_type = ?9, action_params = ?10, schedule_kind = ?11, \
             schedule_at = ?12, schedule_weekdays = ?13, snooze_until = NULL \
             WHERE id = ?8",
            params![
                n.kind,
                n.label,
                n.interval_minutes,
                n.start_time,
                n.end_time,
                n.enabled as i64,
                n.use_fireworks as i64,
                id,
                n.action_type,
                n.action_params,
                n.schedule_kind,
                n.schedule_at,
                n.schedule_weekdays,
            ],
        )
        .map_err(|e| format!("update reminder #{id}: {e}"))?;
    if rows == 0 {
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

/// 自动消失 / 烟花结束 / snooze 结案回报（via = "auto" | "fireworks" | "snooze"；
/// TC-RM-03/09 + v2 M4 TC-M4-13）。
pub fn dismiss_log(conn: &Connection, log_id: i64, via: &str) -> Result<(), String> {
    if via != "auto" && via != "fireworks" && via != "snooze" {
        return Err(format!("dismissed_via 非法：{via}（应为 auto/fireworks/snooze）"));
    }
    conn.execute(
        "UPDATE reminder_logs SET dismissed_via = ?2 WHERE id = ?1 AND dismissed_via IS NULL",
        params![log_id, via],
    )
    .map_err(|e| format!("dismiss reminder_log {log_id}: {e}"))?;
    Ok(())
}

/// 按天更新 last_triggered_at（触发路径落库）。v2 M4：触发即清 snooze_until
/// （§4.3——snooze 重发触发时清空，按 kind 常规推进已由内存完成）。
pub fn mark_triggered(conn: &Connection, id: i64, ts: &str) -> Result<(), String> {
    conn.execute(
        "UPDATE reminders SET last_triggered_at = ?2, snooze_until = NULL WHERE id = ?1",
        params![id, ts],
    )
    .map_err(|e| format!("mark triggered #{id}: {e}"))?;
    Ok(())
}

/// v2 M4（N1/P3-5）：skipped 判定落库——写 last_skipped_at（与 last_triggered
/// 分离，防 3min dedup 拒绝手动补跑）+ 清 snooze_until（未过期同清）。
/// next_due 推进不持久化（内存态；reload 由 last_skipped_at 重算，与 v1
/// last_triggered 同构）。
pub fn mark_skipped(conn: &Connection, id: i64, ts: &str) -> Result<(), String> {
    conn.execute(
        "UPDATE reminders SET last_skipped_at = ?2, snooze_until = NULL WHERE id = ?1",
        params![id, ts],
    )
    .map_err(|e| format!("mark skipped #{id}: {e}"))?;
    Ok(())
}

// ---------------------------------------------------------------------------
// v2 M4：action_logs（exec 执行历史；notify 维持 reminder_logs 不双写）
// ---------------------------------------------------------------------------

/// action_logs 行（serde 与 TS `ActionLog` 一致）。
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct ActionLog {
    pub id: i64,
    pub reminder_id: i64,
    /// 冗余快照（规则删除后类型仍可读）。
    pub action_type: String,
    /// 当时任务名快照（004；沿用来源列 reminders.label 同名——规则改名/
    /// 删除不影响历史；迁移前旧行 NULL → 前端「未记录」）。
    pub label: Option<String>,
    /// 当时配置的任务命令快照（004；action_params.command；解析不出 → NULL）。
    /// 005 起「实际执行命令」不再单列——命令串逐字节原样传给 sh/powershell
    ///（目录经进程属性生效），实录与配置恒同值（routine-exec.md Part C）。
    pub command: Option<String>,
    /// 当时工作目录快照（005；action_params.cwd 非空值；未配置 → NULL）——
    /// 「当时在哪个目录执行」的时点实录（规则改/删后仍可回查）。
    pub cwd: Option<String>,
    pub status: String,
    /// i18n 模板键（`task.summary.*`；参数化键 `key:arg`——P3-3 展示按语言渲染）。
    pub summary: String,
    pub output_tail: Option<String>,
    pub exit_code: Option<i32>,
    pub started_at: String,
    pub finished_at: Option<String>,
    pub scheduled_at: Option<String>,
}

/// insert running 态日志（spawn 时刻写；summary 置空串，终态回写补齐）。
/// 快照：label = 派发时刻 rule.label；command = 当时配置命令（与实际执行
/// 同串）；cwd = 当时工作目录（未配置 → NULL）。
pub fn insert_action_log_running(
    conn: &Connection,
    reminder_id: i64,
    action_type: &str,
    label: &str,
    command: Option<&str>,
    cwd: Option<&str>,
    started_at: &str,
    scheduled_at: &str,
) -> Result<i64, String> {
    conn.execute(
        "INSERT INTO action_logs (reminder_id, action_type, label, command, cwd, \
         status, summary, started_at, scheduled_at) \
         VALUES (?1, ?2, ?3, ?4, ?5, 'running', '', ?6, ?7)",
        params![reminder_id, action_type, label, command, cwd, started_at, scheduled_at],
    )
    .map_err(|e| format!("insert action_log: {e}"))?;
    Ok(conn.last_insert_rowid())
}

/// insert skipped 态日志（超窗/暂停两来源；finished_at = 判定时刻）。
/// 快照 label/command/cwd = 判定时刻配置（「配置了但没跑」的完整上下文）。
pub fn insert_action_log_skipped(
    conn: &Connection,
    reminder_id: i64,
    label: &str,
    command: Option<&str>,
    cwd: Option<&str>,
    summary_key: &str,
    scheduled_at: &str,
    finished_at: &str,
) -> Result<i64, String> {
    conn.execute(
        "INSERT INTO action_logs (reminder_id, action_type, label, command, cwd, status, summary, \
         started_at, finished_at, scheduled_at) \
         VALUES (?1, 'exec', ?2, ?3, ?4, 'skipped', ?5, ?6, ?6, ?7)",
        params![reminder_id, label, command, cwd, summary_key, finished_at, scheduled_at],
    )
    .map_err(|e| format!("insert skipped action_log: {e}"))?;
    Ok(conn.last_insert_rowid())
}

/// 终态回写（ok/failed；v2 M4 执行链完成路径）。
/// R2（TC-M4-15-1 P2 竞态修复）：**`WHERE status='running'` 守卫**——只写仍
/// 在 running 的行。退出处置（abort）先行结案为 interrupted 后，被杀进程
/// 唤醒的完成回调在此被拦下（0 行更新），「App 退出中断」summary 不被
/// 通用 failed 覆盖；反向（自然完成先落库）同理不被 abort 覆盖——两个
/// 写入方以行状态为单调屏障，天然与 N7 登记表语义互补。
pub fn finish_action_log_with(
    conn: &Connection,
    log_id: i64,
    status: &str,
    summary: &str,
    output_tail: Option<&str>,
    exit_code: Option<i32>,
    finished_at: &str,
) -> Result<(), String> {
    conn.execute(
        "UPDATE action_logs SET status = ?2, summary = ?3, output_tail = ?4, \
         exit_code = ?5, finished_at = ?6 WHERE id = ?1 AND status = 'running'",
        params![log_id, status, summary, output_tail, exit_code, finished_at],
    )
    .map_err(|e| format!("finish action_log {log_id}: {e}"))?;
    Ok(())
}

/// 历史页分页查询（倒序 10/页；reminder_id 可选过滤）。
pub fn list_action_logs(
    conn: &Connection,
    reminder_id: Option<i64>,
    page: u64,
) -> Result<(Vec<ActionLog>, i64), String> {
    // 单页行数收归 ACTION_LOG_PAGE_SIZE 单一事实源（routine-exec.md Part A：
    // 原局部 PAGE_SIZE 与常量两份维护，只改其一会 page_size/LIMIT 失配）。
    let page = page.max(1);
    let offset = (page as i64 - 1) * ACTION_LOG_PAGE_SIZE;
    let (where_clause, bind_id): (&str, Option<i64>) = match reminder_id {
        Some(id) => ("WHERE reminder_id = ?1", Some(id)),
        None => ("", None),
    };
    let total: i64 = conn
        .query_row(
            &format!("SELECT COUNT(*) FROM action_logs {where_clause}"),
            rusqlite::params_from_iter(bind_id),
            |r| r.get(0),
        )
        .map_err(|e| format!("count action_logs: {e}"))?;
    let mut stmt = conn
        .prepare(&format!(
            "SELECT id, reminder_id, action_type, label, command, cwd, status, \
             summary, output_tail, exit_code, started_at, finished_at, scheduled_at \
             FROM action_logs {where_clause} \
             ORDER BY id DESC LIMIT {ACTION_LOG_PAGE_SIZE} OFFSET {offset}"
        ))
        .map_err(|e| format!("list action_logs: {e}"))?;
    let rows = stmt
        .query_map(rusqlite::params_from_iter(bind_id), |row| {
            Ok(ActionLog {
                id: row.get(0)?,
                reminder_id: row.get(1)?,
                action_type: row.get(2)?,
                label: row.get(3)?,
                command: row.get(4)?,
                cwd: row.get(5)?,
                status: row.get(6)?,
                summary: row.get(7)?,
                output_tail: row.get(8)?,
                exit_code: row.get(9)?,
                started_at: row.get(10)?,
                finished_at: row.get(11)?,
                scheduled_at: row.get(12)?,
            })
        })
        .map_err(|e| format!("list action_logs: {e}"))?;
    Ok((rows.filter_map(|r| r.ok()).collect(), total))
}

// §十二 F14（2026-08-28）：stats()（按 kind 聚合 reminder_logs 的历史统计查询）
// 随面板统计区移除清退——记账写路径（insert_log/ack_log/dismiss_log）保留。

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

/// notify 触发落库 + 发事件（`reminder://trigger` 广播，pet 窗口消费）。
/// v2 M4：仅 notify 走本路径（exec 走 action_exec 执行链——action_logs 记账，
/// 不写 reminder_logs，§4.13 不双写）。泛型 Runtime：mock runtime 可直调。
fn fire_and_notify<R: tauri::Runtime>(app: &tauri::AppHandle<R>, fired: &[ReminderRule]) {
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
            plog!("[pulsepet] reminder #{} insert_log 失败，跳过事件", rule.id);
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
        plog!(
            "[pulsepet] reminder fired: #{} kind={} label={:?} fireworks={} log={} at {}",
            rule.id, rule.kind, rule.label, rule.use_fireworks, log_id, ts
        );
    }
}

/// skipped 判定落库（N1 闭环的调用方半段）：写 last_skipped_at + 清 snooze；
/// exec 型落 action_logs(status='skipped')，notify 型不落库（错过无害）。
fn persist_skipped<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    skipped: &[SkippedRule],
    now_ts: &str,
) {
    let Some(db) = app.try_state::<Mutex<Connection>>() else {
        return;
    };
    let Ok(conn) = db.lock() else {
        return;
    };
    for s in skipped {
        let _ = mark_skipped(&conn, s.id, now_ts);
        if s.action_type == "exec" {
            let key = match s.reason {
                SkipReason::MissedWindow => crate::action_exec::SUMMARY_MISSED,
                SkipReason::Paused => crate::action_exec::SUMMARY_PAUSED,
            };
            let sched = ms_to_rfc3339(s.scheduled_at_ms)
                .unwrap_or_else(|| now_ts.to_string());
            // 快照取判定时刻配置（与 running 的派发时刻快照语义对齐——Part C）
            let cmd = crate::action_exec::command_from_params(s.action_params.as_deref());
            let dir = crate::action_exec::cwd_from_params(s.action_params.as_deref());
            if let Err(e) = insert_action_log_skipped(
                &conn,
                s.id,
                &s.label,
                cmd.as_deref(),
                dir.as_deref(),
                key,
                &sched,
                now_ts,
            ) {
                plog!("[pulsepet] insert skipped log for #{} failed: {e}", s.id);
            }
        }
        plog!(
            "[pulsepet] task #{} ({:?}) skipped ({:?})",
            s.id,
            s.label,
            s.reason
        );
    }
    // §二十七：skipped 行落库 → 整批一次广播失效（防逐行风暴），panel 执行历史实时出现 skipped 行
    if !skipped.is_empty() {
        let _ = app.emit(
            crate::action_exec::ACTION_LOGS_CHANGED_EVENT,
            serde_json::json!({}),
        );
    }
    plog!("[pulsepet] {} task(s) skipped (missed window/paused) recorded", skipped.len());
}

/// 计算烟花 play payload（DESIGN §5.3 用户补充需求）：
/// - 发射点 = pet 窗口中心；
/// - **绽放点 = pet 当前所处显示器（monitor）的水平中轴 + 屏高 × 0.3**
///   （多显示器取宠物所在屏；单显示器即当前屏）；
/// - 坐标换算到 fireworks 窗口逻辑像素（payload 消费方 ×dpr 进 canvas）。
///
/// A9（M4 P2① 清偿）：多屏路径**不回读 fireworks 窗口位置**——
/// cover_monitor 刚请求 set_position/set_size 后窗口 bounds 读数可能仍是
/// 旧值（异步应用竞态），而"窗口 == 显示器"由 cover 语义保证，直接以
/// 显示器 bounds 为坐标系即无竞态（`fireworks_points` 纯函数 + 单测钉住）。
/// 窗口读数仅在取不到显示器信息（mon=None 兜底）时使用。
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
    // 窗口物理 bounds（A9 后仅兜底路径消费：mon=None 时的坐标系）
    let (fw_x, fw_y, fw_w, fw_h) = match (
        fw.as_ref().and_then(|w| w.outer_position().ok()),
        fw.as_ref().and_then(|w| w.outer_size().ok()),
    ) {
        (Some(p), Some(s)) => (p.x as f64, p.y as f64, s.width as f64, s.height as f64),
        _ => (0.0, 0.0, 1280.0 * sf, 800.0 * sf),
    };

    // 3) 发射点素材：pet 中心（物理像素；取不到退化为 None，由纯函数给兜底点）
    let pet_rect = pet.as_ref().map(|w| match (w.outer_position(), w.outer_size()) {
        (Ok(p), Ok(s)) => Some((p.x as f64, p.y as f64, s.width as f64, s.height as f64)),
        _ => None,
    });
    let mon_rect = mon.as_ref().map(|m| {
        let p = m.position();
        let s = m.size();
        (p.x as f64, p.y as f64, s.width as f64, s.height as f64)
    });

    let (origin_x, origin_y, target_x, target_y) = fireworks_points(
        pet_rect.flatten(),
        mon_rect,
        (fw_x, fw_y, fw_w, fw_h),
        sf,
    );
    plog!(
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

/// 发射/绽放边距（逻辑像素；clamp 安全兜底，防 pet 贴屏缘时点出画布）。
const POINT_MARGIN: f64 = 20.0;

/// 烟花发射点/绽放点纯函数（A9：单测主战场）。
///
/// - `pet`：pet 窗口物理 `(x, y, w, h)`（None → 发射点退化为该坐标系底部中央）；
/// - `mon`：目标显示器物理 `(x, y, w, h)`——**主路径**（窗口已 cover 该屏，
///   以显示器为窗口坐标系，直接由 bounds 计算，不依赖窗口位置回读）；
/// - `win`：fireworks 窗口物理 `(x, y, w, h)`——仅 `mon=None` 兜底路径的坐标系；
/// - `sf`：显示器缩放系数（物理 → 逻辑）。
/// 返回 `(origin_x, origin_y, target_x, target_y)`（逻辑像素，已 clamp 在
/// 坐标系内留 POINT_MARGIN 边距）。
pub fn fireworks_points(
    pet: Option<(f64, f64, f64, f64)>,
    mon: Option<(f64, f64, f64, f64)>,
    win: (f64, f64, f64, f64),
    sf: f64,
) -> (f64, f64, f64, f64) {
    // 坐标系 = 窗口物理 origin + 尺寸（主路径：显示器；兜底：窗口自身读数）
    let (base_x, base_y, base_w, base_h) = mon.unwrap_or(win);
    let clamp = |v: f64, hi: f64| v.clamp(POINT_MARGIN, (hi - POINT_MARGIN).max(POINT_MARGIN));
    // 发射点：pet 中心（物理 → 坐标系逻辑）；无 pet → 坐标系底部中央
    let (ox, oy) = match pet {
        Some((px, py, pw, ph)) => ((px + pw / 2.0 - base_x) / sf, (py + ph / 2.0 - base_y) / sf),
        None => (base_w / 2.0 / sf, base_h * 0.85 / sf),
    };
    // 绽放点：坐标系水平中轴 + 高度 × 0.3（A9：由 bounds 直接算，不经窗口回读；
    // 窗口 origin == 坐标系 origin——主路径 = cover 后窗口与显示器重合，
    // 兜底路径 = 窗口自身当作"屏"）
    let (tx, ty) = monitor_burst_point_in_window(
        base_x as i32,
        base_y as i32,
        base_w as u32,
        base_h as u32,
        base_x as i32,
        base_y as i32,
        sf,
    );
    (
        clamp(ox, base_w / sf),
        clamp(oy, base_h / sf),
        clamp(tx, base_w / sf),
        clamp(ty, base_h / sf),
    )
}

/// 绽放点 = 显示器水平中轴（x 居中）+ 屏高 × 0.3 → fireworks 窗口逻辑坐标
/// （纯函数，可单测）。`(mon_x, mon_y, mon_w, mon_h)` 为显示器物理 bounds，
/// `(win_x, win_y)` 为窗口物理左上角。
///
/// A9 后主路径由 `fireworks_points` 以"窗口 origin = 显示器 origin"直接计算，
/// 本函数保留给"窗口尚未对齐显示器"的理论形态（mon=None 时窗口自身当屏）。
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
    plog!(
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

/// 启动调度循环：tokio interval + `MissedTickBehavior::Skip`（TC-RM-02）；
/// v2 M4 select 完成通知通道——exec 完成回调出队等待任务（pending_execs）。
pub fn spawn_scheduler(app: tauri::AppHandle, state: Arc<Mutex<RemindersState>>) {
    tauri::async_runtime::spawn(async move {
        let (tx, mut rx) = tokio::sync::mpsc::channel::<()>(16);
        if let Ok(mut st) = state.lock() {
            st.slot_free_tx = Some(tx);
        }
        let mut interval =
            tokio::time::interval(std::time::Duration::from_millis(tick_ms()));
        // 睡眠恢复不补发：错过的 tick 直接跳过，等下一个整 tick（TC-RM-02/C10）
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        // interval 首个 tick 立即到期：跳过第 0 次避免启动瞬间扫一次（无害但省心）
        interval.tick().await;
        plog!("[pulsepet] reminder scheduler started (tick {}ms)", tick_ms());
        loop {
            tokio::select! {
                _ = interval.tick() => run_tick(&app, &state),
                _ = rx.recv() => crate::action_exec::drain_pending_execs(&app, &state),
            }
        }
    });
}

fn run_tick<R: tauri::Runtime>(app: &tauri::AppHandle<R>, state: &Arc<Mutex<RemindersState>>) {
    let now = now_ms();
    let ts = now_rfc3339();
    let minute = now_minute_of_day();
    let (fired, skipped) = {
        let Ok(mut st) = state.lock() else {
            return;
        };
        st.collect_due(now, &ts, minute)
    };
    if !skipped.is_empty() {
        persist_skipped(app, &skipped, &ts);
    }
    // 触发分派（§4.3）：notify → 既有气泡/烟花链路；exec → ActionExecutor 链
    let notify: Vec<ReminderRule> = fired
        .iter()
        .filter(|f| f.rule.action_type != "exec")
        .map(|f| f.rule.clone())
        .collect();
    if !notify.is_empty() {
        fire_and_notify(app, &notify);
    }
    for f in fired.iter().filter(|f| f.rule.action_type == "exec") {
        // R5（tester R4 P2）：**排队中去重**——collect_due fire 与 dispatch 落库
        // 之间被 CRUD reload 插入时，reload 重建的内存无 handled 标记 → 该规则
        // next_due 回到过去时刻 → 下个 tick 重复 fire。此处按 id 查等待队列：
        // 已排队 = 本周期已认领，跳过分派并补 mark_triggered 落库（handled
        // 持久化，此后任意 reload 不再复活）。
        let already_pending = state
            .lock()
            .map(|st| {
                st.pending_execs
                    .iter()
                    .any(|p| p.rule.id == f.rule.id)
            })
            .unwrap_or(false);
        if already_pending {
            if let Some(db) = app.try_state::<Mutex<Connection>>() {
                if let Ok(conn) = db.lock() {
                    let _ = mark_triggered(&conn, f.rule.id, &ts);
                }
            }
            plog!(
                "[pulsepet] exec task #{} already pending, skip re-dispatch (reload race guard)",
                f.rule.id
            );
            continue;
        }
        crate::action_exec::dispatch_exec(app, state, &f.rule, f.scheduled_at_ms);
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

/// 手动触发（面板"试一试"）：返回 "fired" | "dedup" | "paused"。
/// v2 M4（P3-9）：exec 行 = 真实执行一次（接 ActionExecutor 分派，受暂停/
/// 去重约束，结果气泡同正常触发）；notify 行走既有气泡/烟花链路。
/// 泛型 Runtime：可在 tauri::test mock runtime 下直调（todos 命令先例）。
#[tauri::command]
pub fn reminders_trigger_now<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    state: tauri::State<'_, Arc<Mutex<RemindersState>>>,
    id: i64,
) -> Result<String, String> {
    let now = now_ms();
    let ts = now_rfc3339();
    let sched = state
        .lock()
        .map_err(|e| format!("state lock: {e}"))?
        .rules
        .iter()
        .find(|rs| rs.rule.id == id)
        .map(|rs| rs.next_due_ms)
        .unwrap_or(now);
    let (status, rule) = state
        .lock()
        .map_err(|e| format!("state lock: {e}"))?
        .force_fire_one(id, now, &ts)?;
    if let Some(rule) = rule {
        if rule.action_type == "exec" {
            crate::action_exec::dispatch_exec(&app, state.inner(), &rule, sched);
        } else {
            fire_and_notify(&app, &[rule]);
        }
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

/// v2 M4 snooze（TC-M4-13，仅 notify）：气泡按钮「稍后 10 分钟」→
/// **语义 = 重发本次（P1-1）**——snooze_until = now+10min 写表（持久化，
/// 10min 内重启重发仍有效）+ 当前 log 结案 dismissed_via='snooze' + 内存
/// next_due 直接置为 snooze_until（优先于常规计算）。重发触发时清空
/// snooze_until（mark_triggered）按 kind 常规推进。
#[tauri::command]
pub fn reminders_snooze<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    state: tauri::State<'_, Arc<Mutex<RemindersState>>>,
    log_id: i64,
) -> Result<(), String> {
    let now = now_ms();
    let ts = now_rfc3339();
    let until_ms = now + SNOOZE_MS;
    let until_ts = ms_to_rfc3339(until_ms).unwrap_or_else(|| ts.clone());
    let reminder_id = {
        let db = app.state::<Mutex<Connection>>();
        let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
        let rid: i64 = conn
            .query_row(
                "SELECT reminder_id FROM reminder_logs WHERE id = ?1",
                [log_id],
                |r| r.get(0),
            )
            .map_err(|e| format!("reminder_log {log_id} 不存在：{e}"))?;
        let rule = rule_by_id(&conn, rid)?;
        if rule.action_type != "notify" {
            return Err("仅提醒支持稍后（exec 结果气泡无 snooze）".into());
        }
        conn.execute(
            "UPDATE reminders SET snooze_until = ?2 WHERE id = ?1",
            params![rid, until_ts],
        )
        .map_err(|e| format!("snooze reminder #{rid}: {e}"))?;
        dismiss_log(&conn, log_id, "snooze")?;
        rid
    };
    // 内存 next_due 置为 snooze_until（直接置为，非 max）
    let mut st = state.lock().map_err(|e| format!("state lock: {e}"))?;
    if let Some(rs) = st.rules.iter_mut().find(|rs| rs.rule.id == reminder_id) {
        rs.next_due_ms = until_ms;
        rs.rule.snooze_until = Some(until_ts.clone());
    }
    plog!("[pulsepet] reminder #{} snoozed (log {log_id}) until {until_ts}", reminder_id);
    Ok(())
}

/// v2 M4「跳过本次」（TC-M4-14）：内存 next_due 即时推进（interval → +interval；
/// daily → 下个匹配日；once → MAX），不触发不记录；snooze_until 未过期一并
/// 清空（N2：写表 + 内存同清）。已知边界（P3-4）：once 跳过后在补跑窗内
/// 重启 App → reload 检测会补跑（跳过标记未持久化，接受）。
#[tauri::command]
pub fn tasks_skip_once<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    state: tauri::State<'_, Arc<Mutex<RemindersState>>>,
    id: i64,
) -> Result<(), String> {
    let now = now_ms();
    let clear_snooze = state
        .lock()
        .map_err(|e| format!("state lock: {e}"))?
        .skip_once(id, now)?;
    if clear_snooze {
        let db = app.state::<Mutex<Connection>>();
        let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
        conn.execute(
            "UPDATE reminders SET snooze_until = NULL WHERE id = ?1",
            [id],
        )
        .map_err(|e| format!("clear snooze for #{id}: {e}"))?;
    }
    plog!("[pulsepet] task #{id} skipped once (snooze cleared: {clear_snooze})");
    Ok(())
}

/// v2 M4 执行历史分页查询（TC-M4-16）：倒序 10 条/页，reminder_id 可选过滤。
#[tauri::command]
pub fn action_logs_list(
    app: tauri::AppHandle,
    reminder_id: Option<i64>,
    page: Option<u64>,
) -> Result<ActionLogPage, String> {
    let db = app.state::<Mutex<Connection>>();
    let conn = db.lock().map_err(|e| format!("db lock: {e}"))?;
    let (rows, total) = list_action_logs(&conn, reminder_id, page.unwrap_or(1))?;
    Ok(ActionLogPage {
        rows,
        total,
        page: page.unwrap_or(1).max(1),
        page_size: ACTION_LOG_PAGE_SIZE,
    })
}

/// 单页行数（§4.7 执行历史区；2026-08-30 用户裁定 50→15，routine-exec.md Part A；
/// 2026-08-31 用户裁定 15→10，V2-OPEN-ITEMS §二十七）。
pub const ACTION_LOG_PAGE_SIZE: i64 = 10;

/// 分页返回结构（与 TS `ActionLogPage` 一致）。
#[derive(Debug, Clone, Serialize)]
pub struct ActionLogPage {
    pub rows: Vec<ActionLog>,
    pub total: i64,
    pub page: u64,
    pub page_size: i64,
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
    plog!("[pulsepet] debug fireworks (hotkey)");
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
            plog!(
                "[pulsepet] fireworks not ready, queueing play (log {log_id})"
            );
            st.fw_pending = Some(payload);
        }
    }
    if let Some(old) = superseded {
        if let Some(db) = app.try_state::<Mutex<Connection>>() {
            if let Ok(conn) = db.lock() {
                let _ = dismiss_log(&conn, old, "fireworks");
                plog!("[pulsepet] fireworks superseded: backfill log {old} via 'fireworks'");
            }
        }
    }
    windows::show_fireworks(app);
    spawn_fireworks_watchdog(app.clone(), state.clone(), log_id, gen);
}

/// 6.5s watchdog（A5 抽出为可复用段）：前端未回报 finished 则强制 hide
/// （防常驻窗口）。前端正常 finished 已 hide 过时窗口不可见 → 跳过，避免
/// 冗余 hide（E2E 实测修正）。M4 P2 ④：超时同样对未结案 log 补
/// dismissed_via='fireworks'（前端崩溃时不再残留 NULL）。
///
/// A5（M4 P2⑦ 清偿）：pending 补发路径（ready 握手晚于 play 请求）会 bump
/// `fw_gen` 后重起本 watchdog——否则 6.5s 计时仍从 play 时刻起算，ready 晚于
/// ~2.7s 到达时补发场次的中段会被旧 watchdog 截断 hide（概率极低但行为可
/// 预期化：每次实际下发 play 都有自己的完整 6.5s 窗口）。
fn spawn_fireworks_watchdog<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    state: Arc<Mutex<RemindersState>>,
    log_id: i64,
    gen: u64,
) {
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(std::time::Duration::from_millis(6500)).await;
        let cur = state
            .lock()
            .map(|st| st.fw_gen)
            .unwrap_or(u64::MAX);
        if cur == gen {
            let still_active = state
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
                if let Some(db) = app.try_state::<Mutex<Connection>>() {
                    if let Ok(conn) = db.lock() {
                        let _ = dismiss_log(&conn, log_id, "fireworks");
                        plog!("[pulsepet] fireworks watchdog: backfill log {log_id} via 'fireworks'");
                    }
                }
            }
            let visible = app
                .get_webview_window("fireworks")
                .and_then(|w| w.is_visible().ok())
                .unwrap_or(false);
            if visible {
                windows::hide_fireworks(&app);
                plog!("[pulsepet] fireworks watchdog hide (gen {gen})");
            }
        }
    });
}

/// fireworks 窗口挂载完成（ready 握手）：补发 pending 的 play。
/// A5：补发即"一次实际下发"——bump gen 作废旧 watchdog（其计时从 play 请求
/// 时刻起算，对晚到的补发场次窗口不足），并重起新 watchdog。
/// 泛型 Runtime：可在 tauri::test mock runtime 下直调（A5 单测）。
#[tauri::command]
pub fn fireworks_ready<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    state: tauri::State<'_, Arc<Mutex<RemindersState>>>,
) -> Result<(), String> {
    let pending = {
        let mut st = state.lock().map_err(|e| format!("state lock: {e}"))?;
        st.fw_ready = true;
        st.fw_pending.take()
    };
    if let Some(p) = pending {
        let gen = {
            let mut st = state.lock().map_err(|e| format!("state lock: {e}"))?;
            st.fw_gen += 1;
            st.fw_gen
        };
        let _ = app.emit_to("fireworks", "fireworks://play", p.clone());
        windows::show_fireworks(&app);
        spawn_fireworks_watchdog(app.clone(), state.inner().clone(), p.log_id, gen);
        plog!(
            "[pulsepet] fireworks ready → replay pending (log {}, watchdog reset to gen {gen})",
            p.log_id
        );
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
    plog!("[pulsepet] fireworks finished: log {log_id} hidden");
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

    // ---- v2 M2：load_active_rules（调度器专用过滤，TC-UI-08） ----

    fn seed_rules_for_plugin_toggle(c: &Connection) {
        crate::db::set_state(c, "seed", "1").ok();
        c.execute(
            "INSERT INTO plugins (id, name, version, manifest_version, enabled) \
             VALUES ('built-in-todo', 'Todo', '0.1.0', 1, 1)",
            [],
        )
        .unwrap();
        c.execute(
            "INSERT INTO reminders (kind, label, interval_minutes, enabled, use_fireworks) \
             VALUES ('hydration', '喝水', 30, 1, 0)",
            [],
        )
        .unwrap();
        c.execute(
            "INSERT INTO reminders (kind, label, interval_minutes, enabled, use_fireworks, \
             source_todo_id, start_time, todo_due_at) \
             VALUES ('todo', '交周报', 0, 1, 0, 7, '2026-08-25T09:55', '2026-08-25T10:00')",
            [],
        )
        .unwrap();
    }

    #[test]
    fn load_active_rules_filters_todo_derived_when_plugin_disabled() {
        let c = conn();
        seed_rules_for_plugin_toggle(&c);

        // 插件启用：全量参与调度
        assert_eq!(load_active_rules(&c).unwrap().len(), 2);

        // 禁用：todo 派生行被过滤（停派生提醒），普通行保留
        c.execute("UPDATE plugins SET enabled = 0 WHERE id = 'built-in-todo'", [])
            .unwrap();
        let active = load_active_rules(&c).unwrap();
        assert_eq!(active.len(), 1);
        assert_eq!(active[0].kind, "hydration");

        // reminders_list 口径不变：load_rules 照旧全量（可见但惰性，P2-2 定案）
        assert_eq!(load_rules(&c).unwrap().len(), 2, "列表可见性依据 load_rules 全量");

        // 重启用：派生行恢复参与调度（数据保留，无 DELETE）
        c.execute("UPDATE plugins SET enabled = 1 WHERE id = 'built-in-todo'", [])
            .unwrap();
        assert_eq!(load_active_rules(&c).unwrap().len(), 2);
    }

    #[test]
    fn load_active_rules_defaults_to_enabled_when_plugin_row_missing() {
        let c = conn();
        crate::db::set_state(&c, "seed", "1").ok();
        // plugins 表无登记（异常态：ensure_builtin_plugins 未跑）——保守视为启用，
        // 不因元数据缺失丢提醒
        c.execute(
            "INSERT INTO reminders (kind, label, interval_minutes, enabled, use_fireworks, source_todo_id) \
             VALUES ('todo', '孤儿派生行', 0, 1, 0, 1)",
            [],
        )
        .unwrap();
        assert_eq!(load_active_rules(&c).unwrap().len(), 1);
    }

    #[test]
    fn scheduler_reload_uses_active_rules_and_collect_due_skips_disabled() {
        let c = conn();
        seed_rules_for_plugin_toggle(&c);
        c.execute("UPDATE plugins SET enabled = 0 WHERE id = 'built-in-todo'", [])
            .unwrap();

        let mut st = RemindersState::default();
        st.reload(&c).unwrap();
        assert_eq!(st.rules.len(), 1, "reload 走 load_active_rules（禁用行不进内存）");

        // 重启用后 reload 恢复（禁用期间行未被删除）
        c.execute("UPDATE plugins SET enabled = 1 WHERE id = 'built-in-todo'", [])
            .unwrap();
        st.reload(&c).unwrap();
        assert_eq!(st.rules.len(), 2);
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
            action_type: String::new(),
            action_params: None,
            schedule_kind: String::new(),
            schedule_at: None,
            schedule_weekdays: None,
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

    /// v2 M4 字段缺省尾巴（struct update 语法用；老测试只关心 v1 字段）。
    fn m4_fields() -> ReminderRule {
        ReminderRule {
            id: 0,
            kind: "custom".into(),
            label: String::new(),
            interval_minutes: 0,
            start_time: None,
            end_time: None,
            enabled: true,
            use_fireworks: false,
            last_triggered_at: None,
            source_todo_id: None,
            todo_due_at: None,
            created_at: String::new(),
            action_type: "notify".into(),
            action_params: None,
            schedule_kind: "interval".into(),
            schedule_at: None,
            schedule_weekdays: None,
            snooze_until: None,
            last_skipped_at: None,
        }
    }

    #[test]
    fn next_due_never_triggered_anchors_at_created() {
        let rule = ReminderRule {
            id: 1,
            kind: "hydration".into(),
            label: "该喝水啦 💧".into(),
            interval_minutes: 30,
            created_at: rfc(1000),
            ..m4_fields()
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
            last_triggered_at: Some(rfc(1_000_000)),
            created_at: rfc(0),
            ..m4_fields()
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
            last_triggered_at: None,
            source_todo_id: Some(42),
            created_at: rfc(0),
            ..m4_fields()
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
            ..Default::default()
        }
    }

    fn base_rule(id: i64, interval: i64) -> ReminderRule {
        ReminderRule {
            id,
            kind: "hydration".into(),
            label: "该喝水啦 💧".into(),
            interval_minutes: interval,
            created_at: rfc(0),
            ..m4_fields()
        }
    }

    /// 测试便捷：collect_due → fired 规则 Vec（skipped 断言单独取 .1）。
    fn fire(st: &mut RemindersState, now: i64, minute: i64) -> Vec<ReminderRule> {
        st.collect_due(now, &rfc(now), minute)
            .0
            .into_iter()
            .map(|f| f.rule)
            .collect()
    }

    #[test]
    fn collect_due_fires_when_due_and_advances() {
        let now = 1_000_000;
        let mut st = state_with(base_rule(1, 30), now);
        st.rules[0].next_due_ms = now; // 到期
        let fired = fire(&mut st, now, 600);
        assert_eq!(fired.len(), 1);
        assert_eq!(fired[0].id, 1);
        assert_eq!(fired[0].last_triggered_at.as_deref(), Some(rfc(now).as_str()));
        // 触发后 next_due 推进：同一时刻不再触发
        assert!(st.rules[0].next_due_ms > now);
        assert!(fire(&mut st, now, 600).is_empty());
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
        assert!(fire(&mut st, now, 8 * 60).is_empty());
        assert_eq!(st.rules[0].next_due_ms, now);
        // 09:00 进入窗口 → 触发
        assert_eq!(fire(&mut st, now, 9 * 60).len(), 1);
        // 跨午夜窗口 22:00-06:00：12:00 不触发
        let mut rule2 = base_rule(2, 30);
        rule2.start_time = Some("22:00".into());
        rule2.end_time = Some("06:00".into());
        let mut st2 = state_with(rule2, now);
        st2.rules[0].next_due_ms = now;
        assert!(fire(&mut st2, now, 12 * 60).is_empty());
        assert_eq!(fire(&mut st2, now, 23 * 60).len(), 1);
    }

    #[test]
    fn collect_due_dedup_blocks_interval_below_three_minutes() {
        // interval=1min 的实测规则：触发后 1min 到期，但 3 分钟去重内不得重复（TC-RM-05）
        let now = 1_000_000;
        let mut st = state_with(base_rule(1, 1), now);
        st.rules[0].next_due_ms = now;
        assert_eq!(fire(&mut st, now, 600).len(), 1);
        // +2min：next_due（now+1min）已过，但去重拦截
        assert!(fire(&mut st, now + 120_000, 600).is_empty());
        // +3min 整：去重窗口过去 → 再触发
        assert_eq!(fire(&mut st, now + 180_000, 600).len(), 1);
    }

    #[test]
    fn collect_due_disabled_rule_never_fires() {
        let now = 1_000_000;
        let mut rule = base_rule(1, 30);
        rule.enabled = false;
        let mut st = state_with(rule, now);
        st.rules[0].next_due_ms = now;
        assert!(fire(&mut st, now, 600).is_empty());
    }

    #[test]
    fn collect_due_paused_defers_and_resumes_tc_rm_08() {
        let now = 1_000_000;
        let mut st = state_with(base_rule(1, 30), now);
        st.rules[0].next_due_ms = now;
        // 暂停：到期不触发，倒计时顺延 now+30min
        st.paused = true;
        let (fired, skipped) = st.collect_due(now, &rfc(now), 600);
        assert!(fired.is_empty());
        assert!(skipped.is_empty(), "interval 类暂停不记 skipped（v1 顺延）");
        assert_eq!(st.rules[0].next_due_ms, now + 1_800_000);
        // 暂停期间每 tick 顺延：仅在再次到期的 tick 才继续顺延（1 分钟后未到期 → 保持）
        let (fired, skipped) = st.collect_due(now + 60_000, &rfc(now + 60_000), 600);
        assert!(fired.is_empty() && skipped.is_empty());
        assert_eq!(st.rules[0].next_due_ms, now + 1_800_000);
        // 取消暂停：顺延点之前不触发
        st.paused = false;
        let due = st.rules[0].next_due_ms;
        assert!(fire(&mut st, due - 1, 600).is_empty());
        // 到顺延点 → 恢复触发
        assert_eq!(fire(&mut st, due, 600).len(), 1);
    }

    #[test]
    fn collect_due_todo_kind_single_fire_no_repeat() {
        let now = 1_000_000;
        let mut rule = base_rule(9, 0);
        rule.kind = "todo".into();
        rule.source_todo_id = Some(3);
        let mut st = state_with(rule, now);
        st.rules[0].next_due_ms = now; // 从未触发 → 立即到期
        assert_eq!(fire(&mut st, now, 600).len(), 1);
        assert_eq!(st.rules[0].next_due_ms, i64::MAX);
        // 后续 tick / 更晚时刻均不再触发（不误重复）
        assert!(fire(&mut st, now + 60_000, 600).is_empty());
        assert!(fire(&mut st, now + 6_000_000, 600).is_empty());
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
    fn logs_trigger_ack_dismiss_paths() {
        // §十二 F14（2026-08-28）：stats 断言随统计区移除清退，logs 记账/
        // ack/dismiss 路径保留验证（原 TC-RM-13 记账面的测试延续）
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

    // ---- A9（M4 P2① 清偿）：烟花点位直接由 monitor bounds 计算，不回读窗口 ----

    #[test]
    fn fireworks_points_single_display_dpr2() {
        // 主屏 2940×1912 物理（dpr=2），pet 中心 (1470, 956)：
        // 发射点 = pet 中心逻辑 (735, 478)；绽放点 = (735, 286.8)。
        // 关键语义：坐标只来自 monitor bounds + pet 位置——不依赖窗口回读，
        // cover 后窗口 bounds 读数是否更新（竞态）不再影响结果。
        let (ox, oy, tx, ty) =
            fireworks_points(Some((1360.0, 846.0, 220.0, 220.0)), Some((0.0, 0.0, 2940.0, 1912.0)), (0.0, 0.0, 2940.0, 1912.0), 2.0);
        assert!((ox - 735.0).abs() < 1e-9);
        assert!((oy - 478.0).abs() < 1e-9);
        assert!((tx - 735.0).abs() < 1e-9);
        assert!((ty - 286.8).abs() < 1e-9);
    }

    #[test]
    fn fireworks_points_secondary_display_offset_invariant() {
        // 次屏从 x=2940 起，pet 在次屏 (2940+1360, 846)：
        // 绽放点仍在**窗口（=次屏）坐标系**中轴 (735, 286.8)——与屏的原点偏移
        // 无关（A9 钉住的"无竞态"语义：以显示器为坐标系，无需知道窗口位置）。
        let (ox, oy, tx, ty) = fireworks_points(
            Some((2940.0 + 1360.0, 846.0, 220.0, 220.0)),
            Some((2940.0, 0.0, 2940.0, 1912.0)),
            (0.0, 0.0, 2940.0, 1912.0), // 窗口读数故意给"未更新的旧值"（主屏）——结果不受影响
            2.0,
        );
        assert!((ox - 735.0).abs() < 1e-9, "origin 用 mon 坐标系：{ox}");
        assert!((oy - 478.0).abs() < 1e-9);
        assert!((tx - 735.0).abs() < 1e-9, "target 用 mon 坐标系：{tx}");
        assert!((ty - 286.8).abs() < 1e-9);
    }

    #[test]
    fn fireworks_points_pet_missing_falls_to_bottom_center() {
        // pet 读不到（窗口异常关闭等）→ 发射点退化为坐标系底部中央
        let (ox, oy, tx, ty) =
            fireworks_points(None, Some((0.0, 0.0, 2940.0, 1912.0)), (0.0, 0.0, 2940.0, 1912.0), 2.0);
        assert!((ox - 735.0).abs() < 1e-9);
        assert!((oy - 1912.0 * 0.85 / 2.0).abs() < 1e-9);
        assert!((tx - 735.0).abs() < 1e-9);
        assert!((ty - 286.8).abs() < 1e-9);
    }

    #[test]
    fn fireworks_points_monitor_missing_falls_to_window_bounds() {
        // mon 取不到（current_monitor 全失败）→ 用窗口读数当坐标系（兜底语义
        // 与 M4 行为一致：窗口同比例点 + pet 相对窗口）
        let (ox, oy, tx, ty) =
            fireworks_points(Some((1360.0, 846.0, 220.0, 220.0)), None, (0.0, 0.0, 2940.0, 1912.0), 2.0);
        assert!((ox - 735.0).abs() < 1e-9);
        assert!((oy - 478.0).abs() < 1e-9);
        assert!((tx - 735.0).abs() < 1e-9);
        assert!((ty - 286.8).abs() < 1e-9);
    }

    #[test]
    fn fireworks_points_clamps_tiny_display() {
        // 极小坐标系：clamp 退化到 ≥20 逻辑像素，不产生负坐标/越界
        let (ox, oy, tx, ty) =
            fireworks_points(Some((0.0, 0.0, 4.0, 4.0)), Some((0.0, 0.0, 24.0, 24.0)), (0.0, 0.0, 24.0, 24.0), 1.0);
        for v in [ox, oy, tx, ty] {
            assert!(v >= 20.0 - 1e-9, "clamp 下界：{v}");
        }
    }

    // ---- A5（M4 P2⑦ 清偿）：pending 补发重置 watchdog ----

    #[test]
    fn fireworks_ready_replay_bumps_gen_and_clears_pending() {
        // ready 握手晚于 play 请求：pending 补发时 bump fw_gen → 旧 watchdog
        // （从 play 时刻起算的 6.5s）因 gen 不匹配自动作废，补发场次获得由
        // spawn_fireworks_watchdog 重起的完整窗口。此处钉住状态机语义。
        let app = tauri::test::mock_app();
        let handle = app.handle();
        let st = std::sync::Arc::new(std::sync::Mutex::new(RemindersState {
            fw_ready: false,
            fw_pending: Some(PlayPayload {
                log_id: 7,
                origin_x: 10.0,
                origin_y: 10.0,
                target_x: 100.0,
                target_y: 100.0,
            }),
            fw_gen: 3, // dispatch_play 已 bump 过的旧 gen
            ..Default::default()
        }));
        handle.manage(st.clone());
        fireworks_ready(handle.clone(), handle.state::<Arc<Mutex<RemindersState>>>()).unwrap();
        let s = st.lock().unwrap();
        assert!(s.fw_ready, "ready 置位");
        assert!(s.fw_pending.is_none(), "pending 已消费");
        assert_eq!(s.fw_gen, 4, "补发必须 bump gen（作废旧 watchdog）");
    }

    #[test]
    fn fireworks_ready_without_pending_keeps_gen() {
        // 无 pending 的普通 ready（正常启动路径）：不 bump gen、不重起 watchdog
        let app = tauri::test::mock_app();
        let handle = app.handle();
        let st = std::sync::Arc::new(std::sync::Mutex::new(RemindersState::default()));
        handle.manage(st.clone());
        fireworks_ready(handle.clone(), handle.state::<Arc<Mutex<RemindersState>>>()).unwrap();
        let s = st.lock().unwrap();
        assert!(s.fw_ready);
        assert!(s.fw_pending.is_none());
        assert_eq!(s.fw_gen, 0, "无补发不动 gen");
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
            last_triggered_at: None,
            source_todo_id: Some(3),
            todo_due_at: Some("2026-08-18T15:30".into()),
            created_at: rfc(0),
            ..m4_fields()
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
            last_triggered_at: None,
            source_todo_id: Some(4),
            todo_due_at: Some("2026-08-18T15:30".into()),
            created_at: rfc(0),
            ..m4_fields()
        };
        let mut st = state_with(rule, 0);
        // 未到点（含 start_time 是绝对时刻而非 HH:MM 窗口的判定）→ 不触发
        assert!(st.collect_due(start_ms - 1, &rfc(start_ms - 1), 0).0.is_empty());
        // 到点 → 触发一次；之后（即便再过很久）不再触发（TC-TD-06）
        let (fired, skipped) = st.collect_due(start_ms, &rfc(start_ms), 0);
        assert_eq!(fired.len(), 1);
        assert_eq!(fired[0].rule.kind, "todo");
        assert_eq!(fired[0].rule.todo_due_at.as_deref(), Some("2026-08-18T15:30"));
        assert!(skipped.is_empty(), "todo 派生行不参与 skipped 记账");
        assert_eq!(st.rules[0].next_due_ms, i64::MAX);
        assert!(st.collect_due(start_ms + 3_600_000, &rfc(start_ms + 3_600_000), 0).0.is_empty());
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
        // 派生规则的 start_time 是绝对时刻（非 HH:MM 窗口），必须被 upsert 入口接受
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

    // =========================================================================
    // v2 M4（TC-M4-03/04/07/13/14/16）：daily/once 调度 + 补跑窗 + snooze +
    // skipped 闭环 + 跳过 + validate 重置 + action_logs
    // =========================================================================

    /// 本地时区当日 10:00 的 epoch ms（+days 天偏移）。
    fn daily_at(days_offset: i64, hour: u32, min: u32) -> i64 {
        let today = Local::now().date_naive();
        let day = today
            .checked_add_signed(ChronoDuration::days(days_offset))
            .unwrap();
        Local
            .with_ymd_and_hms(day.year(), day.month(), day.day(), hour, min, 0)
            .unwrap()
            .timestamp_millis()
    }

    /// daily/once 规则构造器（notify 缺省；exec 传 action_type）。
    fn daily_rule(id: i64, hhmm: &str, weekdays: Option<&str>) -> ReminderRule {
        ReminderRule {
            id,
            kind: "custom".into(),
            label: "定点任务".into(),
            interval_minutes: 0,
            schedule_kind: "daily".into(),
            schedule_at: Some(hhmm.into()),
            schedule_weekdays: weekdays.map(|s| s.to_string()),
            created_at: rfc(daily_at(-7, 0, 0)), // 一周前创建
            ..m4_fields()
        }
    }

    fn once_rule(id: i64, at_ms: i64) -> ReminderRule {
        ReminderRule {
            id,
            kind: "custom".into(),
            label: "一次性任务".into(),
            interval_minutes: 0,
            schedule_kind: "once".into(),
            schedule_at: Some(
                DateTime::from_timestamp_millis(at_ms)
                    .unwrap()
                    .with_timezone(&Local)
                    .format("%Y-%m-%dT%H:%M")
                    .to_string(),
            ),
            created_at: rfc(at_ms - 86_400_000),
            ..m4_fields()
        }
    }

    /// 今天星期（1=周一…7=周日）。
    fn today_weekday() -> u32 {
        Local::now().date_naive().weekday().num_days_from_monday() as u32 + 1
    }

    // ---- TC-M4-03-1：daily next_due ----

    #[test]
    fn daily_next_due_today_future_and_past() {
        // 干净状态（昨日 10:05 已触发）：now = 今日 09:00（未到）→ 今日 10:00
        let now = daily_at(0, 9, 0);
        let mut r1 = daily_rule(1, "10:00", None);
        r1.last_triggered_at = Some(rfc(daily_at(-1, 10, 5)));
        assert_eq!(compute_next_due(&r1, now), daily_at(0, 10, 0));
        // 当日已过（now = 今日 11:00，今日 10:00 未处理）→ 返回今日 10:00（过去，
        // 交 tick 补跑窗判定）；昨日已处理不构成干扰
        let now = daily_at(0, 11, 0);
        let mut r2 = daily_rule(2, "10:00", None);
        r2.last_triggered_at = Some(rfc(daily_at(-1, 10, 5)));
        assert_eq!(
            compute_next_due(&r2, now),
            daily_at(0, 10, 0),
            "本周期未处理 → 过去时刻（补跑窗判定入口）"
        );
        // 今日已处理 → 次日
        let mut r3 = daily_rule(3, "10:00", None);
        r3.last_triggered_at = Some(rfc(daily_at(0, 10, 5)));
        assert_eq!(compute_next_due(&r3, now), daily_at(1, 10, 0));
    }

    #[test]
    fn daily_next_due_weekdays_filter() {
        // 星期过滤不含今天 → 跳到下个匹配日；NULL = 每天（干净状态：昨日已触发）
        let today = today_weekday();
        let next_weekday = (today % 7) + 1; // 明天的星期编号
        let now = daily_at(0, 9, 0);
        let handled = Some(rfc(daily_at(-1, 10, 5)));
        // 过滤 = [next_weekday]：今天不匹配 → 下个匹配日（1-7 天内）
        let mut r = daily_rule(1, "10:00", Some(&format!("[{next_weekday}]")));
        r.last_triggered_at = handled.clone();
        let due = compute_next_due(&r, now);
        assert!(
            due > now && due <= now + 8 * 86_400_000,
            "下个匹配日在未来 8 天内"
        );
        // due 那天的星期确实匹配
        let due_date = Local.timestamp_millis_opt(due).single().unwrap().date_naive();
        assert_eq!(due_date.weekday().num_days_from_monday() as u32 + 1, next_weekday);
        // NULL / 空数组 = 每天（今天匹配 → 今日）
        let mut r2 = daily_rule(2, "10:00", Some("[]"));
        r2.last_triggered_at = handled;
        assert_eq!(compute_next_due(&r2, now), daily_at(0, 10, 0));
    }

    // ---- TC-M4-03-2：once next_due / 终态 ----

    #[test]
    fn once_next_due_future_and_terminal() {
        let at = daily_at(1, 21, 0); // 明晚 21:00
        let rule = once_rule(1, at);
        assert_eq!(compute_next_due(&rule, at - 3_600_000), at, "未来时刻 → schedule_at");
        // 已触发 → MAX（终态，跨重启成立——last_triggered ≥ schedule_at）
        let mut fired = rule.clone();
        fired.last_triggered_at = Some(rfc(at));
        assert_eq!(compute_next_due(&fired, at + 60_000), i64::MAX);
        // 已跳过（last_skipped_at）同样终态
        let mut skipped = rule;
        skipped.last_skipped_at = Some(rfc(at));
        assert_eq!(compute_next_due(&skipped, at + 60_000), i64::MAX);
    }

    // ---- TC-M4-03-4：snooze 重发语义（P1-1 回归钉子） ----

    #[test]
    fn snooze_overrides_regular_next_due_and_clears_on_fire() {
        let at = daily_at(1, 21, 0);
        let mut rule = once_rule(1, at);
        // 触发后常规 next_due 已是未来（once → MAX），snooze 必须"直接置为"才能重发
        rule.last_triggered_at = Some(rfc(at));
        let snooze_until = at + 10 * 60_000;
        rule.snooze_until = Some(rfc(snooze_until));
        assert_eq!(
            compute_next_due(&rule, at + 60_000),
            snooze_until,
            "snooze_until 未过期优先于常规计算（非 max——P1-1）"
        );
        // 过期 → 静默丢弃回落常规（N3 已知边界）
        assert_eq!(
            compute_next_due(&rule, snooze_until + 1),
            i64::MAX,
            "过期 snooze 丢弃 → once 已触发的常规值 MAX"
        );
    }

    #[test]
    fn snooze_daily_refire_advances_to_next_match() {
        // daily + snooze：重发后（snooze 已清、last_triggered=重发时刻）→ 下个匹配日
        let at = daily_at(0, 10, 0);
        let mut rule = daily_rule(1, "10:00", None);
        rule.snooze_until = Some(rfc(at + 600_000));
        assert_eq!(compute_next_due(&rule, at + 60_000), at + 600_000);
        // 模拟重发触发：snooze 清空 + last_triggered = 重发时刻（10:10）
        rule.snooze_until = None;
        rule.last_triggered_at = Some(rfc(at + 600_000));
        assert_eq!(
            compute_next_due(&rule, at + 600_000),
            daily_at(1, 10, 0),
            "daily 重发后 → 下个匹配日"
        );
    }

    #[test]
    fn snooze_interval_chain_shifts_by_ten_minutes() {
        // interval ≥10min：重发链整体顺延（重发时刻为新锚点）
        let t0 = 1_000_000i64;
        let mut rule = base_rule(1, 30);
        rule.last_triggered_at = Some(rfc(t0));
        let snooze_until = t0 + 10 * 60_000;
        rule.snooze_until = Some(rfc(snooze_until));
        assert_eq!(compute_next_due(&rule, t0 + 60_000), snooze_until);
        // 重发触发（10:10）→ 常规推进 30min：11:40 的锚点链（非原 10:30 链）
        rule.snooze_until = None;
        rule.last_triggered_at = Some(rfc(snooze_until));
        assert_eq!(
            compute_next_due(&rule, snooze_until),
            snooze_until + 1_800_000,
            "interval 重发后锚点链后移 10min"
        );
    }

    // ---- TC-M4-03-5：reload 错过检测（P2-5，经 compute_next_due 的 daily 分支） ----

    #[test]
    fn daily_reload_missed_window_returns_past_due() {
        // App 关闭跨过 schedule_at：本周期（今天 10:00）未处理 → next_due = 今天 10:00
        //（过去的时刻，由 tick 补跑窗判定：窗内补跑 / 超窗 skipped）
        let now = daily_at(0, 10, 5); // 过了 5 分钟重启
        assert_eq!(compute_next_due(&daily_rule(1, "10:00", None), now), daily_at(0, 10, 0));
        // last_triggered 已晚于 schedule_at（今早已跑）→ 不误报，给下个匹配日
        let mut r = daily_rule(2, "10:00", None);
        r.last_triggered_at = Some(rfc(daily_at(0, 10, 0)));
        assert_eq!(compute_next_due(&r, now), daily_at(1, 10, 0));
        // 已 skipped 同样不误报（N1 ①）
        let mut r = daily_rule(3, "10:00", None);
        r.last_skipped_at = Some(rfc(daily_at(0, 10, 1)));
        assert_eq!(compute_next_due(&r, now), daily_at(1, 10, 0));
    }

    // ---- TC-M4-03-6：interval 分支 v1 断言全量保留（回归，上组测试已覆盖核心） ----

    #[test]
    fn interval_branch_v1_semantics_untouched() {
        // 错过不补：anchor 过期 → now + interval
        let rule = base_rule(1, 30);
        assert_eq!(compute_next_due(&rule, 10_000_000), 10_000_000 + 1_800_000);
        // snooze 过期回落 interval 常规
        let mut r = base_rule(2, 30);
        r.snooze_until = Some(rfc(1_000));
        assert_eq!(compute_next_due(&r, 10_000_000), 10_000_000 + 1_800_000);
    }

    // ---- TC-M4-04：collect_due 补跑窗 + skipped 闭环 ----

    #[test]
    fn catchup_window_boundary_14m59s_fires_15m01s_skips() {
        // 窗内（14m59s）→ 正常触发
        let at = daily_at(0, 10, 0);
        let mut st = state_with(daily_rule(1, "10:00", None), at);
        st.rules[0].next_due_ms = at;
        let (fired, skipped) = st.collect_due(at + CATCHUP_WINDOW_MS - 1_000, &rfc(at), 600);
        assert_eq!(fired.len(), 1, "14m59s → 触发（补跑）");
        assert!(skipped.is_empty());
        // 超窗（15m01s）→ skipped + 推进 + 记 last_skipped_at
        let mut st = state_with(daily_rule(2, "10:00", None), at);
        st.rules[0].next_due_ms = at;
        let ts = rfc(at + CATCHUP_WINDOW_MS + 1_000);
        let (fired, skipped) = st.collect_due(at + CATCHUP_WINDOW_MS + 1_000, &ts, 600);
        assert!(fired.is_empty(), "15m01s → 不触发");
        assert_eq!(skipped.len(), 1);
        assert_eq!(skipped[0].id, 2);
        assert_eq!(skipped[0].reason, SkipReason::MissedWindow);
        assert_eq!(skipped[0].scheduled_at_ms, at, "记原定时刻（溯源）");
        // 闭环：内存写 last_skipped_at + 推进 next_due（daily → 下个匹配日）
        assert_eq!(st.rules[0].rule.last_skipped_at.as_deref(), Some(ts.as_str()));
        assert_eq!(st.rules[0].next_due_ms, daily_at(1, 10, 0));
        // 同一 tick 不再判定（下一 tick 到期前无动作）
        let (fired2, skipped2) = st.collect_due(at + CATCHUP_WINDOW_MS + 61_000, &rfc(at), 600);
        assert!(fired2.is_empty() && skipped2.is_empty(), "记后推进 → 不重复判定");
    }

    #[test]
    fn once_skipped_writes_last_skipped_and_stays_max_across_reload() {
        // once 超窗 skipped → 内存 MAX；落库（mark_skipped）后 reload 仍 MAX（N1 ②）
        //（once 创建须未来时刻——用明日 10:00；到期判定用手动置过的 next_due）
        let at = daily_at(1, 10, 0);
        let c = conn();
        let mut inp = input("custom", "一次性任务", 30);
        inp.interval_minutes = 30; // once normalize 会强制 0
        inp.schedule_kind = "once".into();
        inp.schedule_at = Some(
            DateTime::from_timestamp_millis(at)
                .unwrap()
                .with_timezone(&Local)
                .format("%Y-%m-%dT%H:%M")
                .to_string(),
        );
        let r = insert_rule(&c, &inp).unwrap();
        let mut st = RemindersState::load(&c).unwrap();
        // 模拟超窗 tick：next_due 已过 15 分钟（now = at + 窗 + 1min）
        let ts = rfc(at + CATCHUP_WINDOW_MS + 60_000);
        st.rules[0].next_due_ms = at;
        let (fired, skipped) = st.collect_due(at + CATCHUP_WINDOW_MS + 60_000, &ts, 600);
        assert_eq!(skipped.len(), 1);
        assert!(fired.is_empty());
        // 调用方落库（N1：skipped 列表随 fired 一起返回）
        mark_skipped(&c, r.id, &ts).unwrap();
        // reload（等价重启）→ once 终态 MAX 不复活
        let st2 = RemindersState::load(&c).unwrap();
        assert_eq!(st2.rules[0].next_due_ms, i64::MAX, "once skipped 重启仍 MAX");
        // 醒来 3 分钟内手动补跑：dedup 判定源 last_triggered 为空 → 不被拒（P3-2）
        let mut st3 = RemindersState::load(&c).unwrap();
        let (_, rule) = st3.force_fire_one(r.id, now_ms(), &rfc(now_ms())).unwrap();
        assert!(rule.is_some(), "skipped 后手动补跑不被 dedup 拒绝");
    }

    #[test]
    fn paused_daily_once_records_skipped_and_resumes_without_catchup() {
        // 暂停分支：daily/once 到期记 skipped（含原定时刻）+ 推进 + 清 snooze；
        // 恢复后不补跑（完全冻结）；interval 维持顺延
        let at = daily_at(0, 10, 0);
        let mut rule = daily_rule(1, "10:00", None);
        rule.snooze_until = Some(rfc(at + 600_000)); // 未过期 snooze 应被清（P3-5）
        let mut st = state_with(rule, at);
        st.rules[0].next_due_ms = at;
        st.paused = true;
        let ts = rfc(at + 60_000);
        let (fired, skipped) = st.collect_due(at + 60_000, &ts, 600);
        assert!(fired.is_empty());
        assert_eq!(skipped.len(), 1, "daily 暂停到期记 skipped");
        assert_eq!(skipped[0].reason, SkipReason::Paused);
        assert_eq!(st.rules[0].rule.snooze_until, None, "记 skipped 清未过期 snooze（P3-5）");
        assert_eq!(st.rules[0].next_due_ms, daily_at(1, 10, 0), "记后推进（防每 tick 重复）");
        // 暂停期间每 tick 只记一次
        let (f2, s2) = st.collect_due(at + 120_000, &rfc(at + 120_000), 600);
        assert!(f2.is_empty() && s2.is_empty());
        // 恢复后不补跑（推进后的到期点之前不触发）
        st.paused = false;
        assert!(fire(&mut st, at + 180_000, 600).is_empty(), "恢复后不补跑");
        // interval 类维持 v1 顺延（同 tick 内不记 skipped）
        let mut sti = state_with(base_rule(9, 30), 1_000_000);
        sti.rules[0].next_due_ms = 1_000_000;
        sti.paused = true;
        let (fi, si) = sti.collect_due(1_000_000, &rfc(1_000_000), 600);
        assert!(fi.is_empty() && si.is_empty(), "interval 暂停顺延不记 skipped");
        assert_eq!(sti.rules[0].next_due_ms, 1_000_000 + 1_800_000);
    }

    // ---- TC-M4-04-5：并发上限 2 + pending_execs 等待队列 ----

    #[test]
    fn dispatch_exec_queues_third_beyond_limit() {
        use crate::action_exec::RunningTasks;
        // R4（P2-1）：满员态 = active_execs 计数（槽位预留同步化）——预置
        // 2 个在飞槽位 → 第 3 个 dispatch 必进 pending_execs（不写 running）
        let app = tauri::test::mock_app();
        let handle = app.handle();
        handle.manage(Arc::new(Mutex::new(RunningTasks::default())));
        // conn 也 manage（start_exec_run 会写库——满员分支不会走到）
        let c = Connection::open_in_memory().unwrap();
        crate::db::migrate(&c).unwrap();
        handle.manage(Mutex::new(c));
        // 调度器 state：预占 2 槽（等价两条在飞 exec）+ 规则在内存
        //（run_tick 分派形态：dispatch 的规则必在 st.rules；drain 的 P3-1
        // stale 校验按 id 查内存表）
        let mut rule = daily_rule(1, "10:00", None);
        rule.action_type = "exec".into();
        rule.action_params = Some(r#"{"command":"sleep 30"}"#.into());
        let sched = Arc::new(Mutex::new(RemindersState {
            active_execs: crate::action_exec::MAX_CONCURRENT_EXECS,
            rules: vec![RuleState {
                rule: rule.clone(),
                next_due_ms: 42_000,
            }],
            ..Default::default()
        }));
        crate::action_exec::dispatch_exec(handle, &sched, &rule, 12345);
        {
            let st = sched.lock().unwrap();
            assert_eq!(st.pending_execs.len(), 1, "第 3 个任务进等待队列");
            assert_eq!(st.pending_execs[0].rule.id, 1);
            assert_eq!(st.pending_execs[0].scheduled_at_ms, 12345);
        }
        // drain：槽位仍满 → 不出队
        crate::action_exec::drain_pending_execs(handle, &sched);
        assert_eq!(sched.lock().unwrap().pending_execs.len(), 1);
        // 释放一个槽位（run_task 完成回调的锁内递减语义）→ drain 出队
        sched.lock().unwrap().active_execs -= 1;
        crate::action_exec::drain_pending_execs(handle, &sched);
        assert!(
            sched.lock().unwrap().pending_execs.is_empty(),
            "空位出现 → 出队"
        );
        assert_eq!(
            sched.lock().unwrap().active_execs,
            crate::action_exec::MAX_CONCURRENT_EXECS,
            "出队即占槽（计数回满）"
        );
        // spawn 已发生：running 日志已写（mock app 直连同一 conn）；sleep 30
        // 不会先于断言完成 → running 态稳定可断言
        let db = handle.state::<Mutex<Connection>>();
        let conn = db.lock().unwrap();
        let (status,): (String,) = conn
            .query_row("SELECT status FROM action_logs ORDER BY id DESC LIMIT 1", [], |r| {
                Ok((r.get(0)?,))
            })
            .unwrap();
        assert_eq!(status, "running", "出队即写 running（spawn 时刻）");
        drop(conn);
        // 清理：杀掉测试拉起的进程——**先等登记就绪**（R5 P3-2：spawn 任务
        // 首 poll 才插入登记表，不等会 drain 空 → sleep 30 孤儿泄漏）
        {
            use tauri::Manager;
            let reg = handle.state::<Arc<Mutex<crate::action_exec::RunningTasks>>>();
            for _ in 0..100 {
                if reg.lock().unwrap().len() >= 1 {
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(50));
            }
            let mut r = reg.lock().unwrap();
            for (_, proc_) in r.tasks.drain() {
                crate::action_exec::kill_process_tree(proc_.pid);
            }
        }
        let _ = rule;
    }

    /// R4 批量钉子（committer P2-1 必补）：**单 tick 3 个 due exec 同步循环
    /// 分派**（run_tick 形态）→ 恰 2 运行 + 1 排队——旧实现读
    /// `RunningTasks.len()`（登记要等 spawn 首 poll 才插入），同步循环里
    /// 3 次 dispatch 全部读到 0 → 超发 3 个 running；新实现 active_execs
    /// 在 sched 锁内同步自增，第 3 个必入队。drain 满员不超发同步钉住。
    #[test]
    fn batch_dispatch_three_due_execs_two_run_one_pending() {
        use crate::action_exec::{RunningTasks, MAX_CONCURRENT_EXECS};
        let app = tauri::test::mock_app();
        let handle = app.handle();
        handle.manage(Arc::new(Mutex::new(RunningTasks::default())));
        let c = Connection::open_in_memory().unwrap();
        crate::db::migrate(&c).unwrap();
        handle.manage(Mutex::new(c));
        let sched = Arc::new(Mutex::new(RemindersState::default()));
        // 3 条 exec 规则（同 tick 到期——多条 daily 同 HH:MM / 连环补跑形态）
        let mk = |id: i64, cmd: &str| {
            let mut r = daily_rule(id, "10:00", None);
            r.action_type = "exec".into();
            r.action_params = Some(format!(r#"{{"command":"{cmd}"}}"#).into());
            r
        };
        // sleep 45：断言期进程稳定存活 + 清理万一漏杀时 45s 自愈（不长命孤儿）
        let rules = vec![
            mk(1, "sleep 45"),
            mk(2, "sleep 45"),
            mk(3, "sleep 45"),
        ];
        // run_tick 的同步循环形态：顺序 dispatch，无 await
        for r in &rules {
            crate::action_exec::dispatch_exec(handle, &sched, r, 42_000);
        }
        {
            let st = sched.lock().unwrap();
            assert_eq!(st.active_execs, MAX_CONCURRENT_EXECS, "恰占 2 槽");
            assert_eq!(st.pending_execs.len(), 1, "第 3 个进等待队列");
            assert_eq!(st.pending_execs[0].rule.id, 3, "排队的是最后分派的");
        }
        // 无第三行 running（排队的未写库）
        let running_count = |handle: &tauri::AppHandle<tauri::test::MockRuntime>| -> i64 {
            use tauri::Manager;
            let db = handle.state::<Mutex<Connection>>();
            let conn = db.lock().unwrap();
            conn.query_row(
                "SELECT COUNT(*) FROM action_logs WHERE status = 'running'",
                [],
                |r| r.get(0),
            )
            .unwrap()
        };
        assert_eq!(running_count(handle), 2, "恰 2 行 running（第 3 个不写）");
        // drain 超发场景：槽位已满 → 不出队、不新增 running
        crate::action_exec::drain_pending_execs(handle, &sched);
        assert_eq!(sched.lock().unwrap().pending_execs.len(), 1, "满员 drain 不出队");
        assert_eq!(running_count(handle), 2, "满员 drain 不新增 running");
        // 清理：先清队列（防杀进程唤醒完成回调 → 递减 → drain 启动第 3 个），
        // 再等登记就绪杀进程组
        sched.lock().unwrap().pending_execs.clear();
        {
            use tauri::Manager;
            let reg = handle.state::<Arc<Mutex<RunningTasks>>>();
            for _ in 0..100 {
                if reg.lock().unwrap().len() >= 2 {
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(50));
            }
            let mut r = reg.lock().unwrap();
            for (_, proc_) in r.tasks.drain() {
                crate::action_exec::kill_process_tree(proc_.pid);
            }
        }
    }

    /// R4 顺手修复 P3-1：等待队列的 stale 快照——规则删除（reload 后不在
    /// 内存）的排队条目出队时丢弃，不执行已删规则、不占槽。
    #[test]
    fn drain_drops_stale_rule_snapshots() {
        use crate::action_exec::RunningTasks;
        let app = tauri::test::mock_app();
        let handle = app.handle();
        handle.manage(Arc::new(Mutex::new(RunningTasks::default())));
        let c = Connection::open_in_memory().unwrap();
        crate::db::migrate(&c).unwrap();
        handle.manage(Mutex::new(c));
        let live = {
            let mut r = daily_rule(7, "10:00", None);
            r.action_type = "exec".into();
            r.action_params = Some(r#"{"command":"sleep 45"}"#.into());
            r
        };
        let mut stale = daily_rule(999, "10:00", None);
        stale.action_type = "exec".into();
        stale.action_params = Some(r#"{"command":"sleep 45"}"#.into());
        let sched = Arc::new(Mutex::new(RemindersState {
            // 内存规则表只含 live（id=7）——999 已删除
            rules: vec![RuleState {
                rule: live.clone(),
                next_due_ms: i64::MAX,
            }],
            pending_execs: vec![
                crate::action_exec::PendingExec {
                    rule: stale,
                    scheduled_at_ms: 7_000,
                },
                crate::action_exec::PendingExec {
                    rule: live.clone(),
                    scheduled_at_ms: 8_000,
                },
            ]
            .into(),
            ..Default::default()
        }));
        crate::action_exec::drain_pending_execs(handle, &sched);
        {
            let st = sched.lock().unwrap();
            assert!(st.pending_execs.is_empty(), "队列排空（stale 丢弃 + live 启动）");
            assert_eq!(st.active_execs, 1, "仅 live 占槽");
        }
        use tauri::Manager;
        let db = handle.state::<Mutex<Connection>>();
        let conn = db.lock().unwrap();
        let (cnt, only_id): (i64, i64) = conn
            .query_row(
                "SELECT COUNT(*), MAX(reminder_id) FROM action_logs WHERE status = 'running'",
                [],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .unwrap();
        assert_eq!(cnt, 1, "只启动 1 个（stale 未执行）");
        assert_eq!(only_id, 7, "启动的是 live 规则");
        drop(conn);
        // 清理
        {
            let reg = handle.state::<Arc<Mutex<RunningTasks>>>();
            for _ in 0..100 {
                if reg.lock().unwrap().len() >= 1 {
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(50));
            }
            let mut r = reg.lock().unwrap();
            for (_, proc_) in r.tasks.drain() {
                crate::action_exec::kill_process_tree(proc_.pid);
            }
        }
    }

    /// R5（tester R4 P2）：**排队中规则 reload 后不重复 fire**——实机缺陷形态：
    /// 3 条 once 同分钟触发，第 3 条排队；排队期间 CRUD reload 重建内存（排队
    /// 条目 handled 只在内存）→ next_due 回过去时刻 → 下 tick 重复 fire →
    /// 队列同规则重复条目 → 双重执行。修复 = dispatch_exec 入口无条件
    /// mark_triggered 落库（排队分支持久化）+ run_tick 分派前按 id 查 pending
    /// 去重（毫秒窗口兜底）。对照断言：非排队规则（disabled daily）reload 后
    /// 照常重算（过去时刻补跑判定入口不回归）。
    #[test]
    fn queued_rule_reload_does_not_refire_or_duplicate() {
        use crate::action_exec::RunningTasks;
        let app = tauri::test::mock_app();
        let handle = app.handle();
        let c = conn();
        // 3 条 once exec 同刻（now+120s：分钟截断后必然严格未来、过 validate
        // 未来校验；next_due 手动置过去模拟到点）+ 1 条 disabled daily（对照）
        let at_local = {
            let at = now_ms() + 120_000;
            DateTime::from_timestamp_millis(at)
                .unwrap()
                .with_timezone(&Local)
                .format("%Y-%m-%dT%H:%M")
                .to_string()
        };
        let mut ids = Vec::new();
        for i in 0..3 {
            let mut inp = input("custom", &format!("排队钉子 {i}"), 30);
            inp.schedule_kind = "once".into();
            inp.schedule_at = Some(at_local.clone());
            inp.action_type = "exec".into();
            inp.action_params = Some(r#"{"command":"sleep 20"}"#.into());
            ids.push(insert_rule(&c, &inp).unwrap().id);
        }
        // at 置真实过去（insert 需未来过 validate；UPDATE 绕行模拟"已到点"——
        // 实机缺陷形态即 at 为过去时刻）
        let at_past = {
            let at = now_ms() - 120_000;
            DateTime::from_timestamp_millis(at)
                .unwrap()
                .with_timezone(&Local)
                .format("%Y-%m-%dT%H:%M")
                .to_string()
        };
        for id in &ids {
            c.execute(
                "UPDATE reminders SET schedule_at = ?2 WHERE id = ?1",
                params![id, at_past],
            )
            .unwrap();
        }
        let mut daily_inp = input("custom", "对照（停用 daily）", 30);
        daily_inp.schedule_kind = "daily".into();
        daily_inp.schedule_at = Some("09:00".into());
        daily_inp.enabled = false;
        let daily_id = insert_rule(&c, &daily_inp).unwrap().id;

        let sched = Arc::new(Mutex::new(RemindersState::load(&c).unwrap()));
        handle.manage(Arc::new(Mutex::new(RunningTasks::default())));
        handle.manage(Mutex::new(c));

        // 模拟到点：3 条 once 的 next_due 置过去
        {
            let mut st = sched.lock().unwrap();
            for rs in st.rules.iter_mut() {
                if rs.rule.schedule_kind == "once" {
                    rs.next_due_ms = now_ms() - 1_000;
                }
            }
        }
        // tick1：3 个 exec fire → 2 启动 + 1 排队
        run_tick(handle, &sched);
        {
            let st = sched.lock().unwrap();
            assert_eq!(st.active_execs, 2, "恰 2 槽");
            assert_eq!(st.pending_execs.len(), 1, "第 3 个排队");
        }
        let daily_due_before: i64 = {
            let st = sched.lock().unwrap();
            st.rules
                .iter()
                .find(|rs| rs.rule.id == daily_id)
                .unwrap()
                .next_due_ms
        };
        assert!(
            daily_due_before > now_ms() && daily_due_before != i64::MAX,
            "对照 daily（未处理，created=刚才）常规值 = 次日 09:00"
        );

        // ---- 排队期间 CRUD reload（缺陷触发条件）----
        {
            let db = handle.state::<Mutex<Connection>>();
            let conn = db.lock().unwrap();
            sched.lock().unwrap().reload(&conn).unwrap();
        }
        // 修复点 1：排队条目 handled 已落库 → reload 重算 once → MAX（不复活）
        {
            let st = sched.lock().unwrap();
            for id in &ids {
                let due = st
                    .rules
                    .iter()
                    .find(|rs| rs.rule.id == *id)
                    .unwrap()
                    .next_due_ms;
                assert_eq!(due, i64::MAX, "once #{id} reload 后不复活（handled 持久化）");
            }
            // 对照：非排队 daily 照常重算（常规值不受排队保护波及）
            let daily_due = st
                .rules
                .iter()
                .find(|rs| rs.rule.id == daily_id)
                .unwrap()
                .next_due_ms;
            assert_eq!(
                daily_due, daily_due_before,
                "非排队规则 reload 语义不回归（重算结果一致）"
            );
        }

        // tick2：无重复 fire → 队列无重复条目、无新 running
        run_tick(handle, &sched);
        {
            let st = sched.lock().unwrap();
            assert_eq!(st.pending_execs.len(), 1, "队列无重复条目");
            assert_eq!(st.pending_execs[0].rule.id, ids[2], "排队的仍是原第 3 条");
        }
        // db：3 条 once 的 handled 标记全落库（dispatch 时刻）
        {
            let db = handle.state::<Mutex<Connection>>();
            let conn = db.lock().unwrap();
            for id in &ids {
                let (lt,): (Option<String>,) = conn
                    .query_row(
                        "SELECT last_triggered_at FROM reminders WHERE id = ?1",
                        [id],
                        |r| Ok((r.get(0)?,)),
                    )
                    .unwrap();
                assert!(lt.is_some(), "once #{id} handled 已持久化");
            }
        }

        // 清理：清队列（防出队）+ 等登记就绪 + 杀进程组
        sched.lock().unwrap().pending_execs.clear();
        {
            use tauri::Manager;
            let reg = handle.state::<Arc<Mutex<RunningTasks>>>();
            for _ in 0..100 {
                if reg.lock().unwrap().len() >= 2 {
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(50));
            }
            let mut r = reg.lock().unwrap();
            for (_, proc_) in r.tasks.drain() {
                crate::action_exec::kill_process_tree(proc_.pid);
            }
        }
    }

    // ---- TC-M4-07：validate kind 切换重置无关字段 ----

    #[test]
    fn normalize_resets_unrelated_fields_on_kind_switch() {
        let c = conn();
        // interval 行：schedule_at/weekdays 清空
        let mut inp = input("custom", "任务", 30);
        inp.schedule_kind = "interval".into();
        inp.schedule_at = Some("10:00".into()); // 应被清
        inp.schedule_weekdays = Some("[1,3]".into()); // 应被清
        let r1 = insert_rule(&c, &inp).unwrap();
        assert_eq!(r1.schedule_at, None);
        assert_eq!(r1.schedule_weekdays, None);
        assert_eq!(r1.interval_minutes, 30);
        // daily 行：start/end 窗口清空 + interval 恒 0
        let mut inp = input("custom", "定点", 30); // interval>0 传入
        inp.schedule_kind = "daily".into();
        inp.schedule_at = Some("09:00".into());
        inp.start_time = Some("08:00".into()); // 应被清（防 in_window 卡住误 skipped）
        inp.end_time = Some("22:00".into());
        inp.schedule_weekdays = Some("[1,3,5]".into());
        let r2 = insert_rule(&c, &inp).unwrap();
        assert_eq!(r2.interval_minutes, 0, "P2-6：daily 行 interval 恒 0");
        assert_eq!(r2.start_time, None);
        assert_eq!(r2.end_time, None);
        assert_eq!(r2.schedule_weekdays.as_deref(), Some("[1,3,5]"));
        // once 行：过去时刻拒绝
        let mut past = input("custom", "过期", 0);
        past.schedule_kind = "once".into();
        past.schedule_at = Some("2020-01-01T09:00".into());
        assert!(insert_rule(&c, &past).is_err(), "once 过去时刻 validate 拒绝");
        // weekdays 非法元素拒绝 / JSON 拒绝
        let mut badw = input("custom", "x", 0);
        badw.schedule_kind = "daily".into();
        badw.schedule_at = Some("09:00".into());
        badw.schedule_weekdays = Some("[0,8]".into());
        assert!(insert_rule(&c, &badw).is_err());
        badw.schedule_weekdays = Some("not json".into());
        assert!(insert_rule(&c, &badw).is_err());
        // exec：action_params JSON 解析失败拒绝（TC-M4-01-4）
        let mut bade = input("custom", "执行", 0);
        bade.schedule_kind = "once".into();
        bade.schedule_at = Some("2030-01-01T09:00".into());
        bade.action_type = "exec".into();
        bade.action_params = Some("{not json".into());
        assert!(insert_rule(&c, &bade).is_err(), "action_params JSON 失败拒绝");
        // exec 正常：kind 强制 custom + 参数原样存
        bade.action_params = Some(r#"{"command":"echo hi","timeout_minutes":10}"#.into());
        let r3 = insert_rule(&c, &bade).unwrap();
        assert_eq!(r3.action_type, "exec");
        assert_eq!(r3.kind, "custom");
        assert!(r3.action_params.as_deref().unwrap().contains("echo hi"));
        // notify 缺省字段兼容：v1 载荷（无新字段）→ notify/interval
        let r4 = insert_rule(&c, &input("hydration", "喝水", 30)).unwrap();
        assert_eq!(r4.action_type, "notify");
        assert_eq!(r4.schedule_kind, "interval");
    }

    // ---- TC-M4-13/14：snooze / skip_once（状态机 + 命令） ----

    #[test]
    fn skip_once_advances_by_kind_and_clears_snooze() {
        // daily：next_due → 下个匹配日；snooze 未过期 → 一并清（N2 内存侧）
        let at = daily_at(0, 10, 0);
        let mut rule = daily_rule(1, "10:00", None);
        rule.snooze_until = Some(rfc(at + 600_000));
        let mut st = state_with(rule, at);
        st.rules[0].next_due_ms = at;
        let cleared = st.skip_once(1, at - 60_000).unwrap();
        assert!(cleared, "snooze 未过期 → 通知写表清除");
        assert_eq!(st.rules[0].rule.snooze_until, None);
        assert_eq!(st.rules[0].next_due_ms, daily_at(1, 10, 0), "跳过 → 下个匹配日");
        // 本周期不再触发
        let (fired, skipped) = st.collect_due(at + 3_600_000, &rfc(at), 600);
        assert!(fired.is_empty() && skipped.is_empty(), "跳过不触发不记录");
        // once → MAX
        let mut st2 = state_with(once_rule(2, daily_at(1, 21, 0)), 1);
        st2.rules[0].next_due_ms = daily_at(1, 21, 0);
        assert!(!st2.skip_once(2, 1).unwrap(), "无 snooze → 不写表");
        assert_eq!(st2.rules[0].next_due_ms, i64::MAX);
        // interval → +interval
        let mut st3 = state_with(base_rule(3, 30), 1_000_000);
        st3.rules[0].next_due_ms = 1_000_000;
        st3.skip_once(3, 1_000_000).unwrap();
        assert_eq!(st3.rules[0].next_due_ms, 1_000_000 + 1_800_000);
        // 不存在 id → Err
        assert!(st.skip_once(999, 1).is_err());
    }

    #[test]
    fn reminders_snooze_command_writes_until_and_closes_log() {
        // 命令级（mock runtime）：写 snooze_until + log 结案 via='snooze' +
        // 内存 next_due 置为
        let app = tauri::test::mock_app();
        let handle = app.handle();
        let c = conn();
        let r = insert_rule(&c, &input("hydration", "喝水", 30)).unwrap();
        let log_id = insert_log(&c, r.id, &rfc(1000)).unwrap();
        let mut st = RemindersState::load(&c).unwrap();
        st.rules[0].next_due_ms = 500;
        handle.manage(Arc::new(Mutex::new(st)));
        handle.manage(Mutex::new(c));
        reminders_snooze(
            handle.clone(),
            handle.state::<Arc<Mutex<RemindersState>>>(),
            log_id,
        )
        .unwrap();
        let (until,): (Option<String>,) = {
            let db = handle.state::<Mutex<Connection>>();
            let conn = db.lock().unwrap();
            conn.query_row("SELECT snooze_until FROM reminders WHERE id = ?1", [r.id], |row| {
                Ok((row.get(0)?,))
            })
            .unwrap()
        };
        assert!(until.is_some(), "snooze_until 已写表（持久化）");
        let via: String = {
            let db = handle.state::<Mutex<Connection>>();
            let conn = db.lock().unwrap();
            conn.query_row(
                "SELECT dismissed_via FROM reminder_logs WHERE id = ?1",
                [log_id],
                |row| row.get(0),
            )
            .unwrap()
        };
        assert_eq!(via, "snooze", "当前 log 结案 via='snooze'");
        let st = handle.state::<Arc<Mutex<RemindersState>>>();
        let s = st.lock().unwrap();
        let until_ms = parse_rfc3339_ms(until.as_deref().unwrap()).unwrap();
        assert_eq!(
            s.rules[0].next_due_ms, until_ms,
            "内存 next_due 置为 snooze_until（直接置为，非 max——P1-1）"
        );
        // exec 型拒绝 snooze（仅 notify）
        let c2 = conn();
        let mut inp = input("custom", "执行", 0);
        inp.schedule_kind = "once".into();
        inp.schedule_at = Some("2030-01-01T09:00".into());
        inp.action_type = "exec".into();
        inp.action_params = Some(r#"{"command":"echo x"}"#.into());
        let r2 = insert_rule(&c2, &inp).unwrap();
        let log2 = insert_log(&c2, r2.id, &rfc(1000)).unwrap();
        let app2 = tauri::test::mock_app();
        let h2 = app2.handle();
        h2.manage(Arc::new(Mutex::new(RemindersState::default())));
        h2.manage(Mutex::new(c2));
        assert!(reminders_snooze(
            h2.clone(),
            h2.state::<Arc<Mutex<RemindersState>>>(),
            log2
        )
        .is_err());
    }

    #[test]
    fn tasks_skip_once_command_clears_snooze_in_db() {
        let app = tauri::test::mock_app();
        let handle = app.handle();
        let c = conn();
        // interval 行插入（normalize 校验 1-1440），再 UPDATE 成 daily + snooze
        let r = insert_rule(&c, &input("custom", "定点", 30)).unwrap();
        c.execute(
            "UPDATE reminders SET schedule_kind = 'daily', schedule_at = '10:00', \
             snooze_until = ?2 WHERE id = ?1",
            params![r.id, rfc(now_ms() + 600_000)],
        )
        .unwrap();
        let mut st = RemindersState::load(&c).unwrap();
        // 直接构造 snooze 未过期的内存态
        st.rules[0].rule.snooze_until = Some(rfc(now_ms() + 600_000));
        st.rules[0].next_due_ms = now_ms() + 600_000;
        handle.manage(Arc::new(Mutex::new(st)));
        handle.manage(Mutex::new(c));
        tasks_skip_once(
            handle.clone(),
            handle.state::<Arc<Mutex<RemindersState>>>(),
            r.id,
        )
        .unwrap();
        let (until,): (Option<String>,) = {
            let db = handle.state::<Mutex<Connection>>();
            let conn = db.lock().unwrap();
            conn.query_row("SELECT snooze_until FROM reminders WHERE id = ?1", [r.id], |row| {
                Ok((row.get(0)?,))
            })
            .unwrap()
        };
        assert_eq!(until, None, "N2：写表同清（防 reload 复活）");
    }

    // ---- TC-M4-16：action_logs 增删查全链路 + 悬空保留 ----

    #[test]
    fn action_logs_crud_pagination_and_orphan_survival() {
        let c = conn();
        let r = insert_rule(&c, &input("custom", "执行", 30)).unwrap();
        // 60 条 ok 日志 + 1 条 running（004 起 insert 携带 label/command 快照；
        // 005 起 executed 位换 cwd 快照——Part C）
        for i in 0..60 {
            finish_action_log_with(
                &c,
                insert_action_log_running(
                    &c,
                    r.id,
                    "exec",
                    "执行",
                    Some(&format!("cmd-{i}")),
                    Some("/tmp/loop"),
                    &rfc(1000 + i),
                    &rfc(1000 + i),
                )
                .unwrap(),
                "ok",
                crate::action_exec::SUMMARY_OK,
                Some(&format!("tail-{i}")),
                Some(0),
                &rfc(2000 + i),
            )
            .unwrap();
        }
        insert_action_log_running(
            &c,
            r.id,
            "exec",
            "运行中",
            Some("run-cmd"),
            Some("/tmp/run"),
            &rfc(999_000),
            &rfc(999_000),
        )
        .unwrap();
        // 第 1 页：倒序（最新 running 在前）10 条（§二十七起分页 10 条/页）
        let (page1, total) = list_action_logs(&c, None, 1).unwrap();
        assert_eq!(total, 61);
        assert_eq!(page1.len(), 10);
        assert_eq!(page1[0].status, "running", "倒序：id 最大（running 那条）在前");
        assert_eq!(page1[1].output_tail.as_deref(), Some("tail-59"));
        // 第 2 页：10 条，末条 tail-41（61 条倒序：offset 10..20）
        let (page2, _) = list_action_logs(&c, None, 2).unwrap();
        assert_eq!(page2.len(), 10);
        assert_eq!(page2.last().unwrap().output_tail.as_deref(), Some("tail-41"));
        // 第 7 页（末页）：1 条——最早一条位于末页末尾的边界覆盖
        let (page7, _) = list_action_logs(&c, None, 7).unwrap();
        assert_eq!(page7.len(), 1);
        assert_eq!(page7.last().unwrap().output_tail.as_deref(), Some("tail-0"));
        // 按规则过滤
        let (filtered, ftotal) = list_action_logs(&c, Some(r.id), 1).unwrap();
        assert_eq!(ftotal, 61);
        assert_eq!(filtered.len(), 10);
        // 删除规则 → 历史保留（悬空 reminder_id + 冗余快照可读）
        delete_rule(&c, r.id).unwrap();
        let (after, atotal) = list_action_logs(&c, None, 1).unwrap();
        assert_eq!(atotal, 61, "规则删除后历史保留");
        assert_eq!(after[0].action_type, "exec", "action_type 冗余快照可读");
        // 快照列在规则删除后仍可读（Part C：label/command/cwd 悬空保留）
        assert_eq!(after[0].label.as_deref(), Some("运行中"), "label 快照悬空可读");
        assert_eq!(after[0].command.as_deref(), Some("run-cmd"), "command 快照悬空可读");
        assert_eq!(after[0].cwd.as_deref(), Some("/tmp/run"), "cwd 快照悬空可读");
        // skipped 插入（超窗两来源共用形状；005 起带 label/command/cwd 快照）
        let _ = insert_action_log_skipped(
            &c,
            999,
            "悬空例程",
            Some("planned-cmd"),
            Some("/tmp/plan"),
            crate::action_exec::SUMMARY_MISSED,
            &rfc(1000),
            &rfc(2000),
        )
        .unwrap();
        let (rows, total) = list_action_logs(&c, None, 1).unwrap();
        assert_eq!(total, 62);
        assert_eq!(rows[0].status, "skipped", "倒序：最新 skipped 在首页首位");
        assert_eq!(rows[0].label.as_deref(), Some("悬空例程"));
        assert_eq!(rows[0].command.as_deref(), Some("planned-cmd"));
        assert_eq!(rows[0].cwd.as_deref(), Some("/tmp/plan"), "skipped 亦快照 cwd（配置了但没跑的完整上下文）");
    }

    // ---- R2（TC-M4-15-1 P2）：finish_action_log_with 的 running 守卫 ----

    #[test]
    fn finish_action_log_with_guarded_by_running_status() {
        // 守卫钉子：已离开 running 态的行（如 abort 先行结案 interrupted、
        // 或已完成 ok）不被后续完成回写覆盖——两个写入方以行状态为屏障
        let c = conn();
        let log_id =
            insert_action_log_running(&c, 1, "exec", "任务", None, None, &rfc(1000), &rfc(1000))
                .unwrap();
        // running → 首次正常回写成功
        finish_action_log_with(
            &c, log_id, "ok", crate::action_exec::SUMMARY_OK, Some("out"), Some(0), &rfc(2000),
        )
        .unwrap();
        // 迟到的第二次回写（failed）被守卫拦下：仍是 ok
        finish_action_log_with(
            &c, log_id, "failed", crate::action_exec::SUMMARY_FAILED, None, Some(9), &rfc(3000),
        )
        .unwrap();
        let (status, summary, exit_code): (String, String, Option<i32>) = c
            .query_row(
                "SELECT status, summary, exit_code FROM action_logs WHERE id = ?1",
                [log_id],
                |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?)),
            )
            .unwrap();
        assert_eq!(status, "ok", "已结案行不被二次回写覆盖");
        assert_eq!(summary, crate::action_exec::SUMMARY_OK);
        assert_eq!(exit_code, Some(0), "旧值全保留（守卫 = 整行不动）");
        // abort 结案（interrupted）后的完成回写同样被拦——action_exec 侧的
        // 真实进程竞态钉子覆盖该主场景，此处钉纯 SQL 语义
        let log2 =
            insert_action_log_running(&c, 2, "exec", "任务", None, None, &rfc(1000), &rfc(1000))
                .unwrap();
        c.execute(
            "UPDATE action_logs SET status = 'failed', summary = ?2 WHERE id = ?1",
            params![log2, crate::action_exec::SUMMARY_INTERRUPTED],
        )
        .unwrap();
        finish_action_log_with(
            &c, log2, "failed", crate::action_exec::SUMMARY_FAILED, None, None, &rfc(4000),
        )
        .unwrap();
        let summary2: String = c
            .query_row("SELECT summary FROM action_logs WHERE id = ?1", [log2], |r| r.get(0))
            .unwrap();
        assert_eq!(summary2, crate::action_exec::SUMMARY_INTERRUPTED, "interrupted 不被通用 failed 覆盖");
    }

    // ---- 模板命令：exec trigger_now 走分派（试一试 = 真实执行，P3-9） ----

    #[test]
    fn trigger_now_exec_dispatch_writes_running_log() {
        let app = tauri::test::mock_app();
        let handle = app.handle();
        let c = conn();
        let mut inp = input("custom", "执行任务", 30);
        inp.schedule_kind = "once".into();
        inp.schedule_at = Some("2030-01-01T09:00".into());
        inp.action_type = "exec".into();
        inp.action_params = Some(r#"{"command":"echo test-ran"}"#.into());
        let r = insert_rule(&c, &inp).unwrap();
        let st = Arc::new(Mutex::new(RemindersState::load(&c).unwrap()));
        handle.manage(st);
        // RunningTasks 登记（dispatch_exec 读取；issue #9：先 manage 再触发）
        handle.manage(Arc::new(Mutex::new(crate::action_exec::RunningTasks::default())));
        handle.manage(Mutex::new(c));
        let status = reminders_trigger_now(
            handle.clone(),
            handle.state::<Arc<Mutex<RemindersState>>>(),
            r.id,
        )
        .unwrap();
        assert_eq!(status, "fired");
        // dispatch_exec 已 insert running 日志（mock runtime 下 spawn 可能未完成，
        // 但 running 行同步写——钉住分派确实发生）
        let (n,): (i64,) = {
            let db = handle.state::<Mutex<Connection>>();
            let conn = db.lock().unwrap();
            conn.query_row("SELECT COUNT(*) FROM action_logs", [], |row| Ok((row.get(0)?,)))
                .unwrap()
        };
        assert!(n >= 1, "exec 试一试真实执行（写 action_logs）");
    }
}
