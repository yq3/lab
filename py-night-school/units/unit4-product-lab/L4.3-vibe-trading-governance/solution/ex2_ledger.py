# 参考答案：ex2_ledger（练习文件的完整解法——完成前别看）
"""补全哈希链账本：compute_record_hash / verify_chain / append_record 见 TODO 原位。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: 首条记录的 prev_record_hash 哨兵——没有前驱可引用（对版产品同名常量）。
GENESIS_PREV_HASH = "sha256:genesis"

#: append 写入的保留键；调用方载荷不得自带。
CHAIN_FIELDS = frozenset({"seq", "prev_record_hash", "record_hash"})


class LedgerCorruptionError(RuntimeError):
    """账本已断链时拒绝追加（对版产品同名异常）。"""


@dataclass(frozen=True)
class ChainBreak:
    """verify_chain 停止信任链的位置与原因。"""

    index: int  # 0 起行号
    seq: int | None  # 该行声称的 seq；整行解析失败为 None
    reason: str  # unparseable json / seq gap / prev mismatch / hash mismatch


@dataclass(frozen=True)
class ChainVerificationResult:
    """整链验证结果。"""

    ok: bool
    record_count: int
    first_break: ChainBreak | None


def canonical_json(obj: Any) -> str:
    """已给：确定性序列化（排序键 + 紧凑分隔）——同 dict 同字节串（L4.1 陷阱的正解）。"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _read_lines(path: Path) -> list[str]:
    """已给：读出账本全部行（文件不存在返回空表；行内空白不 trim，解析交给 _parse_line）。"""
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def _parse_line(line: str) -> dict[str, Any] | None:
    """已给：解析一行 JSONL；任何失败返回 None（verify_chain 把它当断点）。"""
    try:
        record = json.loads(line)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def compute_record_hash(seq: int, prev_record_hash: str, payload: Mapping[str, Any]) -> str:
    """一条记录的哈希：摁住位置 + 前驱 + 载荷，canonical 后 sha256。"""
    body = canonical_json({"seq": seq, "prev_record_hash": prev_record_hash, "payload": payload})
    return f"sha256:{hashlib.sha256(body.encode('utf-8')).hexdigest()}"


def verify_chain(path: Path) -> ChainVerificationResult:
    """端到端验链：seq 连续（1 起）/ prev 衔接（首条 = GENESIS）/ 哈希重算一致。"""
    expected_prev = GENESIS_PREV_HASH
    count = 0
    for index, line in enumerate(_read_lines(path)):
        if not line.strip():
            continue  # 容忍末尾空行，不计入记录
        record = _parse_line(line)
        if record is None:
            return ChainVerificationResult(False, count, ChainBreak(index, None, "unparseable json"))
        count += 1
        seq = record.get("seq")
        if not isinstance(seq, int) or seq != count:
            return ChainVerificationResult(
                False, count, ChainBreak(index, seq if isinstance(seq, int) else None, "seq gap")
            )
        if record.get("prev_record_hash") != expected_prev:
            return ChainVerificationResult(False, count, ChainBreak(index, seq, "prev mismatch"))
        stored_payload = {k: v for k, v in record.items() if k not in CHAIN_FIELDS}
        if record.get("record_hash") != compute_record_hash(seq, expected_prev, stored_payload):
            return ChainVerificationResult(False, count, ChainBreak(index, seq, "hash mismatch"))
        expected_prev = str(record["record_hash"])
    return ChainVerificationResult(True, count, None)


def append_record(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    """追加一条记录并返回它；断链时抛 LedgerCorruptionError，一个字节不写。"""
    result = verify_chain(path)
    if not result.ok:
        assert result.first_break is not None
        raise LedgerCorruptionError(f"chain broken at index {result.first_break.index}: {result.first_break.reason}")
    record = dict(payload)
    record["seq"] = result.record_count + 1
    record["prev_record_hash"] = GENESIS_PREV_HASH if result.record_count == 0 else _tail_hash(path)
    record["record_hash"] = compute_record_hash(record["seq"], record["prev_record_hash"], payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def _tail_hash(path: Path) -> str:
    """末条记录的哈希（追加时算 prev 用；调用方保证链非空且完好）。"""
    lines = [ln for ln in _read_lines(path) if ln.strip()]
    record = _parse_line(lines[-1])
    assert record is not None
    return str(record["record_hash"])
