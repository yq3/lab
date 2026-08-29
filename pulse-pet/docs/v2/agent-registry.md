# PulsePet 多 agent 接入与注册表收敛设计（agent-registry）

> 状态：**方案定稿、已立项（2026-08-28 用户拍板三项决策，见 §8.0）——应用户指示暂不实施，启动待指令**
> 来源：`V2-OPEN-ITEMS.md` §十三（2026-08-28 第三 agent 接入成本审计预研）+ 同日独立源码复核（基线 HEAD `e7d58ed`，v0.2.2）+ 同日**实证对照**（v2 接入第二家 Claude Code 的 M1/M5/M6 commit diff 校验清单，见 §10）+ 同日**方案讨论定稿**（总体方案 → P3/degraded 与数据源概念澄清 → 双链独立接入确认 → 三项决策 → degraded 边界场景发现与口径 A′，见 §10）+ 同日**评审轮**（reviewer subagent：NEEDS_CHANGES，2 P1 + 8 P2 + 5 P3 + 4 澄清项 → 用户裁定按评审意见修改，当日全部落档，原文收录 §11）+ 同日**测试覆盖核定**（既有测试网覆盖面核实 + 待补钉清单，§8.7）。用户判断：**以后可能对接很多个 agent**——收敛价值从"可选重构"升级为"多 agent 路线上的结构性前置"。
> 术语约定：本文"agent"指被 PulsePet 监测的 coding agent 宿主（opencode / Claude Code / 未来的 codex 等），与 PulsePet 开发流程中的 subagent（coder/tester 等）无关。

---

## 1. 结论

接入一个新 agent（以 codex 为例）**不是纯新增——老代码必改 14 处**（§4：12 处静态审计 + 2 处实证对照补充，其中 1 处为软性文档联动）。分层抽象总体良好（状态机 / token 页 / 气泡链路均数据驱动零改动），但 agent 注册点**散落各层、各持一份微型注册表互不引用**：

- Rust 3 份：`AGENT_WHITELIST`（http_server）/ `ID_*` 常量（integrations）/ 双源编排硬编码（token_stats）；
- TS 1 份：`AGENT_*` 常量 + switch（token-stats.ts）及 TokenStats / Settings 内散点三元；
- i18n 键一组（zh/en 成对，键集合一致性测试强制同步）。

其中 2 处是**静默错误级**（新 agent 被错误当作 claude-code / oc 处理，功能"看起来能跑"但数据是错的，见 §5）。多 agent 已定为长期方向，registry 收敛**已立项**：方案见 §6（定稿）、实施计划见 §8（文件级，未启动）。收敛后新增 agent 回归纯新增形态：**一个 hook 脚本 + 一套函数 + 一行注册 + i18n 键**；新 agent 接入的"事件链 / 统计链"双链切分方法论见 §7。

## 2. 零改动面（已数据驱动，2026-08-28 复核确认）

| 面 | 依据（行号 = HEAD e7d58ed） |
|---|---|
| 状态机 `session_state.rs` | 复合键 `agent:sessionId`，agent 纯字符串透传，优先级合并只看 kind |
| Token 页 agent tab / 模型 chips | `token-chart.ts:189` `agentsWithRows` 从 rows 动态导出——新 agent 有数据自动出 tab |
| 气泡 `[徽标]` / 右键菜单 by_agent 分布行 | `bubble-queue.ts:64`、`pet-menu.ts:66` 共用 `agentShortName`，未知 agent **原名兜底**（丑不算错） |
| `POST /state` 契约 | `http_server.rs:287` 只做白名单字符串校验，body 协议 agent 无关 |
| 工具级气泡（detail） | detail 协议 agent 无关，新插件发 detail 即得 |
| 例程功能 | 绑定 opencode CLI，与第三 agent 正交 |
| `task` 伪 agent | `action_exec.rs` 的 task 与 HTTP agent 不冲突；**唯一约束：新 agent id 不能叫 `"task"`** |
| 前端 `AgentAdapter`（`src/lib/agent-adapter.ts` + `adapters/`） | **装饰性抽象**：主链路无人 import（仅各 adapter 自测试引用），新增 adapter 无运行时效果——可写可不写（`iconSet` 注释里甚至已提及 "codex"） |
| `petStore.displayAgent` | 纯字符串存取（默认 "opencode" 仅初值），未知 agent 无影响 |
| 面板状态芯片（实证补充） | `Panel.tsx:79` 渲染原始 agent id（仅 `task` 特例走 i18n `panel.agentTask`）——原名直显，新 agent 自动显示 "codex"，与既有行为一致 |
| Rust 汇报文案模板（实证澄清） | `i18n.rs:114` `token_report` / `:124` `token_report_today`——F1 收敛后已 **agent 无关**（`cc_token_report` 已并入）；`intg_*` 接入诊断文案本就通用。新 agent 的 Rust 侧气泡/接入文案**零改动**，idle 汇报函数直接复用现有模板 |

## 3. 纯新增面（照现有模式写新文件/函数，不动老代码）

| # | 内容 | 照抄模板 |
|---|---|---|
| 1 | 事件源 hook 脚本（POST 协议现成，`agent:"<id>"`） | `opencode-plugin/claude-code-hook.js` |
| 2 | 统计提取模块（codex 的本地数据源读取/缓存） | `transcript.rs`（`cc_projects_dir` :63） |
| 3 | 行转换 + idle 汇报 | `cc_to_token_row`（token_stats.rs:659）/ `build_cc_idle_report`（:894） |
| 4 | 接入管理第三套 install/uninstall/config_state/canonical | `integrations/mod.rs` 现有两套（含 `BUNDLED_*_HOOK` 内嵌脚本模式 :43-44） |

**hook 脚本契约（实证提炼，M1）**：每个 hook = **自包含单文件**（仅 import node 内置模块）——这是安装机制（`include_str!` 单文件拷贝）决定的硬约束；POST 协议 / killswitch（`runtime/hooks-disabled`，`runtime.rs:49`）/ 1s 超时 / drain stdin 三重防护逻辑**逐脚本复制**而非共享模块。配套**三件套**：脚本 + `.d.ts` 类型声明 + `src/lib/<name>-hook.test.ts`（claude-code-hook 三件套 HEAD 实测：382 行脚本 / 72 行 d.ts / 397 行测试·25 用例；M1 时点为 231/46/281+79——评审 P2-7 校正，量化参照以现行为准）。

**注意**：codex 的本地数据形态（有无 opencode.db 等价物 / transcript 文件）**尚未调研**——这是"纯新增面"里唯一的前置未知项，见 §9-5 与 §7.1。

## 4. 必改老代码清单（14 处 = 12 处静态审计 + 2 处实证对照补充；行号 2026-08-28 HEAD 复核校准）

| # | 层 | 位置（现状） | 新 agent 不改会怎样 |
|---|---|---|---|
| 1 | Rust 事件入口 | `http_server.rs:41` `AGENT_WHITELIST: [&str; 2]`（:287 消费；注释已注明"新增 agent 时同步"） | 事件被直接拒绝——**第一道门** |
| 2 | Rust idle 分流 | `lib.rs:109` `idle_hook_body` match：`"opencode"`（:110，臂内 :124/:126 字面量）/ `"claude-code"`（:129）两臂 + `make_idle_hook` 闭包内 :202/:210 字面量 | 落 `other` 分支仅记日志 skip，无 token 汇报 / 无 success 注入 |
| 3 | Rust 统计编排 | `token_stats.rs` `query_stats_dual`（:782）/ `today_stats_dual`（:830）+ 命令 `token_stats_query`（:944）/ `token_stats_today`（:973）——双源（`opencode_data_dir()` :161 + CC transcript 缓存）**写死**；degraded 语义只建模「opencode 错 × CC 有数据」（:107-143 结构体 + :776-781 容错矩阵） | 新源用量不进任何统计；degraded 需重推 **N 源容错**——**唯一需要设计而非机械扩的一处** |
| 4 | Rust doctor | `integrations/mod.rs:876` `status_for`：`if id == ID_OPENCODE`（:879）… **else 一律按 CC 探测**（:945 起：读 `~/.claude/settings.json` + spawn node） | 新 agent **错误落进 CC 探测分支**，报基于错误路径的状态——**静默错误 ①** |
| 5 | Rust doctor | `mod.rs:1022-1025` `integrations_status` 硬编码 `vec![两行]` | 设置页只显示两张接入卡 |
| 6 | Rust 接入命令 | `integrations_install`（:1034，id 守卫 :1038 + match 二元分发 :1045-1048 + CC 独有安装提示 :1057-1061）；`integrations_uninstall`（:1067，守卫 :1071 + match :1078-1081 + 提示 :1090-1093）。无 trait 无注册表 | 安装/卸载直接报「未知接入 id」；若新 agent 也需"重开会话"类提示需再加分支 |
| 7 | 前端短名 | `token-stats.ts:45-56` `agentShortName` switch（oc/cc/task，:37-38 常量与 Rust 注释互钉） | 徽标/分布行显示全名（原名兜底，丑不算错） |
| 8 | 前端徽标 | `TokenStats.tsx:83-87` `agentBadgeOf`：三元 **else 一律 → "oc"** | 新 agent 会话行被**错标 oc**——**静默错误 ②（全清单最阴险）** |
| 9 | 前端展示规则 | `agentLabel`（:90-96，未知 agent 原名兜底）；cost「—」per-agent 规则会话行 `:485` + 详情行 `:520`（均 `=== AGENT_CLAUDE_CODE ? "—" : …`） | 新 agent 若无费用数据，cost 列显示 `$0.00` 而非「—」（错值，非错标） |
| 10 | 前端接入 UI | `Settings.tsx:565` nameKey 三元（else → claudeDesc，第三卡显示错名「Claude Code」）；`integrations.ts:33` `IntegrationId` 联合类型不含新 id | 类型层面即不含；UI 错名 |
| 11 | i18n | `token.agent.<id>`（zh :73-76 / en :433-435）、`integrations.<id>Desc`（zh :357-358 / en :712-713）、`token.degraded` 措辞 N 源化重写——zh/en 成对（键集合一致性测试强制）；`costOpencodeOnly` 已随 §十二 F3 清退（较 §13.3 原清单少一处） | 缺键测试红；degraded 文案语义不再准确 |
| 12 | 测试面 | `http_server.rs:968` 白名单遍历用例、`lib.rs:570-722` idle 分流单测、`token_stats.rs:1742-2040` 双源/degraded/by_agent 用例、`token-chart.test.ts:202-212`、`i18n.test.ts:167`（键存在性） | 改 #1/#2/#3 后必红，需同步 |
| 13 | Rust 运行时接线（**实证补充**） | `lib.rs:295` 创建数据缓存（照 `TranscriptCache` 模式）/ `:311` `make_idle_hook(&state, app, &cc_cache, &notifier)` **签名扩展**（参数随家数增长）/ `:359` `app.manage(<新缓存>)` + 配套钉子测试（`lib.rs:748` TC-M5-02-1：manage 必须先于窗口创建，issue #9 铁律）——M5 实证 lib.rs 动了 152 行，远超 idle 分流本身 | 新数据源建了却接不进事件链（无缓存注入）；漏 manage 违反 #9 铁律，Windows 上有命令期 state() panic/闪退风险 |
| 14 | 文档联动（**实证补充，软性**） | `opencode-plugin/README.md`（killswitch/脚本说明——M1 实证同步更新过）、AGENTS.md / README / V2 文档口径 | 文档漂移（非功能缺陷） |

## 5. 风险定级：两处"静默错误"

机械扩 §4 清单时最容易漏的是**不显式报错、而是把新 agent 静默当作既有 agent 处理**的两处：

- **#4（`status_for` else 分支）**：新 id 落进 CC 探测——读错误的配置路径、可能 spawn node，产出一张"错误但看起来合理"的接入卡；
- **#8（`agentBadgeOf` else→oc）**：新 agent 会话行错标 oc——数据层正确、展示层错标，且其余短名消费点（#7）都是"原名兜底"的良性形态，唯独此处是三元无兜底。

若选择"直接照清单硬改"路线，实施时这两处必须列为 P1 级验证点（新 agent id 在 doctor 与徽标两处均不得落 else）；收敛路线则由 §6.2 的查表 + 显式兜底策略根治，并以"未知 id"钉子测试把守。

## 6. registry 收敛方案（2026-08-28 定稿；实施未启动）

一句话定位：把散落在 Rust 3 份 + 前端 1 份 + i18n 键里的 agent 微型注册表，收敛为**两端各一份单一事实源注册表**，14 处硬编码分支全部变查表——**纯重构、行为零变化**（P3 的 N 源化除外，其语义扩展见 §6.4），为"每接一家 = 一个脚本 + 一套函数 + 一行注册"铺路。

### 6.0 设计原则（四条）

1. **行为零变化**：重构前后 `integrations_status` / `token_stats_query` / 气泡徽标 / doctor 输出逐字节一致——现有 346+ cargo / 442 npm 钉子就是回归网（npm 基线 442 为评审轮两次实测，此前记 439 系批次时点数——评审 P2-6），另加"未知 id 不落 else"新钉子（消 #4/#8 两处静默错误的温床）。
2. **单一事实源**：一个 agent 的全部属性（id / 短名 / 安装函数 / 探测函数 / 统计源 / 文案键）只在一处定义。
3. **贴现有代码风格**：静态数组 + 函数指针 + enum 分发——不上 trait object / 泛型 / 运行时注册（与 crate 现有无泛型静态风格一致，`#[cfg(test)]` 路径注入测试模式全部保留不动）。
4. **分阶段可回滚**：P1（Rust）/ P2（前端）/ P3（N 源化）各自独立提交、独立验证、可单独放弃。

### 6.1 Rust 侧：`agents.rs` + `AgentSpec` 函数指针表

```rust
pub struct AgentSpec {
    pub id: &'static str,             // "opencode" / "claude-code" / "codex" / …（唯一事实源）
    pub short_name: &'static str,     // "oc" / "cc" / …（与前端锁步，§6.3 互钉）
    pub integration: Option<IntegrationSpec>,  // None = 无本地安装物形态（§9-6）
    pub stats: StatsSource,           // enum：OpenencodeDb / CcTranscript / None
}
pub struct IntegrationSpec {
    pub install:  fn(...) -> Result<..>,        // 直接指向现有 install_opencode / install_cc 内层函数
    pub uninstall: fn(...) -> Result<..>,       // （签名不变，tempdir 注入单测全部免改）
    pub status_probe: fn(...) -> IntegrationStatus,  // 拆自 status_for 的 if/else 两分支
    pub needs_node_probe: bool,   // CC 独有 spawn node → 提为字段
    pub install_hint: bool,       // 「建议新开会话」类提示 → 提为字段
}
pub static AGENTS: &[AgentSpec] = &[AgentSpec::opencode(), AgentSpec::claude_code()];
pub fn find(id: &str) -> Option<&'static AgentSpec>;
```

三个关键设计决策：

- **函数指针而非 trait**（2026-08-28 已拍板）：零运行时开销、无泛型/生命周期负担，现有内层函数直接挂表；P3 的统计源用 enum dispatch（同样无 trait object）。
- **源生命周期自注册**（吸收 #13 接线组）：spec 增加 `register_state: fn(&tauri::AppHandle)`——lib.rs setup 内窗口创建循环之前一行 `agents::register_states(&app)` 消掉逐个 `manage`；manage-before-windows 铁律（issue #9）由现有钉子继续把守（断言改盯 register_states 位置）。各源后台线程句柄改从 `app.state::<Arc<Mutex<_>>>()` 取（integrations `activity_of` 同款模式）。
- **idle 分流查表**：`idle_hook_body` 的 match 两臂 → `find(agent)` + 按 `spec.stats` 分发到各源 dispatch（opencode → SQL 汇报、cc → 后台线程 transcript）；**注入式签名 P1 冻结不变**（`state / emit_bubble / query_report / cc_dispatch / agent / session_id`，`lib.rs:570-722` 闭包注入单测免改，其中已有 "codex" 未知分支防御性钉子可复用）；臂内与闭包内 `"opencode"`/`"claude-code"` 字面量 → `spec.id`；`make_idle_hook` 参数不再随家数增长。
- **第 3+ 源 idle 汇报落点（评审 P2-2 补答）**：注入的 `query_report` 闭包现绑死 opencode（`lib.rs:160-168` `build_idle_report_with_today`），签名冻结下第三个**带统计源**的 agent 的汇报路径需第二波泛化——处置：P4 接入时 `AgentSpec` 增 `idle_report: fn` 指针（各源自带汇报构建与 today 段），注入闭包降级为仅测试保留；该成本计入 P4，不阻塞 P1-P3（当前两家各走既有臂/闭包，行为零变化）。

### 6.2 前端侧：`src/lib/agents.ts` 单一 `AGENTS` 表

```ts
const AGENTS = [
  { id: "opencode",    short: "oc", labelKey: "token.agent.opencode",   descKey: "integrations.opencodeDesc", hasCost: true  },
  { id: "claude-code", short: "cc", labelKey: "token.agent.claudeCode", descKey: "integrations.claudeDesc",   hasCost: false },
  // { id: "codex", ... },
] as const;
```

配套 helpers：`shortOf(id)`（保留 `task` 伪 agent 特例 + 原名兜底）、`badgeOf(id)`、`hasCostOf(id)`、`descKeyOf(id)`；`IntegrationId` 联合类型改由表派生。消费点收敛映射：`agentShortName` switch → `shortOf`；`agentBadgeOf` else→oc → **badgeOf 查表 + 显式兜底（未知 id 显原名）**，消静默错误 ②；`agentLabel` → `t(labelKey)` + 兜底；Settings nameKey 三元 → `descKeyOf`；cost 两处「—」→ `!hasCostOf(agent)`。

### 6.3 双端一致性互钉

Rust/TS 注册表无法编译期互验——沿用 v0.2.1 R4 的 `include_str!` 源码断言先例：Rust 侧 agents.rs 测试 `include_str!("../../src/lib/agents.ts")`（相对 `src-tauri/src/agents.rs` 两级上溯到 pulse-pet 根；评审 P2-3 校正——原写 `../../../` 会多上一级指到 lab/ 仓库根），断言两端 id + short_name 集合逐项一致——防两端漂移（这正是今天 4 份注册表各自腐烂的根因）。随 P2 落地（前端表建成才有钉的对象）。

### 6.4 degraded / 报错语义——已定口径 A′（2026-08-28 两轮拍板）

**现状（含缺陷）**：degraded 触发 = 「opencode 源查询 Err × CC 有数据」，而 **Err 不区分"未安装"与"故障"**——CC-only 用户（未装 opencode，无 `opencode.db`）走 `detect_db_path` 返回 None（token_stats.rs:175）→ `no-database` Err → `query_stats_dual` Err 臂（:815-824）返回 CC-only + `degraded=Some` → Token 页**常驻横幅**「opencode 源不可用：仅显示 Claude Code 数据」（`TokenStats.tsx:334-336` / i18n `token.degraded`）——对未装 opencode 的用户是永久性误导。伴生边角：双源全缺（两 agent 都没用过）→ `no-database` 硬错误态。根因：M3/M5 时代"人人有 opencode"的主源假设（2026-08-28 用户提问实测场景发现）。

**口径 A（前身，2026-08-28 首轮拍板）**：仅主源（opencode）查询错误才降级横幅、非主源错误静默、**不区分"未安装"与"故障"**——A′ 在此基础上三态化并收窄横幅触发（评审 P3-3：定稿文档自含定义）。

**口径 A′（用户裁定，A 的三态收窄版）**——每个统计源查询后归入三态：

| 源状态 | 含义 | 例子 |
|---|---|---|
| **Ok**（可含 0 行） | 查询成功 | db 在、正常返回（哪怕没用量） |
| **Missing** | 库/目录不存在 = 该 agent 未安装未使用 | 无 `opencode.db` / 无 `~/.claude/projects` |
| **Failed** | 源**在但坏了** | schema 变更（opencode 升级）、db 文件在但打不开（损坏/WAL 缺失/权限）；CC transcript 坏行现状静默跳过、无错误通道——其 Failed 态 P3 不探测（见下方 per-source 判据，评审 P2-1 处置） |

判定规则（四条）：

1. **展示**：所有 Ok 源合并；只要有任一源有数据 → 正常展示，**绝不报错**；
2. **硬报错**：仅当**全部源无数据**（全 Missing/Failed，无一源 Ok）→ 报错；文案 N 源中性化（`token.error.noDatabase`「未找到 opencode 数据库」→「未检测到任何 agent 用量数据」类）；
3. **degraded 横幅（收窄）**：仅主源 **Failed**（在但坏）× 其余有数据 → 横幅；**Missing 不触发**（CC-only 用户从此干净）；非主源 Failed 静默（口径 A 原则不变）；`token.degraded` 文案随 Missing 剔除微调；
4. **空态保留**：有源 Ok 但 0 行（装了没用过）→「暂无数据」，非报错。

差异对照（vs 现状）：

| 场景 | 现状 | 口径 A′ |
|---|---|---|
| CC-only（oc Missing × CC 有数据） | ⚠️ 常驻横幅 | ✅ 静默正常（本轮诉求） |
| oc Missing × CC **Missing**（无目录） | Err「未找到 opencode 数据库」 | Err，文案中性化 |
| oc **Failed**（在但坏）× CC 有数据 | ⚠️ 横幅 | ⚠️ 横幅**保留**（2026-08-28 用户确认） |
| oc Failed × CC **Missing** | Err（schema/query 错） | Err（同） |
| oc Missing × CC **Ok 但 0 行**（目录在、无 transcript） | Err（现状 `cc_has_data` 只看行数，CC Ok-0行与 CC Missing 同走 Err 透传） | ✅ **空态「暂无数据」——行为变更（评审 P1-1 补行）** |
| oc Failed × CC **Ok 但 0 行** | Err | ✅ **空态——行为变更（评审 P1-1 补行；非横幅：CC 无数据不满足横幅触发条件）** |
| 双源在但都 0 行 | 空态「暂无数据」 | 空态（不变） |

> 行为变更共三处（评审 P1-1 划界）：CC-only 静默化 + 两组 Ok-0行 从 Err 改空态——均源于"有源 Ok 就不算全缺"的判定规则 2/4；`m5_degraded_both_missing_error_passthrough`（:1787，构造 = 无 db × CC 无目录）落在第二行，**语义不变仍 Err**。

横幅保留 Failed 的理由：装着的 agent 用量凭空从图表消失，若完全静默会被用户当成丢数据 bug——静默掩盖 Failed 等于把排障代价转嫁给用户；Missing（没装）与 Failed（装了但坏）必须分开。口径 B（`Vec<SourceError>` 逐源列错）维持未选留档。

实现判据（评审 P1-2 修正为**按文件存在性、与错误码解耦**——代码里"db 文件在但打不开（损坏/WAL 缺失/权限）"同样报 `no-database` 码（`token_stats.rs:241-247`），若按错误码判会把这个典型 Failed 场景误静默成 Missing，恰好杀掉上方拍板保留的横幅）：

- **opencode 源**：`detect_db_path` 返回 None = **Missing**；返回 Some × 后续任何错误（open 失败 / schema-mismatch / query）= **Failed**；无错 = Ok；
- **CC 源（评审 P2-1 处置）**：目录不存在 = **Missing**；目录在 = **Ok**（坏行静默跳过是 `transcript.rs:174-176` 既定健壮行为，P3 不新建解析失败探测——Failed 态对 CC 当前为空集，未来需要再加坏行计数）；**第 N 源**照此模式各自定义"存在性判据"；
- 两判据均无需跨子系统读接入管理状态。

### 6.5 吸收映射（14 处 → 2 张表）

| 现状必改点 | 收敛后 |
|---|---|
| #1 白名单 / #5 status vec / #6 三命令 match / #4 status_for if-else | 全部 `AGENTS` 查表遍历 |
| #2 idle 分流 + #13 lib.rs 接线组 | spec.stats 分发 + register_states 循环 |
| #3 双源编排 | 遍历 AGENTS 逐源查询合并（P3，degraded/报错口径 A′） |
| #7/#8/#9/#10 前端散点 | 前端 AGENTS 查表/派生 |
| #11 i18n 键 | 沿用现有 camelCase 键名风格，新键按同风格添加（如 `token.agent.codex` / `integrations.codexDesc`），注册表 labelKey/descKey 引用键名（评审 P3-2：现有键为 `token.agent.claudeCode` / `integrations.claudeDesc`，非 `<id>` 直拼，不做键名重排） |
| #12 测试面 | 既有用例语义不变改写数据，另加未知 id 钉子 |
| #14 文档联动 | AGENTS 表即文档锚点 |

### 6.6 收敛后新增 agent 的形态（目标态）

```
opencode-plugin/codex-hook.js          # 事件脚本（照 claude-code-hook 抄，含 .d.ts + hook 测试三件套）
src-tauri/src/codex_source.rs          # 统计提取（transcript.rs 等价物，若有数据源）
static AGENTS += AgentSpec{ id: "codex", ... }   # 一行注册
i18n: token.agent.codex / integrations.codexDesc（zh/en 成对）
```

——回归纯新增：不触碰任何既有分支/switch/三元。（评审 P3-4 注记：现有两处 "codex" **拒绝钉子**——`http_server.rs:954` 白名单拒绝用例列表、`lib.rs:599-613` 未知 agent 零查询断言——P4 真接 codex 时需同步改为接受断言；属预期内测试面调整，非分支改动。）

### 6.7 明确不做（防蔓延）

- 不激活/不删除前端 `AgentAdapter` 装饰性抽象（维持现状，加注释标注即可）
- 不动 HTTP 协议、DB schema、气泡/菜单/状态机（已数据驱动）
- 不顺手接 codex（P4 另立项，先拿真实第三家验证"一行注册"承诺）
- killswitch 分粒度（§9-7）**本轮不动**——涉及已安装 canonical command 的兼容承诺，单独决策
- 不引入任何新依赖

## 7. 新 agent 接入方法论：双链切分（2026-08-28 讨论定稿）

新 agent 的接入可分两部分**独立实施**：①事件链路（最小接入）与②统计链路（可后补）。"仅事件链"就是一个完整可发布形态。

### 7.1 两条链路与"数据源"概念

PulsePet 对每个 agent 有两条独立链路，**"数据源"是统计链路的起点**——指该 agent 把 token 用量记录在哪里、什么格式：

```
链路 ① 事件链（实时状态，走 HTTP）——与"数据源"无关
  hook 脚本 ──POST /state──▶ 状态机 ──▶ 宠物动画/气泡/状态芯片
  （只告诉 PulsePet "它正在编辑 X / 跑命令 X"，不留历史）

链路 ② 统计链（token 用量，走本地文件）——起点即"数据源"
  agent 本地记录 ──PulsePet 读取──▶ Token 页/今日汇总/会话结束汇报气泡
```

| agent | 数据源形态 | PulsePet 读法 |
|---|---|---|
| opencode | 自带 SQLite 库 `opencode.db`（`~/.local/share/opencode/`） | 直接 SQL 查询（`token_stats.rs:161` `opencode_data_dir()`） |
| claude-code | 无 db，仅会话记录 JSONL（`~/.claude/projects/`） | transcript 解析 + 内存缓存（`transcript.rs`），再转 token 行（`cc_to_token_row`） |
| codex | **未知**（§9-5 调研项） | 有 db → 照 opencode 模式；有 transcript → 照 CC 模式；**什么都没有 → 只能进链路①，Token 页永远没有它的数据** |

### 7.2 两部分的构成与 3 处交接点

| | ① 事件链路接入（最小接入） | ② 统计链路接入（可后补） |
|---|---|---|
| 功能 | 宠物动画跟随、状态芯片、工具级气泡、接入管理卡 | Token 页 tab/行、今日汇总、会话结束汇报气泡 |
| 新增 | hook 三件套（§3 契约） | 数据源模块（transcript.rs 等价物） |
| 必改点（§4 编号） | #1、#4/#5/#6、#10、#11（integrations 键）；**#2 无需改**——非收敛路径下新 agent 的 idle 落 `other` 分支无害（交接点 1），收敛路径下注册后自动覆盖（评审 P3-1） | #3（即 P3）、#8/#9、#11（token.agent 键）、#13、#7 |
| 前提 | 无 | 数据源调研有结果——**没有数据源 = 这部分"不做"而非"后做"** |

仅事件链下的两个可感知行为差异（无害但需知情）：没有"本次会话消耗 token X"汇报气泡；没有 success 状态注入（会话结束宠物从 working 直接回 idle，少一次成功神态）。

**3 处交接点**（独立 ≠ 零耦合）：

1. **idle 事件是两链交接点**（`lib.rs:109`）：事件链的 idle 事件触发统计链的汇报查询。统计链未接时新 agent 的 idle 自动落 `other` 分支跳过（记一条日志）——无害。
2. **`agentShortName`（#7）两链共用**：气泡徽标（事件链）与菜单今日分布行（统计链）同走一个函数——谁先接谁顺手扩展（不扩展则显示原名，兜底良性）。
3. **agent id 字符串是两链共同主键**：白名单（事件链门禁）与统计行 `agent` 字段必须逐字一致，且不能叫 `"task"`——两链唯一必须锁死的约定。

### 7.3 接入顺序（与收敛的配合）

```
P1/P2 收敛（先行——两链的必改点大部分被注册表吸收）
   ├─▶ ① 事件链接入（小：脚本三件套 + 一行注册 + integrations i18n 键）
   └─▶ codex 数据源调研 ──有结果──▶ P3（N 源 + degraded 口径 A′）+ ② 统计链接入
                        └─无数据源──▶ 到此为止，形态已完整
```

最大好处：**统计链的调研不确定性与 P3 的 degraded 决策都不阻塞事件链上线**——codex 能不能拿到 token 数据慢慢查，宠物先动起来。

## 8. 实施计划（文件级，2026-08-28 定稿；**未启动——应用户指示暂不实施**）

### 8.0 决策记录（2026-08-28 用户拍板）

| # | 决策项 | 决定 |
|---|---|---|
| 1 | 立项与顺序 | **立项，按 P1 → P2 → P3**，每阶段独立实施/验证/可回滚 |
| 2 | degraded / 报错口径 | **A′（三态收窄版，同日二轮裁定）**：源分 Ok / Missing / Failed——报错仅当全部源无数据；横幅仅主源 Failed × 其余有数据（保留）；Missing 静默（§6.4） |
| 3 | 分发形态 | **函数指针表**（不上 trait object；统计源 enum dispatch，§6.1） |
| 附 | 本轮明确不动 | killswitch 粒度（§9-7 悬置）、codex 接入本身（P4 另立项，数据源调研可并行启动） |
| 附 | 实施状态 | 方案落档即止，**启动实施待用户后续指令** |

### 8.1 P1：Rust `agents.rs` 注册表（行为零变化，~400 行净变动，多为删分支）

**新增 `src-tauri/src/agents.rs`**：`AgentSpec` / `IntegrationSpec` / `StatsSource` + `static AGENTS`（两家）+ `find(id)`（§6.1 结构）。自测：find 已知 id 命中、**未知 id → None**（"不落 else"基础钉子）、AGENTS id 唯一、无 id 叫 `"task"`。

| 改造点 | 改前 → 改后 |
|---|---|
| `http_server.rs:41` | 删 `AGENT_WHITELIST` 常量；`:287` 校验改 `agents::find(..).is_some()`；`:968` 测试遍历改 `agents::AGENTS` |
| `lib.rs:109` idle 分流 | match 两臂 → `find(agent)` + 按 `spec.stats` 分发；臂内 :124/:126 字面量 → `spec.id`；**签名不变**（:570-722 闭包注入测试免改） |
| `lib.rs:202/:210` | cc_dispatch 闭包内字面量 → spec.id |
| `lib.rs:295/:311/:359` 接线组（#13） | TranscriptCache 创建+manage 收敛为 `agents::register_states(&app)`（窗口创建循环之前）；cc_dispatch 改从 `app.state::<Arc<Mutex<_>>>()` 取句柄；`:730-748` 时序钉子改盯 register_states 位置（issue #9 铁律把守不变） |
| `integrations/mod.rs:63-64` | `ID_*` 常量迁 agents.rs（AgentSpec.id 成唯一事实源，mod.rs 引用处跟随） |
| `integrations/mod.rs:876` | status_for if/else → 拆 `status_opencode`/`status_cc` 两函数，经 `spec.integration.status_probe` 指针分发；node 探测由 `needs_node_probe` 控制 |
| `integrations/mod.rs:1022-1025` | vec![两行] → 遍历 AGENTS |
| `integrations/mod.rs:1038/:1071/:1045/:1078` | id 守卫 → `find` + 未知 id 明确 Err；match 分发 → `spec.integration.install/uninstall` 指针；`:1057/:1090` CC 提示 → `install_hint` 字段 |

tempdir 注入单测（install_cc / install_opencode 内层函数）签名不动、全部免改。**新钉子**：status_for / install 传未知 id 必须报错而非落 CC 探测（消静默错误 ① 的回归钉）。

验证：`cargo test` 全绿（基线 346 passed + 3 ignored）+ `cargo build` 零警告 + dev 冒烟（设置页两张接入卡 doctor / 安装 / 卸载与改前一致）。测试策略 = **既有网回归**（白名单双向 / idle 未知分支 / 双臂闭包注入 / tempdir 全套，覆盖核定见 §8.7.1）+ **新钉 5 枚**（agents.rs 自测 ×3、status_for 未知 id 报错、时序钉子改写，清单见 §8.7.2）。

> **实施记录（P1，2026-08-29，task-pulsepet-v2-registry R1）**：已实施。cargo 基线实测 346 passed + 3 ignored → 实施后 **351 passed + 3 ignored**（新钉 5 枚：agents.rs 自测 ×3 + register_states 功能钉〔mock_app 驱动 + 指针表身份断言〕+ status_for 未知 id 明确 Err；时序钉子为改写不计增量）；`cargo build` 零警告。行号基线 e7d58ed → 实施 HEAD b8cf83d，§8.1 表格点位行号漂移 +0~+2，均按源码核对命中。实施微调三处：① install/uninstall 函数指针经 agents.rs 薄适配函数挂表（`install_opencode` 返回 `PathBuf`、`install_cc` 双路径注入，签名异构无法直接挂表；**内层函数与 tempdir 注入单测零改动**）；② node 探测耗时日志自 status_cc 内移至查表分发层 `probe_status`（原 CC 状态行 "(probe {}ms)" 片段改为独立 plog 行，诊断信息保留；IntegrationStatus 输出逐字节一致）；③ `register_states` 置于 `http_server::start` **之前**（强于"窗口创建前"下限——cc_dispatch 改经 `app.state` 取句柄后，server 先起会留 manage 前派发的 panic 窗口，#9 同源；时序钉子相应加严为双断言）。附带核定：遗留事项 A（reconcile manual SQL 旧口径）经查**已在 M6 R1（8973813）顺手修复**（现行 SQL 即 `GROUP BY day,agent,model_id` + mock 过滤），无需重复修改。

### 8.2 P2：前端 `agents.ts` 注册表（~150 行）

**新增 `src/lib/agents.ts`**：`AGENTS` 表 + helpers（`shortOf` / `badgeOf` / `hasCostOf` / `descKeyOf`）+ `IntegrationId` 派生类型（§6.2）。

| 改造点 | 改前 → 改后 |
|---|---|
| `token-stats.ts:37-38/:45-56` | 删 `AGENT_*` 常量与 switch，`agentShortName` 迁移为 `shortOf`；import 点全部改引用 agents.ts（已盘点仅 4 文件：TokenStats.tsx / token-stats.ts / token-stats.test.ts / token-chart.test.ts:9） |
| `TokenStats.tsx:83-87` | agentBadgeOf → `badgeOf` 查表 + **未知 id 显原名**（消静默错误 ②），加 "codex"→ 非 "oc" 钉子 |
| `TokenStats.tsx:90-96/:485/:520` | agentLabel → `t(labelKey)` + 兜底；cost 两处 → `!hasCostOf(agent)` |
| `Settings.tsx:565` | nameKey 三元 → `descKeyOf(s.id)` |
| 双端互钉（§6.3） | agents.rs 测试 `include_str!` 断言两端 id + short 集合一致（R4 先例风格） |

验证：`npm test`（基线 442，评审轮实测校正——P2-6）/ `npx tsc --noEmit` / `npm run build` 全绿。测试策略 = **既有网回归**（短名兜底 `bubble-queue.test.ts:330` / agentsWithRows / i18n 键完备性）+ **新钉 2 枚**（badgeOf 未知 id 显原名、include_str 互钉；`IntegrationId` 派生类型由 tsc 编译期自证，无需专测），清单见 §8.7.2。

> **实施记录（P2，2026-08-29，task-pulsepet-v2-registry R1）**：已实施。npm 基线实测 442 passed（31 文件）→ 实施后 **447 passed（32 文件）**（新钉 5 例：agents.test.ts 五个 it，其中含 P2 钉 1 badgeOf 未知 id 显原名与表完整性；P2 钉 2 include_str 互钉落 Rust 侧 agents.rs tests，cargo 351 → **352 passed** + 3 ignored）；`npx tsc --noEmit` / `npm run build` 全绿。实施微调：① `agentShortName` 消费方比 §8.2 盘点的 4 文件多两处（bubble-queue.ts / pet-menu.ts 的 import）——迁移为 `shortOf` 时一并改引 agents.ts（§8.7.1 既有短名兜底钉 bubble-queue.test.ts:330 原样通过）；② 两个测试文件的 `AGENT_*` 引用改为**本地字面量常量**（钉 wire 值而非同源常量，解 import 耦合）；③ Settings nameKey 查表后未知 id 走原名兜底渲染（`nameKey ? t(nameKey) : s.id`，消 §4 #10 第三卡错名温床）；④ agent-adapter.ts 按 §6.7 加装饰性标注注释（不激活不删除）。附带核定：遗留事项 B（TokenStats.tsx symmetricToggle 注释「模型/agent 共用」过时）经查**已在 polish 轮（8a054e0）清偿**（现行注释即准确措辞「模型筛选用——R2 后 agent 维度不再消费」），无需重复修改。

### 8.3 P3：N 源编排 + degraded/报错口径 A′（~300 行，语义扩展）

- `query_stats_dual`/`today_stats_dual` → **`query_stats_all`/`today_stats_all`**（评审 P2-4：避开与现存单源函数 `query_stats`（:441）/ `today_stats`（:568）重名——旧单源函数保留原名，继续被 idle 汇报引用）：遍历 AGENTS 逐源查询合并（enum dispatch，无 trait object）；源结果三态化 Ok/Missing/Failed，判据按文件存在性两段式（§6.4，评审 P1-2）——**本阶段含三处有意行为变更**：① CC-only（oc Missing × CC 有数据）从横幅改静默；②③ oc Missing / oc Failed × CC Ok-0行 两组合从 Err 改空态（差异表见 §6.4，评审 P1-1）；
- `AgentSpec` 增 `is_primary`（仅 opencode true）；degraded = 主源 **Failed** × 其余有数据 → `Some`；硬报错 = 全部源无数据且无一源 Ok，文案 N 源中性化（`token.error.noDatabase` 重写）；
- 消费点全覆盖（评审 P2-5 补漏）：`token_stats.rs:944/:973` 两命令层、by_agent 合并、**`:894/:921` `build_cc_idle_report` 今日段**（CC idle 汇报气泡 today 段——degraded 语义沿用现状 `.ok()` 吞错静默省略，TC-M3-09-3 既有口径不变）；
- 性能口径（评审 P2-8）：维持单 `spawn_blocking` 内**串行**逐源查询（现状 dual 即串行：SQL → transcript 扫描），源数个位数下每源 ms~几十 ms、延迟线性增长可接受——标注为已知取舍，源数上双位数再考虑 per-source 并行/缓存；
- 测试：`m5_degraded_opencode_error_with_cc_data_degrades`（:1742，现用"无 db"构造 degraded）改用**伪造 schema 错误**构造 Failed 场景，另补 **db 文件在但打不开/损坏** 的 Failed 用例（P1-2——防"文件在但坏"误判 Missing）；补三组新钉子：Missing × 有数据 = 无横幅、oc Missing × CC Ok-0行 = 空态、oc Failed × CC Ok-0行 = 空态（P1-1）；`m5_degraded_both_missing_error_passthrough`（:1787，构造 = 无 db × CC 无目录）**语义不变仍 Err**；TC-M5-08/09 预期口径同步；i18n `token.degraded` / `token.error.noDatabase` 两文案联动；其余双源用例语义不变；新增三源用例——第三源注入形态实施时二选一：a) tempdir 伪造 transcript 源（贴真实，优先）b) `#[cfg(test)]` 假源变体。（P3 **必须新增用例而非纯回归**——三处行为变更靠新钉证明；覆盖核定与完整清单见 §8.7。）

### 8.4 收尾（随各阶段）

- `agent-registry.md` 分阶段回写实施记录；`V2-OPEN-ITEMS.md` §13 补交叉引用与闭环记录；
- 项目 `AGENTS.md` 加一句"新增 agent 指南见 `docs/v2/agent-registry.md`"；
- 每阶段独立 commit（遵守仓库约定：除非用户明确要求，不 commit / push）。

### 8.5 风险与回滚

最大风险点 = P1 动 lib.rs run() 接线（issue #9 manage 时序铁律）——现有时序钉子 + dev 冒烟双保险；三阶段各自独立 commit 可单独回滚。P1/P2 的安全性由"既有测试网全绿且零改语义"证明；P3 语义扩展集中在 degraded 与签名泛化，由三源新用例把守。

### 8.6 执行层待定项（启动实施前确认）

| # | 问题 | 备注 |
|---|---|---|
| 1 | 节奏：P1 做完停下评审，还是 P1+P2 连做？ | P3 建议无论如何单独一批（它是语义扩展） |
| 2 | dev 冒烟频次：每阶段跑一次 `tauri dev` 目验，还是最后统一？ | 涉及接入卡/气泡人工目验 |

### 8.7 测试补充与回归清单（2026-08-28 既有测试网覆盖核定，第七轮）

> 结论：**P1/P2 主体靠既有测试网回归证明**（"行为零变化"设计的安全网，覆盖面经逐项核实扎实），但各需少量**新不变量钉子**；**P3 必须新增用例**（三处行为变更靠新钉证明）——不是纯回归就行。清单为本轮对既有网真实覆盖面的核定结论（grep + 测试源码逐项核实）。

#### 8.7.1 既有网覆盖面（回归部分，已核实存在）

| 覆盖点 | 既有钉子 | 服务阶段 |
|---|---|---|
| 白名单双向（拒绝含 "codex"） | `state_unknown_agent_returns_400` / `state_whitelist_accepts_both_agents`（http_server.rs:951/:968） | P1 |
| idle 未知分支 | `lib.rs:599-613` "codex" 零查询零派发 | P1 |
| idle 双臂行为 | `lib.rs:570-722` 闭包注入单测（CC idle 零 opencode 查询 / oc idle 汇报 + success 注入） | P1 |
| 接入安装/幂等/卸载 | integrations tempdir 注入全套（内层函数签名不变，免改） | P1 |
| 短名兜底 | `bubble-queue.test.ts:330` "未知→原名" | P2 |
| agent tab 动态导出 | `token-chart.test.ts:202` agentsWithRows | P2 |
| i18n zh/en 完备性 | `i18n.test.ts` 键集合断言（新键漏译自动红） | P2/P3 |
| 双源容错矩阵 | `token_stats.rs:1742-2040` degraded 三用例 + 双源合并 + by_agent | P3 |

#### 8.7.2 待补新钉（旧网钉不住的新不变量）

**P1（5 枚）**：

| # | 钉子 | 内容 | 目的 |
|---|---|---|---|
| 1 | agents.rs 自测 ① | `find` 已知 id 命中 | 查表基本功能 |
| 2 | agents.rs 自测 ② | **未知 id → None** | "不落 else"根基（消静默错误 ①② 的温床） |
| 3 | agents.rs 自测 ③ | AGENTS id 唯一、无 id 叫 `"task"` | task 伪 agent 冲突约束（§2） |
| 4 | status_for 未知 id 报错钉 | 未知 id 返回明确 Err，而非落 CC 探测 | 消静默错误 ① 的回归钉——**现状无任何测试把守** |
| 5 | 时序钉子改写 | `lib.rs:730-748` 断言改盯 `register_states` 在窗口创建循环之前 | issue #9 铁律继续把守（改写非新增） |

**P2（2 枚）**：

| # | 钉子 | 内容 | 目的 |
|---|---|---|---|
| 1 | badgeOf 未知 id 显原名 | `"codex"` → 显 `"codex"` 非 `"oc"` | 消静默错误 ②——`agentBadgeOf` 现为模块私有、**零直接测试**，else→oc 今天就无钉把守 |
| 2 | include_str 双端互钉 | Rust 测试断言两端 id + short 集合一致 | 防 Rust/TS 注册表漂移（§6.3），全新测试类型 |

（附：`IntegrationId` 派生类型无需专测——`tsc` 即编译期验证。）

**P3（6 枚，明细已在 §8.3 测试条）**：三组行为变更钉子（Missing × 有数据 = 无横幅 / 两组 Ok-0行 = 空态）＋"db 在但打不开"Failed 用例＋`m5_degraded_opencode_error_with_cc_data_degrades` 改写（预期从 degraded=Some 变 None）＋三源合成用例；`m5_degraded_both_missing_error_passthrough` 回归确认（语义不变仍 Err）。

#### 8.7.3 既有缺口发现与豁免

- **integrations 命令层未知 id 守卫无行为测试**：`integrations_install/uninstall` 守卫（mod.rs:1039/:1072）现状无直接测试——命令层 async + AppHandle 不易单测，现有 tempdir 测试只覆盖内层函数。P1 后守卫收敛为 `find().ok_or()` 一行薄壳，核心钉子放 find/status_for 层即可，**命令层不强测**（豁免理由：一行薄壳无分支逻辑）。
- **CC"目录在但空"（Ok-0行）是全新场景**：既有测试无此构造（`cc_absent` 用例构造的是"目录缺失"，两者现状代码层同走 Err 不可分、A′ 下分道）——正是 §8.3 新钉的必要性来源。

## 9. 待决策问题（2026-08-28 更新：1/2/3 已拍板，4-7 悬置）

| # | 问题 | 状态与备注 |
|---|---|---|
| 1 | 是否立项收敛 | ✅ **已拍板（2026-08-28）**：立项，P1→P2→P3（§8.0） |
| 2 | degraded / 报错口径 | ✅ **已拍板（两轮）**：口径 A′ 三态模型——报错仅当全部源无数据；横幅仅主源 Failed（保留）；Missing 静默（§6.4，含 CC-only 场景差异表） |
| 3 | `AgentSpec` 分发形态 | ✅ **已拍板**：函数指针表（§6.1；统计源 enum dispatch） |
| 4 | `short_name` 分配（codex → "cx"？） | 悬置——codex 接入（P4）时定；zh/en 同值（技术名不翻译约定） |
| 5 | codex 本地数据源调研 | 悬置——**可与 P1-P3 并行启动**；结果决定 §7.1 走向与 P3 紧迫性（无数据源则短期内仍是两源） |
| 6 | 新 agent 是否都要进"接入管理"卡 | 悬置——P4 时定；`AgentSpec.integration` 已设计为 `Option` 兜住"无安装物"形态 |
| 7 | killswitch 粒度（实证观察项） | 悬置——现状**全局单开关**（`runtime/hooks-disabled` 一份文件，关一家 = 全关）；多 agent 规模化后是否按接入分文件涉及既有 canonical command 兼容，**本轮明确不动** |

## 10. 调查与讨论记录

- **2026-08-28 独立复核**（本档 §2-§5 行号来源）：对照 §13.3 原清单逐项 grep + 读源码，全部印证；行号差异仅为 §十二 F1~F16 实施后的漂移（如 `agentShortName` :47→:45、Settings nameKey :545→:565、cost 规则 :467/:502→:485/:520），另确认 `costOpencodeOnly` 已随 F3 清退、`agentBadgeOf`/`agentLabel` 现为 :83-87/:90-96。零改动面与"AgentAdapter 装饰性"论断亦经 grep 复核（adapters 仅自测试引用）。
- **2026-08-28 实证对照**（用户指令："对照 v2 接入 Claude 的设计与实施过程查遗漏"）：以 v2 接入第二家（Claude Code）的三个 commit 实际 diff 校验本档清单——**M1** `858b91d`（CC 事件接入+接入管理，20 文件 +3693 行）/ **M5** `6d7a1c7`（CC transcript 双源，17 文件 +2128 行）/ **M6** `8973813`（徽标/抢镜基建，23 文件 +961 行）。结论：①12 处静态清单**无错报**，零改动面全部经实证成立（M1 动的 `session_state.rs`/`http-bridge.ts`/`petStore.ts`、M6 动的 `bubble-queue.ts`/`pet-menu.ts`/`todayToken.ts` 等均为当年建 agent 维度的一次性基建投入，现已通用化）；②补充 #13 lib.rs 接线组、#14 文档联动两处必改（§4）；③提炼 hook 自包含单文件契约 + 三件套（§3）；④新观察项 killswitch 全局单开关粒度（→ §9-7）；⑤澄清 Rust i18n.rs 汇报模板 F1 后已 agent 无关（§2）。**量化参照**：接第二家的真实成本 ≈ 事件链+接入管理 3.7k 行 / 数据源 2.1k 行 / 徽标基建 1k 行——第三家若带数据源，纯新增体量参照 M5（~2-3k 行），另加 §4 必改 14 处。
- **2026-08-28 方案讨论定稿**：四轮讨论——总体方案（设计原则四条 + 两端注册表 + 互钉 + 吸收映射）→ P3 与"数据源"概念澄清（→ §6.4/§7.1）→ 双链独立接入确认（→ §7）→ 用户三项决策（立项 P1→P2→P3 / 口径 A / 函数指针表，→ §8.0），并指示**先不实施、方案落档**（→ §8 状态）。补充调查：`idle_hook_body` 为闭包注入签名（`lib.rs:570-722` 测试免改依据，且已有 "codex" 未知分支钉子）；`AGENT_*` 常量前端仅 4 文件引用；`TranscriptCache { entries: HashMap }` 可被 register_states 模式接管。
- **2026-08-28 degraded 边界场景发现与口径 A′（第五轮）**：用户问"只有 Claude 没有 opencode 的用户会报错吗"——源码验证：不报错，但**常驻横幅**（`detect_db_path` None → `no-database` Err（token_stats.rs:175）× CC 有数据 → Err 臂 :815-824 返回 CC-only + `degraded=Some` → `TokenStats.tsx:334-336` 横幅「opencode 源不可用：仅显示 Claude Code 数据」，hover 可见原始错误串）；伴生边角：双源全缺 → `no-database` 硬错误态。根因 = M3/M5"人人有 opencode"的主源假设，口径 A 原样继承。用户裁定：**"全部对接的统计链路都没有数据时，才报错"** → 定稿三态模型（Ok / Missing / Failed，§6.4 口径 A′）；横幅去留经确认：**保留** Failed（在但坏）场景、剔除 Missing（CC-only 干净）。实现判据：Err.code `no-database`=Missing / `schema-mismatch`·`query`=Failed，无需耦合接入管理状态。落点：P3（属行为变更，不入零变化的 P1/P2）。
- **2026-08-28 评审轮（reviewer subagent，第六轮）**：用户指令调用 reviewer 评审本档——全维度（事实准确性 / 方案合理性 / 可实施性 / 一致性 / 遗漏盲点）+ 源码逐项核验 + 基线实测。结论 **NEEDS_CHANGES**（2 P1 + 8 P2 + 5 P3 + 4 澄清项）：事实面全部过硬（§4 十四处行号逐项精确、§2 零改动面十项全印证、M1/M5/M6 数据吻合、cargo 基线一致），两个 P1 均落在口径 A′（CC Ok-0行边界与差异表矛盾 / 错误码判据误杀 Failed 横幅）。用户裁定"按评审意见修改"（含澄清项四条处置），当日全部落档，评审原文全文收录 §11。
- **2026-08-28 测试覆盖核定（第七轮）**：用户问"测试用例是否需要补充，还是既有覆盖回归即可"——逐项核实既有测试网真实覆盖面（白名单双向含 "codex" 拒绝 / idle 未知分支与双臂注入 / tempdir 全套 / 短名兜底 / agentsWithRows / i18n 完备性 / 双源容错矩阵，均存在）→ 结论：**P1/P2 主体靠既有网回归证明，各补少量新钉（5/2 枚），P3 必须新增 6 枚**（三处行为变更靠新钉证明，非纯回归）；顺带发现既有缺口两处：integrations 命令层未知 id 守卫无行为测试（P1 后一行薄壳豁免）、CC"目录在但空"为全新场景无既有构造。清单落档 §8.7，§8.1-8.3 验证行联动。
- **原文档**：`V2-OPEN-ITEMS.md` §十三（2026-08-28 预研，commit `8db121a`）——本档为其展开与后续工作底稿，收敛实施后回写闭环记录。

---

## 11. 评审记录（2026-08-28，reviewer subagent）

> 评审对象：本档 v2026-08-28 定稿（331 行时点）；源码基线 HEAD `e7d58ed`；评审方实测 `cargo test` 346 passed + 3 ignored（与文档一致）、`npm test` **442 passed**（31 文件，两次实测一致——文档原记 439，见 P2-6）。
> 处置：用户裁定"按评审意见修改"（2026-08-28），P1/P2/P3 全部意见与澄清项当日修订落档；每条意见原文后附**处置**行标注落点。以下为评审报告原文收录。

### 11.1 问题清单（原文收录）与处置

#### P1（实施前必须解决）

**【P1-1】§6.4 差异对照表与判定规则四条自相矛盾：CC"Ok 但 0 行"的边界场景被表格错判为"不变/报错"**
- 位置：§6.4「差异对照（vs 现状）」表第 2、4 行 + 判定规则 2/4
- 问题描述：表格写"oc Missing × CC 也无数据 → Err，文案中性化"、"oc Failed × CC 无数据 → Err（同）"。但"CC 也无数据/无数据"未区分 **CC Missing（无目录）** 与 **CC Ok 但 0 行（目录在、无 transcript）**。按规则 2（"全部源无数据（全 Missing/Failed，**无一源 Ok**）"才报错）+ 规则 4（"有源 Ok 但 0 行 → 空态"），当 CC 为 Ok-0 行时：oc Missing → 空态（非 Err）；oc Failed → 空态（非 Err、非横幅）。即这两个子场景在 A′ 下是**行为变更**（现状 Err → 空态），表格却标"（同）"或未覆盖——按表格实现会与四条规则直接冲突，而 §8.3 的 P3 测试计划（"其余双源用例语义不变"）也建立在该误判之上。
- 依据：现状代码 `token_stats.rs:815-824` 仅按 `cc_has_data = !cc_rows_all.is_empty()`（行数）判，CC-Missing 与 CC-Ok-0 同走 Err 透传——文档若想标"同"只能指 CC-Missing 子场景；`transcript.rs:80-82` 目录缺失返回空 Vec，与"目录在但空"现状代码层不可分。
- 建议处置：差异表补两行——"oc Missing × CC Ok 但 0 行 → 空态（变更）"、"oc Failed × CC Ok 但 0 行 → 空态（变更）"；并把第 2/4 行的"CC 也无数据/无数据"改写为"CC Missing（无目录）"消除歧义；§8.3 测试计划相应补这两组三态组合用例。
- **处置**：✅ 已修订——§6.4 差异表改写第 2/4 行为"CC Missing"、补两行 Ok-0行场景（标注行为变更），表下加"行为变更共三处"划界注记；§8.3 测试计划补三组新钉子并明确 `m5_degraded_both_missing_error_passthrough` 语义不变。

**【P1-2】§6.4 "实现判据现成"与代码错误语义不对齐："库损坏/文件在但打不开"会被误判为 Missing 而静默——恰好违背用户拍板的"Failed 保留横幅"**
- 位置：§6.4 末段"实现判据现成……Err.code `no-database`（detect_db_path None）= Missing；`schema-mismatch`/`query` = Failed" + 三态表 Failed 示例（"库损坏"）
- 问题描述：三态表把"库损坏"列为 Failed 的例子，但代码中 `detect_db_path` Some 之后**打开失败（含 WAL 缺失、损坏、权限）同样映射 ERR_NO_DATABASE**（`token_stats.rs:241-247`：`open_readonly` 打开失败 → `StatsError::new(ERR_NO_DATABASE, "数据库未运行/未初始化")`；`:462-476` `open_checked` 流程）。按文档判据（no-database=Missing），一个"源在但坏"的 opencode 会静默成 Missing——用户明确裁定要保留横幅的正是"装了但坏"场景，判据按错误码实现会把这一核心语义静默掉。
- 依据：`token_stats.rs:247`（打开失败→no-database）、`:472`（detect None→no-database），两者同码不同因；§6.4 判据句"（detect_db_path None）"的括号限定说明作者有意按文件存在性判，但行文"Err.code no-database = Missing"会诱导按码实现。
- 建议处置：判据改为两段式——"`detect_db_path` None = Missing；`detect_db_path` Some × 后续任何错误（open/schema/query）= Failed"，即文件存在性判定与错误码解耦；§8.3 的 Failed 构造测试除"伪造 schema 错误"外，补"db 文件在但损坏/WAL 缺失"用例。
- **处置**：✅ 已修订——§6.4 判据改为按文件存在性两段式（opencode：detect None=Missing / Some×任何错误=Failed），§8.3 补"db 文件在但打不开/损坏"Failed 用例。

#### P2（建议修）

**【P2-1】§6.4 三态模型的 CC 侧（及未来第 N 源）Failed 判据缺失，而"解析失败"被列为 Failed 示例现状根本无法探测**
- 位置：§6.4 三态表（Failed 行"解析失败"）+ 末段实现判据
- 问题描述：CC transcript 解析对坏行是**静默跳过**（`transcript.rs:174-176` "坏行/非 JSON：跳过不崩"），目录缺失返回空 Vec（`:80-82`），全链路无错误通道——CC 的 Failed 态在现状代码中不存在，A′ 的"非主源 Failed 静默"对 CC 是空集语义；P3 若要实现"全部源无数据→报错"的精确三态，必须新建 CC 侧失败探测。文档"实现判据现成"仅覆盖 opencode。
- 依据：`transcript.rs:80-82 / 174-176`；`query_stats_dual`（`:798-801`）只拿行数不拿错误。
- 建议处置：§6.4 补 per-source 判据表：CC 的 Missing=目录不存在；Failed 要么明确"P3 不探测（删掉'解析失败'这个 Failed 示例以免误导）"，要么定义探测方案（如统计坏行数）。
- **处置**：✅ 已修订——§6.4 判据改 per-source 两分（CC：目录在即 Ok，P3 不新建解析失败探测、Failed 对 CC 为空集留档），三态表 Failed 示例删"解析失败"改为 CC 侧注记。

**【P2-2】§6.1 核心扩展路径空白："注入式签名保持不变"与"make_idle_hook 参数不再随家数增长 / 新源一行注册"存在未交代的张力**
- 位置：§6.1 第三个关键设计决策（idle 分流查表）
- 问题描述：文档同时承诺（a）`idle_hook_body` 注入式签名不变（5 个闭包 + agent/session_id，单测免改）、（b）`make_idle_hook` 参数不再随家数增长、§6.6 目标态"一行注册"。但注入的 `query_report` 闭包是 opencode 专属（`build_idle_report_with_today`，`lib.rs:160-168`），第三个**带统计源**的 agent 的 idle 汇报路径如何挂入完全没有说明——签名不变则新源仍需扩展签名或泛化闭包；文档只解释了"臂内字面量→spec.id"与"cc_dispatch 改从 app.state 取句柄"，两者都不解决第三个源。P1 阶段（两家、行为零变化）无影响，但作为"多 agent 路线结构性前置"的方案，这是目标态扩展路径的设计空白。
- 依据：`lib.rs:101-140`（签名与两臂）、`:160-168`（query_report 闭包绑死 opencode_data_dir）。
- 建议处置：补一段明确第 3+ 源 idle 分发落点（如 AgentSpec 增 `idle_report: fn` 指针、注入闭包降级为仅测试保留），或显式声明"idle 注入签名 P1 冻结，P4 接第三家时再做第二波泛化"并计入 P4 成本。
- **处置**：✅ 已修订——§6.1 增第四个设计决策"第 3+ 源 idle 汇报落点"：P1 冻结注入签名，P4 时 `AgentSpec` 增 `idle_report: fn` 指针、注入闭包降级为测试保留，成本计入 P4。

**【P2-3】§6.3 include_str! 路径写错一级**
- 位置：§6.3 "`include_str!("../../../src/lib/agents.ts")`"
- 问题描述：agents.rs 规划位置是 `src-tauri/src/agents.rs`（§8.1），据此 `../../../` 会指到仓库根 `lab/`（路径变成 lab/src/lib/agents.ts，不存在）。正确路径应为 `"../../src/lib/agents.ts"`。既有先例可证：`integrations/mod.rs:43-44`（位于 src-tauri/src/integrations/，深一级）用 `"../../../opencode-plugin/…"` 指到 pulse-pet 根。
- 依据：`integrations/mod.rs:43` 先例路径形态。
- 建议处置：改为 `include_str!("../../src/lib/agents.ts")`。
- **处置**：✅ 已修订——§6.3 路径改两级并注上溯说明。

**【P2-4】§8.3 改名目标与既有函数重名**
- 位置：§8.3 "`query_stats_dual`/`today_stats_dual` → `query_stats`/`today_stats`"
- 问题描述：`query_stats`（`token_stats.rs:441`）与 `today_stats`（`:568`）是**现存**单源编排函数，被 dual 函数、`build_idle_report_with_today` 及大量单测引用。文档未说明重名处置（旧函数改名/吸收/保留现名），照抄会产生歧义甚至编译错。
- 依据：`token_stats.rs:441/568/803/859` 及测试调用点（:1154 等）。
- 建议处置：目标名改为 `query_stats_all`/`today_stats_all`，或明示旧单源函数的处置方案。
- **处置**：✅ 已修订——§8.3 目标名改 `query_stats_all`/`today_stats_all`，注明旧单源函数保留原名继续被 idle 汇报引用。

**【P2-5】§8.3 P3 文件级清单漏列 `build_cc_idle_report` 的 today 段消费点**
- 位置：§8.3 改造清单
- 问题描述：`build_cc_idle_report` 在 `token_stats.rs:921` 调用 `today_stats_dual`（CC idle 汇报气泡的"今日合计"段）——P3 改名/N 源化时该调用点必须同步改，但 §8.3 只列了 `:944/:973` 两命令层与 by_agent。漏列会导致实施中编译断点或语义漏改。
- 依据：`token_stats.rs:894-924`（:921 调用点）。
- 建议处置：清单补 `:894/:921`（idle 汇报 today 段的 N 源适配），并明确其 degraded 语义（现状 `.ok()` 吞错，A′ 下是否沿用）。
- **处置**：✅ 已修订——§8.3 消费点补 `:894/:921`，degraded 语义明确沿用现状 `.ok()` 吞错静默省略（TC-M3-09-3 口径不变）。

**【P2-6】npm 基线数字与实测不符：文档称 439，HEAD 实测 442**
- 位置：§6.0 设计原则 1、§8.2 验证节
- 问题描述：本机对 HEAD `e7d58ed` 两次 `npm test` 均为 **442 passed（31 文件）**；文档与 §12.4 清偿记录均写 439（§十一 记录为 433）。差 3 个测试，需作者复核差值来源（疑为批次记录漂移或统计口径不同）。cargo 基线 346+3 **实测精确一致**。
- 依据：实测 vitest 输出 "Tests 442 passed (442)"；`git show e7d58ed` 无测试文件改动，说明差值不在 e7d58ed 内。
- 建议处置：复核差值并更正数字（若 439 出自某个排除口径，注明口径）。
- **处置**：✅ 已修订——§6.0/§8.2 基线改 442 并注明评审实测来源；差值来源未深究（e7d58ed 无测试改动，疑批次时点数），以评审两次实测为准。

**【P2-7】§3 hook 三件套行数与现状不符（成本参照数字过时）**
- 位置：§3 "claude-code-hook 三件套实证：231 行脚本 / 46 行 d.ts / 281+79 行测试"
- 问题描述：实测 `claude-code-hook.js` **382 行**、`.d.ts` **72 行**、测试 **397 行（25 tests）**。§10 量化参照（"第三家纯新增体量参照 M5 ~2-3k 行"）若部分基于此数会有偏差。
- 依据：`wc -l` 实测。
- 建议处置：更新为现行数字，或注明统计时点（如"M1 时点数"）以免被当作现状引用。
- **处置**：✅ 已修订——§3 更新为 HEAD 实测（382/72/397·25）并保留 M1 时点数对照注记。

**【P2-8】性能维度（N 源串行查询）未讨论**
- 位置：§6.4/§8.3（P3 遍历 AGENTS 逐源查询合并）
- 问题描述：`token_stats_query`/`token_stats_today` 在单个 `spawn_blocking` 内串行 I/O（现有 dual 已是串行：SQL → transcript 扫描）。N 源化后 Token 页/今日汇总延迟随源数线性增长，文档未说明并行/缓存取舍，也未标注可接受源数上限。作为"接很多个 agent"的长期方案这是显性维度。
- 依据：`token_stats.rs:944-981`（spawn_blocking 内串行）、`:782-826`（dual 串行结构）。
- 建议处置：§8.3 加一句性能口径（串行可接受、或计划 per-source 并行/缓存），至少标注为已知取舍。
- **处置**：✅ 已修订——§8.3 增性能口径条目：维持串行、个位数源延迟线性可接受、标注已知取舍，源数上双位数再议并行/缓存。

#### P3（打磨/备忘）

**【P3-1】§7.2 表把 #2（idle 分流）列入 ①事件链必改点，与交接点 1 自相矛盾**——交接点 1 明说"统计链未接时新 agent 的 idle 自动落 other 分支跳过——无害"，即非收敛路径下 ① 接入**不必**改 #2（收敛路径下由一行注册自动覆盖）。建议从 ① 移除 #2 或加注"收敛后自动覆盖"。
- **处置**：✅ 已修订——§7.2 ① 列移除 #2 并加注（非收敛路径无害 / 收敛路径自动覆盖）。

**【P3-2】§6.5 "#11 键名规则化（token.agent.<id> / integrations.<id>Desc）"与现有关键名不符**——现有键是 `token.agent.claudeCode`/`integrations.claudeDesc`（camelCase，非 <id> 直拼），§8 无重命名计划，"规则化"表述易误导为键名重排。建议改为"沿用现有命名风格，新键按同风格添加"。
- **处置**：✅ 已修订——§6.5 改为"沿用现有 camelCase 键名风格，新键按同风格添加"，并注明非 `<id>` 直拼、不做键名重排。

**【P3-3】口径 A 被引用但全文未定义**——§6.4 出现"口径 A 的三态收窄版""非主源 Failed 静默（口径 A 原则不变）"、§8.0 引"口径 A′（三态收窄版，同日二轮裁定）"，但本档无口径 A 原文（讨论记录在 §10 只有一句"口径 A 原样继承"）。定稿文档作为独立实施依据应自含。建议加一句 A 的定义（主源错误才降级横幅、非主源错误静默、Missing 与 Failed 不分等）。
- **处置**：✅ 已修订——§6.4 口径 A′ 段前补口径 A 定义句。

**【P3-4】§6.6"回归纯新增：不触碰任何既有分支/switch/三元"与既有 codex 拒绝钉子有轻微张力**——`http_server.rs:954` 白名单拒绝用例列表含 `"codex"`、`lib.rs:599-613` 未知 agent 钉子用 `"codex"` 断言零查询；P4 真接 codex 时这两处需同步改（从拒绝清单移除/改断言）。建议 §6.6 或 §9-4 加注。
- **处置**：✅ 已修订——§6.6 尾部加注（两处 "codex" 拒绝钉子 P4 时同步改接受断言，属预期测试面调整）。

**【P3-5】§6.1/§8.1 的 ":575-639 闭包注入单测"范围不精确**——idle 单测实际跨 `:570-722`（§4 #12 自己写的正是 :571-722，同一文档两处口径不一）。建议统一为 :570-722。
- **处置**：✅ 已修订——§4 #12 / §6.1 / §8.1 / §10 四处统一为 :570-722。

### 11.2 澄清项（原文）与补答

原文：

> 1. **CC 侧 Failed 判据的去向**（对应 P2-1）：P3 是否探测 CC transcript 解析失败？若不探测，"解析失败"应从三态表 Failed 示例删除——请确认。
> 2. **基线 442 vs 439 差值来源**（对应 P2-6）：请复核哪个数字为准，避免 P2 验证节拿错误基线做回归网判定。
> 3. **第 3+ 源的 idle 汇报落点**（对应 P2-2）：签名冻结与"一行注册"如何并存，建议在 §6.1 或 §9-6 附近明确一句。
> 4. **§8.3 中"其余双源用例语义不变"的适用边界**（对应 P1-1）：差异表补行后，`m5_degraded_both_missing_error_passthrough`（:1787）等既有用例里哪些属于"语义不变"、哪些需按新口径改写，请随补行一起划清。

补答（2026-08-28，随修订落档）：

1. **不探测**——CC 的 Failed 态 P3 为空集（目录在即 Ok，坏行静默跳过是既定健壮行为）；"解析失败"已从三态表 Failed 示例删除，未来需要再加坏行计数（§6.4 per-source 判据）。
2. **以 442 为准**（评审两次实测；e7d58ed 无测试改动，439 系批次时点数）；§6.0/§8.2 已更正。
3. **P1 冻结注入签名，P4 第二波泛化**——`AgentSpec` 届时增 `idle_report: fn` 指针，注入闭包降级为测试保留，成本计入 P4（§6.1 第四个设计决策）。
4. **边界已划清**——行为变更共三处（CC-only 静默化 + 两组 Ok-0行 Err→空态）；`m5_degraded_both_missing_error_passthrough`（无 db × CC 无目录）语义不变仍 Err；§6.4 表下注记 + §8.3 测试计划同步（§8.3）。

### 11.3 评审结论（原文）

> **verdict: NEEDS_CHANGES**
>
> 存在 2 个 P1：(1) §6.4 差异对照表在 CC"Ok 但 0 行"边界场景上与判定规则四条直接矛盾（含"（同）"错标）；(2) §6.4 实现判据按错误码实现会把"库损坏/文件在但打不开"误判为 Missing 而静默——恰好推翻用户拍板保留的 Failed 横幅语义。两者都落在本文档的核心决策（口径 A′）上，P3 实施前必须修订。
>
> 其余事实面表现优秀：§4 必改 14 处清单的行号我逐项对照 HEAD 源码**全部精确**（含 :109 的 match、:202/:210、:295/:311/:359、:815-824、:876/:879/:945、:1022-1025、:1034-1093、TokenStats.tsx:83-87/:90-96/:334-336/:485/:520、Settings.tsx:565、i18n 双侧键位、测试点位等）；§2 零改动面 10 项全部印证（复合键、agentsWithRows、AgentAdapter 装饰性——grep 确认仅自测试引用、Panel.tsx:79、i18n.rs:114/124、task 伪 agent 等）；§6.4 现状缺陷证据链（CC-only 常驻横幅）完整成立；§10 的 M1/M5/M6 commit 数据（20/+3693、17/+2128、lib.rs 152 行、23/+961）实测吻合；cargo 基线 346+3 实测一致；"codex"防御钉子（lib.rs:609）与 include_str 源码断言先例（mod.rs:1674 等）确实存在。
>
> 修订 P1-1/P1-2（含差异表补行与判据两段式化）后，文档可作为 P1/P2 阶段的实施依据；P3 实施前还需同步消化 P2 清单中的口径与清单完整性问题。

**终审（2026-08-28 用户）**：按评审意见修改——P1×2、P2×8、P3×5 与澄清项×4 当日全部修订落档（处置见 11.1/11.2 各条）；按结论口径，本档可作为 P1/P2 实施依据，P3 启动前以本修订版为准。
