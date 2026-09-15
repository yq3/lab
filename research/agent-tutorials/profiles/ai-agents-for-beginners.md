# ai-agents-for-beginners 教程解剖档案

> 对象：microsoft/ai-agents-for-beginners（本地 ~/develop/opensource/ai-agents-for-beginners，HEAD 25b7985f 2026-09-10；稀疏克隆，`git sparse-checkout` 排除 `translations/` 与 `translated_images/`——本档案所有结论仅基于未被排除的内容，不涉及被排除目录）
> 视角：为 py-night-school（Java 工程师 × Python Agent 夜校）提炼课程设计与教学方式启发
> 证据纪律：结论可溯源到本地路径；区分【核心】（实际文件所见）与【推断】（分析判断）；查不到的标 ⚠️ 不臆测

## 1. 定位与形态

- 【核心】Microsoft 官方出品的 Agent 通识课：19 个编号目录（00 环境安装 + 01–18 正课），主题覆盖设计模式（tool use / planning / multi-agent / metacognition）、RAG、可信度、生产化、协议（MCP/A2A）、context engineering、memory、部署、本地模型、安全。README.md 自述"Each lesson covers its own topic so start wherever you like!"——定位为可跳跃的自助式课程，非强线性。
- 【核心】形态 = 每课一个 README（长文讲义，含大量行内代码）+ 一个 Jupyter notebook（`*-python-agent-framework.ipynb`）+ YouTube 短视频（README 首图即视频链接）。`.github/workflows/` 下有 smoke-test.yml（对已部署 agent 的冒烟测试，详见 4.1）。
- 【核心】技术栈强绑定 Microsoft：代码统一用 Microsoft Agent Framework (MAF) + `FoundryChatClient` 连 Microsoft Foundry Agent Service V2（Responses API）；根 requirements.txt 把 `agent-framework-core==1.10.0`、`agent-framework-foundry~=1.10.0` 钉死并写明原因（1.11.0 有破坏性变更）。另留 OpenAI 兼容后门：MiniMax / Novita AI / Foundry Local 三种替代 provider（00-course-setup/README.md）。
- 【核心】多语言（50+ 译本）由 co-op-translator GitHub Action 自动生成，排在被排除的 translations/ 里，本仓库源内容全是英文。
- 【推断】这是"官方框架推广课"而非"中立技术课"：框架绑定 + Azure 订阅门槛意味着它假设学习者愿意进 Microsoft 生态，这与 py-night-school 的"无框架手写 mini-agent"路线正好相反——反过来说明我们对照组的差异化价值。

## 2. 结构总览（关键目录树 + 组织逻辑）

```
ai-agents-for-beginners/
├── README.md                  # 课程级导航表（课时名 | Text & Code | Video | Extra Learning）
├── STUDY_GUIDE.md             # 12.7KB 学习指南：一条贯穿全课的 demo 线索（"course helper agent"）
├── requirements.txt           # 全仓唯一 Python 依赖清单（分课注释，统一钉版）
├── .env.example               # 全部环境变量模板（AZURE_AI_* / MINIMAX_* / NOVITA_* ...）
├── 00-course-setup/           # 环境课：README.md + AzureSearch.md/.cs + 19 张配置截图
├── 01-intro-to-ai-agents/ ... 18-securing-ai-agents/   # 18 个正课，统一为：
│     ├── README.md            #   讲义正文（300–1200 行不等）
│     ├── code_samples/        #   notebook + 少量 .py/.cs/.md
│     └── images/              #   1–6 张图
├── images/                    # 仅仓库 thumbnail
├── scripts/validate-notebooks.ps1   # notebook 校验脚本（PowerShell）
└── tests/                     # smoke-test 目录：README + 4 份 lesson-*-smoke-tests.json
```

- 【核心】组织逻辑：**课 = 目录**，目录名 `NN-slug` 全仓字典序即课程序；课内三件套（README / code_samples / images）恒定。例外：08-multi-agent 额外有 `assets/`（练习底图）与 `solution/`（练习答案 + quiz 答案）；11/14 有子项目目录（github-mcp、workflows-agent-framework、code-samples）。
- 【核心】依赖策略：**全仓单 requirements.txt**，不按课拆分；注释标明哪个包属于哪课（如 `# Lesson 17 ... foundry-local-sdk / chromadb`、`# Lesson 18 ... jcs / pynacl`）。
- 【核心】STUDY_GUIDE.md 是"第二层教学设计"：提出一个贯穿全课的 demo（课程助手 agent），每课学完问"What can my demo agent do now that it could not do before?"，并用一张 8 行表把 Model/Tools/Knowledge/Context/Memory/Planning/Orchestration/Trust 映射到该 demo 上。
- 【推断】"单仓单依赖 + notebook 即代码"是最省运维的组织法，但代价是环境一经升级全课联动（requirements.txt 里那大段钉版注释就是伤疤记录）。

### 2.1 00-course-setup 完整内容（环境要求 / 配置方式 / 厂商绑定程度）

00-course-setup/README.md（419 行）+ AzureSearch.md/.cs（Azure AI Search 索引搭建的 Python/.NET 补充样例）+ images/ 19 张配置截图。章节依次为：Introduction → Join Other Learners（Discord）→ Clone or Fork（含 Shallow/Sparse Clone 与 Codespaces 三种下载策略）→ Running the Code → Requirements → Setup VSCode → Set Up Microsoft Foundry and Microsoft Foundry Agent Service（Step 1–5）→ Optional Setup: Azure AI Search → Additional Setup for Lessons 6/8 → 替代 Provider（MiniMax / Novita AI / Foundry Local）→ Lesson 8 Bing 变量 → Troubleshooting（macOS SSL 证书三方案）→ Next Lesson。

| 维度 | 【核心】实际内容 |
|---|---|
| 语言/运行时 | Python 3.12+（venv 命令逐步给出）；.NET 10 SDK（仅 .NET 样例需要） |
| 云依赖 | **硬依赖**：Azure 订阅 + Azure CLI（`az login`）+ Foundry hub/project + 部署模型（示例 gpt-5-mini）。认证走 `AzureCliCredential`/`DefaultAzureCredential` 免 API key，文中称此为 security best practice |
| 必需配置 | `.env` 仅两个变量：`AZURE_AI_PROJECT_ENDPOINT`、`AZURE_AI_MODEL_DEPLOYMENT_NAME`（附"去哪找"表格） |
| 按课附加 | 课 5/16 可选 Azure AI Search（不配则回落内存知识库）；课 6/8 直连 Azure OpenAI（Responses API）；课 8 Bing grounding 的 `BING_CONNECTION_ID` |
| 厂商解绑程度 | 主路径绑定 Foundry；但 MAF 的 `OpenAIChatClient` 兼容任何 OpenAI 端点，故 MiniMax（204K 上下文）、Novita AI（kimi/glm/deepseek 等开源模型）、Foundry Local（本机 phi-4-mini，brew 可装）三种替代均给出 env 表与示例代码；README 主文件同时说明"Novita 当前样例不会自动读取 env，需显式传参"——绑定向开放，但默认体验仍是 Azure |
| 环境课的排错位 | Troubleshooting 专门处理 macOS Python SSL 自签证书问题（Install Certificates.command / connection_verify=False / truststore 三方案，含安全警告）——把最劝退的第一坑前置处理 |

- 【推断】"两变量起步 + 按课增量 + 云服务有本地回落"是环境设计的三条好原则；但对无 Azure 账号的学习者，主路径第一课就断——夜校应把"无云依赖可跑"设为硬约束，云增强作为可选延伸。

### 2.2 课程级 README 的导航表结构

- 【核心】导航表四列：`Lesson | Text & Code | Video | Extra Learning`。18 行课时：每行课时名 + README 相对链接 + YouTube 链接 + aka.ms 收藏集链接；13 课（Managing Memory）起 Video 列开始出现空缺，15–18 课 Video/Extra 两列大面积留空——更新中的课程用表格空格自然暴露覆盖度。
- 【核心】表前有 `## 📂 Each lesson includes` 三行承诺："A written lesson located in the README and a short video / Python code samples using Microsoft Agent Framework with Microsoft Foundry / Links to extra resources"——相当于课时模板的公开契约。
- 【核心】表不标注时长、难度、前置；前置关系外置到 STUDY_GUIDE.md（"Complete Lessons 01-06 in order"）。
- 【推断】"每课包含什么"写在导航表之前是个好习惯：学员在点进任何一课前已知道课时形态契约；夜校可照抄为"每课 = 目标/Java 对照/动手/练习(pytest)/坑位/延伸 六段"声明。

## 3. 单课解剖

### 3.1 课时 04 Tool Use（04-tool-use/README.md，334 行）完整章节结构

| 章节标题 | 功能 |
|---|---|
| （顶部缩略图链接 + 一句引言） | 视频入口；一段无标题导语定义本章主题 |
| `## Introduction` | 以 4 个问题的形式列出本章要回答什么（what/use cases/elements/considerations） |
| `## Learning Goals` | 4 条"学完你将能……"的能力目标（Define/Identify/Understand/Recognize） |
| `## What is the Tool Use Design Pattern?` | 概念定义。原文："Tools are code that can be executed by an agent to perform actions." |
| `## What are the use cases it can be applied to?` | 5 类场景列表（动态取数 / 代码执行 / 工作流自动化 / 客服 / 内容生成） |
| `## What are the elements/building blocks needed...` | 6 个构建块加粗列表（Schema / 执行逻辑 / 消息处理 / 集成框架 / 错误处理 / 状态管理） |
| `### Function/Tool Calling`（属上一节） | **核心动手段**：先用原生 OpenAI Responses API 手写三步（初始化 client → 建 JSON schema → 实现函数 + 回填 function_call_output），每步代码 + 期望输出都贴出来；结尾承认"implementing it from scratch can sometimes be challenging"，引出框架 |
| `## Tool Use Examples with Agentic Frameworks` | 对照组：同一 get_current_time 例子改用 `@tool` 装饰器（MAF）；再介绍 Foundry Agent Service 的 server-side 工具调用与开箱工具（Knowledge Tools / Action Tools 两类清单） |
| `## What are the special considerations ... trustworthy AI agents?` | 信任/安全讨论（LLM 生成 SQL 的注入风险、只读库缓解） |
| `## Sample Codes` | 两行链接：Python notebook、.NET 版（.md 文档形态） |
| `## Got More Questions ...?` | Discord 入口（模板化出现在每课） |
| `## Additional Resources` | 3 个外部延伸链接 |
| `## Smoke-Testing This Agent (Optional)` | 指向 tests/lesson-04-smoke-tests.json，注明学完 16 课部署后可回来测 |
| `## Previous Lesson` / `## Next Lesson` | 线性导航闭环 |

- 【核心】有：学习目标、行内代码、输出示例、延伸链接、前后课导航。**没有**：quiz（仅 08 课有）、作业、时长标注、TODO 式练习——正文读代码为主，动手全在 notebook 里。
- 【核心】教学顺序值得注意：**先裸 API 手写 tool call 循环，再展示框架糖**（`@tool` 装饰器）——与 py-night-school"无框架对照组先手写"的思路撞车，可作为先例引用。
- 【核心】notebook（04-python-agent-framework.ipynb，14 个 cell）与 README 不重复：notebook 走 `FoundryChatClient` + `@tool` + 多工具 agent + Pydantic 结构化输出 + `approval_mode`（human-in-the-loop），markdown 标题构成第二套小大纲，末尾有 Summary cell。

### 3.2 课时 12 Context Engineering（12-context-engineering/README.md，180 行）完整章节结构

| 章节标题 | 功能 |
|---|---|
| `# Context Engineering for AI Agents` + 视频链接 + 导语 | 区分本课与 prompt engineering 的动机 |
| `## Introduction` | 4 个要点式覆盖范围（是什么 / 策略 / 常见失败） |
| `## Learning Goals` | 4 条能力目标 |
| `## What is Context Engineering?` | 定义。原文："making sure the AI Agent has the right information to complete the next step of the task." |
| `### Prompt Engineering vs Context Engineering` | 一对一对比：静态指令规则 vs 动态信息管理 |
| `### Types of Context` | 5 类上下文清单（Instructions/Knowledge/Tools/History/Preferences），配概念图 |
| `## Strategies for Effective Context Engineering` | 分两层 |
| `### Planning Strategies` | 3 步规划法（Define Clear Results → Map the Context → Create Context Pipelines） |
| `### Practical Strategies` → `#### Managing Context` | 6 个实操策略：Scratchpad / Memories / Compressing / Multi-Agent / Sandbox / Runtime State Objects |
| `#### Inspecting Context` | 生产环境调试：不记原始 prompt，记 counts/ids/hashes/policy labels；核心问句"Did the agent load too much context, the wrong context, or miss context it needed?" |
| `### Example of Context Engineering` | 一个"订巴黎机票"贯穿例子：prompt-only agent vs context-engineered agent 的回复对比 |
| `## Common Context Failures` | 全课最精彩段落：4 种失败模式各按 What/What to do/Travel Example/Solution 四段展开——Poisoning（验证+隔离）、Distraction（摘要压缩）、Confusion（工具 RAG，"limiting tool selections to fewer than 30"）、Clash（剪枝+外置） |
| `## Got More Questions About Context Engineering?` | Discord |
| `## Previous Lesson` / `## Next Lesson` | 导航 |

- 【核心】本课 README **无 Sample Codes 章节、无代码块**；code_samples/ 里只有一个 `12-chat_summarization.ipynb` 和一份 `vacation_agent_scratchpad.md`——纯理论课 + 轻量佐证 notebook 的形态。
- 【核心】四失败模式（poisoning/distraction/confusion/clash）是原创性的教学骨架，且全部用同一个 travel 例子贯穿。
- 【推断】04（重代码）与 12（重概念）代表本课程的两种课时形态：模式课带完整代码走读，理论课靠"一个例子贯穿 + 失败模式分类"撑起来。py-night-school 可对应"动手课/概念课"双模板。

## 4. 教学机制拆解

### 4.1 练习与验收机制（有没有练习/quiz/作业？完成如何判定？有无自动验证？）

- 【核心】**主体没有练习**：18 个正课 README 里没有 TODO 练习、没有作业提交；练习性内容内嵌在 notebook 的"跑通并观察输出"里。
- 【核心】**唯一 quiz**：08-multi-agent/solution/solution-quiz.md（Knowledge Check Answers），题目以 checkbox 形式出在 08 课 README 里，答案单独放 solution/ 目录——防止顺手看到答案的简单分离。
- 【核心】**唯一自动验收 = smoke tests**：tests/ 下 4 份 JSON catalog（lesson-01/04/05/16），由 `.github/workflows/smoke-test.yml` 调 AI Smoke Test GitHub Action，对**部署到 Foundry 的 hosted agent** 发 prompt 并断言回复包含指定子串（`contains_any/contains_all/contains_none`，还支持 `save_response_id_as` 做多轮链测）。tests/README.md 明说哪些课**故意不给** smoke test（"Lessons that are conceptual, run only locally, or produce non-deterministic creative output are intentionally excluded"）。
- 【核心】验收的前提是先完成 16 课的部署流程——验收被设计为"学习部署后的回归手段"而非每课达标门槛。
- 【推断】对本课程这种部署型作业，子串断言已是务实的下限；但对 py-night-school"TODO + pytest 自动验收"的模式，这个课程几乎没有可借鉴的实现细节，只能借鉴它"catalog 与课对应 + 声明哪些课不适合自动测"的元信息表达。

### 4.2 代码组织（每课独立项目？共享依赖？版本锁定？运行入口？）

- 【核心】每课 `code_samples/` 一个 notebook 为主，命名 `NN-python-agent-framework.ipynb`；.NET 版是 `.cs` 源文件 + `.md` 使用说明（见 01/03/04/05/07/08 课）。少数课多 notebook（06 两份、11 两份 mcp/a2a、13 两份、18 两份）。
- 【核心】依赖全仓共享（根 requirements.txt），版本半锁定：`agent-framework-core==1.10.0` 精确钉，`openai>=1.108.1` 下限式，其余不钉；仅 18 课自带局部 requirements.txt。
- 【核心】运行入口统一：notebook 首个 code cell 直接 `%pip install ... -U -q` 后接环境加载，root .env 两变量（`AZURE_AI_PROJECT_ENDPOINT` + `AZURE_AI_MODEL_DEPLOYMENT_NAME`）+ `az login` 免密（AzureCliCredential）。00-course-setup 把"哪课要额外变量"集中交代（课 5/16 Azure Search、课 6/8 Azure OpenAI 直连、课 8 Bing）。
- 【核心】scripts/validate-notebooks.ps1 用于维护者校验 notebook（CI 而非学习者工具）。
- 【推断】"notebook 即运行入口 + 全局 .env"使上手成本最低；但 `%pip install -U` 与根 requirements 的钉版互相打架（-U 会装最新版），属于教程工程化不严谨处。

### 4.3 视觉与辅助材料

- 【核心】每课 images/ 1–6 张（中位数 3），三种角色：①lesson-N-thumbnail.png（视频封面，兼视频超链接载体）②概念图（context-types.png、functioncalling-diagram.png、A2A-Diagram.png 等，PNG 矢量风格架构/流程图）③产品截图（agent-service-in-action.jpg、00 课的 19 张 Azure 配置截图）。**没有手绘 sketchnote**——手绘风是 generative-ai-for-beginners 的传统，本课不是（见各课 images/ 实际文件名）。
- 【核心】后期课（15/18）images 为空、10/13/16/17 仅 1 张：视频与配图投入随课程更新逐渐下降（15 课起导航表的 Video 列也开始空缺）。
- 【核心】00-course-setup 的 19 张截图全部是 Azure portal/GitHub fork 操作截屏，配合分步文字。
- 【推断】图片密度与其说服务于理解，不如说"前 11 课每课标配 thumbnail+1~2 图"是模板纪律；对夜校更有参考价值的是 00 课**分步截图化环境配置**——环境课图文比 1:1 是降低弃课率的关键。

### 4.4 进阶曲线（前置关系、理论实践配比、篇幅节奏）

- 【核心】官方推荐的路径在 STUDY_GUIDE.md："Complete Lessons 01-06 in order"——前 6 课（intro→框架概览→设计模式总览→tool use→RAG→可信）是强序核心，之后自由选学。
- 【核心】README 导航表 18 行三列（Text & Code / Video / Extra Learning），无时长、无难度标注；11–18 为追加章（13 memory 起 Video/Extra 列开始稀疏）。
- 【核心】篇幅节奏（README 行数）：04 课 334 行、12 课 180 行属中位；08 课（含 quiz）与 05 课更长。代码量集中在 notebook（04 课 14 cells）。
- 【核心】课程自带"版本时间线教学"：CHANGELOG.md 16KB 记录课程演进（GitHub Models 弃用改 Azure OpenAI Responses API 等），.env.example 内嵌"模型退役日期"注释（gpt-4.1 retire 14 Oct 2026）。
- 【推断】理论:实践 ≈ 6:4（多数课一半篇幅是概念与场景列举）；对已是有经验工程师的夜校受众，可压缩概念列举、保留"手写→框架"对照与"失败模式"两类高价值段落。

## 5. 对 py-night-school 的可借鉴点（编号列表，每条给具体落地建议）

1. **"裸 API 手写 → 框架糖"的课内顺序**（04 课先写三步 Responses API tool-call 循环再给 `@tool`）：与我们"无框架 mini-agent 对照组"完全同构。落地：每课动手段固定两栏——左边手写循环（含期望输出贴片），右边等价框架代码；04 课原文 "a **tool call** is what is returned, **not** the final answer" 可直接用作 TODO 练习的断言目标（pytest 里断言拿到的先是 tool_call 再是 final answer）。
2. **Introduction 用 3–4 个问题当章节地图**（每课 `## Introduction` 只列问题，`## Learning Goals` 列可验证能力动词）：落地：六段式模板的"目标"段拆两小节——"本课回答的 N 个问题"+"学完你能……（Define/Identify/Build/Debug 动词开头）"，目标动词直接对应 pytest 验收断言。
3. **贯穿全课程的单一 demo 线索**（STUDY_GUIDE 的 course helper agent + 8 部件映射表 + "每课学完问 demo 多了什么能力"）：落地：金融毕业设计就是我们的 demo 线索，为它做一张"概念×课时×毕设落点"映射表放进课程 README，每课结尾一段"本课让你的毕设 agent 多了什么"。
4. **失败模式命名学**（12 课 poisoning/distraction/confusion/clash 四失败 + What/Example/Solution 四段模板，全程一个 travel 例子）：落地：坑位段（六段式的"坑位"）把每课 2–3 个坑起专有名词（如"schema 漂移"、"上下文泄漏"），统一用毕设的金融场景举例，可预期记忆点远高于零散 tips。
5. **smoke-test catalog 与课分离 + "哪些课不适合自动测"的显式声明**（tests/README.md 列出排除原因）：落地：我们的 pytest 验收也做两级——练习级（每课 tests/test_lesson_NN.py，TODO 填空后跑）与毕设级（对成品 agent 的断言 catalog，JSON 描述 prompt+期望子串），并在文档里声明哪些练习因非确定性只做半自动验收。
6. **环境课全截图化 + 变量集中表**（00 课 19 张截图、.env.example 两必需变量起步、按课列出"额外需要什么"的表格）：落地：第 0 课为 Java 工程师写"Python 3.12 + venv + uv + API key"每步截图；env 变量表分"必需（2 个）/按课附加"两段，附 Java 侧对照（Spring 的 application.yml ↔ .env）。
7. **quiz 与答案分文件**（08 课题目在 README、答案在 solution/solution-quiz.md）：落地：课后小测同样答案分离，且题目用"选场景"型（什么时候用 X）而非名词解释型。
8. **钉版理由写进 requirements 注释**（1.10.0 钉版附一段"1.11 破坏了什么"）：落地：毕设模板的 requirements 每个钉版包写一行为什么，教"依赖治理"本身就是 Java 工程师熟悉的话题。

## 6. 局限与反例（不适合我们或做得不到位的地方）

- 【核心】无练习闭环是最大短板：18 课里仅 1 个 quiz、0 个带判定的练习；"动手"等于"跑通别人写好的 notebook"。py-night-school 的 TODO+pytest 模式不能从这里取材。
- 【核心】厂商绑定深：跑通任何 notebook 都需要 Azure 订阅 + Foundry 项目 + 部署模型，非 Microsoft 生态的学习者只能"读代码"。我们应以"一个 API key（或本地模型）即可跑"为底线。
- 【核心】notebook `%pip install -U -q` 与根 requirements 钉版自相矛盾（见 4.2），且全仓单依赖清单导致任何一课升级牵动全课——夜校若每课独立目录，应每课自带可独立安装的依赖（或共享 workspace + 锁文件）。
- 【核心】概念列举密度高而工程深度浅：多数课的 use-cases/elements 段落是清单式罗列（04 课 5 类场景 + 6 个构建块），对有后端经验的 Java 工程师信息增量低；真正高价值的"手写对照"和"失败模式"反而占比小——夜校应反转这个比例。
- 【核心】课程后期维护衰减明显（15/18 课无图、视频断更、导航表后几行 Video/Extra 列空缺）：提醒我们课时模板要"可持续"，宁可每课固定轻量骨架（目标/对照/动手/练习/坑位/延伸）也不要重型配套（视频/手绘图）拖垮更新。
- ⚠️ translations/ 与 translated_images/ 被稀疏克隆排除，多语言机制的实际质量（译文准确度、图片本地化）无法核查，不作评价。
