# openai/openai-cookbook 教程解剖档案

> 对象：openai/openai-cookbook（本地 ~/develop/opensource/openai-cookbook，HEAD 9aad95f，2026-09-12；全量克隆，约 2GB，含数据素材）
> 视角：为 py-night-school（Java 工程师 × Python Agent 夜校）提炼课程设计与教学方式启发，并评估其作「延伸阅读池」的用法
> 证据纪律：结论可溯源到本地路径；区分【核心】（实际文件所见）与【推断】（分析判断）；查不到的标 ⚠️ 不臆测
> 背景：1458 个 commit（2022-03-10 起），周更级活跃；MIT 协议【核心】

## 1. 定位与形态

- 自我定位是 **recipe 集（菜谱）而非课程**：README 仅 12 行，核心一句 "Example code and guides for accomplishing common tasks with the OpenAI API"，并声明 "Most code examples are written in Python"【核心，README.md】
- 真正的导航主入口在站外："✨ Navigate at cookbook.openai.com"——仓库是内容源，网站是阅读层，两者靠 `registry.yaml` 元数据生成器连接【核心】
- 无课程顺序、无练习、无学习路径；每个 recipe 独立成篇，解决一个具体任务（"How to count tokens"、"How to handle rate limits"）。与 anthropics/courses 的「课」形态形成鲜明对照：**cookbook = 查阅型资产，courses = 跟练型路径**【核心+推断】
- 大量内容为官方产品带路：articles/ 里有 ChatGPT 工作区 agent 操作教程、gpt-oss 本地部署系列（Ollama/LM Studio/vLLM）——厂商把 cookbook 当产品发布配套文档用【核心】

## 2. 结构总览（关键目录树 + 组织逻辑）

```
openai-cookbook/
├── README.md            # 12 行极简：定位 + API key 说明 + 网站链接
├── AGENTS.md            # 仓库贡献规范（结构/命令/风格/测试/PR/编辑流程/recent learnings）
├── registry.yaml        # 95KB，316 条内容索引 → 生成 cookbook.openai.com（title/path/slug/description/date/authors/tags）
├── authors.yaml         # 作者档案（name/website/avatar），覆盖 GitHub 默认资料
├── articles/            # 12 项：叙述性长文（.md/.mdx）+ gpt-oss 系列子目录（11 篇）
├── examples/            # 主体：~85 个松散 .ipynb/.py 文件（历史遗留平铺）+ ~35 个主题子目录
│   └── data/            # 46 项共享小数据资产（csv/jsonl/pdf/db/图片/音频）
├── images/              # 470 张共享截图/图解
└── .github/             # PR 模板 + check_notebooks.py + validate-notebooks.yaml（CI）
```

- **articles/ 与 examples/ 分工**（AGENTS.md 原文）："Place notebooks and Python scripts under `examples/<topic>/` … Narrative guides and long-form docs live in `articles/`"——**可运行代码归 examples，叙述性文字归 articles**【核心，AGENTS.md L5】
- examples/ 的主题组织是**双轨混合**【核心】：
  - 老内容：根下平铺 `How_to_xxx.ipynb` / `Orchestrating_agents.ipynb`（约 85 个）
  - 新内容：按「产品/SDK/场景」建子目录：`agents_sdk`(14 条)、`agents_api`、`mcp`、`responses_api`、`chatgpt`(35)、`vector_databases`(35)、`evaluation`(16)、`multimodal`、`gpt-5`、`codex`、`partners`(12，第三方共建)、`azure`、`o1`、`deep_research_api`、`voice_solutions`…（registry.yaml path 统计）【核心】
  - 子目录命名按**功能域/产品域**而非难度或场景顺序；同一主题靠 registry tags 横向聚合（tags 高频：embeddings 99、completions 94、chatgpt 37、responses 35、evals 31、agents 29、functions 27、agents-sdk 26）【核心】
- **导航三层**：README（一句话）→ registry.yaml（机器可读全索引）→ 网站（tag/搜索人工导航）。仓库内没有给人看的大目录页【核心】
- registry.yaml 每条目 8 字段：`title / path / slug / description / date / authors / tags`（+多行 path 折叠），顶部声明 "This file is used to generate cookbook.openai.com. It specifies which paths we should build pages for, and indicates metadata such as tags, creation date and authors for each page"——**内容与站点元数据单点同步**，且 AGENTS.md 把"新增内容必须登记 registry + PR 模板勾选"写进流程【核心】
- articles/ 的 gpt-oss/ 子系列（11 篇）是「一产品一组文」的样例：run-locally-ollama / run-locally-lmstudio / run-vllm / run-nvidia / verifying-implementations…按部署后端逐篇拆开，而非一篇大而全【核心】

## 3. 单课解剖（代表性 recipe 章节结构）

### 3.1 articles/chatgpt-agents-sales-meeting-prep.md（154 行，完整读毕）——article 形态【核心】

章节流：`# Building workspace agents in ChatGPT…` → **Introduction**（销售团队会议准备的真实痛点 + agent 一天的工作流描述）→ **Prerequisites and setup**（列出 4 项管理员权限确认清单，逐条 RBAC 配置）→ **Building your agent**（3 个编号小节：Describe your workflow → Review and configure your apps → Enabling skills and memories）→ **Testing your agent** → **Deploying your agent**（定时调度 + 分享）

- 特征 1：**给可粘贴的完整任务描述词**——"1. Describe your workflow" 小节直接给一段 40 行的自然语言工作流描述让读者贴进 agent builder【核心】
- 特征 2：**权限模型讲透**——End-user account vs Agent-owned account 两种连接器鉴权的差异，及其对"共享 agent 后谁能看到什么"的连锁影响，写在部署环节【核心】
- 特征 3：纯产品操作 walkthrough，配 15+ 张 CDN 外链截图（`cdn.openai.com/cookbook/...`），无代码、无练习
- 【推断】article 的隐性模板 = 场景价值 → 前置条件（含管理员项）→ 编号搭建步骤 → 测试 → 部署，本质是「产品上手指南」

### 3.2 articles/what_makes_documentation_good.md（65 行，完整读毕）——OpenAI 的写作宪法【核心】

三节 + 例外条款：**Make docs easy to skim**（标题用信息完整的句子不用抽象名词、加目录、短段落、段首主题句、"Put the takeaways up front. Don't write a Socratic big build up"、多用 bullet/表格/加粗）→ **Write well**（简单句、可无歧语解析、避免左分支句、避免指示代词 this、一致性、"Don't tell readers what they think"）→ **Be broadly helpful**（"Explain things more simply than you think you need to"、"even an expert JavaScript engineer or C++ engineer might be a beginner at Python. Err on explaining too much"、避免缩写、示例自包含最小依赖、**"Don't teach bad habits"——绝不展示把 API key 写进代码的示例**）→ **Break these rules when you have a good reason**（"Documentation is an exercise in empathy"）

### 3.3 examples/agents_sdk/multi-agent-portfolio-collaboration/ ——「recipe as 迷你项目」形态（完整读毕）【核心】

文件构成：`multi_agent_portfolio_collaboration.ipynb`（18 cell 主文档）+ `investment_agents/`（Python 包：pm/editor/fundamental/macro/quant 各一文件 + config）+ `prompts/`（6 个 .md 系统提示词外置）+ `tools.py` + `utils.py` + `mcp/yahoo_finance_server.py`（本地 MCP 服务器）+ `requirements.txt`（15 个依赖，未锁版本）+ 独立 `.gitignore`

notebook 章节流（18 cell）：

| 节 | 功能 |
|---|---|
| # 标题 + Introduction | 开头一句读者定位："*This guide is for readers already familiar with… and want to see how to orchestrate a team of agents for a real-world, complex task*"，然后 **What You'll Learn**（4 条 bullet）+ **Why this matters** |
| ## Table of Contents | 锚点目录 |
| ## What is Multi-Agent Collaboration? | 概念对比小节：**Handoff vs. Agent-as-Tool** 两种协作模式各自取舍，并声明本例选后者及理由 |
| ## Architecture Overview / Supported Tool Types | 图解架构；三类工具（MCP server / OpenAI 托管工具 / 自定义函数）一次讲齐 |
| ## Setup / Running the Workflow | 装 requirements、跑通主流程（与 investment_agents/ 包联动，notebook 只做编排演示） |
| ## Breaking Down the Head PM Agent | **Why This Design?**（拆分动机：深度/模块化/并行/可审计）→ 代码走读 → "The Head PM System Prompt: Enforcing Best Practices"（用 cell 直接 render prompts/pm_base.md 讲提示词设计） |
| ## Example Output | 内嵌一份完整真实运行产物：5 页投资备忘录（Executive Summary → Fundamentals → Macro → Quant → PM → Recommendation）——**拿产物当证据** |
| ## Best Practices / Further Reading | SDK 能力清单收尾 |

### 3.4 examples/mcp/building-a-supply-chain-copilot-with-agent-sdk-and-databricks-mcp/ ——README 驱动全栈项目【核心】

`README.md`（78 行）+ `api_server.py`（FastAPI 流式 /chat）+ `databricks_mcp.py` + `main.py` + `supply_chain_guardrails.py` + `ui/`（React）+ `requirements.txt`。README 结构：Features → Quickstart（0. Databricks assets → 1. Prerequisites → 2. Install → 3. Start Backend → 4. Start Frontend，每步带命令与验证 URL）→ Usage → **Troubleshooting**（端口占用、前端不加载的具体命令）→ Customization（改哪个文件改什么）。**无 notebook，README 即课程**

### 3.5 examples/Orchestrating_agents.ipynb（38 cell，完整读毕）——无框架手写 agent 的历史名篇【核心】

章节流：`# Orchestrating Agents: Routines and Handoffs`（开篇即立场："quite often all you need for solid performance is a good prompt and the right tools"）→ **# Routines**（定义 routine = 系统提示词 + 工具集，给出客服 routine 完整示例：system_message 字符串 + `look_up_item`/`execute_refund` 两个硬编码返回值的假工具）→ **## Executing Routines**（手写 agent 循环 `run_full_turn`：user input → append → call model → append；`tools_map` 分发；用 `inspect` 从函数签名自动生成 schema）→ **# Handoffs**（`class Agent(BaseModel)` 四字段 → handoff 函数 → triage→refund→escalation 三级转接）→ **# Swarm**（"we've packaged these ideas into a sample library called Swarm … should not be directly used in production. However, feel free to take the ideas and code to build your own!"）

## 4. 教学机制拆解

### 4.1 练习与验收机制（有没有练习/quiz/作业？完成如何判定？有无自动验证？）

- 【核心】**没有**：316 条内容里无统一练习/quiz/作业机制；验收 = 「能跑通」本身。这是 recipe 集与课程仓的根本差异
- CI 只验格式不验执行：`.github/scripts/check_notebooks.py` 用 nbformat 读取变更的 ipynb，"Checks that the notebook … is valid by attempting to read it with nbformat"——只保证 JSON 合法【核心】
- 执行纪律靠人工约定：AGENTS.md 要求 "Execute notebooks top-to-bottom after installing dependencies and clear lingering execution counts before committing"；外部服务依赖要 "mock responses or gate the cells behind clearly labeled opt-in flags"【核心】
- 少量自测存在：`examples/agents_sdk/tests/test_security_review_repository_labels.py`（单文件 pytest）与 `examples/object_oriented_agentic_approach/tests`（AGENTS.md 点名），属个别 recipe 自带【核心】

### 4.2 代码组织（每课独立项目？共享依赖？版本锁定？运行入口？）

- 【核心】**每 recipe 自管依赖**：AGENTS.md 明令 "`pip install -r examples/<topic>/requirements.txt` (each sample lists only what it needs)"；根级无统一环境文件
- 依赖**不锁版本**（portfolio 例的 requirements.txt 全是裸包名）——与教程仓「跑得起就行」的取向一致，但老 notebook 的 API 漂移靠不定期人工翻新（最近 commit 大量是 "Update Agents API examples for the official Python SDK" 式维护）【核心+推断】
- **notebook 与包分离**：大 recipe 是「notebook 当讲义 + 同目录 Python 包当实现」（portfolio 例：notebook import investment_agents），notebook 只承担叙事与编排演示——讲义/代码分层明确【核心】
- **作者署名机制**：authors.yaml 自定义展示（name/website/avatar），registry 条目挂 author slug，缺省回落 GitHub 资料——316 条内容明确到个人（含 31 条 ted-at-openai 等高产作者），PR 模板强制核对 authors checklist【核心】
- 运行入口多元：ipynb（多数）、README+脚本（supply chain 例）、单 .py（api_request_parallel_processor.py）【核心】

### 4.3 视觉与辅助材料

- images/ 顶层共享 470 张截图，article 图片走 CDN 外链，examples 内嵌图少量【核心】
- evaluate_agents.ipynb 内嵌 Cloudflare Stream 视频 iframe（演示 trace 可视化）——notebook 里嵌视频的做法【核心】
- Example Output 全文嵌入（portfolio 例的完整投资备忘录）是比截图更强的「产物证明」【核心】
- 概念图有源文件管理：examples/mermaid/ 存 4 个 .mmd 图源（agents SDK / Realtime API 流程图），说明其图解走"源文件+渲染"而非只贴死图【核心】

### 4.4 进阶曲线（前置关系、理论实践配比、篇幅节奏）

- 【核心】无前置关系声明，仅个别 article 自标难度（portfolio 例 "*for readers already familiar with…*"）
- 【推断】进阶靠「内容类型」隐式分层：articles/how_to_work_with_large_language_models.md（LLM 通识）→ examples/How_to_xxx（单任务）→ examples/agents_sdk 子目录（多 agent 系统）→ examples/evaluation（评估与生产化），网站 tag 聚合起隐形课程的作用
- 理论:实践 ≈ 1:9：几乎每篇都可直接运行；articles/techniques_to_improve_reliability.md 是少数纯理论文（从 GPT-3 失败模式讲到 CoT/least-to-most/self-consistency/verifiers，带 Bibliography）【核心】
- 篇幅两极：article 65~573 行；example notebook 18~50 cell；无统一节奏
- 内容保鲜机制【推断】：无"版本化课程"概念，靠持续投稿+人工归档维持新鲜（近期 commit 即"archive the GPT Image models prompting guide"式操作）；date 字段让网站可按时效排序，把陈旧判断交给读者

## 5. 对 py-night-school 的可借鉴点（编号列表，每条给具体落地建议）

1. **把 Orchestrating_agents.ipynb 定为「无框架 mini-agent 对照组」课时的官方对照组原件**：它与我们的教学目标完全同构（手写 run_full_turn 循环 + tools_map + Agent(BaseModel) + handoff，然后引出框架）。做法：延伸阅读引用原路径，练习课让学员先读它的 Routines→Handoffs 两节，再写我们自己的 mini-agent；Java 对照点（Agent 类 ≈ 只有字段的 POJO + 策略模式注册表）可直接映射它的 tools_map dict
2. **prompts/*.md 外置系统提示词**：portfolio 例把 6 个 agent 的系统提示词放独立 markdown 文件、notebook 里 render 讲解。金融毕业设计的多角色（研究员/风控/交易员）提示词照此办理——提示词即文档，可单独 diff、单独评审，也方便「源码路标」课时带学员定位
3. **Example Output 当「验收样张」**：每课讲义末尾内嵌一份完整真实产物（如 portfolio 例的 5 节投资备忘录），学员作业对着样张自评——弥补主观题无自动判分的缺口；金融毕业设计可直接定「产物模板 = Executive Summary / 各视角 / 建议」六节结构
4. **registry.yaml 式内容索引**：为 py-night-school 建一份小 registry（每课时：title/path/目标/tags/难度/date），既当网站/讲义生成源，又当「源码路标」的总地图；tags 用横切维度（如 py-syntax / agent-loop / tools / evals / finance）
5. **what_makes_documentation_good.md 当讲义写作规范全员必读**：直接采纳其可操作条目——标题写信息句不写抽象名词、结论前置不做苏格拉底式铺垫、"even an expert Java engineer might be a beginner at Python"、绝不示例硬编码 API key（我们练习验收文件里应专门断言这一点）
6. **共享 examples/data/ 式素材库**：建 `py-night-school/data/` 放小型练习资产，直接复用 cookbook 的金融素材起步：`examples/data/NotRealCorp_financial_data.json`（虚构公司季度财报，4.5KB）、`labelled_transactions.csv`、`data/10k/`（Lyft/Uber 真实年报 PDF，适合做 RAG/抽取练习）；遵守其纪律「大数据不进仓，讲义里写获取命令」
7. **每 recipe 自带 requirements.txt**：我们的对照组 mini-agent 与毕业设计各自独立依赖文件（「每个示例只装它需要的」），不追求全仓统一环境——对学员机器更友好，也练 pip 基本功
8. **AGENTS.md 式贡献规范 + CI 校验**：教学仓自己也要 AGENTS.md（结构约定、验收文件命名、notebook 清 execution count）；CI 最低配 = nbformat 格式校验 + pytest 收集练习文件（比 cookbook 多走一步：验执行不只验格式）
9. **Troubleshooting 小节入课时模板**：仿 supply chain 例，六段式的「坑位」段固化成 Quickstart 式三段：现象 → 一行诊断命令 → 修复（如 "Port already in use: lsof -ti:8000 | xargs kill -9"）

## 6. 局限与反例（不适合我们或做得不到位的地方）

1. **无课程性**：没有顺序、没有练习、没有验收——它是查阅型资产。py-night-school 不能照搬其组织（学员会迷路），只能作为延伸层挂在课时末尾；引用时要给「为什么此刻读这篇」的一句导读，不能甩链接
2. **API/版本漂移严重**：老平铺 notebook（How_to_format_inputs_to_ChatGPT_models 等大量 GPT-3/ChatML 时代内容）仍保留在 registry 里，与 Agents SDK 新内容混排；引用前必须逐篇核对是否仍适用于当前 API——延伸池要「验后再引」
3. **不锁版本 + 依赖厂商生态**：requirements 全裸包名；heavy 依赖 OpenAI SDK/托管工具（Code Interpreter、WebSearch、Agents API 沙箱）——学员拿国内模型/本地模型跑不通。我们引用时应优先挑「协议思想」类内容（Orchestrating_agents、reliability 文章），跳过深度绑定托管服务篇
4. **2GB 仓库体积**：数据素材直接进仓导致克隆成本极高，反面印证「大数据不进仓」自己定的规矩执行得不彻底（10k/ 里有 1.4~1.9MB PDF、winemag/ 等整目录数据）。我们的 data/ 应设体积红线（如单文件 <5MB）
5. **平铺与目录双轨造成的历史包袱**：examples/ 根下 85 个松散文件与 35 个主题目录并存，同一主题内容散落两处（如 agent 内容在根 Orchestrating_agents.ipynb、agents_sdk/、agents_api/ 三处）——我们一开始就该目录化，不留平铺区

## 7. 延伸阅读池引用清单（课时「延伸」段最值得引的子集）

| 引用对象 | 本地路径 | 建议挂在哪课 |
|---|---|---|
| Orchestrating_agents.ipynb（无框架手写 agent 循环） | examples/Orchestrating_agents.ipynb | mini-agent 对照组课时（正主） |
| 多 agent 金融组合分析（agent-as-tool + 提示词外置 + 产物样张） | examples/agents_sdk/multi-agent-portfolio-collaboration/ | 金融毕业设计起步课 |
| 无框架可靠性技巧长文（CoT/least-to-most/verifiers） | articles/techniques_to_improve_reliability.md | prompt 工程与评估课 |
| 官方文档写作法 | articles/what_makes_documentation_good.md | 教师侧规范 + 学员写毕设报告前必读 |
| agent 评估与 trace（Langfuse） | examples/agents_sdk/evaluate_agents.ipynb | 评估/可观测课 |
| MCP 工具接入指南 + 全栈 copilot | examples/mcp/mcp_tool_guide.ipynb；examples/mcp/building-a-supply-chain-copilot-with-agent-sdk-and-databricks-mcp/ | 工具接入/MCP 课 |
| 金融练习素材 | examples/data/NotRealCorp_financial_data.json、labelled_transactions.csv、data/10k/ | 练习数据直接复用 |

引用纪律（从本仓自身教训归纳）【推断】：

1. 引用一律带本地路径 + HEAD 快照说明，并给一句"为什么此刻读"的导读（cookbook 自身无课程性，裸链会让学员迷路）
2. 优先引「协议思想」类（Orchestrating_agents、reliability 文章、mcp_tool_guide），少引深度绑定 OpenAI 托管服务/最新模型 API 的篇目（漂移最快）
3. 每次引用前跑一遍该 recipe 的 requirements 并确认 API 仍存在（本仓 CI 只验格式不验执行，保鲜靠人工）
4. 数据素材（NotRealCorp 等）体积小、语义虚构，可直接拷入 py-night-school/data/ 并注明出处，避免让学员克隆 2GB 大仓

（完。本档案所有路径均相对 ~/develop/opensource/openai-cookbook/，未修改被解剖仓库任何文件。）
