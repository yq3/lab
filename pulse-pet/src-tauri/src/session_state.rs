//! 多 session 状态机 + 优先级合并（DESIGN §3.3，TC-EV-16/TC-EV-17/TC-EV-06）。
//!
//! - 每个 opencode 会话（`sessionId`）维护独立的 `SessionRecord`（最近一次归一化
//!   状态 + 该事件的时间戳）。
//! - 单只宠物显示所有 session 的「最高优先级」状态（clawd 式优先级合并）。
//! - 长时间无事件的 session 回收为 `idle`（30s，`/health` 不参与）；任一瞬态
//!   超时兜底：`N` 秒（默认 30s，可配）内无新事件 → 回退 `working`，再无事件 30s
//!   → 回退 `idle`（§3.1 ③ / TC-EV-06）。
//!
//! 本模块不依赖 Tauri，纯 `std`，便于 `cargo test` 直接覆盖。

use std::collections::HashMap;
use std::time::{Duration, Instant};

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
#[derive(Clone, Copy, Debug)]
pub struct SessionRecord {
    pub kind: Kind,
    /// 最近一次 `/state` 事件到达的时刻（也用于瞬态超时与 idle 回收的计时）。
    pub last_event_at: Instant,
}

/// 多 session 状态机（`HashMap<SessionId, SessionRecord>`）。
#[derive(Default)]
pub struct SessionStateMachine {
    sessions: HashMap<String, SessionRecord>,
}

impl SessionStateMachine {
    pub fn new() -> Self {
        Self::default()
    }

    /// 记录一条 `/state` 事件（覆盖该 session 的最近状态）。
    pub fn apply_event(&mut self, session_id: &str, kind: Kind, now: Instant) {
        self.sessions.insert(
            session_id.to_string(),
            SessionRecord {
                kind,
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

    /// 当前显示状态：所有 session 的优先级合并（无 session 时 idle）。
    pub fn display(&self) -> Kind {
        self.sessions
            .values()
            .map(|r| r.kind)
            .max_by_key(|k| k.priority())
            .unwrap_or(Kind::Idle)
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
        m.apply_event("a", Kind::Editing, t);
        m.apply_event("b", Kind::Error, t);
        assert_eq!(m.display(), Kind::Error); // B error 覆盖 A editing（TC-EV-16）
        m.apply_event("b", Kind::Working, t);
        assert_eq!(m.display(), Kind::Editing); // A editing 高于 B working
        m.apply_event("a", Kind::Idle, t);
        assert_eq!(m.display(), Kind::Working);
    }

    #[test]
    fn empty_machine_displays_idle() {
        assert_eq!(SessionStateMachine::new().display(), Kind::Idle);
    }

    #[test]
    fn idle_reclamation_after_30s_no_event() {
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("a", Kind::Working, t0);
        // 29s 无事件 → 仍 working
        m.tick(t0 + secs(29), secs(30), secs(30));
        assert_eq!(m.display(), Kind::Working);
        // 30s 无事件 → idle（TC-EV-17）
        m.tick(t0 + secs(30), secs(30), secs(30));
        assert_eq!(m.display(), Kind::Idle);
    }

    #[test]
    fn transient_falls_back_to_working_then_idle() {
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("a", Kind::Editing, t0);
        // 29s → 仍 editing（瞬态尚未超时）
        m.tick(t0 + secs(29), secs(30), secs(30));
        assert_eq!(m.display(), Kind::Editing);
        // 30s → 回退 working（TC-EV-06 第一步）
        m.tick(t0 + secs(30), secs(30), secs(30));
        assert_eq!(m.display(), Kind::Working);
        // working 再 29s → 仍 working
        m.tick(t0 + secs(59), secs(30), secs(30));
        assert_eq!(m.display(), Kind::Working);
        // working 再 30s（距回退 30s）→ idle（TC-EV-06 第二步）
        m.tick(t0 + secs(60), secs(30), secs(30));
        assert_eq!(m.display(), Kind::Idle);
    }

    #[test]
    fn transient_timeout_is_configurable() {
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("a", Kind::Thinking, t0);
        // 5s 超时兜底：5s 后 → working
        m.tick(t0 + secs(5), secs(5), secs(30));
        assert_eq!(m.display(), Kind::Working);
    }

    #[test]
    fn new_event_refreshes_session_timer() {
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("a", Kind::Editing, t0);
        // 20s 后又来一个新 editing 事件 → 计时重置，30s 后仍未超时
        m.apply_event("a", Kind::Editing, t0 + secs(20));
        m.tick(t0 + secs(40), secs(30), secs(30));
        assert_eq!(m.display(), Kind::Editing);
    }

    // ---- P3-⑥：回收即 remove（内存不随 session 数无界增长） ----

    #[test]
    fn reclaimed_sessions_are_removed_from_map() {
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("a", Kind::Working, t0);
        m.apply_event("b", Kind::Idle, t0); // idle 条目同样按超时回收
        m.apply_event("c", Kind::Success, t0); // token 汇报注入的 success 也会回收
        assert_eq!(m.len(), 3);
        m.tick(t0 + secs(30), secs(30), secs(30));
        assert_eq!(m.len(), 0, "非瞬态条目超时后应被 remove，而非常驻");
        assert_eq!(m.display(), Kind::Idle, "缺席 = idle，显示语义不变");
    }

    #[test]
    fn reclaimed_session_resumes_on_new_event() {
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("a", Kind::Working, t0);
        m.tick(t0 + secs(30), secs(30), secs(30)); // 回收
        assert_eq!(m.len(), 0);
        // 回收后同一 session 来新事件 → 正常重建（不影响后续状态）
        m.apply_event("a", Kind::Editing, t0 + secs(31));
        assert_eq!(m.display(), Kind::Editing);
        assert_eq!(m.len(), 1);
    }

    #[test]
    fn transient_two_step_reclaim_keeps_other_sessions() {
        let mut m = SessionStateMachine::new();
        let t0 = Instant::now();
        m.apply_event("a", Kind::Editing, t0);
        m.apply_event("b", Kind::Working, t0 + secs(5)); // b 晚 5s
        m.tick(t0 + secs(30), secs(30), secs(30));
        // a：瞬态→working（计时重置）；b：非瞬态但才 25s → 保留
        assert_eq!(m.len(), 2);
        m.tick(t0 + secs(60), secs(30), secs(30));
        // a：working 30s → remove；b：working 55s → remove
        assert_eq!(m.len(), 0);
    }
}
