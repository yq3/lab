# PulsePet 新 agent 接入指南（agent-onboarding）

> 状态：**操作指南**（2026-08-30 整理；基线 = v0.2.3 · registry P1/P2/P3 已实施 + V2-OPEN-ITEMS §20 统计源状态行 / §21 品牌名规范）
> 姊妹篇：`agent-registry.md`（设计与实施记录，§4 十四处必改审计 / §6 注册表方案定稿 / §8 实施记录）——本档是它的**落地操作手册**：接一个新 agent 按清单照抄即可，设计依据回读姊妹篇对应节。
> 引用约定：设计节引用（§4 / §6 / §6.x / §8 / §9 / §12）指姊妹篇 agent-registry.md（该档仅 §1~§12）；**§13 起（§14 跨天归属 / §20 统计源状态行 / §21 品牌名规范）指 `docs/v2/V2-OPEN-ITEMS.md` 对应节**。
> 术语：本文"agent"指被 PulsePet 监测的 coding agent 宿主（opencode / Claude Code / 未来的 codex 等），与开发流程 subagent 无关。

---

## 0. 一句话结论

registry 收敛后，接入新 agent = **两条独立链路按需接入**：

- **① 事件链**（宠物动画/气泡/状态芯片/接入管理卡）——纯新增 + 两端注册表各加一行，**本身即完整可发布形态**；
- **② 统计链**（Token 页/今日汇总/idle 汇报气泡）——可后补；**前提 = 数据源调研有结果**，什么都没有则这部分"不做"而非"后做"。

唯一仍需触碰旧代码的地方全部是**集中扩展点**（enum 加变体后的编译器强制 match 补臂、接 codex 时 7 处预期内拒绝钉翻转——清单见 §1 步骤 5），无散落 if/switch/三元。

## 1. ① 事件链接入（最小接入，5 步）

| # | 类型 | 内容 | 照抄模板 |
|---|---|---|---|
| 1 | 纯新增 | **hook 三件套**：`opencode-plugin/<id>-hook.js`（自包含单文件，仅 import node 内置模块——`include_str!` 安装机制决定的硬约束；POST 协议 + killswitch + 1s 超时 + drain stdin 防护逐脚本复制）+ `<id>-hook.d.ts` + `src/lib/<id>-hook.test.ts` | `opencode-plugin/claude-code-hook.js` 三件套 |
| 2 | 表加一行 | **Rust**：`src-tauri/src/agents.rs` 的 `static AGENTS` 加一个 `AgentSpec`——`id`（**不得为 `"task"`**，有钉）、`short_name`（与前端锁步，见悬置项）、`is_primary: false`（全表恰一主源，有钉）、`integration: Some(IntegrationSpec{ install, uninstall, status_probe, needs_node_probe, install_hint })`（无本地安装物形态填 `None`，§9-6 预留）、`stats`（见 §2；仅事件链填 `StatsSource::None`）、`register_state`（无状态源挂 `register_noop`） | 两个既有 spec |
| 3 | 表加一行 | **前端**：`src/lib/agents.ts` 的 `AGENTS` 加一行——**必须保持「每 agent 一行 `{ id: "..", short: "..", ... }`」字面格式**（Rust 互钉测试按源码匹配，文件头 ⚠️ 注记）；`labelKey`/`descKey` 用 camelCase 键名风格（参照 `token.agent.claudeCode` / `integrations.claudeDesc`，非 `<id>` 直拼）；`hasCost`（统计源是否产费用数据） | 两个既有行 |
| 4 | 纯新增键 | **i18n**：`token.agent.<name>` + `integrations.<name>Desc`，zh/en 成对（键集合一致性测试自动把守漏译）；显示值用品牌规范写法（见 §3） | `token.agent.claudeCode` |
| 5 | 预期内旧用例翻转 | **7 处 "codex" 拒绝钉改接受断言**（P4 接 codex 时同步翻转；接其他 id 则这些钉不动、按需为新 id 增对应拒绝钉——把守未知 id 不落 else）——Rust 4：`http_server.rs` `state_unknown_agent_returns_400`（白名单拒绝列表含 codex）、`lib.rs` `claude_code_idle_never_queries_opencode_db` 末尾未知 agent 臂（codex 零查询零派发）、`agents.rs` `find_unknown_id_returns_none`（`find("codex")` 不得命中）、`integrations/mod.rs` `status_for_unknown_id_is_explicit_error`（`status_for("codex")` 须 Err）；前端 3 文件：`agents.test.ts`（shortOf / badgeOf / descKeyOf 三断言，codex 原名兜底）、`bubble-queue.test.ts`（`bubbleAgentBadge` codex 原名兜底）、`pet-menu.test.ts`（by_agent 行 "codex 5.0k" 短名兜底） | — |

接入管理三套函数（步骤 2 的 `IntegrationSpec` 内容）：install/uninstall/status_probe 指向 `integrations/mod.rs` 的内层函数（tempdir 注入可单测），经 agents.rs 薄适配函数挂表——照现有两套抄；`needs_node_probe`（CC 独有 spawn node）与 `install_hint`（"建议新开会话"类提示）按新 agent 实情填布尔。

**做完 5 步后自动生效**（注册表查表 + 数据驱动，零额外改动）：`POST /state` 白名单放行、idle 分流（`StatsSource::None` 臂 = 跳过 token 汇报）、宠物动画/状态芯片、气泡徽标 `[xx]`（`shortOf` 兜底原名）、右键菜单 by_agent 分布行、Token 页 agent tab（数据来了自动出）、接入管理卡（含 V2-OPEN-ITEMS §20 统计源状态行——新源探测随 `probe_one` 臂自动进卡）、Settings 卡名（`descKeyOf` 查表）。

## 2. ② 统计链接入（可后补；前提 = 数据源调研有结果）

先调研新 agent 本地把 token 用量记在哪、什么格式，三选一定路线：

| 数据源形态 | 路线 | 照抄模板（注意 agent-registry §12：模板随 V2-OPEN-ITEMS §14 实施升级） |
|---|---|---|
| 有 db（SQLite 等价物） | 照 opencode 模式 | `token_stats.rs` opencode 源：`open_checked` 两段式 + **§14 起含 message 表 schema 校验与 message 级归天口径**（`MESSAGE_ROW_FILTER_SQL` / 按 `time_created` 归天）——照抄即自动获得跨天正确口径 |
| 有会话记录文件（JSONL 等） | 照 CC 模式 | `transcript.rs`：解析 + `TranscriptCache` 缓存 + **§14 起 `CcSessionRow.by_day` 按消息时间分桶**（ts 缺失兜底归会话 time_updated）——照抄即跨天正确 |
| 什么都没有 | **不做**（仅事件链，形态已完整） | — |

实施步骤：

| # | 类型 | 内容 |
|---|---|---|
| 6 | 纯新增 | 数据源模块（`<id>_source.rs` 或并入 transcript.rs 形态）——读取/缓存/转 token 行/（可选）idle 汇报构建 |
| 7 | enum 加变体 | `StatsSource` 加变体（如 `CodexDb`）→ 编译器**强制**在全部 exhaustive match 补臂：`lib.rs` `idle_hook_body` 分发、`token_stats.rs` `sources_from_agents` 的 kind 映射 + `SourceKind` enum 本身 + `query_source_rows` / `today_source_stats` / **`probe_one`（§20 探测，三态判据同款两段式——漏了编译不过，不会静默漏）** |
| 8 | P4 预留泛化 | **idle 汇报**：注入式 `query_report` 闭包绑死 opencode（闭包在 `lib.rs`；汇报构建函数为 `token_stats.rs` 的 `build_idle_report_with_today`）——第三个**带统计源**的 agent 需 `AgentSpec` 增 `idle_report: fn` 指针（各源自带汇报构建 + today 段），注入闭包降级为仅测试保留。该成本已计入 P4（agent-registry §6.1 注记） |
| 9 | 缓存注意 | **第二个 transcript 形态源需 per-source cache**（P4-① 移交：`TranscriptCache::plan_refresh` 的 retain 以单目录扫描为前提，共享 cache 会互相驱逐条目；生产路径一个 CcTranscript spec 无此形态，源码注记在位） |
| 10 | 注册接线 | 有状态源在步骤 2 的 `register_state` 挂注册函数（照 `register_cc_cache`：泛型内层 + Wry 薄壳 + mock 测试）；`agents::register_states` 集中调用时序由 order_nails 双断言把守（issue #9 铁律），新源无需另动 lib.rs 接线 |

## 3. 显示层规范（v0.2.3 起，V2-OPEN-ITEMS §21）

- **品牌名指代**用规范大小写：`OpenCode` / `Claude Code`（i18n 值直接写规范形；zh/en 同值——技术名不翻译约定）；
- **技术字面量豁免不改**：CLI 命令（`opencode run`）、数据文件名（`opencode.db`）、payload 字段名（`opencode_auto`）、wire id（`"opencode"`——两链共同主键，逐字一致且不得为 `"task"`）、shortName（`oc`/`cc`——气泡徽标与分布行共用）；
- 状态芯片（Panel.tsx）、Token 页 tab/徽标 title、接入卡名均已查表 `labelKey` 渲染，未知 agent 原名兜底——新 agent 只需 i18n 值写对即全站一致。

## 4. 测试面

**自动把守（无需为新 agent 专写）**：双端互钉（`frontend_agents_table_matches_rust_registry`——两端 id+short 集合一致）、id 唯一且无 `"task"`、全表恰一个 `is_primary`、i18n zh/en 键集合完备、tempdir 接入安装全套。

**需要人工动的**：§1 步骤 5 的 7 处拒绝钉翻转（接 codex）或按需新增（接其他 id）；建议为新源补三态钉（照 `s20_probe_*` 形态：Missing / Ok / "文件在但坏"Failed）与编排钉（照 `p3_three_source_merge_*` 源清单注入形态）。

## 5. 悬置决策项（接入时拍板，agent-registry §9）

| # | 问题 | 备注 |
|---|---|---|
| 1 | `short_name` 分配（codex → "cx"？） | §9-4；zh/en 同值，与 Rust `short_name` 锁步（互钉把守） |
| 2 | 新 agent 是否都进接入管理卡 | §9-6；`AgentSpec.integration: Option` 已兜住"无安装物"形态（`None` = 不出卡） |
| 3 | killswitch 粒度 | §9-7；现状全局单开关（`runtime/hooks-disabled`），涉及 canonical command 兼容承诺，单独决策 |
| 4 | 顺手项 | P4-②：动 MergeAcc 时顺手补「oc Failed × CC Missing → Err」专属钉 + 清理主源 has_data 冗余 |

## 6. checklist（合订）

```
事件链（最小可发布）：
  [ ] opencode-plugin/<id>-hook.js + .d.ts + hook.test.ts（照 claude-code 三件套）
  [ ] agents.rs AGENTS += AgentSpec{ id, short_name, is_primary:false, integration, stats, register_state }
  [ ] agents.ts AGENTS += 一行（每 agent 一行格式，labelKey/descKey camelCase，hasCost）
  [ ] i18n: token.agent.<name> / integrations.<name>Desc（zh/en 成对，品牌规范写法）
  [ ] 例程模板行（Part B，2026-08-30 起）：有 headless run CLI 的 agent 在
      src/lib/routine-templates.ts 的 ROUTINE_TEMPLATES += 一行（agentId /
      matches 前缀 / build / flags 声明）+ i18n tasks.tpl.<camel>.* 键对
      （hint 必需，flag 按 i18nKey/i18nKey+"Hint"）；无 run CLI 不加，UI 不受影响
  [ ] "codex" 拒绝钉翻转（Rust 4 + 前端 3 文件，清单见 §1 步骤 5；接其他 id 不动、按需新增）
  [ ] 验证：cargo test / npm test / tsc / build 全绿 + dev 冒烟（白名单、卡、徽标、芯片）

统计链（数据源调研有结果后）：
  [ ] 数据源模块（db 形态含 message 级归天 / transcript 形态含 by_day 分桶）
  [ ] StatsSource 加变体 → 编译器强制补臂（idle 分流 / sources_from_agents / SourceKind /
      query_source_rows / today_source_stats / probe_one）
  [ ] idle_report fn 指针泛化（P4 预留；仅事件链 agent 不需要）
  [ ] 第二个 transcript 形态源 → per-source cache（P4-①）
  [ ] register_state 挂缓存注册（照 register_cc_cache；时序由 order_nails 把守）
  [ ] 新源三态钉 + 编排钉（照 s20_probe_* / p3_three_source_*）
```

——发现清单与现实不符时以代码为准并回改本档（本档锚点是 v0.2.3，行号不钉、按符号名定位）。
