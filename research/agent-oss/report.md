# 财务 Agent 参考架构研究报告——18 个开源 agent 产品应用架构解剖

> **任务**：为「Java 技术栈 + 财务领域企业级 agent」自研系统提炼参考架构模式。硬约束：① agent 服务独立部署、与业务服务通过 API 通信；② 图编排工作流；③ 硬性审批/审计/合规。
> **输入**：`profiles/` 18 份解剖档案（源码级证据）+ `dimensions/` 5 份维度分析。上游研究：`research/agent-framework/`（17 框架 × 15 维）。
> **证据等级**：【核心】核心代码 /【示例】examples /【文档】宣称 /【还原源码】sourcemap 还原（仅 claude-code-sourcemap）。全部基线与证据路径见档案。

## TL;DR

1. **没有可直接引入的依赖，只有可照抄的结构。** 18 仓中与三约束同时命中度最高的是 virattt 系之外的 Vibe-Trading（真实交易 + 五层风控 + 哈希链审计）与 opencode（server 即产品 + 审批完全外化 REST/SSE）——前者给合规骨架，后者给服务化形态。但两仓都不是 Java；Java 同栈样本（supersonic、DataAgent）恰好都缺审批与审计工程。结论：**抄模式、不引依赖**。
2. **审批架构的共识形态已收敛**：规则引擎进程内求值第一道（人只接灰区）+ 审批外化为可重放事件（REST+SSE，执行线程挂起）+ 执行出口二次校验 + 授权写入路径物理上不在 agent 工具面内（「授权不可达」）。
3. **图编排的正确姿势是「静态图 + 计划驱动路由」**（DataAgent 样板）：拓扑静态可审计，LLM 动态性只出现在四个合法位置——条件边循环 / 计划驱动路由 / 声明式 DAG / 图上 human 节点回环。
4. **风控必须分层齐备**：③ 处置层纯函数（管量）+ ④ 授权层不可达（管权）+ ⑤ 执行层 fail-closed 门（管不可逆动作）；只做 prompt 软约束的（FinRobot/TradingAgents）是决策建议器，做不了审批执行器。
5. **审计三台阶起步于「缓存即审计」**：每个 LLM 决策的 prompt/response/输入快照哈希按内容寻址落盘（ai-hedge-fund），合规回放零额外成本；资金/记账动作流升级哈希链账本（Vibe-Trading）。

## 1. 总览：18 仓对三约束的命中度

| 组 | 仓库 | 一句话 | ①独立部署+API | ②图编排 | ③审批/审计 | 主要贡献 |
|---|---|---|---|---|---|---|
| A | ai-hedge-fund | 层级投票 + 纯函数风控管线（v2 全量重写，无框架） | ❌ CLI | ❌ 顺序管线 | 🔶 硬 clamp 无 HITL | 「LLM 影响力终止于 Signal」、缓存即审计、一管线三模式 |
| A | FinRobot | README 宣称与开源代码落差极大（辩论/调度在闭源 V2） | 🔶 V1 FastAPI | ❌ AutoGen 群聊 | ❌ 全 prompt 软约束 | request_logs 审计中间件、反面教材集 |
| A | TradingAgents | LangGraph 单线主干 + 辩论-裁决（论文配套） | ❌ CLI/库 | ✅ StateGraph | ❌ 纯 prompt（README「PM 审批」无代码） | 计划驱动的反面——辩论拓扑、Pydantic 决策 schema、PIT 决策日志 |
| A | **Vibe-Trading** | 真实交易（14 券商）+ Mandate 授权合同 | ✅ FastAPI 多入口 | 🔶 自研 YAML DAG（语义等价） | ✅✅ 五层风控 + 哈希链账本 | **合规骨架最全**：授权不可达、fail-closed 门、问责链、对账不重发 |
| B | DB-GPT | AWEL 框架 + 新旧两代（ReAct agent / 场景管线）并存 | ✅ | 🔶 AWEL DAG | ❌ 确认门 fail-open 三缺陷 | 子 agent 扇出隔离五件套、confirm_actions 目录三消费、view message 审计 |
| B | **SQLBot** | 确定性多段流水线 + AST 硬闸 | ✅ FastAPI | ❌（无图，顺序管线） | 🔶 SQL 只读硬、无审批门 | **审计双平面**（chat_log × system_log）、check_sql_read 四层校验 |
| B | supersonic | Java/Spring ChatBI：S2SQL 受限方言 + Calcite 确定性翻译 | ✅ 多模块可拆 | 🔶 ChatWorkflowEngine 状态机 | 🔶 权限 AOP 强、审批流无 | **S2DataPermissionAspect**、语义层元模型（指标/维度/术语）、记忆双审 |
| B | WrenAI | 治理引擎化：MDL 语义层在 Git，编排外置给宿主 agent | ✅ CLI/MCP/SDK | ❌ | 🔶 policy 防火墙强、身份层在商业版 | **治理即代码**、policy.py SQL 防火墙范本、RLAC 声明式行权限 |
| B | **DataAgent** | Java + spring-ai-alibaba graph：固定 16 节点图 + 计划驱动 | ✅ Spring Boot 服务 | ✅ StateGraph | 🔶 HITL 暂停-恢复有、审批不落库 | **「固定图+计划驱动路由」图表达**、interruptBefore HTTP 协议、连接层三件套 |
| B | data-formulator | code-first：LLM 生成 pandas/DuckDB 代码，沙箱执行 | ❌ 本地研究工具 | ❌ 手写循环 | 🔶 inspection/action 双通道 | 计算可复算 + 代码即审计物、受限计划与自由代码双轨 |
| C | cline | 已 SDK 化：插件/CLI/hub daemon 三形态同核 | 🔶 hub daemon | ❌ 自研 loop | ✅ 三段管线 fail-closed + approvedRevision | **审批版本绑定（防 TOCTOU）**、审批可重放事件、上下文溢出强制确定性恢复 |
| C | **codex** | Rust 单二进制多入口；双轴审批 × Starlark 规则引擎 | ✅ app-server | ❌ 自研 loop | ✅✅ 执行前三态预判 + amendment | **「批准并记住」最高形态**、双轴模型、环境级锁死、rollout 持久化 |
| C | gemini-cli | TOML 五层优先级带 + 确认总线 + a2a-server 桥 | ✅ a2a-server | ❌ | ✅ 三态策略引擎 | Admin 层永远压过用户、压缩七节模板、审批远端代答先例 |
| C | **opencode** | **server 即产品**：全部能力 REST+SSE，TUI 只是 client | ✅✅ | ❌ | ✅ 审批完全外化 | **审批外化 API 组**（Spring 可照抄端点语义）、SQLite 事件溯源、location 多租户路由 |
| C | OpenHands | 事件溯源架构（经典 Python 版，HEAD 已清仓迁移） | ✅ headless | ❌ | ✅ 动作预确认 + 二次校验 | EventStream 单一真相源、写时脱敏、执行侧纵深防御、每会话容器 |
| C | claude-code (sourcemap) | 生产级 harness 权限内核（v2.1.88 还原源码） | — | ❌ | ✅✅ 有序求值管线 + bypass 免疫 | **DecisionReason 可解释权限**、两级压缩 + 状态恢复清单、审批四路竞速 |
| D | gpt-researcher | 固定流水线（LLM 是文本处理器不是决策器） | ✅ FastAPI | 🔶 旁路 LangGraph | ❌ | 能力声明式契约、分步成本归集、并发检索编排 |
| D | browser-use | 感知-行动循环 + `<secret>` 占位符协议 | 🔶 | ❌ | ❌（宿主实现） | **凭据引用协议**、动态动作空间裁剪、双层变更守卫 |

（状态备注：supersonic 维护模式、DataAgent 1.0.0-RC、SQLBot 许可 NOASSERTION、OpenHands 引用锚定 git 历史 e8249f00a、claude-code-sourcemap 为非官方还原源码。详见 README 对象表。）

## 2. Pattern Catalog（模式清单）

三级分类标准——**A 直接可用**：概念与结构可同构映射 Java/Spring，照抄结构即可；**B 需改造**：模式成立但关键实现要按 Java 生态/企业环境重做；**C 仅参考**：思想与方向有效，实现不可迁移或场景不同。每条注明来源档案与迁移注意点。

### 2.1 A 级：直接可用（30 条）

**审批与风控（约束③核心）**

| # | 模式 | 来源 | Java + 图编排迁移要点 |
|---|---|---|---|
| A1 | **审批外化 API 组**：建请求 / 跨会话待审总表 / reply(once/always/reject+message) / saved 授权 CRUD + SSE 推送，执行线程挂起等待 | opencode 档案 §5.3（`packages/protocol/src/groups/permission.ts`） | Spring MVC + SseEmitter 一比一照抄端点语义；挂起用 CompletableFuture；数据模型一步到位（action/resources/save/source 四元组，避开 opencode v1/v2 双代坑）；reject 的 message 回喂模型做纠错 |
| A2 | **审批是可重放事件**：approval.requested 挂 pending map、重订阅即重放、无人在线不丢单不隐式作答、审批端是 capability 声明 | cline 档案 §5（hub `approval-handlers.ts`） | Spring 事件 + WebSocket/SSE 重放；多审批端（Web 工单/移动端）天然支持 |
| A3 | **审批三段管线 + fail-closed 回调**：hook → 策略 → 审批回调，回调未配置/抛错即拒绝 | cline 档案 §5 | AOP/HandlerInterceptor 链 + ApprovalCallback 接口；宿主回调实时读最新设置（防策略快照过期——真踩过的坑）；cline SDK 默认 autoApprove=true 不可照搬，安全责任在服务端 |
| A4 | **双轴权限模型**：审批策略（每步审/按需/白名单/全拒）× 数据访问模式（只读/受限写/放开）正交组合 + 环境级锁死（部署档不可被会话覆盖） | codex 档案 §5（`AskForApproval` × `SandboxMode`） | Java 枚举组合即可；财务默认应「全审批 × 只读」，放开是逐档显式授予 |
| A5 | **有序求值管线 + bypass 免疫位 + DecisionReason**：deny→ask→工具自评→硬合规判定（连 bypassPermissions 也要问）→mode→allow，每个决策附结构化理由 | claude-code-sourcemap 档案 §4【还原源码】 | sealed interface + record 建模决策理由，直接进审计报表；超限额/敏感科目判定放在任何提权模式之前 |
| A6 | **审批与被审内容版本绑定**（approvedRevision：内容一改即撤销审批、与 spec 对账不一致 fail-closed）**+ 批准并记住=可审计规则修订**（amendment：谁/何时/批了什么） | cline 档案 §5、codex 档案 §5 | 「批这版分录 + 以后该供应商 10 万以下自动过」的正确形态：规则修订事件（带审批人签名）+ 内容 hash 绑定，绝非内存 yes 集合 |
| A7 | **执行侧二次校验**：执行器收口处独立复核审批状态（只执行 CONFIRMED），与决策层形成纵深防御 | OpenHands 档案 §5 | 业务 API 调用出口统一再查审批单；防中间层缺位/被绕过 |
| A8 | **fail-closed 决策门 + 三态裁决**：固定检查顺序纯函数，任何输入不可解析即 DENY；结构性违规 DENY / 定量违规 PAUSE_FOR_REAUTH 分流 | Vibe-Trading 档案 §5（enforcement.py#check_mandate 八查） | 付款门照抄检查序列（黑名单→科目→单笔→累计→频次→预算）；「宁可误拒不可放行」 |
| A9 | **授权不可达**：限额/白名单写入口不是工具、不进注册表、不可被自省发现；只从审批服务 API + 人工确认进入；agent 面上只有 propose 类工具 | Vibe-Trading 档案 §5（commit_mandate 命门不变量） | 财务「调额/解冻/科目白名单维护」同构处理——比 prompt 约束强的结构性保证；授权合同带生命周期（默认 30 天过期） |
| A10 | **granular 关闭=自动拒绝**：用户关掉某类审批询问，系统按拒绝处理而非跳过（防审批疲劳全点同意） | codex 档案 §5 | 审批疲劳是财务场景真实风险（量大后人全点同意），交互设计层就要防 |

**状态与审计（约束③核心）**

| # | 模式 | 来源 | 迁移要点 |
|---|---|---|---|
| A11 | **事件溯源会话存储**：event(aggregate_id, seq) + 唯一索引 + 会话/消息/part 规范化三表；审批/成本/风险分/压缩皆一等事件类型 | opencode 档案 §4.1、codex 档案 §4（TokenUsageRecord/SecurityRiskScore 独立持久化项） | Spring Data/JPA 直接建模；JSONL 只做归档/合规报送格式不做主存；gemini-cli 全量重写式存储是并发反例 |
| A12 | **审计双平面**：执行面逐 LLM 调用留痕（操作枚举+完整 prompt+token+时长）× 管理面声明式操作日志（注解驱动、IP 链解析、敏感 header 排除、删除前资源名补录） | SQLBot 档案 §4/§5 | Java：Spring AOP + 自定义注解完全同构；再叠 DB-GPT view message（用户最终所见独立落库）成三线齐备 |
| A13 | **缓存即审计**：每个 LLM 决策的 prompt/response/输入快照哈希按内容寻址落盘，缓存=审计=调试三合一 | ai-hedge-fund 档案 §4（llm/cache.py） | 合规回放零额外成本的起步设计；回测重跑 $0 |
| A14 | **PIT 决策日志 pending→resolved**：决策当下存 pending，事实发生后回填 outcome+反思，resolution_date 供时点过滤 | TradingAgents 档案 §4（memory.py） | 「当时知道什么」可回答；离线复盘闭环同时就是审计流水 |
| A15 | **审计绑定版本**：图形状签名进 checkpoint key（改图自动作废旧执行态）+ 方法论指纹（prompt/工具/版本→hash，可 diff） | TradingAgents 档案 §4、Vibe-Trading 档案 §4（manifest.py） | 审计记录必须绑定产生它的规则与拓扑版本，否则重放无法解释 |
| A16 | **哨兵值拒绝静默降级**：不可解析的决策返回 REVIEW 进人工队列；脏输出字段级归一（"N/A"/百分比/货币符号） | TradingAgents 档案 §5（schemas.py） | LLM 输出卫生的底线；解析失败必须可见 |
| A17 | **revert 两阶段**（stage→人工确认→commit，可反悔）+ checkpoint 恢复前先 stash 现状 | opencode 档案 §4.2、cline 档案 §4 | 财务「草稿/冲正」对应物：回滚本身不破坏现场 |
| A18 | **对账不重发**：不可逆动作前写 crash-safe 标记，重启后拿对端证据关闭重发窗口，mutation 永不自动重试 | Vibe-Trading 档案 §5（pending_action.py） | 付款/过账类动作的崩溃恢复纪律；重发窗口=双倍付款风险 |

**工具与集成（约束①核心）**

| # | 模式 | 来源 | 迁移要点 |
|---|---|---|---|
| A19 | **能力面收窄**：deny 的工具从发给 LLM 的工具列表**移除**（看不见即不可被注入诱导）；按用户权限/账套/场景动态裁剪工具面 | opencode 档案 §5.1、browser-use 档案 §2（domains 动作裁剪） | 优先于一切拦截器；全量注册+执行时拦截是下策 |
| A20 | **工具目录单源真相**：注册中心 + 读写权限声明 + 审计元数据三合一，审批门/子 agent 过滤/工具列表裁剪/审计打点四处消费同一份声明 | codex 档案 §5（FileSystemSandboxPolicy 双处执行）、DB-GPT 档案 §5（confirm_actions 三消费） | Spring Bean + 注解 + 配置库；修掉 DB-GPT 三缺陷（状态入持久层、拦截 fail-closed、resolve 带操作者身份） |
| A21 | **执行边界 AOP 权限注入 + 透明回执**：`@S2DataPermission` 切面强制注入行权限 WHERE + 列敏感级校验 + QueryAuthorization 回执告知「结果已过滤+条件+找谁申请」 | supersonic 档案 §5（S2DataPermissionAspect.java，**Java 原生**） | 直接照抄结构；过滤行为对用户可解释可直接进合规报告 |
| A22 | **SQL 六层校验**：根白名单+全树禁写扫描 → 方言危险函数清单 → AST 表名白名单（不信任 LLM 自报）→ 语义层表封闭 → 改写后复查（fail-closed）→ 连接层 readonly/maxRows/timeout | SQLBot 档案 §5、WrenAI 档案 §5、DataAgent 档案 §6（组合结论见 dimensions/B §4） | JSqlParser / Calcite validator 同构实现；六层各挡一类逃逸；prompt 约束（LIMIT 写提示词）与后置截断都是假限制 |

**执行架构（约束②核心）**

| # | 模式 | 来源 | 迁移要点 |
|---|---|---|---|
| A23 | **固定图 + 计划驱动路由**：拓扑静态可审计，LLM 规划 Plan JSON（schema 强约束 + 工具白名单 + 必填参数校验）作为状态变量驱动确定性 dispatcher，步进游标由代码执行 | DataAgent 档案 §2.2（workflow/node/PlanExecutorNode.java，**Java 原生**） | 「先出方案→审批→逐步执行」的最直接图表达；计划可整体重生成（失败原因回喂，计数封顶）；补 DataAgent 缺口：审批后执行前再加执行级确认、审批数据落库 |
| A24 | **图上 human 节点回环**：interruptBefore + checkpoint.nextNodeId + updateState(反馈) + resume 断点续跑，HTTP 层 `HUMAN_FEEDBACK_REQUIRED` 事件 | DataAgent 档案 §5、gpt-researcher 档案 §2（multi_agents human 节点） | HITL 是图的一等节点而非外挂；审批拒绝→带反馈重规划（max 3 次）；与 A1 外化审批 API 组合 |
| A25 | **条件边循环 + 计数终止 + MsgClear**：辩论/审查回环用条件边+纯计数器（token 可预算）；阶段结束裁剪上下文、只向下游传结构化报告字段 | TradingAgents 档案 §2（LangGraph conditional_logic） | 图上可预算的循环；path_map 全量映射防 fall-through |

**上下文与凭据**

| # | 模式 | 来源 | 迁移要点 |
|---|---|---|---|
| A26 | **压缩三件套**：阈值参数化 + overflow 兜底 + 溢出恢复强制确定性降级（绝不赌再一次 LLM 调用）；固定节摘要模板（目标/约束/待办/关键文件是公约数）+ 压缩后状态恢复清单 | cline 档案 §4、gemini-cli 档案 §4、claude-code-sourcemap 档案 §6（六方共识见 dimensions/C §3） | 原文 append-only 不可变、摘要旁挂可校验可重生成；连续失败熔断（3 次）；财务长会话摘要模板需本地化（叠加科目余额/未决事项节） |
| A27 | **工具输出落盘指针**：大结果集（报表/流水）超阈值全文落文件，上下文只留占位+路径按需取回 | gemini-cli 档案 §6、opencode 档案 §6 | 财务大报表场景直接可用；对象存储 + 引用 |
| A28 | **凭据引用协议**（secret 占位符）：LLM 全程只见键名清单；执行层域限定替换真值；回注消息只写 `Typed <password>`；落盘前再脱敏；未锁域白名单启动即警告 | browser-use 档案 §6 | 「密码不出密管、LLM 与审计全程只见掩码」——Java 凭据引用协议：KMS 存真值 + 引用键流转 + 执行层解析 + 展示层打码 |
| A29 | **失败原因显式状态键驱动定向重生成**：`SQL_REGENERATE_REASON` / `PLAN_VALIDATION_ERROR` 式错误原因入状态，AST 结构校验在前、LLM 语义校验在后双闸门；高频错误先建确定性本地修复器 | DataAgent 档案 §2.4、data-formulator 档案 §2.3 | 纠错回路不靠「错误文本扔给模型碰运气」；<1ms 确定性补丁消灭一类 LLM 往返 |
| A30 | **单服务多租户路由**：location 中间件按请求 header 路由到 per-租户服务实例 | opencode 档案 §7（location.ts） | Spring HandlerInterceptor + 租户级 ServiceLocator 缓存同构 |

### 2.2 B 级：需改造（10 条）

| # | 模式 | 来源 | 改造点 |
|---|---|---|---|
| B1 | **哈希链审计账本 + 问责链**：每笔资金动作 seq+prev_record_hash，append 前验链、断链拒写；被拒与 halt 也入账；mandate_snapshot_ref+consent_record_ref 回溯到人工授权 | Vibe-Trading 档案 §5（agent/src/governance/ledger.py） | 单机 flock 的并发语义必须重设计：企业多实例下哈希链写入要收敛到单写者（审计服务串行化）或改 Merkle 树批量锚定；账本存储独立于 agent 运行目录 |
| B2 | **子 agent 扇出隔离五件套**：派生会话 ID（含批次号防跨批泄漏）+ 独立记忆 + 独立工具集（只读过滤）+ 共享只读资源 + 产物旁路/仅压缩结论进主上下文 + 单失败不炸批 | DB-GPT 档案 §2（dispatch_parallel_tasks） | 图编排下表达为「子图并行分支」；隔离语义（独立 thread、工具面裁剪、结果汇聚节点）要自己长在图引擎上（spring-ai-alibaba graph 子图 + 状态隔离，见 agent-framework 档案） |
| B3 | **语义层口径治理**：指标唯一权威定义 + 派生口径 + 值级映射 + 术语字典（机制）；口径文件在 Git、变更走 PR、审批后发布运行时（治理形态） | supersonic 档案 §6（元模型）、WrenAI 档案 §4（MDL 治理即代码） | 机制学 supersonic（Calcite schema + 元模型表），治理形态学 WrenAI（YAML/JSON + JSON Schema 校验进 Git，CI 审批后发布）；建设成本高，按财务域优先级分期（先核心报表指标） |
| B4 | **受限语义方言 + 确定性翻译**：LLM 只写逻辑层（指标名/维度名），物理展开/join/方言在确定性翻译层完成 | supersonic 档案 §2（S2SQL + Calcite） | B3 的执行半边；「LLM 输出落在可校验的受限表达域」是 B 组谱系结论的分水岭——与 A22 出口校验双管齐下 |
| B5 | **授权合同对象零解析面**：给 agent 读的合同用不可变、零验证歧义形式（Vibe 用 frozen dataclass 而非 Pydantic 的动机：不给 agent 留可利用的解析差异） | Vibe-Trading 档案 §8 | Java 对应：record + Jackson 严格模式 + 显式 final；所有给模型消费的结构体都过一遍「可利用面」审查 |
| B6 | **kill switch 物理制动**：独立于 LLM/主循环/SSE 存活的开关，payload 损坏视为已触发 | Vibe-Trading 档案 §5（halt.py） | 服务化后=独立存储标志位（DB/Redis）+ 每动作前检查 + 运维面专用入口（不经 agent 服务） |
| B7 | **advisory 与 gate 分离**：外部风控建议（fail-open、绝不阻塞、默认关）与硬门（fail-closed、唯一权威）严格分离 | Vibe-Trading 档案 §5 | 财务同理：外部风控建议服务挂了不该阻断合规门，也不能因「建议通过」绕过门——混用会把外部依赖可用性变成资金链路可用性风险 |
| B8 | **代码沙箱（仅对账/批量核算场景）**：每会话容器 + 容器内执行服务器 + session key 鉴权 | OpenHands 档案 §6、data-formulator 档案 §2 | JVM 无 OS 沙箱等价物（SecurityManager 废弃），Docker(+gVisor) 是现实替代；**能力面收窄（A19）优先，确需执行分析代码才上容器** |
| B9 | **MCP 双面暴露**：同一 agent 服务 REST/SSE 主面 + MCP Server 工具面 | DataAgent 档案 §6.5 | 业务系统消费 REST 主面，其他 agent 系统消费 MCP 工具面；MCP server 自述 readOnlyHint 不可作安全依据（Vibe curated map 反制先例） |
| B10 | **worker 六分类质量闸门**：completed/failed/timeout/token_limit/**incomplete**（跑完但伪造交付/空计划）/cancelled | Vibe-Trading 档案 §2（models.py#WorkerStatus） | 多 agent 工作流必备：专设状态抓「跑完但没实质交付」；Java 枚举 + 产物校验器（空检查/溯源检查） |

### 2.3 C 级：仅参考（8 条）

| # | 模式 | 来源 | 参考价值与不迁移原因 |
|---|---|---|---|
| C1 | **层级投票拓扑**（agent 并行独立、零通信、代码加权合成） | ai-hedge-fund 档案 §2 | 月结审查/报销初审的映射思路（各检查维度独立投票、算术合成、clamp 异常）；实现 trivial，价值在「零串扰 + 确定性」的设计取向 |
| C2 | **辩论-裁决拓扑**（固定轮次对抗 + deep 模型裁判） | TradingAgents 档案 §2 | 报销争议/异常调查的对抗推理思路；轮次固定=可预算可审计（优于「自由讨论到收敛」）；输出零强制力，只能做建议器 |
| C3 | **并行研究 + 独立审查 + 授权合同拓扑** | Vibe-Trading 档案 §2（Swarm YAML） | 生成与审查分离（审查者不写结论）的结构保证；权威来自人工授权而非 agent——拓扑思想可平移，自研 runtime 不迁移 |
| C4 | **事件溯源多订阅者架构**（append-only 流为唯一真相源，controller/审计/风控/推送都是订阅者） | OpenHands 档案 §2 | 审计器/风控器/进度推送天然获得完整轨迹的方向；服务端直接用 A11 事件表即可，无需完整 EventStream 中间件 |
| C5 | **审批四路竞速 + resolve-once**（本地 UI/桥/手机/分类器谁先答谁生效） | claude-code-sourcemap 档案 §5【还原源码】 | 多审批渠道（Web/移动/IM）的方向参考；实现复杂度高，起步双渠道（工作台+IM 通知跳转）足够 |
| C6 | **OS 级沙箱细节**（Seatbelt/bubblewrap/seccomp、网络 MITM 按域名审批） | codex 档案 §5 | 不可迁移（JVM 生态无等价物）；「网络不是开关而是按 host 审批」的思想用 egress 白名单（agent 进程无公网 outbound，一切外部调用经统一 API client）承接 |
| C7 | **watchdog 事件总线**（14 个安全看门狗挂会话事件总线，策略与动作实现解耦） | browser-use 档案 §5 | Spring 事件/切面链承载「目标白名单/频次/敏感目标」检查的方向；具体看门狗集合是浏览器域的 |
| C8 | **能力声明式契约**（retriever 类属性声明「返回 URL 待爬/已带全文」，取代长度启发式——后者曾致引用丢失） | gpt-researcher 档案 §6 | 财务数据源适配器 SPI 用注解显式声明读写语义/PIT 属性/是否含派生列，禁止从返回形状推断能力 |

## 3. 反模式与避坑（18 仓工程债汇总）

1. **fail-open 审批门**（DB-GPT 档案 §5）：确认拦截整体包在 `try/except pass` 里静默放行 + pending 存模块级内存 dict（重启丢、多副本失效）+ resolve 端点无鉴权（任何人可替人批准）+ 只盖 MCP 连接器不盖 SQL/代码执行。四缺陷叠加=审批门形同虚设。**教训：审批链路上任何一环异常都必须拒绝执行，状态必须持久化，resolve 必须带操作者身份。**
2. **prompt 当控制**：行数限制写 prompt（DB-GPT）、LIMIT 写 prompt + 全量拉回后截断（SQLBot）——prompt 约束只是文案，数据量控制必须进连接层（maxRows/timeout/limit 探测）。
3. **LLM 重写权限 SQL**（SQLBot generate_filter）：行权限靠又一次 LLM 调用拼进 SQL，正确性依赖模型且无行级语义验证——**权限相关变换必须有确定性执行者**（AOP/引擎注入）。
4. **文本协议动态路由**（FinRobot `[员工名]` 派工）：路由正确性=LLM 遵守格式 × 正则匹配，不可静态验证、TERMINATE 终止不可预算、每轮 reset 无状态。动态性应上移图编排层（A23）。
5. **凭据「装饰性加密」四连**：db_pwd 明文+API 回传（DB-GPT）、硬编码 key + AES-ECB（SQLBot、supersonic）、明文但表注释写「加密存储」（DataAgent）。**「有加密」≠「加密有效」——评审看密钥管理（KMS/env、AEAD-GCM），不看是否调了加密函数。**
6. **宣称 vs 实现落差**（18 仓通病）：FinRobot 辩论/调度闭源、TradingAgents「PM 审批+模拟交易所」无代码、ai-hedge-fund live/ledger 是 roadmap、DataAgent「加密存储」实为明文、WrenAI RLS/审计是商业版、supersonic「Java SPI」实为 SpringFactoriesLoader。**任何能力宣称先对码并注明证据等级；选型评审禁止引用 README 能力清单。**
7. **审批不落库 / checkpoint 用完即删**（DataAgent 档案 §5）：HITL 暂停-恢复协议是对的，但审批数据无持久化、故障恢复缺失——审批必须独立落库（谁/何时/批了什么版本/理由）。
8. **全量重写式会话存储**（gemini-cli logs.json）：读改写全文件，并发弱、不适合服务端；服务端多会话场景正确解是事件表 + 唯一索引（A11）。
9. **双代架构并存债**：opencode permission v1/v2、gemini-cli 双 context 架构、DB-GPT 新旧代、FinRobot V0/V1、gpt-researcher 三线、data-formulator 双目录迁移——**新系统一步到位定数据模型**（审批四元组、事件 schema），避免迁移期双倍维护。
10. **隐式只读**（DataAgent executeQuery）：隐式行为不可声明、不可审计、不可测试——读写语义必须显式声明（工具目录 A20）并可在网关侧复核。
11. **前缀黑名单防注入**（DB-GPT startswith）：注释/CTE/多语句皆可绕过——内容级校验必须上 AST（SQLBot/WrenAI/opencode/codex 四仓一致路线）。
12. **溢出恢复赌 LLM**：上下文压缩失败后再调一次 LLM 做摘要（provider 刚拒绝过长请求）——必须有确定性降级路径（截断/占位符）。
13. **审批疲劳无防护**：长期「全部询问」导致人机械点同意——codex 的「关闭询问=自动拒绝」+ 规则修订（A6）+ always 强制收窄到 pattern（gemini TOOLS_REQUIRING_NARROWING）三件套防护。
14. **基线漂移风险**：18 仓中至少 6 仓处于形态剧变（cline SDK 化、codex 双轴化、OpenHands 清仓迁移、WrenAI 2026-05 巨变、opencode/gemini 双代并存、supersonic 维护模式）——引用旧架构资料前必读本报告 README 的基线表；本报告所有结论锚定 2026-09-13 基线。

## 4. 面向财务 Agent 的推荐架构

### 4.1 总体形态（对照约束①）

采用 **opencode 形态：agent 服务是独立 Spring Boot 服务，全部能力经 REST/SSE API 暴露；对业务系统再开 MCP 工具面**（DataAgent 先例）。部署上「一个 agent 服务 + 一个审批工作台（可同进程不同模块）+ 一个审计存储」，业务系统与 agent 服务只经 API 网关通信。

```
                         ┌────────────────────────────────────────────────────┐
                         │                Agent 服务（Java / Spring Boot）      │
   业务系统 ──REST/SSE──▶ │  ┌──────────┐  ┌───────────────┐  ┌────────────┐  │
   其他agent ──MCP工具面─▶ │  │ 接入层    │─▶│ 编排层（图引擎）│─▶│ 执行层      │  │
                         │  │ REST/SSE │  │ 静态图+计划驱动 │  │ 受控工具面  │  │
   审批工作台 ◀─SSE/REST─ │  │ MCP 面   │  │ + human 节点   │  │ 业务API封装 │  │
   （Web/移动/IM）        │  └──────────┘  └───────┬───────┘  └─────┬──────┘  │
                         │                        │                │         │
                         │  ┌─────────────────────▼────────────────▼───────┐ │
                         │  │ 横切层：权限规则引擎│审批挂起/恢复│上下文管理     │ │
                         │  │         事件溯源存储│审计│凭据引用│压缩+落盘指针  │ │
                         │  └────────────────────────────────────────────┘ │
                         └───────┬─────────────────────────┬────────────────┘
                                 │                         │
                    ┌────────────▼───────────┐  ┌─────────▼──────────────┐
                    │ 审批/授权服务（人工面）   │  │ 审计存储（事件库+哈希链账本)│
                    │ 规则修订·consent·kill   │  │ append-only·只增不改     │
                    │ switch·限额合同(mandate) │  │                        │
                    └────────────────────────┘  └────────────────────────┘
```

要点：
- **审批/授权是独立面**（约束③）：限额合同（mandate）的写入口只存在于审批服务（人工确认回执），agent 工具面只有 propose 类工具——授权不可达（A9）；kill switch 是审批服务里的独立标志位（B6）。
- **审计存储只增不改**：LLM 决策事件流（A11/A13）+ 资金/记账动作哈希链（B1）双平面；agent 服务无删除权限。

### 4.2 编排层（对照约束②）

图引擎选型沿用 agent-framework 轮结论（Java 侧 spring-ai-alibaba graph 或 langgraph4j，见 `research/agent-framework/profiles/` 对应档案），本报告只定**图上语义**：

1. **主形态：静态图 + 计划驱动**（A23）。财务主流程（取数→分析→生单→送审）拓扑静态声明、可静态审计；LLM 规划产物是 Plan JSON（schema 强约束），经工具白名单+参数校验后由确定性代码步进执行。计划先送审（A24 human 节点），批准后逐步执行，每步产物回写事件流。
2. **动态性只允许四个位置**：条件边循环（固定轮次计数终止，A25）/ 计划驱动路由（A23）/ 声明式子任务 DAG（B2 子图）/ human 节点回环（A24）。禁止自由群聊式派工（反模式 4）。
3. **拓扑分轨按「金额 × 可逆性」**（dimensions/A §2）：月结审查/报销初审=并行独立检查节点+算术合成+clamp；争议/异常调查=固定轮次辩论+deep 模型裁决节点；付款/过账终点=proposal 节点（无权）→ 审批服务 → fail-closed 执行门（A8）。同一张图不同分支挂不同拓扑。
4. **LLM 影响力终止于建议**（ai-hedge-fund 总纲）：agent 产物 schema 校验（A16）后进纯函数管线（合成/裁剪/生成动作单），限额 clamp 事件逐条入审计；数字必须确定性代码算（FinRobot ValuationEngine 与 ai-hedge-fund 互证的「数字代码算、叙述 LLM 写」）。

### 4.3 审批与风控五层（对照约束③，dimensions/跨组 §2.6 拼装）

```
 LLM 请求工具/动作
      │
 ①规则引擎（进程内，策略即数据：Admin 层硬合规 DENY 永远最高）          [A4/A5]
      │ ALLOW→放行（只读类）；DENY→拒绝（附理由回喂模型）；ASK↓
 ②有序求值管线：超限额/敏感科目判定（bypass 免疫）+ DecisionReason      [A5]
      │ 灰区↓
 ③审批外化：REST 建单 + SSE 推送审批工作台；执行线程挂起（CompletableFuture）
    回复三元 once/always/reject(+feedback 回喂模型)；断线重放不丢单      [A1/A2/A3/A6]
      │ CONFIRMED↓（always = 可审计规则修订 + 内容版本绑定）
 ④执行出口二次校验：只执行 CONFIRMED 状态的审批单                      [A7]
      │
 ⑤不可逆动作门（付款/过账）：fail-closed 纯函数检查链（授权有效→kill switch
    →对账→限额三态裁决），不可解析即 DENY；崩溃恢复=对账不重发           [A8/A18/B6/B7]
```

辅助纪律：解析失败哨兵值进人工队列（A16）；granular 关闭询问=自动拒绝（A10）；advisory（外部风控建议，fail-open）与 gate（fail-closed）分离（B7）。

### 4.4 工具面与数据访问（对照约束①）

1. **工具面=业务 API 受控封装**（A19/A20）：不提供 shell/任意代码执行；deny 工具从模型列表移除；工具目录（注册+读写声明+审计元数据）单源四处消费；确需分析代码（对账脚本）才上容器沙箱（B8）。
2. **凭据引用协议**（A28）：KMS 存真值 → 引用键在配置与消息流转 → 工具执行层域限定解析 → 展示层全量打码；业务系统凭据不进 prompt、不进 agent 配置库。
3. **取数走语义层**（B3/B4 + A22）：财务口径文件（指标/维度/术语）进 Git 走 PR 审批，发布到运行时 Calcite schema；LLM 只写逻辑层（指标名），确定性翻译展开物理 SQL；SQL 唯一出口六层校验 + 连接层三件套。
4. **数据权限分层**（A21）：主体隔离（法人/账套）声明式 fail-closed；行权限执行边界 AOP 注入 + 透明回执；绝不用 LLM 重写权限 SQL（反模式 3）。
5. **egress 白名单**：agent 进程无公网 outbound，一切外部调用经统一 API client 层（C6 思想的承接）。

### 4.5 审计基线（12 条 checklist，dimensions/跨组 §3.5）

① 会话=append-only 事件流（含审批/成本/风险分/压缩事件）② 用户可见产物独立落库 ③ 资金/记账动作哈希链+问责链 ④ LLM 决策缓存即审计 ⑤ 决策日志 pending→resolved 带 resolution_date ⑥ 规则与拓扑版本进审计键 ⑦ 凭据全程占位符/写时脱敏 ⑧ 审批数据独立持久化 ⑨ 回滚不破坏现场（两阶段）⑩ 不可逆动作对账不重发 ⑪ 审计双平面（执行面×管理面）⑫ 决策失败哨兵值可见化。

### 4.6 分期落地建议

- **第一期（合规骨架）**：固定图+计划驱动（A23/A24）+ 审批外化 API（A1-A3）+ 规则引擎（A4/A5）+ 事件溯源存储（A11）+ 审计双平面（A12/A13）+ SQL 六层校验（A22）+ 凭据引用（A28）。此期 agent 只做「取数+分析+生成建议单」，写操作全部人工执行。
- **第二期（受控执行）**：fail-closed 执行门（A8）+ 授权不可达 mandate（A9）+ kill switch（B6）+ 哈希链账本（B1）+ 对账不重发（A18）。低金额高频率操作（自动过账、小额付款）进入自动执行白名单。
- **第三期（规模化）**：语义层口径治理（B3/B4）+ 子 agent 扇出（B2）+ 辩论/委员会拓扑分轨（C1-C3）+ 多审批渠道（C5）+ 容器沙箱分析代码（B8）。

## 5. 与上游研究的衔接

- 图引擎能力（checkpoint/HITL/subgraph/多 agent 原语）见 `research/agent-framework/profiles/`（spring-ai-alibaba、langgraph4j、agentscope-java 等 Java 系档案）与 `report.md` 选型结论——本报告不重复框架层分析。
- DataAgent 构建在 spring-ai-alibaba graph 上、TradingAgents 构建在 LangGraph 上，其「怎么用框架」见各自档案 §2/§3。
- 学术与基准参照（Data Agent survey、NL2SQL handbook、DAB leaderboard、财务基准群）见 `references.md`；财务 agent 基准全部 star<60 且碎片化，佐证本领域评估标准远未收敛——自建评估集时应参照 FinVault 的执行安全口径与 DAB 的任务/评分维度。
