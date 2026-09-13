# B 组横向：BI / 数据智能（NL2SQL 与 ChatBI 产品形态）

> 输入：`profiles/` 下 DB-GPT、SQLBot、supersonic、WrenAI、DataAgent、data-formulator 六份档案（基线与源码路径见各档案）。本组共性：核心都是「LLM 生成 SQL 或分析代码」，最大的分化轴是**把「智能」放在管线的哪个位置**——由此决定了可控性、安全边界与审计形态的全部分化。

## 1. 组内定位图谱

| 项目 | 确定性管线 ↔ 自由 agent | 语义层 | 技术栈 | 形态定位 | 状态备注 |
|---|---|---|---|---|---|
| SQLBot | 最左端：顺序多段 LLM 流水线（一次问答最多 6 次调用），无循环无 agent | ❌ 无（表勾选+术语库+表关系图，属 RAG 上下文供给） | Python / FastAPI | 产品：只读问数 SaaS | 许可 NOASSERTION（DataEase 系疑 GPLv3+附加条款），细粒度权限在 xpack 闭源包——商用需法务核验 |
| supersonic | 偏左：受限方言 S2SQL → Apache Calcite 确定性翻译；状态机编排 | ✅ 组内最全：DB 元数据（模型/维度/指标/术语/数据集/主题域） | **Java 21 / Spring Boot 3.3** | 产品：ChatBI + Headless BI 平台 | **维护模式**（release 停 2024-11 v0.9.8，单人维保）——只作架构参考 |
| WrenAI | 编排外置：引擎自身几乎不调 LLM，智能在宿主 agent，治理在引擎 | ✅ MDL 语义模型（Git 文件，治理即代码） | **Rust**（DataFusion）+ Python | 引擎：CLI / MCP / SDK | **open-core**：per-user 行权限、审计日志、hosted API 均为商业版；2026-05 刚整体改版（v1 移 legacy 分支） |
| DB-GPT | 最右端：新代 ReAct 自由 agent + 并行子 agent（旧代固定管线并存） | ❌ 无（表级/字段级双向量 schema 召回） | Python（自研 AWEL DAG + dbgpt.agent） | 产品+框架双体 | 活跃；认证是显式 mock，安全边界停在「单机自用」 |
| DataAgent | 中间折中：固定 16 节点 StateGraph + LLM 计划驱动路由 | 🔶 弱：schema 向量召回 + Excel 语义模型导入（不钳制生成 SQL） | **Java 17 / Spring Boot / spring-ai-alibaba graph** | 产品：独立部署的数据分析师服务 | **1.0.0-RC 未 GA**：权限/审计/租户三块工程缺口 |
| data-formulator | 偏右：手写 tool-calling 循环；数据加载侧另有受控计划双轨 | ❌ 无（「数据记忆」只是连接器关系图） | Python（零框架，litellm） | 本地研究工具（微软研究院，MIT） | 0.8 beta，架构迁移中（agents/ 与 analyst/ 并存） |

「确定性 ↔ 自由」不是优劣轴而是**信任轴**：越靠左行为越可枚举、失败模式可穷举、审计越容易，但能回答的问题形态越窄；越靠右覆盖面越宽，安全与合规成本陡增。财务场景应落在左半区，只在受控点引入受限的动态性——DataAgent 的「静态拓扑 × 动态计划」正是这种折中的现成样本。

## 2. NL2SQL / 数据问答管线形态谱系

六条路线，各含适用场景 / 可控性-灵活性取舍 / 失败模式：

**(1) 确定性多段 LLM 流水线（SQLBot）**——一次问答 = 选数据源 → RAG 上下文（术语/示例）→ 伪对话 priming → 生成 SQL → 权限重写 → 只读校验后执行 → 图表生成 → SSR 渲染，全链顺序写在一个方法里。
- 适用：问数 SaaS、多租户、产出形态固定（表+图）。- 取舍：每段可独立打点/审计/回放（chat_log 14 种操作枚举），但新分析能力=改代码，且无轮内重试。
- 失败模式：仅靠 `<error-msg>` 跨轮回喂纠错；行权限重写本身是 LLM 调用（安全洞，见 §5）。

**(2) 受限语义方言 + 确定性翻译（supersonic：S2SQL + Calcite）**——LLM 只写逻辑层 S2SQL（指标名/维度名，无 join、无物理表、无方言函数），HanLP 词典+向量把词汇前置映射到受控词汇表，Calcite 确定性展开指标/join/方言。
- 适用：口径强统一的企业指标问答（ChatBI+Headless BI 双面）。- 取舍：LLM 幻觉面被 DSL 边界钳住；代价是语义层建模成本，且「问不出未建模的东西」。
- 失败模式：Schema Mapper 未命中词汇直接 FAILED 终态（宁可拒答不瞎猜——正确取向）；LLMPhysicalSqlCorrector 让 LLM 二次改写物理 SQL 有语义漂移风险（默认关闭是正确的）。

**(3) 语义层治理引擎 + 编排外置（WrenAI）**——引擎自己不调 LLM：agent（Claude Code/Cursor 等）用模型名写目标方言 SQL，dry_plan 经 sqlglot 策略防火墙 + Rust 规划展开（join/口径）+ 翻译后复查，query 受治理执行。
- 适用：已有编码 agent 的工程团队；把治理做成可独立测试的引擎而非产品。- 取舍：治理与智能彻底解耦、策略 fail-closed；但产品体验外包给了宿主 agent。
- 失败模式：planned-SQL 复查 fail-open（源码注释自认权衡）；OSS 无身份层——「机制在、人不在」。

**(4) ReAct 自由 agent + 工具（DB-GPT 新代）**——主 agent 持 8 类工具（sql_query/code_interpreter/shell/skill…）+ todowrite 任务板 + dispatch_parallel_tasks 并行子 agent，执行错误文本成为 observation 自行改写重试。
- 适用：探索式深度分析、产出 HTML 报告；覆盖面最宽。- 取舍：自由度换可控性——SQL 出口只有前缀黑名单（可绕过），确认门 fail-open、内存态、只盖 MCP 连接器。
- 失败模式：步数预算内打转（主 agent 上限 30 步）；上下文靠字符截断与快照落盘硬扛；安全靠子 agent 隔离模型自守。

**(5) 固定图 + 计划驱动（DataAgent）**——StateGraph 拓扑静态固定（16 节点/11 条件边），LLM 规划产物 Plan JSON（schema 强约束）经工具白名单校验后，由确定性代码按步进游标调度，修复回路计数封顶。
- 适用：「先出方案→审批→逐步执行」的合规形态，与本项目硬约束③天然对齐。- 取舍：图可静态审计 × 计划可动态生成两者兼得；但状态键全 REPLACE 无 reducer，且审批后到 SQL 执行之间无二次闸门。
- 失败模式：审批数据不落库（checkpoint 用完即删→无痕）；计划校验失败重规划超限后终止。

**(6) code-first 生成分析代码（data-formulator）**——「LLM 不算数，代码算」：生成 pandas/DuckDB 代码（output_variable 契约）→ 确定性补丁先行 → 沙箱执行 → 字段级结果校验 → observation 回喂自修复；数据加载侧却是 SPJQ 受限计划 + 人工选择状态机。
- 适用：报表加工/可视化探索（数据拉回本地算，不生成 SQL 下推）。- 取舍：计算确定性可复算、代码可签名审计；表达力最强但信任边界全靠沙箱配置。
- 失败模式：沙箱配置错误即全线失守（存在 not_a_sandbox 模式）；trajectory 由前端持有，服务化必须重构。

**谱系结论**：真正的分水岭是「**LLM 输出是否落在一个可校验的受限表达域**」——S2SQL（supersonic）、manifest 内模型名 SQL（WrenAI）、Plan JSON（DataAgent）、SPJQ 计划（data-formulator）都做到了；裸 SQL/裸代码（DB-GPT、SQLBot 生成段）则只能靠出口校验兜底。财务系统应**生成域受限 + 出口确定性校验**双管齐下。

## 3. 语义层与口径治理（财务报表刚需）

| 维度 | supersonic（DB 元数据） | WrenAI（Git 文件 MDL） | DataAgent（schema 召回） |
|---|---|---|---|
| 载体 | 元数据库表 + 建模 UI | MDL JSON + instructions.md + knowledge/ 例句，全在 Git | 向量召回表/列文档 + Excel 语义模型导入 |
| 指标口径 | Metric 唯一定义（表达式+默认聚合+格式），defineType 支持指标派生（毛利率=利润/收入建成新指标） | Cube+Measure「受批指标定义」+ 计算列 expression | ❌ 无口径强制，语义模型只是 prompt 上下文 |
| 值级口径 | dimValueMaps（"华南"→粤桂）+ Term 术语字典进 prompt | enumDefinitions（status=3→"已逾期"）+ instructions.md | ❌ |
| 变更治理 | isPublish 布尔开关 + createdBy/updatedAt 留痕，**无审批流** | **变更 = Git PR**，可 diff 可 review（治理即代码） | Excel 重导入，无流程 |
| 对生成 SQL 的钳制 | 强：LLM 只能写逻辑指标名，翻译期统一展开 | 强：strict 模式表封闭，只许命中 manifest | 无：LLM 直写物理 SQL |

**「财务口径统一」的选择：机制取 supersonic，治理形态取 WrenAI。** 指标唯一权威定义（含派生口径、值级映射、术语字典）保证「营收只有一个算法」，是 supersonic 元模型给出的可运行答案；但口径变更必须走审批+diff 留痕，DB 里的布尔开关做不到，WrenAI「定义即文件、变更即 PR」才是合规要的形态。落地建议：**口径文件（YAML/JSON + JSON Schema 校验）进 Git 走审批流水线，审批通过后发布到运行时语义层（Calcite schema），LLM 只见逻辑指标名**。DataAgent 式 schema 召回只配作 RAG 上下文补充，不是口径治理。

## 4. SQL 安全与只读隔离工程

### AST（抽象语法树）校验器横向对比

| 项目 | 工具与层次 | 覆盖 | 缺口 |
|---|---|---|---|
| SQLBot | sqlglot 四层：首关键词白/黑名单 → 危险模式正则 → AST 写类型节点 → **方言敏感危险函数清单**（xp_cmdshell/UTL_FILE/lo_import…）；另加 AST 提真实表名对可见表白名单（**不信任 LLM 自报 tables**） | 广而全 | 无查询超时；LIMIT 只在 prompt + 结果后置截断（全量数据已拉回应用层） |
| WrenAI | sqlglot policy 三层：只读 AST 白名单（**根类型+全树扫描**：防数据修改型 CTE、SELECT..INTO、多语句、FOR UPDATE 锁意图）→ strict 表封闭（fail-closed）+ 数据读取函数黑名单 40+（防 SSRF/路径穿越，报错不回显参数）→ **翻译/内联后复查** | 最深 | planned-SQL 复查 fail-open（财务场景应改 fail-closed） |
| supersonic | jsqlparser 是**改写器**（S2SQL 修正、行权限 WHERE 注入）而非校验器；物理 SQL 无白名单校验器 | 只读性靠 DSL 边界（S2SQL 表达不出 DML）+ 模型即受控视图 | 上游绕过语义层即裸奔；行权限表达式是管理员手写裸 SQL 片段 |
| DataAgent | Druid AST 做**结构**校验（恰好一条语句 + 无 `?` 占位符）；executeQuery 隐式只读 + setMaxRows(1000) + setQueryTimeout(30s) | 连接层三件套是组内最规范的执行边界 | 无显式 DML/函数/表白名单——隐式只读不可声明、不可审计 |
| DB-GPT | **反例**：startswith 前缀黑名单（注释/CTE/多语句可绕过）；连接器层对 DML/DDL 无条件执行 | — | 出口校验形同虚设，只读实际靠「运维用只读账号」的约定 |

**最优组合（Java 侧用 JSqlParser / Calcite validator 同构实现）**：① WrenAI 的根白名单 + 全树禁写扫描（含 CTE 内、INTO、FOR UPDATE）→ ② SQLBot 的方言危险函数清单 → ③ SQLBot 的 AST 表名白名单（不信任 LLM 自报元数据）→ ④ supersonic/WrenAI 的表封闭（只许命中语义层已定义模型）→ ⑤ WrenAI 翻译/改写后复查（改为 fail-closed）→ ⑥ DataAgent 连接层三件套（readonly connection + maxRows + timeout）。六层各挡一类逃逸；DB-GPT 演示了缺 AST 层的下场，SQLBot 演示了缺连接层三件套的下场。

### 凭据管理正反案例

- **反面**：DB-GPT `db_pwd` 明文入库且 API 原样回传；SQLBot 硬编码 key `SQLBot1234567890` + AES-ECB（源码即密钥，装饰性加密）；supersonic 同为 AES-ECB；DataAgent 明文入库且表注释宣称「加密存储」。四仓两种病：**根本不加密**与**加密了但密钥随源码分发**——合规审计里同等级缺陷。
- **正面**：DB-GPT MCP CredentialStore（Fernet 加密、master key 走 env、确认弹窗敏感参数打码、`${env:VAR}` 插值）；WrenAI profiles `${VAR}` 占位 + .env 解析 + 「永不在聊天里要凭据」写进编排模板；data-formulator TokenStore 六级解析链（cached→refresh→sso_exchange→delegated→vault）+ 本地加密 vault。共同点：**密钥在代码与数据之外，凭据不进 prompt、不进任何展示层**。

## 5. 权限注入位置

四种位置，强度递增：

1. **prompt 约束**（DB-GPT 行数 top_k 只写 prompt；SQLBot「只能生成查询」）：可被注入攻击诱导失效，只能当提示不能当控制——写进 prompt 的安全要求只是文案。
2. **LLM 权限重写**（SQLBot generate_filter：又一次 LLM 调用把行权限条件拼进 SQL）：组内唯一此路线，正确性依赖模型，重写结果只重过只读校验、无行级语义验证——**组内共识性反面模式**，权限相关 SQL 变换必须有确定性验证器。
3. **执行边界 AOP（面向切面编程）强制注入**（supersonic S2DataPermissionAspect：`@Around` 织入查询服务——模型可见性 → 列敏感级（sensitiveLevel=HIGH 须授权）→ 行权限 jsqlparser `SqlAddHelper.addWhere` 强制注入 WHERE → `QueryAuthorization` 回执告知用户「结果已经过行权限过滤，条件如下」）：Java 可直接照抄的结构；弱点是行权限表达式为管理员手写裸 SQL 片段（注入面依赖信任边界）。
4. **引擎策略层**（WrenAI RLAC，行级访问控制：Model 上声明 condition + requiredProperties（SessionProperty），规划期由 Rust 引擎注入，**缺必需属性规划直接失败——fail-closed**；属性值由调用方会话上下文提供，LLM 不可见不可改）：声明式最强形态，但 OSS 版「机制在、身份层不在」（per-user 注入是商业版）。

**财务数据权限的应然做法（分层叠加）**：主体隔离（法人/账套/币种）用 RLAC 式声明——权限参数来自审批后的会话上下文、缺即 fail；表/列权限在执行前做 AST 白名单 + 敏感级校验；行权限在执行边界确定性注入（AOP/Calcite planner，绝不经 LLM）；过滤行为对用户透明可解释（supersonic 回执模式可直接进合规报告）；prompt 约束仅作最后一层提示。

## 6. 组内分化点与教训

1. **「有加密」≠「加密有效」**：评审要点是密钥管理（KMS/env、AEAD-GCM），不是「有没有调用加密函数」。
2. **宣称落差是本组通病**：DataAgent 表注释「加密存储」实际明文；DB-GPT DDL 分支日志暗示有配置开关实际没有；WrenAI README 的 RLS/审计实为商业特性；SQLBot README 细粒度权限在 xpack 闭源；supersonic README「Java SPI」实为 SpringFactoriesLoader。任何能力宣称先回源码验证。
3. **只读保证的强度取决于注入位置**：prompt < 前缀黑名单 < 隐式 executeQuery < AST 白名单 < DSL 边界+视图建模。越靠近生成端越弱，越靠近执行端越强——校验器必须横在「唯一执行出口」上。
4. **数据量控制必须进连接层**：prompt 约束（DB-GPT）与后置截断（SQLBot，全量已拉回）都是假限制；setMaxRows + limit 探测（DataAgent/WrenAI）才是真限制。
5. **审计成熟度谱系**：DataAgent（审批无痕、checkpoint 用完即删）< WrenAI OSS（无审计，商业特性）< DB-GPT（trace + view message 留痕，非合规口径）< supersonic（QueryStat 全量留痕 + 记忆双审）< SQLBot（双平面最成熟：执行面 chat_log 完整 prompt/token/14 种操作枚举 + 管理面声明式 @system_log）。
6. **基线稳定性差是本组风险**：supersonic 维护模式、WrenAI 2026-05 形态巨变、data-formulator beta 双目录迁移、DataAgent RC——「抄模式不引依赖」在本组不是偏好而是必要。
7. **两代架构并存是常态**（DB-GPT 旧 scene/新 ReAct、data-formulator agents//analyst/）：仓库快照可能同时含新旧两套答案，引用前先确认哪条是现役链路。

## 7. 对本项目的启示清单

1. SQL 唯一出口设六层校验：根白名单+全树扫描 → 方言危险函数 → 表名白名单 → 语义层表封闭 → 改写后复查（fail-closed）→ 连接层 readonly/maxRows/timeout——来源：SQLBot.md §5、WrenAI.md §5、DataAgent.md §6.2。
2. 财务口径建语义层：指标唯一权威定义 + 派生口径 + 值级映射 + 术语字典（机制学 supersonic）；口径文件进 Git 走 PR 审批后发布到运行时（治理学 WrenAI）——来源：supersonic.md §6.1、WrenAI.md §4/§6.1。
3. 编排用「固定图 + 计划驱动」：LLM 规划 Plan JSON（schema 强约束），白名单校验 + 步进游标由代码执行；审批门除计划级外，SQL 执行前再加执行级确认（DataAgent 只审计划不审 SQL 是缺口反例）——来源：DataAgent.md §2.2/§5。
4. 审批必须持久化：审批人/时间/原计划/决策/理由落独立表（DataAgent checkpoint 即删是反例）；执行产物绑定签名（data-formulator HMAC 代码签名扩展为「审批人签名已执行的 SQL/代码」）——来源：DataAgent.md §5、data-formulator.md §2.3。
5. 审计双平面照抄 SQLBot：执行面逐 LLM 调用记录（操作枚举+完整 prompt+token+时长），管理面声明式注解（IP 链解析、敏感 header 排除、DELETE 前资源名补录）；用户可见结果（SQL+数据+图表类型）作为独立消息类型落库（DB-GPT view message 审计面）——来源：SQLBot.md §4/§5、DB-GPT.md §4。
6. 权限分层：主体隔离用 session property 声明式 fail-closed（RLAC 式），行权限在执行边界 AOP 确定性注入 + 透明回执，绝不用 LLM 重写权限——来源：WrenAI.md §5、supersonic.md §5、SQLBot.md §5（反例）。
7. 凭据工程：KMS/env 密钥 + AEAD（GCM）存储 + `${env:}` 参数插值 + 展示层全量打码——来源：DB-GPT.md §6（CredentialStore 正例 + db_pwd 反例）、SQLBot.md §5（ECB 反例）、WrenAI.md §6.3。
8. 纠错回路：失败原因用状态键显式传递（`SQL_REGENERATE_REASON`/`PLAN_VALIDATION_ERROR` 式）驱动定向重生成；「AST 结构校验在前、LLM 语义校验在后」双闸门；高频错误先建确定性本地修复器（<1ms 补丁消灭一类 LLM 往返）——来源：DataAgent.md §2.4、SQLBot.md §2、data-formulator.md §2.3。
9. 语义层映射/规划做成图上显式阶段（MAPPING→PARSING→CORRECTING→TRANSLATING），每段计时留痕——来源：supersonic.md §2.2。
10. 并行对账类任务用 DB-GPT 子 agent 隔离模型：派生会话 ID（含批次号防泄漏）+ 独立记忆 + 共享只读资源 + 产物走旁路/结论进上下文 + 单失败不炸批——来源：DB-GPT.md §2。
11. 取数计划与自由分析双轨：高风险操作（取数/写账）走可校验受限 DSL + 人工选择状态机（AWAITING_SELECTION 式），低风险探索走沙箱 + 结果契约兜底——来源：data-formulator.md §2.5。
12. few-shot/知识准入双审：LLM 预审 + 人工终审通过才进向量库影响后续 prompt——来源：supersonic.md §5。
