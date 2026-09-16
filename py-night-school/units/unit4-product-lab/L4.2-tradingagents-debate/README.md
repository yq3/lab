# L4.2 TradingAgents：辩论-裁决——条件边循环与预算封顶

> Unit 4 从「读过架构」到「跑过、改过」的第二站。三个产品一条递进线：L4.1 ai-hedge-fund
> （无框架纯 Python，层级投票）→ **本课 TradingAgents（LangGraph 实战，辩论-裁决）** →
> L4.3 Vibe-Trading（治理合规架构）。本课是三产品中**唯一用标准图引擎**的产品——你在
> L3.2–L3.4 熟的 StateGraph / 条件边 / reducer，在这里第一次以「生产产品的全部拓扑」
> 的规模出现。明线照旧：把金融辩论拓扑映射到**报销争议上诉**——CLM-2026-0004（发票校验
> 未过被驳回）的钱工对驳回提起上诉。

## 1. 本课目标

今晚跑懂 TradingAgents 的核心——**辩论-裁决拓扑**，并对它做两个真实改造。完成后你能：

- 用**条件边循环 + 纯计数器终止**装一张辩论图（分析师 → 申辩人⇄合规官 N 轮 → deep 裁决
  → 三方风险辩论 M 轮 → deep 终审），说清它为什么「可预算、可审计」（调用次数先验可算）；
- 完成**改造一：辩论轮次参数化**（对版产品的 `max_debate_rounds` 从 default_config 流进
  路由器——ex1）与**改造二：预算封顶**（模型调用预算，对照 superstep 预算双轴——ex2）；
- 精读 `conditional_logic.py`：计数终止、前缀轮转、`DEBATE_PATH_MAP` 全量映射防漂移
  （issue #1088）三件事各在哪几行；
- 说清**辩论-裁决 vs 层级投票**（昨晚 L4.1）的分界与适用场景（§2.3 分轨结论）。

**完成判据**：本目录下三条命令同时全绿（`exercises/` 是设计内的 TODO 红）——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 2. 概念讲解

先给全课对照表，再逐个展开：

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| `record Config(...`（不可变配置 bean） | `@dataclass(frozen=True) AppealConfig` | 都是「一次定型、运行期不可改」；差别在产品的轮次还有 env 第二层覆盖（`TRADINGAGENTS_MAX_DEBATE_ROUNDS`），本课教学版收敛成一层 |
| 内部静态类嵌套的 DTO | 嵌套 TypedDict 字段（`debate: DebateState`） | 长得像内部静态类，语义是**整体替换**不是引用共享——§5 坑位的主角 |
| BPMN 多实例/循环子流程 + 边界事件 | 条件边循环 + `count >= 2*N` 计数终止 | 循环的退出从流程图语义变成**路由函数里一个 if**；「轮次」是配置不是画布属性 |
| Flowable 网关的 default 流向 | `DEBATE_PATH_MAP` 全量映射 | 排他网关漏分支是建模期报错；条件边漏映射是**运行中崩**——全量映射是补丁（#1088） |
| `RejectedExecutionException`（线程池拒绝策略） | `BudgetExceeded`（模型调用预算） | 提交前查容量、满了响亮拒绝、绝不默默超卖——同一条纪律挪到了 LLM 调用层 |
| `enum` + 预留 `UNKNOWN` 档 | `Literal` 五档 verdict + `REVIEW` 哨兵 | 「解析失败」是一等业务状态不是异常路径 |
| `@JsonComponent` 反序列化钩子 | `field_validator(mode="before")` | 都在 schema 边界归一脏数据；Pydantic 把它写进字段声明，不用注册组件 |
| 定期清理 HttpSession 防膨胀 | `MsgClear`（RemoveMessage 清空 + 锚定占位） | 没有直接对应物——最接近的直觉是「清 Session」；差别：清理是**图里的一等节点**，可审计可断点 |

### 2.1 拓扑全景：一家交易公司 → 一次报销上诉

TradingAgents 把一家交易公司的投研流程编码成一张 StateGraph（12 个 agent 节点：4 个
分析师 + 辩论与裁决 3 + 交易员 1 + 风险辩论 3 + 终审 1；全部拓扑集中在
`setup.py#GraphSetup.setup_graph`）：

```text
START → 分析师×4（各带工具 ReAct 循环 + MsgClear）→ Bull ⇄ Bear（辩论循环）
→ Research Manager（裁决）→ Trader → Aggressive/Conservative/Neutral（风险辩论循环）
→ Portfolio Manager（终审）→ END
```

本课把它映射成**报销争议上诉**（官方映射出自调研 dimensions/A §2：报销争议/异常调查 =
固定轮次辩论 + deep 裁决）——角色一一对应，只有 Trader 在上诉场景无对应物被裁掉：

| 产品角色（模型） | 本课节点（模型） | 干什么 |
|---|---|---|
| Market Analyst 等 4 分析师（quick） | 政策分析师（quick，bind_tools 查政策） | ReAct 工具循环，产出 str 报告字段 |
| Msg Clear 节点 | 清理上下文 | 阶段结束清空消息史，换锚定占位 |
| Bull Researcher（quick） | 申辩人（quick） | 申请人立场：主张适用 POL-9.1 例外 |
| Bear Researcher（quick） | 合规官（quick） | 合规立场：主张 POL-7.2 红线 |
| Research Manager（**deep**） | 裁决官（**deep**） | 辩论史 → 结构化裁决 |
| Trader（quick） | ——（裁掉） | 上诉场景无「下单」环节 |
| Aggressive/Conservative/Neutral（quick） | 宽松解释/严格合规/例外处理（quick） | 三种政策视角的风险辩论 |
| Portfolio Manager（**deep**） | 终审官（**deep**） | 三方意见 → 终审决定 |

争议单是老朋友 CLM-2026-0004：发票 INV-2026-0005 已作废（连号重开），初审
`REJECT:INVOICE_INVALID`——钱工上诉主张「支出真实、新票已补」，申辩人与合规官围绕
POL-7.2（无有效发票整单驳回）与 POL-9.1（连号重开可按 80% 封顶）对抗。

### 2.2 条件边循环 + 纯计数器终止（本课教学主轴）

产品路由器全文只有十几行（`TauricResearch/TradingAgents@be952b8#tradingagents/graph/
conditional_logic.py`，下面是节选）：

```python
def should_continue_debate(self, state: AgentState) -> str:
    if state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds:
        return "Research Manager"
    if state["investment_debate_state"]["current_response"].startswith("Bull"):
        return "Bear Researcher"
    return "Bull Researcher"
```

三件事各值一提：

1. **纯计数器终止，无收敛判断**——路由器从不问「辩出结果了吗」，只数发言次数到没到
   `2 * max_debate_rounds`。这不是偷懒，是取向：**固定轮次 = token 可预算、过程可审计**
   （跑之前就知道辩论段恰好 2N 次调用），对照「自由讨论直到收敛」——终止条件是模型自己说
   TERMINATE，既不可预算也不可审计（调研里群聊派工被列为本项目反面教材的三宗罪之一）。
2. **前缀轮转**——`current_response` 一字段两用：路由器按它的前缀（"Bull"/"Bear"）决定
   下一个发言的对立面，辩手按它的全文取对方最新论点。`startswith` 容忍标签漂移（"Bull
   Analyst: ..." 与改名后的标签都命中）。先手辩手拿到空串时，产品给它换显式的「对方尚未
   发言」标记而不是空插值——否则模型会**虚构对方立场**（`opponent_argument_or_opening`，
   issue #1176）。
3. **path_map 全量映射**——辩论双方的条件边**共享同一个 `DEBATE_PATH_MAP`**，映射路由器
   的全部可能返回值（#1088）：路由器的返回集大于任何单条边「自然」的去向集合，不全量映射，
   一次提示词/国际化/重构漂移就会让 LangGraph 在图中途找不到路而崩掉。

风险辩论同构：`count >= 3 * max_risk_discuss_rounds` 终止，Aggressive→Conservative→Neutral
固定顺序轮转。讲义区 `code/conditional.py` 是两台路由器的同构复刻，`code/test_conditional.py`
直测「任何标签的返回值必落 path_map」（对版产品的 `tests/test_risk_router_path_map.py`）。

**新 Python 知识点（Java 类比）**：嵌套 `TypedDict`（`debate: DebateState`）≈ 内部静态类，
但状态更新是**声明式整体替换**——节点返回 `{"debate": {...}}` 就顶掉整个嵌套值，不是
「取出对象改一个字段 set 回去」。

### 2.3 辩论-裁决 vs 层级投票（对照昨晚 L4.1）

| | 层级投票（L4.1 ai-hedge-fund） | 辩论-裁决（本课 TradingAgents） |
|---|---|---|
| agent 间通信 | **互不可见**：各自出结论，代码加权合成 | **面对面对抗**：辩手读对方最新论点逐条反驳 |
| 终止 | 无循环（一次扇出+合成） | 固定轮次计数终止（可预算） |
| 确定性 | 最强（同输入可重放、prompt cache 命中） | 过程确定（轮次固定），内容依赖辩论史 |
| 交锋价值 | 零（防观点趋同是优点也是上限） | 对抗暴露单边盲区（申辩人 vs 合规官各自看不到的） |
| 软肋 | 共识质量完全取决于合成权重 | 输出无强制力（裁决全在 prompt 层，无硬审批代码） |

分轨结论（调研 dimensions 一句话版）：拓扑可组合、应按**金额 × 可逆性**分轨——低金额
可逆（报销初审）走层级投票，快而便宜；中金额（报销争议、异常调查，正是本课明线）叠
辩论-裁决；高金额不可逆（付款）无论前面用什么拓扑，终点必须是代码门 fail-closed
（L4.3 Vibe-Trading 的领地）。

### 2.4 deep/quick 双模型：贵模型只花在裁决

产品配置里有**两个模型名**（`default_config.py` 的 `deep_think_llm` / `quick_think_llm`），
但 deep 只用在两处：Research Manager 与 Portfolio Manager——都是「读完全部辩论史、出
结构化结论」的裁决节点；分析师、辩手、风险三方全用 quick。本课同款：`AppealConfig` 带
`quick_model` / `deep_model` 两个名字，离线跑出来 **quick 7 次 + deep 2 次 = 9 次**。

Java 类比：这就是读写分离/大小查询路由的 LLM 版——便宜快的实例扛高频调用，贵的实例
只接低频高价值的裁决请求。产品顺手把这件事做成了配置而非代码：改 env 就能换 deep 模型。

### 2.5 双预算轴：模型调用预算 vs superstep 预算

产品已有的一条轴是 `max_recur_limit=100`（对版 langgraph 的 `recursion_limit`）：数
**superstep**——图步数，不调模型的节点（工具分发、MsgClear）也烧步数，防的是死环。
但按 token 计费的世界里，成本 ≈ **模型调用次数**——一个不调模型的 superstep 免费，
一个 deep 调用很贵，两条轴根本不同量纲。固定轮次辩论让模型调用次数可以先验算出
（辩论段恰好 2N、风险段恰好 3M），「预算封顶」这才可能——本课改造二补的就是这条轴
（`LLMCallBudget` 包装模型客户端，超限抛 `BudgetExceeded`，对照 L2.3 手写循环里的
`AgentBudgetExceeded`——同一条确定性护栏纪律的第三次登场）：

| | superstep 预算 | 模型调用预算 |
|---|---|---|
| 谁在数 | langgraph 引擎（`recursion_limit`） | 你的包装层（`LLMCallBudget`） |
| 数什么 | 图步数（含不调模型的节点） | LLM API 调用 |
| 防什么 | 死环（拓扑错误） | 账单（预算超支） |
| 烧穿表现 | `GraphRecursionError` | `BudgetExceeded` |

Step 4（`step2_budget.py`）实测两条轴各烧各的：cap=5 时模型调用轴先断（第 6 次调用被拒），
recursion_limit=4 时 superstep 轴先断（此时模型只被调了 2 次）。

### 2.6 嵌套 state 手工回填 + MsgClear：长工作流的两条纪律

**回填纪律**：嵌套辩论 dict **没有 reducer**——LastValue 通道整体替换。所以每个辩手节点
干完 1 次模型调用后，必须手工回填嵌套 dict 的**全部键**（history 拼接、专属 history 拼接、
current_speaker 换新、count+1——产品 `bull_researcher.py` 回填 5 键）。漏一个键会怎样？
§5 整节讲这个坑。产品的备选方案本可以是「上移扁平 + Annotated reducer 各键自动合并」，
它没这么做——代价与取舍在 §5 的修复段。

**MsgClear**：产品在每个分析师阶段结束放一个清屏节点——`RemoveMessage(id=...)` 逐条删除
messages（add_messages reducer 认 id，删除指令走合并通道完成），换一条**锚定占位**
HumanMessage。下一阶段从干净上下文起步，跨阶段传递靠 str 报告字段而不是消息史——这是
长工作流防上下文膨胀与阶段串扰的图级方案。占位为什么锚定（产品教训 #888）：干巴巴一句
"Continue" 会被某些 OpenAI 兼容端点当字面任务，模型对着「继续」二字发挥——锚到具体业务
对象（产品锚标的+日期，本课锚争议单号+已归档结论）才钉得住任务。

### 2.7 输出卫生两道闸：REVIEW 哨兵 + 脏字段归一

调研结论值得原样记住：TradingAgents 的风控/审批「全部是 prompt 软约束，无任何硬性审批
拦截代码」——仅有的两处「硬」保护都在**输出解析层**：

1. **哨兵值**：rating 解析失败返回 `REVIEW` 而不是捏造 `Hold`（`signal_processing.py`，
   #1170）——失败必须可见，绝不静默降级成「可执行的中性」；
2. **字段归一**：LLM 会往可选数值字段填占位串（"N/A"）、百分比（"15%"）、人写货币
   （"$1,234.50"）——`schemas.py#_coerce_optional_float`（#1058/#1288）把前两者归一为
   null（**百分比绝不冒充绝对数额**：把 "15%" 读成 15 会给 600 美元的股票挂 15 美元
   止损），后者折成数字。

本课 `code/schemas.py` 是整数分字段的变体：五档 verdict 里 `REVIEW` 是哨兵档，
`parse_ruling` 解析失败回落哨兵；`_coerce_optional_cents` 归一脏金额——带小数的货币串
（"¥1,234.50"）在整数分字段里定不了单位，与百分比同判「不可抢救」→ None（这是与产品
的诚实差异，讲义与代码 docstring 都写明了）。

## 3. 动手代码

先 `uv sync`。`code/` 十四个运行文件：八个机制件（config / states / conditional /
debaters / msg_clear / schemas / budget / policy_tools，对版关系全写在各自 docstring 里）、
装配 graph.py + demo.py、三个讲义脚本（step1_debate_loop / step2_budget / demo_trace），
外加从 L3.2 原样服役的 mock_endpoint.py（另有四个 test_*.py 讲义区验收）。明线素材：
CLM-2026-0004 的单据数据读
[data/expense/review_mock.json](../../../data/expense/review_mock.json)（唯一来源），
政策条目表在 policy_tools.py。

### Step 1：辩论循环最小复现（10 分钟，零 LLM）

```bash
uv run python code/step1_debate_loop.py
```

```text
== Step1 辩论循环：条件边循环 + 纯计数器终止（零 LLM） ==
[路由器直调（rounds=1，终止计数 = 2*1 = 2）]
  count=0 speaker=               -> 申辩人  <- 开场：current_speaker 为空 → 申辩人先手
  count=1 speaker=申辩人（钱工代理）：…    -> 合规官  <- 申辩人刚发言（前缀轮转）→ 合规官
  count=2 speaker=合规官：…          -> 裁决官  <- count=2 已达 2*rounds → 裁决官（终止）
  count=1 speaker=合规官：…          -> 申辩人  <- count<2 且非申辩人前缀 → 申辩人
[rounds=1 真图轨迹（终止计数 = 2*1 = 2）]
  节点序列: 申辩人 → 合规官 → 裁决官（裁决官是占位节点，不调模型）
  模型调用: 2 次 = 恰好 2*rounds(2)——辩论段可预算的实证
[rounds=2 真图轨迹（终止计数 = 2*2 = 4）]
  节点序列: 申辩人 → 合规官 → 申辩人 → 合规官 → 裁决官（裁决官是占位节点，不调模型）
  模型调用: 4 次 = 恰好 2*rounds(4)——辩论段可预算的实证
[path_map 漂移防御（#1088）：任何 current_speaker，返回值都必落 DEBATE_PATH_MAP]
  speaker=申辩人（钱工代理）：…        -> 合规官（∈ DEBATE_PATH_MAP）
  speaker=合规官（新标签）：…         -> 申辩人（∈ DEBATE_PATH_MAP）
  speaker=                   -> 申辩人（∈ DEBATE_PATH_MAP）
  speaker=申辩人（Agresivo 漂移）   -> 合规官（∈ DEBATE_PATH_MAP）
```

对着输出指认四件事：终止发生在哪一行判断（count 到 2\*rounds）；轮转为什么用 startswith
（第二段直调里「申辩人（钱工代理）」带标签漂移照样命中）；rounds=1/2 两态的调用次数差
（2 → 4，先验可算）；漂移标签为什么不会让图崩（返回值全部落在 DEBATE_PATH_MAP 里）。

### Step 2：读装配（15 分钟，code/graph.py + code/demo.py）

`build_appeal_graph` 与产品 `setup.py` 逐行对版：分析师的条件边走 `[工具节点, 清理节点]`
简写（产品 `[current_tools, current_clear]`）；**辩论双方的条件边共享同一个
DEBATE_PATH_MAP**、风险三方共享 RISK_PATH_MAP（#1088 的原样落地）；轮次从
`AppealConfig` 流进 `AppealConditionalLogic`（ex1 改造的成品形态）。`demo.py` 是离线
剧本编排：quick/deep 各起一个 MockLLMEndpoint，9 份剧本按确定性执行顺序入队（工具轮 →
政策归纳 → 四段辩论台词 → 三方意见；deep 两份裁决 JSON）——rounds=2 时辩论段消费到第
9 份，这正是 ex1 要你参数化的那条数据流。

### Step 3：离线跑通争议全程（10 分钟）

```bash
uv run python code/demo_trace.py
```

```text
== L4.2 辩论-裁决上诉图：CLM-2026-0004（离线剧本，rounds=1/1） ==
图: START → 政策分析师 ⇄ 政策工具 → 清理上下文 → 申辩人 ⇄ 合规官（2*rounds 计数终止）→ 裁决官 → 宽松→严格→例外（3*rounds）→ 终审官 → END


== 段落① 政策分析师（工具循环） ==
  [政策分析师] + ai: [并行选了工具: lookup_policy, lookup_policy]
  [政策工具] + tool(_pol_1): {"found": true, "article": "POL-7.2", …
  [政策工具] + tool(_pol_2): {"found": true, "article": "POL-9.1", …
  [政策分析师] + ai: 政策归纳：POL-7.2 规定无有效发票整单驳回——本单 INV-2026-00…
  [清理上下文] + human: 报销争议上诉 CLM-2026-0004 已受理：政策分析阶段已完成，结论已归档…
  [清理上下文] - RemoveMessage ×6（清空消息史，换 1 条锚定占位——阶段裁剪）

== 段落② 申辩人 ⇄ 合规官（计数终止） ==
  [申辩人] debate.count 0→1（不写 messages——走嵌套 state）
  [合规官] debate.count 1→2（不写 messages——走嵌套 state）

== 段落③ 裁决官（deep 模型） ==
  [裁决官] ruling: APPROVE_WITH_CAP / 封顶 4000 分

== 段落④ 风险三方 + 终审（deep） ==
  [宽松解释] risk.count 0→1
  [严格合规] risk.count 1→2
  [例外处理] risk.count 2→3
  [终审官] final : APPROVE_WITH_CAP / 封顶 4000 分

== 收口 ==
  ruling : mock-deep → APPROVE_WITH_CAP / 封顶 4000 分
  final  : mock-deep → APPROVE_WITH_CAP / 封顶 4000 分（终审维持）
  模型调用: quick 7 次 + deep 2 次 = 9 次
    其中辩论段恰好 2*rounds=2 次、风险段恰好 3*rounds=3 次——固定轮次=可预算
  工具白名单: 分析师首请求绑定 ['lookup_policy']；辩论段请求不带 tools 字段（对版「工具按角色静态划分」）
```

看四个证据：①RemoveMessage ×6 后 messages 只剩 1 条锚定占位——辩论阶段根本不读消息史，
跨阶段传递的是 `policy_report` 这个 str 字段（§2.6）；②辩论段只动嵌套 debate 的 count
与 history；③两次 deep 调用分别产出 ruling 与 final（§2.4）；④辩论段请求体里没有
tools 字段——工具白名单只在分析师段，这是 ep.requests 取证出来的（产品的「工具按角色
静态划分」）。然后跑讲义区验收——

```bash
uv run pytest code/
```

```text
.......................................                                  [100%]
39 passed in 5.81s
```

39 个测试 = 路由器直测 14（漂移参数化 11 + 计数边界与轮转 2 + path_map 全量性 meta 1）
+ 输出卫生 16（脏归一参数化 9 + 哨兵参数化 4 + 合法存活 1 + 终审哨兵 1 + 五档 meta 1）
+ 预算 4 + 整图契约 5（9 次调用精确断言、工具白名单取证、MsgClear 效果、rounds=2 两态、
cap=5 烧穿）——「可预算」三个字全部有机器证明。

### Step 4：双预算轴实测（10 分钟）

```bash
uv run python code/step2_budget.py
```

```text
== Step2 双预算轴：模型调用预算 vs superstep 预算 ==
[1] max_llm_calls=None（不限，默认配置）
  完成: verdict=APPROVE_WITH_CAP, cap=4000 分
  调用: quick 7 + deep 2 = 9 次（预算没咬人，零感知）
[2] cap=9（恰好够：2 分析师 + 2 辩论 + 3 风险 + 1 裁决 + 1 终审）
  完成: verdict=APPROVE_WITH_CAP；budget.used=9——不超卖也不预留
[3] cap=5（中途烧穿）
  BudgetExceeded: LLM 调用预算耗尽：limit=5, 已调用 5 次
  烧穿点: 第 6 次调用（风险辩论第 1 方发言被拒）——预算检查在放行前，已花的恰好 = cap
[4] 另一条轴：recursion_limit=4（模型调用不限）
  GraphRecursionError: Recursion limit of 4 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
  口径差: superstep 数到 4 就停——「政策工具/清理上下文」不调模型也烧步数；
          这条轴防死环，模型调用预算防账单，两条轴缺一不可
```

对照 §2.5 的表逐行指认：第 3 段是模型调用轴先断（已花 5 次 = cap，第 6 次在放行前被拒，
不超卖）；第 4 段是 superstep 轴先断（此时模型只被调了 2 次——两条轴量的不是同一种东西）。

### Step 5（可选）：真实端点加餐

```bash
uv run python code/demo_trace.py --real
```

（首次配 `.env`：`cp .env.example .env`，Windows PowerShell：`copy .env.example .env`。
图一行不改；真实模式下 quick/deep 都用 `MODEL_NAME`——生产应给 deep 配更强的模型。）

### Step 6（可选）：真跑 TradingAgents 产品本体

主线离线可验收，产品真跑是加餐（需要模型端点与网络）。克隆并安装：

```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
uv sync
```

`.env` 按产品 `.env.example` 配最少四项（夜校端点中立纪律照样适用——产品支持
`openai_compatible` 供应商，可指向任意 OpenAI 兼容端点）：`TRADINGAGENTS_LLM_PROVIDER=
openai_compatible`、`TRADINGAGENTS_LLM_BACKEND_URL=<你的端点>`、
`TRADINGAGENTS_DEEP_THINK_LLM` / `TRADINGAGENTS_QUICK_THINK_LLM`（或按其文档配对应
供应商的 key）。跑仓库自带的 `main.py`（就是官方最小运行：`TradingAgentsGraph(
debug=True, config=config)` + `ta.propagate("NVDA", "2024-05-10")`）。省 token 的姿势：
`TradingAgentsGraph(selected_analysts=("market",), debug=True, config=config)`——只留
一个分析师，图形状就小一截。跑起来后对照 §2.1 的拓扑表看终端输出：分析师报告 →
Bull/Bear 辩论 → Research Manager → 风险三方 → Portfolio Manager。

真改造（Unit 4 里程碑的素材，改造说明留给 milestone）：在本地分支给产品加
`max_debate_llm_calls`——在 `default_config.py` 加配置项与 env 映射，贯穿到辩论节点
或路由器，超限即停——把本课 ex2 的预算轴移植进真产品。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改 TODO 标注区与所需的顶部 import（骨架只预置了 given
部分用到的；ex3 需要的那个 import 在文件头点名了）。卡住先想 5 分钟，再看渐进提示
（在 exercises/ 目录下）：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_rounds.py` | 辩论轮次参数化：路由器轮次写死 + 装配无视 config，改成配置驱动（对版 max_debate_rounds 的数据流）；验收含 rounds=1/2 两态调用次数精确断言与轮转序列 |
| ex2 | `exercises/ex2_budget.py` | 预算封顶：补全 LLMCallBudget（检查-放行-计数-委托）；cap 恰好够/中途烧穿/与 recursion_limit 是不同轴三态验收 |
| ex3 | `exercises/ex3_sentinel.py` | 哨兵 + 脏字段归一：补全 `_coerce_optional_cents` 与 `parse_ruling`；13 例参数化（百分比绝不冒充金额、乱码宁可丢字段、unparseable → REVIEW 绝不捏造） |

三题骨架全部自包含（零 HTTP：ex1/ex2 用 FakeChatModel 替身，ex3 纯 Pydantic）。测试数：
ex1 三个（rounds=1/2 两态 + path_map 覆盖）、ex2 三个（恰好够 / 中途烧穿 / 另一条轴）、
ex3 三个测试函数共 13 例参数化（脏归一 8 + 哨兵 4 + 合法存活 1）——与各题 docstring 的
完成判据逐字对齐。验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：嵌套状态静默丢键坑

这是本课的命名化失败模式——它就是产品选择嵌套辩论 state + 手工回填的代价面。

- **现象**：给合规官节点「优化」了一下，只回填它改过的两个键——图跑完了，但辩论第二轮
  路由错乱（count 丢了）、裁决官读到的辩论史是空的（history 丢了）。前者撞 `KeyError:
  'count'` 图当场崩（算走运）；后者被 `.get("history", "")` 兜住，**一个报错都没有**——
  裁决官对着空辩论史照样给出一份看起来合法的裁决，直到审计对不上才发现。
- **最小复现**（`code/debaters.py` 的合规官节点改坏成这样即可复现）：

  ```python
  turn = f"合规官：{response.content}"
  return {"debate": {"current_speaker": turn, "count": debate["count"] + 1}}
  # ↑ 嵌套 dict 无 reducer：LastValue 通道整体替换——history/applicant_history/
  #   office_history 三个键连同旧值一起蒸发，不报错、不留痕
  ```

- **Java 直觉为何失效**：Java 里「取出嵌套对象、改一个字段、set 回去」天经地义——
  `Debate d = state.getDebate(); d.setCount(...); state.setDebate(d);` 其余字段原封不动。
  这里的状态更新是**声明式替换**：返回值就是新值的全部，不是对旧对象的补丁。langgraph
  面对嵌套无 reducer 键，拿到什么就整体存什么——它以为你在声明完整的新状态，不知道你
  漏抄了三个键。类型层也救不了你：节点的返回类型是 `dict`，键名少写不红（L3.2 §5
  「写侧无检查」的嵌套版）。
- **修复与纪律**：① **回填全部键做成节点模板**——辩手节点工厂里固定「读旧值 → 逐键拼新
  值 → 返回完整 dict」，review 时只看「有没有抄全」，不看「改了什么」（产品
  `bull_researcher.py` 就是这个模板，本课 debaters.py 同款）；② 审计断言钉住嵌套键——
  test_demo 对 `debate.count` / `risk.count` 的精确断言会让丢键立刻红；③ 备选方案是
  **上移扁平 + Annotated reducer**（每个键各自 `operator.add`/覆盖，漏写不丢）——代价是
  嵌套结构被拍平、辩论史拆成一堆顶层键。产品选了嵌套+手工回填：结构可读（辩论史聚在
  一个 dict 里）、无 reducer 复杂度，代价就是这个坑——**取舍知情，模板兜底**。

## 6. 延伸

源码路标（本地克隆 `~/develop/opensource/TradingAgents`，锚定 be952b8，按图索骥）：

- `TauricResearch/TradingAgents@be952b8#tradingagents/graph/conditional_logic.py` ——
  本课教学主轴的本体：`should_continue_debate` / `should_continue_risk_analysis`，
  纯计数器终止 + 前缀轮转，十几行读完；
- `TauricResearch/TradingAgents@be952b8#tradingagents/graph/setup.py` —— 全部拓扑的
  装配处：`DEBATE_PATH_MAP` / `RISK_ANALYSIS_PATH_MAP` 全量映射（#1088 注释原文就在
  常量上方）、辩论双方共享 path_map 的写法；
- `TauricResearch/TradingAgents@be952b8#tradingagents/agents/researchers/bull_researcher.py` ——
  §5 坑位的正面教材：手工回填 5 键的节点模板（history 拼接、current_response 前缀、
  count+1）；
- `TauricResearch/TradingAgents@be952b8#tradingagents/agents/utils/agent_utils.py` ——
  `create_msg_delete`（RemoveMessage 清空 + 锚定占位，#888 教训写在 docstring）与
  `opponent_argument_or_opening`（先手防虚构对方立场，#1176）；
- `TauricResearch/TradingAgents@be952b8#tradingagents/agents/schemas.py` ——
  `_coerce_optional_float` 与 `_NULLISH_FLOAT`：脏字段归一的产品原文（"N/A"/百分比/
  货币串三种形态的处置与理由）；
- `TauricResearch/TradingAgents@be952b8#tradingagents/graph/signal_processing.py` ——
  REVIEW 哨兵的出处（#1170）：「不可识别的决策 → REVIEW 而非捏造 Hold」；
- `TauricResearch/TradingAgents@be952b8#tradingagents/default_config.py` ——
  `max_debate_rounds=1` / `max_risk_discuss_rounds=1` / `max_recur_limit=100` 与
  `TRADINGAGENTS_*` env 覆盖层、deep/quick 双模型名——本课两个改造的配置原型；
- `TauricResearch/TradingAgents@be952b8#tradingagents/agents/utils/agent_states.py` ——
  `InvestDebateState` / `RiskDebateState`：嵌套无 reducer 的原始形状；
- `TauricResearch/TradingAgents@be952b8#tradingagents/graph/trading_graph.py` ——
  `_run_signature`：图形状签名折进 checkpoint thread_id（改轮次/分析师选择，旧检查点
  自动失效，#1089）；顺带看 `propagate` 的最小运行路径；
- `TauricResearch/TradingAgents@be952b8#tests/test_risk_router_path_map.py` ——
  路由器直测范式（漂移标签参数化 + 「返回值必落 path_map」），本课 test_conditional.py
  的对版原件。

官方文档与论文：README（`TauricResearch/TradingAgents@be952b8#README.md`，含架构图与
免责声明「not intended as financial advice」）；论文 *TradingAgents: Multi-Agents LLM
Financial Trading Framework*（arXiv 2412.20138，https://arxiv.org/abs/2412.20138 ）——
辩论-裁决拓扑的设计动机与实验对照；langgraph 条件边与 recursion_limit 的语义见
https://docs.langchain.com/oss/python/langgraph/overview （L3.2 已覆盖，此处对照产品用法）。

下一课 L4.3 Vibe-Trading 收 Unit 4 的尾：以读为主——fail-closed 八查、哈希链账本、
对账不重发，把「输出无强制力」这个本课软肋变成代码硬门。

## 离毕业又近的一块

- **条件边循环 = 毕业设计重规划回环的原型**（L5.1）：毕设「取数→分析→生成建议单→送审」
  的静态图里，审批被打回后的重规划回环就是今晚这张 `申辩人 ⇄ 合规官` 的放大版——计数
  终止保证回环可预算，绝不无限重试；
- **REVIEW 哨兵 = L5.4 fail-closed 的输入端底线**：今晚它管「解析不了的裁决绝不捏造」，
  毕设把它扩成「不可解析即 DENY」的执行门纪律——同一句话的两种射程；
- **图形状签名 = L5.3 图版本绑定的先例**：产品把轮次/分析师选择折进 checkpoint key，
  定义一变旧执行态自动作废——毕设的事件溯源审计要用同一个思想回答「结论在什么规则
  版本下产生」。
