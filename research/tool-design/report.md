# 业务 API 包装为 Agent Tool 的设计实践调研

> 2026-10-28 · 网络调研 · 入口见 [README.md](README.md)。证据等级：【一手】官方原文全文抓取 /【转述】第三方转述 /【摘要】仅搜索摘要 /【未找到】。

## 0. 结论速览

1. **业界高度共识：不要把业务 API 1:1 暴露成 tool。** 所有权威来源的第一条原则都是"面向结果（outcome）而非操作（operation）"——AWS 把 1:1 REST 透传明确定义为基线反模式，Anthropic 明说"常见错误是不管适不适合 agent 就把现有 API 端点包一层"。
2. **Tool 设计本质是上下文工程（context engineering），不是 API 设计。** 两大失败模式（AWS 总结）：bloat（tool 定义和返回值每轮都占上下文，把窗口撑爆）与 confusion（工具太多/名字歧义，模型选错、填错，重试又加剧 bloat）。给描述加料能治 confusion 但加重 bloat——所有设计决策都是在这条轴上找平衡。
3. **描述（description）就是 prompt 工程。** Anthropic 的两个实锤：仅靠精修 tool description 让 Claude Sonnet 3.5 达到 SWE-bench Verified SOTA；修一句 web search 的描述文案就消掉了模型多余拼 "2025" 的行为。
4. **有现成的渐进改造阶梯。** AWS 博文用同一个真实 API 做了 V1→V6 六个版本演进实验（V1 裸透传 → V3 改名/枚举/默认值 → V4 懒加载 → V5 服务端挂小模型 → V6 agent-as-tool），每级都有取舍数据，是工程上最可操作的一篇。
5. **写操作安全是治理重点。** Stripe 官方 MCP server 的做法是"变更类工具 opt-in、默认只读"；MCP tool annotations 标注 destructive；返回值全量 PII 脱敏。
6. **Evals 驱动 + 用 agent 改 tool。** Anthropic 的方法论闭环：评测任务要贴近真实复杂度（几十次 tool 调用），指标除准确率外看 token 消耗 / 调用次数 / 错误数，并把评测 transcript 喂回 Claude Code 批量重构 tool。
7. **跨大厂高度收敛，学术侧有量化背书。** Google 官方口径"活跃工具集 10~20 个"、Azure 硬限"工具描述 ≤1024 字符"、GitHub 用工程博客公开"合并工具省上下文"的改造；安全主张（最小权限 / 写操作确认 / opt-in）三家一致。学术基准 RoTBench 实测工具描述被扰动后调用成功率骤降，TAU-bench 的 pass^k 指标把"可靠性"推成第一指标。

## 1. 权威来源总表

| # | 来源 | 类型 | 证据 | 核心贡献 |
|---|---|---|---|---|
| 1 | [Anthropic Engineering《Writing effective tools for agents》](https://www.anthropic.com/engineering/writing-tools-for-agents)（2025-09） | 官方·一手 | 【一手】 | 最系统的 tool 设计指南：选型、命名空间、参数、返回值、描述、evals、用 agent 写 tool |
| 2 | [AWS ML Blog《MCP tool design: Practical approaches and tradeoffs》](https://aws.amazon.com/blogs/machine-learning/mcp-tool-design-practical-approaches-and-tradeoffs/) | 厂商·一手 | 【一手】 | 同一 API 的 V1~V6 六版本演进实验；bloat/confusion 两难框架；85% token 降减数据 |
| 3 | [philschmid.de《MCP is Not the Problem, It's your Server》](https://www.philschmid.de/mcp-best-practices) | 一线工程师·一手 | 【一手】 | 六条最佳实践：outcome 优先 / 参数扁平 / 描述即上下文 / 无情裁剪 / 命名可发现 / 分页 |
| 4 | [OpenAI《A Practical Guide to Building Agents》](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)（2025） | 官方 | 【转述】 | agent 定义；三类 tool（function calling / 定义型工具 / agents-as-tools）；自描述契约；从简单开始 |
| 5 | [Anthropic《Building Effective Agents》](https://www.anthropic.com/engineering/building-effective-agents)（2024-12） | 官方 | 【转述】 | 工具描述="给初级开发者写一份出色的 docstring"；workflow vs agent 演进路径 |
| 6 | [MCP 官方教程《Writing Effective Tools for Agents》](https://modelcontextprotocol.io/docs/tutorials/writing-effective-tools) | 官方 | 【摘要】 | #1 的官方教程化版本（MCP 视角） |
| 7 | [awslabs/mcp DESIGN_GUIDELINES.md](https://github.com/awslabs/mcp/blob/main/DESIGN_GUIDELINES.md) | 厂商·官方风格 | 【摘要】 | 面向动作的命名、全限定名 <64 字符等硬性规范 |
| 8 | [Speakeasy《Design MCP tools》](https://www.speakeasy.com/mcp/tool-design) | 工具厂商 | 【摘要】 | 工具选择/组织/命名以降低 LLM 困惑与上下文占用 |
| 9 | [Stripe 官方 MCP](https://docs.stripe.com/agents)（+[第三方拆解](https://www.developersdigest.tech/library/mcp/stripe)） | 厂商实践 | 【转述】 | 变更类工具 opt-in、默认只读安全暴露 |
| 10 | [udaykapur《Building a Hardened Stripe MCP Server》](https://udaykapur.com/work/stripe-mcp-server) | 一线工程师 | 【摘要】 | 52 tools / 8 域 + 全响应 PII 脱敏的加固实践 |
| 11 | [Shopify Engineering《MCP UI》](https://shopify.engineering/mcp-ui-breaking-the-text-wall)（2025-08） | 厂商实践 | 【摘要】 | 超越文本：tool 返回交互式 UI 组件（另一条减 token 路线） |
| 12 | [Itential《Designing MCP Servers That Don't Become a New Mess》](https://www.itential.com/resource/blog/designing-mcp-servers-for-infrastructure) | 厂商实践 | 【摘要】 | outcome 优先 / 受控暴露面 / 限界上下文 / 提示词纪律 |
| 13 | [arXiv《MCP Tool Descriptions》](https://arxiv.org/html/2602.14878v3) | 学术 | 【摘要】 | 对 MCP 输入 schema、参数命名、工具描述的实证分析 |
| 14 | [Anthropic《Effective context engineering for AI agents》](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)、《The "think" tool》 | 官方·延伸 | 【转述】 | tool 返回值治理 / 长工具链中的思考工具，tool 设计的上下文侧延伸 |
| 15 | [Google《Function calling with the Gemini API》官方文档](https://ai.google.dev/gemini-api/docs/function-calling) | 官方·一手 | 【一手】 | 官方最佳实践：工具集 10~20 个上限、强类型、tool_choice 模式、远端 MCP 约束（Streamable HTTP、snake_case） |
| 16 | [Microsoft《How to use function calling》Azure AI Foundry 文档](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/function-calling) | 官方·一手 | 【一手】 | 参数描述带值格式示例、系统提示协同、描述 ≤1024 字符硬限、负责任使用五条（校验/最小权限/确认步） |
| 17 | [GitHub《A practical guide on how to use the GitHub MCP Server》](https://github.blog/ai-and-ml/generative-ai/a-practical-guide-on-how-to-use-the-github-mcp-server)（2025-07）+ [github-mcp-server 仓库](https://github.com/github/github-mcp-server) | 厂商·一手实践 | 【摘要】 | toolset 分组（repos/issues/PRs/…）+ 按需启用（`GITHUB_TOOLSETS`、`X-MCP-Tools` 头）；OAuth 2.1 + PKCE |
| 18 | [GitHub《How we're making GitHub Copilot smarter with fewer tools》](https://github.blog/ai-and-ml/github-copilot/how-were-making-github-copilot-smarter-with-fewer-tools)（2025-11） | 厂商·一手实践 | 【摘要】 | 官方改造实录：把多个细粒度 MCP 工具合并为更少的多功能工具以省上下文 |
| 19 | [BFCL（Berkeley Function Calling Leaderboard）](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard/blob/735ca8a49af0327066c27ac95cf4862970124537/README.md)（Gorilla 团队） | 学术/评测 | 【摘要】 | 函数调用能力的事实标准公开榜 |
| 20 | [ToolLLM / ToolBench（arXiv 2307.16789）](https://arxiv.org/html/2307.16789v2) | 学术 | 【摘要】 | 大规模 API 工具指令微调数据集 + API 检索器 |
| 21 | [API-Bank（arXiv 2304.08244）](https://arxiv.org/abs/2304.08244) | 学术 | 【摘要】 | 73 个 API 的分层评测（调用/检索/规划） |
| 22 | [TAU-bench / τ²-bench（Sierra）](https://github.com/sierra-research/tau-bench)（[τ² 说明](https://evalscope.readthedocs.io/en/v1.5.0/benchmarks/tau2_bench.html)、[Toloka 扩展](https://toloka.ai/datasets/tau-bench-dataset-extension)） | 学术+工业 | 【摘要】 | 最贴近业务场景：真实 API+政策文档+模拟用户；pass^k 可靠性指标 |
| 23 | [ToolSandbox（Apple）](https://huggingface.co/datasets/apple/ToolSandbox) | 学术 | 【摘要】 | 有状态、多轮对话式工具使用评测 |
| 24 | [StableToolBench / MirrorAPI](https://www.researchgate.net/publication/390213764_StableToolBench-MirrorAPI_Modeling_Tool_Environments_as_Mirrors_of_7000_Real-World_APIs) | 学术 | 【摘要】 | 7000 真实 API 镜像环境，解决基准不稳定 |
| 25 | [RoTBench](https://openreview.net/forum?id=zVI3qVofDk) | 学术 | 【摘要】 | 工具文档扰动鲁棒性评测——描述质量与调用成功率的量化关系 |
| 26 | [LangChain《How to build an agent》](https://www.langchain.com/blog/how-to-build-an-agent)（+社区综述转述） | 框架生态 | 【转述】 | verb-noun 命名、起步限制工具数、显式测试工具选择准确率 |
| 27 | [Neo4j《How AI agents use tools and MCP》](https://neo4j.com/blog/agentic-ai/agent-tools)（2026-05） | 社区 | 【摘要】 | 工具类型/选择机制/MCP 集成的系统讲解，适合当团队入门读物 |
| 28 | [Cloudflare：Agents SDK 建 MCP server](https://community.cloudflare.com/t/agents-workers-build-mcp-servers-with-the-agents-sdk/819613)（2025-07） | 厂商 | 【摘要】 | Workers 上建远程 MCP server 的官方路径 |
| 29 | [Google ADK 官方文档](https://adk.dev/agents/llm-agents)（+[《Add Real-World Tools》](https://medium.com/google-cloud/teaching-your-adk-agent-to-do-more-add-real-world-tools-1d729605a0e6)） | 官方·框架 | 【摘要】 | 不要只罗列工具，要在指令里解释"何时、为何用"；AgentTool 组合模式 |

## 2. 十条核心原则（合并各家，每条注明出处）

### P1. 面向结果，不面向操作（Outcomes, not operations）★第一原则

- 拒绝 1:1 REST 映射：AWS 将其定义为基线反模式（14 个内部命名参数 + 一行 docstring，模型靠猜枚举值、拿到空结果无诊断、重试烧上下文）；philschmid 原则 1；Anthropic"常见错误是无差别包装现有端点"。
- **把多步工作流合并进单一 tool**（Anthropic）：`list_users` + `list_events` + `create_event` → 一个 `schedule_event`（内部查空闲+订位）；`get_customer_by_id` + `list_transactions` + `list_notes` → 一个 `get_customer_context`。
- **按模型的使用方式封装**（philschmid）：三个原子工具 `get_user_by_email` / `list_orders` / `get_order_status` → 一个 `track_latest_order(email)`；编排发生在你的服务端代码里，而不是模型的上下文窗口里。
- **给模型的"认知负担"让路**（Anthropic 通讯录案例）：不要 `list_contacts` 全量返回让模型逐个扫，直接给 `search_contacts` / `message_contact`——agent 的上下文是稀缺资源，工具要规避暴力枚举。
- **反例**（philschmid Gmail 案例）：暴露原始 Gmail API 意味着模型要自己拼 base64 编码的 MIME 消息、解析嵌套 `payload.body.data`。正确做法是 `gmail_search(query, limit)` / `gmail_read(message_id)` / `gmail_send(to, subject, body, reply_to_id)`。

### P2. 粒度是平衡术，暴露面要无情裁剪

- 两个方向都会翻车：太细 → 多次往返、每跳都是错误机会（AWS / Anthropic）；太多太像 → 模型选错工具，重试加剧上下文膨胀（AWS confusion）。
- 单 server 5~15 个 tool、"一个 server 一件事"、按 persona 拆分（admin server / user server）、没人用的 tool 直接下架（philschmid 原则 4；Itential 同）。
- 把多用途工具拆成职责单一的工具也是合法方向（AWS：`search` 与 `get_resource_detail` 拆开后各自响应简洁、定位清晰）——拆还是并，判据是"模型一次调用能不能拿到做决策所需的最小完整信息"。

### P3. 命名要为"可发现性"服务

- 模式 `{service}_{action}_{resource}`：`slack_send_message`、`linear_list_issues`、`sentry_get_error_details`（philschmid 原则 5）。裸名 `create_issue` / `send_message` 在多 server 并存时让模型猜。
- **参数名去内部黑话**（AWS V3）：`discipline` → `subject`、`content_bucket` → `resource_class`——值域也要让模型看得懂（'Student Resource' 自解释）。
- namespacing 用前缀还是后缀、按服务分组还是按资源分组，对 eval 结果有"非平凡影响"，但方向因模型而异——**用自己的评测定，别抄别人结论**（Anthropic）。注意 MCP 客户端有时会自动加 server 名前缀。
- awslabs 规范（摘要级）：动作导向命名、全限定名 <64 字符。

### P4. 参数扁平、受限、带默认值

- **扁平顶层原始类型**，拒绝嵌套 dict / 配置对象：`search_orders(filters: dict)` 会让模型猜结构、幻觉键名（philschmid 原则 2）。
- **枚举约束**：用 Literal / enum 把合法值写进 schema 本身——比长篇描述更省 token 且更准（AWS V3：schema 即约束）。
- **默认值 = 最常见取值**（AWS V3）：`structure='Asset'`、`language='en'`，模型只声明差异项；返回里带 `defaults_applied` 让模型知道发生了什么。
- **参数个数控制在 ~8 个以内**（AWS 引用其 Prescriptive Guidance）；删掉低频和"模型不友好"字段。
- 加 `response_format` 档位参数（DETAILED / CONCISE）让模型自己控制详略（Anthropic：Slack 案例简洁档 ~1/3 token，72 vs 206）。

### P5. 描述就是 prompt 工程

- 心法：当成**给团队新同事写 onboarding 文档**（Anthropic）/"给初级开发者写出色的 docstring"（Building Effective Agents）——把隐性知识（查询格式、领域黑话、资源间关系）显式写进描述。
- docstring 三要素（philschmid 原则 3）：何时用我（"用户询问订单状态时"）、参数格式（"邮箱必须小写"）、返回什么。
- **改文案有大效果**（Anthropic 实锤）：精修 tool description → Sonnet 3.5 SWE-bench Verified SOTA；模型给搜索查询多余拼 "2025" → 改描述即修复。
- 描述还能承载行为引导：截断提示里写"请收窄查询/分多次小查询"而不是干巴巴一句 truncated。

### P6. 返回值：高信号、可裁剪、可链式

- **字段取舍**（Anthropic）：返回 `name` / `image_url` 而不是 `uuid` / `256px_image_url` / `mime_type`——先给模型能直接行动的信息。
- **ID → 自然语言**：把 UUID 翻译成名字 / 0 起始序号能显著提升检索精度、减少幻觉；但保留 ID 供链式调用（`search_user(name='jane')` → `send_message(id=12345)`）——详细档位里留着，简洁档位里藏起来。
- **默认裁剪到决策相关字段**（AWS：50 字段 → 5 字段；Anthropic 数据：按需详细视图约省 2/3 token）。
- **分页是一等公民**（philschmid 原则 6）：`limit` 默认 20~50，返回 `has_more` / `next_offset` / `total_count`。
- **给返回设 token 上限**：Claude Code 默认单次工具返回 25,000 token 截断（Anthropic）。
- 返回格式（XML / JSON / Markdown）没有银弹，模型各有偏好，**用自家 eval 定**（Anthropic）。
- 另一条路线（Shopify MCP UI）：tool 返回交互式 UI 组件而非长文本，"打破文本墙"（摘要级）。

### P7. 错误信息要能指导下一步动作

- 错误返回是"可行动的字符串"，不是异常栈或数字错误码（philschmid 原则 3）：
  - 好：`User not found. Please try searching by email address instead.` / `search requires 2 or more terms in query`
  - 坏：抛异常、`{"code": 40012}`、干巴巴 `no results`（模型只能瞎猜或放弃，AWS）。
- 本质：错误信息也是 prompt——它是模型下一轮重试时读到的"提示词"。

### P8. 上下文是预算，懒加载是手段

- **bloat 与 confusion 的两难**（AWS）：描述加厚治 confusion 但加重 bloat；tool 定义不管用不用都每轮占上下文，多个 server 叠加可能在用户开口前就把窗口吃掉大半（"context rot"）。
- **懒加载**（AWS V4）：把大枚举表 / 分类体系挪到按需调用的 `get_taxonomy` 工具后面，常用值留 hint——Anthropic 数据：按需加载最多省 85% token。
- 截断消息本身也要写成引导（见 P5）。

### P9. 安全与治理

- **写操作 opt-in**（Stripe 官方实践，转述级）：变更类工具默认关闭，只读默认安全暴露——这是"暴露面分级"的标杆做法。
- **MCP tool annotations** 标注 destructive / open-world 等属性，供客户端（和网关）做策略（Anthropic；Shopify 生态也在推）。
- **PII 脱敏**：返回值层面全量脱敏的加固实践（udaykapur hardened Stripe server，摘要级）。
- **按 persona 拆 server** 本身就是权限边界（philschmid：admin / user 分家）。
- 映射到我们的场景：哪些 tool 能过公司网关、什么身份、什么审计粒度，属于 tool 设计的一部分而非事后补丁。

### P10. Evals 驱动，让 agent 参与写 tool

- **任务要贴近真实复杂度**（Anthropic）：好任务需要几十次 tool 调用（"为客户 9182 调查三重扣款并查是否波及他人"），坏任务是单次查询（"搜一个日志 ID"）。
- **验证器从宽到严**：精确匹配 → LLM-as-judge；验证器别太严，拒绝合法的等价表述；可声明期望的 tool 调用序列但别限定策略。
- **指标不止准确率**：运行时长、tool 调用次数、token 消耗、工具错误数——冗余调用多说明分页/limit 设计有问题，参数错误多说明描述要改（Anthropic）。
- **held-out 测试集**防过拟合；评测 agent 让它先输出推理再给结论（CoT 加成）。
- **用 agent 优化 tool**（Anthropic 的元实践）：把评测 transcript 整段喂给 Claude Code，批量重构一批 tool 的命名/描述/参数使其自洽；分析时"agent 没说什么"比"说了什么"更重要，要读原始 transcript 而非只看 CoT。

## 3. 重点原文详述

### 3.1【一手】Anthropic《Writing effective tools for agents》

官方工程博客（2025-09），标题副题是 "with agents"——Anthropic 自己的 tool（Slack、Asana 内部工具）就是用 Claude Code 对着内部工作流的评测迭代优化出来的。除 §2 已提炼的内容外，值得单独记录的点：

- 工具选择的判据是"agent affordances"（agent 的认知特性）：上下文有限、不能暴力枚举、会把计算成本转嫁到多次调用上。
- 原型验证路径：把 API 文档（`llms.txt`）+ MCP SDK 文档喂给 Claude Code，让它先包一版本地 MCP server（`claude mcp add`），再靠 eval 迭代。
- 底层哲学收尾：**tool 是确定性系统与非确定性 agent 之间的契约，设计方式应当与传统 API 不同**；好工具清晰定义、节俭用上下文、能组合进多样工作流、且"连人用起来都觉得直观"。

### 3.2【一手】AWS ML Blog 六版本演进实验

同一真实 API（教育资源的 14 参数查询接口）从裸透传一路改到 agent-as-tool，是最可操作的改造阶梯：

| 版本 | 做法 | 收益 | 代价 |
|---|---|---|---|
| V1 | 裸 REST 透传 | 定义最小 | 模型猜枚举值→空结果→重试烧上下文，"低基线成本是幻觉" |
| V2 | 描述加厚（合法值、同义词映射） | 准确率↑ | 定义变大，bloat↑ |
| V3 | 参数改名（去黑话）+ enum + 默认值 | 准确率↑ 且定义反而变小 | 需要改 schema |
| V4 | 结构重组 + 分类表懒加载（`get_taxonomy` 按需取） | 基线最瘦 | 多一次往返 |
| V5 | 服务端挂小模型（Nova 2 Lite）做意图内省 | 扛自然语言歧义 | 付推理成本 |
| V6 | agent-as-tool（Strands Agent 在服务端编排） | 控制力/一致性最强 | 成本与延迟最高 |

- V5/V6 有个被低估的优点：**服务端自选模型，prompt 工程和 golden-query 测试变得可靠，客户端换模型行为不漂移**——对"公司网关后面客户端模型不可控"的场景有特殊价值。
- 选型判据：字段数、词表稳定性、延迟预算、跨客户端一致性需求。V2 是不动结构的最快改进；V4 最瘦；V5 扛歧义；V6 要控制力。

### 3.3【一手】philschmid 六条最佳实践

`Outcomes not operations` / `Flatten your arguments` / `Instructions are context` / `Curate ruthlessly` / `Name tools for discovery` / `Paginate large results`——内容已并入 §2 各原则，其 Gmail 正反例（base64 MIME vs 扁平四工具）是给团队做培训时最好用的教学素材。

### 3.4【转述】OpenAI《A Practical Guide to Building Agents》

34 页官方 PDF（本机无法直接解析 PDF，以下为转述级）：

- agent = LLM + 工具 + 指令，自主完成多步任务；**从最简单的形态起步**（单 LLM + tools），编排/管理者模式按需再加。
- 三类工具：function calling（自定义 API）、定义型工具（如 web search / file search 这类平台内置）、**agents-as-tools**（把另一个 agent 当工具——与 AWS V6 呼应）。
- 工具三件套（名称 / 描述 / 参数 schema）必须自描述、自足，让模型不靠外部文档就能正确调用。

### 3.5 其他业界实践速览

- **awslabs/mcp DESIGN_GUIDELINES**（摘要）：硬性编码规范风格——动作导向命名、全限定名 <64 字符。
- **Speakeasy**（摘要）：以"降低 LLM 困惑 + 降上下文占用"为目标的工具选择/组织/命名指南（商业 MCP 工具链厂商）。
- **Stripe**（转述）：官方 MCP server 只读默认安全、变更类 opt-in；hosted 与本地两种形态。
- **Shopify**（摘要）：Dev MCP（无鉴权的文档语义层）之外，工程博客探索 MCP UI——tool 返回交互组件，是"压缩返回值"的另一条路线。
- **arXiv 2602.14878**（摘要）：对 MCP 工具描述/参数命名的实证分析，学术侧印证上述工程经验。

### 3.6【一手】Google《Function calling with the Gemini API》官方文档

- 官方最佳实践清单：描述清晰具体；命名描述性强、无空格与特殊字符；**强类型**（integer / string / enum，别全用 string）；**活跃工具集上限 10~20 个**（Google 给出的量化口径，与 philschmid 的 5~15 同量级）；先校验再执行；健壮的错误处理；外部 API 要鉴权。
- `tool_choice` 模式（AUTO / ANY / NONE / VALIDATED）+ `allowed_tools` 白名单——**客户端侧的暴露面分级机制**，与 Stripe 的"写操作 opt-in"是同一思想的两种实现位置。
- 远端 MCP 直接作为工具接入 Gemini：`name/url/headers/allowed_tools`；硬约束：只支持 Streamable HTTP（不支持 SSE）、server 名必须 snake_case（不能带 `-`）——接公司网关前值得逐条问清这类协议细节。
- 一个有趣的官方排坑：让模型在调工具前先输出结构化文本（如 XML 工作笔记）会触发 Malformed_Function_Call；Google 推荐的解法是**把工作笔记包成一个专用函数调用**（`update(previous_step, plan, next_step, external)`）——与 Anthropic 的 "think" tool 同构异名。

### 3.7【一手】Microsoft《How to use function calling》Azure AI Foundry 文档

- 参数描述要带**值格式与示例**：`location` 的描述写 "Seattle, WA or Miami, FL"（城市+州缩写）——"描述里写格式"是官方口径。
- 系统提示与工具协同：明确"用户问找酒店时调用 search_hotels"；要求模型主动追问澄清（"Don't make assumptions about the values to insert"）；幻觉调用抑制语 "Only use the functions you have been provided with"。
- **硬约束：工具/函数描述上限 1024 字符**（Azure OpenAI）——描述预算是真实存在的，AWS 的"描述加厚 vs 定义膨胀"两难在 MS 这里有硬顶。
- 负责任使用五条：每次调用前校验；只用可信数据与工具（工具输出可被注入污染）；**最小权限**（官方举例数据库场景"只给只读"，且明说"不能依赖'没提供某函数'当安全边界"）；考虑真实世界影响；**执行类工具加用户确认步骤**。与 Stripe opt-in、MCP annotations 三方收敛。

### 3.8 GitHub：toolset 分组与"更少的工具"（官方实践，摘要级）

- **[GitHub MCP Server](https://github.com/github/github-mcp-server) 的 toolset 设计**：工具按域分组（repos / issues / pull_requests / notifications / discussions…），默认只开最小集，用 `GITHUB_TOOLSETS=repos,pull_requests` 按需启用，2025-12 又加了 `X-MCP-Tools` 请求头做到单次会话级挑选——**"全量能力注册 + 按需小暴露面"** 的标杆实现，正好对应 §2 P2/P8 的懒加载思想。
- **[《How we're making GitHub Copilot smarter with fewer tools》](https://github.blog/ai-and-ml/github-copilot/how-were-making-github-copilot-smarter-with-fewer-tools)（2025-11）**：GitHub 自己的改造实录——把多个细粒度 MCP 工具**合并为更少的多功能工具**以省上下文。这是对"拆细 vs 合粗"平衡的最新一线数据点：连 GitHub 也在往"合并"方向回调。
- 远程 server 2025-09 GA：OAuth 2.1 + PKCE——企业级 MCP 的鉴权基线参考。

### 3.9 学术与评测基准（摘要级）

经典工具学习数据集/基准：ToolBench/ToolLLM（大规模真实 API 指令数据）、API-Bank（73 API 分层评测）、StableToolBench/MirrorAPI（7000 真实 API 镜像，解决基准不稳定）、BFCL（函数调用事实标准榜，Gorilla 团队）。

对"业务 API 包装成 tool"最有参考价值的三个：

- **TAU-bench / τ²-bench（Sierra）**：形态与我们的场景最像——航空/零售客服域，给模型真实 API 工具 + 业务政策文档 + 模拟用户，考察政策遵从；提出 **pass^k** 指标（k 次全过才算过）专测可靠性，比平均准确率更贴近生产要求。
- **RoTBench**：系统性扰动工具文档（删描述、改值域、注入噪声）测鲁棒性——用数据实锤"描述质量直接决定调用成功率"，为 P5"描述即 prompt 工程"提供学术背书。
- **Apple ToolSandbox**：有状态、多轮对话式工具使用评测（中间态依赖、隐式状态推理）。

对我们的意义：评测基建不必全部自研——TAU-bench 的"真实 API + 政策 + 模拟用户 + pass^k"模式可以直接抄成公司网关接入的评测框架。

### 3.10 框架生态与社区（摘要/转述）

- **LangChain**（转述）：[《How to build an agent》](https://www.langchain.com/blog/how-to-build-an-agent)（2025-07）从想法到生产；社区综述提炼的实践——verb-noun 命名、起步阶段限制工具数（3~5）、显式测试工具选择准确率。
- **Google ADK**（摘要）：[官方文档](https://adk.dev/agents/llm-agents)明确"不要只罗列工具，要在指令里解释何时、为何用"；AgentTool（把一个 agent 当另一个 agent 的工具）是官方推荐的组合模式——与 AWS V6 / OpenAI agents-as-tools 呼应。
- **Neo4j**（摘要）：[《How AI agents use tools and MCP》](https://neo4j.com/blog/agentic-ai/agent-tools)（2026-05）系统讲解工具类型/选择机制/MCP 集成，适合当团队入门读物。
- **Cloudflare**（摘要）：[Agents SDK 在 Workers 上建远程 MCP server](https://community.cloudflare.com/t/agents-workers-build-mcp-servers-with-the-agents-sdk/819613) 的官方路径。
- 【未找到】社区口口相传的 varun.ca《MCP tool design》个人经典文章本轮检索未命中（site 限定检索为空），不作引用。

## 4. 映射到我们的场景（Java 业务系统 + 公司统一 Python MCP 网关）

结合本轮调研与前几轮讨论的架构（Python 薄接入层 = 唯一 MCP；Java 侧普通内部 REST），这套原则的落点非常清晰：

1. **职责分层**：Java 内部 API 扮演"V1 原语"角色（细粒度、面向程序）；Python 接入层负责 V2/V3/V4 的全部改造——场景粒度封装（P1）、参数扁平化与去黑话（P3/P4）、返回裁剪与分页（P6）、可行动的错误翻译（P7）。**这正是那个 Python 薄层存在的工程理由。**
2. **从 top 场景倒推 tool 清单**（呼应上轮结论）：每个场景一个 outcome 粒度的 tool，控制总量在 5~15 个；用一张评审表管理：`tool 名 / 何时用（description 三要素）/ 参数（枚举+默认）/ 返回字段 / 错误文案 / 权限级别（读/写/需确认）/ 审计`。
3. **渐进策略**：OpenAPI 自动生成当脚手架（V1），立刻做 V3（改名 + enum + 默认值）——这步收益/成本比最高；枚举表大的域（类目、状态机）上 V4 懒加载。V5/V6 默认不碰；唯一例外是网关后面客户端模型不可控且某域歧义极大时，可考虑个别 tool 用 V5 换确定性。
4. **安全基线抄 Stripe 作业**：默认只读，变更类工具逐个 opt-in + 审计 + 身份透传校验；返回值脱敏在 Python 层统一做（这也避免了 Java 侧为 agent 特殊改造）。
5. **评测先行**：每个场景 tool 上线前配 3~5 个真实复杂度的评测任务（多工具链），记录 token / 调用数 / 错误数基线；把网关联调的 transcript 攒下来喂给 agent 批量优化描述（P10 闭环）。
6. **量化口径可直接当验收标准**：单 agent 活跃工具数（Google ≤10~20 / philschmid 5~15）；描述预算（Azure ≤1024 字符——先问公司网关有没有类似硬限）；命名规范（snake_case、无连字符——Gemini 远端 MCP 连 `-` 都不允许）；工具暴露面用 GitHub toolset 模式做"全量注册 + 按需启用"。
7. **评测框架抄 TAU-bench 作业**：真实业务 API + 政策文档 + 模拟用户 + pass^k 可靠性指标——这套形态就是为"业务系统 + 客服政策"设计的，可直接映射到我们的场景。

## 5. 延伸阅读（与本主题相邻）

- [Anthropic《Effective context engineering for AI agents》](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)——tool 返回值治理的上下文工程总纲。
- [Anthropic《The "think" tool》](https://www.anthropic.com/engineering/think-tool)（原 e-phor 效仿帖的官方出处方向）——长工具链中给模型显式思考位。
- [Anthropic《Equipping agents for the real world with Agent Skills》](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world)——tool 之外的第二种能力暴露形态（Skills）。
- [Reddit r/mcp《Good/proper MCP design》](https://www.reddit.com/r/mcp/comments/1s63dgo/goodproper_mcp_design)——社区实践讨论。
- [Medium《The MCP Revolution: Tool Granularity》](https://medium.com/@pyneuronaut/the-mcp-revolution-how-tool-granularity-can-make-or-break-your-ais-performance-and-cost-d9b5a66182b3)——粒度专题长文。

## 6. 证据与复核记录

第一轮（Anthropic / OpenAI / AWS / 社区）：

- 【一手】3 篇：Anthropic engineering（全文抓取成功）、AWS ML Blog（全文抓取成功）、philschmid.de（全文抓取成功）。
- 【转述】OpenAI Practical Guide（PDF 无法解析，经搜索结果交叉转述）；Stripe opt-in 机制（Developers Digest 转述官方 docs）；Building Effective Agents 的 docstring 论（Scribd 镜像片段）。
- 【摘要】Speakeasy / awslabs guidelines / Itential / udaykapur / Shopify / arXiv / Medium——仅搜索摘要，未读原文；引用时只取其摘要中明确陈述的结论。
- 【未找到】Stripe 官方"我们如何设计 MCP server"的工程博客（官方只有 docs.stripe.com/agents 与 stripe-mcp 仓库）；OpenAI platform.openai.com function calling 指南（403）。

第二轮（Google / Microsoft / GitHub / 学术 / 框架生态，2026-10-28 同日扩展）：

- 【一手】新增 2 篇：Google Gemini function calling 官方文档、Azure AI Foundry function calling 指南——WebFetch 对两域直连超时，改用 web_reader 全文抓取成功。
- 【摘要】GitHub 两篇工程博客与 github-mcp-server 仓库（结论取自搜索摘要与 changelog 摘要，链接为官方域名）；全部学术基准 8 项（仅取标题/摘要级结论，未读论文原文）；ADK / Neo4j / Cloudflare / LangChain 生态。
- 【转述】LangChain 工具设计实践（digitalapplied 综述转述官方博客）。
- 【未找到】varun.ca《MCP tool design》（site 限定检索为空）。
- 复核建议不变：要写进团队规范的条目，先对其一手出处重读原文（#1/#2/#3/#15/#16 可直接复核；#4 需人工下载 PDF 阅读；#17/#18 建议后续用 web_reader 补抓原文）。
