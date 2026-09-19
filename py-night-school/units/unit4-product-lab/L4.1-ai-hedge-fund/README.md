# L4.1 ai-hedge-fund：层级投票——LLM 影响力终止于 Signal

> Unit 3 结业那晚，五框架同题对照跑完，你手里多了一张**自己跑出来的选型决策表**——「为什么
> 用 langgraph」从此有三行证据可引用。Unit 4 换打法：**读真产品、抄真机制**——三个真实的
> 开源金融产品各解剖一课，把机制对版搬进报销域。第一站 virattt/ai-hedge-fund（下称 ahf），
> 它最值得学的不是金融，是一句话：**LLM 只形成观点，确定性代码管钱**——本课把它抽成「报销
> 初审层级投票」机制件（code/ 目录，离线可验收），真跑产品是 §3 末尾的可选加餐。

## 1. 本课目标

今晚对 ahf 做三件事——**跑懂、改对、精读**：

- **跑懂**：说清它的核心拓扑「层级投票」——agent 之间零通信、并行独立对同一快照投票，
  共识不靠对话靠**算术合成**（加权平均，弃权从分子分母同剔），风控是**确定性 clamp**
  （先单笔封顶再总额等比缩，只缩不放，每刀留审计）——并在 `code/` 的报销初审映射里
  亲手跑通这条管线（快照→投票→合成→clamp→回执，全程离线零 key）；
- **改对**：完成三道改造题——自己实现 `weighted_vote` 加权合成（ex1）、`DecisionCache`
  缓存即审计（ex2）、`apply_limits` 双闸门 clamp（ex3），数学精确到分；
- **精读**：按 §6 路标读产品源码的六个文件（run_cycle / construction / limits / cache /
  llm_agent / buffett），每个机制在 `code/` 里都有对版件，读完能回答「为什么共识靠算术
  不靠辩论、为什么缓存即审计、为什么 LLM 影响力必须终止于 Signal」。

**完成判据**：本目录下三条命令同时全绿（`exercises/` 是设计内的 TODO 红）——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 2. 概念讲解

先给全课对照表，再逐个展开：

| 你熟悉的 Java 物 | 今天的 ahf 物 | 一句话差异 |
|---|---|---|
| 抽象类（abstract class，`AlphaModel` 这种 IS-A 层级） | `Reviewer` / 产品的 `AlphaModel`（ABC） | LLM 人格与量化模型**同一个抽象基类**混编——像 `AbstractPricingEngine` 下挂本地规则引擎与远程 AI 引擎 |
| 接口（interface，只关心能不能调用） | 产品的 `LLMClient`（Protocol，L1.2 学过） | Java 里 abstract class 与 interface 的取舍，在 Python 里对应 **ABC vs Protocol**——这里也有 |
| Jackson 的 `FAIL_ON_UNKNOWN_PROPERTIES` | pydantic `ConfigDict(extra="forbid")` | YAML/spec 拼错字段名**加载期炸响**，不是静默吞掉后在交易期暴雷——异常要炸在越早的边界越好 |
| `Object.equals/hashCode` 契约 | `hashlib.sha256` 内容寻址 key | Python 的 dict 相等**不保证序列化字节相等**——缓存 key 想稳，要么规范化序列化、要么根本不序列化（§5 陷阱主角） |
| 规则引擎（Drools）硬规则 | `apply_limits` 纯函数 clamp | 没有 DSL、没有引擎——两个 for 循环 + 一个比例除法，「不可协商」由**纯函数 + 顺序**保证 |
| 审计日志表（append-only AOP 切面） | PromptCache + CycleRecord | 审计不是另建子系统：**缓存文件就是审计记录**，回执就是全量真相——省了一整套存储与一致性成本 |
| `CompletableFuture.allOf` 并发聚合 | 顺序 for 循环「并行独立」 | 独立性是**语义属性**（互不依赖、互不可见），不是执行属性——顺序跑也一样对，想并发随时能并发 |

### 2.1 产品架构总览：三层基金 + 一条管线三种模式

先说一个防坑警告：ahf v2.x 全量重写过——经典 v1（`src/agents/` + LangGraph 结构）已不存在，
网上基于 v1 的旧教程全部失效；本课锚定 v2.2，代码全在 `hedge_fund/` 包里。组织结构三层
（`fund/spec.py` 的 docstring 画的就是这张图）：

```text
FUND      = 资本切片 + 主风控（对合成后的总账 clamp）     FundSpec（YAML mandate）
STRATEGY  = 一队分析师 + 合成政策 + 资本切片（"pod"）      StrategySpec
MODEL     = 一个观点生成器 -> Signal                       AlphaModel 实现
```

MODEL 层是本课主角：**LLM 人格 ×5**（Buffett/Munger/Graham/Lynch/Druckenmiller，每个 =
一个 name + 一段 system prompt，机制全在基类 `LLMAgent`）与**量化模型**（PEAD，纯数学）
实现**同一个 ABC**，对引擎完全可互换——「主观 pod 与量化 pod 同一个 spec 形状」。

执行侧只有一条管线（`pipeline/run_cycle.py`）：

```text
run_cycle: point-in-time 数据 -> analysts 投票 -> blend 合成 -> risk clamp -> 执行 -> 记录
```

**一管线三模式**：回测 = 历史时钟 + SimBroker 循环；「跑今天」= 同一 run_cycle 单 tick；
paper/live（规划中）= 同一循环换时钟换 broker——**回测即生产代码路径**，研究实现与
生产实现永远不会漂移。

以及最反直觉的一条：**无框架**。没有 LangGraph/AutoGen/状态机，主循环就是一条确定性
Python 函数调用链，langchain 只当多厂商传输层用。它故意把 LLM 的作用域压到最小——
这是设计，不是没做。

### 2.2 层级投票 vs 辩论拓扑（预告 L4.2）

两个产品代表了多 agent 共识的两极（课程调研 18 个开源产品后的一致结论）：

| | 层级投票（ahf，本课） | 辩论-裁决（TradingAgents，L4.2） |
|---|---|---|
| 共识怎么来 | 算术：加权平均，代码算 | 对话：多轮辩论，裁判 agent 收束 |
| agent 间通信 | **零**——互相看不见 | 密集——消息驱动 |
| 确定性 | 同输入字节级可重放 | 依赖模型对话质量 |
| 成本 | 一次投票（缓存后 $0） | 对话轮次 × 参与者 |
| 擅长 | 可枚举检查（月结、报销初审） | 需要对抗推理的判断 |

层级投票的代价也直白：agent 不能互相质询，共识质量完全取决于合成权重——所以权重表
是 mandate YAML 的一级字段（改话语权不碰代码），弃权的语义被严格定义（见 2.4）。
调研给出的映射总纲：**低金额可逆（报销初审）走层级投票，快、确定、便宜；需要对抗推理
的场景再叠辩论**。本课把这条拓扑搬到报销初审：合规/预算/发票三个人格检查员 + 一个规则
表量化检查员，并行独立投票，代码加权合成，硬规则 clamp。

### 2.3 风控光谱：本课站在第 ③ 层

调研报告把金融产品的 LLM 风控分成五层（dimensions/A-金融交易组.md §4，模式编号来自
research 报告）：

```text
① 观点层（prompt 里写风险人格）   ② 决策层（schema 校验失败 -> 弃权哨兵）
③ 处置层（纯函数 clamp 限额）     ④ 授权层（mandate 合同/限额授权）
⑤ 最后一道门（fail-closed 执行门）
```

FinRobot（AI4Finance 系的开源金融 agent，调研样本里「宣称 vs 实现落差」的典型——
辩论架构在闭源 V2）停在 ①（风险控制 = 让 LLM 写风险分析文本）；TradingAgents 到 ②；**ahf 到
③**；Vibe-Trading 覆盖 ①—⑤（L4.3 的主角）。本课机制件占两层：LLMCheckerBase 的
「解析失败即弃权 + 原始响应留盘」是 ② 的哨兵语义；`apply_limits` 的确定性 clamp 是
③ 的处置语义——**"conviction requests, risk disposes"**：检查员只能请求，风控用算术
处置，LLM 的影响力到 Vote 为止。

### 2.4 本课新 Python 知识三件

**ABC vs Protocol**。产品两处各用了一个：模型层用 **ABC**（`signals/base.py` 的
`AlphaModel`：`@abstractmethod name/predict`）——因为注册表在运行时枚举全部实现、基类
还携带共享机制（LLMAgent 的缓存与解析流程）；传输层用 **Protocol**（`llm/client.py` 的
`LLMClient`：只有一个 `complete(system, user) -> str`）——只关心能不能调用、谁实现都行。
Java 直觉完美对应：**IS-A 层级用 abstract class，纯能力契约用 interface**。L1.2 学过
Protocol 的结构化类型（不继承也对得上），今晚看产品在同一个包里把两者各用在刀刃上。

**pydantic `extra="forbid"`**。产品 spec 全家（ModelSpec/BlendPolicy/StrategySpec/
FundSpec）都带 `ConfigDict(extra="forbid")`——mandate YAML 拼错字段名在**加载期**抛
`ValidationError`，不是静默吞掉后在交易期暴雷。对照 Jackson 的
`FAIL_ON_UNKNOWN_PROPERTIES`：默认宽容（忽略未知字段，向前兼容），要显式打开才严格。
本课 `ClaimSnapshot` 同款（快照是要哈希、要进审计的数据，多一个字段就该炸）。

**hashlib 内容寻址**。`sha256(规范化内容)` 截 24 位当文件名/缓存 key——同样的内容必然
同 key（免费命中）、内容一变 key 必变（自动失效）。它是「缓存即审计」「同数据不二次
付费」「快照绑定回执」三个设计的共同地基。坑在「规范化」三个字上，§5 专门讲。

## 3. 动手代码

先 `uv sync`。`code/` 是本课的机制抽取件——**对版产品的结构，不是抄产品的域**：把
`hedge_fund/` 的投票/合成/clamp/缓存机制搬到报销初审域（明线四单 review_mock.json 照旧）。
每个文件头 docstring 都标注了它对版产品的哪个文件。模型离线指向 L2.3 服役至今的
`MockLLMEndpoint`（与 L3.2 的 code/mock_endpoint.py 字节相同），剧本在
`pipeline.SCRIPTS`——离线确定、零 key、三态可验收。

### Step 1：权重语义与弃权剔除（10 分钟，零模型调用）

```bash
uv run python code/step1_blend.py
```

```text
== Step1 层级投票的权重语义（零模型调用） ==
[一] 加权合成：conviction = sum(w·score) / sum(w)，弃权票分子分母同剔
  votes      : compliance +0.80 / budget -0.60 / invoice +0.90 / rules 弃权
  weights    : {'compliance': 1.0, 'budget': 0.5, 'invoice': 1.0, 'rules': 1.5}
  conviction = (1.0*0.8 + 0.5*(-0.6) + 1.0*0.9) / (1.0+0.5+1.0) = 0.5600
  voters=['compliance', 'budget', 'invoice']  abstained=['rules']
[二] 对照错误算法：把弃权当 0 分计入分母（捏造中性）
  错误算法 conviction = 0.3500 <- 一个没投票的检查员稀释了 0.16 的确信
[三] 全弃权：显式边界，不捏造中性
  conviction = None  <- None 而非 0.0：pipeline._decide 据此 ESCALATE 转人审
[四] 权重即话语权：同一组票，把 budget 的权重 0.5 抬到 3.0
  conviction = (0.8 + 3.0*(-0.6) + 0.9) / 5.5 = -0.0200  <- 反对票拿到了话语权
  产品对应物：mandate YAML 里的 model_weights（deep-value.yaml 给 graham 2.0 同款操作）
```

对着输出指认三个语义：弃权票从分子**和分母**同时剔除（[二] 演示了「当 0 分」的错误
算法稀释了多少确信）；全弃权返回 `None` 而不是 `0.0`（下游据此转人审，不捏造中性）；
换权重表就是换话语权（[四] 直接翻转结论）。

### Step 2：单细看——全管线五幕（15 分钟）

```bash
uv run python code/demo_trace.py
```

```text
== L4.1 层级投票·报销初审：CLM-2026-0002（离线剧本） ==
== ① 快照（检查员被允许知道的全部；render() 即 user prompt） ==
报销单 CLM-2026-0002（李工，项目验收宴请（单餐超标））。
明细：明细1 8800 分；总额 8800 分。
部门 SALES 剩余预算 10000 分。
发票校验：通过（抬头、税号与报销人一致）。
content_hash = 40c4cdcd8bf630cf575b17cd（model_dump_json 的确定性序列化 -> sha256 截 24 位）

== ② 逐票（零通信：每个检查员独立对同一快照投票，互相看不见） ==
  [compliance ] score=-0.85  prompt_key=8a6132b4…  单餐超单笔上限
  [budget     ] 弃权  reason=parse failed: no parseable JSON in response: '这单预算没问题，我同意。'
  [invoice    ] score=+0.90  prompt_key=39e87266…  发票有效，问题不在发票
  [rules      ] score=-0.95  零 LLM  存在超过单笔上限 5000 分的明细
（剧本台词按调用顺序入队：compliance/budget/invoice；rules 零 LLM）

== ③ 合成（纯算术，弃权从分子分母同剔） ==
  1.0 * (-0.8500) = -0.8500   <- compliance
  1.0 * (+0.9000) = +0.9000   <- invoice
  1.5 * (-0.9500) = -1.4250   <- rules
  conviction = -0.392857

== ④ 风控 clamp（先单笔封顶再总额等比缩，只缩不放） ==
  max_single_cents: 明细1 8800 -> 5000 分
  金额: 8800 -> 5000 分

== ⑤ 回执（ReviewRecord——对版 CycleRecord 的「一个 tick 的完整真相」） ==
  REJECT / REJECT:ITEM_OVER_LIMIT / 剩余预算 10000 分
  留档: 每票 reasoning+prompt_key、合成前后金额、clamps——回放免费
  模型请求: 3 次（3 个人格各 1 次；rules 0 次；缓存目录 3 个 JSON）
  备注: 本单 budget 的剧本台词不含 JSON -> parse_error 留盘（Step2 看那颗文件）
```

这张单是教学密度最高的一单：预算检查员的剧本台词故意不含 JSON——你看它**弃权**且
`parse_error` 留盘（风控光谱②的哨兵语义）；规则检查员零 LLM（量化模型与人格混编）；
单笔超标先被 clamp 到 5000（③的处置语义）然后整单 REJECT——**clamp 记账与最终结论
互不替代，回执两头都要有**。可以换单号再看三张：`uv run python code/demo_trace.py CLM-2026-0003`。

### Step 3：四单全跑 + 讲义区验收（10 分钟）

```bash
uv run python code/demo.py
```

```text
== L4.1 层级投票·报销初审：四单全跑（离线剧本） ==
权重表: {'compliance': 1.0, 'budget': 1.0, 'invoice': 1.0, 'rules': 1.5}（rules 是零 LLM 的量化检查员）

-- CLM-2026-0001（王工，客户拜访：交通 + 工作餐）hash=50accaff --
  compliance  +0.80 请求  (交通与工作餐属合理开支…)
  budget      +0.75 请求  (总额远低于剩余预算…)
  invoice     +0.90 请求  (发票校验通过…)
  rules       +0.85 规则表  (五条硬规则全部未命中…)
  合成: conviction=+0.8278（弃权 0 票已从分子分母剔除）
  clamp: 无
  回执: APPROVE / PASS / 金额 7100 -> 7100 分 / 剩余预算 10000 分 / 模型请求 3 次

-- CLM-2026-0002（李工，项目验收宴请（单餐超标））hash=40c4cdcd --
  compliance  -0.85 请求  (单餐超单笔上限…)
  budget      弃权      (abstained: parse failed: no parseabl…)
  invoice     +0.90 请求  (发票有效，问题不在发票…)
  rules       -0.95 规则表  (存在超过单笔上限 5000 分的明细…)
  合成: conviction=-0.3929（弃权 1 票已从分子分母剔除）
  clamp: [ClampEvent(limit='max_single_cents', item='明细1', before=8800, after=5000)]
  回执: REJECT / REJECT:ITEM_OVER_LIMIT / 金额 8800 -> 5000 分 / 剩余预算 10000 分 / 模型请求 3 次

-- CLM-2026-0003（赵工，打车费冲账（录入了负数））hash=ac5bc43d --
  compliance  -0.60 请求  (负数金额疑似录入错误…)
  budget      +0.55 请求  (总额为负不占预算…)
  invoice     +0.70 请求  (发票本身有效…)
  rules       -0.95 规则表  (明细含非正数金额，数据可疑…)
  合成: conviction=-0.1722（弃权 0 票已从分子分母剔除）
  clamp: 无
  回执: ESCALATE / REJECT:INVALID_AMOUNT / 金额 -500 -> -500 分 / 剩余预算 40000 分 / 模型请求 3 次

-- CLM-2026-0004（钱工，展会物料采购（发票校验未过））hash=b77626a0 --
  compliance  +0.65 请求  (展会物料采购属正常开支…)
  budget      +0.70 请求  (总额在剩余预算内…)
  invoice     -0.95 请求  (发票已作废不能报销…)
  rules       -0.95 规则表  (关联发票校验未通过…)
  合成: conviction=-0.2278（弃权 0 票已从分子分母剔除）
  clamp: 无
  回执: REJECT / REJECT:INVOICE_INVALID / 金额 5000 -> 5000 分 / 剩余预算 40000 分 / 模型请求 3 次

缓存目录留档: 12 个 JSON（一决定一文件=缓存即审计，Step2 细看）
```

四单结论与 data 的 expect_* 全对上（0003 是决策门的短路顺序：脏数据优先转人审，即便
conviction 是负的）。然后跑讲义区验收——

```bash
uv run pytest code/
```

```text
...................                                                      [100%]
19 passed in 6.40s
```

19 个测试 = blend 4（加权精确断言/弃权同剔/全弃权与权重全零的 None 边界/换权重变结果）+
cache 4（第二趟零 HTTP/parse_error 留盘/损坏当 miss/key 内容寻址）+ limits 3（先单后总
与事件顺序/只缩不放与 floor/幂等）+ 管线 3（四单端到端/rules 零 LLM/决策门边界）+
ABC 契约 2（抽象类不可实例化与队伍对齐/人格即 prompt）+ 快照与规则表 3（hash 稳定且
敏感/规则表五条走查/机制件行数 meta）。

### Step 4：缓存即审计——同单跑两遍（10 分钟）

```bash
uv run python code/step2_cache.py
```

```text
== Step2 缓存即审计：同一张单跑两遍 ==
[第一遍 冷缓存] 模型请求 3 次（compliance/budget/invoice 各一；rules 零 LLM）
[第二遍 同缓存目录] 模型请求 0 次（ep2.requests 为空——想花钱都没门）
  三个人格票 cached 标记: [True, True, True]
  回执一致: advice=True / conviction=True

[缓存目录] 3 个 JSON——一决定一文件：
  00f5aaa33a5370fddf732cdf.json  checker=compliance  parsed  claim_hash=50accaff…
  a237b5bdbd2ecc3be04f2f2c.json  checker=budget      parsed  claim_hash=50accaff…
  a2e07901dda5df10f9fa1529.json  checker=invoice     parsed  claim_hash=50accaff…
  每颗文件同时是缓存条目、审计记录（system/user/response 全在）、调试踪迹

[调试踪迹] CLM-2026-0002 的 budget 票：台词不含 JSON -> 弃权 + 留盘
  budget 票: abstained=True  score=0.0
  留盘文件: parse_error=no parseable JSON in response: '这单预算没问题，我同意。'…
  原始响应原样在盘: response=这单预算没问题，我同意。（重放/排查两不误）
```

第二遍的端点**连剧本都没装**——任何请求都会 500，`ep.requests` 为空就是「零请求」的
铁证。这是产品「回测重跑一遍 $0」的机制在报销域的同构：缓存文件同时是审计记录
（合规问「当时模型看到了什么、说了什么」，打开 JSON 就是原话）。注意教学版纪律：
缓存目录必须注入（测试 tmp_path / 演示 TemporaryDirectory），产品默认写
`~/.hedge-fund/cache/llm/`——机制同款，落点改了。

### Step 5：clamp 三纪律（10 分钟，零模型调用）

```bash
uv run python code/step3_limits.py
```

```text
== Step3 风控 clamp：conviction requests, risk disposes ==
幕一 单笔封顶：只有一笔超单笔上限，一刀砍到上限，一刀一事件
[幕一] 明细={'A': 8800, 'B': 1200} 单笔上限=5000 总额上限=10000
  clamp: max_single_cents     A        8800 -> 5000 分
  结果: {'A': 5000, 'B': 1200}（缩后总和 6200 分）
幕二 先单后总：两笔各自超单笔上限，封顶后总额仍超，再等比缩
[幕二] 明细={'A': 8000, 'B': 6000} 单笔上限=5000 总额上限=8000
  clamp: max_single_cents     A        8000 -> 5000 分
  clamp: max_single_cents     B        6000 -> 5000 分
  clamp: max_dept_total_cents （批次级）    10000 -> 8000 分
  结果: {'A': 4000, 'B': 4000}（缩后总和 8000 分）
  <- 顺序即语义：先砍单笔 [5000,5000]，总额 10000 仍超 8000，等比缩 0.8 -> [4000,4000]
     缩只会变小，缩完不会重新违反单笔上限——这对组合因此幂等
幕三 只缩不放 + 幂等：不该动的金额一个不动；跑两遍结果一致
[幕三a 低于两道上限] 明细={'A': 3000, 'B': 800} 单笔上限=5000 总额上限=4000
  结果: {'A': 3000, 'B': 800}（缩后总和 3800 分）
[幕三b 幂等] 再跑一遍幕二的结果: amounts={'A': 4000, 'B': 4000} clamps=[]
  <- 全等且零事件；被砍金额不重分配——留在预算里（对版「留在现金」）
```

产品 `risk/limits.py` 全文 82 行（wc -l 口径）干的就是这三幕。注意「被砍金额不重分配」
的反直觉：把 A 砍掉的钱补给 B 听起来更「公平」，但那等于让风控阶段获得了**加钱**的
能力——与它的职责正好相反。ex3 让你亲手把这三纪律写一遍。

### Step 6（可选加餐）：真跑 ai-hedge-fund

本课主线是机制抽取件，产品本身跑不跑不影响毕业。想跑（需要两个 key：行情数据的
[financialdatasets.ai](https://financialdatasets.ai) 与任一 LLM 厂商）：

```bash
git clone https://github.com/virattt/ai-hedge-fund.git
```

在克隆目录里安装（pipx 与 uv tool 都行；产品 README 的开发路径是 poetry）：

```bash
uv tool install . --force
```

配好环境变量再跑单周期（PowerShell 用 `$env:` 语法）：

```bash
export FINANCIAL_DATASETS_API_KEY=<你的行情 key>
export HEDGE_FUND_LLM_MODEL=gpt-5.6
export OPENAI_API_KEY=<你的 key>
export OPENAI_API_BASE=<你的 OpenAI 兼容端点>
aihf ~/.hedge-fund/mandates/example.yaml --tickers AAPL,MSFT
```

三个细节：模型 id 由 `HEDGE_FUND_LLM_MODEL` 指定，provider 由 `llm/registry.py` +
`api_models.json` 路由——**未登记的 id 默认走 Anthropic 传输**，所以指向兼容端点最稳
的是选 registry 里 provider=OpenAI 的 id（如 gpt-5.6），再用 `OPENAI_API_BASE` 覆盖
传输地址（`llm/client.py` 只在这一处读它）；无参 `aihf` 进 TUI（交互式建基金）；
带 mandate 参数则非交互跑单周期，完整 `CycleRecord` JSON 打到 stdout——**对着本课
ReviewRecord 的五个字段读它**，一眼能认出 signals/clamps/final_weights 的对版位置。

跑通后的两个观察动作（改代码在本课只做观察，真正的「改造产出」留给 Unit 4 里程碑）：

- 改人格：编辑 `hedge_fund/signals/buffett.py` 的 system prompt（比如把「估值」检查项
  权重调到第一），重跑看 buffett 的 Signal reasoning 变不变——人格=一个 prompt 的直接
  证据；
- 改话语权：编辑 mandate YAML 里某个 model 的 `weight:`（参照
  `hedge_fund/strategies/deep-value.yaml` 给 graham 2.0 的写法），重跑看合成 conviction
  怎么动——Step1 第 [四] 幕的真产品版。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改 TODO 标注区与所需的顶部 import（骨架只预置了 given
部分用到的）。卡住先想 5 分钟，再看渐进提示（hints.py 在 exercises/ 目录下）：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_weights.py` | blend 加权投票：加权合成算术 + 弃权从分子分母同剔 + 全弃权/权重全零的 None 边界；验收含小数精确断言与「换权重变结果」meta |
| ex2 | `exercises/ex2_cache.py` | DecisionCache：sha256 内容寻址 key + get/put 文件读写 + parse_error 原始响应留盘；验收断言第二次 review 零模型调用 |
| ex3 | `exercises/ex3_limits.py` | apply_limits + ClampEvent：先单后总顺序 + 只缩不放（floor）+ 事件对账 + 双跑幂等 |

三题都是「机制重写题」：讲义 `code/` 里的 blend.py / cache.py / limits.py 是能跑的参照
（结构相同、你可以先读它们），但 TODO 区必须自己写——验收测试只认你自己文件里的实现。
每题测试数：ex1 五个 / ex2 五个 / ex3 四个（docstring 里的判据与断言逐条对齐）。

验收命令同 §1 的完成判据（三条同时全绿 = 本课毕业）。

## 5. Java 直觉陷阱：相等不等哈希（缓存永不命中）

这是本课的命名化失败模式——Java 人的直觉是「相等的对象哈希必然相同」（equals/hashCode
契约），在 Python 的内容寻址缓存里这层保证**不存在**。

- **现象**：缓存永不命中——同一张报销单审两遍，第二遍照样全价调模型（对产品就是回测
  重跑照付钱）；或者更阴的版本：命中率时好时坏，取决于字典是哪条代码路径构建的。
  测试单跑全绿、并发跑偶发「缓存穿透」，没人往「相等的东西哈希不同」上想。
- **最小复现**（真实可跑，两段输出是实跑结果）：

  ```python
  a = {"checker": "compliance", "model": "m", "system": "s", "user": "u", "extra": 1}
  b = {"extra": 1, "user": "u", "system": "s", "model": "m", "checker": "compliance"}
  print(a == b)        # True —— dict 相等与插入序无关
  h1 = sha256(json.dumps(a).encode()).hexdigest()[:16]
  h2 = sha256(json.dumps(b).encode()).hexdigest()[:16]
  ```

  ```text
  a == b: True
  sha256 前 16 位: 2a31eb20bd17dfda vs f335083fb38856b5 -> 不相等
  ```

  `a == b` 为 True，但 `json.dumps` 按插入序序列化，两个相等的 dict 产出**不同的字节**，
  于是不同的哈希、不同的缓存文件名——两份付费，两份留档。
- **Java 直觉为何失效**：`HashMap` 的 equals/hashCode 契约保证相等对象落同一个桶——
  哈希是**对对象身份**的；而内容寻址缓存哈希的是**序列化字节**，Python 的 `json.dumps`
  对 dict **没有键序规范化的承诺**（键序=插入序，ensure_ascii/分隔符还有默认值）。
  「相等」与「序列化相等」之间有一条 Java 里不存在的缝。pydantic 也一样：
  `model_dump_json` 按字段声明序序列化——同一个类、同一条构造路径才稳定，塞进去一个
  插入序不同的 dict 字段照样踩坑。
- **修复与纪律**：三选一，按场景挑。① 显式规范化：`json.dumps(x, sort_keys=True,
  separators=(",", ":"))`——上面复现加两个参数后两串哈希全等（`a93bf2c8213f3c4d`）；②
  压根不序列化 dict：产品 `llm/cache.py` 的 key 是 `f"{agent}|{model}|{system}|{user}"`
  字符串拼接——字符串拼接天然确定，「相等不等」问题从根上不存在（§3 Step4 那 24 位
  hex 文件名就是这么来的）；③ 像本课快照：固定类 + `model_dump_json`（声明序），并让
  **构造路径唯一**（`build_snapshot` 只有一条路）。最后一条纪律：给内容寻址 key 写
  「同输入同 key」的测试（本课 test_demo.py 的 key 决定性测试、ex2 的验收都在守这条线）。

## 6. 延伸

- 源码路标（本地克隆 `~/develop/opensource/ai-hedge-fund`，HEAD 即此 commit，按图索骥；
  本节引用的行数均为 `wc -l` 口径，与 §3 Step5 的标注同一口径）：
  - `virattt/ai-hedge-fund@fc1bf25#hedge_fund/pipeline/run_cycle.py` —— 管线心脏：一条
    确定性函数调用链怎么组织「数据→投票→合成→风控→执行→记录」，以及「唯一不纯的一块」
    的自我定位（docstring 值得逐行读）；
  - `virattt/ai-hedge-fund@fc1bf25#hedge_fund/portfolio/construction.py` —— blend_signals：
    本课 weighted_vote 的母本——弃权从分子分母同剔的那四行，加上「假中性会稀释确信」的
    注释；
  - `virattt/ai-hedge-fund@fc1bf25#hedge_fund/risk/limits.py` —— apply_limits：82 行的
    硬闸门——先单后总、只缩不放、不重分配、每刀 ClampEvent，ex3 的对照原件；
  - `virattt/ai-hedge-fund@fc1bf25#hedge_fund/llm/cache.py` —— PromptCache：48 行三合一
    （缓存=审计=调试踪迹），key 拼接与「损坏当 miss」的宽容语义都在；
  - `virattt/ai-hedge-fund@fc1bf25#hedge_fund/signals/llm_agent.py` —— LLMAgent 基类：
    查缓存→调用→extract_json→校验→弃权的全部机械，与「数据错误传播、模型错误弃权」的
    失败契约（locked decisions 注释）；
  - `virattt/ai-hedge-fund@fc1bf25#hedge_fund/signals/buffett.py` —— 人格的全部本体：
    一个 name + 一段 system prompt（检查清单 + JSON schema），「人格即 prompt」的证据；
  - `virattt/ai-hedge-fund@fc1bf25#hedge_fund/signals/base.py` —— AlphaModel ABC 与
    QuantModel：LLM 人格与量化模型同接口混编的地方，§2.4 ABC vs Protocol 的现场；
  - `virattt/ai-hedge-fund@fc1bf25#hedge_fund/fund/spec.py` —— 三层 spec 全家
    extra="forbid"：YAML 拼错加载期炸响的纪律，以及「spec 即数据」的 mandate 哲学。
- 官方文档：产品 README（安装与 aihf 用法）https://github.com/virattt/ai-hedge-fund ；
  设计哲学原文 VISION.md（"The backtest is the live system" / "The LLM never touches the
  trade" 两条不妥协原则的出处）
  https://github.com/virattt/ai-hedge-fund/blob/fc1bf250ead209ae5f02c39c3d0062c4bb554505/VISION.md 。

## 离毕业又近的一块

今晚的三个机制直接长进毕业设计：层级投票 + clamp 就是 L5.1 执行器「取数→分析→生成
建议单→送审」确定性管线的投票段——固定拓扑、纯函数合成、数字全部代码算；apply_limits
的 clamp 是 L5.4 fail-closed 执行门「限额裁剪」的直接先例（先单后总、只缩不放、每刀
留事件）；缓存即审计是 L5.3「每个 LLM 决策可回放」的最经济实现——audit log 不用另建
子系统，缓存文件就是审计记录（模式编号来自 research 报告的推荐架构，到 Unit 5 逐一对
号）。下一课 L4.2 换 TradingAgents：共识从算术换成辩论——你会开始想念今晚的确定性。
