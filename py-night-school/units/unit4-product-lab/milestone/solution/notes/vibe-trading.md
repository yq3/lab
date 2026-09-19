# 改造说明：Vibe-Trading（L4.3 治理合规）

**改造要求（任务卡）**

- [x] `check_mandate` 抄改到报销付款域（科目/限额/黑名单换域）；
- [x] 照 `test_mandate_enforcement.py` 的 per-limit 思想写一组 pytest；
- [x] 前置阅读三件（mandate/model.py → enforcement.py 精读 → 测试文件）；
- [x] 锚定 `HKUDS/Vibe-Trading@f84b2977`。

## 改什么

域定义：报销付款域（高金额不可逆动作，金额一律整数「分」）——直接复用 L4.3 机制件
`code/enforcement.py` 的参数集。域内新两个文件（放克隆里的独立目录，不碰产品源码）：

- `lab_domain/mandate_check.py`：抄改 `agent/src/live/enforcement.py#check_mandate`
  ——八查裁成七查（对版 L4.3 Step1 的对照表）：意图可解析 / 收款方黑名单 / 科目
  白名单 / 单笔上限 / 当日累计 / 日次数 / 授权过期；裁掉资产类别、杠杆、资金防线
  （付款域无对应物）；`BreachEvent` 合同保留 kind 两值（structural / quantitative）；
- `lab_domain/test_mandate_check.py`：per-limit 测试组。

产品八查 → 本域七查的裁剪对照（对版 Step1 表的形状）：

| # | 产品（交易域） | 本域（付款域） | kind |
|---|---|---|---|
| 0 | 意图可解析（symbol/side） | 意图可解析（收款方/科目/正整数分） | structural |
| 1 | exclude_symbols 黑名单 | excluded_vendors 黑名单 | structural |
| 2 | 工具类型白名单（空=全拒） | 科目白名单（空=全拒） | structural |
| 3 | 单笔名义额（不可定价→breach） | 单笔上限 | quantitative |
| 4 | 交易后总敞口 | 当日累计（已付条目解析失败→breach） | quantitative |
| 5 | 杠杆/资金（裁掉） | 日次数 | quantitative |
| 6 | 日次数 | 授权过期（收进链尾） | quantitative→structural |

## 为什么

抄改而不是重写：检查链的价值在**顺序即语义**（结构性先于定量、首查命中即停——黑名单
违规永远不该先撞单笔限额）与 **fail-closed**（不可解析即 breach）——这两条换域不变，
变的只是限额与科目表。本域的结构性/定量边界：黑名单、科目白名单、授权过期是结构性
（不改合同永远不可能放行）；单笔、日累计、日次数是定量（量太大，重新授权可解）。
另一条动机是 L5.4：这就是毕业设计 fail-closed 执行门的预演。

## 最小 diff

新增文件清单（`git status --short` 口径）：

```text
?? lab_domain/__init__.py
?? lab_domain/mandate_check.py     # check_mandate 抄改：八查 -> 七查，参数换付款域
?? lab_domain/test_mandate_check.py  # per-limit 测试组（12 项）
```

与产品的关键差异段（mandate_check.py 里，唯一不是照抄的部分——杠杆/资金镜像裁掉后，
日次数从第 6 查上移）：

```python
def check_payment(mandate, intent, today):
    """付款域七查：固定顺序，首查命中即返回（对版产品 check_mandate 的裁剪版）。"""
    checks = (
        _intent_parseable,      # 0 structural
        _vendor_not_excluded,   # 1 structural
        _category_allowed,      # 2 structural（空白名单=全拒）
        _single_cap,            # 3 quantitative
        _daily_total_cap,       # 4 quantitative（脏已付清单 -> breach，fail-closed）
        _daily_count_cap,       # 5 quantitative
        _mandate_not_expired,   # 6 quantitative->structural
    )
```

## 复现步骤

1. `git clone git@github.com:HKUDS/Vibe-Trading.git ~/develop/opensource/Vibe-Trading`
   ——检查点：`git log --oneline -1` 显示 f84b2977；
2. `cd ~/develop/opensource/Vibe-Trading`；
3. `git checkout f84b2977`；
4. `git switch -c lab/payment-domain-chain`；
5. 前置阅读三件（每件 10 分钟）：`agent/src/live/mandate/model.py` →
   `agent/src/live/enforcement.py`（只精读 `check_mandate` 函数体与 `BreachEvent`）→
   `agent/tests/test_mandate_enforcement.py`——检查点：能说出 per-limit 用例表怎么组织；
6. 放入 `lab_domain/` 两个文件（从 L4.3 机制件 `code/enforcement.py` 起步改最快——
   它已是付款域七查的骨架）；
7. `uv run pytest lab_domain/test_mandate_check.py`——检查点：收集到 12 项、全绿。

## 证据

（范本注：本改造零模型调用零网络，你的真证据就是测试输出——机制件替身在此与真跑
几乎同构，对版本课讲义区验收。）

机制件替身（L4.3 `uv run pytest code/` 的真实输出）：

```text
................................                                [100%]
32 passed in 0.03s
```

per-limit 用例表摘录（lab_domain/test_mandate_check.py 的参数化名单，对版
`test_mandate_enforcement.py` 的 per-limit 思想）：

```text
只破单笔:    amount=200001, 其余合规 -> PAUSE_FOR_REAUTH (quantitative, max_single)
只破日累计:  已付 480000 + 本次 30000 -> PAUSE_FOR_REAUTH (max_daily_total)
只破日次数:  已付 3 笔 + 第 4 笔      -> PAUSE_FOR_REAUTH (daily_count)
只破黑名单:  payee=sketchy-mall      -> DENY (structural, excluded_vendors)——先于单笔命中
脏输入:      amount_cents="900,000.00"（千分位）-> DENY (structural, intent_parseable)
```

指认：黑名单用例断言命中顺序在第 3 查之前（结构性先于定量）；脏输入用例钉死
fail-closed（§5 fail-open 兜底的机器证明——谁把兜底改成 `return None`，这条立刻红）。
交作业时贴你自己 `uv run pytest lab_domain/ -v` 的输出摘录 + 至少一条脏输入断言原文。
