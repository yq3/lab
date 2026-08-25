//! v2 M4：ActionExecutor——动作泛化（notify / exec）执行层（V2-DESIGN §4.4/§4.5）。
//!
//! - `ActionExecutor` trait：`validate(&Value)`（保存前校验）+ `run(&Value, RunCtx)`
//!   （真实执行 → `ActionOutcome`）；dyn 兼容（run 返回 boxed future，无新依赖）。
//! - `NotifyExecutor` 薄壳：触发即 ok——气泡/烟花编排走既有 `reminder://trigger`
//!   链路（调度器分派 notify 不经本模块的 run）。
//! - `ExecExecutor`：`sh -c`（Unix）/ `powershell -NoProfile -Command`（Windows，
//!   分支同构、实机挂观察项 TC-M4-18）真实执行；cwd 生效；**进程组 kill**
//!   （Unix setsid + `kill(-pgid)`；Windows `taskkill /T /F`）；stdout+stderr
//!   合并攒 buffer 超 2KB 保尾部（截尾标记 `…(已截断)`）；超时杀进程组 →
//!   Failed「超时（N 分钟）被终止」。
//! - 分派注册表 `executor_for(action_type)`；运行句柄登记表 `RunningTasks`
//!   （`HashMap<log_id, pid>`，供 `RunEvent::Exit` 退出处置——N7：完成回写先
//!   从登记表移除，Exit 只处置仍在登记表的句柄，防竞写）。
//! - 通用层伪 session（P2-7）：`task_apply`——agent=常量 `"task"`、session key
//!   `task:<log_id>`，Rust 内部直连 `apply_event`（不经 HTTP 白名单）；每次
//!   apply 后必调 `DisplayNotifier::notify`；**不更新 AgentActivity、不触发
//!   idle_hook**（伪 session 非真实 agent 事件）。
//! - 执行编排：`dispatch_exec`（并发上限 2 + `pending_execs` 等待队列）→
//!   insert action_logs(running) → spawn 独立任务（15s 心跳保鲜防 30s idle
//!   回收，P2-9）→ 完成回写 + 终态 apply + 结果气泡
//!   `pulsepet://task-result`（P1-3 独立事件，不复用 M2 冻结为 info 级的
//!   `pulsepet://bubble`）→ channel 通知调度器出队。
//!
//! summary 一律存 i18n 模板键（P3-3，展示按当前语言渲染）：`task.summary.*`；
//! 参数化键以 `key:arg` 形式存参（timeout 的分钟数）。

use std::collections::HashMap;
use std::future::Future;
use std::pin::Pin;
use std::sync::{Arc, Mutex};

use rusqlite::{params, Connection};
use serde_json::Value;

use crate::plog;
use crate::reminder_scheduler::{
    finish_action_log_with, insert_action_log_running, ms_to_rfc3339, now_rfc3339, RemindersState,
    ReminderRule,
};
use crate::session_state::{Kind, SessionStateMachine};

/// exec 并发上限（§4.5：并发满 2 进等待队列）。
pub const MAX_CONCURRENT_EXECS: usize = 2;
/// 执行期间伪 session 心跳周期（P2-9：30s idle 回收的 1/2，裕量 15s）。
pub const TASK_HEARTBEAT_MS: u64 = 15_000;
/// 心跳防的 idle 回收窗（session_state 后台 tick 的 30s，测试注入用）。
#[cfg_attr(not(test), allow(dead_code))]
pub const IDLE_RECYCLE_MS: u64 = 30_000;
/// 伪 session 的 agent 常量（M2 芯片对 agent=="task" 显示 panel.agentTask）。
pub const TASK_AGENT: &str = "task";
/// 结果气泡独立事件名（P1-3；桥层按 M2 critical 入队，无 reminder 载荷）。
pub const TASK_RESULT_EVENT: &str = "pulsepet://task-result";

// ---- summary 模板键（存库形态；P3-3 展示按当前语言渲染） ----

pub const SUMMARY_OK: &str = "task.summary.ok";
pub const SUMMARY_FAILED: &str = "task.summary.failed";
pub const SUMMARY_TIMEOUT: &str = "task.summary.timeout";
pub const SUMMARY_MISSED: &str = "task.summary.missed";
pub const SUMMARY_PAUSED: &str = "task.summary.paused";
pub const SUMMARY_INTERRUPTED: &str = "task.summary.interrupted";
pub const SUMMARY_STALE: &str = "task.summary.stale";

/// 超时键的存参形态：`task.summary.timeout:<minutes>`。
pub fn summary_timeout_key(minutes: u64) -> String {
    format!("{SUMMARY_TIMEOUT}:{minutes}")
}

// ---------------------------------------------------------------------------
// ActionOutcome / ActionExecutor
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ActionStatus {
    Ok,
    Failed,
    /// 跳过（skipped 记账主要走 action_logs 直写；枚举值保持设计完整性，
    /// 前端 task-result status 字段与 ActionOutcome 语义预留）。
    #[allow(dead_code)]
    Skipped,
}

impl ActionStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            ActionStatus::Ok => "ok",
            ActionStatus::Failed => "failed",
            ActionStatus::Skipped => "skipped",
        }
    }
}

/// 执行结果（§4.4）：summary 存 i18n 模板键；output_tail ≤2KB；exit_code 退出码。
#[derive(Debug, Clone)]
pub struct ActionOutcome {
    pub status: ActionStatus,
    pub summary: String,
    pub output_tail: Option<String>,
    pub exit_code: Option<i32>,
}

/// run 的执行上下文：action_log_id（完成回写）+ 运行句柄登记表引用。
#[derive(Clone)]
pub struct RunCtx {
    pub log_id: i64,
    /// 运行句柄登记表（与 lib.rs managed state 同一实例）。
    pub registry: Arc<Mutex<RunningTasks>>,
}

pub type RunFuture<'a> = Pin<Box<dyn Future<Output = ActionOutcome> + Send + 'a>>;

/// 动作执行器（§4.4）。dyn 兼容：run 手动 boxing（无 async_trait 依赖）。
pub trait ActionExecutor: Send + Sync {
    /// 保存前校验（与前端同规则预检的权威版本）。
    fn validate(&self, params: &Value) -> Result<(), String>;
    /// 真实执行。ExecExecutor 在内部完成登记表注册/注销（N7：返回前先注销）。
    fn run<'a>(&'a self, params: &'a Value, ctx: RunCtx) -> RunFuture<'a>;
}

// ---------------------------------------------------------------------------
// NotifyExecutor（薄壳：触发即 ok；编排走既有 reminder://trigger）
// ---------------------------------------------------------------------------

pub struct NotifyExecutor;

impl ActionExecutor for NotifyExecutor {
    fn validate(&self, _params: &Value) -> Result<(), String> {
        Ok(())
    }

    fn run<'a>(&'a self, _params: &'a Value, _ctx: RunCtx) -> RunFuture<'a> {
        Box::pin(async {
            ActionOutcome {
                status: ActionStatus::Ok,
                summary: SUMMARY_OK.to_string(),
                output_tail: None,
                exit_code: None,
            }
        })
    }
}

// ---------------------------------------------------------------------------
// ExecExecutor（真实命令执行）
// ---------------------------------------------------------------------------

pub struct ExecExecutor;

/// exec 的 action_params JSON 文本 → 结构化参数（解析失败 → Err）。
pub fn parse_exec_params(text: &str) -> Result<Value, String> {
    serde_json::from_str::<Value>(text)
        .map_err(|e| format!("action_params JSON 解析失败：{e}"))
}

impl ExecExecutor {
    /// timeout_minutes 缺省 10（§4.0 裁定：1-120 分钟可配置）。
    pub fn timeout_minutes(params: &Value) -> u64 {
        params
            .get("timeout_minutes")
            .and_then(Value::as_u64)
            .unwrap_or(10)
            .clamp(1, 120)
    }

    /// validate 规则（TC-M4-07）：command 非空 ≤2000；cwd 可选（存在则须为
    /// 目录）；timeout_minutes 1-120（缺省 10）；opencode_auto 须 bool（仅
    /// 校验不改命令——模板拼接在 UI 完成）。特殊字符给警告不阻止（R3）。
    pub fn validate_params(params: &Value) -> Result<(), String> {
        let obj = params
            .as_object()
            .ok_or_else(|| "action_params 应为 JSON 对象".to_string())?;
        let command = obj
            .get("command")
            .and_then(Value::as_str)
            .ok_or_else(|| "command 不能为空".to_string())?;
        if command.trim().is_empty() {
            return Err("command 不能为空".to_string());
        }
        if command.chars().count() > 2000 {
            return Err("command 超长（≤2000 字符）".to_string());
        }
        if let Some(cwd) = obj.get("cwd").and_then(Value::as_str) {
            if !cwd.trim().is_empty() {
                let p = std::path::Path::new(cwd);
                if p.exists() && !p.is_dir() {
                    return Err(format!("cwd 不是目录：{cwd}"));
                }
            }
        }
        match obj.get("timeout_minutes") {
            None | Some(Value::Null) => {}
            Some(v) => match v.as_u64() {
                Some(m) if (1..=120).contains(&m) => {}
                _ => return Err("timeout_minutes 非法（应为 1-120 分钟，缺省 10）".to_string()),
            },
        }
        if let Some(a) = obj.get("opencode_auto") {
            if !a.is_boolean() {
                return Err("opencode_auto 应为布尔值".to_string());
            }
        }
        // R3：特殊字符（非 ASCII 可打印 + 空白之外的字符）警告不阻止——
        // Windows PowerShell 参数转义风险（TC-M4-18 观察项）。
        let suspicious = command
            .chars()
            .any(|c| !(c.is_ascii_graphic() || c == ' '));
        if suspicious {
            plog!(
                "[pulsepet] exec command contains special characters (windows escaping risk, R3): {:?}",
                &command[..command.len().min(80)]
            );
        }
        Ok(())
    }
}

impl ActionExecutor for ExecExecutor {
    fn validate(&self, params: &Value) -> Result<(), String> {
        Self::validate_params(params)
    }

    fn run<'a>(&'a self, params: &'a Value, ctx: RunCtx) -> RunFuture<'a> {
        let timeout = std::time::Duration::from_secs(Self::timeout_minutes(params) * 60);
        Box::pin(exec_run_with_timeout(params, ctx, timeout))
    }
}

/// exec 执行体（`run` 的内部实现；timeout 参数化供测试注入短超时——对外
/// 契约仍是 timeout_minutes 1-120 分钟）。
async fn exec_run_with_timeout(
    params: &Value,
    ctx: RunCtx,
    timeout: std::time::Duration,
) -> ActionOutcome {
    let timeout_min = timeout.as_secs() / 60;
    let command = params.get("command").and_then(Value::as_str).unwrap_or("");
    if command.trim().is_empty() {
        return ActionOutcome {
            status: ActionStatus::Failed,
            summary: SUMMARY_FAILED.to_string(),
            output_tail: None,
            exit_code: None,
        };
    }
    let cwd = params
        .get("cwd")
        .and_then(Value::as_str)
        .filter(|s| !s.trim().is_empty());

    let mut cmd = build_shell_command(command);
    if let Some(dir) = cwd {
        cmd.current_dir(dir);
    }
    cmd.stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .kill_on_drop(true);
    // Unix：进程组隔离（setsid）——超时/退出处置可 kill(-pgid) 杀整组，
    // 防 `sh -c` 只杀壳留孤儿子进程（§4.4）。
    #[cfg(unix)]
    unsafe {
        cmd.pre_exec(|| {
            if libc::setsid() == -1 {
                // setsid 失败不阻断（仍可 kill 直接 pid）
            }
            Ok(())
        });
    }

    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            return ActionOutcome {
                status: ActionStatus::Failed,
                summary: SUMMARY_FAILED.to_string(),
                output_tail: Some(format!("spawn failed: {e}")),
                exit_code: None,
            };
        }
    };
    // tokio Child::id() 在子进程已退出后为 None——None 时无进程可杀，
    // 不登记（防 pid=0 误杀调用方自身进程组）
    let pid = child.id();
    if let Some(pid) = pid {
        let mut reg = ctx.registry.lock().unwrap_or_else(|p| p.into_inner());
        reg.tasks.insert(ctx.log_id, RunningProc { pid });
    }

    // 输出捕获：stdout+stderr 合并攒尾部 buffer（≤2KB，超限保尾部）。
    let tail = Arc::new(Mutex::new(TailBuf::default()));
    let mut readers = Vec::new();
    if let Some(stream) = child.stdout.take() {
        let tail = tail.clone();
        readers.push(tauri::async_runtime::spawn(read_into_tail(stream, tail)));
    }
    if let Some(stream) = child.stderr.take() {
        let tail = tail.clone();
        readers.push(tauri::async_runtime::spawn(read_into_tail(stream, tail)));
    }

    let status = tokio::select! {
        st = child.wait() => Some(st),
        _ = tokio::time::sleep(timeout) => None,
    };
    if status.is_none() {
        // 超时：杀进程组 → Failed「超时（N 分钟）被终止」，tail 保留已捕获部分
        if let Some(pid) = pid {
            kill_process_tree(pid);
        }
        let _ = child.wait().await;
        plog!("[pulsepet] exec log#{} timed out ({} min), process group killed", ctx.log_id, timeout_min);
    }
    // 子进程退出后管道关闭；给读者任务一个短窗口收尾（防孤儿子进程
    // 持管道导致读者不 EOF 而永久挂起）。
    for h in readers {
        let _ = tokio::time::timeout(
            std::time::Duration::from_millis(300),
            h,
        )
        .await;
    }

    // N7：完成路径先从登记表移除，再回写——Exit 只处置仍在登记表的句柄。
    {
        let mut reg = ctx.registry.lock().unwrap_or_else(|p| p.into_inner());
        reg.tasks.remove(&ctx.log_id);
    }
    let output_tail = Arc::try_unwrap(tail)
        .ok()
        .map(|t| t.into_inner().unwrap_or_else(|p| p.into_inner()).finish())
        .flatten()
        .filter(|s| !s.is_empty());

    match status {
        Some(Ok(st)) if st.success() => ActionOutcome {
            status: ActionStatus::Ok,
            summary: SUMMARY_OK.to_string(),
            output_tail,
            exit_code: st.code(),
        },
        Some(Ok(st)) => ActionOutcome {
            status: ActionStatus::Failed,
            summary: SUMMARY_FAILED.to_string(),
            output_tail,
            exit_code: st.code(),
        },
        Some(Err(e)) => ActionOutcome {
            status: ActionStatus::Failed,
            summary: SUMMARY_FAILED.to_string(),
            output_tail: output_tail.or_else(|| Some(format!("wait failed: {e}"))),
            exit_code: None,
        },
        None => ActionOutcome {
            status: ActionStatus::Failed,
            summary: summary_timeout_key(timeout_min),
            output_tail,
            exit_code: None,
        },
    }
}

/// 平台 shell 构造（§4.4）：Unix `sh -c` / Windows `powershell -NoProfile -Command`。
fn build_shell_command(command: &str) -> tokio::process::Command {
    let mut cmd = tokio::process::Command::new(shell_program());
    #[cfg(unix)]
    {
        cmd.arg("-c").arg(command);
    }
    #[cfg(windows)]
    {
        cmd.arg("-NoProfile").arg("-Command").arg(command);
    }
    #[cfg(not(any(unix, windows)))]
    {
        let _ = command;
        compile_error!("unsupported platform for exec executor");
    }
    cmd
}

/// 读一截输出流攒进尾部 buffer（stdout/stderr 共用；EOF/错误即止）。
async fn read_into_tail<S: tokio::io::AsyncRead + Unpin>(
    mut stream: S,
    tail: Arc<Mutex<TailBuf>>,
) {
    use tokio::io::AsyncReadExt;
    let mut chunk = [0u8; 4096];
    loop {
        match stream.read(&mut chunk).await {
            Ok(0) | Err(_) => break,
            Ok(n) => tail
                .lock()
                .unwrap_or_else(|p| p.into_inner())
                .push(&chunk[..n]),
        }
    }
}

fn shell_program() -> &'static str {
    #[cfg(unix)]
    {
        "sh"
    }
    #[cfg(windows)]
    {
        "powershell"
    }
}

/// 杀进程组（Unix `kill(-pgid, SIGKILL)`——pid 即 pgid（setsid）；Windows
/// `taskkill /T /F /PID` 杀进程树）。
pub fn kill_process_tree(pid: u32) {
    #[cfg(unix)]
    {
        let pgid = pid as i32;
        let r = unsafe { libc::kill(-pgid, libc::SIGKILL) };
        if r != 0 {
            // 组杀失败（组已消亡等）兜底杀直接 pid
            let _ = unsafe { libc::kill(pgid, libc::SIGKILL) };
        }
    }
    #[cfg(windows)]
    {
        let _ = std::process::Command::new("taskkill")
            .args(["/T", "/F", "/PID", &pid.to_string()])
            .status();
    }
}

// ---------------------------------------------------------------------------
// 输出尾部 buffer（≤2KB 保尾部 + 截尾标记）
// ---------------------------------------------------------------------------

/// stdout+stderr 合并攒 buffer，超 2KB 只保留尾部（内存不随输出量膨胀）。
#[derive(Default)]
pub struct TailBuf {
    buf: Vec<u8>,
    truncated: bool,
}

impl TailBuf {
    pub const MAX: usize = 2048;
    pub const TRUNC_MARK: &str = "…(已截断)";

    pub fn push(&mut self, data: &[u8]) {
        if data.len() >= Self::MAX {
            // 单块超限：直接以本块尾部覆盖（前段丢弃 → 置截断标记）
            let keep = &data[data.len() - Self::MAX..];
            self.buf.clear();
            self.buf.extend_from_slice(keep);
            self.truncated = true;
        } else {
            self.buf.extend_from_slice(data);
            if self.buf.len() > Self::MAX {
                let excess = self.buf.len() - Self::MAX;
                self.buf.drain(..excess);
                self.truncated = true; // 累计溢出丢弃了前段
            }
        }
    }

    /// 收尾：无内容 → None；截断 → 前缀标记 `…(已截断)`。
    pub fn finish(self) -> Option<String> {
        let tail = String::from_utf8_lossy(&self.buf).trim().to_string();
        if tail.is_empty() {
            return None;
        }
        Some(if self.truncated {
            format!("{}{}", Self::TRUNC_MARK, tail)
        } else {
            tail
        })
    }
}

// ---------------------------------------------------------------------------
// 分派注册表 + 运行句柄登记表
// ---------------------------------------------------------------------------

static NOTIFY_EXECUTOR: NotifyExecutor = NotifyExecutor;
static EXEC_EXECUTOR: ExecExecutor = ExecExecutor;

/// action_type → 执行器（未知类型 → None，调用方按 notify 兜底不执行命令）。
pub fn executor_for(action_type: &str) -> Option<&'static dyn ActionExecutor> {
    match action_type {
        "notify" => Some(&NOTIFY_EXECUTOR),
        "exec" => Some(&EXEC_EXECUTOR),
        _ => None,
    }
}

/// 运行任务句柄登记表（`HashMap<log_id, pid>`；managed state）。
#[derive(Debug, Default)]
pub struct RunningTasks {
    pub tasks: HashMap<i64, RunningProc>,
}

#[derive(Debug, Clone, Copy)]
pub struct RunningProc {
    pub pid: u32,
}

impl RunningTasks {
    #[cfg_attr(not(test), allow(dead_code))]
    pub fn len(&self) -> usize {
        self.tasks.len()
    }

    #[cfg_attr(not(test), allow(dead_code))]
    pub fn is_empty(&self) -> bool {
        self.tasks.is_empty()
    }
}

// ---------------------------------------------------------------------------
// 通用层伪 session（P2-7）
// ---------------------------------------------------------------------------

/// 伪 session key：`task:<log_id>`（复合 key 首段 agent = 常量 "task"，
/// 与 HTTP 白名单 opencode|claude-code 互不冲突）。
pub fn task_session_key(log_id: i64) -> String {
    format!("{TASK_AGENT}:{log_id}")
}

/// 伪 session 注入：apply_event（agent="task"）+ DisplayNotifier::notify 成对
/// （对齐 HTTP 路径行为，否则宠物动画不变）；不更新 AgentActivity、不触发
/// idle_hook（伪 session 非真实 agent 事件）。泛型 Runtime：mock runtime 可直调。
pub fn task_apply<R: tauri::Runtime>(app: &tauri::AppHandle<R>, log_id: i64, kind: Kind) {
    use tauri::Manager;
    let Some(state) = app.try_state::<Arc<Mutex<SessionStateMachine>>>() else {
        return;
    };
    let key = task_session_key(log_id);
    {
        let mut st = state.lock().unwrap_or_else(|p| p.into_inner());
        st.apply_event(TASK_AGENT, &key, kind, std::time::Instant::now());
    }
    if let Some(notifier) = app.try_state::<Arc<crate::http_server::DisplayNotifier>>() {
        notifier.notify(&state);
    }
}

// ---------------------------------------------------------------------------
// 启动清理 + 退出处置（R5 / P1-2）
// ---------------------------------------------------------------------------

/// 启动时幂等清理崩溃残留的 running 态 action_logs（R5：正常退出走
/// RunEvent::Exit；强杀路径无 Exit → 残留 running 行在此结案为 failed）。
pub fn cleanup_running_logs(conn: &Connection) -> usize {
    conn.execute(
        "UPDATE action_logs SET status = 'failed', summary = ?1, finished_at = ?2 \
         WHERE status = 'running'",
        params![SUMMARY_STALE, now_rfc3339()],
    )
    .unwrap_or(0)
}

/// `RunEvent::Exit` 退出处置（P1-2）：遍历登记表句柄杀进程组 + action_logs
/// 补写 failed（「App 退出中断」）。N7：只处置登记表内的句柄（完成路径已
/// 先行移除自身，不竞写）。同步执行（退出路径 async runtime 不可依赖）。
pub fn abort_all_on_exit<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    use tauri::Manager;
    let Some(registry) = app.try_state::<Arc<Mutex<RunningTasks>>>() else {
        return;
    };
    let entries: Vec<(i64, u32)> = {
        let mut reg = registry.lock().unwrap_or_else(|p| p.into_inner());
        reg.tasks.drain().map(|(k, v)| (k, v.pid)).collect()
    };
    if entries.is_empty() {
        return;
    }
    plog!(
        "[pulsepet] exit: killing {} running task process group(s)",
        entries.len()
    );
    for (_, pid) in &entries {
        kill_process_tree(*pid);
    }
    if let Some(db) = app.try_state::<Mutex<Connection>>() {
        if let Ok(conn) = db.lock() {
            let now = now_rfc3339();
            for (log_id, _) in &entries {
                let _ = conn.execute(
                    "UPDATE action_logs SET status = 'failed', summary = ?2, finished_at = ?3 \
                     WHERE id = ?1 AND status = 'running'",
                    params![log_id, SUMMARY_INTERRUPTED, now],
                );
            }
        }
    }
}

// ---------------------------------------------------------------------------
// 执行编排（§4.5 执行链）
// ---------------------------------------------------------------------------

/// 到期分派 exec（tick / 试一试共用）：并发满 2 → 进 `pending_execs` 等待队列
/// （不写 running 行；空位出现由完成回调经 channel 通知出队）。
pub fn dispatch_exec<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    sched: &Arc<Mutex<RemindersState>>,
    rule: &ReminderRule,
    scheduled_at_ms: i64,
) {
    use tauri::Manager;
    let registry = app
        .state::<Arc<Mutex<RunningTasks>>>()
        .inner()
        .clone();
    let running = registry
        .lock()
        .map(|r| r.tasks.len())
        .unwrap_or(0);
    if running >= MAX_CONCURRENT_EXECS {
        if let Ok(mut st) = sched.lock() {
            st.pending_execs.push_back(PendingExec {
                rule: rule.clone(),
                scheduled_at_ms,
            });
            plog!(
                "[pulsepet] exec queue full ({}), task #{} pending (queue {})",
                running,
                rule.id,
                st.pending_execs.len()
            );
        }
        return;
    }
    start_exec_run(app, rule.clone(), scheduled_at_ms);
}

/// 完成回调出队：空位可能多个，循环出队到满/空（channel 每次完成通知一次）。
pub fn drain_pending_execs<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    sched: &Arc<Mutex<RemindersState>>,
) {
    use tauri::Manager;
    let registry = app
        .state::<Arc<Mutex<RunningTasks>>>()
        .inner()
        .clone();
    loop {
        let running = registry.lock().map(|r| r.tasks.len()).unwrap_or(0);
        if running >= MAX_CONCURRENT_EXECS {
            break;
        }
        let next = sched
            .lock()
            .ok()
            .and_then(|mut st| st.pending_execs.pop_front());
        let Some(p) = next else { break };
        plog!(
            "[pulsepet] exec dequeued: task #{} (scheduled {:?})",
            p.rule.id,
            ms_to_rfc3339(p.scheduled_at_ms)
        );
        start_exec_run(app, p.rule, p.scheduled_at_ms);
    }
}

/// 等待队列条目（RemindersState 持有；排队中无进程无 running 行——
/// App 退出/崩溃时自然消失无残留）。
#[derive(Debug, Clone)]
pub struct PendingExec {
    pub rule: ReminderRule,
    pub scheduled_at_ms: i64,
}

/// 真正启动一次 exec：insert running 日志 → 伪 session Working → spawn 执行。
fn start_exec_run<R: tauri::Runtime>(
    app: &tauri::AppHandle<R>,
    rule: ReminderRule,
    scheduled_at_ms: i64,
) {
    use tauri::Manager;
    let started = now_rfc3339();
    let log_id = {
        let db = app.state::<Mutex<Connection>>();
        let Ok(conn) = db.lock() else { return };
        let sched_ts = ms_to_rfc3339(scheduled_at_ms).unwrap_or_else(|| started.clone());
        match insert_action_log_running(&conn, rule.id, &rule.action_type, &started, &sched_ts) {
            Ok(id) => id,
            Err(e) => {
                plog!("[pulsepet] exec insert running log failed: {e}");
                return;
            }
        }
    };
    // last_triggered 持久化（推进锚点；与 notify 触发同口径，reload 语义一致）
    {
        let db = app.state::<Mutex<Connection>>();
        let guard = db.lock();
        if let Ok(conn) = guard {
            let _ = crate::reminder_scheduler::mark_triggered(&conn, rule.id, &started);
        }
    }
    task_apply(app, log_id, Kind::Working);
    plog!(
        "[pulsepet] exec started: task #{} log#{} scheduled {:?}",
        rule.id,
        log_id,
        ms_to_rfc3339(scheduled_at_ms)
    );
    let registry = app
        .state::<Arc<Mutex<RunningTasks>>>()
        .inner()
        .clone();
    tauri::async_runtime::spawn(run_task(app.clone(), rule, log_id, registry));
}

/// 单次执行全链路：执行（15s 心跳保鲜）→ 回写 action_logs → 终态 apply →
/// 结果气泡（task-result 独立事件）→ 通知调度器出队。
async fn run_task<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    rule: ReminderRule,
    log_id: i64,
    registry: Arc<Mutex<RunningTasks>>,
) {
    let params: Value = rule
        .action_params
        .as_deref()
        .and_then(|s| serde_json::from_str(s).ok())
        .unwrap_or_else(|| serde_json::json!({}));
    let executor = executor_for(&rule.action_type).unwrap_or(&NOTIFY_EXECUTOR);
    let ctx = RunCtx {
        log_id,
        registry: registry.clone(),
    };

    // 心跳（P2-9）：执行期间每 15s 重 apply Working + notify，防 30s idle 回收。
    let mut hb = tokio::time::interval(std::time::Duration::from_millis(TASK_HEARTBEAT_MS));
    hb.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    hb.tick().await; // interval 首个 tick 立即到期：跳过（启动时刚 apply 过）

    let run_fut = executor.run(&params, ctx);
    tokio::pin!(run_fut);
    let outcome = loop {
        tokio::select! {
            o = &mut run_fut => break o,
            _ = hb.tick() => task_apply(&app, log_id, Kind::Working),
        }
    };

    // 回写终态（executor 已先行从登记表移除自身，N7）
    {
        use tauri::Manager;
        if let Some(db) = app.try_state::<Mutex<Connection>>() {
            if let Ok(conn) = db.lock() {
                if let Err(e) = finish_action_log_with(
                    &conn,
                    log_id,
                    outcome.status.as_str(),
                    &outcome.summary,
                    outcome.output_tail.as_deref(),
                    outcome.exit_code,
                    &now_rfc3339(),
                ) {
                    plog!("[pulsepet] exec finish log#{log_id} failed: {e}");
                }
            }
        }
    }
    // 终态 apply（exit 0 → Success；非 0/超时 → Error，30s 自然回收）
    let kind = match outcome.status {
        ActionStatus::Ok => Kind::Success,
        ActionStatus::Failed | ActionStatus::Skipped => Kind::Error,
    };
    task_apply(&app, log_id, kind);

    // 结果气泡（P1-3）：text = 任务名 + summary（lib 层拼接、按当前语言渲染）
    {
        use tauri::Emitter;
        let rendered = crate::i18n::current().render_task_summary(&outcome.summary, outcome.exit_code);
        let text = crate::i18n::current().task_result_text(&rule.label, &rendered);
        let _ = app.emit_to(
            "pet",
            TASK_RESULT_EVENT,
            serde_json::json!({
                "text": text,
                "logId": log_id,
                "status": outcome.status.as_str(),
            }),
        );
    }
    plog!(
        "[pulsepet] exec finished: task #{} log#{} status={} exit={:?}",
        rule.id,
        log_id,
        outcome.status.as_str(),
        outcome.exit_code
    );
    notify_slot_free(&app);
}

/// 完成回调 → 调度器 select 分支出队（try_send：通道满即丢——下一 tick 兜底）。
fn notify_slot_free<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    use tauri::Manager;
    if let Some(sched) = app.try_state::<Arc<Mutex<RemindersState>>>() {
        let tx = sched
            .lock()
            .ok()
            .and_then(|st| st.slot_free_tx.clone());
        if let Some(tx) = tx {
            let _ = tx.try_send(());
        }
    }
}

// ---------------------------------------------------------------------------
// 测试
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn ctx() -> (Arc<Mutex<RunningTasks>>, RunCtx) {
        let reg = Arc::new(Mutex::new(RunningTasks::default()));
        (
            reg.clone(),
            RunCtx {
                log_id: 1,
                registry: reg,
            },
        )
    }

    // ---- validate（TC-M4-07） ----

    #[test]
    fn exec_validate_command_rules() {
        let ok = |cmd: &str| serde_json::json!({ "command": cmd });
        assert!(ExecExecutor::validate_params(&ok("echo hi")).is_ok());
        // 空 / 空白 / 缺失 / 超长
        assert!(ExecExecutor::validate_params(&ok("   ")).is_err());
        assert!(ExecExecutor::validate_params(&serde_json::json!({})).is_err());
        assert!(ExecExecutor::validate_params(&serde_json::json!({ "command": "x".repeat(2001) })).is_err());
        assert!(ExecExecutor::validate_params(&ok(&"x".repeat(2000))).is_ok());
        // 非 JSON 对象
        assert!(ExecExecutor::validate_params(&serde_json::json!("echo")).is_err());
        assert!(ExecExecutor::validate_params(&serde_json::json!([1])).is_err());
    }

    #[test]
    fn exec_validate_cwd_timeout_auto() {
        let cwd = std::env::temp_dir().to_string_lossy().to_string();
        assert!(ExecExecutor::validate_params(&serde_json::json!({ "command": "ls", "cwd": cwd })).is_ok());
        // 存在但非目录 → 拒绝；不存在 → 放行（spawn 时失败落 failed 日志）
        let this_file = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("Cargo.toml");
        assert!(ExecExecutor::validate_params(&serde_json::json!({
            "command": "ls", "cwd": this_file.to_string_lossy()
        }))
        .is_err());
        assert!(ExecExecutor::validate_params(&serde_json::json!({
            "command": "ls", "cwd": "/definitely/not/exists/xyz"
        }))
        .is_ok());
        // timeout 1-120 缺省 10
        for good in [1u64, 10, 120] {
            assert!(ExecExecutor::validate_params(&serde_json::json!({
                "command": "ls", "timeout_minutes": good
            }))
            .is_ok());
        }
        for bad in [0u64, 121, 999] {
            assert!(ExecExecutor::validate_params(&serde_json::json!({
                "command": "ls", "timeout_minutes": bad
            }))
            .is_err());
        }
        assert!(ExecExecutor::validate_params(&serde_json::json!({
            "command": "ls", "timeout_minutes": "10"
        }))
        .is_err());
        // opencode_auto 仅 bool
        assert!(ExecExecutor::validate_params(&serde_json::json!({
            "command": "ls", "opencode_auto": true
        }))
        .is_ok());
        assert!(ExecExecutor::validate_params(&serde_json::json!({
            "command": "ls", "opencode_auto": "yes"
        }))
        .is_err());
        assert_eq!(
            ExecExecutor::timeout_minutes(&serde_json::json!({ "command": "ls" })),
            10,
            "缺省 10"
        );
    }

    #[test]
    fn parse_exec_params_rejects_bad_json() {
        assert!(parse_exec_params("{not json").is_err());
        assert!(parse_exec_params(r#"{"command":"ls"}"#).is_ok());
    }

    // ---- registry / executor 分派 ----

    #[test]
    fn executor_for_dispatches_by_action_type() {
        assert!(executor_for("notify").is_some());
        assert!(executor_for("exec").is_some());
        assert!(executor_for("webhook").is_none());
    }

    // ---- TailBuf（TC-M4-06-4） ----

    #[test]
    fn tail_buf_keeps_last_2kb_with_mark() {
        let mut t = TailBuf::default();
        t.push(&b"hello".to_vec());
        assert_eq!(t.finish().as_deref(), Some("hello"));
        // 洪水：两次 2KB → 只有最后 2KB + 截断标记
        let mut t = TailBuf::default();
        t.push(&vec![b'a'; 3000]);
        t.push(&vec![b'b'; 100]);
        let out = t.finish().unwrap();
        assert!(out.starts_with(TailBuf::TRUNC_MARK), "截尾标记：{out}");
        assert_eq!(out.len(), TailBuf::TRUNC_MARK.len() + 2048);
        assert!(out.ends_with(&"b".repeat(100)));
        // 累计超限（多次小块）同样截断
        let mut t = TailBuf::default();
        for _ in 0..5 {
            t.push(&vec![b'x'; 500]);
        }
        let out = t.finish().unwrap();
        assert!(out.starts_with(TailBuf::TRUNC_MARK));
        assert_eq!(out.len(), TailBuf::TRUNC_MARK.len() + 2048);
        // 空输出 → None
        assert!(TailBuf::default().finish().is_none());
    }

    // ---- run（真实进程；Unix 实测，Windows 分支同构挂观察项） ----

    fn block_on<F: Future>(fut: F) -> F::Output {
        tauri::async_runtime::block_on(fut)
    }

    #[test]
    fn exec_run_echo_ok_and_exit_code() {
        let exec = ExecExecutor;
        let (_reg, c1) = ctx();
        let out = block_on(exec.run(
            &serde_json::json!({ "command": "echo ok" }),
            c1,
        ));
        assert_eq!(out.status, ActionStatus::Ok);
        assert_eq!(out.summary, SUMMARY_OK);
        assert_eq!(out.exit_code, Some(0));
        assert!(out.output_tail.as_deref().unwrap_or("").contains("ok"));

        let (_reg, c2) = ctx();
        let out = block_on(exec.run(
            &serde_json::json!({ "command": "echo bad >&2; exit 3" }),
            c2,
        ));
        assert_eq!(out.status, ActionStatus::Failed);
        assert_eq!(out.summary, SUMMARY_FAILED);
        assert_eq!(out.exit_code, Some(3));
        assert!(out.output_tail.as_deref().unwrap_or("").contains("bad"), "stderr 合并捕获");
    }

    #[test]
    fn exec_run_cwd_takes_effect() {
        let (_reg, ctx) = ctx();
        let dir = std::env::temp_dir().to_string_lossy().to_string();
        let out = block_on(ExecExecutor.run(
            &serde_json::json!({ "command": "pwd", "cwd": dir }),
            ctx,
        ));
        assert_eq!(out.status, ActionStatus::Ok);
        // macOS /tmp → /private/tmp 符号链接：canonicalize 后比较
        let got = std::path::Path::new(out.output_tail.as_deref().unwrap_or("").trim()).canonicalize();
        let want = std::path::Path::new(&dir).canonicalize();
        assert_eq!(got.unwrap(), want.unwrap(), "cwd 生效");
    }

    #[test]
    fn exec_run_timeout_kills_process_group() {
        let (_reg, ctx) = ctx();
        let start = std::time::Instant::now();
        // 注入 2s 超时（对外契约 1-120 分钟；sleep 598 + 孤儿子进程组杀后无残留；
        // 标记 598 与 kill_process_tree 测试的 599 区分——并行测试互不误判）
        let out = block_on(exec_run_with_timeout(
            &serde_json::json!({ "command": "sleep 598 & sleep 598" }),
            ctx,
            std::time::Duration::from_secs(2),
        ));
        assert!(start.elapsed() < std::time::Duration::from_secs(30), "超时应及时终止");
        assert_eq!(out.status, ActionStatus::Failed);
        assert_eq!(out.summary, summary_timeout_key(0), "summary 为超时模板键（注入秒级 → 0 分钟参数）");
        // sleep 进程被杀（系统内无本测试拉起的 sleep 598）
        let out_str = std::process::Command::new("sh")
            .arg("-c")
            .arg("ps -eo command | grep 'sleep 598' | grep -v grep || true")
            .output()
            .unwrap();
        assert!(
            String::from_utf8_lossy(&out_str.stdout).trim().is_empty(),
            "进程组被杀无残留"
        );
    }

    #[test]
    fn exec_run_output_flood_truncated() {
        let (_reg, ctx) = ctx();
        let out = block_on(ExecExecutor.run(
            // 5KB 输出洪水：尾部 ≤2KB + 截断标记（yes 输出每行 "0123456789\n"，
            // finish 的 trim 去掉收尾换行 → 尾部为循环节的子串）
            &serde_json::json!({ "command": "yes 0123456789 | head -c 5120" }),
            ctx,
        ));
        assert_eq!(out.status, ActionStatus::Ok);
        let tail = out.output_tail.unwrap();
        assert!(tail.starts_with(TailBuf::TRUNC_MARK), "截尾标记：{}", &tail[..tail.len().min(40)]);
        let body = &tail[TailBuf::TRUNC_MARK.len()..];
        assert!(
            ((TailBuf::MAX - 11)..=TailBuf::MAX).contains(&body.len()),
            "截取后长度 ≈2KB（trim 收尾换行 ±1 行）：{}",
            body.len()
        );
        let pat = "0123456789\n".repeat(220);
        assert!(pat.contains(body), "尾部须为循环节后缀");
    }

    #[test]
    fn exec_run_registers_and_deregisters_in_registry() {
        // N7 钉子：run 期间登记表有句柄；run 返回前已注销（完成后登记表空）
        let (reg, ctx) = ctx();
        let reg2 = reg.clone();
        let jh = tauri::async_runtime::spawn(async move {
            ExecExecutor
                .run(&serde_json::json!({ "command": "sleep 2" }), ctx)
                .await
        });
        // 等登记出现（spawn 后注册）
        let mut seen = false;
        for _ in 0..40 {
            if reg2.lock().unwrap().len() == 1 {
                seen = true;
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(50));
        }
        assert!(seen, "执行期间登记表有运行句柄");
        let out = block_on(async { jh.await.unwrap() });
        assert_eq!(out.status, ActionStatus::Ok);
        assert!(
            reg2.lock().unwrap().is_empty(),
            "完成先从登记表移除（N7）"
        );
    }

    #[test]
    fn kill_process_tree_unix_kills_group() {
        // 直接钉组杀：setsid 的进程组内孤儿子进程也被杀（ps 断言）。
        // 注：`sh -c "sleep 600 & sleep 600"` 的 sh 本体起完后台进程即退出
        //（wait 拿到的是早已正常的退出码）——组杀的对象是残留的孤儿组。
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt as _;
            let mut child = {
                let mut c = std::process::Command::new("sh");
                c.arg("-c").arg("sleep 599 & sleep 599");
                unsafe {
                    c.pre_exec(|| {
                        libc::setsid();
                        Ok(())
                    });
                }
                c.stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .spawn()
                    .unwrap()
            };
            let pid = child.id();
            std::thread::sleep(std::time::Duration::from_millis(300));
            kill_process_tree(pid);
            let _ = child.wait();
            // 孤儿子进程（同组 sleep 599）同样无残留
            let ps = std::process::Command::new("sh")
                .arg("-c")
                .arg("ps -eo command | grep 'sleep 599' | grep -v grep || true")
                .output()
                .unwrap();
            assert!(String::from_utf8_lossy(&ps.stdout).trim().is_empty());
        }
    }

    // ---- 伪 session（TC-M4-10） ----

    #[test]
    fn task_apply_emits_state_and_notifier_pair() {
        use tauri::Manager;
        let app = tauri::test::mock_app();
        let handle = app.handle();
        let sm = Arc::new(Mutex::new(SessionStateMachine::new()));
        let notified = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let n2 = notified.clone();
        let notifier = Arc::new(crate::http_server::DisplayNotifier::new(Arc::new(
            move |_kind, agent| {
                assert_eq!(agent, TASK_AGENT);
                n2.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
            },
        )));
        handle.manage(sm.clone());
        handle.manage(notifier);
        // AgentActivity 也 manage（断言 task_apply 不写它）
        let activity = crate::http_server::new_agent_activity();
        handle.manage(activity.clone());

        task_apply(handle, 7, Kind::Working);
        task_apply(handle, 7, Kind::Success);

        let st = sm.lock().unwrap();
        let d = st.display();
        assert_eq!(d.kind, Kind::Success);
        assert_eq!(d.agent, TASK_AGENT);
        drop(st);
        assert_eq!(
            notified.load(std::sync::atomic::Ordering::SeqCst),
            2,
            "每次 apply 必配一次 notify（apply+notify 成对）"
        );
        assert!(
            activity.lock().unwrap().is_empty(),
            "伪 session 不更新 AgentActivity"
        );
    }

    #[test]
    fn task_session_key_shape() {
        assert_eq!(task_session_key(42), "task:42");
        assert_eq!(TASK_AGENT, "task");
    }

    // ---- 心跳 15s vs idle 回收 30s（TC-M4-10-3，注入时钟） ----

    #[test]
    fn heartbeat_interval_keeps_session_alive_between_recycles() {
        use std::time::{Duration, Instant};
        let mut sm = SessionStateMachine::new();
        let t0 = Instant::now();
        let hb = Duration::from_millis(TASK_HEARTBEAT_MS);
        let idle = Duration::from_millis(IDLE_RECYCLE_MS);
        // 正常心跳：t0 注入 Working，之后每 15s 心跳；30s 粒度 tick 不回收
        sm.apply_event(TASK_AGENT, "task:1", Kind::Working, t0);
        for round in 1..=4u32 {
            let now = t0 + hb * round; // 15s/30s/45s/60s
            if round % 2 == 0 {
                sm.tick(now, Duration::from_secs(30), idle);
            }
            sm.apply_event(TASK_AGENT, "task:1", Kind::Working, now);
        }
        sm.tick(t0 + Duration::from_secs(65), Duration::from_secs(30), idle);
        assert_eq!(sm.display().kind, Kind::Working, "15s 心跳 < 30s idle 回收：持续保鲜");
        // 心跳停止 >30s → 回收（延迟 >15s 两次即超 30s：可观察）
        let mut sm2 = SessionStateMachine::new();
        sm2.apply_event(TASK_AGENT, "task:2", Kind::Working, t0);
        sm2.tick(t0 + Duration::from_secs(31), Duration::from_secs(30), idle);
        assert_eq!(sm2.display().kind, Kind::Idle, "无心跳 30s 后被回收");
    }

    // ---- 启动清理 / 退出处置（TC-M4-15） ----

    #[test]
    fn cleanup_running_logs_is_idempotent() {
        let conn = Connection::open_in_memory().unwrap();
        crate::db::migrate(&conn).unwrap();
        conn.execute(
            "INSERT INTO action_logs (reminder_id, action_type, status, summary, started_at) \
             VALUES (1, 'exec', 'running', '', '2026-08-25T10:00:00+08:00')",
            [],
        )
        .unwrap();
        assert_eq!(cleanup_running_logs(&conn), 1);
        let (status, summary): (String, String) = conn
            .query_row("SELECT status, summary FROM action_logs WHERE id = 1", [], |r| Ok((r.get(0)?, r.get(1)?)))
            .unwrap();
        assert_eq!(status, "failed");
        assert_eq!(summary, SUMMARY_STALE);
        // 幂等：再跑 0 行
        assert_eq!(cleanup_running_logs(&conn), 0);
    }

    #[test]
    fn abort_all_on_exit_kills_and_writes_failed() {
        use tauri::Manager;
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt as _;
            let app = tauri::test::mock_app();
            let handle = app.handle();
            let conn = Connection::open_in_memory().unwrap();
            crate::db::migrate(&conn).unwrap();
            conn.execute(
                "INSERT INTO action_logs (reminder_id, action_type, status, summary, started_at) \
                 VALUES (1, 'exec', 'running', '', '2026-08-25T10:00:00+08:00')",
                [],
            )
            .unwrap();
            let mut child = {
                let mut c = std::process::Command::new("sh");
                c.arg("-c").arg("sleep 600");
                unsafe {
                    c.pre_exec(|| {
                        libc::setsid();
                        Ok(())
                    });
                }
                c.stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .spawn()
                    .unwrap()
            };
            let pid = child.id();
            let registry = Arc::new(Mutex::new(RunningTasks::default()));
            registry.lock().unwrap().tasks.insert(1, RunningProc { pid });
            handle.manage(registry);
            handle.manage(Mutex::new(conn));

            std::thread::sleep(std::time::Duration::from_millis(200));
            abort_all_on_exit(handle);
            let st = child.wait().unwrap();
            assert!(!st.success(), "退出处置杀掉运行中进程");
            let (status, summary): (String, String) = {
                let db = handle.state::<Mutex<Connection>>();
                let c = db.lock().unwrap();
                c.query_row("SELECT status, summary FROM action_logs WHERE id = 1", [], |r| Ok((r.get(0)?, r.get(1)?)))
                    .unwrap()
            };
            assert_eq!(status, "failed");
            assert_eq!(summary, SUMMARY_INTERRUPTED, "补写「App 退出中断」");
            // N7：二次调用（登记表已清空）无动作、不重复写
            abort_all_on_exit(handle);
            let (status, _): (String, String) = {
                let db = handle.state::<Mutex<Connection>>();
                let c = db.lock().unwrap();
                c.query_row("SELECT status, summary FROM action_logs WHERE id = 1", [], |r| Ok((r.get(0)?, r.get(1)?)))
                    .unwrap()
            };
            assert_eq!(status, "failed");
        }
    }
}
