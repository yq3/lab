# solution/ —— L5.4 参考答案

覆盖用法（三态验证的毕业态自动做，手动看 diff 时）：

```bash
cp solution/ex1_gate.py exercises/ex1_gate.py
cp solution/ex2_wire.py exercises/ex2_wire.py
cp solution/ex3_mapping.py exercises/ex3_mapping.py
uv run pytest
```

- `ex1_gate.py`：check_intent 链体——统一入口（unparseable → DENY）+ given ①② + 定量
  三查（clamp 语义：超限裁到上限/剩余额度继续查，笔数不可裁）+ 收口（clamped 带
  clamp_cents）。
- `ex2_wire.py`：execute 三出口（ALLOW 记账+paid_cents+两条事件 / DENY/PAUSE 写
  gate_reject 交哨兵分码）+ route_after_execute 两分支。
- `ex3_mapping.py`：validate（四列齐 + Java 列非空 + TODO 标记报未填——if/elif 链：
  缺列的行不再读 row[2]）与 count_rows（split_tables 产出的数据行求和）。

**ex3 的另一半答案不在 .py 里**：学员任务是补全 `code/JAVA-MAPPING.md` 的 4 行 TODO——
完整对照版在本目录 `JAVA-MAPPING.md`（golden answer 行尾降级：开放设计不硬造判分，
先自己写再对，差异处才是认知增量）。
