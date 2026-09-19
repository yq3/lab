# L3.8 对照总结课：mini-agent vs 四框架——决策表、跳读指南与结业自查

> Unit 3 收口。前七课你把同一道报销单审查题交给了五个框架重做（langgraph 占两课，
> 末站还隔着栏杆看了一眼平台）；昨晚里程碑的选型工作台跑完——`bench.py` 五课时契约
> 重验、`tablegen.py` 数出依赖数与手写总行数、五页对照笔记落定，手里握着**自己跑出
> 的**选型数据。今晚把这些体感收成一张**能重新推导的决策表**：每个数字有口径、每个
> 事实有出处、每个定性结论有源码证据——CURRICULUM §7「框架」判据的结业形态，是能
> 重新推导，而不是背下来。

## 1. 本课目标

不写新 agent——换一种交付物。完成后你能：

- 用 `code/tablegen.py` 重新生成「能力-成本-锁定性」决策表数据页，并**逐格说出取数口径**
  （依赖数怎么数的、装配行数什么口径、轮数是哪一课实测的）——宪法纪律「量化结论必须
  可复现」的选型版落地；
- 对六个维度（HITL / 检查点 / 扇出 / 子代理 / 调试器 / eval）与三种锁定性
  （端点中立 / 私有格式 / 生态绑定）各给出一个**带课次出处的机制证据**；
- 拿着五个不设编程课的框架仓（crewai / llama_index / agentscope / langchain /
  MS agent-framework）的跳读路线，各花 30 分钟找到它的核心抽象入口——
  已了解架构之后，「快速跳读」是有方法的；
- 填完**结业自查表**（本课固定收尾）：对齐 CURRICULUM §7 框架判据，逐条可勾选。

**完成判据**：本目录下三条命令同时全绿——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

发货态诚实说明：`code/` 讲义区绿，`exercises/` 是设计内的红（TODO 未填）。

本课运行依赖**仅标准库**（解析 TOML 与统计行数都不需要第三方包）——决策表生成器
本身就是一个「零依赖也能干重活」的样本。`.env.example` 照宪法随课携带（本课无
真实端点调用，留给同目录其他命令的习惯延续）。

## 2. 概念讲解

先给全课对照表（Java 同学先看这张再往下读）：

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| 技术选型评审表（容量/风险/迁移成本列） | 能力-成本-锁定性决策表 | 三维同构；差别在定量列——Python 生态的依赖数可以从锁文件直接机器数，Java 侧要 `mvn dependency:tree` 解析 POM 才有树 |
| Maven 依赖树的大小（dependency:tree 的节点数） | uv.lock 的 `[[package]]` 计数（tomllib） | 同一个信号：传递依赖的重量；uv.lock 是锁文件即事实，不用解析仓库元数据 |
| ArchUnit 自定义规则 / SonarQubit 度量 | ast 口径行数统计（count_loc / tablegen） | 都是把「评审标准」写成可执行检查——不靠 grep 印象，口径写在代码里 |
| 供应商锁定 / Spring 生态迁移成本 | 锁定性三格（端点中立/私有格式/生态绑定） | Java 老话题的新拼写：从「换消息中间件」变成「换模型端点 / 换框架 / 迁出平台」 |
| Jackson 序列化的版本兼容矩阵 | Checkpoint msgpack / RunState JSON / DSL version | 私有序列化格式的 `version` 字段管导入策略，不管行为兼容（L3.7 §5 的教训） |
| `javac` 编译期全量检查 | 「重新生成一遍」的验收 | 决策表的可信度不来自讲义，来自任何人重跑同一命令得到同一页 |

### 2.1 比较基准：抽象光谱是第一坐标

Unit 3 的框架课沿一条光谱展开，比较之前先钉住你站在哪一格：

```text
SDK（原语）      →  openai-agents（L3.1）：Agent/Runner，循环进框架、零件全给你
图引擎           →  langgraph（L3.2–L3.4）：StateGraph/条件边/checkpoint/Send
harness（工作台） →  deepagents（L3.5）：虚拟文件系统/子代理/记忆的中间件栈
全家桶           →  adk-python（L3.6）：五服务+调试器+eval+部署 CLI
平台             →  dify（L3.7）：你的逻辑是它画布上的数据
```

光谱每往右一格，框架替你多管一层、你也多交出一层控制权。**决策表的第一列
不是框架名，是光谱位**——§5 陷阱的主角：跨层直接比数字是选型评审最常见的翻车。

### 2.2 三维各是什么：能力、成本、锁定性

- **能力**（六格事实表）：HITL / 检查点 / 扇出 / 子代理 / 调试器 / eval——前四个是
  Unit 2 的 mini-agent 没有的执行能力，后两个是工程配套。只看能力会永远选平台
  （能力最全），所以——
- **成本**（全定量）：依赖数（uv.lock 计数）、装配 loc（把同题 demo 装进框架的行数）、
  自写节点/循环 loc（框架没替你付的部分）、模型轮数（每单的模型调用次数，token 成本
  的代理指标）。只看成本会永远选 mini-agent（最轻），所以——
- **锁定性**（定性 + 证据）：端点中立（你的会话数据默认发去哪、换端点要动什么）、
  私有格式依赖（状态/快照/DSL 的格式解释权在谁手里）、生态绑定（迁出时要重学什么）。
  锁定性是**三年后的成本**——demo 阶段看不见，平台迁移那天全部兑现。

三维合成一句话：**能力问「能不能」，成本问「现在付多少」，锁定性问「以后付多少」**。

### 2.3 为什么定量列必须可复现：宪法纪律的选型版

宪法先例：「292 行」因 BSD grep 不认 `\s` 而不可复现，四处复述全部返工为 249（ast 口径）。
选型评审比讲义更不能容忍口径漂移——数字会被抄进技术评审文档、被不同的人复述。
本课的落地：

- **依赖数**：tomllib 解析 uv.lock，数 `[[package]]` 条目（口径：含本项目自身与 dev 组）；
- **装配/节点 loc**：ast 定位目标函数行区间（`def` 行计入）→ 剔各级 docstring 行区间 →
  数非空非注释行——L3.4 `count_loc.py` 的先例口径，`tablegen.def_loc` 同款重实现；
- **讲义实测数字**（轮数、249）：作为静态数据写进生成器并注明出处课次——这些数字
  本来就是各课用 `ep.requests` / ast 实测过的，运行时抓不到「讲义」这种东西。

自证口径一致性：生成器实测复现了 L3.4 讲义已发布的 `build_graph` 10 loc 与
`build_agent` 6 loc——同一口径能重算已发布数字，口径才算可复现。

### 2.4 tomllib：标准库的 TOML 解析器（新知识点，首现）

Python 3.11 起标准库自带 TOML 读取器 `tomllib`（本教程 3.12 环境直接可用）：

```python
import tomllib

with lock_path.open("rb") as fh:      # 只收二进制模式 rb——文本模式直接 TypeError
    data = tomllib.load(fh)
packages = data["package"]            # [[package]] 是 TOML 的「表数组」→ list[dict]
```

对照 Java：没有等价的一等公民——POM 是 XML 要 DOM/ JAXB，TOML 在 Python 世界是
「配置即数据」（pyproject.toml / uv.lock 都是它），解析器进了电池。两个工程细节：
只进不出（写入要第三方 `tomli-w`——标准库刻意只管读）；`data["package"]` 的每个元素
是 `dict`，键就是锁文件里的字段（name/version/source…）。

### 2.5 functools.cache：函数级记忆化（新知识点，首现）

`tablegen.parse_module` 头上那行 `@cache` 是 `functools.cache`——把「参数 → 返回值」
记在函数对象上，同参数第二次调用直接回缓存。生成器数 L3.1 的三个装配函数都要
`ast.parse` 同一个 demo.py：不缓存就 parse 三遍（ast 解析不便宜）。对照 Java：
手写 `ConcurrentHashMap` + computeIfAbsent 的活儿，这里一个装饰器。纪律两条：
参数必须**可哈希**（所以签名收 `str` 不收 `Path`——`Path` 可哈希但两个等价路径
会击穿缓存，统一 `str(path)` 更稳）；只用于**纯函数**（`parse_module` 无副作用）。
L1.5 装饰器课讲过「装饰器是运行时替换行为」——`cache` 是「行为不变、加记忆」的最小样本。

## 3. 动手代码

先 `uv sync`（只有 dev 四件套，秒级）。本课全部动作围绕 `code/tablegen.py`（生成器）
与它的验收 `code/test_tablegen.py`（16 个测试，全部用合成夹具——不依赖兄弟课时存在）。

### Step 1：生成决策表数据页（15 分钟）

```bash
uv run python code/tablegen.py
```

```text
== L3.8 决策表数据页（code/tablegen.py 生成；重新运行本命令即可复现每一格） ==

| 行 | 依赖数 | 装配 loc（ast） | 自写节点/循环 loc | 模型轮数（讲义实测） |
|---|---|---|---|---|
| mini-agent（milestone） | 44 | — | 249* | 3 |
| openai-agents（L3.1） | 51 | 15 | 0 | 2 |
| langgraph 手装（L3.2） | 54 | 10 | 20 | 2 |
| langgraph prebuilt（L3.4） | 54 | 6 | 0 | 2 |
| deepagents（L3.5） | 70 | 8 | 0 | 5 |
| adk-python（L3.6） | 88 | 9 | 0 | 2 |

注：依赖数 = uv.lock 的 [[package]] 条目数（tomllib）；装配/自写节点 loc = ast 口径
（剔 docstring 的非空非注释行，L3.4 count_loc.py 同款）；「0」= 该层全部在框架内部；
「—」= 无装配函数（无框架可装配，成本全在自写列）；* 249 = 完成态核心五模块裸逻辑
（milestone README 的 ast 口径——发货态 run() 是 TODO 桩，生成器不数桩）；轮数为各课
讲义 ep.requests 实测静态数字，出处见生成器 COST_ROWS.turns_source。

### 能力表（事实，每格注出处课次）

[mini-agent]
  HITL : 无——进程退出状态即丢，messages 是局部变量（milestone 对照表）
  检查点 : 无——历史在调用栈里，跑完即忘（milestone 对照表）
  扇出 : 无——并行要自己写（milestone）
  子代理 : 无——转交要自己再造一个循环（milestone）
  调试器 : print_trace 手写轨迹打印（milestone main.py）
  eval : pytest 手搓契约十一路取证（milestone tests）
[openai-agents]
  HITL : RunState 快照审批：needs_approval→to_state（约 18KB JSON）→批准恢复（L3.1 Step5）
  检查点 : RunState 即快照——会话对账/schema 版本/并发守卫在 run_state.py（5271 行，wc -l 口径）（L3.1 §2.8）
  扇出 : 无并行原语——handoff 是串行换人接管（L3.1 Step3：ESCALATE 单 3 请求）
  子代理 : handoff-as-tool：专员包装成 transfer_to_* 工具，换 agent 不换对话（L3.1 Step3）
  调试器 : 无 GUI；trace span 树默认外发 OpenAI，第一件事 set_tracing_disabled(True)（L3.1 Step2）
  eval : 无 eval 工具链，pytest 自理（L3.1）
[langgraph]
  HITL : interrupt()+Command(resume)：暂停→杀进程→恢复，payload 落盘（L3.3 Step2）
  检查点 : checkpointer 每 superstep 落盘；get_state_history 可回放每一步（L3.3 Step4）
  扇出 : Send 动态扇出：4 分支墙钟 229.7ms vs 分支合计 912.2ms（L3.4 Step4）
  子代理 : subgraph 图即节点（L3.2 Step5）；Send worker 内跑完整 agent（L3.4 Step4）
  调试器 : astream 流式轨迹免费；LangSmith 默认零外发（L3.2 §2.5、Step3）
  eval : 无内建（LangSmith 在平台侧，本单元未展开——诚实边界）（L3.2 延伸）
[deepagents]
  HITL : interrupt_on / permissions 规则表挂点（L3.5 §5 修复纪律）
  检查点 : 复用 langgraph：files 也是 state channel，可 checkpoint（L3.5 Step2）
  扇出 : task 是串行派活收报告，非并行扇出（L3.5 Step3：子代理隔离对话）
  子代理 : 声明式 SubAgent spec→task 工具；一个不声明也自动塞 general-purpose（L3.5 §2.4）
  调试器 : 同 langgraph 谱系；虚拟文件系统可 ls/read_file 取证（L3.5 Step2）
  eval : 无内建（L3.5）
[adk]
  HITL : 无内建 interrupt——四类 callback 可自造短路（L3.6 §2.3、Step4）
  检查点 : Session+state 由 SessionService 持久化；InMemory 是「testing and development」默认件（L3.6 §2.2、§5）
  扇出 : 无一等扇出原语（本单元未展开——诚实边界）（L3.6）
  子代理 : 无声明式子代理——LlmAgent 组合 transfer（本单元未展开）（L3.6 §6）
  调试器 : adk web：本地服务+浏览器调试器，事件流/会话/state 可视化（L3.6 Step5）
  eval : AgentEvaluator+eval set+指标族；TrajectoryEvaluator 确定性轨迹比对（L3.6 Step5）
[dify（平台）]
  HITL : human-input 节点：表单+按钮即出边，平台生成 UI、自带超时（L3.7 §2.4）
  检查点 : 工作流状态挂起在平台运行时——静态可解析、动态 pytest 够不着（L3.7 §1、Step2）
  扇出 : iteration / loop 画布节点（DSL 节点类型表 19 种之一）（L3.7 §2.3）
  子代理 : 画布节点组合（agent-backend 是 v2 新组件，Pydantic AI 运行时）（L3.7 §2.2）
  调试器 : web 控制台：运行日志/标注/应用统计——运营视角（L3.7 Step4 能力清单）
  eval : 控制台标注，人工运营——对行为的断言进不了 CI（L3.7 Step4 能力清单）

### 锁定性表（定性 + 证据，每格注出处课次）

[mini-agent]
  端点中立 : 完全自控——client.py 自写直连任意 OpenAI 兼容端点（Unit 2 milestone）
  私有格式依赖 : 无——messages/tools 载荷就是公共 chat-completions 协议（milestone client/tools）
  生态绑定 : 无——httpx+pydantic+mcp 三件，44 个依赖全透明可数（milestone）
[openai-agents]
  端点中立 : 模型客户端可注入（OpenAIChatCompletionsModel 换端点）；但 trace 默认外发 api.openai.com，先关（L3.1 §2.7、Step2）
  私有格式依赖 : RunState 快照 JSON——schema 版本门禁与会话对账在框架内部（L3.1 §2.8）
  生态绑定 : openai 谱系轻绑定：span 协议、Responses API 默认路径（L3.1 §2.1）
[langgraph]
  端点中立 : 默认零外发——不设 LANGSMITH_* 即关（L3.2 §2.5）
  私有格式依赖 : Checkpoint=msgpack BLOB+serde 白名单——跨版本恢复要锁类型（L3.3 §2.4、Step4）
  生态绑定 : langchain 谱系（RunnableConfig/channels）；但它是 langgraph4j 同源上游——绑定即预习 Java 生产栈（L3.2 开场）
[deepagents]
  端点中立 : 同 langgraph：模型层任意 ChatModel 可换（L3.5 §2.3）
  私有格式依赖 : state['files'] channel——虚拟文件系统的存储形态绑图引擎（L3.5 Step2）
  生态绑定 : AgentMiddleware hook 族与中间件栈顺序是 deepagents 私有词汇（L3.5 §2.2）
[adk]
  端点中立 : litellm 中转：openai/ 前缀是路由记号出网前剥掉；api_base/api_key 是 litellm 参数名（L3.6 §2.4）
  私有格式依赖 : Session/Event/state 作用域前缀（app:/user:）是 adk 私有词汇（L3.6 §2.2）
  生态绑定 : Google 生态：adk deploy 的 Cloud Run 一等公民、VertexAi* 服务件（L3.6 §2.1、对照表）
[dify（平台）]
  端点中立 : 模型供应商体系是平台数据库里的配置不是代码——换平台要重配全部路由（L3.7 Step4 能力清单）
  私有格式依赖 : App DSL 的 version 管导入策略不管行为兼容——minor 落后照常导入仅警告（L3.7 §5）
  生态绑定 : 平台本体：插件市场/向量库/运行时——迁出=按 DSL 把画布重写成代码（L3.7 §2.1）

== 生成完毕：成本表 6 行 / 能力表 6 行 / 锁定性表 6 行；missing 格：无 ==
```

对着输出走三遍：成本表（每格现场计算）、能力表与锁定性表（静态事实、格格带出处）、
missing 行（兄弟课时缺失时优雅降级——你如果只 checkout 了本课时，重跑会看到
`missing` 格与点名，这正是降级路径）。讲义区验收：

```bash
uv run pytest code/
```

16 个测试全部用 **tmp_path 合成夹具**（tomllib 数合成 uv.lock、ast 数合成 demo.py、
缺失目录降级）——不真读兄弟课时，因此在任何 checkout 形态下都确定地绿。

### Step 2：逐列导读——每个数字回指它的证据（20 分钟）

成本表五个定量列，逐列把证据链接上：

- **依赖数 44/51/54/54/70/88**：六个课时各自 `uv.lock` 的 `[[package]]` 计数（tomllib，
  现场计算）。三个看点：44 里含 mini-agent 自己的 httpx/pydantic/mcp 及 dev 四件套
  （milestone）；51 是「最薄 SDK」的重量——薄不等于零，openai 谱系的客户端全在；
  70 与 88 是 harness 与全家桶的结构性重量——deepagents 拖着整个 langchain 谱系，
  adk 再加 litellm 多供应商层（L3.6 pyproject 特意没装 `google-adk[extensions]` 全家，
  88 已是按需直装后的数字）。
- **装配 loc 15/10/6/8/9**：各课 demo 的装配函数 ast 行数——L3.1 的 `_build_tools` +
  `_build_model` + `_build_agent`（2+5+8）、L3.2 的 `build_graph`（10）、L3.4 的
  `build_agent`（6）、L3.5 的 `build_agent`（8）、L3.6 的 `build_reviewer` +
  `build_runner`（7+2）。其中 10 与 6 和 L3.4 讲义发布的数字一字不差（口径自证）。
- **自写节点/循环 loc —/0/20/0/0/0**：L3.2 手装图的四个节点/路由函数
  （`make_reviewer` 5 + `tools_node` 10 + `route_after_reviewer` 2 + `finalize` 3 = 20）
  是「图引擎之外自己写的循环内脏」——ast 口径 20，与 L3.4 讲义发布的数字一字不差。
  mini-agent 的 249* 是完成态核心五模块（milestone README 口径；发货态 `run()`
  是 TODO 桩，生成器不数桩——静态列）。
- **模型轮数 3/2/2/2/5/2**：全部是各课 `ep.requests` 实测的静态数字。两个导读点：
  mini-agent 的 3 轮是「查单→预审→回答」的剧本编排；deepagents 的 5 轮**不是框架
  笨**——task 转交一轮、子代理独立对话两轮（L3.5 Step3 的隔离性证据）、写底稿一轮、
  Advice 收尾一轮（harness 把「交表」也做成了工具调用，L3.5 Step1）。轮数是
  「编排形态 × 框架默认行为」的乘积，读数时要拆开归因。
- **「—」与「0」**：mini-agent 无装配函数（没有框架可装配，成本全在自写列）；
  四个框架行的自写列是 0（循环与节点全部在框架内部——「0」就是「框架替你付掉了」
  的定量写法）。

### Step 3：五仓跳读指南——不设编程课的框架怎么快速读（40 分钟）

五个仓都克隆在 `~/develop/opensource/`（HEAD 锚点已核实，路径以锚点为准）。跳读的
通用方法：**先找核心抽象（1–3 个类）→ 再找入口方法（谁驱动循环）→ 最后扫 quickstart
样例**——带着本单元学过的概念去对照，每个仓 30 分钟足够定位。

**① crewAIInc/crewAI@894898f84 —— 角色化多代理编排**
定位：Crew/Agent/Task 三原语——「一组有人设的 agent 按流程干一组有交付物的任务」。
带着问题去读：Crew/Task 对照 openai-agents 的 Agent/handoff 是什么关系？
（Task 是有 `expected_output` 契约的作业单元，handoff 是对话接管——crewai 编排
**任务**，openai-agents 编排**对话**）；`kickoff` 是编排器入口不是循环本体，循环在哪一层？

- crewAIInc/crewAI@894898f84#lib/crewai/src/crewai/crew.py —— `Crew`（164 行起）与
  `kickoff`（995 行起）：编排入口，Sequential/Hierarchical 两种 Process 的分发处；
- crewAIInc/crewAI@894898f84#lib/crewai/src/crewai/task.py —— `Task`（120 行起）：
  `expected_output` 字段就是任务的交付物 schema（对照 L2.4 的结构化出口）；
- crewAIInc/crewAI@894898f84#lib/crewai/src/crewai/agent/core.py —— `Agent`
  （216 行起）：role/goal/backstory 人设三件——「角色扮演」流派的样本。

**② run-llama/llama_index@7169bcd0d —— 检索起家、workflow 为核**
定位：LlamaIndex 的 agent 层全部站在自家 Workflow 事件引擎上（不是 langgraph）。
带着问题去读：`AgentWorkflow` 的 agent 间转交（第 73 行的 `handoff` 工具 +
`can_handoff_to` 权限表）对照 L3.1 的 handoff-as-tool 与 L3.2 的条件边——
「转交」在第三家框架的第三种拼写；`take_step` 的「一步」对照 mini-agent 循环的一轮。

- run-llama/llama_index@7169bcd0d#llama-index-core/llama_index/core/agent/workflow/react_agent.py ——
  `ReActAgent`（38 行起，`take_step` 121 行起）；
- run-llama/llama_index@7169bcd0d#llama-index-core/llama_index/core/agent/workflow/multi_agent_workflow.py ——
  `AgentWorkflow`（99 行起）：多 agent 编排与 handoff 权限表；
- run-llama/llama_index@7169bcd0d#llama-index-core/llama_index/core/workflow/workflow.py ——
  一个只有一行的桥接文件（re-export）：Workflow 引擎已拆成独立包
  `llama-index-workflows`（core 的 pyproject 依赖 `>=2.14.0,<3`）——monorepo 把
  引擎拆成独立库的活样本（对照 langgraph 的 libs/ 布局）。

**③ agentscope-ai/agentscope@b82253ba1 —— 单 Agent 类 + 中间件钩子**
定位：阿里系的「一个大 Agent 类」路线——ReAct 不是独立类，是 Agent 的执行配置。
带着问题去读：`_reasoning`（选工具）与 `_acting`（执行回喂）两段正好对照
mini-agent 循环十行的一半一半；middleware hook 族对照 deepagents 的
`AgentMiddleware`（`before/after` 挂点的两种流派）。

- agentscope-ai/agentscope@b82253ba1#src/agentscope/agent/_agent.py —— `Agent`
  （117 行起）：`reply`（332）→ `_reasoning`（1634）→ `_acting`（2727）的执行链；
- agentscope-ai/agentscope@b82253ba1#src/agentscope/model/_base.py —— `ChatModelBase`
  （37 行起）：多供应商模型层的基座（端点中立的又一实现，对照 L3.6 litellm 路线）；
- agentscope-ai/agentscope@b82253ba1#src/agentscope/pipeline/_base.py ——
  `PipelineProtocol`：把「编排」做成可组合协议（对照 L3.2 的图：协议组合 vs 图拓扑）。

**④ langchain-ai/langchain@348c9dc57 —— Runnable 谱系总仓**
定位：L3.2–L3.4 的 langgraph 是它的近亲；本仓看点是 prebuilt 的官方继任。
带着问题去读：L3.4 读过的 `create_react_agent`（已挂弃用告警）官方迁名
`langchain.agents.create_agent`——骨架是否还是「模型节点+工具节点+条件边」？
middleware 族（含 `human_in_the_loop.py`）对照 adk 的四类 callback。

- langchain-ai/langchain@348c9dc57#libs/langchain_v1/langchain/agents/factory.py ——
  `create_agent`（818 行起）：prebuilt `create_react_agent` 的官方继任者；
- langchain-ai/langchain@348c9dc57#libs/langchain_v1/langchain/agents/middleware/ ——
  AgentMiddleware 族目录（human_in_the_loop / context_editing / file_search…）；
- langchain-ai/langchain@348c9dc57#libs/core/langchain_core/runnables/config.py ——
  `RunnableConfig` 与 `DEFAULT_RECURSION_LIMIT = 25`（L3.2/L3.4 已引用过的公共配置
  出处——全谱系的「预算」词汇都从这里长出来）。

**⑤ microsoft/agent-framework@3c6707077 —— AutoGen 的继任者，三层同仓**
定位：Agent（对话循环）/ Workflow（编排）/ harness（工作台）三层塞进同一个 core 包，
Python 与 .NET 双实现。带着问题去读：它的 `Workflow`（事件驱动）对照 langgraph 的
`StateGraph`（状态驱动）——「图引擎」的两种内芯；`_harness/`（todo/file memory/
background agents）对照 deepagents 三件套——两家 harness 长得像不是巧合（都在学
编码 agent 的工作台形态）。

- microsoft/agent-framework@3c6707077#python/packages/core/agent_framework/_agents.py ——
  `Agent`（1794 行起；`RawAgent` 727 行起是无中间件的裸循环）；
- microsoft/agent-framework@3c6707077#python/packages/core/agent_framework/_workflows/_workflow.py ——
  `Workflow`（228 行起）与同目录 `_checkpoint.py`（对照 L3.3 的检查点语义）；
- microsoft/agent-framework@3c6707077#python/samples/01-get-started/01_hello_agent.py ——
  quickstart：仓里自带的「入门最短路径」（01–07 七个样例就是一条官方跳读路线）。

### Step 4：决策表定稿——何时选谁（15 分钟）

数据页 + 逐列导读合成定性结论。抄进技术评审的版本：

| 场景特征 | 选 | 一句话依据（出处） |
|---|---|---|
| 要断电恢复 / 审批外化 / 状态自持 | **langgraph** | interrupt+checkpoint 落盘、thread_id 隔离（L3.3）；显式图可审计（L3.2）；Java 生产栈同源（L3.2 开场） |
| 一次性 POC / 即弃 / 要深度定制循环内脏 | **mini-agent 自研** | 249 行零锁定、messages 即公共协议（milestone）；「—」格的含义就是「不交税」 |
| 工作台型长任务（子代理+文件+记忆） | **deepagents** | harness 三件套默认全给（L3.5）——代价：收窄默认件、覆盖 9999 预算 |
| 已在 Google 栈 / 要调试器与 eval 工具链 | **adk** | adk web + AgentEvaluator 四框架独一份（L3.6 Step5）——代价：litellm 中转与生态绑定 |
| 业务同学维护流程 / 表单式 HITL | **dify（平台）** | 画布+human-input 表单（L3.7）——代价：不可 git diff、不可单测、迁出重写 |
| 薄原语 / 双 agent 转交快速起步 | **openai-agents** | 离 mini-agent 最近的框架层（L3.1）——第一件事关 trace 外发 |
| 毕业设计（L5） | **langgraph** | 本表正式落锤：可测试（pytest 够得着）、可 git（diff 可审）、可迁移（langgraph4j 对照）——L3.7 已预演三个判据 |

两个定稿纪律：①「选 mini-agent 级自研」不是反面答案——决策表的左列和右列都是合法
选项，区别只在你愿意为什么付钱；②任何一行都可以被新证据推翻——生成器重跑一遍，
数字变了就回来改结论（决策表是**活文档**，这就是它可复现的全部意义）。

## 4. 练习（本课过关点）

三题都是「决策表工程」的延续。规则：**单变量编辑约束**——只改 TODO 标注区与所需的
顶部 import（骨架只预置了 given 部分用到的）。卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_contract_column.py` | tablegen 扩展：加「契约测试是否在位」列——五课 test_contract.py 字节一致的校验；验收：四个合成夹具测试（全对版 in-place / 漂移点名 drift / 缺文件 missing / 指纹并列时基准确定） |
| ex2 | `exercises/ex2_scenario_map.py` | 六个选型场景 → 框架映射 + 理由；验收：映射与期望表逐格一致、理由非空够长带课次证据 |
| ex3 | `exercises/ex3_selfcheck.py` | 结业自查表数据补全（覆盖型 + meta-test）；验收：四个 meta 断言（12 行无空、框架判据在表、六个框架名齐、维度白名单） |

验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 直觉陷阱：比较基准（跨层直比数字）

这是本课的命名化失败模式——选型评审上最容易发生、也最像「有数据支撑」的错误。

- **现象**：评审会上有人指着数据页说「deepagents 70 个依赖比 openai-agents 的 51 个
  多了近四成，太重了，排除」；或者反过来「langgraph 手装要 10 行、openai-agents 要
  15 行，图引擎反而更省事？这数据不对吧」。两句话都引用了真实数字，结论都不成立。
- **最小复现**（本课数据页就是证据）：依赖数 51（SDK 层）→ 54（图引擎层）→ 70
  （harness 层，内含 langchain 全谱系）→ 88（全家桶层，再加 litellm 多供应商）——
  数字随**光谱位**单调上升，这是结构性事实（上层复用下层），不是同层竞品的质量差。
  真正的同层比较只有一组：L3.2 手装 10 loc vs L3.4 prebuilt 6 loc（同框架、同题、
  同口径）——这一组才能回答「谁好」。
- **Java 直觉为何失效**：Java 人其实早就会这条纪律——没人拿 Netty 的 jar 数去说
  Spring Boot 不好，因为「HTTP 框架」和「应用框架」显然不在一层。但 agent 框架的
  名字全带「agent/框架」，层次感被名字抹平了：openai-agents 与 deepagents 都叫
  框架、都能三行跑起一个 agent，光谱位却差了两格。依赖数的因果方向是
  **光谱位 → 依赖数**，不是「依赖数多 = 设计差」。
- **修复与纪律**：① 比较前先钉住比较层——同一光谱位、同一解决的问题，才进入数字
  比较；② 跨层数字只回答「我要站在哪一层」（用 70 vs 51 评估「上 harness 值不值」
  是合法用法，用它评「deepagents 好不好」是非法用法）；③ 决策表把光谱位写进第一列
  （§2.1），生成器把口径写进每个格子——让下一个引用数字的人看得见层的存在。

## 6. 延伸

官方文档（跳读入口，版本以源码锚点为准）：

- crewAI：https://docs.crewai.com/quickstart （Quickstart 与 Crews/Flows 概念页）；
- LlamaIndex：https://docs.llamaindex.ai/ （Agent Workflows 与 Workflows 概念页）；
- AgentScope：https://doc.agentscope.io/ （Quickstart 的 Agent/Toolkit 最小样例）；
- langchain：https://docs.langchain.com/oss/python/langchain/agents （v1 的 create_agent）；
- agent-framework：https://microsoft.github.io/agent-framework/ （get-started 与
  core concepts；仓内 `python/samples/01-get-started/` 就是官方跳读路线）。

源码路标（本课 §3 Step3 的完整版，HEAD 均已核实；五仓克隆在 `~/develop/opensource/`）：

- crewAIInc/crewAI@894898f84#lib/crewai/src/crewai/crew.py —— `Crew` 与 `kickoff`；
- crewAIInc/crewAI@894898f84#lib/crewai/src/crewai/task.py —— `Task.expected_output`；
- run-llama/llama_index@7169bcd0d#llama-index-core/llama_index/core/agent/workflow/multi_agent_workflow.py ——
  `AgentWorkflow` 与 `handoff` 工具（73 行起）+ `can_handoff_to` 权限表；
- run-llama/llama_index@7169bcd0d#llama-index-core/llama_index/core/workflow/workflow.py ——
  引擎拆包的一行桥接（依赖 `llama-index-workflows>=2.14.0,<3`）；
- agentscope-ai/agentscope@b82253ba1#src/agentscope/agent/_agent.py —— `Agent` 的
  `reply/_reasoning/_acting` 执行链（117/332/1634/2727 行起）；
- microsoft/agent-framework@3c6707077#python/packages/core/agent_framework/_workflows/_workflow.py ——
  事件驱动的 `Workflow`（228 行起），对照 langgraph 状态驱动；
- microsoft/agent-framework@3c6707077#python/packages/core/agent_framework/_agents.py ——
  `Agent`（1794 行起）与裸循环 `RawAgent`（727 行起）；
- （本单元已锚定的五框架主路标见各课 §6：openai-agents@fbd2dbca、langgraph@e539ac122、
  deepagents@9e7d62ff6、adk-python@7b246e01、dify@79effdd498。）

下一学段预告（Unit 4 产品实战）：决策表不是终点——L4.1–L4.3 把框架放回真实产品仓
（ai-hedge-fund 的缓存即审计、TradingAgents 的辩论循环、Vibe-Trading 的 fail-closed
门），从「读过架构」到「跑过、改过」。你今晚的决策表会在每一站被真实约束重新检验。

### 结业自查表

Unit 3 结业判据（对齐 CURRICULUM §7「框架」一行：**决策表能自己重新推导**）。
逐条勾选；哪条勾不动，回对应课次补——练习 ex3 会把这张表变成可验收的数据。

- [ ] **框架判据**：盖住讲义，能自己重新推导成本表六行的四个定量列——依赖数（tomllib
      数 uv.lock）、装配 loc（ast 剔 docstring）、自写节点 loc（L3.2 的 20）、轮数
      （各课 ep.requests 实测），并说出口径（CURRICULUM §7）
- [ ] **成本**：能背出依赖数光谱 44→51→54→70→88 的顺序与两端（mini-agent 最轻、
      adk 最重），并说出 dify 为何不在这一列（平台不进依赖清单，L3.7 题眼）
- [ ] **能力**：HITL 三种形态各给一个机制证据——RunState 快照（openai-agents，L3.1）、
      interrupt+checkpoint（langgraph，L3.3）、human-input 表单（dify，L3.7）
- [ ] **能力**：能解释 deepagents 同题 demo 为什么 5 轮而其他框架 2 轮（L3.5 Step1）
- [ ] **能力**：能讲清 Send 扇出「执行并发、归并确定」与线程池 submit 的本质差异（L3.4）
- [ ] **能力**：能指出 adk 独有的两件——adk web 调试器与 AgentEvaluator（L3.6 Step5）
- [ ] **成本**：能现场重数装配 loc：口径是 def 行计入、docstring 剔除（L3.4 count_loc /
      本课 tablegen 同款）
- [ ] **锁定性**：能对「trace 默认外发」与「litellm 中转」各给一句源码级证据（L3.1
      Step2 / L3.6 §2.4）
- [ ] **锁定性**：能说出 Checkpoint 私有格式的风险与对策（msgpack BLOB + serde 白名单，
      L3.3 Step4）
- [ ] **锁定性**：能说出「绑定即预习」为什么是 langgraph 独有的正面锁定（langgraph4j
      同源上游，L3.2 开场）
- [ ] **跳读**：五仓路线各能说出一个核心抽象入口（crewai 的 Crew/Task、llama_index 的
      AgentWorkflow、agentscope 的 Agent.reply、langchain 的 create_agent、
      agent-framework 的 Workflow）
- [ ] **框架判据**：能说出「何时选 mini-agent 级自研」（一次性 POC / 零锁定 / 深度
      定制循环——决策表「—」格的含义），以及毕设为什么落锤 langgraph（可测试 /
      可 git / 可迁移）

## 离毕业又近的一块

决策表今晚完工——它就是毕业设计技术评审（L5.0）的选型依据：评审文档里「为什么用
langgraph」不再是「听说成熟」，而是三行证据（checkpoint 落盘可审计 / pytest 够得着
每条链路 / langgraph4j 同源可翻译回 Java）。下一学段进真实产品仓（Unit 4）：跑通、
改过、读穿三个金融产品——「框架」从选型对象变成你的工具。距离毕设动手，只剩一个
学段的距离。
