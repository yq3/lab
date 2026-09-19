"""文件哨兵 kill switch——对版 HKUDS/Vibe-Trading@f84b2977#agent/src/live/halt.py。

产品的 HALT 是「独立于 LLM 合作」的物理制动：一个 out-of-band 哨兵文件，由用户或外部
watchdog 直接 touch——loop 卡死、模型循环、SSE 挂掉都拦不住它生效；执行门在**任何**
下单前检查它。哨兵里那份 JSON 只是归因元数据（tripped_at/by/reason），**文件的存在本身
就是停机**：payload 损坏照样 tripped（fail-closed——「存在性即停机，JSON 只是归因」）。

付款域同构：财务负责人 `touch` 一个 HALT 文件，付款门下一笔立刻全拒。
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_HALT_FILENAME = "HALT"

#: 认可的停机来源（对版产品 _VALID_BY；写进哨兵供审计归因）。
VALID_TRIP_SOURCES = ("cli", "user", "watchdog", "file")


class HaltSentinel:
    """单个付款通道的 kill switch（产品有全局 + 单券商两级；教学版留一级讲清语义）。

    Args:
        directory: 哨兵目录（一般是运行时状态目录）；哨兵即 ``directory/HALT``。
    """

    def __init__(self, directory: Path) -> None:
        self._path = directory / _HALT_FILENAME

    @property
    def path(self) -> Path:
        return self._path

    def trip(self, by: str = "user", reason: str = "") -> None:
        """拉闸：原子写哨兵（tmp + os.replace，对版产品「写永远留不下损坏哨兵」）。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "tripped_at": datetime.now(UTC).isoformat(),
            "by": by if by in VALID_TRIP_SOURCES else "file",
            "reason": reason,
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        os.replace(tmp, self._path)

    def clear(self) -> bool:
        """解除停机（删哨兵）。返回是否真的删了东西。"""
        try:
            self._path.unlink()
            return True
        except FileNotFoundError:
            return False

    def tripped(self) -> bool:
        """是否处于停机状态：**文件存在即 tripped**，内容不看（fail-closed）。"""
        return self._path.exists()

    def read(self) -> dict[str, Any] | None:
        """读哨兵归因元数据；文件不存在或 payload 损坏返回 None。

        注意：read 返回 None ≠ 未停机——tripped() 只看存在性（对版产品 read_halt）。
        """
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None
