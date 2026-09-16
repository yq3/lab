# L4.3 Vibe-Trading：治理合规——fail-closed 门、哈希链与对账不重发

> Unit 4 收官课。三个产品同一条递进线：L4.1 无框架纯 Python、L4.2 LangGraph 实战、
> 本课治理合规架构——前两课你在「读产品怎么想」，这一课读「产品怎么**不敢出错**」。
> 全课零框架零网络零模型调用：机制件只用标准库（dataclasses / json / hashlib / pathlib /
> datetime），连 Pydantic 都不用——这不是省事，是产品的刻意取舍（§2.4），本课照做并讲清为什么。

## 1. 本课目标

读完 Vibe-Trading 治理三件套的源码思想，并在**报销付款域**（付款＝高金额不可逆动作，
金额一律整数「分」）复刻它们。完成后你能：

- 读懂三件套：`live/enforcement.py` 的 fail-closed 固定顺序检查链、`governance/ledger.py`
  的哈希链防篡改账本、`live/pending_action.py` 的「先标记后提交 + 对账不重发」；
- 用 mock 券商连接器（`Broker` ABC + `MockBroker`）把 mandate 检查链抽出写成 pytest 单测
  ——本课三道改造题干的就是这件事的付款域版；
- 说清**授权不可达**（产品的「命门不变量」）：为什么 agent 侧模块里干脆**没有**
  `save_mandate`，为什么这是结构性保证而不是 prompt 级保证；
- 用风控光谱给 Unit 4 收口：①观点层 → ②决策层 → ③处置层 → ④授权层 → ⑤执行层，
  L4.1（ai-hedge-fund）停在 ③、L4.2（TradingAgents）停在 ②、本课（Vibe-Trading）到
  ④⑤——三课正好把光谱走完整。

**完成判据**：本目录下三条命令同时全绿（发货态：`code/` 讲义区绿，`exercises/` 是设计内的红）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 2. 概念讲解

先给全课对照表，再逐个展开：

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| record（不可变 DTO + 紧凑构造器） | `@dataclass(frozen=True)` | 不可变字段同款；但没有紧凑构造器（用 `__post_init__` + `object.__setattr__` 补）、没有解构模式匹配——「零验证面」正是产品要的（§2.4） |
| Bean Validation（`@NotNull` + Validator） | Pydantic BaseModel | 边界校验器：L2.4 出口把关用它；**合同对象反而不用它**——验证面＝可利用面 |
| checked exception（编译器强迫 catch） | 不存在——`except` 是裸的 | fail-closed 的语义责任全在你：`except` 的出口写 DENY 还是放行，没有任何工具盯着（§5 全课最大坑） |
| private 方法 / 模块访问边界 | **函数干脆不存在**（没有 `save_mandate`） | 授权不可达不靠访问修饰符，靠写路径物理缺席——被劫持的 agent 连试都没得试 |
| 审计表 + DBA 权限 | 哈希链 JSONL 账本 | append-only + `prev_record_hash` 传播性：改/删任何一条历史，其后整条链都断（§2.5） |
| 幂等消费 / JMS `JMSXGroupID` 去重 | `ref_id` 幂等键 + 对账不重发 | 付款域的铁律：**重试＝双倍付款**；恢复靠取证（by exact identity），永不靠重发 |
| `Instant`（必然带时区）vs `LocalDateTime` | aware `datetime` vs naive `datetime` | naive/aware 在 Python 是**运行时属性不是类型**——两者一比较直接 TypeError（§2.6） |
| 注入 `Clock`（测试可控时间） | `clock: Callable[[], datetime]` 参数 | 同款思想：生产给系统钟、测试给固定钟；检查链本身**绝不自己取时钟** |
| kill switch / 熔断开关（服务注册中心旗标） | `HALT` 文件哨兵 | 文件存在即停，payload 损坏仍算停——独立于 LLM/SSE/主循环存活的物理制动 |

### 2.1 风控光谱：Unit 4 三课收口

把「风控嵌在管线哪一层」画成一张光谱，八个开源产品各归其位——Unit 4 三课正好按它收口：

| 层 | 名字 | 一句话 | 代表 |
|---|---|---|---|
| ① | 观点层（prompt 约束） | 系统提示里的风险人格 / 检查清单 | 四个产品都有（TradingAgents 风险辩手、Vibe 的 CRO preset） |
| ② | 决策层（解析校验拦截） | 输出 schema 校验失败 → 哨兵值/弃权，绝不静默降级 | TradingAgents（L4.2 读过的 REVIEW 哨兵值） |
| ③ | 处置层（纯函数 clamp） | 确定性算术裁剪 LLM 产出，只缩不放 | ai-hedge-fund `risk/limits.py`（L4.1 的 `apply_limits`） |
| ④ | 授权层（不可达） | 权限/限额写入路径物理上不在 agent 可调用面内 | 仅 Vibe-Trading（本课） |
| ⑤ | 执行层（fail-closed 门） | 唯一执行出口上的检查链 + kill switch + 对账不重发 | 仅 Vibe-Trading（本课） |

逐课归位：L4.1 停在 ③、L4.2 停在 ②、本课到 ④⑤。光谱的结论值得抄进你的笔记本：
**① 只是文案，任何合规声称不能建立在这**；② 是输入卫生；③④⑤ 职能不同必须齐备——
③管「量」、④管「权」（谁能批多少、授权有效期）、⑤管「不可逆动作的最后一道门」。
映射到报销付款域（dimensions 官方映射原话）：「高金额不可逆（付款）无论前面用什么拓扑，
终点必须是 proposal 无权 + 代码门裁决 + mandate 授权 + 哈希链问责」。

### 2.2 fail-closed vs fail-open：门的两种脾气

- **fail-closed（本课的门）**：任何不可解析输入、缺数据、组件故障 → 拒绝。宁可误杀一百
  （用户重新提交），不可带着脏数据放行一笔。产品的原话级纪律：「Any unparseable input,
  missing market data, or ambiguous field **denies** the order rather than waving it through」。
- **fail-open（产品的 advisory 层）**：门**外**的观察性风险意见（外部 /review 服务）——
  provider 挂了订单照走（`REVIEW_UNAVAILABLE`）、默认关、**绝不阻塞**。

两者同时存在于产品里，靠「权威分离」划清边界：advisory never block; mandate gate remains
the sole authority。为什么 advisory 必须 fail-open？因为它如果会阻塞，一个外部服务的
可用性就变成了下单链路的可用性——那不是风控，是单点故障。反过来，**门**必须 fail-closed：
门 fail-open 的下场见 §5（DB-GPT 四缺陷先例）。Java 对照：checked exception 曾强迫你
「要么 catch 要么 throws 声明」，catch 了就得写清楚恢复策略；Python 的 `except` 是裸的，
「检查链任何一处 `except Exception: return None`」没人拦你——fail-closed 在 Python 里
是一种**你要主动写测试钉死的纪律**，不是语言给的。

### 2.3 三态裁决：DENY / PAUSE_FOR_REAUTH / ALLOW

检查链返回 breach 时带 `kind` 两值，门按 kind 路由：

- **structural（结构性违规）→ DENY**：黑名单、科目不在白名单、授权过期。共同点：
  不修改合同就永远不可能放行——而 agent 永远改不了合同（§2.4）。没有恢复路径，直接拒。
- **quantitative（定量违规）→ PAUSE_FOR_REAUTH**：单笔超限、当日累计超限、日次数超限。
  合同本身没错，是这笔交易要的量太大——暂停，等用户重新授权（升额或拒绝）。
- **无 breach → ALLOW**：转入 pending 执行流程（§2.7）。

注意 DENY 和 PAUSE 都是「不放行」——fail-closed 不因裁决温和而打折。产品同名常量
`PAUSE_FOR_REAUTH` 直译「暂停等待重新授权」，它不是「先放行再补手续」。

### 2.4 frozen dataclass vs Pydantic vs Java record：零验证面

产品的 mandate 四件套（HardCaps / UniverseConstraint / ConsentMeta / Mandate）用
`@dataclass(frozen=True)`，**刻意不用 Pydantic**，源码注释写明动机：mandate 只在启动时
读一次、之后永不变化，frozen dataclass 给出最强不可变保证，且**零验证面**（zero
validation surface）——Pydantic 的宽松解析/强制转换（`"200000"` 能变 200000、能填默认值）
对「给 agent 读的合同」是**可利用的解析空间**，不是便利。分工表：

| | Pydantic | frozen dataclass | Java record |
|---|---|---|---|
| 用在哪 | **边界**：LLM 输出、外部 payload（L2.4 的出口把关） | **合同/内部值对象**：读一次永不变 | 两者都常用来做 DTO |
| 校验 | 有（coerce + 默认值——边界友好，合同危险） | 无（错了就崩，fail-closed 反而喜欢） | 无（紧凑构造器可手写检查） |
| 不可变 | `frozen=True` 可选 | 天生（改字段抛 `FrozenInstanceError`） | 天生 |
| 缺什么 | — | 紧凑构造器（用 `__post_init__` + `object.__setattr__` 补，见 `code/mandate.py` 的默认 30 天过期）、模式匹配 | 无关（这是 Python 侧的取舍） |

Java 人最该带走的一句：**给 agent 读的合同对象不要留可利用的解析空间**——record 的
紧凑构造器如果要加校验，也只加「让坏输入构造失败」的，不加「帮坏输入修复成好输入」的。

### 2.5 哈希链账本：防篡改审计

每条记录嵌入 `seq`（位置）与 `prev_record_hash`（前一条的哈希；首条用哨兵
`sha256:genesis`），再把「位置 + 前驱 + 载荷」一起摁进自己的 `record_hash`。于是**改/删
任何一条历史，其后整条链全部失效**——让篡改可检测的是这个传播性，不是逐行校验和。
（这就是区块链的前两页：一条链、每块带前块哈希；后页的共识/挖矿与本课无关，一句话
带过。）三条配套纪律：

1. **canonical JSON**：`sort_keys=True + separators=(",", ":")` 把同一个 dict 永远序列化
   成同一串字节——这是 L4.1「相等不等哈希」坑（dict 顺序不定导致哈希漂移）的正解：
   **先规范化，再哈希**；
2. **append 前整链先验，断链拒写**（`LedgerCorruptionError`）：绝不往被篡改的历史上
   续建合法后缀——O(n) 换最强保证，合规账本低频写，付得起；
3. **轮转绝不删历史**：老段归档，链跨段延伸。

### 2.6 对账不重发：崩溃安全

付款重试＝双倍付款，所以 mutation **永不自动重试**（产品 `repeatable=False`）。安全顺序：

```text
门裁决 ALLOW → 落盘 crash-safe 标记（tmp + os.replace）→ broker.pay(ref_id) → 删标记
                    ↑ 落盘失败 → DENY，零 broker 调用
崩溃恢复（标记还在盘上）：
  broker.get_payment_by_ref(ref_id) 查得到 → 审计后关闭窗口（删标记）
  查不到                              → 标记保留，NEEDS_MANUAL_REVIEW 等人
  —— "Resolve ... by exact identity, never by resubmission"（产品 sdk_order_gate.py 恢复函数 docstring 原话）
```

为什么标记必须**先于**提交落盘：标记写失败时你还没碰外部世界（安全地拒）；反过来就存在
「款已付出、本地毫无记录」的崩溃窗口——对账连 ref_id 都不知道。`ref_id` 是幂等键（对版
产品的 `client_order_id`）：broker 侧同 ref 不重复入账。Java 人可对照 JMS 的幂等消费，
但注意方向：这里**没有**死信重投，查无证据就停在人工——自动化宁可停也不双倍付款。

### 2.7 新 Python 知识（给 Java 人的三件）

- **frozen dataclass ≈ record，但没有紧凑构造器**：字段归一化用 `__post_init__` +
  `object.__setattr__`（frozen 实例普通赋值会抛 `FrozenInstanceError`，绕过它只能走
  `object.__setattr__` 这个后门——本课 `code/mandate.py` 的「expires_at 默认 +30 天」就是它）；
- **`dataclasses.replace(obj, field=new)`**：不可变对象的「拷贝改字段」——Java record 没有
  内建等价物（你大概写过 `withXxx()` 或 builder）。注意**replace 会重跑 `__post_init__`**：
  传 `expires_at=None` 会按新的 `created_at` 重取默认——`code/test_demo.py` 的过期用例
  注释里就点名了这个点；
- **datetime 时区：naive vs aware**。`datetime(2026, 9, 16, 12, 0)` 是 naive（没有时区
  信息），`datetime(..., tzinfo=UTC)` 是 aware——**这是运行时属性不是类型**，pyright 分不出
  来；naive 和 aware 一比较直接 `TypeError: can't compare offset-naive and offset-aware
  datetimes`。Java 对照：`LocalDateTime`（naive）/`Instant`（必然 UTC）是**不同的类型**，
  编译器帮你拦；Python 全靠纪律。本课纪律：凡是时间，一律 aware UTC（`datetime.now(UTC)`
  / ISO 串解析后 `tzinfo is None` 就补 UTC），`expires_at` 从头到尾 aware；顺带 `Z` 后缀
  （`...Z`）不是 `fromisoformat` 在所有版本都认的写法，产品代码统一 `.replace("Z", "+00:00")`。

## 3. 动手代码

先 `uv sync`（本课**零运行时依赖**——pyproject 的 dependencies 是空的，只有 dev 组；
对齐产品哲学：机制件纯标准库，`.env` 三变量本课主线用不上，见 `.env.example` 注释）。
`code/` 七个机制件 + 四个讲义脚本 + 讲义区测试：

```text
mandate.py      授权合同四件套 + load_mandate（刻意没有 save_mandate）
enforcement.py  check_payment 七查纯函数（对版产品八查）
gate.py         PaymentGate 六步 ceremony（对版 sdk_order_gate）
broker.py       Broker ABC + MockBroker（可注入故障的确定性 mock）
halt.py         HALT 文件哨兵（存在即停，损坏仍停）
ledger.py       HashLedger 哈希链账本（append 前整链先验）
pending.py      PendingPaymentManager（先标记后提交 + 对账不重发）
step1/2/3*.py   三个讲义脚本 + demo.py 全 ceremony 端到端
```

### Step 1：零状态跑检查链（10 分钟）

```bash
uv run python code/step1_chain.py
```

```text
== Step1 检查链七查：固定顺序、首查命中即停（零状态纯函数） ==
mandate: 单笔≤200000 分, 日累计≤500000 分, 日次数≤3, 科目=['travel', 'office_supplies', 'training'], 黑名单=['sketchy-mall']
today: now=2026-09-16T12:00:00+00:00, 已付 2 笔共 240000 分

幕1 ALLOW   | 合规小额
  -> ALLOW  kind=-            limit=-
幕2 DENY    | 黑名单收款方
  -> DENY   kind=structural   limit=excluded_vendors
     detail: sketchy-mall is on the mandate exclude list
幕3 PAUSE   | 单笔超上限（定量）
  -> PAUSE_FOR_REAUTH kind=quantitative limit=max_single_payment_cents
     detail: attempted 250000 分
幕4 PAUSE   | 已付清单脏数据（fail-closed）
  -> PAUSE_FOR_REAUTH kind=quantitative limit=max_daily_total_cents
     detail: today's paid list could not be read (fail-closed)

读法：幕2 优先命中黑名单（第 1 查先于单笔第 3 查）；幕4 是本课的魂——
已付清单缺 amount_cents，定量检查算不下去就 breach：宁可不放行，绝不带着脏数据放行
（DENY 与 PAUSE 都是「不放」，差别只在恢复路径：结构性没救、定量可重新授权）。
```

对着输出读 `code/enforcement.py#check_payment`：产品八查 → 本课七查的裁剪对照表
（固定顺序，首查命中即返回）：

| # | 产品（交易域） | 本课（付款域） | kind |
|---|---|---|---|
| 0 | 意图可解析（symbol/side） | 意图可解析（收款方/科目/正整数分） | structural |
| 1 | exclude_symbols 黑名单 | excluded_vendors 黑名单 | structural |
| 2 | 工具类型白名单（空=全拒） | 科目白名单（空=全拒） | structural |
| — | 资产类别（付款域无对应，裁掉） | — | — |
| 3 | 单笔名义额（不可定价→breach） | 单笔上限 | quantitative |
| 4 | 交易后总敞口（持仓行解析失败→breach） | 当日累计（已付条目解析失败→breach） | quantitative |
| 5 | 杠杆（资金≤0→attempted=inf） | 日次数（付款域无杠杆，裁掉杠杆/资金镜像） | quantitative |
| 6 | 日次数 | 授权过期（产品放在门 ceremony，本课收进链尾） | quantitative→structural |
| 7/8 | 资金防线 / universe 地板（裁掉） | — | — |
| — | — | 授权过期（同上第 6 查） | structural |

两个刻意保留的细节：`type(x) is not int` 连 bool 一起拒（bool 是 int 子类——著名的坑）；
`today` 参数注入「现在 + 当日已付清单」，检查链**绝不自己取时钟**（对版产品 manifest
模块的纪律——纯函数因此可测试，同一组输入永远同一结论）。

### Step 2：哈希链四幕（15 分钟）

```bash
uv run python code/step2_ledger.py
```

```text
== Step2 哈希链账本：追加 → 验链 → 篡改 → 断链拒写 ==
genesis prev = sha256:genesis（首条没有前驱，用哨兵）

[幕1 追加三条付款事件]
  seq=1 prev=sha256:genesis… hash=sha256:5ed57269bcdcb…
  seq=2 prev=sha256:5ed57269bcdcb… hash=sha256:4951fbdf94738…
  seq=3 prev=sha256:4951fbdf94738… hash=sha256:2e87519593031…
  每条都摁住了自己的位置(seq) + 前一条的哈希 + 载荷

[幕2 验链：完好]
  ok=True record_count=3 first_break=None

[幕3 篡改第 2 条的载荷（decision 改成 ALLOW）]
  ok=False 断点=index 1 (seq=2) reason='hash mismatch'
  -> 改载荷不改哈希：本条自身哈希对不上，当场被抓

[幕3b 高手版：把第 2 条的哈希也一起修好]
  ok=False 断点=index 2 (seq=3) reason='prev mismatch'
  -> 本条洗白了，但第 3 条还攥着旧哈希——prev mismatch，传播性让下一条出卖它

[幕4 断链拒写]
  LedgerCorruptionError: chain broken at index 2: prev mismatch
  -> 绝不往被篡改的历史上续建合法后缀；先人工对账，再谈追加
```

读 `code/ledger.py` 时盯两处与产品的**合理差异**（就地注释也声明了）：产品 `append` 持
POSIX `flock`（Windows 走 `msvcrt` 字节锁）做跨进程互斥，且每写 fsync、建文件先 fsync
目录；教学版是单进程单写者假设、不锁不 fsync——本课红线「不用 fcntl/flock（平台中立，
Windows 学员跑不了）」。防篡改语义（整链先验、断链拒写、verify 三查）与产品一致；
锁只是防两个写者互踩的 liveness 优化，不是防篡改保证的来源（产品源码原话）。

### Step 3：对账不重发三幕（15 分钟）

```bash
uv run python code/step3_reconcile.py
```

```text
== Step3 对账不重发：先标记后提交，按 ref_id 精确身份对账，绝不重发 ==

[幕1 正常付款：门 ALLOW → 标记落盘 → broker.pay → 删标记]
  status=PAID ref_id=pay-5bcaf228f95b45a6b116c0a30ad1a78b
  broker.pay 调用 1 次；未决标记残留=False

[幕2 崩溃恢复：款项已到达但确认丢失 → 证据关窗]
  崩溃现场: payment arrived but confirmation was lost (simulated crash, ref=pay-85a9f27f58434fba86cb88f5053e485d)
  重启前: 标记在盘=True broker.pay 调用 1 次
  reconcile: status=RESOLVED_BY_EVIDENCE
    evidence.ref_id=pay-85a9f27f58434fba86cb88f5053e485d
  重启后: 标记在盘=False broker.pay 仍 1 次（零重发）

[幕3 无证据阻断：broker 全程不可达 → 标记保留 + 拒绝新付款]
  崩溃现场: broker unreachable before payment reached the channel (ref=pay-99a71671437d45fb8b18a2e1042dd3ca)
  reconcile: status=NEEDS_MANUAL_REVIEW detail='no broker evidence — manual review required; never resubmit'
  未决窗口内新付款: status=REFUSED detail='pending window open — reconcile first'
  全程 broker.pay 调用 1 次（零重发）——要不要补付，人说了算
```

（ref_id 是 uuid，每次跑值不同。）`MockBroker` 的两种故障注入是本步的教学支柱：
`arrived_unconfirmed`＝款项入账后抛异常（模拟「款到了、确认丢了」——证据在 broker）；
`unreachable`＝款项未到达就抛（无证据——只能人工）。`pay_calls` 列表数的是 broker.pay
被调了几次：三幕全看完，它**从来没超过 1**。

### Step 4：全 ceremony 端到端 + 讲义区验收（15 分钟）

```bash
uv run python code/demo.py
```

```text
== L4.3 付款门全 ceremony（报销付款域，整数分） ==
mandate 加载: 单笔≤200000 分 日累计≤500000 分 日次数≤3 过期=2026-10-13T12:00:00+00:00
today: 已付 1 笔 60000 分；now=2026-09-16T12:00:00+00:00

[六步裁决 ×3]
  airline-co       90000 分 -> ALLOW            payment in mandate
  Sketchy-Mall     50000 分 -> DENY             breach: excluded_vendors (structural)
  training-co     480000 分 -> PAUSE_FOR_REAUTH breach: max_single_payment_cents (quantitative)

[ALLOW 者走安全付款（先标记后提交）]
  status=PAID ref_id=pay-333fca5d061d480b95fc467d38704fa9 回执={'ref_id': 'pay-333fca5d061d480b95fc467d38704fa9', 'payee': 'airline-co', 'category': 'travel', 'amount_cents': 90000, 'status': 'paid'}

[拉闸后再裁决一笔]
  HALT 存在 -> DENY: payments halted (kill switch tripped)

[审计账本]
  seq=1 verdict  ALLOW
  seq=2 verdict  DENY
  seq=3 verdict  PAUSE_FOR_REAUTH
  seq=4 payment  pay-333fca5d061d480b95fc467d38704fa9
  seq=5 verdict  DENY
  verify: ok=True record_count=5 —— 改任何一条，其后整条链都会断
```

六步 ceremony 对版 `sdk_order_gate.py#execute_live_order`：load_mandate（None→DENY）→
过期 → HALT 哨兵（存在/损坏→DENY）→ 意图归一 → 今日已付快照（读失败→DENY）→
check_payment 三态。其中 demo 的合同由「用户侧」直接 json.dump 写盘——**agent 侧模块
没有 save_mandate**，这就是授权不可达的教具。然后跑讲义区验收：

```bash
uv run pytest code/
```

```text
................................                                [100%]
32 passed in 0.03s
```

32 个 = 合同 3（roundtrip / fail-closed 加载 / **授权不可达断言：模块里没有 save_mandate**）
+ 检查链 11（七查逐查「只破这一项」+ float/bool 不可解析 + allow + 黑名单先于单笔的顺序断言）
+ 门 6（六步各一步 + 三态路由）+ 账本 6（追加成长 / 篡改三连 / 断链拒写 / canonical 键序无关）
+ 对账 6（正常恰好一次 / 门拒零调用 / 标记落盘失败零调用 / 证据关窗 / 无证据保留 + 拒新 /
标记后崩溃零调用）。篡改三连对版产品 `test_governance.py` 的三个 tamper 测试思想。

### Step 5（可选加餐）：去读产品原文，把 check_mandate 抄进你自己的域

克隆仓库（SSH），锚定本课路标的 commit：

```bash
git clone git@github.com:HKUDS/Vibe-Trading.git ~/develop/opensource/Vibe-Trading
```

```bash
cd ~/develop/opensource/Vibe-Trading
```

```bash
git checkout f84b2977
```

阅读顺序与跳读地图（行数是 wc -l 口径）：先 `agent/src/live/mandate/model.py`（148 行，
四件套全貌，10 分钟）→ `agent/src/live/enforcement.py`（800 行，**只精读 check_mandate
函数体与 BreachEvent**，检查链注释逐条对上 Step 1 的表；跳过 loader/market-cap 细节）→
`agent/src/governance/ledger.py`（738 行，精读 compute_record_hash / verify_chain /
append_record；跳过导出与轮转）→ `agent/src/live/pending_action.py`（389 行，精读
`client_order_id` 生成与恢复注释）→ 最后 `agent/src/live/sdk_order_gate.py`
#execute_live_order（1116 行，只看 ceremony 顺序）。本地建分支，把 check_mandate 抄改到
你自己的域（科目/限额换掉），照 `test_mandate_enforcement.py` 的 per-limit 思想写一组
pytest——「改造说明 + 截图/日志」留给单元里程碑，本课不强制。

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改 TODO 标注区（与所需的顶部 import；骨架只预置了 given
部分用到的）。卡住先想 5 分钟，再看渐进提示：

```bash
cd exercises
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_chain.py` | 补全检查链 4/5/6 查（当日累计 fail-closed / 日次数 / 授权过期）；验收 12 个测试项：用例表 9（每查一个「只破这一项」）+ 顺序断言（黑名单先于单笔）+ 覆盖型 meta（七限制逐维、三态各有、两 kind 各有）+ 纯函数确定性 |
| ex2 | `exercises/ex2_ledger.py` | 补全哈希链三件套（compute_record_hash / verify_chain / append_record）；验收 5 个：追加链成长、篡改 payload 定位、删中间条定位、自修 hash 仍被下一条抓住、断链后 append 抛 LedgerCorruptionError 且拒写 |
| ex3 | `exercises/ex3_reconcile.py` | 对账不重发：pay_with_safety 的先标记后提交顺序 + reconcile_pending 两分支；验收 5 个：正常流恰好一次 broker.pay、门拒零调用、有证据关窗零重发、无证据标记保留且拒新付款、标记后崩溃 pay 零次（重发零次断言——数 MockBroker.pay_calls） |

形态标注（诚实起见）：三题都是**补全型骨架**——0–3 查 / canonical_json / 标记原语已给，
TODO 只挖关键环节；讲义 `code/` 里有同构完整版可对照读（ex1 对照 enforcement.py、
ex2 对照 ledger.py、ex3 对照 pending.py），先自己写再看。验收（三条同时全绿 = 本课毕业）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：fail-open 兜底坑（`except Exception: return None`）

这是本课的命名化失败模式，也是所有治理件的头号杀手——**检查链任何一处兜底返回 None，
整个门形同虚设**。

- **现象**：付款门「跑得好好的」，测试全绿。三个月后一笔 90 万分的付款穿门而过——
  金额字段是从表单来的字符串 `"900,000.00"`（带千分位），检查链里那步解析写的是
  `except Exception: return None`，而 None 的语义恰好是 ALLOW。**真实先例**：DB-GPT 的
  确认门四缺陷——拦截整体包在 `try/except pass` 里静默放行、pending 存
  模块级内存 dict（重启丢）、resolve 端点无鉴权、只盖 MCP 连接器不盖 SQL 执行——四缺陷
  叠加，审批门形同虚设。本课产品的对照纪律：链上任何一环异常都必须拒绝执行。
- **最小复现**（真实可跑——下面的内容存成 `code/fail_open_demo.py`，然后
  `uv run python code/fail_open_demo.py`，用完删掉）：

  ```python
  from datetime import UTC, datetime

  import enforcement
  from enforcement import Breach, PaymentIntent, TodaySnapshot
  from mandate import ConsentMeta, HardCaps, PayMandate, PayUniverse

  def check_single_cap_fail_open(mandate, intent, today):
      try:
          amount = int(intent.amount_cents)  # 一段「看起来无害」的解析
      except Exception:
          return None  # ← 兜底：解析失败被当成「没违规」
      if amount > mandate.hard_caps.max_single_payment_cents:
          return Breach("quantitative", "max_single_payment_cents", amount)
      return None

  now = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
  m = PayMandate(1, HardCaps(200_000, 500_000, 3), PayUniverse(("travel",), ()), ConsentMeta("sha256:x", now))
  dirty = PaymentIntent(payee="a", category="travel", amount_cents="900,000.00")  # 脏数据：表单带千分位
  print(check_single_cap_fail_open(m, dirty, TodaySnapshot(now, ())))  # None —— 门读到 None = ALLOW
  print(enforcement.check_payment(m, dirty, TodaySnapshot(now, ())))   # 对版：breach(payment_intent)
  ```

  实跑输出——同一份脏数据，两个结局：

  ```text
  None
  Breach(kind='structural', limit='payment_intent', attempted_cents=0, detail='payment intent unparseable (payee/category/amount_cents)')
  ```
- **Java 直觉为何失效**：Java 里「解析可能失败」长着 checked exception 的脸（
  `NumberFormatException` 你迟早要 catch，编译器/评审都会盯着 catch 块里写了什么）；
  Python 的 `except Exception` 静默吞掉一切且**控制流照走**，语言层面对「catch 之后干嘛」
  零约束。更阴的是 None 的双重身份：它既是「检查链的 ALLOW 返回值」，又是你最顺手的
  兜底返回值——两个语义在类型上无法区分，bug 就藏在重载里。fail-closed 在 Python 里
  是**你一个人要扛的纪律**：每个 except 的出口必须显式选择「DENY 还是抛」，没有默认项。
- **修复与纪律**：① 检查链里 except 的唯一合法出口是 breach/DENY（本课 `gate.py` 第 5
  步的 `except BrokerUnavailable → DENY` 就是写法范本——异常被翻译成拒绝并带 reason）；
  ② 解析函数把「失败」表达为**显式的值**（本课 `_parse_paid_amount -> int | None`），
  且调用方拿到 None 必须 breach（`_parse_paid_amount` 的 docstring 就写着这句话）；
  ③ 用测试钉死：`code/test_demo.py` 的「喂脏输入断言 DENY」一族（float/bool 金额、
  脏已付清单）就是干这个的——**每个解析边界配一条脏输入用例**，重构时谁把兜底改成
  return None，红灯立刻到。

## 6. 延伸

源码路标（本地克隆 `~/develop/opensource/Vibe-Trading`，按图索骥；行数 wc -l 口径）：

- `HKUDS/Vibe-Trading@f84b2977#agent/src/live/enforcement.py` —— fail-closed 检查链本体：
  `check_mandate` 固定顺序八查、`BreachEvent` 合同、`_resolve_order_notional` 的
  「不可定价即 breach」（800 行，本课 Step 1 的母本）；
- `HKUDS/Vibe-Trading@f84b2977#agent/src/governance/ledger.py` —— 哈希链账本：canonical
  JSON、`compute_record_hash`、append 前整链先验 + `LedgerCorruptionError`、flock/msvcrt
  双路径与 fsync 策略（738 行，本课 Step 2 的母本）；
- `HKUDS/Vibe-Trading@f84b2977#agent/src/live/pending_action.py` —— crash-safe 副作用标记、
  `client_order_id` 幂等键、恢复证据模型 Pydantic 校验矩阵（389 行，本课 Step 3 的母本）；
  "never by resubmission" 的原话在其调用方 sdk_order_gate.py 的恢复函数 docstring；
- `HKUDS/Vibe-Trading@f84b2977#agent/src/live/sdk_order_gate.py` —— SDK 直连下单门
  `execute_live_order` 六步 ceremony 与 `_allow` 的先标记后提交（1116 行，本课 gate.py
  的母本）；
- `HKUDS/Vibe-Trading@f84b2977#agent/src/live/mandate/model.py` —— mandate 四件套
  frozen dataclass（「零验证面」动机原文）、`expires_at` 默认 30 天「不许永生」（148 行）；
- `HKUDS/Vibe-Trading@f84b2977#agent/src/live/halt.py` —— 文件哨兵 kill switch：存在即停、
  payload 损坏仍 tripped（280 行）；
- `HKUDS/Vibe-Trading@f84b2977#agent/src/live/advisory/` —— 门外的观察性意见：fail-open、
  默认关、绝不阻塞——权威分离的另一半（§2.2）；
- 产品测试文件（对版本课测试思想的出处）：`HKUDS/Vibe-Trading@f84b2977#agent/tests/test_governance.py`
  （篡改三连）、`#agent/tests/test_mandate_enforcement.py`（per-limit 用例）、
  `#agent/tests/test_sdk_order_gate.py`（重启不重发）、`#agent/tests/test_no_set_mandate_tool.py`
  （授权不可达的机器断言——本课 `test_no_save_mandate_authorization_unreachable` 的对版）。

官方文档：仓库 README 的 autonomous trading 与 consent 章节（`HKUDS/Vibe-Trading@f84b2977#README.md`，
"It holds no funds and never trades outside the limits you set" 的产品承诺原文）。

Unit 4 到此收官：三个产品、三种气质——ai-hedge-fund 的纯函数美学、TradingAgents 的
图上辩论、Vibe-Trading 的治理纪律。里程碑（unit4 milestone）要做的是把三份改造说明
收进一个可复现的档案。

## 离毕业又近的一块

本课三件套就是毕业设计的直接蓝本：L5.4 的 fail-closed 执行门（限额 clamp/黑名单/频次，
不可解析即 DENY）就是 `check_payment` 换回你的财务域参数；L5.3 的事件溯源与审计
（append-only 事件表、缓存即审计）就是 `HashLedger` 的数据库版；崩溃恢复（审批暂停/
恢复/拒绝回环不丢单）就是 `PendingPaymentManager` 的先落盘后提交。**毕业设计不是从零写，
是把这三块装进你自己的图**——Unit 5 见。

