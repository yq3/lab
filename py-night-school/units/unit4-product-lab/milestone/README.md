# Unit 4 里程碑：产品改造工作台（学段结业项目）

> 任务书 + 验收。三课产品实战跑完，结业判据（CURRICULUM「Unit 4 里程碑」）：
> **三个产品各 1–2 个可复现改造 + 三份改造说明**。真改造发生在你自己的产品克隆里，
> 本仓库测不到它的内容——但机器能验的部分（机制件三态 + 说明结构）都在这个工作台里。
> 工作台骨架对版 Unit 3 里程碑（bench.py 的分层纪律原样继承，见文末对齐表）。

## 你要造的东西（两个层次）

| 层 | 动作 | 命令 / 载体 | 判据 |
|---|---|---|---|
| ① 机制件层（自动可验收） | 三课 `code/` 三态跨课重验 | `uv run python verify.py` | 退出码 0（三课讲义区全 PASS） |
| ② 产品真改造层（你的动作） | 每课 §3 加餐指定的改造，在**自己克隆的本地分支**上完成 | `notes/` 三份改造说明 | 五节齐、`TODO(改造)` 占位符全替换（meta 测试把关） |

**为什么拆两层**：CURRICULUM 的里程碑定义是「3 个产品各 1–2 个可复现改造」——真改造
在你的产品克隆里，pytest 够不着它；但三课机制件（`code/`）是产品机制的**对版抽取件**
（层级投票 / 条件边辩论 / fail-closed 检查链），它们的三态就是「机制我真的跑过」的
机器证据。所以层① 用 verify.py 子进程逐课重跑 `uv run pytest code/`（只跑讲义区——
`exercises/` 是各课自己的学员作答区，发货态含设计内 TODO 红，不进本里程碑判据）；
层② 把真改造写成三份说明：**结构**（章节齐、任务卡的关键物点名）机器把关，
**内容质量**你自己负责——开放设计题不硬造判分（里程碑的一贯形态：结构机器把关，内容自查）。

## 使用步骤

层①（在本目录下，跨平台，bash 块分步走）：

```bash
uv run python verify.py
```

层②（每课一次，细节全在 notes/ 模板头部的「改造要求」任务卡里）：

1. 克隆产品仓库并 checkout 到锚定 commit（fc1bf25 / be952b8 / f84b2977）；
2. 建本地分支，按任务卡完成 1–2 个改造（L4.1：改人格 prompt 或 mandate YAML
   `weight:` 并重跑观察；L4.2：轮次参数化两态 + `max_debate_llm_calls` 预算封顶贯穿
   `conditional_logic.py`；L4.3：`check_mandate` 抄改到自己域 + per-limit pytest）；
3. 把「改什么 / 为什么 / 最小 diff / 复现步骤 / 证据」写进 `notes/` 对应页，替换全部
   `TODO(改造)` 占位符——卡住先想 10 分钟，再看三级提示：

```bash
uv run python -c "from hints import hint; print(hint('notes', 1))"
```

（另两把钥匙：`hint('repro', 1)` 复现步骤怎么写得可复现、`hint('evidence', 1)` 证据
怎么摘录。）

> **IDE 侧**：改造说明的「最小 diff」「证据」两节天然由 IDE 产出——Show Diff 拷贝统一 diff，Run 窗口右键 Copy All 摘日志，Local History 找回中间态。

## verify 实测输出（发货态，2026-09-16，耗时随机器波动）

```text
== Unit 4 里程碑 verify：三课机制件跨课重验（讲义区 code/ 三态） ==
[ok] L4.1-ai-hedge-fund             ai-hedge-fund fc1bf25（层级投票）      PASS    (19 passed, 0 failed, 6.6s)
[ok] L4.2-tradingagents-debate      TradingAgents be952b8（辩论-裁决）     PASS    (39 passed, 0 failed, 6.7s)
[ok] L4.3-vibe-trading-governance   Vibe-Trading f84b2977（治理合规）      PASS    (32 passed, 0 failed, 0.2s)

| 课时 | 产品（锚定 commit） | 结果 | 耗时 |
|---|---|---|---|
| L4.1-ai-hedge-fund | ai-hedge-fund fc1bf25（层级投票） | PASS | 6.6s |
| L4.2-tradingagents-debate | TradingAgents be952b8（辩论-裁决） | PASS | 6.7s |
| L4.3-vibe-trading-governance | Vibe-Trading f84b2977（治理合规） | PASS | 0.2s |

改造说明完成度（只报状态不判分——退出码只看机制件层；结构把关在 pytest 的 meta 测试）：
  ai-hedge-fund   模板态：占位符未替换（对照 solution/notes 收口）
  tradingagents   模板态：占位符未替换（对照 solution/notes 收口）
  vibe-trading    模板态：占位符未替换（对照 solution/notes 收口）

verify 退出码: 0（0=全绿；1=有 FAIL；2=全跳过）
```

三课共 90 个讲义区测试（19 + 39 + 32）。末尾的完成度报告只报状态不判分——退出码
只反映机制件层；改造说明的结构把关在 pytest 的 meta 测试里。

## 骨架怎么读（三个纪律，写给 Java 同学）

1. **执行与解析分层（verify.py）**：解析层（`parse_pytest_summary` / `verdict` /
   `exit_code` / `notes_status`）是纯函数；执行层（`run_lesson`）是薄壳——**runner
   可注入**：默认实现起真 subprocess（`subprocess.run([...], cwd=...)` ≈ Java 的
   `ProcessBuilder`，参数走列表不经 shell 解析），`tests/` 注入 fake runner 喂合成
   输出离线验收 PASS/FAIL/超时分支。为什么 pytest 不直接去跑兄弟课目录（Unit 3 里程碑的
   先例）：课程的验收脚本在一个只含 `milestone/` 与 `data/` 的干净副本里跑——
   兄弟课目录不在副本里，测试碰它们必红。真跑（`uv run python verify.py`）
   是学员命令；在验收副本里跑会如实标 SKIPPED、退出码 2——「没跑」绝不伪装成
   「全绿」。
2. **verify 的两个命令契约**（都在 `tests/test_verify_logic.py` 钉死）：只跑
   `pytest code/` 不碰 `exercises/`（里程碑验机制件层，不替各课判毕业）；不叠 `-q`
   （各课 addopts 已带，叠成 `-qq` 会吞掉汇总行——Unit 3 实测踩坑的制度化）。另有
   `VIRTUAL_ENV` 摘除（子 `uv run` 的告警走 stderr 且出现在汇总行之后，混进解析会
   误判失败）。
3. **改造说明是作答物，文档不硬造判分**：`tests/test_notes_meta.py` 只判结构——三页
   齐、五节齐且正文非空、模板态每节都有占位符（防预填）、含占位符的页必须有
   `solution/notes` 完成版对照；meta 测试的期望关键词从三课讲义提炼成合成夹具
   （不依赖产品仓）；你只需知道它查结构不查内容。内容质量没有
   机器判据——对照 `solution/notes/` 的范本收口（先例 Unit 3 milestone）。

## 验收（全部绿 = Unit 4 结业）

```bash
uv run pytest
uv run ruff check .
uv run pyright
uv run python verify.py
```

前三条全绿 + verify 退出码 0 + 三份说明占位符全替换 = 里程碑完成。

发货态诚实说明：**本里程碑没有设计内红**——与 Unit 3 里程碑（aggregate TODO 的 3 个
设计内红）不同，本里程碑的作答物是文档（notes/*.md 不可 pytest 判分，meta 测试只查
结构），verify.py 是给定基础设施不含 TODO，所以发货态与毕业态的三命令本来就全绿。
这在三态验证法下是合法形态（三态只要求「红必须是设计内的」——零失败时该条件自然成立；里程碑
的作答物是文档）。配套的毕业态布局：三态的 solution 覆盖规则只 glob `solution/*.py`
覆盖到目录根——本里程碑 solution/ 只有 `.md`（范本说明，不参与覆盖），毕业态镜像与
发货态同构。防「预填答案」由 meta 测试守着（模板态五节每节必须有占位符）。

## 目录

```text
milestone/
├── README.md            # 本任务书
├── verify.py            # 层①：跨课重验（解析层纯函数 + 可注入执行层；给定）
├── notes/               # 层②：三份改造说明模板（TODO(改造) 占位；任务卡在页首）
│   ├── ai-hedge-fund.md
│   ├── tradingagents.md
│   └── vibe-trading.md
├── hints.py             # 三级渐进提示（notes / repro / evidence）
├── tests/               # 离线验收（不要改；不碰兄弟课目录）
│   ├── test_verify_logic.py   # fake runner 注入合成输出（零子进程）
│   └── test_notes_meta.py     # 三页结构 + 任务卡关键词对齐（合成夹具）
├── solution/            # notes/ 三份完成版范本（不走覆盖，供誊写对照）+ README
└── pyproject.toml / uv.lock / .env.example / .python-version
```

## 与 Unit 3 里程碑的对齐与差异

| 物 | Unit 3（选型工作台） | Unit 4（本工作台） |
|---|---|---|
| 跨课重验 | bench.py 跑五课 contract | verify.py 跑三课 code/（exercises 不进判据） |
| 执行层可测性 | 目录缺失→SKIPPED 一个分支可离线测 | runner 可注入：PASS/FAIL/超时/命令契约全离线测 |
| 学员编码 TODO | summary.py::aggregate（3 个设计内红） | 无——作答物是文档，无设计内红也合法 |
| 笔记/说明 | 五页对照笔记 + 元测试 | 三份改造说明 + 元测试（多了任务卡关键词对齐） |
| solution | summary.py 完成版（覆盖到根）+ notes 完成版 | 只有 notes 完成版（不参与覆盖，见上文布局说明） |

分层纪律（执行是学员命令、测试只用合成夹具、真跑不进 pytest）原样继承。

## 离毕业又近的一块

Unit 5 开工前的最后一块拼图今晚齐了：三个产品你不止读过——机制件 90 个测试亲手跑绿
（verify 的证据链），真改造各做过 1–2 个（改造说明就是可复现的施工档案）。毕业设计
的三块蓝本（L4.1 加权合成与 clamp → L5.1 确定性执行器；L4.2 条件边循环与 REVIEW 哨兵
→ L5.1 重规划回环 / L5.4 输入卫生；L4.3 检查链与哈希链 → L5.4 执行门 / L5.3 审计
账本）现在都有「改过」的体感，不只是「读过」。剩下的只有一件事：把它们组装成你自己的
产品——Unit 5 见。
