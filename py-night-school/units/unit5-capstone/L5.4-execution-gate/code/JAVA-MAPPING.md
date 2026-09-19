# JAVA-MAPPING.md —— 毕业设计模式 → Java 栈对应物与翻译坑

> 本教程双目的的兑现物：Python 侧学到/写到的每个模式，翻回你的 Java 栈时对应什么、
> 哪里会踩坑——可直接作为 Java 侧开发任务拆解的输入（一行 = 一个可派工的迁移件）。
>
> **诚实纪律（写表前先立规矩）**：Java 对应物只写**从本地克隆核实过**的 API——
> langgraph4j@`c2cf2e33`、spring-ai-alibaba@`f82da0b50`（核实锚点见文末）；克隆里
> 不存在的对应物老实写「**需自建**」+ 一句为什么。禁止编造 API 名——一张掺了想象
> 的迁移表比没有表更危险（Java 侧同学会照着不存在的类名抄 import）。
>
> 学员任务（ex3）：下表有 **4 行的 Java 对应物留了 TODO**——对照本地克隆补全它们；
> 校验器 `exercises/ex3_mapping.py` 检查四列齐 + Java 列非空。参考对照版在
> `solution/JAVA-MAPPING.md`（行尾 golden answer 诚实降级：开放设计不硬造判分）。

| 模式 | Python 侧（本 PoC） | Java 对应物（核实自本地克隆） | 翻译坑 |
|---|---|---|---|
| StateGraph 装配 | `graph.build_graph`：`StateGraph(ExpenseState)` + `add_node`/`add_edge` + `compile(checkpointer=…)` | langgraph4j `StateGraph`（`langgraph4j-core/…/StateGraph.java`）：`new StateGraph<>(Map<String,Channel<?>>, AgentStateFactory)` → `addNode(String, AsyncNodeAction)` → `addEdge(String, String)` → `compile()`；saa 同名 `com.alibaba.cloud.ai.graph.StateGraph`：`new StateGraph(KeyStrategyFactory)` + `addNode(String, AsyncNodeAction)` + `compile(CompileConfig)` | Java 节点动作返回 `CompletableFuture<Map<String,Object>>`——**状态是 Map 不是对象**，键名拼错编译期不查；`compile()` 抛 checked `GraphStateException`，装配代码得 try/catch（Python 是运行时 `ValueError`） |
| 条件边路由（三分支） | `route_after_gate`/`route_after_submit`/`route_after_execute` 返回节点名字符串或 `END` | langgraph4j `addConditionalEdges(String, AsyncEdgeAction<State>, Map<String,String> mappings)`（StateGraph.java）——路由函数 + **分支映射表**两件套；saa 同签名 | Python 返回什么就路由到什么；Java 必须把每个返回值登记进 `Map<String,String>` 映射表——**漏一个 key 编译期不报、跑到了才炸**；END 常量两边都有（`StateGraph.END`）但类型是 String |
| 状态 schema 与 reducer | `ExpenseState(TypedDict)`：`Annotated[list, operator.add]`（合并）、`merge_results`（dict 合并）、`NotRequired[Plan]`（覆盖、单写者） | langgraph4j：`Channels.appender(ArrayList::new)`/`Channels.base(Reducer)` 逐键声明（state/Channels.java），`Reducer<T> extends BiFunction<T,T,T>`；saa：`KeyStrategyFactoryBuilder().addStrategy("messages", KeyStrategy.APPEND)`——REPLACE/APPEND/MERGE 三策略（KeyStrategy.java） | TypedDict 是「带注解的 dict」——键可以缺省（`NotRequired`），AgentState 是类+Map 双层：**缺省键语义要自己约定**（getOrDefault？还是 null？）；dict 合并 reducer 在 Java 要手写 `Map.merge`/`putAll` 的小心版本（同键谁赢） |
| interrupt / Command(resume)（审批暂停恢复） | `graph.submit` 里 `interrupt(payload)`；恢复 `Command(resume={"action": "approve"})`（L5.2 换芯） | langgraph4j：节点实现 `InterruptibleAction<State>.interrupt(nodeId, state, config)` 返回 `Optional<InterruptionMetadata>`（action/InterruptibleAction.java）；恢复 = `compiled.invoke(null, config)`（`GraphInput.resume()`，CompiledGraph.java）；saa：`InterruptableAction` + 恢复 `workflow.stream(null, RunnableConfig.builder().resume().build())`（InterruptionTest.java 原式） | Python 的 `interrupt()` 像「会返回值的 await」——payload 进、resume 值出，节点代码线性；Java 侧是**接口回调 + null 输入恢复**两个动作，恢复值走 `RunnableConfig` 的 metadata（saa 的 `HUMAN_FEEDBACK_METADATA_KEY`）而不是函数返回值——节点要自己查 metadata，代码形状完全不同 |
| checkpointer（挂起态落盘） | `AsyncSqliteSaver` + `thread_id`（`graph.open_saver`）；进程内 `InMemorySaver`（demo 驱动器） | langgraph4j core 自带 `MemorySaver`/`FileSystemSaver`（checkpoint/ 目录）；SQLite/Postgres 等 JDBC saver 在**独立模块**（langgraph4j-sqlite-saver / -postgres-saver）；saa：`checkpoint/savers/MemorySaver.java`、`savers/file/FileSystemSaver.java`、`PostgresSaver`/`MongoSaver`（compile 时经 `SaverConfig` 注册） | Python 侧状态里是 Pydantic 对象——serde 白名单（`JsonPlusSerializer(allowed_msgpack_modules=…)`）锁死可反序列化类型；Java 侧各 saver 自带 Serializer（Kryo/JSON 路线）——**两边都要防反序列化白名单漂移**，且 aiosqlite「连接不关进程挂住」的坑在 JDBC 侧不存在（连接池管）但裸 DriverManager 同样漏 |
| Plan 判别联合（结构化输出契约） | `plan.py`：`Annotated[FetchClaimStep \| FetchBudgetStep \| VerifyInvoiceStep, Field(discriminator="tool")]`——Literal tag 分派 | TODO(ex3)：对照本地克隆/spring-ai 文档补全（提示：Java 侧的判别联合是语言级机制 + JSON 绑定库注解的组合，不是 Pydantic 这种单注解） | 提示（补全时想清楚再写）：①多余字段拒绝——Pydantic `extra="forbid"` 在 Jackson 默认是**忽略**未知字段，要对齐得显式配 FAIL_ON_UNKNOWN_PROPERTIES；②判别符不认识——Pydantic 报 `union_tag_invalid`（映射成 `unknown_tool` 拒绝码），Jackson 报的另一类异常——**错误分类翻译各写各的** |
| 审批外化 API（REST + SSE + 后台 run） | `api.build_app(service)`：FastAPI `POST /runs`（asyncio 后台跑到暂停）、`StreamingResponse` SSE、`EventLog` 重放（L5.2） | Spring MVC 照抄语义（A1 的 Java 直觉侧）：`@RestController` + `SseEmitter`（emitter 挂请求、`onCompletion`/`onTimeout` 回调要手动接）+ `CompletableFuture`/`DeferredResult` 挂起建单请求 + `ExecutorService` 跑后台 run——FastAPI 无对应「emitter 对象」：推流是**异步生成器 yield 帧** | Python 侧断线重连是 `Last-Event-ID` 头 + 事件表重放（一张表两用）；Java 侧 SseEmitter 的完成/超时/错误回调不接会**静默漏事件**；后台 run 在 asyncio 是 `create_task`（协作式），在 Spring 是线程池——「挂起不占线程」这句话只对 asyncio 成立，CompletableFuture 占的可是池子里的线程（虚拟线程另说） |
| 事件溯源（append-only 审计） | `eventstore.EventStore`：`events(aggregate_id, seq)` 主键唯一索引、无 update/delete、`fold`/`replay` 投影 | **Axon Framework 的 `EventStore`**（aggregateId + sequenceNumber + replay，词汇直接平移）；不上框架则 **JPA 事件表 + `(aggregate_id, seq)` 唯一索引**自建——冲突翻译成语义异常（对标 `EventSeqConflict`） | Axon 自带聚合跟踪与 upcaster（事件 schema 演进）；自建 JPA 版要自己管：唯一索引冲突→`DataIntegrityViolationException` 的翻译、重放投影的幂等、以及「Repository 上不给 update/delete 方法」——**append-only 在 Java 靠接口形状，不靠 JPA 声明** |
| fail-closed 执行门（三态检查链） | `gate.check_intent`：纯函数七查固定顺序、`GateVerdict{ALLOW/DENY/PAUSE_FOR_REAUTH}`、不可解析即 DENY、时钟/账本注入 | TODO(ex3)：对照讲义 §2 与 L4.3 读过的 enforcement 原型补全（提示：Java 侧没有框架级的「门」，这是**你自己写的一个类**——想清楚它的形状：静态方法？enum？异常还是返回值？） | 提示（补全时想清楚再写）：①L4.3 读过的 Vibe-Trading `check_mandate` 就是 Java 域原型——纯函数 + 常量顺序 + BreachEvent；②Java 有 checked exception 的「要么 catch 要么 throws」，反而容易写出「catch 后返回 null」——**门的返回值里没有 null 的位置**（连 ALLOW 都是一等值）；③顺序即语义：私有检查方法的调用顺序就是审计契约 |
| 缓存即审计（LLM 决策留原话） | `audit_cache.DecisionCache`：`llm_decisions(prompt_hash PRIMARY KEY, prompt, response)` + `AuditedModel`（Runnable 装饰） | TODO(ex3)：补全（提示：JPA Entity + 主键点查 + upsert 是最小形状；装饰层对标 Spring 的 `Advisor`/代理——想清楚「换的是芯不是壳」在 Java 怎么表达） | 提示（补全时想清楚再写）：①canonical 序列化要在 Java 重写——langchain4j 消息对象的 type 名与 langchain 不同（`user`/`assistant` 两侧方言），**哈希口径要用测试锁死**（同 prompt 两侧必须同 hash，否则迁移后缓存全 miss 且审计对不上账）；②INSERT OR REPLACE ≈ save()+@Id，但「最新原话覆盖旧原话」的审计语义要想清楚 |
| 图版本绑定（改图作废旧执行态） | `versioning.topology_signature`（节点+边排序哈希）→ `run_key` → `assert_compatible` 续跑守门 | **需自建**——langgraph4j/saa 都没有拓扑签名 API（核实过 `StateGraph`/`CompiledGraph` 无 signature 方法） | 自建时**签「拓扑形状」不签「字节码/源码」**：节点名+边+条件性排序序列化后哈希——签字节码会随编译器/JVM 版本漂移；saa 的 `StateGraph.getGraph(GraphRepresentation.Type)` 能导 Mermaid/PlantUML 类图（DiagramGenerator 生成）但不能当签名用（格式不稳定） |
| 当日账本（日历聚合投影） | `graph.PaymentLedger`：`ledger:<date>` 聚合上 `payment.executed` 事件的投影——读=当日已付清单，写=append | **需自建**——无现成对应物；最贴近的是 SQL 视图/物化视图（`SELECT … WHERE type='payment.executed' AND day=?`）或 CQRS 读模型 | 别建第二张「payments 表」——**事件表即账本**，账本是投影不是主存；JPA 侧 temptation 是写个 `PaymentRepository.save()`，一旦写了就出现双写一致性问题（事件 vs 表谁赢？）——投影只读、重建可丢弃，这是它和表的本质区别 |
| 拒绝回环（人审反馈回喂） | `submit --(reject)--> drafter` 回边 + `approval_rejects` 合并账本 + `MAX_APPROVAL_LOOPS` 封顶 + 双哨兵分码 | TODO(ex3)：补全（提示：图侧是条件边回环 + 计数状态键；Java 侧对应 langgraph4j/saa 的哪个 API 能改状态再回环？核实 `CompiledGraph.updateState`） | 提示（补全时想清楚再写）：langgraph4j `CompiledGraph.updateState(config, values, asNode)`（CompiledGraph.java，saa 同名）≈「以某节点身份补写状态」——反馈消息回喂用它；**封顶计数器在哪算**（路由函数里数 vs 节点里数）决定哨兵分码能不能写对 |

## 核实锚点（Java 侧 API 名的出处，本地克隆 `~/develop/opensource/`）

- `langgraph4j/langgraph4j@c2cf2e33#langgraph4j-core/src/main/java/org/bsc/langgraph4j/StateGraph.java`
  —— `addNode(String, AsyncNodeAction)` L218、`addEdge` L353、`addConditionalEdges(String, AsyncEdgeAction, Map)` L408、`compile()` L452；
- `langgraph4j/langgraph4j@c2cf2e33#langgraph4j-core/src/main/java/org/bsc/langgraph4j/action/InterruptibleAction.java`
  —— `interrupt(nodeId, state, config)` → `Optional<InterruptionMetadata>`；
- `langgraph4j/langgraph4j@c2cf2e33#langgraph4j-core/src/main/java/org/bsc/langgraph4j/CompiledGraph.java`
  —— `invoke(null, config)` 走 `GraphInput.resume()`（L522）、`updateState(config, values, asNode)` L242、`getState` L203；
- `langgraph4j/langgraph4j@c2cf2e33#langgraph4j-core/src/main/java/org/bsc/langgraph4j/state/Channels.java`
  —— `appender(Supplier)`/`base(Reducer)`（Reducer extends BiFunction）；
- `langgraph4j/langgraph4j@c2cf2e33#langgraph4j-core/src/main/java/org/bsc/langgraph4j/checkpoint/MemorySaver.java`（同目录 `FileSystemSaver.java`；JDBC savers 在 langgraph4j-sqlite-saver / -postgres-saver 等模块）；
- `alibaba/spring-ai-alibaba@f82da0b50#spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java`
  —— 构造器 `StateGraph(KeyStrategyFactory)` L170、`addNode(String, AsyncNodeAction)` L244、`compile(CompileConfig)` L535；
- `alibaba/spring-ai-alibaba@f82da0b50#spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/KeyStrategy.java`
  —— `REPLACE`/`APPEND`/`MERGE` 三策略常量；
- `alibaba/spring-ai-alibaba@f82da0b50#spring-ai-alibaba-graph-core/src/test/java/com/alibaba/cloud/ai/graph/InterruptionTest.java`
  —— interrupt + 恢复的产品测试原式：`workflow.stream(null, RunnableConfig.builder().resume().build())`。

## 词汇表（两侧名词对齐，开 Java 侧任务会时用）

| 本 PoC 词 | langgraph4j 词 | saa 词 | 备注 |
|---|---|---|---|
| 节点 node | `AsyncNodeAction`（实现）/ Node（声明） | `AsyncNodeAction` / `Node` | Java 侧「节点」是函数式接口实现 |
| 条件边 conditional edge | `AsyncEdgeAction` + mappings | 同 langgraph4j | 路由值必须显式登记进映射表 |
| 状态 state | `AgentState`（Map 底座） | `AgentState` | 键名拼错编译期不查 |
| reducer | `Reducer` / `Channel` | `KeyStrategy`（REPLACE/APPEND/MERGE） | 合并语义逐键声明 |
| 检查点 checkpoint | `Checkpoint` + `BaseCheckpointSaver` | 同名 `BaseCheckpointSaver` | thread_id ↔ `RunnableConfig.threadId` |
| 暂停/恢复 | interrupt / `invoke(null, cfg)` | `InterruptableAction` / `RunnableConfig.builder().resume()` | saa 恢复值走 metadata |
| 聚合 aggregate | 无内置（Axon 有 `AggregateIdentifier`） | 无内置 | 事件表的 aggregate_id 是自定纪律 |
