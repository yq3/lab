# langchain-academy 教程解剖档案

> 对象：langchain-ai/langchain-academy（本地 ~/develop/opensource/langchain-academy，HEAD fa15bec，2026-06-15；全量克隆）
> 视角：为 py-night-school（Java 工程师 × Python Agent 夜校）提炼课程设计与教学方式启发
> 证据纪律：结论可溯源到本地路径；区分【核心】（实际文件所见）与【推断】（分析判断）；查不到的标 ⚠️ 不臆测

## 1. 定位与形态

【核心】LangGraph 官方免费课程 **"Introduction to LangGraph"**（academy.langchain.com）的配套 notebook 仓库：30 本 notebook 分 7 个模块（module-0 ~ module-6），讲义/视频/测验在课程网站，仓库只承载"动手跟打素材"。

【核心】根 README 明确分工："In each module folder, you'll see a set of notebooks. **A link to the LangChain Academy lesson is at the top of each notebook** to guide you through the topic. Each module also has a `studio` subdirectory, with a set of relevant graphs that we will explore using the LangGraph API and Studio."

【核心】配套组件三件：根 `requirements.txt`（全仓单一环境）、`.devcontainer/devcontainer.json`（Codespaces 一键起 Python 3.11 + jupyterlab + 依赖）、每模块 `studio/`（langgraph.json + .py 版 graph + .env.example，跑 `langgraph dev` 进浏览器 Studio 可视化）。

【推断】这是"课程网站为主、GitHub 仓库为辅"的双轨形态——仓库离线可用但失去讲解与顺序信息，网站是教学主体。

## 2. 结构总览（关键目录树 + 组织逻辑）

```
langchain-academy/
├── README.md            # 106 行：无课程大纲！只有简介 + Python 版本/venv/API key/Studio 的 setup
├── requirements.txt     # 全仓单环境，宽松 pin（langgraph 无版本号，langchain-core>=1.2.28）
├── .devcontainer/       # GitHub Codespaces 一键开发环境
├── module-0/            # 1 本：basics.ipynb（课程结构介绍 + chat model/tool 初体验）
├── module-1/            # 6 本：simple-graph / chain / router / agent / agent-memory / deployment
│   └── studio/          # simple.py / router.py / agent.py + langgraph.json + .env.example
├── module-2/            # 6 本：state-schema / state-reducers / multiple-schemas / trim-filter-messages
│   │                    #      / chatbot-external-memory / chatbot-summarization（状态与记忆管理主题）
│   ├── state_db/example.db   # 共享 sqlite 检查点库
│   └── studio/chatbot.py
├── module-3/            # 5 本：breakpoints / dynamic-breakpoints / edit-state-human-feedback
│   └── studio/          #      / streaming-interruption / time-travel（调试与 human-in-the-loop）
├── module-4/            # 4 本：parallelization / map-reduce / sub-graph / research-assistant（综合项目）
│   └── studio/          # 含 sub_graphs.py、research_assistant.py
├── module-5/            # 4 本：memoryschema_profile / memoryschema_collection / memory_store / memory_agent
│   └── studio/          # （长期记忆，产出 task_maistro ToDo 应用）
└── module-6/            # 4 本：creating / connecting / double-texting / assistant（LangGraph Platform 部署）
    └── deployment/      # task_maistro.py + langgraph.json + docker-compose-example.yml
```

【核心】**没有任何模块级 README**（find 全仓验证：README.md 仅根目录一个）。导航逻辑是：根 README 一句话说明 → 每本 notebook 的 cell 0 徽章直达对应线上课时。

【核心】徽章覆盖率 22/30：module-0~4 的每本 notebook cell 0 都是双徽章 `[Open in Colab]` + `[Open in LangChain Academy]`（后者链到 academy.langchain.com 的具体 lesson URL，如 `.../lessons/58238187-lesson-2-simple-graph`）；**module-5/6 的 8 本两枚徽章都没有**（脚本逐一解析 cell 0 验证），改用文首 `## Review / ## Goals` 章节承接上文。

【核心】模块主题线性递进：0 环境 → 1 基础组件（图/链/路由/agent/记忆/部署预览）→ 2 状态深挖 → 3 调试与人工介入 → 4 并行与子图（以 research-assistant 收束）→ 5 长期记忆（以 task_maistro 应用收束）→ 6 部署。每模块 1~6 本，模块内部也有顺序（module-1: simple-graph → chain → router → agent → agent-memory → deployment）。

## 3. 单课解剖（module-1/simple-graph.ipynb，15 cells，全文已读）

这是官方第一课（Lesson 2: Simple Graph），也是全课程的模板样本：

| Cell | 类型 | 功能 |
|---|---|---|
| 0 | md 1行 | **双徽章**：Open in Colab（一键云端运行）+ Open in LangChain Academy（直达视频课时页） |
| 1 | md 5行 | `# The Simplest Graph` + 一句话任务定义 + **手绘架构图截图**（Webflow CDN 外链）："Let's build a simple graph with 3 nodes and one conditional edge." |
| 2 | code | 依赖就地声明：`%%capture --no-stderr` + `%pip install --quiet -U langgraph` |
| 3-4 | md+code | **## State**：用 `TypedDict` 定义状态 schema；markdown 链接官方文档 State 小节，解释"schema 是所有节点/边的输入契约" |
| 5-6 | md+code | **## Nodes**："Nodes are just python functions."；三个节点函数各自返回状态增量，解释默认覆盖语义并链接 reducer 文档 |
| 7-8 | md+code | **## Edges**：普通边 vs 条件边，`decide_mood` 返回 `Literal["node_2","node_3"]` 做 50/50 路由 |
| 9-10 | md+code | **## Graph Construction**：StateGraph 装配 + START/END + compile，`display(Image(graph.get_graph().draw_mermaid_png()))` **实时渲染图结构** |
| 11-12 | md+code | **## Graph Invocation**：invoke 语义逐句讲解（输入 dict → 从 START 执行 → 条件边分派 → 每节点返回值覆盖状态 → 到 END）+ 一行调用 |
| 13-14 | md+空code | 收尾："`invoke` runs the entire graph synchronously." + **给出期望输出字面量** `{'graph_state': 'Hi, this is Lance. I am sad!'}`；末尾留一个空 code cell |

【核心】教学节奏是"概念小节（State→Nodes→Edges→组装→调用）= 图谱的解剖学顺序"，每小节固定为：markdown 讲解（**每个 API 名词都超链到官方文档精确锚点**，如 graph-api#conditional-edges）+ 一个 5-20 行的最小代码 cell。

【核心】module-5 样本（memory_agent.ipynb，38 cells，已读开头）展示进阶课形态：cell 0 直接 `# Memory Agent / ## Review`（回顾上节的 profile/collection/Trustcall）`## Goals`（本节目标：组装带长期记忆的 task_mAIstro）——即"回顾+目标"开场模板。

【核心】module-6/creating.ipynb 仅 4 cells（1 code）——部署课退化为"文档导读 + 少量命令"，因为实跑在 LangGraph Platform 上。

## 4. 教学机制拆解

### 4.1 练习与验收机制（有没有练习/quiz/作业？完成如何判定？有无自动验证？）

【核心】**仓内练习为零**：30 本 notebook 中 grep `TODO`/`Uncomment`/`exercise`，仅有的 "exercise" 命中是对话示例文案（memoryschema_profile 里 "trust fall exercise" 字样）；无 quiz cell、无留白待补 cell、无 solution 文件（全文件树验证无 `solution*` 文件）。

【核心】git 历史佐证"从未有过"：simple-graph.ipynb 首个提交（7bf586c）版本的 markdown 中同样没有 exercise 字样（13 次提交演变中均无练习段加入/移除的痕迹，`git log --grep exercise` 无命中）。

【核心】判定"完成"的唯一线索是课尾给出期望输出字面量（如 simple-graph cell 13），学习者肉眼比对。

【推断】quiz/评分应存在于 academy.langchain.com 平台侧（视频课平台常规能力），但平台内容不在仓内，无法验证 ⚠️。仓库对学习进度完全无感知。

### 4.2 代码组织（每课独立项目？共享依赖？版本锁定？运行入口？）

【核心】notebook 自包含：每本开头 `%pip install -U <本课所需包>`（不是全仓 requirements 的镜像）；API key 用交互式 `_set_env` 助手——先查 `os.environ.get(var)`，没有则 `getpass.getpass` 现场输入并写回进程环境（module-1/agent.ipynb cell 3-5 所见），另有 LangSmith 三件套环境变量就地开启 tracing。

【核心】双形态复刻：notebook 里的每个 graph 在同模块 `studio/*.py` 中以纯 .py 复刻一遍（对照 simple-graph.ipynb 与 module-1/studio/simple.py：State/decide_mood/三个节点/装配代码逐行相同），由 `langgraph.json` 的 `graphs` 字典注册（如 `"simple_graph": "./simple.py:graph"`）供 `langgraph dev` 加载进 Studio 交互调试。**教学代码与可部署资产是同构两份。**

【核心】版本策略宽松：根 requirements.txt 中 `langgraph` 等核心包不 pin、其余用 `>=`（对比 GenAI_Agents 的 `==`），跟随最新版；`.devcontainer` 在 Codespace 创建后自动 `pip install -r requirements.txt`。

【核心】module-2 起出现跨文件状态：`state_db/example.db`（sqlite 检查点持久化）被模块内 notebook 共享使用。

### 4.3 视觉与辅助材料

【核心】三层视觉体系：
1. **课首手绘图**：每本 1-3 张 Keynote/手绘风格截图，全部外链 Webflow CDN（`cdn.prod.website-files.com/.../simple-graph1.png` 等，全仓 43 处引用，文件名规律 `<课名>1.png`）；module-3 的 time-travel 课多到 3 张；
2. **实时 Mermaid 渲染**：24/30 本调用 `graph.get_graph().draw_mermaid_png()` 把代码里的图即时可视化（"你写的图长这样"）；
3. **Studio 交互**：浏览器里点选节点、看实时 trace、time-travel 回放——这是 .py 复刻形态存在的理由。

【核心】文字辅助的核心手法是**文档路标**：markdown 里几乎每个 API 术语（State/Nodes/Edges/START/END/compile/runnable/invoke）都超链官方 docs 的对应小节锚点，教程本身刻意写薄，深读交给文档。

### 4.4 进阶曲线（前置关系、理论实践配比、篇幅节奏）

【核心】两级线性结构（模块序 + 模块内课时序，文件名即顺序），无环无跳线；module-1 的 deployment.ipynb 是"预告式"早讲部署，module-6 再正式展开。

【核心】篇幅随进阶增长（cell 总数统计）：module-1 平均为 12~32 cells，module-3/time-travel 68，module-5/memoryschema_profile 55，module-4/research-assistant 44 cells（其中 code 32）；module-6/creating 反而只有 4（部署靠平台）。

【核心】markdown:code 大体 1:1 到 1:1.2（如 simple-graph 8 md / 7 code；state-reducers 17/19）；module-5 的 memory_agent 反转为 8 md / 30 code——进阶课明显"少讲多敲"。

【核心】收束手法：module-4 以 research-assistant（并行+子图+搜索工具的综合助手）、module-5 以 task_maistro（记忆 ToDo 应用）做模块级"毕业项目"，后者直接被 module-6 拿去部署——课程产出物贯穿到结尾。

## 5. 对 py-night-school 的可借鉴点（编号列表，每条给具体落地建议）

1. **课时头部的导航 cell**（源自 cell 0 双徽章）：每课 notebook 首格固定放：本课在课程树中的位置、前置课链接、练习文件路径、pytest 运行命令——把"去哪儿做练习"做成课文的第一个可点击元素，而不是课后附录。
2. **文档/源码路标手法**（源自每术语超链官方文档锚点）：我们的"源码路标"环节照此做成可点击链接——不只链文档，还链到依赖库 GitHub 源码的类/函数级位置（如手写 mini-agent 课链到 openai-python 的 chat.completions 实现），Java 工程师习惯"进源码看契约"，这条路径要一等公民化。
3. **"回顾+目标"开场模板**（源自 module-5 的 `## Review / ## Goals`）：六段式的"目标"段固化为两小节——上一课交付了什么可复用物（如 mini loop）、本课在它上面加什么、pytest 过了算完成。晚课学员隔周上课，回顾段是记忆锚点。
4. **notebook 与 .py 双形态、练习锚定 .py**（源自 studio/*.py 复刻 + langgraph.json 注册）：每课产出同时落成 讲解 notebook + `exercises/lesson_xx.py`（学员填 TODO 的目标文件），pytest 只测 .py。比在 notebook 里验收更稳（避免 notebook JSON 执行的脆弱性），也逼我们对齐 GenAI_Agents 的"notebook 可执行化"路线二选一时有明确取舍。
5. **课尾期望输出字面量 → 升级为自动断言**：simple-graph 把期望输出印在 markdown 里让我们看到"最低配验收"的形态；我们直接升一档——同一期望值写进 pytest，学员跑 `pytest` 即比对自己结果，输出漂移立即可见。
6. **模块级毕业项目贯穿制**（research-assistant / task_maistro 模式）：金融毕业设计不该是最后一课才启的新项目，而是每模块结课时"长一块"的同一项目（数据模块加行情工具、记忆模块加持仓偏好、多体模块加研报流水线），最后部署课收尾。
7. **`_set_env` 交互式密钥助手**（getpass 回退写回 os.environ）：夜校现场同学环境参差，这个 6 行助手可原样搬进我们的 setup 课，比要求课前配好 .env 更抗事故。
8. **图结构即时可视化**（draw_mermaid_png 等价物）：无框架手写 mini-agent 课可自制 10 行"把消息流水渲染成表格/ASCII 时序"的 helper，让"transcript 即记忆"看得见——对应 LangGraph 的图渲染，是我们的无框架版教具。

## 6. 局限与反例（不适合我们或做得不到位的地方）

1. **仓内零练习、零验收、零 solution**——与 GenAI_Agents 同样的空缺，且连作者侧测试都没有；两仓对照说明"notebook 教程生态默认不做练习"，py-night-school 的 pytest 验收机制在竞品中无先例可抄，需自建。
2. **教学主体在仓外**：讲解视频、测验、课程顺序都在 academy.langchain.com；一旦网站改版/下线，仓库只剩无序可猜的素材（无模块 README 兜底）。反面教训：我们的大纲、顺序、讲解必须自包含在仓库内。
3. **徽章体系不一致**（8/30 缺失，module-5/6 无外链入口）：多批次产出未对齐规范的典型症状；我们的课时导航 cell 应由模板校验脚本保证全覆盖（借鉴 GenAI_Agents 的 validate 思路）。
4. **宽松版本策略对夜校是风险**：`langgraph` 不 pin，半年后新装环境可能与讲义输出不一致；我们应每课 lock + 提供 `pip check` 式预检，宁可旧一点也要可复现。
5. **强产品绑定**：LangSmith/Studio/LangGraph Platform 是自家商业产品，课程即产品漏斗（module-6 整章教付费平台部署）。我们选型必须框架中立、可替换——这正是"无框架对照组"的存在意义。
6. **代码风格对 Java 工程师不够"厚"**：节点函数无类型标注、无 docstring（`def node_1(state):`），教程假设读者已会 Python；我们的受众是 Java 工程师，第一模块必须补 Python 类型系统/数据类/装饰子的桥接，不能学它直接上 API。
7. **图片全外链 CDN**：43 处 Webflow 外链，离线打开或链接腐烂即失图；我们的图应进仓（GenAI_Agents 的 images/ 本地化做法在这一点上更对）。
