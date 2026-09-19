# Unit 5 里程碑：毕业设计收口（学段结业项目 · 全教程收官件）

> 任务书 + 验收。没有逐节讲义——三十课走到这里，讲义已经不需要了：**四课攒的每一层
> 都在这个目录里，毕业判据是你亲手把它们钉进测试**。CURRICULUM 对本里程碑的定义：
> 可运行 PoC + 三条主链路（审批暂停/恢复、拒绝回环、fail-closed 拒绝）pytest 集成测试
> 全绿 + JAVA-MAPPING.md。

## 毕业判据（三条，全满足 = 毕业）

1. **三条主链路测试全绿**：`tests/test_graduation.py` 的四张链路测试（③有两个变体）——
   最关键的三处取证断言是你填的（`graduation_checks.py` 的三个 TODO）；
2. **JAVA-MAPPING.md 定稿**：4 行 `TODO(毕业)` 占位全部补全（对照本地克隆核实——诚实
   纪律：克隆里没有的写「需自建」），`tests/test_mapping_meta.py` 结构把关全绿；
3. **三命令全绿**（本目录下，uv run 跨平台）：

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

## 你要造的东西（三个交付物，PoC 是给定件）

| 交付物 | 形态 | 谁写 |
|---|---|---|
| 可运行 PoC（四层合体） | 目录根的 17 个模块（图/审批/事件/门，L5.4 对版件） | 给定——不要改 |
| 三条主链路 pytest 集成测试 | `tests/test_graduation.py`（given 断言 + meta）+ `graduation_checks.py`（3 个 TODO） | 断言主体 given；三颗取证钉子你写 |
| JAVA-MAPPING.md 定稿 | 根目录 `JAVA-MAPPING.md`（4 行占位待补） | 你写（对照克隆核实） |

**为什么 PoC 全给定**：四课你已经把每一层都亲手写过（L5.1 图、L5.2 审批面、L5.3 事件层、
L5.4 门——每课的 exercises 都是你填的）；毕业设计考的不是再写一遍，是**读懂一张合体系统
并证明它按合同工作**。所以你的两块作答物都关于「证据」：从事件表取证的断言工装，
与从 Java 克隆核实的映射表。

## 学员任务一：graduation_checks.py 的三颗钉子（本里程碑唯一编码 TODO）

`tests/test_graduation.py` 把三条链路跑通、给出绝大部分断言（不要改它）；每条链路最关键
的一处取证留给你——**工装只做断言，取证入口是 `store.events_for(...)`（L5.3 层）**：

| TODO | 链路 | 断什么 |
|---|---|---|
| TODO(g1) `assert_stream_tail` | ①核心，③复用 | 事件流以 expected_tail 顺序收尾 + 整条 seq 从 0 连续无空洞 |
| TODO(g2) `assert_hash_rotated` | ②核心 | 拒绝回环重生成后两张审批单的 content_hash 非空且互异（A6） |
| TODO(g3) `assert_zero_payments` | ③核心 | 当日账本聚合上 payment.executed 零条（「没付」的铁证） |

> **IDE 侧**：写断言前先 Debug 跑 `tests/test_graduation.py` 的单个链路测试（运行 ≠ 修改，不违「不要改」）——在断言处用 Evaluate Expression 直接执行 `store.events_for(...)` 看事件元组的真实形状，回去再填 `graduation_checks.py` 的 TODO。「先看形状再写断言」正是 debugger 相对 print 的强项。

卡住先想 5 分钟，再看三级渐进提示（每次只看一级）：

```bash
uv run python -c "from hints import hint; print(hint('g1', 1))"
```

（另两把钥匙：`hint('g2', 1)` 指纹轮换怎么断、`hint('mapping', 1)` 映射行怎么写才算核实过。）

手动看效果（填 TODO 前后各跑一次，对照事件流水读法）：

```bash
uv run python step1_gate.py
uv run python demo_final.py
```

## 学员任务二：JAVA-MAPPING.md 定稿（4 行占位补全）

根目录 `JAVA-MAPPING.md` 主表 13 行里有 4 行的「Java 对应物」列留了 `TODO(毕业)`：
Plan 判别联合 / fail-closed 执行门 / 缓存即审计 / 拒绝回环。补全口径：

- **核实过再写**：克隆在 `~/develop/opensource/`（langgraph4j@`c2cf2e33`、
  spring-ai-alibaba@`f82da0b50`，锚点在文档末尾）——写下的每个类名/方法名都在克隆里
  亲眼见过；克隆里没有的老实写「需自建」+ 一句为什么；
- 结构把关在 `tests/test_mapping_meta.py`：主表 ≥13 行、四列非空、「需自建」两行保留
  （图版本绑定 / 当日账本——诚实纪律不可丢）、占位行数与全文标记数互证；
- 参考对照版在 `solution/JAVA-MAPPING.md`（golden answer 以行尾注释给出，避免剧透）——先自己写再对，
  差异处才是认知增量。

## 验收（全部绿 = Unit 5 结业 = 全教程毕业）

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

发货态诚实说明：11 个测试里 4 张链路测试是**设计内的红**（`graduation_checks.py` 的
TODO 未填抛 `NotImplementedError`，落在 tests/——三态验证允许的精确红）；其余 7 个
（2 个支撑测试 + 1 个判据对齐 meta + 4 个映射结构测试）发货态就必须绿。填完 TODO、
补完 4 行占位后全绿即毕业。

### 重验四课三态（学员命令清单，bash 逐行、不串联）

毕业前值得把四课各重验一遍（它们是本 PoC 的对版上游——它们不绿，这里的全绿没有根）。
在**仓库根**（克隆处，按你的实际路径）逐条执行，每条结尾应见「三态验证 PASS」：

```bash
cd py-night-school
uv run python scripts/three_state_check.py units/unit5-capstone/L5.1-plan-graph
uv run python scripts/three_state_check.py units/unit5-capstone/L5.2-approval-api
uv run python scripts/three_state_check.py units/unit5-capstone/L5.3-event-sourcing
uv run python scripts/three_state_check.py units/unit5-capstone/L5.4-execution-gate
uv run python scripts/three_state_check.py units/unit5-capstone/milestone
```

（最后一行是本里程碑自己的三态：发货态精确红 → solution 覆盖后的毕业态全绿。）

## PoC 模块地图（四层各来自哪课——L5.4 溯源表的里程碑版）

四层合体：**图**（L5.1 静态拓扑 + 计划驱动）+ **审批面**（L5.2 interrupt 换芯 + 三元回复）+
**事件层**（L5.3 append-only + 缓存即审计 + 图版本绑定）+ **门**（L5.4 fail-closed 七查）。

| 模块 | 来自 | 里程碑差异 |
|---|---|---|
| gate.py | L5.4（核心①：纯函数七查 + 三态裁决） | 无（字节相同） |
| graph.py | L5.4（核心②：四层合体图 + PaymentLedger） | 无 |
| eventstore.py | L5.3，L5.4 扩词汇表至 12 类 | 无 |
| approvals.py | L5.2 + L5.4 审计/门接线 | 无 |
| api.py | L5.2（HTTP 契约原样存活） | 无 |
| demo.py | L5.2 + L5.3（统一审计出口） | 无 |
| demo_final.py / step1_gate.py | L5.4 三链路预演 / 检查链六幕 | step1_gate 用法行去 code/ 前缀（唯一差异） |
| advice / review_rules / mock_endpoint / executor / plan / prompts | L5.1（经 L5.3/L5.4 对版链） | 无 |
| mock_tools.py | L3.2（经 L5.1 对版链） | data/ 相对深度 parents[4]→parents[3]（里程碑层级浅一层，就地注释声明） |
| audit_cache.py / versioning.py | L5.3 | 无 |
| JAVA-MAPPING.md | L5.4（核心③） | 表头「学员任务」段改写 + 占位标记 TODO(ex3)→TODO(毕业)；表格主体/锚点/词汇表逐字相同 |

对版纪律执行记录：除上表声明处外全部与 L5.4 `code/` **字节相同**（`diff` 可验）；L5.4
讲义区的 9 个 `test_*.py` 不随迁——里程碑验收面是 `tests/` 的毕业测试，L5.4 回归由上面
的重验命令覆盖（unit2/3/4 里程碑同构：里程碑 tests/ 全新写，不复制课时测试）。

## CURRICULUM §7 结业自查表（逐条收录，全勾 = 毕业）

- [ ] **语言**：手写 async 并发 fetcher + retry 装饰器，不查资料——对照 L1.4/L1.6（忘了
  就回炉，顺手把 L5.2 §5 的「事件循环里睡死」讲给自己听）；
- [ ] **地基**：能向别人讲清「一个 agent 循环的一轮发生了什么」（从 API 消息到工具回喂）
  ——对照 L2.1/L2.2 与 Unit 2 mini-agent；今天这张图你在毕业测试的事件流水里逐 superstep
  又断言了一遍；
- [ ] **框架**：mini-agent vs 四框架决策表能自己重新推导——对照 L3.8 与 Unit 3 里程碑
  工作台（装配 loc 与手写 loc 两列的口径还记得吗）；
- [ ] **产品**：完成 3 个产品的指定改造并复现——L4.1 llm/cache.py 精读、L4.2 辩论轮次
  参数化 + 预算封顶、L4.3 mandate 检查链抽单测（改造说明在 Unit 4 里程碑的 notes/）；
- [ ] **毕业**：PoC 三条主链路测试全绿，JAVA-MAPPING.md 可作为 Java 侧开发任务拆解输入
  ——就是本目录的两块作答物；拿去开 Java 侧任务会吧（一行 = 一个可派工的迁移件）。

## 目录

```text
milestone/
├── README.md               # 本任务书
├── JAVA-MAPPING.md         # 作答物②：映射表定稿（4 行 TODO(毕业) 占位待补）
├── graduation_checks.py    # 作答物①：三链路取证断言（TODO(g1)/(g2)/(g3)；唯一编码 TODO）
├── gate.py / graph.py / eventstore.py / approvals.py / api.py / audit_cache.py / versioning.py
│                           # 四层合体 PoC（L5.4 对版件，给定——不要改）
├── advice.py / executor.py / plan.py / prompts.py / mock_tools.py / review_rules.py / mock_endpoint.py
├── demo.py / demo_final.py / step1_gate.py   # 驱动器与三链路预演（给定）
├── hints.py                # 三级渐进提示（g1 / g2 / mapping）
├── tests/                  # 毕业测试（不要改）
│   ├── test_graduation.py  # 三链路四张 + 支撑两张 + 判据对齐 meta 一张
│   └── test_mapping_meta.py# JAVA-MAPPING 结构把关四张
├── solution/               # graduation_checks.py 完成版（覆盖到根）+ JAVA-MAPPING 对照版 + README
└── pyproject.toml / uv.lock / .env.example / .python-version
```

## 「离毕业又近的一块」——今晚退役

这句话从 L0.1 讲到 L5.4。三十课的明线（一张报销单从 mock 数据走到带门付款）与暗线
（每课攒下的模式）在这里合流：图会跑、人会批、账会记、门会拦，每一步的证据都被你亲手
断言过。毕业证不是一张证书——是 `JAVA-MAPPING.md` 那张表：Python 侧三十课的每个模式，
都有了回 Java 栈的地址。去把它们钉成 Java 侧的第一个任务吧。
