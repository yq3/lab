//! v2 registry（docs/v2/agent-registry.md §6.1）：Rust 侧 agent 注册表——
//! 单一事实源。
//!
//! 收敛前 agent 注册点散落各层各持一份微型注册表互不引用（http_server
//! `AGENT_WHITELIST` / integrations `ID_*` 常量 + if-else 分发 / lib.rs idle
//! 分流 match 字面量），新增 agent 必改 14 处（§4）。收敛后全部变查表：
//! 新增 agent = 一个 hook 脚本 + 一套函数 + 此表一行注册 + i18n 键（§6.6）。
//!
//! 分发形态（2026-08-28 拍板，§8.0 决策 3）：**函数指针表**——零运行时
//! 开销、无泛型/trait object 负担，现有内层函数直接挂表；统计源 enum
//! dispatch（同样无 trait object）。P3 的 N 源化编排（query_stats_all /
//! today_stats_all）再消费 `StatsSource`，P1 仅作 idle 分流键。
//!
//! 双端互钉（§6.3）：前端 `src/lib/agents.ts` 的 AGENTS 表与本表经
//! include_str! 测试断言两端 id + short 集合一致（防漂移——4 份注册表
//! 各自腐烂的根因）。

use crate::integrations::{self, IntegrationStatus};
use crate::i18n::Lang;
use std::sync::{Arc, Mutex};
use tauri::Manager as _;

/// opencode 接入 id（原 integrations::ID_OPENCODE 迁入，唯一事实源）。
pub const ID_OPENCODE: &str = "opencode";
/// claude-code 接入 id（原 integrations::ID_CLAUDE_CODE 迁入）。
pub const ID_CLAUDE_CODE: &str = "claude-code";

/// 统计源形态（enum dispatch，无 trait object）。P3 的 N 源化编排消费；
/// P1 仅作 lib.rs idle 分流的分发键（§6.1 决策 1）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StatsSource {
    /// opencode 自带 SQLite（`opencode.db` 直接 SQL 查询）。
    OpenencodeDb,
    /// Claude Code 会话 JSONL（transcript 解析 + TranscriptCache 缓存）。
    CcTranscript,
    /// 无统计源：仅事件链接入的形态（§7.1——Token 页永远没有该 agent 数据，
    /// idle 汇报跳过）。当前两家均不使用，为后续「只有事件链」的 agent 预留
    /// （idle 分流的跳过臂已就位；构造点随 P4 接入出现）。
    #[allow(dead_code)]
    None,
}

/// 一个被监测 agent 的全部注册属性（§6.1：单一事实源）。
pub struct AgentSpec {
    /// agent id（事件链与统计链共同主键，两链唯一必须锁死的约定；不得为
    /// `"task"`——action_exec 伪 agent 冲突约束，自测钉住）。
    pub id: &'static str,
    /// 短名（oc / cc；与前端 src/lib/agents.ts 锁步，§6.3 互钉）。
    /// P1 仅测试消费（自测 + P2 include_str 互钉）；运行期消费点在 P3
    /// （N 源化编排的 by_agent 归并）——同 StateEvent.project 先例定点豁免。
    #[allow(dead_code)]
    pub short_name: &'static str,
    /// 主源标记（P3，§6.4 口径 A′ 规则 3）：degraded 横幅仅主源 **Failed**
    /// （在但坏）× 其余有数据触发（Missing 不触发）；硬报错（全部源无数据且
    /// 无一源 Ok）透传主源错误。当前仅 opencode true——「主源」是历史语义位
    /// （M3/M5 时代 opencode 是唯一源），非重要性排序；全表恰一个主源
    /// （find_known_ids_hit 钉住）。
    pub is_primary: bool,
    /// 本地安装物形态（None = 无接入管理卡，§9-6 预留）。
    pub integration: Option<IntegrationSpec>,
    /// 统计源（idle 分流 + P3 编排的分发键）。
    pub stats: StatsSource,
    /// 源生命周期自注册（§6.1 决策 2，吸收 #13 接线组）：该 agent 统计源
    /// 的 managed state 注册（无状态源挂 no-op）。lib.rs setup 经
    /// `register_states` 集中调用，须先于 HTTP server 启动与窗口创建循环
    /// （issue #9 铁律；cc_dispatch 派发时经 app.state 取句柄）。
    pub register_state: fn(&tauri::AppHandle),
}

/// 接入管理（安装/卸载/doctor）的函数指针组（§6.1）。
///
/// install/uninstall 指向本模块的薄适配函数（内层函数签名各异——
/// install_opencode 返回 PathBuf、install_cc 双路径注入——无法直接挂表；
/// 适配层以真实环境路径调用既有内层函数，**内层函数签名不变**，
/// tempdir 注入单测全部免改）。
pub struct IntegrationSpec {
    /// 安装/重装（阻塞 I/O，调用方在 spawn_blocking 内）。
    pub install: fn() -> Result<(), String>,
    /// 卸载（幂等）。
    pub uninstall: fn() -> Result<(), String>,
    /// 接入探测（阻塞 I/O）：node 探测结果（None = 该接入不需要 node）+
    /// lastEventAt + 语言 → IntegrationStatus。指向 integrations 拆分的
    /// status_opencode / status_cc。
    pub status_probe: fn(Option<bool>, Option<u64>, Lang) -> IntegrationStatus,
    /// CC 独有 spawn node 探测 → 提为字段（§6.1）：由查表分发层控制是否
    /// 现测 `node --version`，新 agent 不再靠 if id == 分支。
    pub needs_node_probe: bool,
    /// 「建议新开会话」类安装/卸载后提示 → 提为字段（CC 独有，§1.4.4）。
    pub install_hint: bool,
}

/// agent 注册表（当前两家；新增 agent 在此加一行，§6.6 目标态）。
pub static AGENTS: &[AgentSpec] = &[
    AgentSpec {
        id: ID_OPENCODE,
        short_name: "oc",
        is_primary: true,
        integration: Some(IntegrationSpec {
            install: install_oc,
            uninstall: uninstall_oc,
            status_probe: integrations::status_opencode,
            needs_node_probe: false,
            install_hint: false,
        }),
        stats: StatsSource::OpenencodeDb,
        register_state: register_noop,
    },
    AgentSpec {
        id: ID_CLAUDE_CODE,
        short_name: "cc",
        is_primary: false,
        integration: Some(IntegrationSpec {
            install: install_cc_hook,
            uninstall: uninstall_cc_hook,
            status_probe: integrations::status_cc,
            needs_node_probe: true,
            install_hint: true,
        }),
        stats: StatsSource::CcTranscript,
        register_state: register_cc_cache,
    },
];

/// 按 id 查注册表；未知 id → None（「不落 else」的根基——消两处静默错误的
/// 温床，§8.7.2 P1 钉 2）。
pub fn find(id: &str) -> Option<&'static AgentSpec> {
    AGENTS.iter().find(|spec| spec.id == id)
}

/// 各源 managed state 集中注册（lib.rs setup 调用；取代此前 lib.rs 逐个
/// 创建 + app.manage 的接线组，§8.1）。
pub fn register_states(app: &tauri::AppHandle) {
    for spec in AGENTS {
        (spec.register_state)(app);
    }
}

// ---------------------------------------------------------------------------
// 适配函数（薄壳：真实环境路径 → 既有内层函数；内层签名不变，tempdir
// 注入单测免改）
// ---------------------------------------------------------------------------

fn install_oc() -> Result<(), String> {
    integrations::install_opencode(&integrations::opencode_dir()).map(|_| ())
}

fn install_cc_hook() -> Result<(), String> {
    integrations::install_cc(&integrations::claude_settings_path(), &integrations::cc_hooks_dir())
}

fn uninstall_oc() -> Result<(), String> {
    integrations::uninstall_opencode(&integrations::opencode_dir())
}

fn uninstall_cc_hook() -> Result<(), String> {
    integrations::uninstall_cc(&integrations::claude_settings_path(), &integrations::cc_hooks_dir())
}

/// 无 managed state 的源（opencode 直查 SQLite，无缓存可注册）。
fn register_noop(_: &tauri::AppHandle) {}

/// CC transcript 文件级缓存（原 lib.rs 接线组迁入；TC-M5-02 语义不变）。
/// 泛型内层供 tauri::test（MockRuntime）驱动；生产路径经上面的 Wry 薄壳
/// 挂入函数指针表。
fn register_cc_cache(app: &tauri::AppHandle) {
    register_cc_cache_inner(app)
}

fn register_cc_cache_inner<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    app.manage(Arc::new(Mutex::new(crate::transcript::TranscriptCache::default())));
}

// ---------------------------------------------------------------------------
// 测试（agent-registry §8.7.2 P1 钉 1~3 + register_states 功能钉）
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// P1 钉 1：find 已知 id 命中（id / 短名 / 统计源 / 接入形态齐备）。
    #[test]
    fn find_known_ids_hit() {
        let oc = find(ID_OPENCODE).expect("opencode 必注册");
        assert_eq!(oc.id, "opencode");
        assert_eq!(oc.short_name, "oc");
        assert_eq!(oc.stats, StatsSource::OpenencodeDb);
        assert!(oc.integration.is_some(), "opencode 有接入管理卡");
        let cc = find(ID_CLAUDE_CODE).expect("claude-code 必注册");
        assert_eq!(cc.id, "claude-code");
        assert_eq!(cc.short_name, "cc");
        assert_eq!(cc.stats, StatsSource::CcTranscript);
        let cc_intg = cc.integration.as_ref().expect("cc 有接入管理卡");
        assert!(cc_intg.needs_node_probe, "CC doctor 现测 node（提为字段）");
        assert!(cc_intg.install_hint, "CC 安装/卸载后附「建议新开会话」提示");
        let oc_intg = oc.integration.as_ref().expect("oc 有接入管理卡");
        assert!(!oc_intg.needs_node_probe);
        assert!(!oc_intg.install_hint);
        // P3（§6.4 口径 A′）：主源标记——opencode 是唯一主源（degraded 横幅与
        // 硬报错透传的锚点），全表恰一个。
        assert!(oc.is_primary, "opencode 为主源（is_primary）");
        assert!(!cc.is_primary, "claude-code 非主源");
        assert_eq!(
            AGENTS.iter().filter(|s| s.is_primary).count(),
            1,
            "全表必须恰一个主源（§6.4 规则 3 的锚）"
        );
    }

    /// P1 钉 2：未知 id → None（白名单校验 / idle 分流 / doctor 查表的共同
    /// 根基——「不落 else」，消静默错误 ①② 的温床）。
    #[test]
    fn find_unknown_id_returns_none() {
        assert!(find("codex").is_none(), "未注册 agent 不得命中");
        assert!(find("").is_none());
        assert!(find("claude").is_none(), "typo 形态不得命中");
        assert!(find("task").is_none(), "task 伪 agent 不在注册表");
    }

    /// P1 钉 3：AGENTS id 唯一且无 `"task"`（action_exec 伪 agent 冲突约束）。
    #[test]
    fn agent_ids_unique_and_no_task() {
        let ids: Vec<&str> = AGENTS.iter().map(|s| s.id).collect();
        let mut uniq = ids.clone();
        uniq.sort_unstable();
        uniq.dedup();
        assert_eq!(uniq.len(), ids.len(), "AGENTS id 必须唯一：{ids:?}");
        assert!(
            ids.iter().all(|id| *id != "task"),
            "agent id 不得为 \"task\"（与 action_exec 伪 agent 冲突，§2）"
        );
    }

    /// register_states 功能钉（TC-M5-02-1 精神随接线组收敛迁入）：CC 源
    /// 注册后 TranscriptCache 可经 app.state 取（未 manage 时 state() 直接
    /// panic——本测试即钉「manage 真的发生了」）；并钉指针表确实挂的是它
    /// （时序钉在 lib.rs order_nails）。指针等值比较用 `fn_addr_eq`（`==`
    /// 对函数指针地址唯一性无保证，test 构建告警——P3 顺手根治）。
    #[test]
    fn register_states_manages_transcript_cache() {
        assert!(
            std::ptr::fn_addr_eq(
                find(ID_CLAUDE_CODE)
                    .expect("cc 必注册")
                    .register_state,
                register_cc_cache as fn(&tauri::AppHandle),
            ),
            "CC spec 的 register_state 须指向 register_cc_cache"
        );
        let app = tauri::test::mock_app();
        register_cc_cache_inner(app.handle());
        let cache = app.handle().state::<Arc<Mutex<crate::transcript::TranscriptCache>>>();
        let _guard = cache.lock().unwrap_or_else(|p| p.into_inner());
    }

    /// P2 钉（agent-registry §6.3/§8.7.2）：双端互钉——include_str! 前端
    /// 注册表源码（相对本文件两级上溯到 pulse-pet 根），断言两端 id + short
    /// 集合逐项一致（防 Rust/TS 两表漂移——4 份注册表各自腐烂的根因；
    /// include_str 源码断言先例见 v0.2.1 R4）。匹配依赖 agents.ts 表
    /// 「每 agent 一行 `{ id: "..", short: "..", ... }`」格式（该文件头有注记）。
    #[test]
    fn frontend_agents_table_matches_rust_registry() {
        let ts = include_str!("../../src/lib/agents.ts");
        // 1) Rust → TS：每个 (id, short) 对在前端表逐项出现
        for spec in AGENTS {
            assert!(
                ts.contains(&format!("id: \"{}\", short: \"{}\"", spec.id, spec.short_name)),
                "前端 AGENTS 表缺或不一致：id={} short={}",
                spec.id,
                spec.short_name
            );
        }
        // 2) TS → Rust：前端表的 id 条目数与 Rust 相等（无多出/缺少），
        //    且每个 id 都在 Rust 表注册
        let ts_ids: Vec<&str> = ts
            .lines()
            .filter(|l| {
                let t = l.trim_start();
                !t.starts_with("//") && !t.starts_with("*")
            })
            .filter_map(|l| l.split_once("id: \"").map(|(_, r)| r))
            .filter_map(|r| r.split_once('"').map(|(id, _)| id))
            .collect();
        let rust_ids: Vec<&str> = AGENTS.iter().map(|s| s.id).collect();
        assert_eq!(
            ts_ids.len(),
            rust_ids.len(),
            "前端表条目数须与 Rust 一致（多出/缺少注册）：ts={ts_ids:?}"
        );
        for id in &ts_ids {
            assert!(rust_ids.contains(id), "前端 id {id} 未在 Rust AGENTS 注册");
        }
    }
}
