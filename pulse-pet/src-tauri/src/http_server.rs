//! Rust 侧 HTTP server（tiny_http，DESIGN §3.2，TC-EV-11~15 / TC-SEC-03）。
//!
//! - 绑定 `127.0.0.1:<port>`，首选 `47811`，占用则回退随机端口并写 endpoint 文件。
//! - 路由：`GET /health`（无鉴权）、`GET /whoami`（token）、`POST /state`（token）、
//!   `POST /bubble`（token，v1 留接口）；未知路由 404。
//! - 鉴权：header `x-pulsepet-token`（兼容 `Authorization: Bearer <token>`）；无/错 → 401。
//! - body 契约：`sessionId/kind/agent` 必填（缺 → 400），`kind` 为 8 种归一化值之一
//!   （非法 → 400），`project/detail` 可缺省；合法 → 200 `{action:null}`。
//! - 限流：共享 30 req/s 全局（非 per-session），超出 429。
//! - 超时：连接（接受请求）~2s、响应 ~3s；单次连接 `Connection: close`。
//! - body 上限 ≤16KB（超出 413，服务不崩溃）。
//! - v1 return channel：`/state`/`/bubble` 响应恒 `{action:null}`。
//!
//! 事件入内存：合法 `/state` 事件 apply 到 `SessionStateMachine` 并触发显示状态回调
//! （经 Tauri event 推给前端），不明文落盘（TC-SEC-06）。

use std::io::Read;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use crate::runtime;
use crate::session_state::{Kind, SessionStateMachine};

/// 显示状态变化回调（lib.rs 里封成 Tauri event emit）。
pub type StateChangeCallback = Arc<dyn Fn(Kind) + Send + Sync>;

/// 显示状态去重通知器：仅当合并后的显示状态真正变化时回调一次。
pub struct DisplayNotifier {
    last: Mutex<Option<Kind>>,
    on_change: StateChangeCallback,
}

impl DisplayNotifier {
    pub fn new(on_change: StateChangeCallback) -> Self {
        Self {
            last: Mutex::new(None),
            on_change,
        }
    }

    /// 计算当前显示状态，变化时触发回调。
    pub fn notify(&self, state: &Arc<Mutex<SessionStateMachine>>) {
        let display = {
            let st = state.lock().unwrap_or_else(|p| p.into_inner());
            st.display()
        };
        let mut last = self.last.lock().unwrap_or_else(|p| p.into_inner());
        if *last != Some(display) {
            *last = Some(display);
            (self.on_change)(display);
        }
    }
}

/// HTTP server 配置（测试可覆盖端口 / 上限 / 超时 / runtime 目录）。
pub struct HttpConfig {
    pub runtime_dir: PathBuf,
    pub preferred_port: u16,
    pub max_body: usize,
    pub rate_limit: u32,
    pub rate_window: Duration,
    pub accept_timeout: Duration,
}

impl Default for HttpConfig {
    fn default() -> Self {
        Self {
            runtime_dir: runtime::runtime_dir(),
            preferred_port: 47811,
            max_body: 16 * 1024,
            rate_limit: 30,
            rate_window: Duration::from_secs(1),
            accept_timeout: Duration::from_secs(2),
        }
    }
}

/// 固定窗口限流器（全局共享，非 per-session）。
pub struct RateLimiter {
    window_start: Option<Instant>,
    count: u32,
}

impl RateLimiter {
    pub fn new() -> Self {
        Self {
            window_start: None,
            count: 0,
        }
    }

    /// 返回 true 表示放行（并计数），false 表示超限拒绝。
    pub fn allow(&mut self, now: Instant, limit: u32, window: Duration) -> bool {
        match self.window_start {
            None => {
                self.window_start = Some(now);
                self.count = 1;
                true
            }
            Some(start) => {
                if now.saturating_duration_since(start) >= window {
                    self.window_start = Some(now);
                    self.count = 1;
                    true
                } else if self.count < limit {
                    self.count += 1;
                    true
                } else {
                    false
                }
            }
        }
    }
}

impl Default for RateLimiter {
    fn default() -> Self {
        Self::new()
    }
}

/// 一条合法 `/state` 事件（apply 到状态机）。
/// `agent/project/detail` 为可选元数据：v1 校验通过但不落盘（M3 token 统计用 project、
/// M4 气泡用 detail），故标注 allow(dead_code)。
#[derive(Debug, Clone)]
#[allow(dead_code)]
pub struct StateEvent {
    pub session_id: String,
    pub kind: Kind,
    pub agent: String,
    pub project: Option<String>,
    pub detail: Option<String>,
}

/// 路由处理结果：要么直接响应，要么是一条待 apply 的合法事件。
pub enum HandleOutcome {
    Respond { status: u16, body: String },
    State(StateEvent),
}

/// 从请求头提取 token（`x-pulsepet-token` 优先，兼容 `Authorization: Bearer`）。
pub fn extract_token(headers: &[tiny_http::Header]) -> Option<String> {
    for h in headers {
        if h.field.equiv("x-pulsepet-token") {
            return Some(h.value.as_str().trim().to_string());
        }
    }
    for h in headers {
        if h.field.equiv("authorization") {
            let v = h.value.as_str();
            if let Some(rest) = v.strip_prefix("Bearer ") {
                return Some(rest.trim().to_string());
            }
        }
    }
    None
}

/// 纯路由/鉴权/body 校验（与网络 IO 解耦，便于单测）。
pub fn handle_request(
    method: &str,
    path: &str,
    provided_token: Option<&str>,
    expected_token: &str,
    body: &[u8],
    max_body: usize,
) -> HandleOutcome {
    use HandleOutcome::{Respond, State};

    // body 上限（TC-EV-15）
    if body.len() > max_body {
        return Respond {
            status: 413,
            body: r#"{"error":"payload too large"}"#.to_string(),
        };
    }

    let authed = provided_token.is_some_and(|t| t == expected_token);

    match (method, path) {
        // /health 无鉴权（TC-EV-12）
        ("GET", "/health") => Respond {
            status: 200,
            body: r#"{"status":"ok"}"#.to_string(),
        },
        ("GET", "/whoami") => {
            if !authed {
                return Respond {
                    status: 401,
                    body: r#"{"error":"unauthorized"}"#.to_string(),
                };
            }
            Respond {
                status: 200,
                body: r#"{"instance":"pulsepet"}"#.to_string(),
            }
        }
        ("POST", "/state") => {
            if !authed {
                return Respond {
                    status: 401,
                    body: r#"{"error":"unauthorized"}"#.to_string(),
                };
            }
            match parse_state_event(body) {
                Ok(ev) => State(ev),
                Err(msg) => Respond {
                    status: 400,
                    body: format!(r#"{{"error":"{msg}"}}"#),
                },
            }
        }
        // v1 留接口：opencode 不主动调（TC-EV-12）
        ("POST", "/bubble") => {
            if !authed {
                return Respond {
                    status: 401,
                    body: r#"{"error":"unauthorized"}"#.to_string(),
                };
            }
            Respond {
                status: 200,
                body: r#"{"action":null}"#.to_string(),
            }
        }
        _ => Respond {
            status: 404,
            body: r#"{"error":"not found"}"#.to_string(),
        },
    }
}

fn get_str(obj: &serde_json::Map<String, serde_json::Value>, key: &str) -> Option<String> {
    obj.get(key).and_then(|v| v.as_str()).map(|s| s.to_string())
}

/// 解析并校验 `/state` body：`sessionId/kind/agent` 必填、`kind` 合法。
fn parse_state_event(body: &[u8]) -> Result<StateEvent, String> {
    let v: serde_json::Value =
        serde_json::from_slice(body).map_err(|_| "invalid json".to_string())?;
    let obj = v.as_object().ok_or("body must be an object")?;
    let session_id = get_str(obj, "sessionId").ok_or("missing sessionId")?;
    let kind_str = get_str(obj, "kind").ok_or("missing kind")?;
    let agent = get_str(obj, "agent").ok_or("missing agent")?;
    let kind = Kind::parse(&kind_str).ok_or("invalid kind")?;
    let project = get_str(obj, "project");
    let detail = get_str(obj, "detail");
    Ok(StateEvent {
        session_id,
        kind,
        agent,
        project,
        detail,
    })
}

/// server 运行句柄：端口 + 停机标志。
pub struct HttpServerHandle {
    pub port: u16,
    shutdown: Arc<AtomicBool>,
}

impl HttpServerHandle {
    /// 请求停机（线程在下一个 accept 超时后退出）。运行时 lib.rs 走 `shutdown_flag()`，
    /// 此处供集成测试使用。
    #[allow(dead_code)]
    pub fn shutdown(&self) {
        self.shutdown.store(true, Ordering::SeqCst);
    }

    /// 停机标志（供 lib.rs 的回收线程与 Exit 处理共享）。
    pub fn shutdown_flag(&self) -> Arc<AtomicBool> {
        self.shutdown.clone()
    }
}

/// 构造一个 JSON 响应（`Content-Type: application/json`）。
///
/// 连接语义：tiny_http 本身即「一请求一连接」（无 keep-alive，`respond` 后即关闭），
/// 等价于 `Connection: close`（TC-EV-14「一次性」）；tiny_http 会忽略/自行管理
/// `Connection` 头，故不手动添加。
fn json_response(status: u16, body: &str) -> tiny_http::Response<std::io::Cursor<Vec<u8>>> {
    let mut resp = tiny_http::Response::from_string(body.to_string()).with_status_code(status);
    resp.add_header(
        tiny_http::Header::from_bytes("Content-Type", "application/json")
            .expect("static header is ascii"),
    );
    resp
}

/// 启动 HTTP server（后台线程）+ 写 endpoint 文件。
pub fn start(
    state: Arc<Mutex<SessionStateMachine>>,
    notifier: Arc<DisplayNotifier>,
    token: String,
    config: HttpConfig,
) -> Result<HttpServerHandle, String> {
    std::fs::create_dir_all(&config.runtime_dir)
        .map_err(|e| format!("create runtime dir: {e}"))?;

    // 首选端口，冲突回退随机端口（TC-EV-09）
    let server = match tiny_http::Server::http(("127.0.0.1", config.preferred_port)) {
        Ok(s) => s,
        Err(_) => tiny_http::Server::http(("127.0.0.1", 0u16))
            .map_err(|e| format!("bind fallback port: {e}"))?,
    };
    let port = server
        .server_addr()
        .to_ip()
        .map(|a| a.port())
        .unwrap_or(config.preferred_port);

    // 写 endpoint 文件（端口回退时更新，TC-EV-09）
    let endpoint = config.runtime_dir.join("endpoint");
    std::fs::write(&endpoint, format!("127.0.0.1:{port}"))
        .map_err(|e| format!("write endpoint file: {e}"))?;

    let shutdown = Arc::new(AtomicBool::new(false));
    let shutdown_thread = shutdown.clone();

    std::thread::spawn(move || {
        let mut limiter = RateLimiter::new();
        loop {
            if shutdown_thread.load(Ordering::SeqCst) {
                break;
            }
            match server.recv_timeout(config.accept_timeout) {
                Ok(Some(request)) => {
                    // 全局共享限流（TC-EV-13）
                    if !limiter.allow(Instant::now(), config.rate_limit, config.rate_window) {
                        let _ = request.respond(json_response(429, r#"{"error":"rate limited"}"#));
                        continue;
                    }
                    handle_incoming(request, &token, &state, &notifier, config.max_body);
                }
                Ok(None) => continue, // accept 超时，回到循环检查停机标志
                Err(_) => break,      // unblock / socket 错误 → 退出
            }
        }
    });

    Ok(HttpServerHandle { port, shutdown })
}

fn handle_incoming(
    mut request: tiny_http::Request,
    token: &str,
    state: &Arc<Mutex<SessionStateMachine>>,
    notifier: &Arc<DisplayNotifier>,
    max_body: usize,
) {
    let method = request.method().as_str().to_string();
    let path = request
        .url()
        .split('?')
        .next()
        .unwrap_or("/")
        .to_string();
    let provided_token = extract_token(request.headers());

    // 读取 body（最多 max_body + 1 字节，超限由 handle_request 判 413）
    let mut body = Vec::new();
    {
        let reader = request.as_reader();
        let mut limited = reader.take((max_body + 1) as u64);
        let _ = limited.read_to_end(&mut body);
    }

    match handle_request(
        &method,
        &path,
        provided_token.as_deref(),
        token,
        &body,
        max_body,
    ) {
        HandleOutcome::Respond { status, body } => {
            let _ = request.respond(json_response(status, &body));
        }
        HandleOutcome::State(ev) => {
            {
                let mut st = state.lock().unwrap_or_else(|p| p.into_inner());
                st.apply_event(&ev.session_id, ev.kind, Instant::now());
            }
            notifier.notify(state);
            let _ = request.respond(json_response(200, r#"{"action":null}"#));
        }
    }
}

// ---------------------------------------------------------------------------
// 测试
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::net::TcpStream;

    const TOKEN: &str = "test-token";

    fn body_of(body: &'static str) -> &'static [u8] {
        body.as_bytes()
    }

    #[test]
    fn health_is_open_and_whoami_requires_token() {
        // /health 无鉴权
        match handle_request("GET", "/health", None, TOKEN, b"", 16 * 1024) {
            HandleOutcome::Respond { status, .. } => assert_eq!(status, 200),
            _ => panic!("expected respond"),
        }
        // /whoami 无 token → 401
        match handle_request("GET", "/whoami", None, TOKEN, b"", 16 * 1024) {
            HandleOutcome::Respond { status, .. } => assert_eq!(status, 401),
            _ => panic!("expected respond"),
        }
        // /whoami 正确 token → 200 且标识实例
        match handle_request("GET", "/whoami", Some(TOKEN), TOKEN, b"", 16 * 1024) {
            HandleOutcome::Respond { status, body } => {
                assert_eq!(status, 200);
                assert!(body.contains("pulsepet"));
            }
            _ => panic!("expected respond"),
        }
    }

    #[test]
    fn auth_rejects_wrong_token() {
        match handle_request("POST", "/state", Some("wrong"), TOKEN, body_of(r#"{"sessionId":"s","kind":"idle","agent":"opencode"}"#), 16 * 1024) {
            HandleOutcome::Respond { status, .. } => assert_eq!(status, 401),
            _ => panic!("expected 401"),
        }
    }

    #[test]
    fn state_missing_fields_return_400() {
        for body in [
            r#"{"kind":"idle","agent":"opencode"}"#,        // 缺 sessionId
            r#"{"sessionId":"s","agent":"opencode"}"#,      // 缺 kind
            r#"{"sessionId":"s","kind":"idle"}"#,           // 缺 agent
        ] {
            match handle_request("POST", "/state", Some(TOKEN), TOKEN, body_of(body), 16 * 1024) {
                HandleOutcome::Respond { status, .. } => assert_eq!(status, 400, "body: {body}"),
                _ => panic!("expected 400 for {body}"),
            }
        }
    }

    #[test]
    fn state_invalid_kind_returns_400() {
        let body = r#"{"sessionId":"s","kind":"sprinting","agent":"opencode"}"#;
        match handle_request("POST", "/state", Some(TOKEN), TOKEN, body_of(body), 16 * 1024) {
            HandleOutcome::Respond { status, .. } => assert_eq!(status, 400),
            _ => panic!("expected 400"),
        }
    }

    #[test]
    fn state_valid_body_with_optional_fields_returns_state_event() {
        let body = r#"{"sessionId":"s","kind":"editing","agent":"opencode","project":"pulse-pet"}"#;
        match handle_request("POST", "/state", Some(TOKEN), TOKEN, body_of(body), 16 * 1024) {
            HandleOutcome::State(ev) => {
                assert_eq!(ev.session_id, "s");
                assert_eq!(ev.kind, Kind::Editing);
                assert_eq!(ev.agent, "opencode");
                assert_eq!(ev.project.as_deref(), Some("pulse-pet"));
                assert_eq!(ev.detail, None);
            }
            _ => panic!("expected state event"),
        }
    }

    #[test]
    fn unknown_route_returns_404() {
        match handle_request("GET", "/nope", None, TOKEN, b"", 16 * 1024) {
            HandleOutcome::Respond { status, .. } => assert_eq!(status, 404),
            _ => panic!("expected 404"),
        }
    }

    #[test]
    fn body_over_limit_returns_413() {
        let body = vec![b'x'; 16 * 1024 + 1];
        match handle_request("POST", "/state", Some(TOKEN), TOKEN, &body, 16 * 1024) {
            HandleOutcome::Respond { status, .. } => assert_eq!(status, 413),
            _ => panic!("expected 413"),
        }
    }

    #[test]
    fn body_at_limit_is_accepted() {
        let body = format!(r#"{{"sessionId":"s","kind":"idle","agent":"a","detail":"{}"}}"#, "x".repeat(16 * 1024 - 60));
        match handle_request("POST", "/state", Some(TOKEN), TOKEN, body.as_bytes(), 16 * 1024) {
            HandleOutcome::State(_) => {}
            HandleOutcome::Respond { status, .. } => panic!("expected accept, got {status}"),
        }
    }

    #[test]
    fn rate_limiter_allows_limit_then_rejects() {
        let mut rl = RateLimiter::new();
        let now = Instant::now();
        for i in 0..30 {
            assert!(rl.allow(now, 30, Duration::from_secs(1)), "req {i} should pass");
        }
        assert!(!rl.allow(now, 30, Duration::from_secs(1)), "31st should be rejected");
    }

    #[test]
    fn rate_limiter_resets_after_window() {
        let mut rl = RateLimiter::new();
        let now = Instant::now();
        for _ in 0..30 {
            assert!(rl.allow(now, 30, Duration::from_secs(1)));
        }
        // 窗口滚动后恢复
        assert!(rl.allow(now + Duration::from_secs(1), 30, Duration::from_secs(1)));
    }

    #[test]
    fn extract_token_prefers_x_pulsepet_header() {
        let h1 = tiny_http::Header::from_bytes("x-pulsepet-token", "abc").unwrap();
        assert_eq!(extract_token(&[h1]).as_deref(), Some("abc"));
        let h2 = tiny_http::Header::from_bytes("Authorization", "Bearer def").unwrap();
        assert_eq!(extract_token(&[h2]).as_deref(), Some("def"));
    }

    // ---- 集成测试：真实启动 server，用 TcpStream 打请求 ----

    fn start_test_server(rate_limit: u32) -> HttpServerHandle {
        let tmp = std::env::temp_dir().join(format!("pulsepet-http-test-{}", std::process::id()));
        std::fs::create_dir_all(&tmp).unwrap();
        let state = Arc::new(Mutex::new(SessionStateMachine::new()));
        let notifier = Arc::new(DisplayNotifier::new(Arc::new(|_| {})));
        let cfg = HttpConfig {
            runtime_dir: tmp,
            preferred_port: 0, // 随机端口
            max_body: 16 * 1024,
            rate_limit,
            rate_window: Duration::from_secs(1),
            accept_timeout: Duration::from_millis(200),
        };
        start(state, notifier, TOKEN.to_string(), cfg).unwrap()
    }

    fn raw_request(port: u16, req: &str) -> (u16, String) {
        let mut stream = TcpStream::connect(("127.0.0.1", port)).unwrap();
        stream
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        stream.write_all(req.as_bytes()).unwrap();
        let mut buf = Vec::new();
        stream.read_to_end(&mut buf).unwrap();
        let text = String::from_utf8_lossy(&buf).to_string();
        let status = text
            .lines()
            .next()
            .and_then(|l| l.split_whitespace().nth(1))
            .and_then(|s| s.parse::<u16>().ok())
            .unwrap_or(0);
        let body = text.split("\r\n\r\n").nth(1).unwrap_or("").to_string();
        (status, body)
    }

    fn post_state(port: u16, token: &str, body: &str) -> (u16, String) {
        let req = format!(
            "POST /state HTTP/1.1\r\nHost: 127.0.0.1\r\nx-pulsepet-token: {token}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
            body.len()
        );
        raw_request(port, &req)
    }

    #[test]
    fn integration_routes_and_auth() {
        let h = start_test_server(1000);
        // /health 无鉴权 200
        let (s, _) = raw_request(h.port, "GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n");
        assert_eq!(s, 200);
        // /state 无 token 401
        let (s, _) = raw_request(
            h.port,
            "POST /state HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",
        );
        assert_eq!(s, 401);
        // /state 错 token 401
        let (s, _) = post_state(h.port, "wrong", r#"{"sessionId":"s","kind":"idle","agent":"a"}"#);
        assert_eq!(s, 401);
        // /state 对 token 200 {action:null}
        let (s, body) = post_state(h.port, TOKEN, r#"{"sessionId":"s","kind":"idle","agent":"a"}"#);
        assert_eq!(s, 200);
        assert_eq!(body, r#"{"action":null}"#);
        // 未知路由 404
        let (s, _) = raw_request(h.port, "GET /nope HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n");
        assert_eq!(s, 404);
        // /bubble 对 token 200
        let (s, body) = raw_request(
            h.port,
            &format!("POST /bubble HTTP/1.1\r\nHost: 127.0.0.1\r\nx-pulsepet-token: {TOKEN}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"),
        );
        assert_eq!(s, 200);
        assert_eq!(body, r#"{"action":null}"#);
        h.shutdown();
    }

    #[test]
    fn integration_body_limit_and_validation() {
        let h = start_test_server(1000);
        // 缺 kind → 400
        let (s, _) = post_state(h.port, TOKEN, r#"{"sessionId":"s","agent":"a"}"#);
        assert_eq!(s, 400);
        // kind 非法 → 400
        let (s, _) = post_state(h.port, TOKEN, r#"{"sessionId":"s","kind":"oops","agent":"a"}"#);
        assert_eq!(s, 400);
        // 超 16KB → 413（服务不崩）
        let big = "x".repeat(16 * 1024 + 1);
        let (s, _) = post_state(h.port, TOKEN, &format!(r#"{{"sessionId":"s","kind":"idle","agent":"a","detail":"{big}"}}"#));
        assert_eq!(s, 413);
        h.shutdown();
    }

    #[test]
    fn integration_rate_limit_shared() {
        // rate_limit=2，快速 6 连 → 前 2 个 200，其后 429（全局共享，非 per-session）
        let h = start_test_server(2);
        let mut allowed = 0;
        let mut rejected = 0;
        for _ in 0..6 {
            let (s, _) = post_state(h.port, TOKEN, r#"{"sessionId":"s","kind":"idle","agent":"a"}"#);
            match s {
                200 => allowed += 1,
                429 => rejected += 1,
                other => panic!("unexpected status {other}"),
            }
        }
        assert_eq!(allowed, 2, "first two within limit");
        assert_eq!(rejected, 4, "rest rejected");
        h.shutdown();
    }

    #[test]
    fn integration_single_use_connection() {
        // TC-EV-14「一次性」：插件每次请求带 `Connection: close`，tiny_http 响应后即
        // 关闭连接（EOF），不 keep-alive。
        let h = start_test_server(1000);
        let mut stream = TcpStream::connect(("127.0.0.1", h.port)).unwrap();
        stream
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        stream
            .write_all(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            .unwrap();
        let mut buf = Vec::new();
        stream.read_to_end(&mut buf).unwrap(); // read_to_end 到达 EOF = 服务端已关连接
        let text = String::from_utf8_lossy(&buf).to_string();
        assert!(text.starts_with("HTTP/1.1 200"));
        // 再次读应立即 EOF（连接已被服务端关闭，无法复用）
        let mut extra = [0u8; 1];
        let n = stream.read(&mut extra).unwrap_or(0);
        assert_eq!(n, 0, "connection should be closed after one response");
        h.shutdown();
    }
}
