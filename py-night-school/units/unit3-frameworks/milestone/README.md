# Unit 3 里程碑：选型工作台（学段结业项目）

> 任务书 + 验收。没有逐节讲义——四重奏跑完了，最后一晚把「选哪个框架」从
> **体感**变成**证据**：三个动作，全部命令化、口径可复现。产出物就是 L3.8
> 对照总结课的输入：你自己的数据与结论。

## 你要造的东西（三个动作）

| # | 动作 | 命令（本目录下，uv run 跨平台） | 产出 | 判据 |
|---|---|---|---|---|
| ① | 四框架同题 demo 全量重验 | `uv run python bench.py` | 五课时 contract 重跑汇总表 | 退出码 0（五课时全 PASS） |
| ② | 决策表数据页 | `uv run python tablegen.py` | 依赖数 + 手写总行数（口径可复现） | 六行数据齐、口径打印在页内 |
| ③ | 对照笔记 + 决策表定稿 | 填 `notes/` 五页 + `summary.py` 的 TODO(s1)，然后 `uv run python summary.py` | 五页笔记 + 最终决策表 | 占位符全替换、聚合逻辑过 pytest |

动作 ①② 的脚本**给你**（读它们的 docstring，是本里程碑的知识点载体）；动作 ③
的笔记是你的作业、`aggregate()` 是唯一编码 TODO。

## 为什么是这副骨架（一个架构决定 + 三个新知识点）

**为什么 pytest 不直接去跑兄弟课？** 课程的验收脚本在一个只含 `milestone/` 与
`data/` 的干净副本里跑 pytest——兄弟课时不在副本里，测试碰它们必红。所以 bench 的
「执行」（subprocess 逐课真跑）是**学员命令**，你在真实仓库里自己跑；pytest 只测
**解析层纯函数**（判 pass/fail、汇总、降级）与「目录缺失→SKIPPED」分支，全部用
合成夹具离线跑。执行与解析分层，两边都能各自验收。

新知识点（给 Java 同学，细节在各文件 docstring）：

1. **subprocess 的安全用法**（bench.py）：`subprocess.run([..], cwd=..)` ≈
   `ProcessBuilder(..).directory(..)`——参数走列表不经 shell 解析（没有 shell=True，
   就没有注入，也没有「路径带空格就碎」）。两个实测踩坑也记在 bench.py 里：
   子进程继承 `VIRTUAL_ENV` 会让兄弟课时的 uv 告警、以及 `-q` 叠加成 `-qq`
   会吞掉 pytest 汇总行——环境该摘哪个变量、参数该传几个，都是契约。
2. **tomllib**（tablegen.py）：3.11 起进标准库的 TOML 解析器，`load` 一个二进制
   文件句柄得到 dict——数 uv.lock 的 `[[package]]` 就是 `len(data["package"])`，
   不用任何第三方依赖。
3. **ast 定位函数数行数**（tablegen.py，L3.4 `count_loc.py` 的同款纪律）：
   `ast.parse` → 按 qualname（带外层类/函数名的限定名，如 `Crew.kickoff`）找 def/class → 行区间剔 docstring → 数非空非注释行。
   量化结论必须写明工具与口径（Unit 2 的 292→249 教训的制度化），禁止 grep 管道。

## 动作一：bench 真跑五课时（本里程碑的灵魂）

在**真实仓库**的本目录下跑（干净副本里没有兄弟课时，bench 会如实标 SKIPPED）：

```bash
uv run python bench.py
```

发货态实测输出（2026-09-15，耗时随机器波动）：

```text
== Unit 3 里程碑 bench：四框架同题 demo 全量重验（共用验收 test_contract.py） ==
[ok] L3.1-openai-agents       openai-agents 0.22.2         PASS    (2 passed, 0 failed, 3.5s)
[ok] L3.2-langgraph-basics    langgraph 1.2.11（手装图）        PASS    (2 passed, 0 failed, 3.6s)
[ok] L3.4-langgraph-fanout    langgraph 1.2.11（prebuilt）   PASS    (2 passed, 0 failed, 3.6s)
[ok] L3.5-deepagents          deepagents 0.7.13            PASS    (2 passed, 0 failed, 4.4s)
[ok] L3.6-adk-python          google-adk 2.9.0             PASS    (2 passed, 0 failed, 33.7s)

| 课时 | 框架与装配 | 结果 | 耗时 |
|---|---|---|---|
| L3.1-openai-agents | openai-agents 0.22.2 | PASS | 3.5s |
| L3.2-langgraph-basics | langgraph 1.2.11（手装图） | PASS | 3.6s |
| L3.4-langgraph-fanout | langgraph 1.2.11（prebuilt） | PASS | 3.6s |
| L3.5-deepagents | deepagents 0.7.13 | PASS | 4.4s |
| L3.6-adk-python | google-adk 2.9.0 | PASS | 33.7s |

bench 退出码: 0（0=全绿；1=有 FAIL；2=全跳过）
```

langgraph 由两种装配代表（L3.2 手装图 / L3.4 prebuilt），**两份都绿才算 langgraph
绿**——这正是 summary 聚合时要你实现的合并规则。每课 2 个 contract 测试：四张单
的 expect 字段对账 + 覆盖型 meta 检查（三种 decision、两个部门必须齐、CALL_LOG
证明工具真被执行）。子进程命令、PATH 自查（找不到 uv 给友好报错）与降级逻辑
（课时目录缺失→SKIPPED）都在 `bench.py`。

## 动作二：tablegen 生成决策表数据页

```bash
uv run python tablegen.py
```

（可选落盘：`uv run python tablegen.py --out decision-table-data.md`。）

发货态实测（口径头 + 核心表；页内还打印每行的「口径明细」——数了哪些 `文件::qualname`，
及每行的「= L3.8 装配 + 节点 + 胶水」拆分）：

```text
- 手写总行数（装配+节点+胶水）：ast 定位各课手写函数（对照行是被框架替掉的四个零件），剔 docstring 后数非空非注释行。

| 框架与装配 | 依赖数（uv.lock 包） | 手写总行数（装配+节点+胶水，ast 口径） |
|---|---|---|
| openai-agents 0.22.2 | 51 | 29 |
| langgraph 1.2.11（手装图） | 54 | 63 |
| langgraph 1.2.11（prebuilt） | 54 | 28 |
| deepagents 0.7.13 | 70 | 71 |
| google-adk 2.9.0 | 88 | 33 |
| mini-agent（Unit 2 对照组） | 44 | 86 |
```

读法（这些数字回答的问题）：

- **依赖数**（tomllib 数 uv.lock `[[package]]`，含 dev 四件套及传递依赖，六行同
  口径）：抽象光谱越往右越重——原语层 51 → harness 70 → 全家桶 88；对照组 44。
- **手写总行数（装配+节点+胶水）**（ast 口径：各课同题 demo 里你亲手写的**全部**
  函数；对照行取 solution 参考答案里「被四框架替掉的四个零件」：ReAct 循环 +
  工具 schema 生成 + 注册表分发 + 结构化校验回喂）：手装图 63 vs prebuilt
  28——「约定优于配置」的定价；对照组 86——这就是「它替你付掉了什么」的
  可复现版本，与 Unit 2 README 的「五模块全量 249 行」是**不同口径**（那里数
  全部，这里只数被替掉的零件）。
- **与 L3.8 决策表数据页的对账**（先读 L3.8 再跑本工作台的同学看这条）：L3.8 把
  成本拆两列——装配 loc（装进框架的行）与自写节点/循环 loc（框架没替你付的循环
  内脏）；本页数全量，恒等式：**手写总行数 = L3.8 装配 loc + L3.8 自写节点 loc +
  胶水**（入口消息、模型客户端、run_review 运行编排等两页都没单列的部分）。
  发货态逐课对账：29=15+0+14、63=10+20+33、28=6+0+22、71=8+0+63、33=9+0+24。
  为什么一个数全量、一个拆列？工作台答「**我一共要写多少行**」（动手前的预算），
  决策表答「**框架替我写了哪部分**」（选型时的归因）——同源不同问，两页都留着。
- deepagents 的 71 行偏高有个诚实原因：harness 的默认行为多（子代理转交、底稿
  落盘、结构化收尾），五轮剧本编排占行数（它的 63 行胶水是五课最厚）——「默认件
  越全，编排成本越高」本身是结论的一部分（口径明细里写明含它）。

## 动作三：notes 五页 + summary 的 TODO

五页笔记（`notes/mini-agent.md`、`openai-agents.md`、`langgraph.md`、
`deepagents.md`、`adk-python.md`），每页固定五节（`tests/test_notes_meta.py`
按结构把关）：

| 小节 | 回答什么 |
|---|---|
| 它替 mini-agent 付掉了什么 | 替掉的**行**（对到 mini-agent 的哪个文件） |
| 它没替你付什么 | 留给你的纪律与设计决策 |
| 最惊讶的一个机制 | 一个机制 + 课次 + 为什么惊讶 |
| 锁定性一句话 | 一句压秤的话（summary 会抓进决策表） |
| 什么时候选它 | 两个正例场景 + 一个反例 |

每节模板里的问题只是脚手架——回答完删掉问题、留下结论，`TODO(笔记)` 占位符
必须全部替换（模板页脚手架问题的素材都指向各课讲义的真实机制，先翻讲义再写）。
结构测试的完成态以 `solution/notes/` 为准（那是无占位符的完成版，供你誊写对照
收口——你的结论不必与它相同，结构必须相同）。

然后填 `summary.py::aggregate()`（唯一编码 TODO）：把 bench 结果、tablegen 数据、
笔记的「锁定性一句话」按框架 key join 成决策表。卡住先想 10 分钟，再看三级提示：

> **IDE 侧（PyCharm / IDEA + Python 插件）**：本里程碑唯一编码点 `aggregate()`——直接 Run `summary.py` 报错时，在 `aggregate()` 内打断点 Debug，Variables 面板看三路数据（bench 结果 / tablegen 数据 / 笔记）的真实形状再拼，字段对不上是这里最高频的卡点。另外：bench.py 的五课时重跑是子进程——在子进程内打断点不命中是正常的，调试请调解析层的纯函数。

```bash
uv run python -c "from hints import hint; print(hint('aggregate', 1))"
uv run python -c "from hints import hint; print(hint('notes', 1))"
```

填完后 `uv run python summary.py` 出定稿。完成态示例（笔记取 solution 完成版；
你的表格数字相同，最后一列是你自己的话）：

```text
| 框架 | contract 重验 | 依赖数（lock 包） | 手写总行数（装配+节点+胶水） | 锁定性一句话 |
|---|---|---|---|---|
| mini-agent（Unit 2 对照组） | — | 44 | 86 | 零框架依赖：每个行为都是你要亲手的行，也因此每个行为都是你能改的行。 |
| openai-agents 0.22.2 | PASS | 51 | 29 | 原语层几乎无锁定（薄包装 + 普通对象），但默认值有牙齿：trace 外发与 Responses API 路径是它的私有默认。 |
| langgraph 1.2.11（L3.2 手装 + L3.4 prebuilt） | PASS | 54 | 63 / 28 | 图与节点是我的代码（可 git、可单测），但 StateGraph/reducer/interrupt/Send 是 langgraph 私有词汇——与 Java 生产栈同源，锁定可翻译。 |
| deepagents 0.7.13 | PASS | 70 | 71 | 锁定不在 API 在默认值与中间件栈：工具越全的 harness 越要会收窄，且它站在 langgraph 之上——锁定是叠加的。 |
| google-adk 2.9.0 | PASS | 88 | 33 | 四框架锁定最重：图纸（四类回调、五种服务、目录约定）只有它家有，部署形态偏向 GCP。 |
```

## 验收（全部绿 = Unit 3 结业）

```bash
uv run pytest
uv run ruff check .
uv run pyright
uv run python bench.py
```

前三条全绿 + bench 退出码 0 + 五页笔记占位符全替换 = 里程碑完成。发货态诚实
说明：`tests/test_summary.py` 的 3 个 `aggregate` 测试是**设计内的红**（TODO 未填
抛 `NotImplementedError`，与练习区 TODO 同性质），其余 26 个测试（bench 解析层 /
tablegen 合成夹具 / 笔记结构 meta / summary 给定件）发货态就必须绿。

完成后回到 [unit3-frameworks/README.md](../README.md) 打卡里程碑，然后进 L3.8。

## 与 L3.8 的分工

L3.8 讲**方法论**（能力-成本-锁定性的决策框架、crewai/llama_index/agentscope
跳读指南、结业自查表）；本里程碑产出**你自己的数据与结论**——带着这张表去上
L3.8，每个方法论格子里填的都是你跑出来的数字和你写过的话，而不是教材的转述。
两页数据同名数字只有依赖数一列（44/51/54/54/70/88，口径相同）；行数列刻意
不同名也不同问——本页「手写总行数」答预算（我一共要写多少），L3.8「装配 loc /
自写节点 loc」答归因（框架替我写了哪部分），恒等式对账见动作二。

## 目录

```text
milestone/
├── README.md            # 本任务书
├── bench.py             # 动作①：跨课重验（解析层纯函数 + 执行层薄壳；给定）
├── tablegen.py          # 动作②：tomllib + ast 口径的定量提取（给定）
├── summary.py           # 动作③：聚合（TODO(s1) 在 aggregate；其余给定）
├── notes/               # 五页对照笔记模板（TODO(笔记) 占位）
├── hints.py             # 三级渐进提示（aggregate / notes）
├── tests/               # 四组离线验收（不要改；不碰兄弟课时）
│   ├── test_bench_logic.py
│   ├── test_tablegen.py
│   ├── test_notes_meta.py
│   └── test_summary.py  # 含 3 个设计内红（aggregate TODO）
├── solution/            # summary.py 完成版（结业时复制到本目录根替换 TODO 版）+ notes/ 完成版（不复制，供誊写对照）
└── pyproject.toml / uv.lock / .env.example / .python-version
```

## 离毕业又近的一块

毕业设计开工前的技术评审（L5.0）今晚有了全部输入：执行器选型的证据链
（bench 五课全绿 = 四个框架你都真跑过，不是听说）、成本的量化口径（依赖数与
手写总行数可复现）、锁定性判断（五页笔记，每页一句话）、以及「spoiler：毕设用
langgraph」现在可以自己重新推导一遍——L3.3 的 checkpoint/interrupt 就是
L5.2 审批外化的直接机制。决策表在手，剩下的只是把引擎、机制、选型组装成产品。
