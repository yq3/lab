//! 多 session 状态机 + 优先级合并（DESIGN §3.3，TC-EV-16/TC-EV-17/TC-EV-06；
//! v2 M1 复合 key 化，V2-DESIGN §1.5，TC-INT-10）。
//!
//! - 每个会话以复合键 `agent:sessionId`（v2 M1 起）维护独立的 `SessionRecord`
//!   （最近一次归一化状态 + 归属 agent + 该事件的时间戳）——opencode sessionID
//!   （`ses_*`）与 CC UUID 均不含 `:`，天然无歧义（R6）。
//! - 单只宠物显示按 **v2 M6 两层合并**（V2-DESIGN §6.1）：10s 活跃窗内按
//!   既有优先级表合并（同 priority 平局取最新事件）；窗口空时显示最近活跃
//!   session 的状态（fallback，不做全量优先级合并——陈旧 error 不复活抢镜）；
//!   `display(now)` 返回 `DisplayState { kind, agent }`，归属来自
//!   `SessionRecord.agent` 字段而非反解析 key（V2-DESIGN §1.5 P3-1）。
//! - 长时间无事件的 session 回收为 `idle`（30s，`/health` 不参与）；任一瞬态
//!   超时兜底：`N` 秒（默认 30s，可配）内无新事件 → 回退 `working`，再无事件 30s
//!   → 回退 `idle`（§3.1 ③ / TC-EV-06）。
//!
//! 本模块不依赖 Tauri，纯 `std`，便于 `cargo test` 直接覆盖。

use std::collections::HashMap;
use std::time::{Duration, Instant};

/// v2 M6（V2-DESIGN §6.0 用户裁定）：活跃窗口 10s——对齐 opencode 流式心跳
/// 实际节奏（插件 reaction 桶 10s 冷却 → 生成中会话约每 10s 一事件；活跃语义
/// =「正在产出」，SCOPE 示例值 5s 太严会让生成中会话掉窗）。
pub const ACTIVITY_WINDOW_MS: u64 = 10_000;

/// 活跃窗口（`Duration` 形态，`display(now)` 消费）。
pub const ACTIVITY_WINDOW: Duration = Duration::from_millis(ACTIVITY_WINDOW_MS);

/// 归一化事件状态（与前端 `src/lib/state.ts` 的 8 种常量一一对应，两端一致）。
#[derive(Clone, Copy, PartialEq, Eq, Debug, Hash)]
pub enum Kind {
    Idle,
    Working,
    Thinking,
    Editing,
    Testing,
    WaitingPermission,
    Success,
    Error,
}

impl Kind {
    /// 8 种归一化取值（顺序即 DESIGN §6.1 的列举顺序，供校验与遍历）。
    #[allow(dead_code)]
    pub const ALL: [Kind; 8] = [
        Kind::Idle,
        Kind::Working,
        Kind::Thinking,
        Kind::Editing,
        Kind::Testing,
        Kind::WaitingPermission,
        Kind::Success,
        Kind::Error,
    ];

    pub fn as_str(&self) -> &'static str {
        match self {
            Kind::Idle => "idle",
            Kind::Working => "working",
            Kind::Thinking => "thinking",
            Kind::Editing => "editing",
            Kind::Testing => "testing",
            Kind::WaitingPermission => "waiting-permission",
            Kind::Success => "success",
            Kind::Error => "error",
        }
    }

    /// 从 HTTP body 的 `kind` 字段解析（非法值返回 `None`，由调用方回 400）。
    pub fn parse(s: &str) -> Option<Kind> {
        match s {
            "idle" => Some(Kind::Idle),
            "working" => Some(Kind::Working),
            "thinking" => Some(Kind::Thinking),
            "editing" => Some(Kind::Editing),
            "testing" => Some(Kind::Testing),
            "waiting-permission" => Some(Kind::WaitingPermission),
            "success" => Some(Kind::Success),
            "error" => Some(Kind::Error),
            _ => None,
        }
    }

    /// 显示状态优先级（数值越大越优先）。
    ///
    /// DESIGN §3.3 只列出 `error > waiting-permission > testing > editing >
    /// thinking > working > idle`（未列 `success`）；M2 定案把 `success` 插入
    /// `thinking` 与 `working` 之间——`success` 是瞬态完成信号，低于进行中的
    /// 思考/编辑/测试，但高于泛化的 `working`。
    pub fn priority(&self) -> u8 {
        match self {
            Kind::Error => 7,
            Kind::WaitingPermission => 6,
            Kind::Testing => 5,
            Kind::Editing => 4,
            Kind::Thinking => 3,
            Kind::Success => 2,
            Kind::Working => 1,
            Kind::Idle => 0,
        }
    }

    /// 瞬态状态（DESIGN §3.1：editing/thinking/testing/waiting-permission）。
    /// 瞬态会先超时回退 `working`，再超时回退 `idle`（两步）。
    pub fn is_transient(&self) -> bool {
        matches!(
            self,
            Kind::Thinking | Kind::Editing | Kind::Testing | Kind::WaitingPermission
        )
    }
}

/// 单个 session 的运行时状态。
#[derive(Clone, Debug)]
pub struct SessionRecord {
    pub kind: Kind,
    /// 归属 agent（"opencode" / "claude-code"；来自 `/state` body，非反解析 key）。
    pub agent: String,
    /// 最近一次 `/state` 事件到达的时刻（也用于瞬态超时与 idle 回收的计时）。
    pub last_event_at: Instant,
}

/// 合并后的显示状态（v2 M1：携带归属 agent，供 `pulsepet://state` payload；
/// 前端 M1 只存不显示，M2 状态芯片消费，V2-DESIGN §1.5/§1.6）。
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DisplayState {
    pub kind: Kind,
    /// argmax 获胜 session 的归属 agent；无 session 时为空串（前端优雅降级）。
    pub agent: String,
}

/// 多 session 状态机（`HashMap<复合键 "agent:sessionId", SessionRecord>`）。
#[derive(Default)]
pub struct SessionStateMachine {
    sessions: HashMap<String, SessionRecord>,
}

impl SessionStateMachine {
    pub fn new() -> Self {
        Self::default()
    }

    /// 记录一条 `/state` 事件（覆盖该复合键 session 的最近状态）。
    ///
    /// 复合 key 构造的唯一入口（V2-DESIGN §1.5：合并/回收算法不变，仅 key 构造
    /// 点变化）；同 sessionId 不同 agent 互不覆盖（TC-INT-10-2 / R6）。
    pub fn apply_event(&mut self, agent: &str, session_id: &str, kind: Kind, now: Instant) {
        self.sessions.insert(
            format!("{agent}:{session_id}"),
            SessionRecord {
                kind,
                agent: agent.to_string(),
                last_event_at: now,
            },
        );
    }

    /// 时间推进：处理瞬态超时回退与 idle 回收（由后台定时器周期调用）。
    ///
    /// 规则（TC-EV-06 / TC-EV-17）：
    /// - 瞬态 `>= transient_timeout` 无新事件 → 回退 `working`，并把计时基准重置为
    ///   `now`（保证「再 30s → idle」是完整的新窗口，而非瞬态一步跳到 idle）。
    /// - 非瞬态 `>= idle_timeout` 无新事件 → 回收：**从 map 中 remove 该 session**
    ///   （P3-⑥，M2 遗留：原先只置 `Idle` 不删除，条目常驻导致内存随 session 数
    ///   无界增长；idle 条目同样按超时 remove，显示语义不变——缺席 = idle）。
    ///   回收发生在锁内（本方法持有 `&mut self`），与并发读取（`display`）天然互斥。
    pub fn tick(&mut self, now: Instant, transient_timeout: Duration, idle_timeout: Duration) {
        let mut expired: Vec<String> = Vec::new();
        for (id, rec) in self.sessions.iter_mut() {
            let elapsed = now.saturating_duration_since(rec.last_event_at);
            if rec.kind.is_transient() && elapsed >= transient_timeout {
                rec.kind = Kind::Working;
                rec.last_event_at = now;
            } else if !rec.kind.is_transient() && elapsed >= idle_timeout {
                expired.push(id.clone());
            }
        }
        for id in expired {
            self.sessions.remove(&id);
        }
    }

    /// 当前跟踪的 session 数（测试用：验证 P3-⑥ 回收即 remove）。
    #[cfg(test)]
    pub fn len(&self) -> usize {
        self.sessions.len()
    }

    /// 当前显示状态（v2 M6 两层合并，V2-DESIGN §6.1，注入时钟保单测）：
    ///
    /// ① **活跃集** = `last_event_at >= now - ACTIVITY_WINDOW` 的 session；
    /// ② 活跃集非空 → 集内按 `(priority, last_event_at)` 字典序取最大
    ///    （既有优先级表不变；同 priority 平局取 last_event_at 最新者——防
    ///    HashMap 迭代序任意决定胜者致芯片 agent 无因跳变，P2-2）；
    /// ③ 活跃集空 → 全量按 `(last_event_at, priority)` 取最大（与 ② 互为
    ///    镜像字典序）——显示最近活跃 session 的状态，不做全量优先级合并
    ///    （陈旧 error 不复活抢镜）；
    /// ④ sessions 空 → Idle（v1 语义，agent 空、前端芯片降级）。
    ///
    /// display 成为时间函数后，**无事件时**的显示切换（掉窗让位瞬间）依赖
    /// lib.rs 的 1s 后台 notify 循环兜底（延迟 ≤1s）——该循环对 M6 语义
    /// 不可或缺，不可被优化掉（P3-6 注钉同样落在 lib.rs 循环处）。
    pub fn display(&self, now: Instant) -> DisplayState {
        // ① 活跃集：last_event_at >= now - 10s（闭区间，对齐插件 10s 心跳节奏）。
        //    checked_sub 防御 Instant 下界（进程启动 <10s 时全量视为活跃）；
        //    未来时刻的事件（时钟回拨注入）按活跃处理（saturating 语义）。
        let cutoff = now.checked_sub(ACTIVITY_WINDOW);
        let mut winner: Option<&SessionRecord> = None;
        for r in self.sessions.values() {
            let active = match cutoff {
                Some(c) => r.last_event_at >= c,
                None => true,
            };
            if !active {
                continue;
            }
            // ② 活跃集内 (priority, last_event_at) 字典序取最大：优先级表优先、
            //    同 priority 平局取最新事件（与 ③ 互为镜像字典序，P2-2——
            //    显式比较保证与 HashMap 迭代序无关）
            let better = match winner {
                None => true,
                Some(w) => {
                    (r.kind.priority(), r.last_event_at) > (w.kind.priority(), w.last_event_at)
                }
            };
            if better {
                winner = Some(r);
            }
        }
        if let Some(r) = winner {
            return DisplayState {
                kind: r.kind,
                agent: r.agent.clone(),
            };
        }
        // ③ fallback：活跃集空 → 全量 (last_event_at, priority) 字典序最大
        //    （最近活跃优先、平局取 priority 高者）
        self.sessions
            .values()
            .max_by_key(|r| (r.last_event_at, r.kind.priority()))
            .map(|r| DisplayState {
                kind: r.kind,
                agent: r.agent.clone(),
            })
            .unwrap_or(DisplayState {
                // ④ sessions 空 → Idle（v1 语义，agent 空）
                kind: Kind::Idle,
                agent: String::new(),
            })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn secs(n: u64) -> Duration {
        Duration::from_secs(n)
    }

    #[test]
    fn parse_all_eight_kinds_roundtrip() {
        for k in Kind::ALL {
            assert_eq!(Kind::parse(k.as_str()), Some(k));
        }
        assert_eq!(Kind::parse("bogus"), None);
        assert_eq!(Kind::parse(""), None);
        assert_eq!(Kind::parse("WORKING"), None); // 大小写敏感，与前端常量一致
    }

    #[test]
    fn priority_total_order_matches_design() {
        // error > waiting-permission > testing > editing > thinking > success > working > idle
        assert!(Kind::Error.priority() > Kind::WaitingPermission.priority());
        assert!(Kind::WaitingPermission.priority() > Kind::Testing.priority());
        assert!(Kind::Testing.priority() > Kind::Editing.priority());
        assert!(Kind::Editing.priority() > Kind::Thinking.priority());
        assert!(Kind::Thinking.priority() > Kind::Success.priority());
        assert!(Kind::Success.priority() > Kind::Working.priority());
        assert!(Kind::Working.priority() > Kind::Idle.priority());
    }

    #[test]
    fn transient_states_are_the_four_expected() {
        assert!(Kind::Thinking.is_transient());
        assert!(Kind::Editing.is_transient());
        assert!(Kind::Testing.is_transient());
        assert!(Kind::WaitingPermission.is_transient());
        assert!(!Kind::Working.is_transient());
        assert!(!Kind::Idle.is_transient());
        assert!(!Kind::Success.is_transient());
        assert!(!Kind::Error.is_transient());
    }

    #[test]
    fn display_merges_highest_priority_across_sessions() {
        let mut m = SessionStateMachine::new();
        let t = Instant::now();
        m.apply_event("opencode", "a", Kind::Editing, t);
        m.apply_event("opencode", "b", Kind::Error, t);
        assert_eq!(m.display(t).kind, Kind::Error); // B error 覆盖 A editing（TC-EV-16）
        m.apply_event("opencode", "b", Kind::Working, t);
        assert_eq!(m.display(t).kind, Kind::Editing); // A editing 高于 B working
        m.apply_event("opencode", "a", Kind::Idle, t);
        assert_eq!(m.display(t).kind, Kind::Working);
    }

    #[test]
    fn empty_machine_displays_idle() {
        assert_eq!(SessionStateMachine::new().display(Instant::now()).kind, Kind::Idle);
    }

    #[test]
    fn idle_reclamation_after_30s_no_event() {
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("opencode", "a", Kind::Working, t0);
        // 29s 无事件 → 仍 working
        m.tick(t0 + secs(29), secs(30), secs(30));
        assert_eq!(m.display(t0 + secs(29)).kind, Kind::Working);
        // 30s 无事件 → idle（TC-EV-17）
        m.tick(t0 + secs(30), secs(30), secs(30));
        assert_eq!(m.display(t0 + secs(30)).kind, Kind::Idle);
    }

    #[test]
    fn transient_falls_back_to_working_then_idle() {
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("opencode", "a", Kind::Editing, t0);
        // 29s → 仍 editing（瞬态尚未超时）
        m.tick(t0 + secs(29), secs(30), secs(30));
        assert_eq!(m.display(t0 + secs(29)).kind, Kind::Editing);
        // 30s → 回退 working（TC-EV-06 第一步）
        m.tick(t0 + secs(30), secs(30), secs(30));
        assert_eq!(m.display(t0 + secs(30)).kind, Kind::Working);
        // working 再 29s → 仍 working
        m.tick(t0 + secs(59), secs(30), secs(30));
        assert_eq!(m.display(t0 + secs(59)).kind, Kind::Working);
        // working 再 30s（距回退 30s）→ idle（TC-EV-06 第二步）
        m.tick(t0 + secs(60), secs(30), secs(30));
        assert_eq!(m.display(t0 + secs(60)).kind, Kind::Idle);
    }

    #[test]
    fn transient_timeout_is_configurable() {
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("opencode", "a", Kind::Thinking, t0);
        // 5s 超时兜底：5s 后 → working
        m.tick(t0 + secs(5), secs(5), secs(30));
        assert_eq!(m.display(t0 + secs(5)).kind, Kind::Working);
    }

    #[test]
    fn new_event_refreshes_session_timer() {
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("opencode", "a", Kind::Editing, t0);
        // 20s 后又来一个新 editing 事件 → 计时重置，30s 后仍未超时
        m.apply_event("opencode", "a", Kind::Editing, t0 + secs(20));
        m.tick(t0 + secs(40), secs(30), secs(30));
        assert_eq!(m.display(t0 + secs(40)).kind, Kind::Editing);
    }

    // ---- P3-⑥：回收即 remove（内存不随 session 数无界增长） ----

    #[test]
    fn reclaimed_sessions_are_removed_from_map() {
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("opencode", "a", Kind::Working, t0);
        m.apply_event("opencode", "b", Kind::Idle, t0); // idle 条目同样按超时回收
        m.apply_event("opencode", "c", Kind::Success, t0); // token 汇报注入的 success 也会回收
        assert_eq!(m.len(), 3);
        m.tick(t0 + secs(30), secs(30), secs(30));
        assert_eq!(m.len(), 0, "非瞬态条目超时后应被 remove，而非常驻");
        assert_eq!(m.display(t0 + secs(30)).kind, Kind::Idle, "缺席 = idle，显示语义不变");
    }

    #[test]
    fn reclaimed_session_resumes_on_new_event() {
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("opencode", "a", Kind::Working, t0);
        m.tick(t0 + secs(30), secs(30), secs(30)); // 回收
        assert_eq!(m.len(), 0);
        // 回收后同一 session 来新事件 → 正常重建（不影响后续状态）
        m.apply_event("opencode", "a", Kind::Editing, t0 + secs(31));
        assert_eq!(m.display(t0 + secs(31)).kind, Kind::Editing);
        assert_eq!(m.len(), 1);
    }

    #[test]
    fn transient_two_step_reclaim_keeps_other_sessions() {
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("opencode", "a", Kind::Editing, t0);
        m.apply_event("opencode", "b", Kind::Working, t0 + secs(5)); // b 晚 5s
        m.tick(t0 + secs(30), secs(30), secs(30));
        // a：瞬态→working（计时重置）；b：非瞬态但才 25s → 保留
        assert_eq!(m.len(), 2);
        m.tick(t0 + secs(60), secs(30), secs(30));
        // a：working 30s → remove；b：working 55s → remove
        assert_eq!(m.len(), 0);
    }

    // ---- v2 M1：复合 key + DisplayState（TC-INT-10-2/3、TC-INT-05、R6） ----

    #[test]
    fn same_session_id_different_agents_do_not_overlap() {
        // TC-INT-10-2 / R6：`opencode:s1` 与 `claude-code:s1` 是两个独立条目
        let mut m = SessionStateMachine::new();
        let t = Instant::now();
        m.apply_event("opencode", "s1", Kind::Editing, t);
        m.apply_event("claude-code", "s1", Kind::Error, t);
        assert_eq!(m.len(), 2, "同 sessionId 不同 agent 应互不覆盖");
        let d = m.display(t);
        assert_eq!(d.kind, Kind::Error); // error 优先级最高（TC-INT-05-2）
        assert_eq!(d.agent, "claude-code");
        // CC 会话回 idle 不影响 opencode 会话的 editing
        m.apply_event("claude-code", "s1", Kind::Idle, t);
        let d = m.display(t);
        assert_eq!(d.kind, Kind::Editing);
        assert_eq!(d.agent, "opencode", "opencode 条目应原样保留");
        assert_eq!(m.len(), 2);
    }

    #[test]
    fn display_state_reports_owning_agent_from_field() {
        // TC-INT-10-3：归属来自 SessionRecord.agent 字段而非反解析 key
        let mut m = SessionStateMachine::new();
        let t = Instant::now();
        m.apply_event("opencode", "ses_aaa", Kind::Working, t);
        m.apply_event("claude-code", "uuid-bbb", Kind::WaitingPermission, t);
        let d = m.display(t);
        assert_eq!(d.kind, Kind::WaitingPermission);
        assert_eq!(d.agent, "claude-code");
        // 获胜者更换后 agent 跟随
        m.apply_event("opencode", "ses_aaa", Kind::Error, t);
        let d = m.display(t);
        assert_eq!(d.kind, Kind::Error);
        assert_eq!(d.agent, "opencode");
    }

    #[test]
    fn empty_machine_display_is_idle_with_empty_agent() {
        let d = SessionStateMachine::new().display(Instant::now());
        assert_eq!(d.kind, Kind::Idle);
        assert_eq!(d.agent, "");
    }

    #[test]
    fn cross_agent_priority_merge_follows_v1_order() {
        // TC-INT-05-2：跨 agent 优先级合并与 v1 算法一致
        // error > waiting-permission > testing > editing > thinking > working > idle
        let mut m = SessionStateMachine::new();
        let t = Instant::now();
        m.apply_event("claude-code", "c1", Kind::Error, t);
        m.apply_event("opencode", "o1", Kind::WaitingPermission, t);
        assert_eq!(m.display(t).kind, Kind::Error);
        m.apply_event("claude-code", "c1", Kind::Testing, t); // CC 降级
        assert_eq!(m.display(t).kind, Kind::WaitingPermission); // opencode 权限等待接管
        assert_eq!(m.display(t).agent, "opencode");
        m.apply_event("opencode", "o1", Kind::Idle, t);
        assert_eq!(m.display(t).kind, Kind::Testing);
        assert_eq!(m.display(t).agent, "claude-code");
    }

    #[test]
    fn tick_reclaims_composite_keys_per_session() {
        // 复合 key 条目照常参与瞬态超时/idle 回收（算法不变，TC-EV-06 不回归）
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("opencode", "s1", Kind::Editing, t0);
        m.apply_event("claude-code", "s1", Kind::Editing, t0);
        m.tick(t0 + secs(30), secs(30), secs(30));
        // 两条瞬态都回退 working（各自计时重置）
        assert_eq!(m.len(), 2);
        m.tick(t0 + secs(60), secs(30), secs(30));
        assert_eq!(m.len(), 0);
    }

    // ---- v2 M6（V2-DESIGN §6.1，TC-M6-01）：两层合并算法 ----

    /// 虚拟「现在」：加 60s 偏移，保证测试内任意 `t - ACTIVITY_WINDOW` 减法
    /// 不触碰 Instant 下界（进程启动时刻）。
    fn virtual_now() -> Instant {
        Instant::now() + secs(60)
    }

    #[test]
    fn m6_active_set_merges_by_priority() {
        // ① 活跃集内优先级合并：双 session 均在 10s 窗内，error vs working
        //    → error（正在发生的 error 本就该被看见）
        let mut m = SessionStateMachine::new();
        let t = virtual_now();
        m.apply_event("opencode", "a", Kind::Working, t);
        m.apply_event("claude-code", "b", Kind::Error, t - secs(2));
        let d = m.display(t);
        assert_eq!(d.kind, Kind::Error);
        assert_eq!(d.agent, "claude-code");
    }

    #[test]
    fn m6_same_priority_tie_picks_latest_last_event_at() {
        // ② 同 priority 平局取 last_event_at 最新者（双 agent 同 kind——防
        //    HashMap 迭代序任意决定胜者、芯片 agent 无因跳变，P2-2）
        let mut m = SessionStateMachine::new();
        let t = virtual_now();
        m.apply_event("opencode", "a", Kind::Working, t - secs(8));
        m.apply_event("claude-code", "b", Kind::Working, t - secs(3));
        let d = m.display(t);
        assert_eq!(d.kind, Kind::Working);
        assert_eq!(d.agent, "claude-code", "同 kind 双 agent：事件更新近者胜");
        // 插入序反转不改变胜者（HashMap 迭代序无关）
        let mut m2 = SessionStateMachine::new();
        m2.apply_event("claude-code", "b", Kind::Working, t - secs(3));
        m2.apply_event("opencode", "a", Kind::Working, t - secs(8));
        assert_eq!(m2.display(t).agent, "claude-code");
    }

    #[test]
    fn m6_stale_error_yields_to_active_working() {
        // ③ 掉窗让位（核心修复）：A error（10s+ 前事件后静默）+ B working
        //    （2s 前）→ B（v1 中 error 持续抢镜至回收）
        let mut m = SessionStateMachine::new();
        let t = virtual_now();
        m.apply_event("opencode", "a", Kind::Error, t - secs(12));
        m.apply_event("claude-code", "b", Kind::Working, t - secs(2));
        let d = m.display(t);
        assert_eq!(d.kind, Kind::Working);
        assert_eq!(d.agent, "claude-code");
    }

    #[test]
    fn m6_empty_window_falls_back_to_most_recent() {
        // ④ 窗口空 → 全量最近活跃（平局取 priority 高者）
        let mut m = SessionStateMachine::new();
        let t = virtual_now();
        // 全部掉窗：editing(4) 更旧、working(1) 更新 → fallback 选 working
        // （v1 全量优先级合并会选 editing——这正是 M6 修复点）
        m.apply_event("opencode", "a", Kind::Editing, t - secs(20));
        m.apply_event("claude-code", "b", Kind::Working, t - secs(15));
        let d = m.display(t);
        assert_eq!(d.kind, Kind::Working, "fallback 按 last_event_at，非优先级");
        assert_eq!(d.agent, "claude-code");
        // 平局（同 last_event_at）→ priority 高者（success(2) > working(1)）
        let mut m2 = SessionStateMachine::new();
        m2.apply_event("opencode", "a", Kind::Working, t - secs(25));
        m2.apply_event("claude-code", "b", Kind::Success, t - secs(25));
        let d2 = m2.display(t);
        assert_eq!(d2.kind, Kind::Success);
        assert_eq!(d2.agent, "claude-code");
    }

    #[test]
    fn m6_solo_error_survives_via_fallback_until_reclaim() {
        // ⑤ P1-1 钉子：solo error（无其他会话）经 fallback（最近活跃）仍选中，
        // 显示至 30s 回收——有意行为（失败应被看见，M4 R6 语义；与 v1 无回归
        // 无改善，非本里程碑问题域）
        let mut m = SessionStateMachine::new();
        let t0 = virtual_now();
        m.apply_event("opencode", "a", Kind::Error, t0);
        for q in [5u64, 15, 25, 29] {
            let d = m.display(t0 + secs(q));
            assert_eq!(d.kind, Kind::Error, "掉窗后 fallback 仍选中（{q}s 时刻）");
            assert_eq!(d.agent, "opencode");
        }
        // 30s 回收 → idle
        m.tick(t0 + secs(30), secs(30), secs(30));
        let d = m.display(t0 + secs(30));
        assert_eq!(d.kind, Kind::Idle, "回收后缺席 = idle");
        assert_eq!(d.agent, "");
    }

    #[test]
    fn m6_empty_sessions_display_idle_with_empty_agent() {
        // ⑥ sessions 空 → idle（agent 空，前端芯片降级不显示）
        let d = SessionStateMachine::new().display(virtual_now());
        assert_eq!(d.kind, Kind::Idle);
        assert_eq!(d.agent, "");
    }

    #[test]
    fn m6_cross_agents_participate_equally() {
        // ⑦ 跨 agent 同权：opencode / claude-code / task 伪 session 平等参与
        //    （优先级表与窗口对三者一视同仁）
        let mut m = SessionStateMachine::new();
        let t = virtual_now();
        m.apply_event("task", "task:7", Kind::Testing, t - secs(1));
        m.apply_event("opencode", "s1", Kind::Editing, t - secs(2));
        m.apply_event("claude-code", "u1", Kind::Working, t - secs(3));
        let d = m.display(t);
        assert_eq!(d.kind, Kind::Testing, "窗内按优先级合并（testing > editing > working）");
        assert_eq!(d.agent, "task");
        // task 伪 session 掉窗 + opencode 窗内 → opencode 接管
        let mut m2 = SessionStateMachine::new();
        m2.apply_event("task", "task:7", Kind::Testing, t - secs(30));
        m2.apply_event("opencode", "s1", Kind::Editing, t - secs(2));
        let d2 = m2.display(t);
        assert_eq!(d2.kind, Kind::Editing);
        assert_eq!(d2.agent, "opencode");
    }

    #[test]
    fn m6_task_heartbeat_fallback_stable_during_user_silence() {
        // ⑧ 伪 session 15s 心跳时序（心跳 15s > 窗口 10s 的系统性交互）：
        //    手头静默期（相邻两事件之间，含 >10s 长间隙）例程 working 连续
        //    显示不闪变（fallback 消除心跳节律闪烁）；手头事件到达即夺回；
        //    例程 working(1) 压不过窗内手头 editing/testing
        let mut m = SessionStateMachine::new();
        let t0 = virtual_now();
        // 手头会话 t0 一击后静默；例程 15s 心跳
        m.apply_event("opencode", "s1", Kind::Editing, t0);
        m.apply_event("task", "task:1", Kind::Working, t0 + secs(15));
        // t0+20s：例程心跳 5s 前仍在窗内 → working（active 集）
        assert_eq!(m.display(t0 + secs(20)).kind, Kind::Working);
        // t0+26s：例程心跳 11s 前掉窗、手头 26s 前掉窗 → 窗口空，fallback 选
        // 最近活跃 = 例程（t0+15）→ **仍是 working，显示不闪变**
        let d = m.display(t0 + secs(26));
        assert_eq!(d.kind, Kind::Working, "心跳间隙 fallback 连选例程，不闪变");
        assert_eq!(d.agent, "task");
        // 手头事件到达 → 即夺回（active 集内唯一）
        m.apply_event("opencode", "s1", Kind::Editing, t0 + secs(28));
        let d = m.display(t0 + secs(28));
        assert_eq!(d.kind, Kind::Editing);
        assert_eq!(d.agent, "opencode");
        // 下一拍例程心跳到达（双方均在窗内）→ 例程 working(1) 压不过 editing(4)
        m.apply_event("task", "task:1", Kind::Working, t0 + secs(30));
        let d = m.display(t0 + secs(30));
        assert_eq!(d.kind, Kind::Editing, "例程 working(1) 压不过窗内手头 editing");
        assert_eq!(d.agent, "opencode");
    }

    #[test]
    fn m6_waiting_permission_yields_when_out_of_window() {
        // ⑨ P2-5 钉子：waiting-permission >10s 未审批且手头会话活跃 → review
        //    姿态让位（接受 + 记录：终端弹窗本身持续可见、阻塞会话，不依赖
        //    宠物二次提醒；10s 已覆盖「刚发生」的最重要时段）
        let mut m = SessionStateMachine::new();
        let t = virtual_now();
        m.apply_event("claude-code", "u1", Kind::WaitingPermission, t - secs(12));
        m.apply_event("opencode", "s1", Kind::Working, t - secs(2));
        let d = m.display(t);
        assert_eq!(d.kind, Kind::Working, "掉窗让位（语义钉子）");
        assert_eq!(d.agent, "opencode");
        // 窗内（≤10s）时 waiting-permission 仍按优先级显示（6 > 1）
        let mut m2 = SessionStateMachine::new();
        m2.apply_event("claude-code", "u1", Kind::WaitingPermission, t - secs(8));
        m2.apply_event("opencode", "s1", Kind::Working, t - secs(2));
        let d2 = m2.display(t);
        assert_eq!(d2.kind, Kind::WaitingPermission);
        assert_eq!(d2.agent, "claude-code");
    }

    #[test]
    fn m6_window_boundary_is_inclusive_at_10s() {
        // 窗口边界：last_event_at >= now - 10s——恰 10s 前的事件仍在窗内
        //（对齐插件 reaction 桶 10s 冷却节奏：10s 心跳不会掉窗）
        let mut m = SessionStateMachine::new();
        let t = virtual_now();
        m.apply_event("opencode", "a", Kind::Error, t - ACTIVITY_WINDOW);
        m.apply_event("claude-code", "b", Kind::Working, t - secs(2));
        assert_eq!(m.display(t).kind, Kind::Error, "恰 10s 前 → 仍在窗内（闭区间）");
        // 越过边界（10s+50ms）→ 掉窗让位
        let mut m2 = SessionStateMachine::new();
        m2.apply_event("opencode", "a", Kind::Error, t - ACTIVITY_WINDOW - Duration::from_millis(50));
        m2.apply_event("claude-code", "b", Kind::Working, t - secs(2));
        assert_eq!(m2.display(t).kind, Kind::Working);
    }

    // ⑩ 既有 v1 display 断言修订 = 上方全部旧测试改注入时钟（同刻事件下行为
    //    等价——同刻事件必同在活跃集内，两层合并退化为集内优先级合并 = v1
    //    语义）；无事件时的掉窗让位依赖 lib.rs 1s 后台 notify 循环兜底
    //   （延迟 ≤1s，循环不可被优化掉——注释钉在 lib.rs 循环处）。
}
