# ai-hedge-fund 解剖档案

> 基线：~/develop/opensource/ai-hedge-fund @ fc1bf25 (2026-09-03)；canonical virattt/ai-hedge-fund；v2.2.0 全量重写版（经典 v1 的 `src/agents/`+LangGraph 结构已不存在，当前代码为 `hedge_fund/` 包）。**教育/研究项目，无真实下单通道**（README.md:7 "the system does not actually make any trades"；仅 SimBroker 模拟成交）。MIT。

## 1. 产品定位与形态

- 定位：AI 对冲基金模拟——「把真实基金的 org chart 里的人换成 AI」（`VISION.md#Think of it like a real hedge fund`）。LLM 投资者 agent（Buffett/Munger/Graham/Lynch/Druckenmiller 人格）+ 量化 alpha 模型（PEAD）混编成多策略基金，可单周期运行、历史回测，未来规划 paper/live（ROADMAP 标注 ledger 持久化、paper broker、scheduler 均未完成）。
- 交互形态：单用户本地应用。`aihf` 无参启动 Textual TUI（交互式建基金/回测/看净值曲线）；带 mandate YAML 参数则非交互跑单周期/回测，完整 `CycleRecord` JSON 打 stdout（`hedge_fund/run.py#main`）。❌ 无 server/API 服务形态——是本档案 18 仓库里少见的「纯 CLI/TUI 应用」。
- 目标用户：教育/研究者（README 反复声明 educational use only）。

## 2. Agent 执行架构（★重点：拓扑与数据流）

### 编排模式：纯函数流水线（非图引擎）

**❌ 不用任何 agent 框架做编排**——没有 LangGraph/AutoGen/状态机，主循环就是一条确定性 Python 函数调用链，且刻意把 LLM 的作用域压到最小。langchain-* 依赖仅用作多 provider 的 chat client 传输层（`hedge_fund/llm/client.py#make_llm`，还注释了为何不用 langchain 的 structured-output：`client.py:8-9`）。

一条管线三种模式，只有「时钟和 broker」不同（`hedge_fund/pipeline/run_cycle.py:1-27` docstring）：

```
run_cycle(fund, as_of, broker, data_client, universe):
  point-in-time 数据 → analysts → blend → 风控 clamp → 执行 → 记录
```

回测 = 历史时钟 + SimBroker 循环（`hedge_fund/backtesting/fund.py#backtest_fund`，按 mandate 的 rebalance 节奏在 benchmark 交易日网格上逐 tick 循环，broker 状态跨 tick 持续）；「run today」= 同一 run_cycle 单 tick。**「回测即实盘代码路径」是本项目第一设计原则**（VISION.md "The backtest is the live system"）。

### 多 agent 拓扑（层级制基金组织，非辩论制）

组织结构三层（`hedge_fund/fund/spec.py:1-24` docstring、`VISION.md`）：

| 层 | 代码载体 | 角色 |
|---|---|---|
| FUND | `FundSpec`（YAML mandate） | 资本、主风控（对 netted book 施加）、再平衡节奏 |
| STRATEGY（pod） | `StrategySpec` | 分析师组合 + blend 政策 + 资本切片 |
| MODEL（analyst） | `AlphaModel` 实现 | 形成观点 → `Signal` |

Agent 角色清单（全部注册在 `hedge_fund/signals/__init__.py#ALPHA_MODEL_REGISTRY`）：
- **LLM 人格 agent ×5**：BuffettAgent / MungerAgent / GrahamAgent / LynchAgent / DruckenmillerAgent（`hedge_fund/signals/{buffett,munger,graham,lynch,druckenmiller}.py`）。每个 agent = 一个 name + 一段 system prompt（人格检查清单 + 输出 JSON schema：signal/confidence/reasoning），其余机制全部在基类 `hedge_fund/signals/llm_agent.py#LLMAgent`。
- **量化模型 ×1**：PEADModel（`hedge_fund/signals/pead.py`，盈余漂移纯数学）。
- 两种 flavor 实现同一个 `AlphaModel` ABC（`hedge_fund/signals/base.py#AlphaModel.predict`），对引擎完全可互换——「discretionary pod 与 systematic pod 同一 spec 形状」。

### 数据怎么流动（逐 agent 逐 tick）

1. **输入隔离——Point-in-time 快照**：每个 (ticker, date) 先构建 `FundamentalsSnapshot`（`hedge_fund/features/snapshot.py#build_snapshot`），只含该日期前已 filing 的财务指标 + Python 预计算的派生量（ROE 均值、BVPS CAGR 等，让 LLM「对事实推理而非重做算术」）。快照 `content_hash` 排除 as_of——两次 filing 之间的日期共享同一 hash → 同一 prompt → prompt cache 命中（防重复花钱 + 防日历锚定）。
2. **并行独立投票，无 agent 间通信**：`run_cycle.py:88-106` 三层循环 `for strategy → for ticker → for model: model.predict()`。**agent 之间不对话、不辩论、互相不可见**——每个 agent 独立对同一快照投票，产出 `Signal(value∈[-1,1], reasoning)`（`hedge_fund/models.py#Signal`）。这是与 TradingAgents 类辩论拓扑的根本区别：共识靠算术合成而非对话。
3. **混合（portfolio construction）**：`hedge_fund/portfolio/construction.py#blend_signals`——按 strategy 内 model_weights 加权平均 conviction（纯函数，无 I/O）；abstained signal 从分子分母同时剔除（「没意见 ≠ 中性意见」，`llm_agent.py` 的失败契约）；可选 market_neutral 截面去均值。
4. **净额合并**：各 strategy 的 sleeve 按 `weight/total_slice` 资本切片线性 netting 成一个目标持仓（`run_cycle.py:85-99`）。同一人格出现在两个 strategy 里会被问两次，但第二次是 prompt cache 命中而非花钱。
5. **风控**（见维度 5）。
6. **执行**：`hedge_fund/pipeline/execution.py#build_orders` 纯函数——目标权重 × equity / mark 向零取整得目标股数，与 broker 现仓 diff 出 delta 订单；**先卖后买**（确定性排序 + 卖出释放的现金供同周期买入）。
7. **成交与记录**：broker.place_order 全量成交或抛错（`hedge_fund/brokers/protocol.py#Broker`）；CycleRecord 全量序列化。

### 终止条件

- 单周期无迭代：一趟走完数据→观点→混合→风控→订单即结束，**没有多轮讨论/反思循环**。
- 全员 abstain/中性 → 目标全零 → 基金清仓至 flat（`run_cycle.py:20-23` 注明这个 guard 属于外层 daemon 的职责）。
- 唯一的「循环」在外层：backtest 按 rebalance 网格循环 tick；每 tick 内部仍是无迭代单趟。
- AutoGen 式对话终止词（TERMINATE）不存在——LLM 输出被强约束为单个 JSON 对象（`llm_agent.py#_parse` 校验 signal 枚举 + confidence 范围，解析失败→abstain 并把原始响应留盘）。

### 失败契约（锁定决策，`llm_agent.py:15-21`）

- 数据层错误**向上传播**（fail loud——「坏快照绝不能静默变成中性观点」）；持有仓无价格直接 raise（「无法给自己的持仓定价 = 基础设施故障，NAV 会是谎言」，`run_cycle.py#_mark_prices`）。
- LLM 调用/解析失败 → **abstain**（`Signal(value=0.0, metadata.abstained=True)`），且未解析的原始响应也写盘留痕（`llm/cache.py` 的 debug trail 职责）。

## 3. 技术底座

- Python 3.11 + poetry；pydantic v2（所有数据模型，spec 全部 `extra="forbid"`——「YAML 拼错在加载期炸响，不是在交易期静默」，`fund/spec.py:99-101`）；pandas/numpy/scipy（量化模型）；textual TUI + rich CLI。
- **无 agent 编排框架**（见维度 2）。langchain-anthropic/openai/deepseek/google-genai/xai 仅作 provider 传输（`llm/client.py`），且自写 JSON 提取（`#extract_json`：```json fence → 整串 → 首个配平 {}）。
- LLM 选型：`hedge_fund/llm/registry.py` + `api_models.json`（模型目录/ provider/所需 env var 单一事实源）；6 家 provider 路由（Anthropic 默认兜底传输）。
- 交叉引用：langchain 仅用于 chat client 薄层，未用其 agent/chain 机制，框架层结论参考 agent-framework/profiles/langchain.md 但此处借用极浅，无重做必要。

## 4. 状态与持久化

- **用户主目录 `~/.hedge-fund/`**（`hedge_fund/paths.py`）：`mandates/`（YAML mandate + 运行回执 JSON 回执）、`cache/llm/`、`cache/data/`、`.env`（密钥）。
- **PromptCache = 一决定一 JSON 文件**（`hedge_fund/llm/cache.py`）：key = sha256(agent|model|system|user) 前 24 位；同一文件同时是 ①缓存（回测重跑 $0）②**审计记录**（每个 Signal 背后的精确 prompt+response+snapshot_hash）③调试踪迹（解析失败的原始响应也留盘）。这是本仓库最值得抄的「审计即缓存」设计。
- **CachedDataClient**（`hedge_fund/data/cached.py`）：DataClient 装饰器，(method, params) 哈希键的磁盘 JSON 缓存；只缓存成功响应，错误照常传播（fail-loud 语义不因缓存而变）。
- **CycleRecord/FundBacktestResult = 全量回执**（`hedge_fund/pipeline/models.py#CycleRecord`）：一个 tick 的完整真相——spec 自包含审计副本、universe、marks、每个 strategy 每条 Signal（含 reasoning/prompt_key/snapshot_hash）、净额前/风控后权重、clamps、orders、fills、NAV。TUI 把它写为 `mandates/<fund>-run-<时间戳>.json` / `-backtest-<时间戳>.json`（`tui/app.py:1251-1255, 1801-1806`），历史面板从这些文件读回（`tui/app.py#_receipts`）。
- ❌ 无数据库、无会话管理、无并发控制（单进程单用户）；「ledger 读半边」（从最新回执 seed broker 使 NAV 跨 run 连续）在 ROADMAP 标注为**未完成**——当前每次 run 从 mandate 资本重新开始。
- 确定性主张：同 spec/date/broker state/数据响应 → 记录字节级一致（`run_cycle.py:11-15`）；唯一非确定源是冷 LLM 缓存，prompt cache 让重放精确。

## 5. HITL 与风控（★重点：硬拦截还是软约束）

**结论：风控是代码级硬闸门，不是 prompt 软约束；但 HITL（人工审批门）在代码中不存在，属规划。**

### 风控 = 确定性 clamp，LLM 无法逾越

- `hedge_fund/risk/limits.py#apply_limits`（82 行，全文件核心）：两条硬限制——`max_position_pct`（单票 |weight| 上限）+ `max_gross_exposure`（组合 |weight| 总和上限）。纯算术 clamp，顺序保证幂等（先单票封顶、再等比缩总量，只缩不放）。
- **「conviction requests, risk disposes」**（limits.py:4-5）：LLM 对账户的影响力到 `Signal` 为止——观点只能「请求」，风控用确定性代码「处置」。VISION.md 把这条列为不妥协原则之一："The LLM never touches the trade"——**LLM 只形成观点和叙述决策，确定性代码定仓位和下单，风控限额是 agent 无法突破的硬闸门**。
- 被砍掉的敞口**不重新分配**，留在现金（limits.py:8-10——重分配会让风控阶段有加仓能力，与其职责相反）。
- **每次 clamp 留审计事件**：`ClampEvent(limit, ticker, before, after)` 逐条记录进 CycleRecord（`risk/limits.py#ClampEvent`）——风控动作可解释、可回放。

### HITL 现状

- ❌ 无人工审批门/确认门/veto 代码。订单不经确认直接进 broker（模拟盘，无真实资金风险）。
- 规划中的 HITL（【文档】VISION.md "What we will not compromise on"）：①「自我改进是门控的」——基金自己发明策略可以，但未经 CPCV/PBO 验证门不得获得资本，且**晋升进 live book 默认保持人工批准**；②「paper 先于 real，live 是 opt-in 且默认关闭」。当前 `hedge_fund/validation/__init__.py` 只是空壳 docstring（CPCV/PBO ⬜ 未实现）。
- 人工介入点事实上在「研究回路」：人跑回测、比较 benchmark、自己决定 promote（VISION.md Level 1 lab）。

## 6. 工具与业务系统集成

- **三个 Protocol 接口（结构化类型，runtime_checkable）切开外部世界**：
  - `DataClient`（`hedge_fund/data/protocol.py`）：唯一实现 FDClient（financialdatasets.ai REST，`data/client.py`，带 5/15/30s 重试与 FDClientError——基础设施错误与「无数据」严格区分，回测必须崩而非当作空数据）。
  - `Broker`（`hedge_fund/brokers/protocol.py`）：positions/cash/place_order 三方法；唯一实现 SimBroker（内存撮合、按参考价全量成交——**无真实券商通道**）；PaperBroker/真实 broker 为 ROADMAP 规划。刻意不提供 equity() 方法：「只有管线知道 point-in-time marks，broker 报告持有什么，管线计算值多少」。
  - `LLMClient`（`hedge_fund/llm/client.py`）：complete(system,user)->str。
- **agent 无工具调用能力**：LLM agent 不持工具、不能调 API——它只读快照文本、产出 JSON。取数由管线统一经 CachedDataClient 预取。读写隔离靠「agent 根本不接触执行通道」达成。
- 凭据：env var 优先，`~/.hedge-fund/.env` 兜底（`tui/keys.py#apply_credentials`，load_dotenv 不覆盖已有环境）；TUI 首次使用时掩码输入并**外科手术式单行改写** .env（不重写整文件），chmod 0600（`keys.py#save_credential`）。

## 7. 部署与产品化

- 形态：pipx/uv 安装的本地 CLI+TUI 单用户应用；`aihf` 入口（pyproject scripts）。❌ 无 Docker/server/多租户/API/队列。
- 成本控制：靠两层磁盘缓存（prompt cache + data cache）而非配额系统；❌ 无 token 计量/预算（llm/watch.py 的 ThesisStream 只是流式渐进解析展示，观测体验用）。
- 可观测性：rich stderr 摘要（run.py:153-167：signal 数、abstain 数、clamp 数、订单数、NAV）+ 全量 JSON 回执落盘。TUI 有删除确认弹窗（ConfirmDeleteScreen，列明将删文件清单）——产品细节意识好。
- ❌ 无鉴权（本地单用户，无需）；无测试之外的 CI。

## 8. 对本项目的适用性

硬约束对照：①独立服务+API 通信——❌ 本仓是本地单机应用，无任何服务化设计可抄；②图编排——❌ 它反其道行之（见下）；③硬性审批/审计/合规——**审计与硬风控正是它最强的部分**。

### 可借鉴模式（按价值排序）

1. **「LLM 影响力终止于 Signal」的分层闸门**（`risk/limits.py#apply_limits` + VISION 原则）：LLM 只产观点（含置信度+理由），仓位合成、风控 clamp、订单生成全是无 I/O 纯函数，每步输入输出进审计记录。对财务合规场景这是可直接移植的架构骨架——Java 侧把 `blend_signals/apply_limits/build_orders` 做成无副作用服务，LLM agent 的输出被 schema 校验后进纯算术管线，风控 clamp 事件（before/after/limit/ticker）逐条入审计库。
2. **PromptCache 三合一**（`llm/cache.py`）：缓存=审计记录=调试踪迹，key 为内容哈希、记录含精确 prompt/response/snapshot_hash/created_at。财务 agent 的「每个 LLM 决策可回放」合规要求可以用同一设计满足——审计日志天然就是缓存，不额外付存储/一致性成本。快照 content_hash 排除 as_of 的「同数据不二次付费」也值得抄。
3. **Point-in-time 快照 + fail-loud/abstain 失败契约**（`features/snapshot.py`、`llm_agent.py:15-21`）：给 agent 的输入先收敛成可哈希的确定快照（预计算派生指标）；数据层错误传播（宁可崩不可静默中性），LLM 层错误 abstain 且从合成分母中剔除。对回测/审计场景「数据不可得」与「模型失败」必须语义分离。
4. **一管线三模式（只换时钟与 broker）**（`run_cycle.py` docstring、`backtesting/fund.py`）：同一编排代码跑回测与生产，杜绝研究实现与生产实现漂移——对「工作流需可重放审计」的合规需求是同构的（回放=历史时钟+记录的响应）。
5. **`extra="forbid"` 的 spec 即数据**（`fund/spec.py`）：mandate 是可序列化 YAML，TUI/CLI/（未来的）chat LLM 都产同一格式，「下游永远不需要知道基金是谁 authored」；风控限额是 spec 的一级字段。

### 不可迁移点

- 无服务化/多租户/并发的一切（本地文件即数据库）。
- 无图引擎——若硬约束②要求显式图编排（LangGraph4j 等），本仓的「顺序纯函数管线」是另一种哲学：它证明财务决策链可以完全不需要自由度高的 agent 图。选型时可作「反例对照组」：把拓扑压扁为「并行投票→算术合成→硬闸门」后，可审计性和确定性大幅上升，而损失的是 agent 间辩论与动态分工（对照 TradingAgents/FinRobot V0）。
- TUI（textual）无对应 Java 生态需求。

### 避坑

- 教育项目：README/VISION 中的 paper/live/ledger/scheduler/CPCV 大多为 roadmap 而非代码（【文档】级证据），引用时必须核对 ROADMAP 状态列（如 ledger 只有「写半边」）。
- 市值取数刻意避开 `get_market_cap()` 而用最近 filed 行（`snapshot.py:139-143` 注释：company_facts 的 market_cap 是 latest-only，回测里是 lookahead）——财务数据 PIT 陷阱的现成案例。
