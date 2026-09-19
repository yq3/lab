# py-night-school（Python 夜校）课程大纲

> 本文是教程的骨架：设计原则 → 课时模板 → 练习机制 → 30 课时明细 → 节奏建议。
> 设计前的竞品调研见 [research/agent-tutorials/](../research/agent-tutorials/)：市场扫描（landscape.md）+ 课时内容级解剖综合（report.md）+ 逐仓档案（profiles/ ×8）。
> 夜校话术对照：单元 = 学段，课时 = 晚课讲次，Unit 5 = 结业考；结构性术语保持工程清晰，不硬套主题。

## 1. 设计原则（承袭个人学习计划，经用户确认）

原计划（个人 16 周学习路线）的四条定位原样继承为课程原则：

1. **按 agent 框架的真实用法学语言**，不按通用教程全量学：装饰器、asyncio、Pydantic、生成器是框架源码四大件，优先练熟；GUI、科学计算、Web 前端不碰。
2. **每课必须有可运行产出**，练习以 pytest 验收。
3. **框架学习顺序遵循抽象光谱**：拒抽象的 SDK → 图引擎 → harness → 全家桶；优先 langgraph 谱系（它是 Java 生产栈 langgraph4j / spring-ai-alibaba graph 的同源上游）。
4. **双目的**：学习者既获得 Python 工程能力，也获得把模式带回 Java 栈的迁移地图（毕业设计产出 JAVA-MAPPING.md）。

教程化新增两条：

5. **Java 心智桥贯穿**：每课的概念讲解必须包含 Java↔Python 对照表；每课设「Java 直觉陷阱」小节。
6. **对照组教学法**：Unit 2 的 mini-agent 是全程对照组，Unit 3 每框架课固定收尾「与 mini-agent 对照」。

## 2. 课时模板（六段式，每课 README.md 的固定结构）

```markdown
# L<单元>.<序号> 课程名

> 承接段（2–3 句，blockquote）：昨晚产出了什么（点名具体产出物）→ 今晚解决什么新问题 →
> 为何排在今晚 / 与后续哪课相接。每单元首课回收上一学段；L0.1 写入学引导。

## 1. 本课目标          —— 完成后你能做什么（一句话，可验证）
## 2. 概念讲解          —— 开头先给全课 Java↔Python 对照表，再逐小节展开；含各小节局部表
## 3. 动手代码          —— step-by-step 可运行（本课 code/ 目录）；小节统一命名「Step N」，可选项标「（可选）」
## 4. 练习              —— exercises/ 填空（单变量编辑约束）+ hints 渐进披露 + pytest 验收；表头统一「| 题 | 文件 | 考察 |」
## 5. Java 直觉陷阱     —— 命名化失败模式：现象 / 最小复现 / Java 直觉为何失效 / 修复
## 6. 延伸              —— 官方文档 + 源码路标（仓库@commit#路径）；「与 mini-agent 对照」
                          （若本单元有）排在 §6 开头、源码清单之前
+ 结尾固定段「离毕业又近的一块」—— 暗线进度（散文体，下集预告写在这里；不计入六段编号，拼写以此为准）
```

写作契约（机器校验对象，check_lesson.py 落实）：

- **三命令块全课只贴一次**（§1 末的完成判据）；§4 验收处以一句话引用（「验收命令同 §1」），不复贴整块。
- **完成判据口径统一**为「三命令全绿」，可附一句复述自查；不再用「pytest 全绿 + 能复述 X」的缩水版。
- **术语首现即定义**：本课首次用到的术语，要么一句话定义，要么显式标注「先混个眼熟，Lx.y 主讲」——禁止先用后定义；知识点的主讲课归属见 §2.1 登记表。

### §2.1 知识点登记表（唯一主讲课；改归属须同步两侧互指）

| 知识点 | 主讲课 | 复现课（指路不重讲） |
|---|---|---|
| f-string / print sep·end / 切片解包 | L1.1 §2.7（速览） | L1.2 起日常用 |
| 类型标注 / `str \| None` / 泛型 | L1.2 | 全程 |
| typing.Protocol（结构化类型） | L1.2 §2.5 | L2.3 ModelClient、L2.5 |
| 类语法 / dunder | L1.3 | 全程 |
| dataclass / Pydantic | L1.3 | L2.2 起 agent 建模主力 |
| 闭包 / nonlocal / `*args/**kwargs` | L1.4 | L1.5 地基 |
| 推导式（正式主讲） | L1.4 §2.6 | L1.1 §2.7 已速览 |
| 装饰器（含 @retry 带参形态） | L1.5 | Unit 1 里程碑、L2.2 @tool |
| 迭代器协议 / 生成器 / yield | L1.6 | L1.7 @contextmanager、L1.9 |
| 异常树 / 异常链 / EAFP | L1.7 | L1.9 CancelledError |
| with 协议 / @contextmanager | L1.7 | L2.1 `async with` |
| 事件循环 / 协程 / await | L1.8 | L1.9、L2.1 起 |
| gather / wait_for / Semaphore / async 生成器 | L1.9 | Unit 1 里程碑、L2.1 |
| naive vs aware datetime | L4.3 §2.7 | L5.4 §2.6（结课深化） |
| superstep / BSP 执行模型 | L3.4 §2（深讲）；L3.2 首现带一句定义 | L3.3 pregel |
| checkpoint / interrupt | L3.3 | L5.2 |
| Annotated reducer | L3.2 | L3.4、L5.1 |
| fail-closed / 四态 Literal | L2.4 | L4.3、L5.4 |
| MCP（server/client/桥接） | L2.5 | L5.x 工具层 |

新增知识点入课时在此登记一行；同一知识点两课都宣称「主讲」视为违规（先例：推导式曾 L1.1/L1.4 双主讲，2026-09-18 修为「速览 + 主讲」互指）。

- 六段式借鉴 microsoft/ai-agents-for-beginners 的「文 + 码 + 延伸链接」三件套，在其上增加 Java 对照与陷阱两段（我们的差异化所在）。
- 源码路标统一指向 GitHub 真实路径并**锚定 commit**（如 `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/graph/state.py`），不粘贴大段源码。
- 陷阱的「命名化失败模式」结构与「单变量编辑约束 / hints 渐进披露」依据 [调研报告](../research/agent-tutorials/report.md) §3.1/§3.4（八仓解剖结论）。

## 3. 练习机制（rustlings 模式）

- 每课 `exercises/` 下 2–5 个练习文件，关键实现留 `# TODO`，附测试；练习文件首行注释声明**单变量编辑约束**（只改这个文件/只改标注区）。
- `uv run pytest` 全绿 = 本课通过（`testpaths` 已限定收集 code/ 与 exercises/）；练习文件头部注释写明考察点。
- **答案分离**：`solution/` 不进学员主线视野；每题配 `hints.py` 渐进披露（需显式 `from hints import ...` 才可见，借鉴 anthropics-courses 档案 §4.1）。
- **三方对齐**：题目注释、hints、pytest 断言同一验收口径（借鉴其「判分标准在 hints 第一句复述」）。
- **覆盖型练习配 meta-test**：当题目要求是对用例表的覆盖（先例：L0.1 ex2），验收测试直接检查用例表本身——结果种类、边界、数量，防止「全 PASS 用例」偷懒过关。
- 开放设计题不硬造判分，给行尾 golden answer 诚实降级（借鉴 anthropics 对 6/20 道题的处理）。
- 形态分工：讲义用 md、动手 code/（.py 为主）、**验收只测 .py**；Jupyter 仅语言实验课使用（依据调研报告 §3.6）。
- 每单元结束有一个里程碑小项目（见各单元「里程碑」）。
- 框架课（Unit 3/4）练习改为「改造题」：在能运行的 demo 上完成指定修改并跑通验收脚本；Unit 3 四框架同题 demo **共用一份验收脚本**（借鉴 GenAI_Agents 同模式双框架同验收，调研报告 §3.2）。

## 4. 课程总览（6 单元 / 30 课时）

| 单元 | 课时数 | 标准节奏 | 里程碑 |
|---|---|---|---|
| 0 起步 | 1 | W1 | 工具链模板 |
| 1 语言核心 | 9 | W2–4 | 练习集 + 并发 fetcher |
| 2 无框架手写 | 5 | W5–6 | mini-agent ~250 行 |
| 3 框架四重奏 | 8 | W7–10 | 4 框架 demo + 决策表 |
| 4 产品实战 | 3 | W11–13 | 3 产品改造 |
| 5 毕业设计 | 4 | W14–16 | 财务 agent PoC + 映射表 |

**双贯穿线**（依据调研报告 §3.3，竞品高质量课程的共同骨架）：明线「报销单审查」从 L0.1 就种下（第一课即配好 mock 数据与 `.env` 三变量 `OPENAI_BASE_URL` / `OPENAI_API_KEY` / `MODEL_NAME`），Unit 3 换框架重做；暗线「毕业设计」每课结尾一行进度提示——本课能力对应毕业设计的哪个模块，让 PoC「每课长一块」而非最后才出现。

---

## Unit 0 起步：工具链一次到位（1 课）

**L0.1 环境与工具链（uv / pytest / ruff / pyright / IDE / Jupyter）**
- Maven→uv、JDK 管理→uv python、Checkstyle→ruff、javac→pyright、JUnit→pytest 全对照表；
- 动手：`uv init` 项目、加依赖、配国内 PyPI 镜像（bash / PowerShell 双版本）、三件套全绿、虚拟环境 101（`.venv` / activate / `uv run` 机制 / pip↔uv 关系）、断点调试与 IDE 接入（VS Code+Pylance 或 PyCharm 双 checklist + 终端↔IDE 全量对照表）、Jupyter 起一次；
- 产出：`units/unit0/` 项目模板，后续每课复制起步。
- 里程碑：模板仓库三件套全绿。

## Unit 1 Python 语言核心·Java 对照（9 课）

第一梯队「框架血管」（L1.1–L1.3）→ 第二梯队「行为与错误处理」（L1.4–L1.7）→ 第三梯队「重中之重」（L1.8–L1.9）。

| 课 | 主题 | Java 对照要点 |
|---|---|---|
| L1.1 | 运行模型与模块系统 | 解释执行/`__init__.py`/导入 vs JVM/classpath/Maven 坐标 |
| L1.2 | 类型系统与 Protocol | 渐进类型/泛型/Optional vs Java 静态类型；Protocol（结构化）vs interface（名义） |
| L1.3 | 数据建模：dataclass 与 Pydantic v2 | dataclass vs record；Pydantic = bean+validation+序列化三合一；框架源码里的消息/工具 schema 全是它 |
| L1.4 | 函数是一等公民 | 闭包/`*args/**kwargs`/lambda 差异/函数作参数 |
| L1.5 | 装饰器 vs 注解 | 运行时高阶函数可直接替换行为；functools.wraps；框架里的 `@tool`/`@step`/`@mcp.tool()` |
| L1.6 | 迭代器与生成器 | `yield` 惰性管线；异步生成器是流式输出底座 |
| L1.7 | 上下文管理器与异常处理 | `with` vs try-with-resources、`@contextmanager`；异常体系（**无 checked exception**）、EAFP vs LBYL、`except Exception` 陷阱与清理顺序——L2.4「校验错误回喂重试」的直接前置 |
| L1.8 | asyncio ① | 事件循环/协程/`await`；vs CompletableFuture/虚拟线程；「一个 await 不让出就阻塞全场」事故剖析 |
| L1.9 | asyncio ② | task/gather/超时取消/异步生成器；综合练习 |

- 每课概念讲解后到真实仓库找用例印证（源码路标：crewai `@agent/@task`、langchain `Runnable`、langgraph `astream_events` 等）；
- 教材：官方语言教程 + 《Fluent Python》2e 挑读（数据模型/数据类/一等函数/类型/装饰器/Protocol/迭代器生成器/上下文/并发与 asyncio）。
- 里程碑：不查资料手写「async 并发 fetch 10 URL + 超时重试装饰器 + pytest 覆盖」。

## Unit 2 无框架手写 mini-agent（5 课）

> 设计依据：理解抽象的最好方式是先拥有被抽象的东西。先例：DeepLearning.AI《AI Agents in LangGraph》先手写再上框架；hello-agents 第四章手写经典范式。我们把它从「一节课」升级为「一个单元 + 全程对照组」。

| 课 | 主题 | 要点 |
|---|---|---|
| L2.1 | 裸调 LLM API | messages 协议、function calling 协议、**手撕 SSE 流式解析**（理解 token 怎么一个个吐出来） |
| L2.2 | 工具协议 | Pydantic 模型 → JSON Schema → 工具注册表 |
| L2.3 | ReAct 循环 | 注册/模型选工具/执行/回喂/终止条件/轮数预算（~100 行） |
| L2.4 | 结构化输出 | schema 约束、解析失败、校验错误回喂重试 |
| L2.5 | MCP | 官方 `mcp` SDK 写 server（财务 mock 工具×3）+ client 消费 |

- 朴素上下文管理（token 计数 + 裁剪）作为 L2.3 的加餐；
- 里程碑：**mini-agent ~250 行**（多工具 + 流式 + 结构化输出 + MCP server）——Unit 3 的全程对照组。

## Unit 3 框架四重奏（8 课）

统一 demo 题目：**报销单审查 agent**（工具：查预算余额 mock、发票校验 mock；输出：结构化建议单）。同题换框架，差异体感最大化。

| 课 | 框架 | 学什么 | 固定收尾 |
|---|---|---|---|
| L3.1 | openai-agents-python | 极简原语：Agent/handoff-as-tool/guardrail；RunState 的 HITL；**先关 trace 外发** | 与 mini-agent 对照 |
| L3.2 | langgraph ① | StateGraph/状态 schema/条件边/subgraph | 同上 |
| L3.3 | langgraph ② | **checkpoint/interrupt 实验：暂停→杀进程→恢复**（HITL 机制底层） | 同上 |
| L3.4 | langgraph ③ | `Send` 动态扇出；`prebuilt.create_react_agent` 源码导读（很短，对照 mini-agent） | 同上 |
| L3.5 | deepagents | harness 形态：虚拟文件系统/子代理/MemoryMiddleware | 同上 |
| L3.6 | adk-python | 全家桶：`adk web` 调试器/eval 工具链 | 同上 |
| L3.7 | dify 半日游 | 本地 compose 跑平台形态（画布/HITL 表单/知识库），体感「平台 vs 库」分界 | 平台能力清单 |
| L3.8 | 对照总结课 | mini-agent vs 四框架：能力-成本-锁定性决策表；crewai/llama_index/agentscope 跳读指南 | 结业自查表 |

- langgraph 占 3 课（本教程主干）：它是 Java 生产栈（langgraph4j / spring-ai-alibaba graph）同源上游，学它等于预习生产栈语义；
- crewai / llama_index / agentscope / langchain / MS agent-framework 不设编程课，L3.8 给「已了解架构后如何快速跳读」路线。
- 里程碑：4 框架同题 demo + 每框架一页对照笔记 + 决策表。

## Unit 4 开源产品实战（3 课）

> 从「读过架构」到「跑过、改过」。三个产品同一条递进线：无框架纯 Python → LangGraph 实战 → 治理合规架构，全部金融/财务域。

| 课 | 产品 | 动作 |
|---|---|---|
| L4.1 | ai-hedge-fund | 跑通回测 → 改某 agent 的 prompt/投票权重观察变化 → 精读 `llm/cache.py`（缓存即审计） |
| L4.2 | TradingAgents | 跑通辩论流程 → 对照源码读条件边循环 → 改造：辩论轮次参数化 + 预算封顶 |
| L4.3 | Vibe-Trading | 以读为主：`live/enforcement.py`（fail-closed 八查）/`governance/ledger.py`（哈希链）/`live/pending_action.py`（对账不重发）→ 改造：mock 券商连接器，把 mandate 检查链抽出写 pytest 单测 |

- 明确不选 OpenHands（HEAD 已清仓迁移 TS，Python 学习价值打折，详见 landscape）；
- 每课两层（L3.7 先例的推广）：**主线**是把产品核心机制抽取成对版机制件（锚定 commit、报销域、零 key 三态可验收），真跑产品与本地分支改造是**可选加餐**；
- 每课改造在本地分支完成，产出「改造说明 + 截图/日志」。
- 里程碑：3 个产品各 1–2 个可复现改造。

## Unit 5 毕业设计：财务 agent（4 课）

> 把研究报告的推荐架构做成 Python PoC——用最低成本验证模式，再翻译回 Java。技术栈：langgraph + FastAPI + SQLite + 任一 OpenAI 兼容模型。

| 课 | 主题 | 交付 |
|---|---|---|
| L5.1 | 静态图 + 计划驱动路由 | 固定拓扑「取数→分析→生成建议单→送审」；Plan JSON（Pydantic 强约束 + 工具白名单）驱动确定性执行 |
| L5.2 | 审批外化 API 组 | REST 建单 + SSE 推送 + once/always/reject 三元回复；asyncio 挂起；断线重放不丢单 |
| L5.3 | 事件溯源与审计 | append-only 事件表（会话/消息/审批/成本一等事件）；缓存即审计；图版本绑定 |
| L5.4 | fail-closed 执行门 + 结业 | 纯函数检查链（限额 clamp/黑名单/频次），不可解析即 DENY；**JAVA-MAPPING.md**（每个模式在 saa/langgraph4j 的对应物与翻译坑） |

- 里程碑：可运行 PoC + 三条主链路（审批暂停/恢复/拒绝回环）pytest 集成测试全绿 + JAVA-MAPPING.md。

## 5. 节奏与调节旋钮

- **标准节奏**：每周 6–8 小时，16 周完成；**紧凑节奏**：每周 12 小时+，8–10 周。
- **只有 4 周**：Unit 0/1 压缩到 10 天（只学 L1.1–L1.3 + L1.8/L1.9）+ Unit 2 全做 + Unit 3 只学 L3.2–L3.4（langgraph 三连）。
- **想尽快到毕业设计**：Unit 4 只做 L4.1。
- **框架学不动时**：L3.1/L3.5/L3.6 均为可弃子，langgraph 三连不可省。

## 6. 仓库布局与工程纪律

```
py-night-school/
├── README.md            # 入口：定位/受众/使用方式
├── CURRICULUM.md        # 本文件（调研依据见 ../research/agent-tutorials/）
├── data/                # 共享 mock 素材（报销/预算/发票），金融素材复用 openai-cookbook examples/data/（NotRealCorp 虚构财报等）
├── scripts/
│   ├── check_lesson.py  # 课时模板机器校验（章节齐全/练习有 TODO/pytest 存在/源码路标带 commit）
│   └── three_state_check.py  # 三态验证自动化（发货态精确红/毕业态全绿/结构校验，一条命令）
└── units/
    └── unit<N>-<slug>/
        ├── README.md            # 单元导学
        ├── L<N>.<m>-<slug>/     # 每课时一目录（本身即独立 uv 项目）
        │   ├── README.md        # 六段式讲义
        │   ├── pyproject.toml   # 依赖与工具配置（uv.lock 同目录提交）
        │   ├── .env.example     # 模型端点三变量约定
        │   ├── code/            # 讲义动手模块 + 示例测试
        │   ├── exercises/       # TODO 挖空 + test_*.py 验收 + hints.py
        │   └── solution/        # 参考答案（不在学员主线视野）
        └── milestone/           # 单元里程碑项目
```

工程纪律（依据 [调研报告](../research/agent-tutorials/report.md) §3.5/§3.6，全部是竞品的系统性短板，做对了就是卖点）：

- 每课是独立 uv 项目并提交 `uv.lock`——竞品反例：MS 钉版与 `%pip install -U` 自相矛盾、GenAI_Agents 依赖 pin 分裂、Anthropic 同课三份手工拷贝漂移。
- 讲义图片本地化存储，不外链 CDN（langchain-academy 反例）；仓库克隆即完整可学，教学主体不外置（HF 全外置 Colab 反例）。
- 所有外链延伸材料锚定 commit；源码路标格式 `仓库@commit#路径`。
- **平台中立**：学员命令一律 `uv run ...`（macOS / Windows / Linux 一致），多步命令分行走（**不用 `&&` 串联**——Windows PowerShell 5.1 默认不支持）；平台差异（安装脚本、环境变量语法、cp/copy）在课时内以对照块标注，不默认 macOS。约定：学员命令统一放 bash 代码块——`check_lesson.py` 只检查 bash 块内的 `&&`，Java 对照示例（`a && b`）不受影响。**IDE 侧栏**（PyCharm / VS Code 的图形化等价操作提示）以 blockquote 定式（`> **IDE 侧…**`）存在：不入 bash 块、不作验收判据，L0.1 Step 7 的终端↔IDE 对照表是全书锚点、各课侧栏只做回收指路。另两条同源纪律：仓库根脚本进入学员路径时同样 `uv run python` 化（先例：unit5 里程碑重验五连的 `python3`）；`~` 家目录参数须双端交代（Windows PowerShell 不为命令参数展开 `~`，源码克隆约定见 unit3 README，课程自有工具用 `expanduser()` 兜底）。

## 7. 验收标准（结业自查）

- [ ] 语言：手写 async 并发 fetcher + retry 装饰器，不查资料；
- [ ] 地基：能向别人讲清「一个 agent 循环的一轮发生了什么」（从 API 消息到工具回喂）；
- [ ] 框架：mini-agent vs 四框架决策表能自己重新推导；
- [ ] 产品：完成 3 个产品的指定改造并复现；
- [ ] 毕业：PoC 三条主链路测试全绿，JAVA-MAPPING.md 可作为 Java 侧开发任务拆解输入。
