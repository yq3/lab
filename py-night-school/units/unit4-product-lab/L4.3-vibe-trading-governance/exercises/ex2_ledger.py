# 练习 2（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""补全哈希链账本：canonical_json 与 GENESIS 已给，你来写 compute_record_hash / append_record / verify_chain。

对版改造题：HKUDS/Vibe-Trading@f84b2977#agent/src/governance/ledger.py（讲义 code/ledger.py
是类封装的完整版，可对照读）。函数式三件套：
  compute_record_hash(seq, prev, payload) —— 把「位置 + 前驱 + 载荷」一起摁进一个哈希；
  verify_chain(path) —— 走整条链，三查（seq 连续 / prev 衔接 / 哈希重算），返回首个断点；
  append_record(path, payload) —— **先验整链再追加**：断链抛 LedgerCorruptionError 拒写。

完成判据：uv run pytest exercises/test_ex2.py 全绿——五个测试：正常追加链成长、
篡改 payload 被定位、删中间条被定位、自修 hash 的篡改仍被下一条抓住、断链后 append 拒写。
TODO 所需的顶部 import：hashlib（json 已预置）。
"""

from __future__ import annotations

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
    """已给：确定性序列化（排序键 + 紧凑分隔）——同 dict 同字节串（L4.1 坑的正解）。"""
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
    """一条记录的哈希，形如 ``sha256:<hex>``。

    TODO(ex2-a)：把哪三样东西装进一个 dict、交给 canonical_json 得到字节串，再对它做
    sha256？返回值的形状（前缀）参考 GENESIS_PREV_HASH 长什么样。
    """
    # TODO(ex2-a): 返回「对什么做哈希」才能让这条记录同时摁住自己的位置、前驱与载荷？
    raise NotImplementedError("TODO(ex2-a): 补全 compute_record_hash")


def verify_chain(path: Path) -> ChainVerificationResult:
    """端到端验链：seq 连续（1 起）/ prev 衔接（首条 = GENESIS）/ 哈希重算一致。

    TODO(ex2-b)：逐行走 _read_lines 的结果，对每条记录数三件事；第一处不一致就带着
    ChainBreak 返回（record_count 数到断点前）；全部走完返回 ok=True。
    空行跳过不计；解析失败的行的断点信息里 seq 该是什么？
    """
    # TODO(ex2-b): 期望的 prev 从 GENESIS_PREV_HASH 开始，每走完一条更新成什么？
    raise NotImplementedError("TODO(ex2-b): 补全 verify_chain")


def append_record(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    """追加一条记录并返回它；断链时抛 LedgerCorruptionError，一个字节不写。

    TODO(ex2-c)：写入之前必须先做什么？下一条的 seq 和 prev_record_hash 从哪来
    （空链时各是什么）？记录本身除了 payload 还要带哪三个保留键？
    """
    # TODO(ex2-c): 组装完整记录（payload + 三个链字段）后，以一行 JSON 追加到文件末尾。
    raise NotImplementedError("TODO(ex2-c): 补全 append_record")
