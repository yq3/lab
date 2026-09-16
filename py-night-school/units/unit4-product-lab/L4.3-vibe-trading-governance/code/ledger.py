"""哈希链审计账本——对版 HKUDS/Vibe-Trading@f84b2977#agent/src/governance/ledger.py。

每条记录嵌入 ``seq``（1 起的位置）与 ``prev_record_hash``（前一条自身的哈希；首条用
:data:`GENESIS_PREV_HASH` 哨兵），再把「位置 + 前哈希 + 载荷」一起摁进自己的
``record_hash``。于是**改/删任何一条历史记录都会断掉其后整条链**——让篡改可检测的是
这个传播性，不是逐行校验和。产品用它给每笔真实下单/被拒/授权/停机事件做
「show me everything the agent did with real money」的合规级记录（live/audit.py 双写
audit.jsonl + audit_chain.jsonl），轮转绝不删历史。

canonical JSON 是哈希链的地基：``sort_keys=True + separators=(",", ":") +
ensure_ascii=True`` 把同一个 dict 永远序列化成同一个字节串——这是 L4.1「相等不等哈希」
坑（dict 顺序不定导致哈希漂移）的正解：**先规范化，再哈希**。

与产品的合理差异（就地声明）：产品 append 在 POSIX ``flock``（Windows 用 ``msvcrt``
字节锁）下持锁做「读尾 + 追加」，且每写 fsync、建文件先 fsync 目录；教学版是**单进程
单写者假设**、不锁不 fsync——本课红线「不用 fcntl/flock（平台中立）」，而防篡改的
语义核心（append 前整链先验、断链拒写 LedgerCorruptionError、verify 三查）与产品一致。
锁只是防两个写者互相踩的 liveness 优化，不是防篡改保证的来源——产品源码原话。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: 首条记录的 prev_record_hash 哨兵——没有前驱可引用（对版产品同名常量）。
GENESIS_PREV_HASH = "sha256:genesis"

#: append 写入的保留键；调用方载荷不得自带（对版产品 _CHAIN_FIELDS）。
_CHAIN_FIELDS = frozenset({"seq", "prev_record_hash", "record_hash"})


class LedgerCorruptionError(RuntimeError):
    """账本已断链时拒绝追加（对版产品同名异常：绝不往被篡改的历史上续建合法后缀）。"""


def canonical_json(obj: Any) -> str:
    """确定性序列化（排序键 + 紧凑分隔 + ASCII 转义）——同 dict 同字节串。"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def compute_record_hash(seq: int, prev_record_hash: str, payload: Mapping[str, Any]) -> str:
    """一条记录的哈希：摁住自己的位置（seq）、前驱（prev）与载荷（payload）。"""
    body = canonical_json({"seq": seq, "prev_record_hash": prev_record_hash, "payload": payload})
    return f"sha256:{hashlib.sha256(body.encode('utf-8')).hexdigest()}"


def _parse_line(line: str) -> dict[str, Any] | None:
    """解析一行 JSONL；任何解析失败返回 None（verify 把它当断点）。"""
    try:
        record = json.loads(line)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


@dataclass(frozen=True)
class ChainBreak:
    """verify 停止信任链的位置与原因（对版产品 ChainBreak）。

    Attributes:
        index: 0 起的行号（断点检测处）。
        seq: 该行声称的 seq；整行解析失败时为 None。
        reason: 断因（unparseable json / seq gap / prev mismatch / hash mismatch）。
    """

    index: int
    seq: int | None
    reason: str


@dataclass(frozen=True)
class ChainVerificationResult:
    """整链验证结果（对版产品 ChainVerificationResult）。

    Attributes:
        ok: 链是否完好。
        record_count: 实际数到的记录数。
        first_break: 首个断点；完好时为 None。
    """

    ok: bool
    record_count: int
    first_break: ChainBreak | None


def _walk(lines: Iterable[str]) -> tuple[ChainVerificationResult, int, str]:
    """走一遍链：seq 连续（1 起）/ prev 衔接 / 哈希重算，停在首个断点。

    返回 (结果, 末条 seq, 末条哈希)——append 用末尾信息算下一条（空链为 0/GENESIS）。
    """
    expected_prev = GENESIS_PREV_HASH
    count = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue  # 容忍文件末尾的空行（编辑器/工具常见），不计入记录
        record = _parse_line(stripped)
        if record is None:
            return (
                ChainVerificationResult(False, count, ChainBreak(index, None, "unparseable json")),
                count,
                expected_prev,
            )
        count += 1
        seq = record.get("seq")
        if not isinstance(seq, int) or seq != count:
            return (ChainVerificationResult(False, count, ChainBreak(index, seq, "seq gap")), count, expected_prev)
        if record.get("prev_record_hash") != expected_prev:
            return (
                ChainVerificationResult(False, count, ChainBreak(index, seq, "prev mismatch")),
                count,
                expected_prev,
            )
        stored_payload = {k: v for k, v in record.items() if k not in _CHAIN_FIELDS}
        recomputed = compute_record_hash(seq, expected_prev, stored_payload)
        if record.get("record_hash") != recomputed:
            return (
                ChainVerificationResult(False, count, ChainBreak(index, seq, "hash mismatch")),
                count,
                expected_prev,
            )
        expected_prev = str(record["record_hash"])
    return (ChainVerificationResult(True, count, None), count, expected_prev)


class HashLedger:
    """教学版哈希链账本（单进程单写者；与产品的差异见模块 docstring）。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def records(self) -> list[dict[str, Any]]:
        """读出全部记录（断链也照读——是否可信以 verify() 为准）。"""
        if not self._path.exists():
            return []
        return [r for r in (_parse_line(line) for line in self._read_lines()) if r is not None]

    def verify(self) -> ChainVerificationResult:
        """端到端验链（对版产品 verify_chain：缺文件视为空链完好）。"""
        return _walk(self._read_lines())[0]

    def append(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """追加一条记录：**先验整条链**，断链抛 :class:`LedgerCorruptionError` 拒写。

        对版产品 append_record 的「refuse-to-extend-a-broken-chain」：O(n) 换最强保证，
        合规账本是低频写（每事件一条，不是每 tick 一条），付得起。
        """
        reserved = _CHAIN_FIELDS & set(payload)
        if reserved:
            raise ValueError(f"payload must not set reserved chain fields: {sorted(reserved)}")
        result, last_seq, last_hash = _walk(self._read_lines())
        if not result.ok:
            break_info = result.first_break
            assert break_info is not None
            raise LedgerCorruptionError(f"chain broken at index {break_info.index}: {break_info.reason}")
        record = dict(payload)
        record["seq"] = last_seq + 1
        record["prev_record_hash"] = last_hash
        record["record_hash"] = compute_record_hash(last_seq + 1, last_hash, payload)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def _read_lines(self) -> list[str]:
        if not self._path.exists():
            return []
        return self._path.read_text(encoding="utf-8").splitlines()
