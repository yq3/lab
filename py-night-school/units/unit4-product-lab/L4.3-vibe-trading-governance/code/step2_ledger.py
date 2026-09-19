"""Step2：哈希链账本四幕——追加 → 验链 → 篡改 → 断链拒写。

用法：uv run python code/step2_ledger.py
（写进系统临时目录，跑完即弃——账本语义与路径无关。）
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ledger import GENESIS_PREV_HASH, HashLedger, LedgerCorruptionError, compute_record_hash


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="l43-ledger-") as tmp:
        path = Path(tmp) / "audit_chain.jsonl"
        ledger = HashLedger(path)

        print("== Step2 哈希链账本：追加 → 验链 → 篡改 → 断链拒写 ==")
        print(f"genesis prev = {GENESIS_PREV_HASH}（首条没有前驱，用哨兵）\n")

        print("[幕1 追加三条付款事件]")
        for payload in [
            {"event": "verdict", "decision": "DENY", "reason": "breach: excluded_vendors"},
            {"event": "verdict", "decision": "PAUSE_FOR_REAUTH", "reason": "breach: max_single_payment_cents"},
            {"event": "payment", "ref_id": "pay-demo001", "amount_cents": 90_000},
        ]:
            record = ledger.append(payload)
            print(f"  seq={record['seq']} prev={record['prev_record_hash'][:20]}… hash={record['record_hash'][:20]}…")
        print("  每条都摁住了自己的位置(seq) + 前一条的哈希 + 载荷\n")

        print("[幕2 验链：完好]")
        result = ledger.verify()
        print(f"  ok={result.ok} record_count={result.record_count} first_break={result.first_break}\n")

        print("[幕3 篡改第 2 条的载荷（decision 改成 ALLOW）]")
        lines = path.read_text(encoding="utf-8").splitlines()
        import json

        tampered = json.loads(lines[1])
        tampered["decision"] = "ALLOW"  # 审计记录被「事后洗白」
        lines[1] = json.dumps(tampered, ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = ledger.verify()
        br = result.first_break
        assert br is not None
        print(f"  ok={result.ok} 断点=index {br.index} (seq={br.seq}) reason='{br.reason}'")
        print("  -> 改载荷不改哈希：本条自身哈希对不上，当场被抓\n")

        print("[幕3b 高手版：把第 2 条的哈希也一起修好]")
        tampered2 = json.loads(lines[1])
        payload = {k: v for k, v in tampered2.items() if k not in ("seq", "prev_record_hash", "record_hash")}
        tampered2["record_hash"] = compute_record_hash(tampered2["seq"], tampered2["prev_record_hash"], payload)
        lines[1] = json.dumps(tampered2, ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = ledger.verify()
        br = result.first_break
        assert br is not None
        print(f"  ok={result.ok} 断点=index {br.index} (seq={br.seq}) reason='{br.reason}'")
        print("  -> 本条洗白了，但第 3 条还攥着旧哈希——prev mismatch，传播性让下一条出卖它\n")

        print("[幕4 断链拒写]")
        try:
            ledger.append({"event": "verdict", "decision": "ALLOW", "reason": "later record"})
        except LedgerCorruptionError as exc:
            print(f"  LedgerCorruptionError: {exc}")
        print("  -> 绝不往被篡改的历史上续建合法后缀；先人工对账，再谈追加")


if __name__ == "__main__":
    main()
