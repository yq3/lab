# D 组横向：研究 / 浏览器自动化（快扫级）

> 输入：`profiles/gpt-researcher.md`、`profiles/browser-use.md`（两档案本身即快扫级，基线与源码路径见各档案）。两项目同属「信息获取」域，但执行形态处于光谱两端：gpt-researcher 把 LLM 当固定流水线上的**文本处理器**，browser-use 把 LLM 当感知-行动循环（perceive-act loop）里的**决策器**。对财务场景的价值不在编排与合规（两者均无服务级审批/审计），而集中在工具契约与凭据协议两处工程设计。

## 1. 执行形态对比：固定流水线 vs 感知-行动循环

| 维度 | gpt-researcher（档案 §2） | browser-use（档案 §2） |
|---|---|---|
| 主循环 | 无 function-calling 循环：`GPTResearcher` 组合 7 个 skill 对象，LLM 只在固定点位被调用（选题/拆 query/压缩/写作） | 五段步循环 `_execute_step`：取浏览器状态摘要 → 历史压缩 → LLM 结构化输出 → 执行动作队列 → 后处理 |
| 动态性来源 | 编排层：子查询 `asyncio.gather` 并发、爬取 WorkerPool 限速；深度研究=递归 breadth/depth 逐层减半 + Semaphore 限并发 | 模型层：每步从约 25 个动作 schema 的动态联合中选；`evaluation_previous_goal/memory/next_goal/plan_update` 自省字段强制逐步评估 |
| 上下文策略 | 每子查询爬取结果经向量压缩（相似度过滤+top-10 截断）后拼接为总 context，可选 LLM 筛源 | DOM 序列化四步管线（可点检测→paint-order 过滤遮挡→剪枝→索引分配），索引从 `backend_node_id` 派生、跨步复用尽量不漂移 |
| 终止条件 | 流程走完即终（无对话终止词问题）；深度研究仅 depth/breadth 软顶 | `done` 动作（只准单动作 + prompt 反幻觉约束）+ max_steps / max_failures / step_timeout 三重熔断 |
| 多 agent | 旁路产品线 `multi_agents/`：LangGraph 固定拓扑（browser→planner→human→researcher→…→publisher）+ human 计划回环限次；FastAPI 主服务默认走单 agent 流水线 | 无编排层（旧 `browser_use.workflow` 已不存在；编排型 Workflow 是 Cloud 闭源概念） |
| 失败契约 | 无重试环：换 provider / 跳过坏 URL；`visited_urls` 跨子查询与父子 researcher 共享去重 | 连续失败计数停机；`AgentHistoryList` 持久化 + 重放纠错（索引重映射、菜单展开重放） |

**核心判断**：「LLM 是文本处理器还是决策器」直接决定系统在可控性-灵活性轴上的位置——前者的行为空间可枚举（每步调什么模型、输入是什么，可静态审计），后者是开放集合（靠守卫与熔断兜底）。这与 B 组「确定性管线 ↔ 自由 agent」信任轴结论互证：财务主链路应取前者；后者形态只配用于「无人预认知的界面/文档操作」子任务，且必须包在审批门与域白名单之内。

## 2. 工具设计的可迁移模式

**模式 1｜能力声明式契约 `requires_scraping`**（gpt-researcher 档案 §6）
- 实现：`BaseRetriever` 类属性声明「返回 URL 待爬 / 已带全文」，取代旧版 `len(raw_content)>100` 启发式——后者导致长 snippet 被误当全文、引用丢失（#1846/#1892，docstring 亲录教训）。
- 迁移要点：财务数据源适配器 SPI 用注解显式声明读写语义 / 是否含派生列 / 是否 point-in-time，禁止从返回内容形状推断能力——启发式契约 = 潜行数据缺陷。

**模式 2｜`<secret>` 占位符凭据协议**（browser-use 档案 §6，D 组对财务最有价值的样板）
- 实现：五步闭环——① LLM 只见按当前页域过滤后的**键名清单**，prompt 指示用 `<secret>key</secret>` 引用；② 执行时递归替换标签为真值，**只有域匹配的 secret 可替换**（支持 TOTP 后缀键现场生成）；③ input 动作回注消息只写 `Typed <password>`；④ 历史压缩与 `save_to_file` 落盘再做一遍 redaction；⑤ 配了 sensitive_data 未锁 `allowed_domains` 启动即警告提示注入风险。
- 迁移要点：等价于「密码不出密管、LLM 与审计全程只见掩码」——可直接移植为 Java 凭据引用协议（密管下发引用键 → 工具执行层域限定解析 → 回注/落盘前统一脱敏）。

**模式 3｜动态动作空间裁剪**（browser-use 档案 §2/§6）
- 实现：动作注册可带 `domains=[...]`，`_update_action_models_for_page` 每步按当前页 URL 重建输出 schema 联合。
- 迁移要点：模型看不见的能力不可被提示注入诱导调用（与 opencode「deny 工具从 LLM 工具列表移除」同构，C 组档案 §2.1）；财务 agent 应按用户权限/账套/场景动态裁剪工具面，而非全量注册+执行时拦截。

**模式 4｜双层页面变更守卫**（browser-use 档案 §2）
- 实现：静态声明（`terminates_sequence=True` 的动作——navigate/search/switch_tab——后自动丢弃剩余队列）+ 运行时检测（每动作后比对 URL 与焦点，变化即截断）。
- 迁移要点：「对陈旧 DOM 执行既定计划」的通用对应物是「对陈旧业务状态执行多步计划」——审批期间基础数据（余额/汇率/授权额度）一变即作废后续步骤，防「批完 A 版执行 B 版」。

**模式 5｜watchdog 事件总线**（browser-use 档案 §5）
- 实现：14 个 watchdog（security 域/IP 拦截 + 重定向后二次校验、captcha、downloads、permissions、crash、dom…）挂 session 事件总线；`allowed_domains` 与 sensitive_data 域 pattern 联动校验。
- 迁移要点：安全策略与动作实现解耦——Java 侧用 Spring 事件/切面链承载「目标白名单/频次/敏感目标」检查，新增策略不改工具代码。

**模式 6｜MCP 执行策略分档 + 会话配置隔离**（gpt-researcher 档案 §6）
- 实现：MCP 检索器 fast（原 query 一次+缓存）/ deep（每子查询）/ disabled 三档，`asyncio.Lock` 防并发重复填缓存；会话级 MCP 配置改 `cfg.retrievers` 而非 `os.environ`（#1676，防进程级环境污染）。
- 迁移要点：外部工具按成本-精度分档调用；「会话配置不落全局环境」是多租户服务的必备细节。

**模式 7｜分步成本归集**（gpt-researcher 档案 §4）
- 实现：`add_costs(cost)` 按 `_current_step` 归集、`get_step_costs` 可查——无计量系统时的最低成本方案。
- 迁移要点：财务 agent 每阶段的 token/调用成本天然是合规留痕字段（对照 codex TokenUsageRecord 独立持久化项，C 组档案 §4）。

## 3. 对财务场景的适用边界与教训

**gpt-researcher——流水线可控性是合规资产，服务化与预算护栏是缺口**（档案 §5/§7/§8）
- 可取：「规划→并发执行→压缩汇总」直接映射财务「取数任务分解→并发查多数据源→汇总」；provider 注册表 + 能力声明是适配器 SPI 样板；主流程无人工门反衬出审批应当是独立服务的事、不是流水线内嵌的事。
- 缺口：① 唯一审批点在旁路 `multi_agents` 的 LangGraph human 节点，依赖 WebSocket 阻塞等待（`receive_text()`），服务化必须换异步审批工单/外化审批 API；② 无鉴权/多租户/队列，报告=单 JSON 文件读写锁；③ 深度研究递归无预算硬顶（仅 depth/breadth 软顶）、子查询 gather 无并发上限（仅爬取层限流，易打爆下游 API）。

**browser-use——协议可移植，执行域不可移植，审批靠宿主**（档案 §5/§8）
- 内置 HITL 为零：`run()` 只有 on_step_start/end 钩子 + pause/resume/stop（SIGINT 一次暂停、两次强退的信号协议）；风控全在 watchdog 与 prompt 约束（DoneAction 反幻觉）——合规门必须由宿主在钩子里实现。
- 可移植资产即 §2 模式 2/3/4/5；不可迁移：CDP/DOM 序列化/索引稳定性等浏览器领域机制；Cloud 侧编排/判官/Profile Sync 闭源不可引证。
- 避坑：sensitive_data 旧格式 `{key: value}` 全域暴露，必须用域限定新格式并配 allowed_domains；结构化输出对 empty-object 敏感的模型需 NoParamsAction 类兼容补丁（Java 侧 JSON-schema 兼容选型同理）。

**共同教训——并行产品线与证据等级**
- gpt-researcher 三线并存（单 agent 主链 / multi_agents LangGraph / deep_agents），且 FastAPI 主服务不走 LangGraph 线；browser-use 的 OSS 库与会话持久化/编排/判官分居两侧。引用能力前先确认现役链路与证据等级（代码 vs【文档】）——与 A 组 FinRobot（V2 辩论闭源）、B 组 WrenAI（审计是商业版）「宣称 vs 实现」通病一致，属 18 仓跨组通病。
- 两仓共同证明：D 组形态（研究/浏览器）都从「只读为主、低危场景」长出来——审批与租户缺席不是疏忽而是场景使然。财务场景引用其模式时，必须把隐含的「低危假设」显式替换为分级审批假设。
