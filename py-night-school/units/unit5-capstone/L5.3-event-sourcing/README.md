# L5.3 毕业设计③：事件溯源与审计——append-only、缓存即审计、图版本绑定

## 1. 本课目标

L5.1 装好了编排层（静态图 + 计划驱动），L5.2 在并行装审批面；今晚给 PoC 装**审计面**——
审计基线（research 报告 §4.5 的 12 条 checklist）里的三条，本课各落一个件，全部离线确定：

- **append-only 事件表**（基线①）：SQLite 一张 `events(aggregate_id, seq, type, payload,
  created_at)`，主键 `(aggregate_id, seq)`——会话、审批、成本全部是一等事件（九类封闭词汇表
  `EVENT_TYPES`）；没有 update / 没有 delete，**接口不存在**，这是纪律不是缺功能；
- **缓存即审计**（基线④）：L4.1 精读过的「一决定一 JSON 文件」升级成 SQLite 决策缓存表
  `llm_decisions`——同 prompt_hash 命中零模型请求，「这轮模型看到了什么/说了什么」一行
  SQL 出原话；
- **图版本绑定**（基线⑥）：L5.1 的 `topology_signature` 接进审计键——run_key 带签名、
  run.started 事件带 graph_version，改图后旧 run_key 续跑被 `GraphVersionMismatch` 拒绝
  （「版本变了就别续旧账」）。

**完成判据**：本目录下三条命令同时全绿（`exercises/` 是设计内的 TODO 红）——

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 2. 概念讲解

先给全课对照表（sqlite3 是标准库——JDBC 心智可以直接平移），再展开三个核心：

| 你熟悉的 Java 物 | 今天的 Python 物 | 一句话差异 |
|---|---|---|
| JDBC `DriverManager.getConnection(url)` | `sqlite3.connect(path)` | 零安装零服务：文件不存在则创建，一个文件就是一个库 |
| `PreparedStatement` + `setString(1, …)` | `cursor.execute(sql, params)` 的 `?` 占位 | 同款防注入：`?` 永远把实参当**值**；f-string 拼接把它当 SQL 的一部分（Step1 实测全表泄露） |
| `ResultSet` `rs.getString("dept")` | `sqlite3.Row` 的 `row["dept"]` | `conn.row_factory = sqlite3.Row` 之后按名取列——不赌下标 |
| `conn.setAutoCommit(true)`（JDBC 默认） | Python sqlite3 默认**不自动提交** | 忘 `commit()` 数据就「消失」且不报错——§5 坑位主角 |
| Spring `@Transactional` | `with conn:` 块 | 正常退出 commit、异常 rollback；但它是**语句级纪律**不是声明式代理，忘了写没人兜底 |
| Axon `EventStore`（aggregateId + sequenceNumber + replay，Java 人熟的 CQRS/ES 词汇） | `eventstore.py` 的 `EventStore` | 词汇直接平移：聚合、seq、唯一索引、重放——本课是最小实现（单文件标准库，不引框架） |
| 审计日志表 + AOP 切面 `@Auditable` | 节点旁挂事件发射（`_with_events`） | 切面是注解魔法（看得见注解看不见发射点），旁挂是显式装饰（装配代码上看得见审计点）——§2.3 讲取舍 |
| Flyway/Liquibase 给 schema 打版本 | 图形状签名进审计键（`run_key`/`graph_version`） | 不是人肉对版本号：拓扑形状哈希进聚合键，改图自动换世界（A15） |

### 2.1 为什么 append-only：审计的物理基础

审计的第一诉求是「事实发生过就抹不掉」。实现它的最重手段是 L4.3 读过的哈希链账本
（每条记录带前链哈希，防篡改）；本课用**最小实现**：一张只有追加口的表——

- **物理上**：`PRIMARY KEY (aggregate_id, seq)` 唯一索引守住序号；同序号二追加抛
  `EventSeqConflict`（唯一索引冲突的语义化翻译），而不是静默覆盖；
- **接口上**：`EventStore` **没有 update / delete 方法**——「不可改」不靠约定靠接口形状，
  讲义区测试有 meta 断言钉住它（`test_no_update_or_delete_api`）。对照 L4.3：哈希链是
  「改了能被发现」，append-only 接口是「想改没有门」——两者可叠加（L5.4/里程碑的扩展位）；
- **事件类型一等**（A11）：`EVENT_TYPES` 九类封闭词汇表——run.started / intake.loaded /
  plan.approved / plan.rejected / tool.called / llm.decision / advice.drafted / submitted /
  cost.recorded。成本（每次模型调用的 prompt/completion tokens，从响应的 usage 取——
  mock 端点也带真实 usage，零 key 也真实）在本课就落为一等事件；审批事件（L5.2 的
  三态回复）的入场在 L5.4/里程碑与 L5.2 合流之后——本课的图还是 L5.1 的分支，没有
  审批半边。它们都是**事件**，不是「日志里的另一行字」。表外类型 `append` 直接
  `ValueError`（fail-closed：审计词汇表是封闭集合，防止拼错的事件类型静默进账本）。

产品先例：sst/opencode 的事件表就是这个形状——`event(aggregate_id, seq, type, data)` 加
`event_aggregate_seq_idx` 唯一索引（见 §6 路标，SQLite + drizzle 声明）；报告 A11 的结论
「JSONL 只做归档不做主存」的理由在这里能摸到：事件表能按聚合点查、按类型过滤、能 join
决策缓存表，JSONL 每次都要全文件扫。

**状态是投影**：`fold` 把事件序列重放成当前视图（results 聚合、advice 终值、成本累计）——
事件表是唯一真相源，图跑出来的 state 只是它某一时刻的投影。Step2 会现场演：丢掉终态
state，只凭事件表把 advice/results/拒绝轨迹全部重放回来，逐项全等。

### 2.2 为什么缓存即审计：性能件同时是取证件（A13）

L4.1 精读 ai-hedge-fund 的 `PromptCache` 时说过：同一个存储同时是缓存（同单重审 $0）、
审计记录（每票背后的精确 prompt+response）、调试踪迹（解析失败原样留盘）。今晚把它从
「每决定一个 JSON 文件」升级成表：

```sql
CREATE TABLE llm_decisions (
    prompt_hash TEXT PRIMARY KEY,   -- sha256(模型名 + 规范化 prompt)
    model       TEXT NOT NULL,
    prompt      TEXT NOT NULL,      -- 模型看到的全文原话
    response    TEXT NOT NULL,      -- 模型说的全文原话
    created_at  TEXT NOT NULL       -- 注入时钟（不取系统时间）
)
```

升级的收益是**可查询**：事件表里 `llm.decision` 事件带 prompt_hash，合规问「这轮模型看到
了什么、说了什么」——顺着 hash 主键点查决策缓存表，原话全量在（与事件表同库：一个 db
文件就是一单的完整审计面）。机制收益照旧：同 prompt_hash 命中→直接回放 response，
**模型一个请求都没收到**（第二遍 `ep.requests` 为空是铁证）；命中也留痕——`llm.decision`
事件带 `cached: True`，「这轮的决策来自缓存」同样是审计事实。

key 的纪律是 L4.1 §5「相等不等哈希」的正解落地：`canonical_prompt` 把消息序列归一成确定
文本——role 归一（OpenAI 协议说 user/assistant，langchain 对象说 human/ai）、内容取全文、
顺序就是消息顺序。dict 消息与同内容的 langchain 消息对象哈希到**同一个 key**；
模型名进键（同 prompt 换模型 = 不同决策）。

### 2.3 为什么图版本绑定：审计记录必须绑定产生它的拓扑版本（A15）

审计的完整问题是「当时发生了什么**+ 出自哪一版规则**」。如果 3 月的审批出自 v1 的图、
4 月的出自 v2 的图，而审计记录里不带版本——重放无法解释，合规无法对账。报告 A15 的
方案：图形状签名进 checkpoint key，改图自动作废旧执行态。产品先例是 TradingAgents 的
`_run_signature`（§6 路标）：分析师选择、辩论轮次、资产模式拼进 checkpoint thread_id——
换了配置的 resume 不许静默续旧检查点（#1089）。本课三个件把它落地：

- `run_key(claim_id, signature)`：聚合键 = 单号 + 签名前 12 位——checkpoint thread_id 与
  事件聚合共用（同图同单稳定；图一改自动换世界）；
- `run.started` 事件的 payload 带 `graph_version`（全签名留档）——每个聚合的出生证明；
- `assert_compatible(stored, current)`：续跑守门——聚合已有 run.started 的版本与当前装配
  的签名逐条核对，不符抛 `GraphVersionMismatch`。注意语义：**不是报错完蛋**，是「版本变了
  就别续旧账」——旧事件 append-only 原样保留（历史不作废，作废的是「续跑权」），
  重开新 run_key 就是了。

顺带一个值得想清的边界（demo 第三幕会看到）：决策缓存**不**随图版本作废——它按 prompt
内容寻址，而拓扑改变不改变模型的输入，所以改图后的新 run 照样命中旧决策（零请求）。
两层审计件各管各的版本面：事件表绑定拓扑版本，缓存绑定内容版本。

### 2.4 审计层怎么接进图：旁挂，不改写

L5.1 的图一行拓扑未动（本课图的拓扑签名与 L5.1 **相同**——`5dbfa594e113…`，这是「审计层
是旁路」的可验证证据）。接线只有两类加法：

- **节点旁挂事件发射**（`graph._with_events`）：节点本体先跑，再把它的 (输入状态, 输出
  更新) 翻译成事件逐条 emit。取舍：另一条路是节点内直接 `store.append`——那会让每个节点
  都 import eventstore、都重复 (store, aggregate_id) 样板，节点从「纯函数」退化为「带隐藏
  写副作用的函数」。旁挂的好处：节点零改动（L5.1 的 22 个测试原样全绿就是回归证据）、
  审计层可拆卸（`recorder=None` 时字节回到 L5.1 行为）、发射点在装配代码上看得见——
  这是 Java AOP 切面的**显式版**：切面靠注解发现，旁挂靠闭包传递，静态图的「静态」
  保证了发射点不会跑出这十几行装配；
- **模型调用过审计层**（`audit_cache.AuditedModel`，Runnable 子类）：planner/drafter 的
  `ainvoke` 被包进「查缓存→命中回放 / 未命中真调用→落缓存→发 llm.decision + cost.recorded
  事件」。llm.decision 与 cost.recorded 由这层发（不经节点）——模型调用的事实发生在调用处，
  审计记录就该落在调用处。

## 3. 动手代码

先 `uv sync`。`code/` 里 L5.1 共享件整目录复制（mock_endpoint / review_rules / advice /
mock_tools / plan / executor / prompts / step1_union / step2_signature / demo_trace 与四个
L5.1 测试文件**字节相同**——对版纪律，diff 可验；graph / demo 注明「L5.1 副本 + L5.3
事件层」）；本课新模块：`eventstore.py`（核心①）、`audit_cache.py`（核心②）、
`versioning.py`（核心③）、`demo_flow.py`（三幕）、`step1_sqlite.py` / `step2_replay.py`
（讲义脚本）与四个新测试文件。

```bash
uv sync
```

### Step 1：sqlite3 五分钟——JDBC 心智逐条对照（10 分钟，零模型零框架）

```bash
uv run python code/step1_sqlite.py
```

```text
== Step1 sqlite3 五分钟：JDBC 心智逐条对照 ==
[1] 连接与建表：connect(path) ≈ DriverManager.getConnection(url)
  建表 + 提交完成（CREATE TABLE IF NOT EXISTS——可重复执行的迁移脚本风格）
[2] 参数化 ?：execute(sql, params) ≈ PreparedStatement.setString(1, ...)
  恶意输入 "x' OR '1'='1":
    参数化 ?  查到 0 行（整串被当『值』，查无此部门）
    f-string 拼接查到 2 行（整串被当『SQL 的一部分』，全表泄露）
[3] Row 工厂：row['dept'] ≈ rs.getString("dept")——按名取列，不赌下标
  row['dept']='DEV'  row['budget_cents']=10000（建 Row 工厂后行像 dict）
[4] with conn: 事务——Python 默认**不自动提交**（JDBC 默认 autocommit=true）
  插入 HR 后不 commit 直接 close，重开查询: 0 行（数据没了，且没报错）
  with conn: 再插一次，重开仍在: 1 行（写路径统一 with conn: 的纪律来源）
[5] 唯一索引冲突：IntegrityError——EventStore 把它翻译成 EventSeqConflict
  PRIMARY KEY 撞车: sqlite3.IntegrityError: UNIQUE constraint failed: departments.dept
  <- eventstore.append 捕获的就是它：翻译成语义化的 EventSeqConflict（讲义 §3）
```

五段对应 §2 表的前五行。[4] 是 §5 坑位的现场版——不 commit 就 close，数据消失且不报错；
[5] 的 `IntegrityError` 就是 `EventStore.append` 翻译成 `EventSeqConflict` 的那个原始异常。

### Step 2：读三个核心模块（15 分钟）

按「一表一异常一纪律」读 `eventstore.py`：`SCHEMA`（一张表四个字段一个主键）→
`EventSeqConflict`（唯一索引冲突的语义化翻译）→ `append`（事务内：取时钟→序列化→
seq 分配→INSERT；表外类型 ValueError）→ `events_for`（按聚合读、按类型过滤）→
`fold`（重放：事件→视图）。`audit_cache.py` 读三样：`canonical_prompt`（相等不等哈希的
正解）、`DecisionCache`（put/get/audit_query）、`AuditedModel`（模型调用过审计层的完整
回路）。`versioning.py` 最短：`run_key` + `assert_compatible` + 签名函数（L5.1 的字节副本，
复制而非 import 的原因写在 docstring：避免与 demo 成环）。

### Step 3：三幕 demo——三层审计件各自干什么（15 分钟）

```bash
uv run python code/demo_flow.py
```

```text
== 第一幕：全量落库——四单跑一遍，事件表记下每一件事 ==
[CLM-2026-0001]（剧本 clean）模型请求 2 次
[CLM-2026-0002]（剧本 dirty_once）模型请求 3 次
[CLM-2026-0003]（剧本 always_dirty）模型请求 3 次
[CLM-2026-0004]（剧本 clean）模型请求 2 次

  CLM-2026-0001@5dbfa594e113  12 条事件
    seq  0  run.started    claim=CLM-2026-0001 graph_version=5dbfa594e113… mode=clean
    seq  1  intake.loaded  SALES 总额 7100 分 发票 ['INV-2026-0001']
    seq  2  llm.decision   node=planner cached=False prompt_hash=5bec5fe8fe60…
    seq  3  cost.recorded  node=planner prompt=12 completion=8
    seq  4  plan.approved  3 步计划 claim_total=7100 分
    seq  5  tool.called    step=s1 tool=fetch_claim produces=claim
    seq  6  tool.called    step=s2 tool=check_budget produces=budget
    seq  7  tool.called    step=s3 tool=verify_invoice produces=invoice
    seq  8  llm.decision   node=drafter cached=False prompt_hash=325ff2645353…
    seq  9  cost.recorded  node=drafter prompt=12 completion=8
    seq 10  advice.drafted APPROVE/PASS 剩余 10000 分
    seq 11  submitted      {'sent': True}
    …
  CLM-2026-0003@5dbfa594e113  12 条事件
    seq  0  run.started    claim=CLM-2026-0003 graph_version=5dbfa594e113… mode=always_dirty
    seq  1  intake.loaded  DEV 总额 -500 分 发票 ['INV-2026-0003']
    seq  2  llm.decision   node=planner cached=False prompt_hash=b840bc6b1b07…
    seq  3  cost.recorded  node=planner prompt=12 completion=8
    seq  4  plan.rejected  reason=unknown_tool
    seq  5  llm.decision   node=planner cached=False prompt_hash=695333ba3fa5…
    seq  6  cost.recorded  node=planner prompt=12 completion=8
    seq  7  plan.rejected  reason=missing_field
    seq  8  llm.decision   node=planner cached=False prompt_hash=20a4db7e9ade…
    seq  9  cost.recorded  node=planner prompt=12 completion=8
    seq 10  plan.rejected  reason=bad_amount
    seq 11  advice.drafted ESCALATE/REJECT:PLAN_REPLANS_EXCEEDED 剩余 0 分
  <- 0001 是干净路：12 条走到 submitted；0003 是超限哨兵：三轮拒绝后 advice.drafted(ESCALATE) 收尾、
     没有 tool.called（计划从未合法，工具一个都没被碰）、没有 submitted（不送审）——事件流水就是执行史

== 第二幕：缓存即审计——同一单第二遍，模型一个请求都没收到 ==
  第二遍模型请求: 0 次（第一遍是 2 次——想花钱都没门）
  事件 12 → 22 条（run.started 第 2 条、seq 接着走）
  cost.recorded 仍 2 条（命中不花钱）；llm.decision 共 4 条:
    seq  2  node=planner  cached=False
    seq  8  node=drafter  cached=False
    seq 14  node=planner  cached=True
    seq 19  node=drafter  cached=True
  <- 缓存命中不等于没有账：llm.decision(cached=True) 照样留痕——「这轮的决策来自缓存」也是审计事实

== 第三幕：图版本绑定——加一个节点，旧账作废 ==
  改图前: 签名 5dbfa594e113…  run_key CLM-2026-0004@5dbfa594e113
  改图后（+audit_stamp 节点）拿旧 run_key 续跑: 被拒
    GraphVersionMismatch: graph version mismatch: stored=5dbfa594e113… current=c71f29f1eb8f…（图形状变了，旧执行态作废——请用新 run_key 重开 run，不要续旧账）
  新 run_key CLM-2026-0004@c71f29f1eb8f（签名 c71f29f1eb8f…）正常开新账:
  CLM-2026-0004@c71f29f1eb8f  10 条事件
    seq  0  run.started    claim=CLM-2026-0004 graph_version=c71f29f1eb8f… mode=clean
    seq  1  intake.loaded  DEV 总额 5000 分 发票 ['INV-2026-0005']
    seq  2  llm.decision   node=planner cached=True prompt_hash=dfd2d7e466a1…
    seq  3  plan.approved  3 步计划 claim_total=5000 分
    seq  4  tool.called    step=s1 tool=fetch_claim produces=claim
    seq  5  tool.called    step=s2 tool=check_budget produces=budget
    seq  6  tool.called    step=s3 tool=verify_invoice produces=invoice
    seq  7  llm.decision   node=drafter cached=True prompt_hash=f5851ef4d2ff…
    seq  8  advice.drafted REJECT/REJECT:INVOICE_INVALID 剩余 40000 分
    seq  9  submitted      {'sent': True}
  <- 两个可复用的观察：①旧事件一条没动（append-only），作的废是「续跑权」不是历史；
     ②llm.decision 无 cost.recorded——决策缓存按 prompt 寻址，不随图版本作废（拓扑不改变模型的输入）

（审计库 audit.db 在系统临时目录，演示结束自动销毁——克隆即学，不写学员主目录）
```

第一幕看两件事：事件流水就是执行史（0003 三轮拒绝的 reason 序列逐条在账）；成本事件
一等（每次真实调用一条 12/8）。第二幕看「命中不花钱但留痕」。第三幕注意那个容易被忽略
的细节：新拓扑的 run 里 `llm.decision cached=True`——§2.3 末段说的边界（缓存绑内容不绑
拓扑）在现场。

讲义区测试（含 L5.1 回归）：

```bash
uv run pytest code/
```

```text
47 passed in 17.12s
```

47 个讲义区测试 = L5.1 回归 22（计划校验门 9 + 执行器 4 + 签名 3 + 图端到端 6——审计层
是旁路的回归证据）+ EventStore 9（顺序 seq、冲突翻译、聚合隔离、事务回滚、表外类型
fail-closed、时钟注入、类型过滤、无 update/delete 接口 meta、fold 重放）+ 决策缓存 6
（canonical 等价、变一字换 key、命中零请求、审计查询原话、换单不误命中、put/get 往返）+
版本绑定 6（同图同 key、改图换签、守门两态、事件带版本、旧 key 拒续、新 key 正常）+
端到端 4（四单事件流水逐条全等、重放视图与终态全等、成本累计、重跑追加不重花）。

### Step 4：事件重放——状态是投影的现场（10 分钟）

```bash
uv run python code/step2_replay.py
```

```text
== Step2 事件重放：状态是投影（fold 现场版） ==
[跑图] CLM-2026-0002（dirty_once）→ run_key CLM-2026-0002@5dbfa594e113，终态 state 拿在手里；现在把它丢掉

[事件表] 唯一真相源（type/seq）：
    seq  0  run.started    {'claim_id': 'CLM-2026-0002', 'graph_version': '5dbfa594e1
    seq  1  intake.loaded  {'claim_id': 'CLM-2026-0002', 'dept': 'SALES', 'total_cent
    seq  2  llm.decision   {'node': 'planner', 'prompt_hash': 'eeb988e46ddc26e0fdbfbd
    seq  3  cost.recorded  {'node': 'planner', 'model': 'mock-model', 'prompt_tokens'
    seq  4  plan.rejected  {'reason_code': 'unknown_tool', 'detail': "steps.1: Input
    seq  5  llm.decision   {'node': 'planner', 'prompt_hash': 'e537b60ad4257658422ce3
    seq  6  cost.recorded  {'node': 'planner', 'model': 'mock-model', 'prompt_tokens'
    seq  7  plan.approved  {'claim_total_cents': 8800, 'steps': [{'step_id': 's1', 'p
    seq  8  tool.called    {'step_id': 's1', 'tool': 'fetch_claim', 'produces': 'clai
    seq  9  tool.called    {'step_id': 's2', 'tool': 'check_budget', 'produces': 'bud
    seq 10  tool.called    {'step_id': 's3', 'tool': 'verify_invoice', 'produces': 'i
    seq 11  llm.decision   {'node': 'drafter', 'prompt_hash': '754263c9707e8a05046fdb
    seq 12  cost.recorded  {'node': 'drafter', 'model': 'mock-model', 'prompt_tokens'
    seq 13  advice.drafted {'claim_id': 'CLM-2026-0002', 'decision': 'REJECT', 'reaso
    seq 14  submitted      {'sent': True}

[fold] 只凭事件归约出的当前视图：
    results 键        : ['budget', 'claim', 'invoice']
    advice            : {"claim_id":"CLM-2026-0002","decision":"REJECT","reason":"REJECT:ITEM_OVER_LIMIT","remaining_cents":10000}
    plan_rejections   : ['unknown_tool']
    sent              : True
    cost              : {'prompt_tokens': 36, 'completion_tokens': 24}（三次真实调用的累计——重放免费，花钱的都记了账）
    graph_version     : 5dbfa594e1131848…（run.started 里带的出生证明）

[对照] 图的终态 vs 事件重放的投影：
    advice 全等 : True
    results 全等: True
    sent 全等   : True
    拒绝轨迹全等    : True
  <- state 会随 run 生死，事件表 append-only 地活着：任何时刻想问「当时到底发生了什么」，
     答案不是翻 state，是重放事件——这就是事件溯源（A11）的全部立场。
（审计库在系统临时目录 tmpXXXX/ 下，演示结束自动销毁）
```

## 4. 练习（本课过关点）

规则：**单变量编辑约束**——只改 TODO 标注区与所需的顶部 import（骨架只预置了 given
部分用到的）。卡住先想 5 分钟，再看渐进提示（在 exercises/ 目录下）：

```bash
uv run python -c "from hints import hint; print(hint('ex1', 1))"
```

| 题 | 文件 | 考察 |
|---|---|---|
| ex1 | `exercises/ex1_store.py` | EventStore 补全：append（事务 + 冲突翻译 + seq 分配 + 常量表校验）与 events_for（参数化 + 类型过滤）；验收含事务回滚（失败追加半个事件不留、seq 不烧）与时钟注入复现 |
| ex2 | `exercises/ex2_cache.py` | 决策缓存补全：canonical 序列化 + prompt_hash + 命中零请求 + 审计查询；验收含 dict/langchain 消息同 hash、第二遍端点零请求、换单不误命中 |
| ex3 | `exercises/ex3_version.py` | 图版本绑定补全：run_key 组装 + assert_compatible 守门；验收含加/删节点换签、旧 key 拒续新 key 正常、run.started 带 graph_version（demo 集成路径） |

三题都是「同构骨架补核心函数」（讲义 `code/` 的 eventstore / audit_cache / versioning 是
能跑的完整参照），零真实网络（ex2 的端点是 L2.3 服役至今的 MockLLMEndpoint）。验收
（三条同时全绿 = 本课毕业；发货态 18 个练习测试里 17 个 TODO 红、1 个 meta 绿）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 5. Java 人坑位：自动提交错觉

这是本课的命名化失败模式——写了一晚上 SQLite 的人最容易在收工前踩的一脚空。

- **现象**：测试全绿（内存里查得到）、demo 打印正常，但重开数据库一查——账本是空的。
  更阴的版本：只「丢」了一部分数据——凡是走 `with conn:` 的都在，裸 `execute` 的都没了。
- **最小复现**（Step1 的 [4] 段就是它，可以再跑一遍）：

  ```python
  import sqlite3

  conn = sqlite3.connect("dept.db")
  conn.execute("INSERT INTO departments (dept, budget_cents) VALUES ('HR', 5000)")
  conn.close()  # 没 commit 就关——不报错、不警告

  conn = sqlite3.connect("dept.db")
  print(conn.execute("SELECT COUNT(*) FROM departments WHERE dept = 'HR'").fetchone())  # (0,)
  ```

  插入、关闭、重开、查询——全程零异常，行没了。

- **Java 直觉为何失效**：JDBC 的默认是 `autoCommit=true`——每条语句即落即提交，Java 人
  「execute 完数据就在」的直觉是**被默认值惯出来的**；Spring 更是把事务包成声明式
  `@Transactional`，想忘了提交都没有机会。Python 的 sqlite3 恰好相反：默认**不自动提交**
  DML（`isolation_level=""` 的 legacy 行为：INSERT/UPDATE/DELETE 后停在未提交事务里），
  也没有声明式事务——忘了 `commit()` 或 `with conn:`，数据就停在未提交事务里随连接关闭
  一起蒸发，而且**不报错**。「编译器提示层」与「运行时防线」的错位在 Java 里由框架填平了，
  在 Python 里是你的事。
- **修复与纪律**：① 写路径一律 `with conn:` 包住（正常退出 commit、异常 rollback）——
  本课 `EventStore.append` 与 `DecisionCache.put` 内部都自带事务，调用方不用再管；
  ② DDL 也是写操作——建表后同样要提交（`EventStore.open` 里那行 `conn.commit()` 不是
  装饰）；③ 测试里每测一个独立 db 文件（`tmp_path` fixture）——「重启后账本空了」这类
  bug 才有被测到的机会（跨连接查是它的最小探测器：新开连接看不到未提交数据）。

## 6. 延伸

- 官方文档：sqlite3 标准库（连接/事务/Row/占位参数的全部语义）——
  https://docs.python.org/3/library/sqlite3.html ，重点读 «sqlite3.Connection» 的
  commit / context manager 与 «sqlite3.Row» 三节；
- 源码路标（本地克隆 `~/develop/opensource/`，按图索骥）：
  - `sst/opencode@95daf90670#packages/core/src/event/sql.ts` —— 产品级事件表的声明现场：
    `event(aggregate_id, seq, type, data)` + `event_aggregate_seq_idx` 唯一索引——
    本课 `events` 表的母本（SQLite + drizzle，A11 的真实形状）；
  - `TauricResearch/TradingAgents@be952b8#tradingagents/graph/trading_graph.py` ——
    `_run_signature`：图形状输入拼进 checkpoint thread_id（改分析师/轮次，旧检查点自动
    失效，#1089）——`run_key` 的先例原文（L4.2 复引，今晚轮到自己写）；
  - `virattt/ai-hedge-fund@fc1bf25#hedge_fund/llm/cache.py` —— PromptCache：48 行的
    缓存=审计=调试三合一文件版（L4.1 精读过）——今晚 `llm_decisions` 表的上一世；
  - `langchain-ai/langgraph@e539ac122#libs/langgraph/langgraph/pregel/main.py` ——
    Pregel 执行循环（L5.1 复引）：superstep 调度本体——本课事件序（seq）与 superstep
    的一一对应，调度器源码是最终解释。
- 研究蓝本（lab 仓内，写作输入）：A11 事件溯源会话存储 / A13 缓存即审计 / A15 审计绑定
  版式的模式条目与迁移要点见
  [../../../../research/agent-oss/report.md](../../../../research/agent-oss/report.md)
  §2.1；§4.5 审计基线 12 条 checklist——本课落地其中 ①（append-only 事件流）、
  ④（LLM 决策缓存即审计）、⑥（规则与拓扑版本进审计键），其余条目是 L5.4 与里程碑的工位。

## 离毕业又近的一块

审计面就位：每一单的执行史 append-only 落账、每一个模型决策可回放原话、每一版图自带
身份。最后一课 L5.4 在执行出口装 **fail-closed 门**——审批单 CONFIRMED 的二次校验 +
限额/黑名单/频次的纯函数检查链（不可解析即 DENY），并收口 **JAVA-MAPPING.md**：把
四课攒下的每个模式翻回 Java 栈的对应物。三条主链路（审批暂停/恢复、拒绝回环、fail-closed
拒绝）的集成测试见里程碑——它们会把今晚的事件表当审计证据链来断言。
