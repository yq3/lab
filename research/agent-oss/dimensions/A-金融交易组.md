# A 组横向：金融/交易（多 agent 决策与风控拓扑）

> 输入：`profiles/` 下 ai-hedge-fund、FinRobot、TradingAgents、Vibe-Trading 四份档案（基线与源码路径见各档案）。本组共性：都把「一家金融机构的决策流程」编码成多 agent 系统，核心分化轴有两条——① 共识怎么形成（算术合成 / 消息驱动 / 辩论 / 委员会）；② 风控嵌在管线哪一层（prompt 文案 / 代码闸门 / 物理不可达）。这两条轴正好对应本项目「图编排 + 硬审批审计」两大硬约束，A 组因此是四组中参考价值最高的一组。

## 1. 组内定位图谱

| 项目 | 模拟研究 ↔ 真实交易 | prompt 软约束 ↔ 代码硬约束 | 教育项目 ↔ 生产系统 | 编排载体 | 服务化 |
|---|---|---|---|---|---|
| ai-hedge-fund | 模拟端（SimBroker，README 明言不做真实交易） | **代码硬约束**（risk limits 纯函数 clamp，LLM 影响力终止于 Signal） | 教育端（README 反复声明 educational only） | 无框架：顺序纯函数管线 | ❌ CLI/TUI 单机 |
| FinRobot | 模拟端（无下单通道，V1 只产研报） | **全线 prompt 软约束**（风控 = 角色扮演文本） | 半产品（V1 Web 可部署，工程糙） | AutoGen 群聊（V0）/ shell 管线（V1） | 🔶 仅 V1 FastAPI |
| TradingAgents | 模拟端（纯决策生成器，无任何 broker 调用） | **全线 prompt 软约束**（风控 = 3 个辩论人格） | 研究框架（论文配套，60+ 回归测试） | **LangGraph StateGraph**（组内唯一标准图引擎） | ❌ CLI/库 |
| Vibe-Trading | **真实交易端**（14 券商连接器，限额内真实下单） | **五层俱全**（prompt 之上叠解析校验 / 纯函数 / 授权不可达 / fail-closed 门） | 最接近生产（工程化组内第一） | 自研 Swarm DAG（YAML 声明式） | ✅ FastAPI + 多入口共 runtime |

对三条硬约束的命中度（详见各档案 §8）：① 独立部署+API——仅 Vibe ✅（FinRobot V1 半个：FastAPI 但任务是本地 subprocess）；② 图编排——仅 TradingAgents 用标准图引擎（Vibe 的 YAML DAG 语义等价、无引擎生态）；③ 硬审批审计——Vibe ✅✅、ai-hedge-fund 审计与硬风控强但无 HITL 门、其余基本缺席。

两个正交观察：①「真实性」与「约束强度」强相关——只有碰真实资金的 Vibe 被迫长出完整代码级风控链（真金白银是最强的需求逼真机制），三个纯模拟项目全部停在 prompt 层；②「是否用图引擎」与两者无关——组内工程最好（Vibe）与风控最严谨（ai-hedge-fund）的都不用 LangGraph。图引擎满足的是「拓扑可静态声明与审计」，而非「行为可控」本身。

## 2. 多 agent 拓扑模式对比（A 组核心）

四种拓扑，各自回答一个不同的决策问题：

| 拓扑 | 项目 | 解决什么决策问题 | 通信机制 | 终止条件 |
|---|---|---|---|---|
| 层级投票（hierarchical voting） | ai-hedge-fund | 多个独立观点如何合成一个组合决策且不引入对话噪声 | **无通信**：agent 并行独立对同一 PIT 快照投票产 Signal，代码按 model_weights 算术合成（abstain 同时出分子分母） | 单趟无迭代；「循环」只在外层回测时钟 |
| 群聊派工（group-chat dispatch） | FinRobot V0 | 复杂任务怎么动态拆解、分派给人格化员工 | Leader 以 `[员工名] 指令` 文本协议 + 正则匹配触发成员嵌套会话，完成后回报、Leader 再派下一单 | TERMINATE 字符串 / max_consecutive_auto_reply / 嵌套 max_turns 计数 |
| 辩论-裁决（debate-adjudication） | TradingAgents | 对立观点如何充分对抗后收敛为一个建议 | bull/bear 交替互驳（共享辩论 history + 对手最新论点）；裁判节点用 deep 模型出结构化裁决 | **纯计数器**：投研 2×轮次、风险 3×轮次，无收敛判断、无提前终止 |
| 并行研究+独立审查+Mandate 授权 | Vibe-Trading | 研究生成与质量审查分离，且**权威不来自 agent 而来自人工授权合同（mandate）** | DAG 分层：bull/bear 并行产 artifact+summary → CRO 独立审 → PM 终审，层间靠上游 summary 注入 | DAG 拓扑走完 + 每 worker max_iterations/timeout/token 预算三重封顶 |

### 各拓扑的取舍

**层级投票（ai-hedge-fund）**——优势：确定性最强（同输入字节级可重放）、成本可控（无对话轮次，prompt cache 命中）、agent 间零串扰（互不可见，防观点趋同）；LLM 人格与量化模型实现同一 ABC 可混编。代价：无推理交换——agent 不能互相质询，共识质量完全取决于合成权重；观点的「交锋价值」为零。
**群聊派工（FinRobot V0）**——优势：任务分解灵活、零框架依赖。代价：路由正确性 = LLM 遵守文本格式 × 字符串正则，不可静态验证；TERMINATE 终止不可预算；每轮 reset 无跨会话状态——对合规场景三宗罪。
**辩论-裁决（TradingAgents）**——优势：对抗出真知（bull/bear 互驳暴露单边盲区）、固定轮次可预算可审计、deep/quick 双模型把贵模型只花在裁决节点；MsgClear 节点是长工作流防上下文膨胀的图级方案。代价：轮次固定无收敛判断（质量不自适应）；辩论与裁决全在 prompt 层，输出无强制力；嵌套 state 手工回填易漏键。
**并行研究+独立审查+Mandate（Vibe-Trading）**——优势：生成与审查分离（审查者不写结论，独立性有结构保证）；权威与智能解耦（授权在 mandate 层，agent 再强也越不过）；worker 结果六分类把「伪造交付」当一等失败态。代价：自研 runtime 无图引擎生态（checkpoint/HITL 原语要自己长）；DAG 层次固定，无辩论的动态交锋（张力靠角色 prompt 对抗补偿）。

### 对财务场景的映射适用性

- **月结审查**（多检查项合成一个结论）：ai-hedge-fund 拓扑最合——各检查维度（科目勾稽、异常波动、期后事项）作为独立投票者并行跑，代码加权合成，硬规则 clamp 异常项；要的是可枚举与确定性，不需要辩论。Vibe 的 DAG 分层并发 + worker 六分类（专抓「跑完但伪造交付」的 incomplete）补足执行层质量闸门。
- **报销审批**（单一凭据的合规判断）：TradingAgents 辩论-裁决最合——政策合规方 vs 申请人立场方固定轮次对抗，deep 模型裁判出结构化结论；固定轮次 = token 可预算、过程可审计，比「自由讨论到收敛」合规友好。其风险辩论三方（激进/保守/中性）可映射为「宽松解释 / 严格合规 / 例外处理」三种政策视角。
- **付款审批**（高金额、不可逆、需问责）：Vibe-Trading 是唯一完整答案——agent 只能产 proposal（持久化不授予任何权限），付款门是代码 fail-closed 纯函数按 mandate（人工 consent 授权的限额合同）三态裁决，每笔动作进哈希链账本并可回溯到 consent 记录；ai-hedge-fund 的 clamp 提供同构的处置层组件。
- FinRobot 群聊派工对本项目是**反面教材**：动态拆解需求应上移到图编排层做受控路由（对照 B 组 DataAgent 的「固定图 × 计划驱动」），而不是消息文本协议。

**映射总纲：拓扑是可组合的，且应按「金额 × 可逆性」分轨**——低金额可逆（报销初审）走层级投票（快、确定、便宜）；中金额（报销争议、异常调查）叠辩论-裁决；高金额不可逆（付款）无论前面用什么拓扑，终点必须是 Vibe 式「proposal 无权 + 代码门裁决 + mandate 授权 + 哈希链问责」。同一图内不同分支挂不同拓扑，正是图编排相对固定管线的优势。

## 3. 风控嵌入位置的光谱

五个位置强度递增（观点层 → 决策层 → 处置层 → 授权层 → 执行层）：

| 层 | 机制 | 项目归位 |
|---|---|---|
| ① 观点层（prompt 约束） | 系统提示里的风险人格 / 检查清单 | FinRobot V0 风险分析师小组、V1 risks_agent（纯文本输出，零代码约束）；TradingAgents 三风险辩手；Vibe swarm 的 CRO preset；ai-hedge-fund LLM 人格检查清单 |
| ② 决策层（解析校验拦截） | 输出 schema 校验失败 → 哨兵值/弃权，绝不静默降级 | TradingAgents（REVIEW 哨兵值 + field_validator 归一 "N/A"/百分比/货币符号）；ai-hedge-fund（解析失败 → abstain 且原始响应留盘） |
| ③ 处置层（纯函数 clamp） | 确定性算术裁剪 LLM 产出的目标，不可协商、不可逾越 | ai-hedge-fund `risk/limits.py#apply_limits`（组内最纯：先单票封顶再等比缩总量、只缩不放、砍掉敞口不重分配）；FinRobot V1 ValuationEngine 数字代码算但无闸门语义 |
| ④ 授权层（不可达） | 权限/限额写入路径物理上不在 agent 可调用面内，只能经人工 consent 的受信服务面 | 仅 Vibe-Trading（commit_mandate 非工具、不进注册表、仅 `POST /mandate/commit` + consent_ack；agent 只有 propose_mandate_profiles） |
| ⑤ 执行层（fail-closed 门） | 唯一执行出口上的检查链：授权有效 → kill switch → 持仓快照对账 → 纯函数裁决；不可解析即拒 | 仅 Vibe-Trading（LiveOrderGuardTool + check_mandate 固定顺序八查 + HALT 哨兵 + 对账不重发 + repeatable=False） |

**逐项目归位一行版**：FinRobot 停在 ①；TradingAgents 到 ②；ai-hedge-fund 到 ③；Vibe-Trading 覆盖 ①—⑤。

**财务合规应选的层**：① 只是文案，任何合规声称不能建立在此（FinRobot 是完整反例——风险控制 = 让 LLM 写风险分析文本）；② 是必备输入卫生；③④⑤ 职能不同必须齐备——③管「量」（限额裁剪，ai-hedge-fund 样板）、④管「权」（谁能批多少、授权有效期，Vibe 样板：mandate 默认 30 天强制过期、「live mandate 不许永生」）、⑤管「不可逆动作的最后一道门」（Vibe 样板）。TradingAgents 恰好演示只有 ①② 的形态：决策质量靠辩论提升但输出零强制力——适合做「决策建议器」，做不了「审批执行器」。另一个不可忽视的设计细节：④ 的合同对象用 frozen dataclass 而非 Pydantic（Vibe，零验证面防 agent 利用解析差异），说明「给 agent 读的合同不要留可利用空间」。

## 4. 状态与审计共性

| 机制 | 记什么 | 防篡改 | point-in-time | 回放 |
|---|---|---|---|---|
| TradingAgents 决策日志（TradingMemoryLog） | 每次决策 pending → resolved（真实 outcome + 反思），append-only markdown | ❌ 明文文件 | ✅ resolution_date 过滤防回测偷看未来 | 🔶 每次运行全量 state JSON 供复盘 |
| ai-hedge-fund PromptCache + CycleRecord | 每个 Signal 的精确 prompt/response/snapshot_hash；一个 tick 的全量回执（spec 审计副本/信号/净额前后权重/clamp/订单/NAV） | ❌ 本地文件 | ✅ 快照只含 filing 前数据（market_cap latest-only 陷阱是现成案例） | ✅✅ 同输入字节级一致，缓存即重放 |
| Vibe-Trading 哈希链账本 + run manifest | 每笔真实资金动作（含被拒与 halt）扇出三 sink；run 级方法论指纹 | ✅✅ seq + prev_record_hash，append 前验链、断链拒绝追加 | ✅ grounding 预取真实数据防训练数据价格 | ✅ events.jsonl 支持 SSE 回放 |
| FinRobot request_logs | API 使用审计（user/endpoint/status/耗时），中间件零侵入 | ❌ SQLite 可改 | ❌ | ❌ V0 会话后 reset，决策无痕 |

三个成熟度台阶：**使用审计**（FinRobot：谁调了什么接口）→ **决策审计**（ai-hedge-fund / TradingAgents：每个决策当时的输入/推理/输出可追溯，回答「当时知道什么」）→ **合规审计**（Vibe：记录不可篡改 + 方法论版本可指纹 + 问责链到人工授权，回答「记录没被改过、在什么规则版本下产生、谁授权的」）。财务硬要求落第三级，但第二级的「缓存 = 审计 = 调试三合一」（PromptCache）是最经济的起步设计。

共性 primitive 值得点名：**append-only、内容寻址哈希、时点纪律**——四仓中凡做了审计的都至少占其二（cache key / snapshot_hash / record_hash 各自承担「输入相同则记录相同」的确定性主张；TradingAgents 三处 look-ahead 过滤与 ai-hedge-fund 的 PIT 快照是同一纪律在不同层的表现）。另两条版本化审计先例：「图形状签名进 checkpoint key，改图后旧执行态自动作废」（TradingAgents）与「方法论指纹可 diff」（Vibe manifest，刻意排除 timestamp/run_id）共同回答「流程版本变了什么」——对财务 agent 的合规意义：**审计记录必须绑定产生它的规则与拓扑版本，否则重放无法解释**。并发一致性方面本组都很朴素（per-ticker 分库 SQLite、跨进程 flock），无跨机方案——企业多实例部署时哈希链账本与审批状态的并发语义需要自行设计，是组内共同的留白。

## 5. 组内分化点与教训

1. **宣称 vs 实现落差是 A 组通病**：FinRobot 的 bull/bear/judge 辩论、Smart Scheduler、四层架构全部来自闭源 V2/论文，开源代码没有；TradingAgents README 的「PM 审批后送模拟交易所执行」——代码无 approve/reject 分支、无任何 broker 调用；ai-hedge-fund 的 paper/live/ledger/scheduler/CPCV 均为 roadmap（ledger 只有写半边）。任何能力宣称必须逐条对码，且要注明证据属于代码还是【文档】。
2. **真金白银是最好的架构纪律**：唯一碰真实资金的 Vibe 拥有组内唯一完整的合规链，纯模拟项目风控全部停在 prompt 层——「教育/研究定位」会系统性弱化风控需求。推论：本项目合规组件不能指望从模拟项目抄，只能从 Vibe（或自建）来。
3. **拓扑自由度与可审计性此消彼长**：FinRobot 自由群聊（TERMINATE 字符串终止、reset 无状态）↔ ai-hedge-fund 零自由度管线（字节级可重放）。图编排的价值在中间态：拓扑显式声明、可静态审计；LangGraph（TradingAgents）与 YAML DAG（Vibe）是同一目标的两种载体。
4. **工程债样本**：FinRobot 两代 requirements 并存钉死旧版、默认 reload=True、OAuth 回调端口硬编码错；TradingAgents 嵌套 state 无 reducer 手工全量回填（漏一个键静默丢数据）；ai-hedge-fund 无并发无 DB（单进程假设）——再次支持「抄模式不引依赖」。
5. **风险意见与风险执行必须分离**：Vibe 把 advisory（fail-open、绝不阻塞、默认关）与 mandate gate（fail-closed、唯一权威）的分离写成设计原则——混用会把外部依赖的可用性变成资金链路的可用性风险。财务系统同理：外部风控建议服务挂了不该阻断合规门，也不能因「建议通过」绕过门。
6. **多代架构并存**（FinRobot V0/V1 同仓互不依赖、ai-hedge-fund v2 全量重写）：仓库快照可能同时含新旧两套答案，引用前先确认哪条是现役链路——与 B 组教训一致，属跨组通病。

## 6. 对本项目的启示清单

1. 决策拓扑分场景双轨：月结审查/报销初审用「并行独立审查 → 代码加权合成 → 硬规则 clamp」（agent 间不对话）；需要对抗推理处（付款建议、争议事项）用固定轮次辩论 + deep 模型裁决——来源：ai-hedge-fund.md §2、TradingAgents.md §2/§8。
2. 立「LLM 影响力终止于建议」总纲：agent 产物经 schema 校验后进纯函数管线（合成/裁剪/生成动作），风控 clamp 事件（limit/before/after）逐条入审计——来源：ai-hedge-fund.md §5（risk/limits.py + VISION 原则）。
3. 授权不可达：付款限额/科目权限/白名单的写入口只放审批服务 API（带人工 consent_ack），不进 agent 工具注册表、不可被自省发现；agent 侧只留 propose 类工具（持久化不授权）——来源：Vibe-Trading.md §5（commit_mandate 命门不变量）。
4. 付款门做成 fail-closed 纯函数：固定检查顺序（黑名单→客户/科目→单笔→累计→频次→预算），任何输入不可解析/数据缺失即 DENY；三态裁决 ALLOW/DENY/PAUSE_FOR_REAUTH，结构性违规与定量违规分流——来源：Vibe-Trading.md §5（enforcement.py#check_mandate）。
5. 解析失败必须可见：不可解析的决策返回哨兵状态（如 REVIEW）进人工队列，绝不静默降级为通过/中性；LLM 脏输出做字段级归一（"N/A"/百分比/带货币符号数字）——来源：TradingAgents.md §5（signal_processing.py、schemas.py）。
6. 审计起步用「缓存即审计」：每个 LLM 决策的 prompt/response/输入快照哈希按内容寻址落盘，合规回放天然免费；资金动作升级为哈希链账本（seq+prev_hash、append 前验链、断链拒写）——来源：ai-hedge-fund.md §4（llm/cache.py）、Vibe-Trading.md §5（governance/ledger.py）。
7. 决策日志 pending→resolved：决策当下只存 pending（不增加 LLM 调用），事实发生（月结完成/付款核销）后回填 outcome 与反思，带 resolution_date 供时点过滤——离线复盘闭环同时就是审计流水——来源：TradingAgents.md §4（memory.py）。
8. 工作流版本进审计键：图形状/拓扑签名进 checkpoint key（定义变更自动作废旧执行态），run 级方法论指纹（prompt/skills/工具/版本 → 一个 hash，可 diff）回答「结论在什么规则版本下产生」——来源：TradingAgents.md §4、Vibe-Trading.md §4（manifest.py）。
9. 物理制动独立于 agent 服务：kill switch 做成不依赖 LLM/主循环/SSE 存活的开关（服务化后为独立存储标志位 + 每动作前检查），payload 损坏视为已触发（fail-closed）——来源：Vibe-Trading.md §5（halt.py）。
10. 外部工具/业务 API 读写三级分类：default-deny，UNKNOWN 一律按写走审批门；不可信服务自述注解只能降级不能升级，维护者 curated map 优先——来源：Vibe-Trading.md §5（classification.py）。
11. 不可逆动作崩溃恢复 = 对账不重发：动作前写 crash-safe 副作用标记，重启后拿对端证据对账关闭重发窗口，mutation 永不自动重试——来源：Vibe-Trading.md §5（pending_action.py）。
12. 长图工作流上下文纪律：阶段结束裁剪消息、只向下游传结构化报告字段（防膨胀与串扰）；辩论/审查轮次纯计数器封顶（token 可预算）；deep 模型只配给裁决节点——来源：TradingAgents.md §2（MsgClear 节点、conditional_logic、deep/quick 配置）。
13. 反幻觉三板斧进 prompt 工程规范：预取真实数据注入（grounding）+ 数字溯源硬规则（无溯源必标「无法获取」）+ 领域否定清单（无引擎不得报该数字）——来源：Vibe-Trading.md §2（worker.py#build_worker_prompt、investment_committee.yaml）。
14. worker 产物六分类含 incomplete：专设状态捕获「跑完但没实质交付」（空计划/伪造数字/零调用零报告），作为多 agent 工作流的质量闸门——来源：Vibe-Trading.md §2（models.py#WorkerStatus）。
15. 给 agent 读的合同对象不留解析面：授权/限额等结构用不可变、零验证歧义的形式（Vibe 用 frozen dataclass 而非 Pydantic 的动机）——来源：Vibe-Trading.md §8（避坑）。
16. 「回测即生产」一管线三模式：同一编排代码只换时钟与执行器跑模拟/回放/生产，杜绝研究实现与生产实现漂移；合规回放 = 历史时钟 + 记录的 LLM 响应（prompt cache 命中即精确重放）——来源：ai-hedge-fund.md §2/§8（run_cycle.py、backtesting/fund.py）。
17. 授权合同带生命周期：mandate 默认 30 天强制过期、commit 时重新校验 profile 未突破用户所见上限——财务侧「调额/解冻」授权同样应有有效期与所见即所批校验——来源：Vibe-Trading.md §5（mandate/model.py、commit.py）。
