# TradingAgents 解剖档案

> 基线：~/develop/opensource/TradingAgents @ be952b8 (2026-09-07)；canonical TauricResearch/TradingAgents；MIT；论文 arXiv 2412.20138 配套框架，v0.4.0。
> 状态：活跃（周级发版），测试异常完备（`tests/` 60+ 回归测试，issue 号写进代码注释）。

## 1. 产品定位与形态

多 agent 交易公司模拟（trading-firm simulation）框架：把一家交易公司的投研流程——分析师团队 → 多空研究员辩论 → 交易员 → 风控辩论 → 投资组合经理——编码成一张 LangGraph 图，对单个 ticker 在指定日期跑出 5 档评级决策【核心】。README 自述「designed for research purposes」「not intended as financial advice」【文档】。

- 形态：Python 库（`pip install tradingagents`）+ Typer/Rich 交互式终端 CLI（`cli/main.py`，Rich TUI 实时显示各 agent 状态与报告流）。**无 Web 服务、无 REST API**——docker-compose 也是 tty 交互容器（`docker-compose.yml`）。单用户单进程。
- 交互入口：CLI 选分析师/LLM/日期 → `propagate()` 跑全图 → 终端渲染 + markdown 报告树落盘（`tradingagents/reporting.py#write_report_tree`）。
- 输出：`final_trade_decision`（结构化 PortfolioDecision 渲染成 markdown）+ 信号 `Buy/Overweight/Hold/Underweight/Sell` 或 `REVIEW`（`tradingagents/graph/signal_processing.py#process_signal`）。

## 2. Agent 执行架构

LangGraph `StateGraph` 线性主干 + 两个辩论循环，全部拓扑集中在 `tradingagents/graph/setup.py#GraphSetup.setup_graph`【核心】：

```
START → 分析师1 ⇄ tools1 → MsgClear1 → 分析师2 ⇄ tools2 → … → MsgClear_last
→ Bull ⇄ Bear（辩论循环）→ Research Manager → Trader
→ Aggressive → Conservative → Neutral（风险辩论循环）→ Portfolio Manager → END
```

框架层（StateGraph/ToolNode/SqliteSaver 语义）不重做，见 agent-framework/profiles/langgraph.md；本仓全部价值在「产品怎么编排」。每个 agent 是工厂函数返回的闭包节点（`create_*` 系列），prompt 为 f-string 模板。

**角色清单（9 个 agent，A 组重点）**：

| 角色 | 模型 | 输入 | 输出（state 字段） | 证据 |
|---|---|---|---|---|
| Market Analyst | quick | messages + 工具 | `market_report` | analysts/market_analyst.py，`prompt \| llm.bind_tools(tools)` ReAct 循环 |
| Sentiment Analyst | quick | get_news 工具 | `sentiment_report`（结构化 SentimentReport：6 档 band + 0-10 score + confidence） | analysts/sentiment_analyst.py；`bind_structured` |
| News Analyst | quick | get_news/get_global_news/get_insider_transactions/get_macro_indicators/get_prediction_markets | `news_report` | graph/trading_graph.py#_create_tool_nodes |
| Fundamentals Analyst | quick | get_fundamentals/四大报表 | `fundamentals_report` | 同上 |
| Bull/Bear Researcher | quick | 4 份报告 + 辩论 history + 对手最新论点 | `investment_debate_state`（history/bull_history/bear_history/current_response/count） | researchers/bull_researcher.py#bull_node |
| Research Manager | **deep** | debate history | `investment_plan`（结构化 ResearchPlan：5 档 recommendation + rationale + strategic_actions） | managers/research_manager.py |
| Trader | quick | investment_plan + market_report（价格 grounding #1167） | `trader_investment_plan`（TraderProposal：Buy/Hold/Sell + entry_price/stop_loss/position_sizing） | trader/trader.py |
| Aggressive/Conservative/Neutral 风险辩手 | quick | trader_plan + 4 报告 + 风险辩论 history | `risk_debate_state` | risk_mgmt/aggressive_debator.py 等 |
| Portfolio Manager | **deep** | risk debate history + investment_plan + trader_plan + `past_context`（记忆） | `final_trade_decision`（PortfolioDecision：rating/executive_summary/investment_thesis/price_target/time_horizon） | managers/portfolio_manager.py |

deep/quick 双模型配置（`deep_think_llm`/`quick_think_llm`，default_config.py），仅 Research Manager 和 PM 用 deep 模型。

**辩论轮次与终止条件**（graph/conditional_logic.py）【核心】：
- 投研辩论：`count >= 2 * max_debate_rounds` → Research Manager（默认 1 轮 = bull、bear 各发言一次）；否则按 `current_response` 前缀轮转对手。纯计数器终止，无收敛/裁判提前终止。
- 风险辩论：`count >= 3 * max_risk_discuss_rounds` → Portfolio Manager；发言顺序固定 Aggressive→Conservative→Neutral 轮转。
- 条件边的 path_map 全量映射防 fall-through 崩溃（setup.py#DEBATE_PATH_MAP，#1088）。

**跨阶段状态传递**：嵌套 dict 整体覆盖（无 reducer）——辩论节点每次手工回填全部字段（bull_researcher.py#L54-62）；分析师消息经 `create_msg_delete()`（RemoveMessage 清空 messages，agent_utils.py#L204）裁剪后进下一阶段，报告以独立 str 字段传递；`instrument_context`（yfinance 确定性解析的标的身份，防 LLM 从 K 线幻觉出公司，#814）与 `past_context`（决策日志）在初始 state 注入（trading_graph.py#_run_graph L516-526）。

## 3. 技术底座

Python 3.12。LangGraph（StateGraph + prebuilt ToolNode + checkpoint-sqlite）做编排，LangChain 做 LLM 封装；自研 `llm_clients/` 工厂支持 16 家 provider（openai/anthropic/google/bedrock/openai_compatible…，factory.py + model_catalog.py）。结构化输出走 `bind_structured`/`invoke_structured_or_freetext`（agents/utils/structured.py），按 provider 原生模式（json_schema/response_schema/tool-use）+ 自由文本回退。框架能力对照见 agent-framework/profiles/langgraph.md、langchain.md。

## 4. 状态与持久化

- **图状态**：`AgentState(MessagesState)` TypedDict——messages + 8 个业务字段 + 两个嵌套辩论 state（agents/utils/agent_states.py）【核心】。
- **Checkpoint**：可选 `checkpoint_enabled`，per-ticker SQLite（`data_cache_dir/checkpoints/{TICKER}.db`，graph/checkpointer.py#get_checkpointer）；thread_id = sha256(`ticker:date:图形状签名`)，签名折叠分析师选择/辩论轮次/资产类型，**改图形状后旧 checkpoint 自动失效**（trading_graph.py#_run_signature，#1089）；resume 时 invoke 传 `None` 防消息 reducer 重复追加（#checkpoint_input，#1249）；成功后删线程（clear_checkpoint）。并发靠 per-ticker 分库避免 SQLite 争用。
- **决策日志**（agents/utils/memory.py#TradingMemoryLog）【核心】：append-only markdown（`trading_memory.md`），HTML 注释硬分隔符；`pending → resolved` 生命周期：跑完存 pending（幂等防重），下次同 ticker 运行时抓真实收益 vs 基准算 alpha、LLM 反思、原子批量更新（temp + os.replace）；resolved 条目记 `resolution_date`，历史回测按 point-in-time 过滤旧教训（#1251 防回测偷看未来）；可配条数上限轮转（pending 永不删）。
- **审计/回放**：每次运行全量状态 JSON（`results/{ticker}/TradingAgentsStrategy_logs/full_states_log_{date}.json`，trading_graph.py#_log_state）+ markdown 报告树。无独立审计链。
- **延迟反思**：reflection.py#Reflector（2-4 句纪律性 prose，存日志供未来 agent 注入）。

## 5. HITL 与风控 ★

**结论：全部是 prompt 软约束，无任何硬性审批/拦截代码**。

- 无 LangGraph `interrupt`、无人工审批门、无工具级权限差异（全部只读数据工具，天然无危险操作面）。全仓 grep `human/approve/confirm/interrupt` 无命中（仅注释）【核心证据】。
- README 宣称「Portfolio Manager approves/rejects the transaction proposal. If approved, the order will be sent to the simulated exchange and executed」——【文档】宣称；代码实现是 PM 单次 LLM 结构化调用输出 PortfolioDecision（portfolio_manager.py#portfolio_manager_node），**无 approve/reject 分支、无任何 exchange/broker 调用**（全仓 grep `broker/place_order/execute_order` 仅命中符号转换注释）。交易执行为零：这是纯决策生成器。
- 「风控团队」= 3 个 prompt 人格辩论（aggressive/conservative/neutral_debator.py 均为纯 prompt f-string）+ 计数终止。
- 仅有的「硬」保护在输出解析层（值得注意的两个小模式）：
  - rating 解析失败返回哨兵值 `REVIEW` 而非捏造 `Hold`（signal_processing.py，#1170）——解析失败可见化；
  - Pydantic `field_validator` 把 LLM 填的 "N/A"/"15%"/"$1,234.50" 归一为 null（schemas.py#_coerce_optional_float，#1058/#1288）——百分比绝不冒充价格。
- 数据正确性硬化（v0.3-0.4 主题）：look-ahead 过滤（FRED/社交/决策日志三处 point-in-time）、OHLCV 缓存新鲜度、ticker 路径穿越防护（safe_ticker_component）——属于「防数据错误」而非「防 agent 越权」。

## 6. 工具与业务系统集成

- 工具 = 只读市场数据 API：yfinance（默认）/Alpha Vantage/FRED/Polymarket/Reddit/StockTwits（`dataflows/` 供应商链）。**按类别显式配置**（default_config.py#data_vendors，"yfinance,alpha_vantage" 表示有序回退，「不静默路由到未选的供应商」）。
- 工具实现 = LangChain `@tool` 函数（agents/utils/agent_utils.py）挂到 prebuilt `ToolNode`，每个分析师一个专属 ToolNode（trading_graph.py#_create_tool_nodes）——工具白名单按角色静态划分。
- 凭据：环境变量（.env.example：16 家 LLM key + FRED_API_KEY），CLI 启动时检测并交互提示补 key（cli/main.py）。无 secret manager。
- 读写隔离：全部只读，无写入面。`get_verified_market_snapshot`（绑定分析师 LLM 的确定性校验快照）用来对抗 LLM 报告与数据不符。

## 7. 部署与产品化

- pip 包 + CLI 为主；Dockerfile 两阶段（venv builder + slim runtime，非 root appuser）；docker-compose 主服务 tty 交互 + 可选 ollama sidecar profile。`main.py`/`test.py` 为最小示例。
- 单用户单进程：无多租户、无配额（仅 `max_recur_limit=100` 防图死循环；callbacks 可挂 token 统计，cli/stats_handler.py）。
- 可观测性：Rich TUI 实时 agent 状态/工具调用/报告流 + 结果全落盘；无 metrics/tracing 集成。
- 配置三层：DEFAULT_CONFIG → TRADINGAGENTS_* 环境变量（类型强转、非法值启动即炸，default_config.py#_coerce）→ CLI 交互选择；`.tradingagents/` 目录（logs/cache/memory）。

## 8. 对本项目的适用性

对照硬约束（Java / 独立部署+API / 图编排 / 硬性审批审计合规）：

- **① 独立部署+API：❌** CLI/库形态，无服务化。但编排器边界干净：`TradingAgentsGraph` 一个类封装图构建+执行+持久化+报告（propagate/ checkpoint_scope/ save_reports），外面包一层 API controller 即可服务化——可作为「图编排器作为独立服务内核」的最小形态参考。
- **② 图编排：✅** LangGraph 标准且克制的产品用法。最值得抄的两个模式：**(a) 辩论循环的条件边 + 计数终止**（conditional_logic.py——固定轮次辩论是可审计、可预算的，比「自由讨论直到收敛」更适合合规场景）；**(b) Msg Clear 节点裁剪跨阶段上下文**（每个分析师阶段结束清 messages，只把报告 str 传下去——长工作流防上下文膨胀与串扰的图级方案）。
- **③ 审批/审计/合规：⚠️ 基本缺席**，但三个小模式可借：REVIEW 哨兵值（不可解析决策绝不静默降级为中性）；决策日志 pending→resolved + resolution_date（审计要能回答「当时知道什么」）；图形状签名进 checkpoint key（工作流定义变更后旧执行状态自动作废——版本化审计先例）。
- **可直接借鉴模式**：
  1. **结构化决策 schema + render 回 markdown**（agents/schemas.py）：Pydantic 给下游系统消费、render_* 给人看/存档，同一条决策两种形态；LLM 字段级校验器兜真实世界的脏输出（"N/A"/百分比/带货币符号）。财务 agent 的决策/凭证对象可直接套此三层（schema → validator → renderer）。
  2. **延迟反思的决策日志**（memory.py + trading_graph.py#_resolve_pending_entries）：决策当下存 pending（快、无 LLM 调用），事实发生后补 outcome+reflection，下次同标的注入——离线复盘闭环，天然是审计流水。
- **不可迁移点**：风控/PM 全靠 prompt（企业合规必须是代码硬门，见 Vibe-Trading 的 mandate gate 对照）；辩论轮次固定计数无收敛判断（token 成本可控但质量无自适应）。
- **避坑**：嵌套 state 无 reducer、节点手工全量回填，漏填一个键就静默丢数据（bull_node 回填 5 键）；README 的「PM 审批/模拟交易所」是论文叙事不是实现——评估开源产品时宣称与实现要逐条对码。
