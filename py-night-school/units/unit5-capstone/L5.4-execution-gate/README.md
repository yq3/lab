# L5.4 毕业设计④：fail-closed 执行门与结业——最后一道门，以及回 Java 的桥

> 昨晚 L5.3 审计面就位：执行史 append-only 落账、模型决策可回放原话、每一版图自带身份。
> 今晚是全教程最后一课，也是两条并行线的**汇合点**：以 L5.3 为底，并入 L5.2 的审批面
> （interrupt 暂停、三元回复、拒绝回环），在执行出口装上 fail-closed 执行门收口，并产出
> **JAVA-MAPPING.md**——本教程「双目的」的兑现物：每个模式在 Java 栈的对应物与翻译坑，
> 拿去就能当 Java 侧开发任务的拆解输入。讲义末尾是结业自查表（CURRICULUM §7 逐条对照）。

## 1. 本课目标

完成后你能：

- **四层合体跑通**：L5.1 的静态图 + L5.2 的 interrupt 审批 + L5.3 的审计三层 + 本课执行门，
  一张图、一个服务、一张审计库——审批批准只是授权，付款必须过门（A7）；
- 写出**纯函数检查链**（`gate.check_intent`）：审批单二次校验（A7+A6「真批了吗、批的是这版吗」）
  → 供应商黑名单 → 单笔上限 → 当日累计 → 当日频次，固定顺序首查命中即停；任何 None/畸形
  输入的答案是 **DENY**，不是 TypeError——不可解析即拒绝，fail-closed；
- 对齐**三态裁决**（对版 L4.3）：结构性违规 → DENY（黑名单/审批缺位/指纹不符/账本不可读）、
  定量超限 → PAUSE_FOR_REAUTH 或按 `Policy.clamp_overruns` 裁到限额后放行（clamp 只缩不放；
  频次不可裁）、全查通过 → ALLOW（连「通过」也是带原因码的一等裁决）；
- 跑通**三条主链路**（demo_final，里程碑集成测试的雏形）：①审批暂停→恢复→门 ALLOW→
  payment.executed；②拒绝回环→新审批单（content_hash 变）→批准→过门；③紧合同超限→
  门不付款→gate.denied + ESCALATE 终态；
- 收口 **JAVA-MAPPING.md**（≥10 个模式、四列表、核实过再写——克隆里没有的老实写「需自建」）。

**完成判据**：本目录下三条命令同时全绿（`exercises/` 是设计内的 TODO 红）——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 2. 概念讲解

先给全课对照表（datetime 一行是今晚的新 Python 件——§5 坑位的主角），再逐个展开：

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| `Instant`（必然带时区）/ `ZonedDateTime` / `LocalDateTime`（不敢乱比） | `datetime` 默认 **naive**（无时区标注） | naive/aware 在 Python 是**运行时属性不是类型**——两者一比较直接 `TypeError`（§5 坑位） |
| 注入 `Clock`（测试可控时间） | 时钟/日期注入参数（`clock=` / `today=`） | 同款思想：生产给系统钟、测试给固定钟；检查链**绝不自己取时钟**（对版 L4.3/L5.3） |
| 纯静态方法 + `enum` verdict（风控规则引擎的古典形态） | `gate.check_intent` 纯函数 + `GateVerdict` 三态 | L4.3 读过的 Vibe-Trading `check_mandate` 就是这个形状的 Java 原型——门没有框架，只有纪律 |
| sealed interface + record（不可变合同） | `@dataclass(frozen=True)`（L4.3 复引） | 合同对象零验证面：错了就崩（fail-closed 反而喜欢），不给「帮坏输入修复」的解析空间 |
| Axon `EventStore` / CQRS 读模型 | 事件表的日历聚合投影（`PaymentLedger`） | 当日账本不是第二张表——`payment.executed` 事件在 `ledger:<date>` 聚合上的读法 |
| `PreparedStatement` + 唯一索引 | append-only 事件表（L5.3 复引） | 账本读不了 → DENY（`ledger_unreadable`）：宁可整单拒绝，不带脏账放行 |
| Spring `@Scheduled` 的 cron 时区坑 | 「当日」窗口用注入 `date` 而非 `datetime.now()` | 时区语义不进业务判断——窗口边界由装配方显式给（§2.6） |

### 2.1 五层风控的⑤收口：产品课见过，今晚自己长出来

L4.3 的风控光谱（研究蓝本 §4.3 的五层图）今晚在**自己的 PoC** 里走完最后一格：

| 层 | 名字 | 一句话 | 在哪见过 → 今晚在哪 |
|---|---|---|---|
| ① | 观点层（prompt 约束） | 系统提示里的风险人格 | 各产品都有——**只是文案，任何合规声称不能建立在这** |
| ② | 决策层（解析校验拦截） | schema 校验失败→哨兵值 | L4.2 TradingAgents → L5.1 的 `plan_gate` 一直在 |
| ③ | 处置层（纯函数 clamp） | 确定性算术裁剪，只缩不放 | L4.1 ai-hedge-fund → 今晚 `clamp_overruns` 的裁剪语义 |
| ④ | 授权层（不可达） | 权限写入口不在 agent 面 | L4.3 mandate → L5.2 审批面（审批人才是授权者） |
| ⑤ | **执行层（fail-closed 门）** | 唯一执行出口的检查链 | **L4.3 产品课读过 → 今晚自己的 `gate.py`** |

研究蓝本 §4.6 的分期也在这收口：第一期「合规骨架」（图+计划+审批+事件溯源）是 L5.1–L5.3；
今晚的执行门是**第二期「受控执行」的核心件**——agent 从「取数+建议」长成「受控付款」。

### 2.2 A7 执行侧二次校验：决策层批了不算数

今晚最重要的一条新纪律（研究蓝本 §2.1 表 A7）：**执行器收口处独立复核审批状态，与决策层
形成纵深防御——只执行 CONFIRMED 状态的审批单，防中间层缺位/被绕过**。落到 `gate.check_intent`
的前两查：

- **审批单在场且 CONFIRMED**：不在场 → `approval_missing`；状态不是 CONFIRMED →
  `approval_not_confirmed`。审批服务说「批了」不算数——执行侧读的是审批回执（A7 的学名）；
- **审批指纹匹配（A6「批的是这版吗」）**：L5.2 的 `content_hash` 在这里归位——submit 批准时
  记下指纹，execute **重算**指纹（`graph.content_hash(advice, total)`，不信在途状态），两个值
  逐字比对：不等 → `approval_content_mismatch`。中间层记错版本、被篡改的回复说「批的是 v1」
  而执行侧算出 v2——门当场拒绝付款（讲义区有接线级测试钉住这条威胁模型）。

为什么决策层批了不算数？因为「批了」这个事实穿过的人越多，走样的面越大：审批面一个 bug、
一次重放、一个被篡改的回复载荷，都可能让「未批」变成「看似批过」。纵深防御的立场是：
**每一层只信自己当场验证过的东西**。L4.3 的原话级纪律今晚一字未改：「宁可误杀一百，不可
带着脏数据放行一笔」。

### 2.3 三态裁决（复引 L4.3）与本课的接线取舍

检查链的裁决对版 L4.3 的三态，本课多了一个可配置的 clamp：

| 裁决 | 触发 | 恢复路径 |
|---|---|---|
| **DENY** | 结构性违规：不可解析 / 审批缺位 / 非 CONFIRMED / 指纹不符 / 黑名单 / 账本不可读 | 没有——不修改合同就永远不可能放行，而 agent 永远改不了合同 |
| **PAUSE_FOR_REAUTH** | 定量超限：单笔 / 当日累计 / 当日频次（`clamp_overruns=False` 缺省） | 人重新授权：升额改的是 Policy（合同），改完**重开新 run** |
| **ALLOW** | 全查通过（`allow`）；或定量超限被裁到限额后放行（`clamped`，带 `clamp_cents`） | 不需要——`paid_cents ≤ amount_cents` 只缩不放 |

两个接线取舍，讲义讲清楚为什么：

- **PAUSE 折叠进 ESCALATE**（不进审批回环）：PAUSE 的语义是「等重新授权」——升额改的是
  Policy 合同、是装配参数，不是图内消息回环能解决的事（回环改不了图运行时的 policy）。
  所以 DENY/PAUSE 都路由到 escalate 哨兵，用**两个枚举码**分家：`REJECT:GATE_DENIED`（结构性，
  没救）与 `REJECT:GATE_REAUTH_REQUIRED`（定量，升额后重开新 run）——审计看码就知道下一步；
- **gate.denied 事件的语义是「没付」**：审计第一问是「付了没」，所以 DENY 与 PAUSE 都落
  `gate.denied`（都是未放行），`payload.action` 再答「三态中的哪一态」——事件粗粒度、
  payload 细粒度，两层各答各的问题。

### 2.4 「LLM 影响力终止于建议」的最终形态

四层合体后数一遍这张图：**planner / drafter 两个 LLM 节点之外，全是确定性代码**——
intake 载单、plan_gate 校验、executor 步进、submit 审批、**execute 执行门**、escalate 哨兵。
L4.1 在 ai-hedge-fund 读过的总纲，今晚在自家 PoC 里长成了完整形状：

- LLM 的输出（计划 JSON、建议单 JSON）每一步都被 schema 门把守（L2.4 纪律的全程贯彻）；
- 建议单只是**建议**：链路②里修订版建议单说 ESCALATE，审批人仍批准——权威在审批面（A1），
  门只再查结构/定量安全。镜像面同样成立：决策层建议 APPROVE 也不构成付款依据——
  没有审批回执，门一律 DENY；
- 付款这个不可逆动作的每一步都有账：`gate.checked`（裁决）→ `payment.executed`（实付）或
  `gate.denied`（未付）——事件表即账本（§3 压轴）。

### 2.5 JAVA-MAPPING.md 的方法论：双目的的兑现物

本教程从 L0.1 第一课就承诺「学员既获得 Python 工程能力，也获得可带回 Java 栈的迁移地图」。
`code/JAVA-MAPPING.md` 就是那张地图的兑现物——每个模式一行：**Python 侧（本 PoC 的模块与
关键 API）/ Java 对应物 / 翻译坑**，可直接作为 Java 侧开发任务的拆解输入（一行 = 一个可派工
的迁移件）。为什么值得单独一课来写：

- **写映射就是复盘**：把「我用过」翻译成「它对应我熟的什么」，每个模式都被迫想到底——
  StateGraph 装配对应 `addNode/addEdge/compile` 还是别的？interrupt 对应接口回调还是异常？
  想不清的地方就是你在 Java 侧要踩的坑；
- **诚实纪律是红线**：Java 对应物只写**从本地克隆核实过**的 API（langgraph4j@`c2cf2e33`、
  spring-ai-alibaba@`f82da0b50`，锚点在文档末尾）；克隆里不存在的对应物老实写「**需自建**」
  + 一句为什么。禁止编造 API 名——一张掺了想象的迁移表比没有表更危险：Java 侧同学会照着
  不存在的类名抄 import；
- **「需自建」的行最有价值**：图版本绑定（拓扑签名）两边框架都没有——这正是你 PoC 里的
  自研件，迁移时要原样移植；标出来，别让它淹没在「框架都替你做了」的错觉里。

### 2.6 新 Python 件：naive vs aware datetime——「当日」窗口为什么不取 now()

（L4.3 §2.7 已讲过 naive/aware 的类型学，此处结课深化：把它用到「当日限额窗口」这个真实决策点上。）

Python 的 `datetime` 默认是 **naive**（不带时区）——它和 Java 的 `Instant`（必然带时区语义）
是两种世界观，§5 坑位专门拆。本课只需要一条纪律的结论：

- 门的「当日」窗口**不依赖 `datetime.now()`**，而是**注入 `today`**（ISO 日期字符串，
  `graph.DEFAULT_TODAY = "2026-09-16"`）：装配方显式给、测试随便改、两次运行可复现——
  对版 L4.3 的 TodaySnapshot 与 L5.3 的事件钟（同一纪律：**边界数据一律注入，
  不取墙钟**）；
- 为什么不用 `date.today()`？三个理由：①时区——`today()` 取本机时区的今天，服务器时区一变，
  「当日」窗口漂移，限额/频次跟着漏判（跨时区主机上「同一时刻」甚至不是同一天）；②可测——
  注入的 date 让「23:59 付款、00:01 再付算不算同一天」变成可写的测试用例，墙钟版只能祈祷；
  ③fail-closed——门的全部输入都该是显式契约，「现在」混进来，同一个 (policy, intent,
  approval, ledger) 就不再永远同一个裁决。

## 3. 动手代码

先 `uv sync`。`code/` 是四层合体（模块地图见 Step 2 的溯源表）：以 L5.3 为底（它已含 L5.1
全部共享件 + 事件层），并入 L5.2 的 `approvals.py`/`api.py` 与图的 interrupt 换芯，再加本课
的 `gate.py`（核心①）与图接线（核心②）；`JAVA-MAPPING.md` 是核心③（Step 4 带读）。

```bash
uv sync
```

### Step 1：零图跑检查链——三态各一幕 + A6/A7 幕 + fail-closed 幕（10 分钟）

```bash
uv run python code/step1_gate.py
```

```text
== Step1 检查链七查：固定顺序、首查命中即停（零图纯函数） ==
policy: 单笔≤200000 分, 日累计≤500000 分, 日次数≤3, 黑名单=['sketchy-mall'], clamp=关
ledger: today=2026-09-16, 已付 2 笔共 240000 分

幕1 ALLOW | 合规小额（审批单 CONFIRMED 且指纹一致）
  -> ALLOW            reason=allow
     detail: 七查通过：90000 分原样放行
幕2 DENY  | 黑名单收款方（双违单：同时超单笔上限——黑名单先查，短路）
  -> DENY             reason=vendor_blocklisted
     detail: sketchy-mall is on the vendor blocklist
幕3 PAUSE | 单笔超上限（定量——clamp 关：暂停等重新授权）
  -> PAUSE_FOR_REAUTH reason=single_over_limit
     detail: 单笔 250000 分 > 上限 200000 分（重新授权或拆单人审）
幕4 DENY  | 审批指纹不符（A6+A7：批的不是这版——执行出口的二次校验）
  -> DENY             reason=approval_content_mismatch
     detail: approved content_hash 'sha256:old-version' != intent 'sha256:demo-v1'（批的不是这版）
幕5 DENY  | 已付清单脏数据（fail-closed——宁可整单拒绝，不带脏账放行）
  -> DENY             reason=ledger_unreadable
     detail: today's ledger entry unparseable: {'vendor': 'airline-co', 'dept': 'SALES', 'category': '差旅'}（fail-closed）
幕6 ALLOW+clamp | 同一笔超限单在 clamp 开启的合同下：裁到上限放行
  -> ALLOW            reason=clamped clamp=200000 分
     detail: 超限裁剪：250000 分 → 200000 分（clamp 只缩不放）

读法：幕2 是短路顺序的证据——同一笔单既进黑名单又超单笔上限，裁决停在黑名单
（结构性先于定量：改数字救不了黑名单，先说没救的事）；幕4 是本课的新查——
决策层「批了」不算数，执行出口把审批指纹与重算指纹逐字比对（A7 纵深防御）；
幕5 是魂——账本读不了，答案不是崩，是 DENY（fail-closed 拒绝的是带脏数据放行）。
```

六幕零图零模型零文件——门是纯函数（对照 L4.3 的 step1_chain 同款形态）：这一步在告诉你，
执行门不依赖任何框架，它是一条你可以在任何栈里复刻的纪律。

### Step 2：读合并后的模块地图——四层各来自哪课（15 分钟）

```text
code/
├── gate.py            ← 本课新增（核心①：纯函数七查）
├── graph.py           ← 四层合体（核心②：submit 写回执 + execute 接门 + 三哨兵 + PaymentLedger）
├── eventstore.py      ← L5.3 + EVENT_TYPES 9→12（登记 gate.checked/payment.executed/gate.denied）
├── approvals.py       ← L5.2 + 可选挂审计层与门三件（store/cache/policy/ledger/today）
├── demo.py            ← L5.2 剧本 + L5.3 run_audited（内置自动批准段）+ run_pipeline 复活
├── api.py             ← L5.2 原样（HTTP 契约不变——test_api 回归为证）
├── step1_gate.py      ← 本课新增（Step 1 脚本）
├── demo_final.py      ← 本课新增（Step 3 三链路压轴）
├── JAVA-MAPPING.md    ← 本课新增（核心③：Step 4 带读）
└── advice / mock_tools / review_rules / mock_endpoint / executor / plan / prompts / audit_cache / versioning
                       ← 对版件（字节相同，diff 可验）
```

逐文件对版（对版纪律：字节相同件 diff 验证，演进件 docstring 声明差异）：

| 模块 | 来自 | 本课差异 |
|---|---|---|
| advice / mock_tools / review_rules / mock_endpoint / executor / plan | L5.1（经 L5.3） | 字节相同 |
| prompts.py | L5.2 | 字节相同（含 approval_feedback_instruction） |
| audit_cache.py / versioning.py | L5.3 | 字节相同 |
| eventstore.py | L5.3 | 词汇表 9→12 类（门三事件登记——封闭词汇表要显式扩）；fold 多三个投影键（gate/paid_cents/gate_denied） |
| graph.py | L5.2 骨架 + L5.3 事件层 + 本课门 | submit 批准后写审批回执、approve 出口 END→execute、新增 route_after_execute 与第三哨兵、PaymentLedger；**RECURSION_LIMIT 20→24**（最坏链 16 步 + 8 步余量） |
| approvals.py | L5.2 | 审批域逻辑字节相同；构造器可选挂 store/cache/policy/ledger/today；剧本消费按**逻辑调用**计（缓存命中不发请求但算一次——否则回环台词错位） |
| api.py | L5.2 | 标题与默认库名（路由/模型/帧全同） |
| demo.py | L5.2 + L5.3 | run_pipeline 复活（内置自动批准段）；run_audited 演进为两段式 + 门三件 |

一个值得停下来的活教材：**图签名必变**。L5.4 的图比 L5.3 多了 execute 节点与两条出边——
拓扑签名从 `5dbfa594e113…` 变成 `58e1ec51d923…`（Step 3 压轴会打出来）。同一单
CLM-2026-0001 的 run_key 因此从 `CLM-2026-0001@5dbfa594e113` 换到 `CLM-2026-0001@58e1ec51d923`：
L5.3 的图版本绑定在这里**自动生效**——旧 checkpoint 不可续、旧聚合续跑被 `GraphVersionMismatch`
拒绝（历史一条不动，作废的是「续跑权」）。改图的代价被机制明码标价，这就是 A15 的意义。

还有一个合并中真实踩到的坑（test_graph 有 meta 断言钉住）：state 新增的 `gate_reject` 键
**漏声明进 TypedDict 时，图会静默丢弃这个更新**——escalate 哨兵读到 None，分码全错还不报错。
schema 是合同，不是文档。

### Step 3：三链路全流程预演——里程碑集成测试的雏形（20 分钟，本课压轴）

```bash
uv run python code/demo_final.py
```

```text
== 链路① 审批暂停→恢复：建 run → interrupt 暂停 → reply once → 门 ALLOW → payment.executed ==
  [start_run 0001 → run-0001] 待审单 tkt-0001 挂在 ['submit']
    （interrupt 暂停——等人的不是线程，是 checkpoint；advice={'decision': 'APPROVE', 'reason': 'PASS', 'remaining_cents': 10000}）
    图内审计流水: ['intake', 'planner', 'plan.approved', 'executor', 'drafter', 'submit.approved', 'gate.allowed', 'payment.executed']
    终态 advice: APPROVE / PASS / paid=7100
    事件流水（CLM-2026-0001@58e1ec51d923，14 条）：
      seq  0  run.started      claim=CLM-2026-0001 graph_version=58e1ec51d923…
      seq  1  intake.loaded    SALES 总额 7100 分
      seq  2  llm.decision     node=planner cached=False
      seq  3  cost.recorded    node=planner prompt=12 completion=8
      seq  4  plan.approved    3 步计划 claim_total=7100 分
      seq  5  tool.called      s1 fetch_claim→claim
      seq  6  tool.called      s2 check_budget→budget
      seq  7  tool.called      s3 verify_invoice→invoice
      seq  8  llm.decision     node=drafter cached=False
      seq  9  cost.recorded    node=drafter prompt=12 completion=8
      seq 10  advice.drafted   APPROVE/PASS 剩余 10000 分
      seq 11  submitted        送审完成
      seq 12  gate.checked     ALLOW/allow 金额 7100 分
      seq 13  payment.executed 王工(SALES) 实付 7100 分
    <- 批准只是授权：submitted 之后 gate.checked→payment.executed——执行出口二次校验过才付款（A7）

== 链路② 拒绝回环：reject+留言 → 回 drafter 重生成 → 新审批单（hash 变）→ 批准 → 过门 ==
  [start_run 0001 → run-0001] 首版建议单 tkt-0001（hash=9a2914bfde8ce4a8）
  [reply reject+留言] 图回 drafter 重生成 → 新单 tkt-0002（hash=fa80fac7933b8af8）
    hash 变了：9a2914bfde8ce4a8 != fa80fac7933b8af8 ——批的是新一版内容（A6）
    图内审计流水: ['intake', 'planner', 'plan.approved', 'executor', 'drafter', 'submit.rejected', 'drafter', 'submit.approved', 'gate.allowed', 'payment.executed']
    终态 advice: ESCALATE / REJECT:APPROVAL_FEEDBACK / paid=7100
    事件流水（CLM-2026-0001@58e1ec51d923，17 条）：
      …（前 10 条同链路①：run.started→advice.drafted 首版）
      seq 11  llm.decision     node=drafter cached=False
      seq 12  cost.recorded    node=drafter prompt=12 completion=8
      seq 13  advice.drafted   ESCALATE/REJECT:APPROVAL_FEEDBACK 剩余 10000 分
      seq 14  submitted        送审完成
      seq 15  gate.checked     ALLOW/allow 金额 7100 分
      seq 16  payment.executed 王工(SALES) 实付 7100 分
    <- 修订版建议单是 ESCALATE（按留言转人工），审批人仍批准——权威在审批面（A1），
       门只再查结构/定量安全；事件表里两条 advice.drafted 就是这次改稿的审计证据

== 链路③ fail-closed 拒绝：超 Policy 单笔上限的提案 → 门不付款 → gate.denied → ESCALATE ==
  [start_run 0002 → run-0001] 提案总额 8800 分 > 紧合同单笔上限 5000 分
    图内审计流水: ['intake', 'planner', 'plan.approved', 'executor', 'drafter', 'submit.approved', 'gate.paused:single_over_limit', 'escalate']
    终态 advice: ESCALATE / REJECT:GATE_REAUTH_REQUIRED / paid=未付款
    事件流水（CLM-2026-0002@58e1ec51d923，11 条）：
      seq  0  run.started      claim=CLM-2026-0002 graph_version=58e1ec51d923…
      seq  1  intake.loaded    SALES 总额 8800 分
      seq  2  plan.approved    3 步计划 claim_total=8800 分
      seq  3  tool.called      s1 fetch_claim→claim
      seq  4  tool.called      s2 check_budget→budget
      seq  5  tool.called      s3 verify_invoice→invoice
      seq  6  advice.drafted   REJECT/REJECT:ITEM_OVER_LIMIT 剩余 10000 分
      seq  7  submitted        送审完成
      seq  8  gate.checked     PAUSE_FOR_REAUTH/single_over_limit 金额 8800 分
      seq  9  gate.denied      PAUSE_FOR_REAUTH/single_over_limit
      seq 10  advice.drafted   ESCALATE/REJECT:GATE_REAUTH_REQUIRED 剩余 0 分
    <- 审批批了、门不放行：定量超限是 PAUSE_FOR_REAUTH（升额改的是 Policy 合同，
       不是图内回环能解决的事）——audit 上 gate.denied 记「没付」，payload.action 记「哪一态」

== 压轴：事件表即账本（当日已付清单 = payment.executed 投影）＋ 图版本 ==
  ledger:2026-09-16 当日已付 1 笔：
    seq 0  CLM-2026-0001  王工(SALES)  7100 分
  <- 限额/频次的「世界状态」就是这条聚合的投影——没有第二张账本表（L5.3 的延续）
  L5.4 图拓扑签名: 58e1ec51d923…（L5.3 是 5dbfa594e113…——多了 execute 节点）
  <- 图一改，run_key 换世界：同一单的旧 checkpoint/旧聚合自动作废（L5.3 图版本绑定的活教材）

（审计库与 checkpoint 都在系统临时目录，演示结束自动销毁——克隆即学，不写学员主目录）
```

每链路盯三件事：**事件流水**（type/seq——append-only 执行史，链路③ 里 `gate.checked →
gate.denied → advice.drafted` 的顺序就是「批了、没付、转人审」的审计叙事）；**终态
advice**（链路③ 是 `REJECT:GATE_REAUTH_REQUIRED`——枚举码告诉你下一步是升额重开）；
**账本**（压轴——当日已付清单是 `ledger:2026-09-16` 聚合上 payment.executed 的投影）。
这三段就是里程碑要长成的 pytest 集成测试（断言点全在 `code/test_final.py` 里，搬过去扩）。

### Step 4：JAVA-MAPPING.md 带读（15 分钟）

打开 `code/JAVA-MAPPING.md` 通读一遍，重点看三类行：

- **框架直接对应**（StateGraph 装配、条件边、interrupt/resume、checkpointer……）：Java 列
  是从本地克隆核实的真实 API——对照 `~/develop/opensource/langgraph4j` 与
  `spring-ai-alibaba` 找到那些类，读一眼它们的测试（文档末尾的锚点给了行号）；
- **「需自建」的诚实行**（图版本绑定、当日账本）：两边框架都没有——这是你 PoC 里的自研件，
  迁移时原样移植，翻译坑列写了为什么不能图省事；
- **留 TODO 的 4 行**（Plan 判别联合、fail-closed 门、缓存即审计、拒绝回环）：这是 ex3
  的补全任务——先自己对照克隆写，再和 `solution/JAVA-MAPPING.md` 对照（差异处才是认知增量）。

### Step 5：讲义区验收（10 分钟）

```bash
uv run pytest code/
```

```text
80 passed in 27.67s
```

80 个讲义区测试 = 门 21（逐查单测七查、三态覆盖 meta「11 种 reason_code 齐 + 三态齐 +
表 11 行」、fail-closed 参数化 None/负数/字符串金额/bool/缺字段、短路顺序双违单、clamp
两态与「裁不动」边界）+ 图接线 8（interrupt payload 形态、批准恢复过门付款、**假指纹整单
DENY**、紧合同 PAUSE 升额码、拒绝回环新 hash、封顶双哨兵、schema 声明 meta）+ 三链路端到端
5（链路①②③ + 图签名变化→run_key 变化 + run_audited 门事件与缓存命中）+ 四单回归 6
（L5.1 系：expect_* 判分 + 0003 纵深防御现场——脏数据单被人批了门也不付）+ 事件表 11
（L5.3 系 9 个 + 日历聚合一等 + 拒付投影）+ 缓存 6 + 执行器 4 + 计划 9 + API 10（L5.2 的
HTTP 契约在合体后原样存活）。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改 TODO 标注区与所需的顶部 import（骨架只预置了 given
部分用到的）。卡住先想 5 分钟，再看渐进提示（在 exercises/ 目录下）：

```bash
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_gate.py` | 检查链补全：统一入口（不可解析即 DENY）+ 定量三查（clamp 语义：超限裁到上限/剩余额度继续查、笔数不可裁）；验收含每查「只破这项」、覆盖型 meta（11 种 reason_code 齐、三态齐、表 11 行）、短路顺序（黑名单先于限额的双违单）、fail-closed 参数化（None/负数/字符串金额/bool 金额/缺字段/脏账本） |
| ex2 | `exercises/ex2_wire.py` | 门入图（复用讲义区真件 `gate.check_intent`）：execute 三出口接线（ALLOW 记账+paid_cents+事件 / DENY/PAUSE 写 gate_reject 交哨兵分码）+ route_after_execute；验收含链路①付款在账、链路③超限未付款且终态 ESCALATE、**审批 hash 不匹配整单 DENY**、clamp 裁剪值、最坏链不炸（RECURSION_LIMIT 足够） |
| ex3 | `exercises/ex3_mapping.py` | 开放设计题·诚实降级：JAVA-MAPPING.md 的校验器（四列齐 + Java 列非空 + TODO 报未填）与行数统计；测试只查结构与统计，不硬造内容判分。**学员任务在文档里**：把 `code/JAVA-MAPPING.md` 的 4 行 TODO 补全（对照本地克隆核实），完整对照版在 `solution/JAVA-MAPPING.md`（行尾 golden answer） |

验收命令同 §1 的完成判据（三条同时全绿 = 本课毕业；发货态 22 个练习测试红、3 个 given/meta 绿）。

## 5. Java 人坑位：天真时间坑

这是本课的命名化失败模式——Python 默认给你的 datetime 是「天真」的，而金融代码里最不该
天真的就是时间。

- **现象**：频次窗口跨时区漏判（同一天的限额被算成两天，多付了）/ 授权永不过期（过期
  判断用了 naive 的「现在」与 aware 的落库时间比）——更阴的版本：本地测试全绿（同一台
  机器同一时区），上服务器（UTC）当天凌晨的单全被拒或全被放。
- **最小复现**（两行，直接 `TypeError`；悄悄错的那种更常见——见下一条）：

  ```python
  from datetime import UTC, datetime

  datetime.now() < datetime.now(UTC)
  # TypeError: can't compare offset-naive and offset-aware datetimes
  ```

  悄悄错的版本：两台不同时区的主机各取一次 `datetime.now()`（都是 naive）传给同一个
  限额服务——「同一时刻」在两边甚至不是同一天，比较**不报错**（naive 比 naive 合法），
  当日窗口因此错位。
- **Java 直觉为何失效**：Java 的 `Instant` **必然**带时区语义、`ZonedDateTime` 显式携带、
  连 `LocalDateTime` 的名字都在警告你「没有时区」——类型系统帮你挡了混比。Python 的
  `datetime` 默认 naive、时区是**运行时属性不是类型**（`tzinfo is None` 与否），混比在
  naive-naive 时还合法——「编译器提示层」与「运行时防线」的错位，Java 人完全没练过。
- **修复与纪律**：①边界数据一律 **aware UTC**——`datetime.now(UTC)`（`UTC` 别名是现代
  写法，ruff UP017 会把老写法 `timezone.utc` 刷成它，L4.3 先例）；②**「当日」窗口不依赖
  `datetime.now()`/`date.today()`，注入 date**——本课 `Policy` 的窗口吃注入的
  `today`（对版 L4.3 的 TodaySnapshot、L5.3 的事件钟：同一纪律第三次出现）——测试才可
  复现、门才 fail-closed 得起来；③序列化统一 `isoformat()`（aware 值自带偏移，落库
  不丢语义）；④跨时区比较前断言 `tzinfo is not None`——fail-closed：读不了时区的时间
  和读不了的账本是同一种脏数据。

## 6. 延伸

- 源码路标（门的产业原型 + Java 侧核实锚，本地克隆 `~/develop/opensource/`，按图索骥）：
  - `HKUDS/Vibe-Trading@f84b2977#agent/src/live/enforcement.py` —— 门的产业原型（L4.3
    精读过）：`check_mandate` 固定顺序八查、任何不可解析输入即 breach——本课
    `gate.check_intent` 的母本，Java 侧照抄检查序列的那张「黑名单→科目→单笔→累计→频次」；
  - `langgraph4j/langgraph4j@c2cf2e33#langgraph4j-core/src/main/java/org/bsc/langgraph4j/StateGraph.java`
    —— Java 侧装配现场：`addNode(String, AsyncNodeAction)` L218、`addEdge` L353、
    `addConditionalEdges(String, AsyncEdgeAction, Map)` L408、`compile()` L452——
    JAVA-MAPPING 第一行的核实锚；
  - `langgraph4j/langgraph4j@c2cf2e33#langgraph4j-core/src/main/java/org/bsc/langgraph4j/action/InterruptibleAction.java`
    —— interrupt 的 Java 形态：`interrupt(nodeId, state, config)` 返回
    `Optional<InterruptionMetadata>`——对照 Python 的 `interrupt()` 像不像「会返回值的
    await」，差异全在 JAVA-MAPPING 第四行；
  - `alibaba/spring-ai-alibaba@f82da0b50#spring-ai-alibaba-graph-core/src/main/java/com/alibaba/cloud/ai/graph/StateGraph.java`
    —— saa 的装配：`StateGraph(KeyStrategyFactory)` L170 + `addNode` L244 + `compile` L535；
    恢复原式在
    `alibaba/spring-ai-alibaba@f82da0b50#spring-ai-alibaba-graph-core/src/test/java/com/alibaba/cloud/ai/graph/InterruptionTest.java`
    ——`workflow.stream(null, RunnableConfig.builder().resume().build())`。
- 研究蓝本（lab 仓内，写作输入）：A7 执行侧二次校验 / A8 fail-closed 决策门三态 / A9
  授权不可达的模式条目见
  [../../../../research/agent-oss/report.md](../../../../research/agent-oss/report.md)
  §2.1 表 A7–A9；§4.3 审批与风控五层（本课=第⑤层的收口）；§4.6 分期落地（本课=第二期
  「受控执行」的核心件）。
- **结业自查表**（CURRICULUM §7 原文收录——逐条对照，全勾即毕业）：
  - [ ] 语言：手写 async 并发 fetcher + retry 装饰器，不查资料（对照 L1.4/L1.6——忘了就回炉，
    顺手把 L5.2 §5 的「事件循环里睡死」讲给自己听）；
  - [ ] 地基：能向别人讲清「一个 agent 循环的一轮发生了什么」（从 API 消息到工具回喂——
    对照 L2.1/L2.2 的手写循环与 Unit 2 的 mini-agent；四层合体后的今天，这张图你在
    demo_final 的事件流水里逐 superstep 又看了一遍）；
  - [ ] 框架：mini-agent vs 四框架决策表能自己重新推导（对照 L3.8 决策表——装配 loc 与
    手写 loc 两列还记得口径吗）；
  - [ ] 产品：完成 3 个产品的指定改造并复现（L4.1 llm/cache.py 精读、L4.2 辩论轮次参数化 +
    预算封顶、L4.3 mandate 检查链抽单测——改造说明和截图都在你本地分支上）；
  - [ ] 毕业：PoC 三条主链路测试全绿，JAVA-MAPPING.md 可作为 Java 侧开发任务拆解输入
    （`code/test_final.py` 的五张测试就是三条主链路的断言版；JAVA-MAPPING 主表 13 行、
    核实锚 8 条、「需自建」2 行——拿去开 Java 侧任务会吧）。

## 离毕业又近的一块

这句话从 L0.1 讲到今晚——今晚之后它退役：**执行门装上，毕业设计四层合体**。图会跑
（静态拓扑 + 计划驱动）、人会批（interrupt 审批 + 三元回复）、账会记（append-only 事件 +
缓存即审计 + 图版本绑定）、门会拦（fail-closed 七查 + 三态裁决）。最后一站是里程碑：
把 §3 的 demo_final 扩成正式的三条主链路集成测试（断言点在 `code/test_final.py` 里都有，
搬过去加密）、JAVA-MAPPING.md 定稿（TODO 四行补全、交一轮 Java 侧同学 review——「核实过
再写」让别人的 review 好做很多）。四课攒的每一块都在那儿了——去把它们钉成毕业证。

