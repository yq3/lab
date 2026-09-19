"""讲义示例测试：EAFP vs LBYL（等价性 + 竞争模拟）。"""

import pytest

from eafp_demo import CLAIMS, RacyClaims, amount_eafp, amount_get, amount_lbyl, pop_eafp, pop_lbyl


def test_three_styles_agree() -> None:
    assert amount_lbyl(CLAIMS, "CLM-2026-0001") == 1200
    assert amount_eafp(CLAIMS, "CLM-2026-0001") == 1200
    assert amount_get(CLAIMS, "CLM-2026-0001") == 1200
    assert amount_lbyl(CLAIMS, "CLM-9999") is None
    assert amount_eafp(CLAIMS, "CLM-9999") is None
    assert amount_get(CLAIMS, "CLM-9999") is None


def test_race_breaks_lbyl() -> None:
    # 检查与使用之间状态变了：LBYL 的 if 通过了，pop 却扑空
    racy = RacyClaims(CLAIMS)
    with pytest.raises(KeyError):
        pop_lbyl(racy, "CLM-2026-0001")


def test_race_is_harmless_to_eafp() -> None:
    # EAFP 把「检查+使用」合成一个动作（pop 本身），竞争天然无害
    racy = RacyClaims(CLAIMS)
    assert pop_eafp(racy, "CLM-2026-0001") == 1200
    assert pop_eafp(racy, "CLM-2026-0001") is None  # 已被取走：安静地 None
