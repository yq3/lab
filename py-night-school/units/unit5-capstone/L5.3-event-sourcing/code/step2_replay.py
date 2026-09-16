"""Step2 事件重放：fold 把事件序列归约成当前视图——「事件表是唯一真相源，状态是投影」。

跑一单 0002（dirty_once，带重规划环）落库，然后丢掉最终 state，只凭事件表把
results / advice / plan_rejections / cost 全部重放出来，与图跑出来的终态逐项对照。
fold 是纯函数（不取时钟、不碰网络、只吃事件列表）——同一串事件永远同一个视图。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import demo
import eventstore

CLAIM = "CLM-2026-0002"  # 重规划单：一轮脏计划→拒绝回喂→二轮过门→正常送审


def main() -> None:
    print("== Step2 事件重放：状态是投影（fold 现场版） ==")
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "audit.db"
        result = asyncio.run(demo.run_audited(CLAIM, db, mode="dirty_once", clock=lambda: demo.DEMO_CLOCK))
        final, run_key = result["final"], result["run_key"]
        print(f"[跑图] {CLAIM}（dirty_once）→ run_key {run_key}，终态 state 拿在手里；现在把它丢掉\n")

        with eventstore.connect(db) as store:
            rows = store.events_for(run_key)
            print("[事件表] 唯一真相源（type/seq）：")
            for row in rows:
                print(f"    seq {row['seq']:>2}  {row['type']:<14} {str(row['payload'])[:58]}")

            print("\n[fold] 只凭事件归约出的当前视图：")
            view = eventstore.replay(store, run_key)
            print(f"    results 键        : {sorted(view['results'])}")
            print(f"    advice            : {view['advice'].model_dump_json()}")
            print(f"    plan_rejections   : {[r['reason_code'] for r in view['plan_rejections']]}")
            print(f"    sent              : {view['sent']}")
            print(f"    cost              : {view['cost']}（三次真实调用的累计——重放免费，花钱的都记了账）")
            print(f"    graph_version     : {view['graph_version'][:16]}…（run.started 里带的出生证明）")

        print("\n[对照] 图的终态 vs 事件重放的投影：")
        pairs = [
            ("advice 全等", view["advice"] == final["advice"]),
            ("results 全等", view["results"] == final["results"]),
            ("sent 全等", view["sent"] == final["sent"]),
            (
                "拒绝轨迹全等",
                [r["reason_code"] for r in view["plan_rejections"]]
                == [r.reason_code for r in final["plan_rejections"]],
            ),
        ]
        for name, equal in pairs:
            print(f"    {name:<10}: {equal}")
        print("  <- state 会随 run 生死，事件表 append-only 地活着：任何时刻想问「当时到底发生了什么」，")
        print("     答案不是翻 state，是重放事件——这就是事件溯源（A11）的全部立场。")
        print(f"（审计库在系统临时目录 {db.parent.name}/ 下，演示结束自动销毁）")


if __name__ == "__main__":
    main()
