"""练习 2 验收（不要改本文件——它就是你的判卷老师）。

篡改三连对版产品 test_governance 的三个 tamper 测试：
编辑定位 / 删中间定位 / 自修 hash 仍被抓（对版 test_tamper_that_also_fixes_its_own_hash）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ex2_ledger as ex2
from ex2_ledger import GENESIS_PREV_HASH, LedgerCorruptionError, append_record, compute_record_hash, verify_chain


def seed(path: Path) -> None:
    """造一条三条记录的好链。"""
    for amount in (100, 200, 300):
        append_record(path, {"event": "payment", "amount_cents": amount})


def rewrite(path: Path, index: int, record: dict) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[index] = json.dumps(record, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_record(path: Path, index: int) -> dict:
    return json.loads(path.read_text(encoding="utf-8").splitlines()[index])


def test_append_grows_chain_and_links_genesis(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    first = append_record(path, {"event": "payment", "amount_cents": 100})
    second = append_record(path, {"event": "payment", "amount_cents": 200})
    third = append_record(path, {"event": "payment", "amount_cents": 300})
    assert (first["seq"], first["prev_record_hash"]) == (1, GENESIS_PREV_HASH)
    assert second["prev_record_hash"] == first["record_hash"]  # 咬住前一条
    assert third["prev_record_hash"] == second["record_hash"]
    result = verify_chain(path)
    assert result.ok and result.record_count == 3 and result.first_break is None


def test_tamper_editing_payload_is_pinpointed(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    seed(path)
    record = read_record(path, 1)
    record["amount_cents"] = 1  # 审计记录被事后改小
    rewrite(path, 1, record)
    result = verify_chain(path)
    assert not result.ok
    assert result.first_break is not None
    assert (result.first_break.index, result.first_break.reason) == (1, "hash mismatch")


def test_tamper_deleting_middle_record_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    seed(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[1]  # 删中间条
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = verify_chain(path)
    assert not result.ok
    assert result.first_break is not None
    assert result.first_break.reason in ("seq gap", "prev mismatch")


def test_tamper_that_fixes_its_own_hash_is_caught_downstream(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    seed(path)
    record = read_record(path, 1)
    record["amount_cents"] = 1
    payload = {k: v for k, v in record.items() if k not in ex2.CHAIN_FIELDS}
    record["record_hash"] = compute_record_hash(record["seq"], record["prev_record_hash"], payload)
    rewrite(path, 1, record)  # 本条的哈希也一起修好
    result = verify_chain(path)
    assert not result.ok
    assert result.first_break is not None
    assert (result.first_break.index, result.first_break.reason) == (2, "prev mismatch")  # 下一条出卖它


def test_append_refuses_to_extend_broken_chain(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    seed(path)
    record = read_record(path, 0)
    record["amount_cents"] = 999  # 断链
    rewrite(path, 0, record)
    before = len(path.read_text(encoding="utf-8").splitlines())
    with pytest.raises(LedgerCorruptionError):
        append_record(path, {"event": "payment", "amount_cents": 400})
    after = len(path.read_text(encoding="utf-8").splitlines())
    assert before == after  # 拒写：一个字节没多
