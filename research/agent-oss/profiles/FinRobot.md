# FinRobot 解剖档案

> 基线：~/develop/opensource/FinRobot @ 6d6ccd3 (2026-09-11)；canonical AI4Finance-Foundation/FinRobot；setup.py 版本 0.1.5。**多代架构并存的混合仓库**：V0（AutoGen，`finrobot/`）与 V1（OpenAI Agents SDK，`finrobot_equity/`）开源；V2 为在线产品（PydanticAI，README 自述源码未开源）、Desktop 为闭源二进制发行——V2/Desktop 仅能作【文档】级证据。MIT（含 NOTICE/TRADEMARK_POLICY）。

## 1. 产品定位与形态

- 定位：金融 LLM agent 平台（白皮书 arXiv:2405.14767），宣称四层架构（Financial AI Agents / LLM 算法 / LLMOps+DataOps / 多源基座）与 Smart Scheduler——**均为论文/README 概念，开源代码未实现 Scheduler**（❌ 仓库内无对应模块，仅 `configs/save_config_forecaster.json` 一类产物）。
- 实际交付三种形态：
  1. **V0 Python 库 + notebook 教程**（`finrobot/` + `tutorials_*`）：AutoGen 多 agent 工作流封装，做财报分析、股价预测、交易策略 demo。
  2. **V1 股票研报生成器**（`finrobot_equity/`）：CLI 三步管线（取数→分析→出 HTML/PDF 报告）+ FastAPI Web 应用（登录/任务/历史/管理端），最接近「产品」的部分。
  3. **V2/Desktop**：闭源（README "source code not yet open-sourced"）；Desktop v0.1.0 宣称 Lead Agent + 5 角色子 agent + 3 辩论 agent（bull/bear/judge）、13 章研报、数字溯源——【文档】级，代码不可核验。
- 目标用户：量化/研究开发者（V0）、分析师（V1 研报）、付费用户（finrobot.ai Pro）。

## 2. Agent 执行架构（★重点：拓扑与数据流）

### V0：AutoGen 群聊 + Leader 嵌套会话派工

编排完全建立在 AutoGen（pyautogen≥0.2.19）之上；AutoGen 不在 agent-framework 的 17 框架档案内，此处按「产品用法」简述。

- **单 agent**：`finrobot/agents/workflow.py#SingleAssistant`——FinRobot（AssistantAgent 子类，`workflow.py#FinRobot`）+ UserProxyAgent 对（`human_input_mode="NEVER"`、`max_consecutive_auto_reply=10`、本地 docker=False 代码执行）；变体 `SingleAssistantRAG`（挂检索工具）、`SingleAssistantShadow`（嵌套「影子」agent 处理 instruction 文件）。
- **群聊型**：`workflow.py#MultiAssistant`——AutoGen GroupChat + 自定义 `custom_speaker_selection_func`（`workflow.py:363-382`：proxy 发言后回到上一发言者；检测到 tool_calls 或 TERMINATE 转给 proxy；否则轮转下一 agent）。终止 = 消息以字符串 "TERMINATE" 结尾；每轮 chat 结束后 `reset()` 全部 agent（**无跨会话状态**）。
- **Leader 型（金融多 agent 主拓扑）**：`workflow.py#MultiAssistantWithLeader`——Leader agent 的 system prompt 要求「每次回复末尾以 `[员工名] 订单` 格式向一名成员下达一条具体指令」（`finrobot/agents/prompts.py#leader_system_message`）；`order_trigger` 正则监听 Leader 消息中的 `[name]` 标记触发该成员的**嵌套会话**（`workflow.py:453-468`，`max_turns=10`、摘要 `reflection_with_llm`）；员工完成后回报，Leader 检查再派下一单，直到回复 TERMINATE。即「经理-员工」消息驱动拓扑，**转移逻辑是字符串模式匹配而非图**。
- **角色库**：`finrobot/agents/agent_library.py#library`——name → {profile(系统提示), toolkits}（Market_Analyst、Expert_Investor、Financial_Analyst 等 11 个）。
- **示例拓扑**（`experiments/investment_group.py`【示例】）：CIO 之下一级查 Market Sentiment / Risk Assessment / Fundamental 三个小组，每组可选 with_leader（Senior 带队派工）或 without_leader（3 名同级分析师，靠 prompt 互评达成共识——"Reach a consensus with Fundamental_Analyst_2..."）。**没有实现 bull/bear/judge 辩论**（那是闭源 V2/Desktop 的宣称）。

### V1：无编排的「分段单发」+ 确定性估值引擎

- `finrobot_equity/core/src/modules/equity_agents/agent_manager.py#EquityResearchAgentManager`：8 个 OpenAI Agents SDK `Agent`（tagline/company_overview/investment_overview/valuation_overview/risks/competitor_analysis/major_takeaways/news_summary，各一个 pydantic `output_type`），`generate_text_section()` 用 `Runner.run(agent, prompt)` **逐段独立单发**——agent 之间无对话、无握手、无共享状态；所谓 manager 只是一个 dict + 字段映射。框架机制见 agent-framework/profiles/openai-agents-python.md。
- 真正的「工作流」是 **shell 管线**：`generate_financial_analysis.py`（FMP 取数→财务处理→预测→可选调 8 agent 生成文字段落）→ `create_equity_report.py`（估值引擎+图表+HTML）→ `generate_pdf_report.py`；Web 应用用 `subprocess.Popen` 串起这三步（`web_app/main.py#execute_analysis_pipeline`）。步骤间通信靠 **CSV/JSON/TXT 中间文件**（financial_metrics_and_forecasts.csv、sensitivity_analysis.json 等）。
- **「数字代码算、叙述 LLM 写」**：`modules/valuation_engine.py#ValuationEngine` 提供 EV/EBITDA、同业比较、DCF 三法估值 + football field + `synthesize_valuation()`（按 confidence 加权合成目标价）——确定性 Python 计算，LLM agent 只把结果写成研报段落。这与 ai-hedge-fund「LLM 不碰交易」同源但更弱（V1 的 LLM 仍直接叙述结论，无风控闸门）。

### 终止条件

V0：TERMINATE 字符串 / max_consecutive_auto_reply / 嵌套 max_turns；V1：管线步骤顺序执行完毕，无循环无重试（agent 单发即终）。

## 3. 技术底座

- V0：Python 3.10，AutoGen 0.2 系（ConversableAgent/GroupChat/nested chats/Cache），yfinance/finnhub/FMP/sec_api 等数据源，reportlab 出 PDF；langchain 0.1.20 仅在依赖清单（retrievechat 用）。
- V1：Python 3.10-3.12（Dockerfile 用 3.13-slim，setup 与镜像已轻微不一致），openai-agents SDK + openai>=1.0；FastAPI + SQLAlchemy(SQLite) + Jinja2 SSR + uvicorn。
- 框架层结论交叉引用：openai-agents-python（V1）；AutoGen 无既有档案。
- 依赖健康度差：V0 requirements 钉死大量旧版（unstructured 0.8.1、aiohttp 3.8.5），V0 与 V1 两套 requirements 并存（requirements.txt vs requirements-equity.txt）。

## 4. 状态与持久化

- **V1 Web 应用有真正的 DB**（`web_app/database/models.py`）：SQLite 四表——`users`（含 GitHub OAuth 用户）、`sessions`（服务端会话，7/30 天过期，cookie session_id）、`request_logs`（**每次 API 调用**记 user/endpoint/method/request_body/status/ip/ua/耗时——事实上的使用审计日志，经 `middleware/request_logger.py`）、`report_requests`（任务状态机 pending→running→completed/failed + 耗时 + 错误信息）。
- 任务运行态：**内存 dict `tasks`** + 每任务日志文件 `logs/task_<id>.log`（服务重启后 status 接口从日志文件恢复只读视图，`main.py:608-625`）——重启即丢运行态，报告产物落 `core/output/<TICKER>/`，**同一 ticker 后次运行覆盖前次**（`main.py:713-715` 注释自认）。
- **V0 无持久化**：AutoGen `Cache.disk()` 仅当调用方传 `use_cache=True` 才启用（缓存 LLM 响应）；每次 `chat()` 后显式 reset 所有 agent（`workflow.py#chat`）——**会话不连续，全部状态在单次群聊消息列表里**。
- ❌ 无 checkpoint/回放：V0 群聊过程只存在于内存 messages；V1 管线中间产物文件可复盘输入输出，但 agent 的完整 prompt/response 不留痕（对比 ai-hedge-fund 的 PromptCache 差距明显）。
- ❌ 无并发控制：单 uvicorn 进程 + 内存 tasks dict；两个用户同时跑同一 ticker 会互相覆盖输出目录。

## 5. HITL 与风控（★重点：硬拦截还是软约束）

**结论：全线皆软。无审批门、无风控闸门、无人工接管代码。**

- V0：`human_input_mode="NEVER"` 是所有 workflow 类的默认（`workflow.py:132,175,281`）——AutoGen 唯一内建的 HITL 钩子被显式关闭；UserProxy 只当工具执行器/代码运行器。`max_consecutive_auto_reply` 是唯一护栏。
- **风险控制以「角色扮演」存在**：`experiments/investment_group.py` 的 Risk Assessment Analysts 小组、V1 的 `equity_agents/risks_agent.py`——都只是**让 LLM 写风险分析文本**的系统提示，不产生任何代码级约束（无限额、无拦截、无 veto）。❌ 检索 approve/confirm/risk_limit/human_input/review/veto/threshold 无命中（唯一相关的是报告页脚免责声明与 prompt 里的「Thesis Under Review」措辞）。
- 代码执行面完全放通：V0 默认 `use_docker: False` 的本地 Python 执行 + `functional/coding.py#CodingUtils`（modify_code/create_file 直接写文件系统）——若照抄进多租户服务是重大安全洞。
- V1 的弱准入控制只覆盖 Web 层：登录（密码 + GitHub OAuth）、`FINROBOT_ADMIN_EMAILS` 邮箱名单式的 admin 检查（`admin_routes.py:20-23` 自注 "in production, use proper role-based auth"）、首次启动随机生成默认 admin 密码打印到 stdout（`auth.py#init_default_admin`）——**产品门禁，不是决策门禁**：任何登录用户提交的分析请求都直接全管线执行，无人工确认环节。
- 【文档】闭源 V2/Desktop 宣称 bull/bear/judge 辩论 + 数字溯源 + IC memo——方向上补 HITL/对抗校验的课，但不可核验，仅当路线图参考。

## 6. 工具与业务系统集成

- **V0 工具注册**（`finrobot/toolkits.py#register_toolkits`）：三类——裸函数 / {function,name,description} dict / 整个类的公开方法批量注册（`register_tookits_from_cls`），统一经 `stringify_output` 包装（DataFrame→str）后用 AutoGen `register_function(caller=agent, executor=user_proxy)` 挂接。数据源工具集中在 `data_source/`（FinnHubUtils/YFinanceUtils/FMPUtils/RedditUtils/SecUtils…），财务函数在 `functional/`（analyzer/charting/quantitative/text/reportlab/rag）。工具选择绑定在 agent 库条目的 `toolkits` 字段（`agent_library.py:41-46,71-78`）。
- **V1 agent 无工具**：数据由管线先经 `market_data_api.py`（FMP）取好、拼成 markdown prompt 喂给 agent；agent 零工具调用——读写隔离靠「agent 只读预取文本」实现（与 ai-hedge-fund 同思路，但没做成协议抽象）。
- 凭据三套并存：V0 用环境变量（FINNHUB_API_KEY/FMP_API_KEY，`data_source/finnhub_utils.py:17` 等）+ `OAI_CONFIG_LIST`（AutoGen 模型表）；V1 用 `core/config/config.ini`（fmp/openai/adanos key，模板 config.ini.example）；Web 层另有 GITHUB_CLIENT_ID/SECRET 与 FINROBOT_ADMIN_* 环境变量。❌ 无密钥管理抽象，`.git` 里直接带 `OAI_CONFIG_LIST` 与 `config_api_keys` 文件名（内容为样例）。
- 与交易系统的集成：❌ 无下单/组合通道（V0 有 backtrader 依赖但仅教程用；V1 只产研报）。

## 7. 部署与产品化

- **V1 是可部署 Web 服务**（本仓唯一满足「独立部署+HTTP 接口」的部分）：`run_web_app.py` → uvicorn 127.0.0.1:8001；`Dockerfile`（python:3.13-slim，CMD uvicorn --host 0.0.0.0 --port 8001）；`deploy.sh`（venv + .app.pid 进程管理 + start/stop/restart/status）；`deploy.gcloud.sh`（GCP 部署）。⚠️ 默认 `reload=True`（开发模式当默认，生产需显式 `--no-reload` 或 WEB_RELOAD=false）。
- 多租户：有用户/会话/审计三件套，但**无配额/限流/成本计量**（LLM 与 FMP 调用不计量、不限额）；admin 端提供 stats/users/requests/reports 只读查询（`admin_routes.py`）。
- 任务模型：FastAPI BackgroundTasks + subprocess 逐行吸日志到内存+文件；**横向扩展为零**（内存 tasks、本地磁盘输出、SQLite）。
- 可观测性：RequestLoggerMiddleware（DB 审计行）+ 任务级日志文件（可下载 `/api/logs/{id}/download`）+ Python logging；无 trace/metrics。
- V0/V2：V0 是库无部署物；V2/Desktop 闭源（DMG 分发、GitHub auto-update）。

## 8. 对本项目的适用性

硬约束对照：①独立服务+API——**仅 V1 web_app 满足**（FastAPI+Docker，但任务是本地 subprocess 不是服务化 agent 运行时）；②图编排——❌ 两代开源代码都无图引擎（V0 消息驱动群聊、V1 shell 管线），其 AutoGen 群聊拓扑更接近「动态路由对话」而非可静态审计的图；③硬性审批/审计/合规——**审计最弱**：V1 的 request_logs 表是仓库里唯一的审计实现，决策级审计缺失。

### 可借鉴模式

1. **request_logs 审计中间件**（`web_app/middleware/request_logger.py` + `database/models.py#RequestLog`）：中间件层把「谁在何时以什么参数调了哪个端点、状态码、耗时」统一落库，业务代码零侵入。对 Java 侧（Spring 拦截器/AOP）是低成本高回报的合规基线，可扩展记录 agent 决策请求的关联任务号。
2. **「数字代码算、叙述 LLM 写」的估值引擎分界**（`valuation_engine.py`）：DCF/同业/EV/EBITDA 全部确定性计算 + `synthesize_valuation()` 显式加权合成，LLM 只叙述——与 ai-hedge-fund 的「LLM 影响力终止于 Signal」互为印证，可作为财务 agent 的通用分层律：**凡是进报告/进账的数字必须来自可单测的确定性代码路径**。
3. **Leader 文本协议派工**（V0 `prompts.py#leader_system_message` + `utils.py#order_trigger`）：用 `[员工名] 指令` 的结构化文本约定 + 消息模式匹配实现经理-员工路由，零框架依赖。作为「LLM 自主编排」的最小实现有参考价值——但对本项目更适合作**反面教材**：路由正确性依赖 LLM 遵守格式与字符串匹配，不可静态验证，与硬约束③冲突；若需要动态派工，应在图编排层（LangGraph4j 节点路由）实现而非消息文本。
4. **任务状态机 + 日志文件恢复**（`web_app/main.py` 的 tasks dict + task_<id>.log）：长任务异步化、状态可查询、服务重启后从日志文件恢复只读视图——朴素但覆盖了「跑一半崩了用户还能看到什么」的问题。

### 不可迁移点

- AutoGen 群聊（V0）整体：无持久化、无审计、TERMINATE 字符串终止、本地代码执行——与 Java/合规目标全部相悖，且 AutoGen 0.2 已过时。
- 中间文件传递的 shell 管线（V1）：步骤间靠 CSV/TXT 文件耦合，无类型契约；Java 侧应换成显式 API/消息契约。
- GitHub OAuth 默认回调硬编码 localhost:8000（与实际端口 8001 不符，`main.py:22`）之类的糙点提示其工程成熟度。

### 避坑

- **「产品宣称 vs 代码实现」落差极大**：README 头部的多 agent 辩论（bull/bear/judge）、Smart Scheduler、四层架构、13 章溯源研报——全部来自闭源 V2/Desktop 或论文，开源部分没有；引用 FinRobot 结论必须注明证据属于 V0/V1 代码还是【文档】。
- 两代代码同仓但互不依赖（V0 甚至没有 import finrobot_equity），不要当作一个连贯架构阅读。
- V0 教程含本地代码执行（use_docker=False），复现 demo 时注意沙箱。
