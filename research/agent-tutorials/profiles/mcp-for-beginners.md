# mcp-for-beginners 教程解剖档案

> 对象：microsoft/mcp-for-beginners（本地 ~/develop/opensource/mcp-for-beginners，HEAD 2f43408b 2026-09-11；depth-1 完整克隆，含 translations/ 与 translated_images/，本档案仅分析英文源内容）
> 视角：为 py-night-school（Java 工程师 × Python Agent 夜校）提炼课程设计与教学方式启发
> 证据纪律：结论可溯源到本地路径；区分【核心】（实际文件所见）与【推断】（分析判断）；查不到的标 ⚠️ 不臆测

## 1. 定位与形态

- 【核心】Microsoft 出品的 MCP（Model Context Protocol）协议课，README 自述"Learn MCP with Hands-on Code Examples in C#, Java, JavaScript, Rust, Python, and TypeScript"——最大特征是**六语言并行**：每个动手环节同时给 TypeScript/Python/.NET/Java/Rust 五套代码（JavaScript 走 samples 目录）。
- 【核心】形态是"课程树"而非平铺课时：12 个 Module（00–12），Module 3 下挂 15 个子课（3.1–3.15）、Module 5 下挂 17 个专题（5.1–5.17）、Module 11 是 13 个 lab 的毕业项目（PostgreSQL + 零售分析 MCP server），总计约 50 个可读单元。课程表在根 README.md 的巨型 markdown 表格里。
- 【核心】教学内容紧跟协议版本：根 README 明示当前教 MCP Specification 2026-07-28（stateless requests、Extensions 框架、Roots/Sampling/Logging 弃用），并有专文 01-CoreConcepts/mcp-2026-07-28.md 讲版本迁移；部分动手示例仍钉在 2025-11-25 并在课时里用 `> [!NOTE]` 标注。
- 【核心】受众定位写在 README "Prerequisites"：会任一门语言 + 理解 client-server/REST 即可，AI/ML 背景可选——**入口比 ai-agents-for-beginners 低**（不需要云订阅即可跑通 stdio 服务器示例）。
- 【推断】六语言并行是它作为"协议课"的必然选择（协议本身语言无关），但也造成每课 README 极长（01-first-server 1382 行）而每种语言的解释被稀释——对我们只有单语言受众是反面参考。

## 2. 结构总览（关键目录树 + 组织逻辑）

```
mcp-for-beginners/
├── README.md                 # 课程表（Module/Topic/Description/Link 四列大表）+ 样例代码导航
├── study_guide.md            # 学习指南，内嵌 mermaid mindmap 可视化课程地图
├── changelog.md              # 课程变更日志
├── 00-Introduction/          # Module 0：协议概览（README）
├── 01-CoreConcepts/          # Module 1：核心概念 + mcp-2026-07-28.md 版本变更专文
├── 02-Security/              # Module 2：安全（README + samples/cimd-dcr-auth 授权示例）
├── 03-GettingStarted/        # Module 3：01-first-server ~ 15-mcp-apps 共 15 个子课
│     ├── 01-first-server/    #   每课 = README.md + assets/（截图）+ solution/<五语言>/
│     ├── ...
│     └── samples/            #   六语言完整样例项目（csharp/java/javascript/python/rust/typescript）
├── 04-PracticalImplementation/   # Module 4：SDK 实践 + pagination 专题 + samples/（六语言进阶版）
├── 05-AdvancedTopics/        # Module 5：17 个专题子目录（oauth2、routing、scaling、context engineering...）
├── 06~10-*/                  # 社区贡献 / 早期采用经验 / 最佳实践 / 案例 / AITK 工作坊
├── 11-MCPServerHandsOnLabs/  # Module 11：13 个 lab（00-Introduction ~ 12-Best-Practices），全 README
├── 12-tooling/               # Module 12：Copilot App 中用 MCP
├── images/                   # 课程公共图（02-Security、03-GettingStarted、视频缩略图等 46 文件）
├── translations/ + translated_images/   # co-op-translator 生成的 50+ 语言
└── .github/                  # 仅 ISSUE_TEMPLATE，无 workflows（无 CI 验收）
```

- 【核心】两级组织：**Module = 主题域目录**（两位数字），**子课 = Module 内目录或单篇 README**；根 README 的课程表用分组行（"Module 0-3: Fundamentals"）标注学习阶段（Foundation → Building → Growing → Mastery 四阶段，README "Your Learning Path Overview" 节）。
- 【核心】代码组织双轨制：①练习轨——每子课 `solution/<语言>/` 存五语言答案项目（python 只需 server.py+README，java 是完整 Spring Boot 工程）；②样例轨——`03-GettingStarted/samples/` 与 `04-PracticalImplementation/samples/` 各放一套六语言**完整可运行项目**（python 目录 = README + mcp_calculator_server.py + requirements.txt + test_calculator.py）。
- 【核心】无根级 requirements.txt / 无统一环境；Python 侧每个样例目录自带 requirements.txt（`mcp>=2.1.1,<3.0.0`）。
- 【推断】"课时文（怎么一步步做）+ samples（成品参照）+ solution（练习答案）"三层代码冗余是有意为之：课时文教过程、samples 可直接跑、solution 供卡壳对照——代价是同一逻辑三处维护。

### 2.1 课程表结构（Module / 子课主题序列）

【核心】根 README 的 `📚 Complete Curriculum Structure` 表（Module | Topic | Description | Link 四列，用加粗分组行切段）+ `🧭 Your Learning Path Overview` 四阶段叙事，共同构成课程表。实际序列：

| 阶段（README 定义） | Module | 内容 |
|---|---|---|
| Foundation | 00 Introduction / 01 Core Concepts（+1.1 版本变更专文）/ 02 Security（+2.1 CIMD-DCR 授权示例） | 概念：client-server 架构、协议组件、消息模式、传输机制、AI 特有威胁 |
| Building | 03 Getting Started，15 个子课：3.1 first-server → 3.2 client → 3.3 llm-client → 3.4 vscode → 3.5 stdio-server → 3.6 http-streaming → 3.7 AITK → 3.8 testing → 3.9 deployment → 3.10 advanced → 3.11 simple-auth → 3.12 mcp-hosts → 3.13 inspector → 3.14 sampling → 3.15 mcp-apps | 全动手：server/client/LLM 三级递进后铺开传输、测试、部署、认证、宿主配置 |
| Growing | 04 Practical Implementation（+4.1 pagination）/ 05 Advanced Topics，17 个专题：5.1 Azure 集成、5.2 多模态、5.3 OAuth2、5.4 root contexts、5.5 routing、5.6 sampling、5.7 scaling、5.8 security、5.9 web search、5.10/5.11 realtime 流式与搜索、5.12 Entra ID、5.13 Foundry 集成、5.14 context engineering、5.15 自定义传输、5.16 协议特性、5.17 对抗式多 agent | 专题字典：每篇独立短文，彼此基本无前置 |
| Mastery | 06 社区贡献 / 07 早期采用经验 / 08 最佳实践 / 09 案例 / 10 AITK 工作坊 / **11 十三个 lab 的 PostgreSQL 毕业项目** / 12 Copilot App 工具 | 社区与综合应用，11 为 capstone：00 概览 → 01 架构 → 02 安全(RLS) → 03 环境 → 04 数据库 → 05 FastMCP server → 06 工具 → 07 语义搜索(pgvector) → 08 测试 → 09 VS Code → 10 部署 → 11 监控 → 12 最佳实践 |

- 【核心】合计：12 个 Module、约 50 个单元（15 + 17 + 13 个子课/专题/lab + 顶层 Module 若干）；课程表每个条目一行链接，描述一句话。
- 【核心】样本代码另有两张导航表（"Basic MCP Calculator Samples" 与 "Advanced MCP Implementations"，Language | Description | Link）：六语言 × 两难度，均指向 samples/ 目录。
- 【推断】课程表用"分组行 + 四列"承载 50 单元仍可读，靠的是"每行只给一句话描述"的克制；夜校课时少（预计 8–12 课），可用同样的表加两列我们更需要的：前置课与毕设关联点。

## 3. 单课解剖（03-GettingStarted/01-first-server/README.md，1382 行，完整章节结构）

| 章节标题 | 功能 |
|---|---|
| `> [!NOTE]`（课前警示） | 版本提示：本课 Java HTTP 示例用旧 HTTP+SSE 传输、面向 2025-11-25；新项目应走 2026-07-28 Streamable HTTP |
| 导语 + `> TLDR;` | 一段话点破动机："把 tools 放到 server 上，任何客户端都能复用" |
| `## Overview` | 本课做什么（搭环境、建第一个 server/host/test） |
| `## Learning Objectives` | 4 条能力目标（Set up environments / Build servers / Create hosts / Test & debug） |
| `## Setting Up Your MCP Environment` → `### Prerequisites` | 环境/IDE/包管理器/API key 清单 |
| `## Basic MCP Server Structure` | 先给一段完整 TypeScript 参考实现（server+tool+resource+prompt+transport），随后 4 点拆解 |
| `## Testing and Debugging` → `### Using MCP Inspector` | 引入 Inspector 可视化测试工具（配截图） |
| `## Common Setup Issues and Solutions` | 8 行"问题→解法"排错表（连接拒绝/schema 校验/CORS/认证） |
| `## Local Development` | 本地跑 server 的三步 |
| `## Building your first MCP Server` → `### What a server can do` | 承上启下：server 五种能力列表 |
| `## Exercise: Creating a server` | **主练习**，步骤化 `-1-` ~ `-8-`：Create project → Add dependencies → Create project files → Create server code → Adding a tool and a resource → Final code → Test the server → Run using the inspector。**每一步内部按 `#### TypeScript / Python / .NET / Java / Rust` 五个 tab 展开同一操作**；Python 侧从 `touch server.py` 起步，最终代码含 `@mcp.tool()` 与 `@mcp.resource()` 两个装饰器 + `mcp.run()` |
| `### Official SDKs` | 7 个官方 SDK 链接（含 C#/Java/TS/Python/Rust/Kotlin/Swift） |
| `## Key Takeaways` | 3 条要点 |
| `## Samples` | 六语言 calculator 样例链接（指向 samples/ 目录） |
| `## Assignment` | 课外作业，4 步：自选语言实现一个自选 tool → 定义输入输出 → 用 Inspector 验证 → 多组输入测试。**无自动判定**，完成标准是"inspector 里能跑" |
| `## Solution` | 链接 ./solution/README.md（五语言答案目录索引） |
| `## Additional Resources` | 3 个 Azure/官方延伸 |
| `## What's next` | 下一课链接 |

- 【核心】练习形态是"步骤号 + 每步五语言并行"的教程式引导（tutorial-style），不是留白的挑战式练习；02-client 课同样结构（`-1-` ~ `-5-` 步骤），但其 Assignment 更开放（"create a client of your own"，还附一个可改造的 server 底稿）。
- 【核心】02-client 课在 Assignment 与 Solution 之间还有 `## 🎯 Complete Examples` 节，明确区分"solution（对应练习的最小答案）vs complete examples（带完整功能的参照项目）"。
- 【推断】这种 `-N-` 步骤编号 + 语言 tab 的写法可直接降维成单语言版：步骤号即 TODO 骨架，每步的"贴出的代码"改成挖空——天然适配我们的 TODO+pytest 模式。

## 4. 教学机制拆解

### 4.1 练习与验收机制（有没有练习/quiz/作业？完成如何判定？有无自动验证？）

- 【核心】**练习有明确模板**：Getting Started 段 7/9 个子课（01–05、07）含 `## Exercise`（编号步骤引导）+ `## Assignment`（开放作业）+ `solution/`（五语言答案）；09-deployment、08-testing 等后期课无此结构。全仓 **无 quiz**（grep "quiz" 仅命中 translations）。
- 【核心】作业完成判定是**人工/工具可视化验收**："Run the inspector tool to ensure the server works as intended"（01 课 Assignment 第 3 步）——用 MCP Inspector 手动点工具、传参数、看响应，没有自动断言门槛。
- 【核心】唯一的自动化测试样例在 samples：`03-GettingStarted/samples/python/test_calculator.py` 是普通 assert 脚本（非 pytest 收集）：①直接 import 函数断言四则运算；②`test_protocol_discovery()` 用 subprocess 以 JSON-RPC 打真 server 进程，断言 `server/discover` 返回的 `supportedVersions` 含两个协议版本、`tools/list` 恰好等于四个工具名、`initialize` 版本协商回退正确——**这是"协议级集成测试"的好范本**。运行方式 `python test_calculator.py`（main 里手动调两个 test 函数）。
- 【核心】08-testing 课专门讲测试三法：MCP Inspector（可视化）/ Manual（curl/HTTP）/ Unit Testing（给出 pytest + `create_connected_server_and_client_session` 内存连接的代码示例，并链接 python-sdk 官方测试文件）。
- 【核心】仓库无 CI 验收：`.github/` 只有 ISSUE_TEMPLATE，没有 workflows（对照 ai-agents-for-beginners 有 smoke-test.yml）。
- 【推断】它把"怎么测"当教学内容（08 课、test_calculator.py），而不做"替学习者测"（无验收 CI）——py-night-school 应两者兼得：教协议级测试写法 + pytest 自动验收练习。

### 4.2 代码组织（每课独立项目？共享依赖？版本锁定？运行入口？）

- 【核心】六语言各按自身惯例成完整项目：Python = 单文件 + requirements.txt（`pip install "mcp[cli]"`，运行 `mcp run server.py`，调试 `mcp dev server.py` 自动拉起 Inspector）；TypeScript = package.json/tsconfig/src；Java = Spring Boot 3.5 + Spring AI MCP starter（Maven wrapper、Dockerfile、health controller、全局异常处理器俱全——**Java 工程师会感到极度亲切**）；Rust = Cargo 工程；.NET = csproj。
- 【核心】版本锁定只到 SDK 合理下限（python `mcp>=2.1.1,<3.0.0`；TS `@modelcontextprotocol/sdk ^1.16.0`；Java Spring AI 走 BOM）；无全仓统一依赖，无 workspace 机制。
- 【核心】**Python 侧代码怎么跑**（以 calculator 样例为例，03-GettingStarted/samples/python/ 与各课 solution/python/ 同一模式）：
  1. `python -m venv venv` 建虚拟环境（solution/python/README.md 的 `-0-` ~ `-4-` 步骤；推荐 uv 但注明非必须）；
  2. `pip install "mcp[cli]"`（requirements.txt 内容就这一行，带版本区间）；
  3. `mcp run server.py` 启动（`mcp[cli]` 提供的入口，等价 `python server.py`，FastMCP 默认 stdio 传输）；
  4. `mcp dev server.py` 或 `npx @modelcontextprotocol/inspector mcp run server.py` 拉起 Inspector 调试（课时文特别提示 Python 包装的 inspector 不全，建议直接用 Node 版）；
  5. `python test_calculator.py` 跑自带 assert 脚本（函数单测 + 协议级子进程集成测试）。
  服务器本体是**单文件 FastMCP**：`mcp = FastMCP("Demo")` + `@mcp.tool()` / `@mcp.resource("greeting://{name}")` 装饰器 + `if __name__ == "__main__": mcp.run()`——零项目脚手架，Java 工程师对照 Spring Boot 版可直观看到"重框架 vs 轻装饰器"的谱系。
- 【核心】Module 11 的 13 个 lab 是**纯 README 讲义**（如 05-MCP-Server/ 只有一个 README.md，行内贴大段 config.py/sales_analysis.py 代码讲解），实际工程在**外部仓库** `microsoft/MCP-Server-and-PostgreSQL-Sample-Retail`（11-MCPServerHandsOnLabs/README.md 明示"walks you through the following MCP server <链接>"）。
- 【核心】05-AdvancedTopics 下 17 个专题目录也多为单 README + 少量代码文件（如 samples/cimd-dcr-auth 是完整可跑的授权对比示例）。
- 【推断】"讲义仓库与代码仓库分离"（Module 11 模式）适合大型毕业项目：我们毕设若代码量大，可以课程仓只放路标与讲解、代码独立成仓，"源码路标"段直接指过去。

### 4.3 视觉与辅助材料

- 【核心】图片分三处：根 images/ 46 个文件（按 Module 分子目录 02-Security、03-GettingStarted、10-AITK + video-thumbnails/）；课时内 assets/（如 01-first-server/assets/ 4 张 Inspector 操作截图：connect → connected → 工具列表 → 运行结果）；samples 内部自带图（java/calculator/images/tool.png）。全仓非翻译 PNG 约 86 张。
- 【核心】图的内容以**工具操作截图**为主（Inspector 界面、VS Code 配置），概念图集中在 01-CoreConcepts 与 study_guide.md（后者用 mermaid mindmap 画全课程地图，纯文本可维护）。
- 【核心】无手绘 sketchnote；无每课视频（video-thumbnails/ 存在但课程表无 Video 列——与 ai-agents-for-beginners 不同）。根 README 侧提供 "Let's Learn MCP" 四语言视频教程系列的 aka.ms 短链（C#/Java/JS/Python 各一套），作为视频补充的外挂入口而非课时组件。
- 【核心】图片随技术动作走：哪里需要"照着做"，截图就贴到哪里（Inspector 四连、VS Code 配置、Java jar 启动验证）；纯概念章节（Module 1）才出现架构示意图。
- 【推断】"mermaid mindmap 当课程地图"是零美术成本的可视化方案，适合夜校 README；Inspector 四连截图（连接→列表→调用→结果）也是"验收长什么样"的直观教材。

### 4.4 进阶曲线（前置关系、理论实践配比、篇幅节奏）

- 【核心】四阶段曲线由 README 显式声明：Foundation（Module 0–2 概念+安全）→ Building（Module 3 十五个动手子课）→ Growing（Module 4–5 实践+17 专题）→ Mastery（Module 6–11 社区/最佳实践/13-lab 毕业项目）。study_guide.md 再按"不同基础的学习路径"给推荐顺序。
- 【核心】动手比重大：Module 3 的 15 个子课全部 step-by-step；概念只有 Module 0–2 三篇。Module 11 是 capstone（架构→安全→环境→库→server→工具→向量搜索→测试→VS Code→部署→监控→最佳实践，13 lab 复刻真实项目全生命周期）。
- 【核心】单课篇幅方差极大：01-first-server 1382 行（因五语言重复），02-client 约 900+ 行，而 08-testing 不足 150 行；Module 5 专题普遍短文。
- 【核心】课间衔接靠每课尾部 `## What's Next` 链接；Module 3 内部 01 server → 02 client → 03 llm-client（client 逐步变聪明）构成清晰的三步递进；同一个 calculator 例子从 Module 3 一路复用到 Module 4 进阶样例。
- 【核心】先安全后动手的顺序值得注意：Module 2（安全）排在 Module 3（第一个 server）**之前**——协议课把"威胁模型"当作地基而非附录。
- 【推断】"同一个 calculator 例子从 server 一路演化到 client 到 LLM client"是最值得抄的叙事线——我们的毕设 demo 也应让同一个金融例子贯穿：第 N 课手写的工具，第 N+1 课变成 MCP server，第 N+2 课被 mini-agent 调用。

## 5. 对 py-night-school 的可借鉴点（编号列表，每条给具体落地建议）

1. **`-1- -2- -3-` 步骤编号练习骨架**（Exercise 内每步 = 一个可验收动作，最后一步固定是"测试/验证"）：落地：六段式的"动手"段用编号步骤，每步末尾给"预期看到什么"（如 01 课 `-8-` 的 Inspector 四连截图）；再把每步改造成 TODO 挖空，pytest 按步骤粒度断言（test_step1_project_runs ... test_stepN_tool_called）。
2. **Exercise → Assignment → Solution 三层练习结构**（引导式练习 + 开放作业 + 答案分离）：落地：每课练习分两层——课上 TODO（有 pytest 验收）+ 课后 Assignment（开放式、无标准答案，如"给毕设 agent 换一个自己想的工具"）；solution 放独立 solution/ 目录防剧透，Assignment 只给验收要点清单。
3. **Java 对照不是桥接而是平行轨**（本仓 Java 侧是完整 Spring Boot + Spring AI `@Tool` 注解工程，pom.xml/健康检查/异常处理器齐全）：落地：我们的"Java 心智桥"可更进一步——对 tool calling、MCP server 等关键课，直接附最小 Java 对照工程（Spring AI 或裸 HTTP），因为目标学员写得最多的就是这类代码；对照表旁给"同一概念两栏代码"而非只给名词翻译。
4. **协议级集成测试范本**（test_calculator.py：subprocess 启动真 server，JSON-RPC 断言 tools/list 与版本协商）：落地：MCP 课时 pytest 验收直接教这一招——不 mock、拉起学员写的 server 进程，断言工具清单与调用结果；这比纯函数断言更接近"真的能用"。
5. **测试本身作为一课**（3.8 Testing：Inspector 可视化 / curl 手动 / pytest+内存会话三法并举）：落地：课时表里给"怎么验收 agent"留专门一课（Inspector、pytest、契约测试三工具），与我们的 pytest 验收机制互相印证——学员最终能自己给毕设写测试。
6. **版本时间线教学**（根 README 声明教的协议版本 + mcp-2026-07-28.md 迁移专文 + 课时 `> [!NOTE]` 标注旧版本示例）：落地：课程 README 钉死"本课基于 SDK X.Y / 协议 Z"，过时风险处用 NOTE 提示框；教 Java 工程师把"依赖版本治理"的敏感度迁移到快速变动的 agent 生态。
7. **mermaid mindmap 课程地图**（study_guide.md 零图片成本画全课结构）：落地：课程 README 顶部放一张 mermaid mindmap/mindmap+表格双视图，标注哪些课是毕设关键路径。
8. **讲义仓与毕设代码仓分离 + 路标**（Module 11 的 13 lab 全是 README、代码在外部仓库）：落地：金融毕设代码独立目录/仓库，课程内"源码路标"段给精确到文件与函数的阅读顺序（Module 11 每个 lab 头部都有 "What This Lab Covers" 索引段可参考）。

## 6. 局限与反例（不适合我们或做得不到位的地方）

- 【核心】无自动验收、无 CI：练习完成与否全靠学员自觉用 Inspector 目测；solution 无保护也无判定。我们的 TODO+pytest 是必须自建的部分，此仓无先例可抄（test_calculator.py 的写法除外）。
- 【核心】五语言并行使单课 README 膨胀到 1382 行，同一步骤五遍重复，读者扫读成本高；且各语言深浅不一（Java 段包含生产级组件，Python 段只有 10 行）——单语言课程绝不应模仿这种排版，应学其"步骤骨架"而弃其"语言 tab"。
- 【核心】结构不一致：Module 3 子课有完整 Exercise/Assignment/Solution，Module 5 专题与 Module 11 lab 多为单篇长文无练习；09-deployment 等课连 solution 也没有。课时模板纪律性明显弱于 ai-agents-for-beginners 的三件套恒定结构。
- 【核心】Module 11 毕业项目代码在外部仓库且 lab 讲义内嵌大段与该仓库耦合的代码副本，仓库内无法独立运行验证（本地只见 README）——"源码路标"若失效（外链改动）会双倍维护成本；我们若采用路标模式，路标应含精确 commit/文件锚点。
- 【核心】`[!NOTE]` 承认部分示例仍钉在旧协议版本（2025-11-25 的 HTTP+SSE），协议快速演进导致课程自身内容有版本分裂——提醒我们课程内嵌代码要尽量贴近"稳定 API 子集"，并把易变部分隔离到第 0 课的环境配置里。
- 【核心】大量情绪化励志文案（"every expert was once a beginner"、"Let's build something amazing together"）占据 README 显著篇幅；对在职工程师夜校受众，这类文字应压缩为冷静的路径说明。
- ⚠️ translations/ 与 translated_images/ 虽在本克隆中存在，但其译文质量未逐语言核查，不作评价。
