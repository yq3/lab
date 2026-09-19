# 改造说明：Vibe-Trading（L4.3 治理合规）

> 素材：L4.3 §3 Step 5 的加餐——本地建分支，把 `check_mandate` 抄改到自己的域，
> 照 `test_mandate_enforcement.py` 的 per-limit 思想写一组 pytest。本改造**零模型
> 调用、零网络**，纯标准库离线可复现（对齐产品哲学 §2.4）。固定五节
> （`tests/test_notes_meta.py` 按结构把关），`- TODO(改造)` 占位必须全部替换；
> 要求清单是任务卡，誊写结论时保留。

**改造要求（任务卡，写完保留）**

- 改造 · 检查链换域：精读 `agent/src/live/enforcement.py` 的 `check_mandate` 函数体
  与 `BreachEvent`（800 行文件只精读这两块），把科目/限额/黑名单换成你自己的域
  ——报销付款域可直接复用 L4.3 机制件 `code/enforcement.py` 的参数（单笔/日累计/
  日次数/科目白名单/黑名单，整数分）；
- 配套测试：照 `agent/tests/test_mandate_enforcement.py` 的 per-limit 思想写一组
  pytest——每查一个「只破这一项」用例 + 脏输入 fail-closed 用例（float/bool 金额、
  脏已付清单）+ 顺序断言（黑名单先于单笔），对版机制件 ex1 的 12 个测试项结构
  （用例表 9 + 顺序 + 覆盖型 meta + 纯函数确定性）；
- 前置阅读（每件 10 分钟）：`agent/src/live/mandate/model.py`（四件套 frozen
  dataclass，148 行）→ `enforcement.py` 精读 → `test_mandate_enforcement.py`；
- 锚定 commit：`HKUDS/Vibe-Trading@f84b2977`（克隆后 `git checkout f84b2977`）；
- 红线继承：检查链任何一处 `except` 的出口必须是 breach/DENY（§5 fail-open 兜底），
  你域里的测试要有一条脏输入用例钉死它。

## 改什么

写清你的域是什么（哪个行业/哪类单据）、检查链裁掉了哪几查、留了哪几查、限额参数
各是多少。形状：一段话 + 一张「产品八查 → 你的域 N 查」对照表（对版 Step1 的表）。

- TODO(改造)：域定义 + 裁剪对照表。

## 为什么

为什么值得抄改而不是重写：固定顺序检查链的价值在**顺序即语义**（结构性先于定量，
首查命中即停）与 fail-closed（不可解析即 breach）——这两条换个域一点不变，变的
只是限额与科目表。写清你的域里「结构性 vs 定量」的边界各是什么。

- TODO(改造)：一句动机 + 你的域里两种 kind 的划分。

## 最小 diff

新文件为主（你的域模块 + 测试文件），`git diff --stat` 或目录树摘录贴出新增/改动
清单；核心检查函数只贴与产品不同的一两段（如裁掉杠杆查、日次数改周次数）。

- TODO(改造)：文件清单 + 关键差异段摘录。

## 复现步骤

从克隆到测试全绿的命令序列（bash 块分步走）：clone → checkout 锚定 commit →
建分支 → 放入你的两个文件 → `uv run pytest <你的测试文件>`。每步一个检查点
（如测试收集到 N 项）。

- TODO(改造)：编号步骤 1..N + 每步一个检查点。

## 证据

测试通过摘要（`N passed`）+ 每查「只破这一项」的用例表摘录（参数化名单）+ 至少
一条脏输入 fail-closed 断言的原文，` ```text ` 块贴出并圈出断言行；截图另存
`notes/assets/`，贴不了图贴日志摘录。

- TODO(改造)：测试摘要 + 用例表 + 脏输入断言各一段。
