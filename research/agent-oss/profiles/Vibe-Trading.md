# Vibe-Trading 解剖档案

> 基线：~/develop/opensource/Vibe-Trading @ f84b2977 (2026-09-12)；canonical HKUDS/Vibe-Trading；MIT；HKUDS（港大数据科学实验室）出品，较新（README 298KB、CHANGELOG 106KB，工程化程度远超一般新项目）。
> 状态：活跃日更；909 个 py 文件 + React/Vite 前端 + Electron 壳 + 15+ IM 渠道。

## 1. 产品定位与形态

开源投研工作区（research workspace）：自然语言 → 市场数据加载、策略生成、回测、报告、导出（Pine/TDX/MT5），外加「自主交易（autonomous trading）」——用户显式授权后，在限额内通过自有券商账户真实下单（README「It holds no funds and never trades outside the limits you set, and you can halt it instantly」【文档】，代码实现见维度 5【核心】）。

形态五合一，共用同一 session runtime【核心】：
- CLI（`pip install vibe-trading-ai`，agent/cli/）
- FastAPI 服务（agent/api_server.py，绑定 127.0.0.1:8899）+ React/Vite Web UI（frontend/）
- MCP server（agent/mcp_server.py——把本产品挂到别人的 agent 上，Path C）
- Electron 桌面壳（desktop/electron）
- IM 渠道（agent/src/channels/：telegram/slack/discord/matrix/whatsapp/signal/qq/napcat/weixin/wecom/feishu/dingtalk/msteams/email/mochat/websocket，共 16 个 + pairing 配对机制）

目标用户：个人研究者/交易者（单用户本地优先设计：文件系统存储、loopback 绑定、OS vault 凭据——见维度 8 不可迁移点）。

## 2. Agent 执行架构

两条执行路径，均为自研（**不是 LangGraph**）：

**(a) 单 agent ReAct 主循环**（agent/src/agent/loop.py#AgentLoop，3101 行，仓内「protected tree」）【核心】：自研 ReAct + 五层上下文管理（L1 microcompact 修剪旧工具结果 / L2 无 LLM 的 context_collapse 折叠长文本 / L3 LLM 结构化摘要 + token 预算尾部保护 / L4 模型显式调 compact 工具触发 L3 / L5 第 N 次压缩增量更新旧摘要）；连续只读工具线程池并行执行；心跳、trace、content filter、背景工具管理。

**(b) Swarm 多 agent DAG**（agent/src/swarm/）【核心】：
- **声明式拓扑**：YAML preset 定义 `agents`（id/role/system_prompt/工具白名单/skills/max_iterations=25/timeout=300s/max_retries）+ `tasks`（DAG：depends_on / blocked_by 运行时收缩 / input_from 上游 summary 注入）+ `variables`（用户填参）。用户目录 `~/.vibe-trading/swarm/presets/` 可覆盖内置（presets.py）。
- **执行**：`SwarmRuntime` 按拓扑分层并发执行（runtime.py#_execute_layer），每 task 一个 ReAct worker（worker.py#run_worker），产出 artifact 文件 + summary，消息与 summary 持久化到 run 目录；worker 结果六分类（completed/failed/timeout/**token_limit/incomplete**/cancelled——`incomplete` 专门捕获「跑完但没实质交付」：plan-only stub、伪造/mock 数字、未解析工具标记、数据 agent 零调用零报告，models.py#WorkerStatus）。
- **30 个内置 preset**（swarm/presets/）：investment_committee（bull/bear 并行 → CRO 独立审 → PM 终审）、risk_committee、宏观/量化/加密/可转债/信用等垂类团队。
- **对比 TradingAgents**：Vibe 是「并行生成 + 串行审阅」的 DAG 分层（bull/bear 同时跑，无交替辩论轮）；TradingAgents 是「交替辩论循环」。Vibe 的辩论张力放在同一 preset 的角色 prompt 对抗 + CRO 独立评审上。
- **失败恢复**：run 级 resume（runtime.py#_apply_resume_overlay）——保留已完成 task（artifacts 搬迁进新 run 目录），但两个失效条件：task 定义或其 agent spec 变了不保留；任何传递上游重跑则不保留（防 stale summary）。README 示例 `vibe-trading swarm resume`。
- **反幻觉三板斧**：① grounding 预取——run 创建时对 prompt 里的标的抓真实 OHLCV 注入（grounding.py，防训练数据价格）；② build_worker_prompt 的「Data Citation Discipline (HARD RULE)」——每个数字必须溯源到本 run 工具结果/Ground Truth/已溯源上游，否则必须标注无法获取（worker.py#build_worker_prompt）；③ preset prompt 里的领域否定清单（如「无 DCF 引擎不得报 DCF 内在价值」「无借券费数据不得报 borrow fee」，investment_committee.yaml）。

## 3. 技术底座

Python 3.11 + FastAPI；**自研 agent loop 与 swarm runtime（无 LangGraph/LangChain 编排）**，LangChain 1.x 仅作 LLM provider 适配层（langchain/langchain-openai，可选 anthropic/deepseek，requirements.txt）；React/Vite + TS 前端；自研 quantlib（VaR/CVaR/GPD 尾部/MC/回测）+ 462 个 alpha 的因子库（factors/zoo：qlib158+alpha101+gtja191+学术+基本面）。OpenBB bridge。框架层对照见 agent-framework/profiles/langchain.md（本仓只用其 ChatModel 抽象，未用编排）。

## 4. 状态与持久化

- **会话**：文件系统 `sessions/{id}/session.json + messages.jsonl + attempts/{id}/attempt.json`（session/store.py#SessionStore）；流式回复崩溃安全——ResponseCheckpoint 节流快照（首 token 立即落盘、后续 0.25s 合并、stream_reset 重写，session/checkpoint.py）。
- **Swarm run**：`.swarm/runs/{id}/run.json`（聚合根：agents/tasks/status/tokens/provider/model/grounding_data）+ `events.jsonl`（run_started/task_completed/task_blocked…，SSE 回放 + 审计）+ 每 agent artifact 目录。
- **治理账本**（见维度 5）：`live/audit.jsonl`（fsync）+ `live/audit_chain.jsonl`（哈希链）。
- **Run manifest——方法论指纹**（governance/manifest.py#build_run_manifest）【核心】：内容寻址指纹 = system_prompt hash + 每个 skill 的 (name, content_hash) + 工具注册表名单+hash + 关键包版本 → `manifest_hash`。刻意排除 timestamp/run_id（「两次运行方法论相同则 hash 必须相同」），`diff_manifests` 能指出是哪个 skill 的正文变了。回答审计问题「这个数字是在什么方法论下产生的」。manifest 模块零运行时依赖（不 import agent 树）、绝不自己取时钟。
- **跨会话记忆**（memory/：hierarchy/compression/lifecycle/search_index/semantic_links，sessions.db 索引）+ workspace memory（agent/memory.py）。
- **Portfolio 快照**：`portfolio/portfolio.sqlite3` 不可变快照，估值方法论变更后新旧历史不直接比较（避免假盈亏）。
- 并发：swarm 层内 worker 并行；ledger 跨进程 POSIX flock。

## 5. HITL 与风控 ★★（全仓最大亮点，开源产品中罕见的完整 bounded-autonomy 实现）

真实下单：14 个券商连接器（trading/connectors/：alpaca/binance/dhan/etoro/futu/ibkr/longbridge/mt5/okx/robinhood/shoonya/tiger/trading212/zerodha）。合规链全部在 `agent/src/live/` + `governance/`【核心】：

1. **Mandate——三层不可变授权合同**（live/mandate/model.py）：frozen dataclass（**刻意不用 Pydantic**：零验证面，agent 无从利用）。Layer(a) `HardCaps` 定量上限：单笔名义 / 总敞口 / 杠杆 / 工具类型白名单 / 日交易数；资金上限由券商侧专用账户余额物理执行（「agent 物理上无法突破的天花板」，本地只做纵深防御镜像）。Layer(b) `UniverseConstraint` 选择域：资产类别桶 + 市值/流动性下限 + 排除名单——**不是 ticker 白名单**（「那会杀死 agent 的发现能力」），agent 在结构过滤内自由选标的。`ConsentMeta` 出处：consent_token_sha256（绑定同意 UX 产出的人工点击 artifact）、broker/account_ref、**expires_at 默认 30 天强制过期**（「live mandate 不许永生」）。`flatten_on_halt` 默认 False（cancel-only 安全默认）。
2. **授权写入唯一路径**（live/mandate/commit.py#commit_mandate）【核心模式】：commit_mandate **不是工具、不进 agent 工具注册表、不 importable-by-discovery**，只由 API `POST /mandate/commit` 调用且需要 surface 来源的 consent_ack——「命门不变量（the 命门 invariant）：结构性保证，不是 prompt 级保证」。被劫持/幻觉的模型无法自我授权。agent 侧的 `propose_mandate_profiles` 工具只能写 proposal（持久化不授予任何权限）。
3. **下单门**（live/order_guard.py#LiveOrderGuardTool）：MCPRemoteTool 子类，**只包装券商的下单类（WRITE/UNKNOWN）远程工具，读工具走裸路径**。每次 execute 的 fail-closed 检查链：mandate 有效 → 未过期 → kill switch 未触发（在任何 broker 调用之前）→ 订单意图可解析 → 经券商 READ 工具快照持仓/余额 → check_mandate。三态裁决：ALLOW 转发 / 结构性违规（universe/instrument）**DENY** / 定量违规 **PAUSE_FOR_REAUTH**。日计数只在「确认 ALLOW 且 broker 返回非 error」时消耗（失败转发不烧次数）；`repeatable=False`——**活单绝不静默重试**。quantity 订单强制取实时报价，按 max(显式名义, qty×价) 执行上限，取不到报价即 DENY。
4. **check_mandate 纯决策函数**（live/enforcement.py）：固定顺序八查（exclude-list → instrument → asset-class → 单笔 → 总敞口 → 杠杆 → 日次数 → 资金），**任何不可解析输入/缺数据 = DENY**（fail-closed）；CN/IN 等无行情 loader 的市场市值下限直接 fail-closed（注释明说 intentional）。
5. **SDK 直连门**（live/sdk_order_gate.py）：tiger/alpaca/okx/binance/futu 直连 SDK 的函数式门，与 MCP 门同一 ceremony。
6. **读写分类三级阶梯**（live/classification.py）：券商 MCP 工具运行时发现，分类 precedence = ① server 自述 annotations（readOnlyHint，只能把工具往 read 降级、永远不能把 WRITE 洗成 read）→ ② 维护者 curated map（**map 赢过 annotations**——「谎称 readOnlyHint=True 的 place_order 骗不过 curated WRITE」）→ ③ default-deny：UNKNOWN 一律当 WRITE 走门。引用 MCP 规范自己的诚实警告（不可信 server 的 annotations 不可作为安全依据）。
7. **Kill switch**（live/halt.py）：文件系统哨兵 `<runtime_root>/live/HALT`（全局）+ `<broker>/HALT`（单券商），**文件存在即停，payload 损坏仍视为 tripped（fail-closed）**，由用户/外部 watchdog 直接 touch——「独立于 LLM 合作」，loop 卡死、SSE 挂掉也有效；每笔下单前检查。
8. **审计三 sink + 双账本**（live/audit.py + governance/ledger.py）：每笔 live action（下单/被拒/mandate commit/breach/halt 触发与清除）扇出到 ①合规账本 `audit.jsonl`（每次 append fsync）+ ②**哈希链副本 `audit_chain.jsonl`**（agent/src/governance/ledger.py：每条记录 seq + prev_record_hash + record_hash，改/删任何历史记录会断其后整条链，verify_chain 可验；append 前验证整链、断链拒绝追加 LedgerCorruptionError；flock 跨进程）——「show me everything the agent did with real money」的合规级记录，与 run 目录隔离、survive run 清理 ③per-run trace + SSE `live.action` 事件。redaction 在进任何 sink 之前执行（broker 响应里的 OAuth token/账号/PII）。**问责链**：mandate_snapshot_ref + consent_record_ref 让每笔实盘单可回溯到授权它的人工点击。
9. **崩溃安全**（live/pending_action.py）：下单前写 crash-safe 副作用标记，重启后拿 broker 证据（RecoveredOrderEvidence）对账；**对账而非重发**（runner.py：「reconciliation, not re-send, closes the cross-restart double-trade hole」——mutation 调用永不自动重试）。
10. **自主实盘 runner**（live/runtime/runner.py）：常驻循环每 tick 固定顺序 `halt → mandate 主动过期检查 → 对账 → 自主 turn → audit`；mandate **内联 pin 进 turn prompt** 以活过主循环五层压缩；agent 只经公开入口（SessionService.send_message）调用，runner 是 caller 不碰 protected 树。
11. **Advisory 层**（live/advisory/）：门**外**的观察性风险意见（外部 /review 服务、规则引擎），**fail-open**（provider 挂了订单照走，REVIEW_UNAVAILABLE）、默认关（VIBE_TRADING_ENABLE_ADVISORY）、**绝不阻塞**——与 mandate 门的权威分离写得极清楚（「advisory never block; mandate gate remains the sole authority」）。
12. Swarm 内的风控（risk_officer/CRO preset）是 prompt 层——与研究层一致；**所有硬风控都在工具出口（live 层），不在 agent 拓扑里**。

对照硬约束③：这是「prompt 层风控 + 代码层硬门」分层的教科书实现。

## 6. 工具与业务系统集成

- 自研 ToolRegistry（agent/tools.py）；核心工具：bash/read_file/write_file/load_skill/get_market_data/backtest/get_options_chain 等 + 文档解析（PDF/DOCX/XLSX/PPTX/图像 OCR、vision 读图）。bash 工具在容器内以 vibe-sandbox 降权用户跑 LLM 生成代码（runner.py drop privilege，compose 保留 SETUID/SETGID 专为此）。
- **数据源智能回退链**（loaders registry：yfinance→akshare、okx→ccxt），数据永不进工作树（compose 挂载 `:ro`，注释「no market data may ever land in the working tree」）。
- **券商读写隔离**（trading/connections.py + 各 connector classification.py/profiles.py）：profile 声明 capabilities（account.read/positions.read…）与 readonly 标志；**只有 readonly 且具备 account.read+positions.read 的连接**才能进只读 Portfolio 聚合页；连接注册表 connections.json credential-free，凭据进 OS vault/CredentialStore。Robinhood 走远程 MCP（工具名映射 connectors/robinhood/mcp.py），tiger 等走本地 SDK。
- **Skills 体系**（agent/src/skills/，SKILL.md 实数 90）：markdown 知识包（SKILL 正文 + references/ + scripts/），load_skill 按需注入描述、agent 自主加载全文；用户目录覆盖内置——「把有用例行流程沉淀成可复用工作流」的产品化路径。
- 脱敏贯穿：redact_payload/redact_text 用于 trace/audit/公开 metadata（credential 正则 + 高熵 token + endpoint 形状检测，swarm/models.py#public_metadata_value）；错误信息 collapsing home 路径（CWE-209）；access log 脱敏 filter。
- MCP 双向：作为 client 消费券商 MCP 工具，也作为 server（mcp_server.py）供外部 agent 调用。

## 7. 部署与产品化

- **Docker 安全加固样板**（Dockerfile + docker-compose.yml）【核心】：多阶段构建（前端 build → hash-pinned `--require-hashes` 依赖锁 venv）；运行时容器 read_only rootfs + `cap_drop: ALL`（仅加回 SETUID/SETGID 供沙箱降权，且注释解释为何与 no-new-privileges 不冲突）+ `no-new-privileges:true` + mem 4g / cpus 2 / pids 512（「bound a single runaway backtest」）+ 只绑 127.0.0.1 + digest 锁定基础镜像。
- **API 安全**（src/api/security.py）：API key、一次性 SSE ticket、loopback-origin/host 校验（防 DNS rebinding/跨站浏览器请求）、shutdown 授权、settings 写独立鉴权。
- 多入口共 runtime：CLI/API/Web/MCP/IM 渠道全部驱动同一 SessionService。
- 可观测：run 目录 trace（每 record fsync）、SSE 事件流、token 预算（worker token_limit 状态 + run 级累计）、run manifest 指纹、CI grep 门禁（tools/ci_grep_gates.sh）。
- 成本控制：per-agent max_iterations/timeout/token 预算；容器资源上限；advisory 超时。

## 8. 对本项目的适用性

四条硬约束里命中三条半——**A 组与本项目（Java + 独立部署 + 图编排 + 硬审批审计）最贴合的仓库**：

- **① 独立部署+API：✅** agent 服务（FastAPI）独立运行，与外部系统（券商/数据源/IM）全部经 MCP/SDK/HTTP 边界通信；多前端共 runtime。可直接类比「agent 服务与业务服务 API 通信」的拓扑。
- **② 图编排：⚠️/✅** 无通用图引擎，但 YAML 声明式 DAG preset + 拓扑分层调度 + 定义变更感知的 resume overlay，覆盖了「声明式工作流 + 部分失败恢复」的工程需求。若 Java 侧选图引擎（LangGraph4j 等），其 preset 格式（agents+tasks+input_from+variables）与「任务定义变了/上游重跑了则丢弃已完成结果」的 resume 语义值得照抄。
- **③ 审批/审计/合规：✅✅** 开源仓里最完整的 bounded-autonomy 合规链，几乎每个组件都能映射到财务场景：
  1. **「授权不可达」模式**（mandate/commit.py）：授权/额度写入路径物理上不在 agent 可调用面内，只能从受信服务面（API + 人工 consent_ack）进入——财务系统里「调整付款限额/解除冻结」应同样做成 agent 不可调用、仅审批服务可写的操作。结构性保证 > prompt 约束，是其自称的「命门不变量」。
  2. **fail-closed 决策纯函数 + 三态裁决**（enforcement.py#check_mandate → DENY/ALLOW/PAUSE_FOR_REAUTH）：固定检查顺序、不可解析即拒、结构性 vs 定量违规分流（结构性=永久拒绝，定量=暂停待重新授权）——可直接翻译成 Java 的 PaymentGate：黑名单 → 客户/科目校验 → 单笔限额 → 总敞口 → 频次 → 额度，每步 fail-closed。
  3. **哈希链审计账本 + run manifest 指纹**（agent/src/governance/ledger.py + manifest.py）：seq+prev_record_hash 的防篡改账本（断链拒绝追加），与「方法论指纹」（prompt/skills/工具/版本 → 一个 hash，可 diff 两次运行的方法论差异）——财务 agent 的两大审计问题「记录没被改过」「结果在什么规则版本下产生」分别有先例。
  4. **文件哨兵 kill switch**（halt.py）：不依赖 LLM/SSE/主循环存活的物理制动；「对账而非重发」的崩溃恢复纪律（mutation 永不自动重试）。
  5. **读写三级分类**（live/classification.py，与各 connector 自带的 classification.py 是两回事）：不可信外部服务自述只能降级不能升级安全等级 + curated map 优先 + default-deny——对接外部 MCP/业务 API 时的权限分级标准做法。
- **最有借鉴价值 top 2**：模式 1（授权不可达）+ 模式 2（fail-closed 门）；次选 3（审计双账本）。
- **不可迁移点**：单用户本地优先（文件系统持久化、loopback 绑定、OS vault 凭据、文件哨兵）——企业多租户需把存储/身份/kill switch 分别换成 DB、IAM、服务化开关，但**语义可原样保留**；自研 loop/swarm 无图引擎生态（LangGraph 的 checkpoint/HITL 原语、langgraph4j 对应物）。
- **避坑**：advisory（fail-open、观察性）与 mandate gate（fail-closed、权威）的分离必须严格守住——文档反复强调「advisory never block」，混用会把外部依赖的可用性变成下单链路的可用性风险；frozen dataclass 的动机（零验证面防 agent 利用）提示：**给 agent 读的合同对象不要留可利用的解析空间**。
