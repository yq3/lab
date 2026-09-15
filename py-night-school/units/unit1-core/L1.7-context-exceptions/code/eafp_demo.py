"""EAFP vs LBYL——两种取数哲学的完整对照，外加一个「检查与使用之间状态变了」的模拟。

运行本文件：
    uv run python code/eafp_demo.py
"""

CLAIMS: dict[str, int] = {"CLM-2026-0001": 1200, "CLM-2026-0002": 8800}


def amount_lbyl(claims: dict[str, int], claim_id: str) -> int | None:
    """Look Before You Leap：先检查再用（Java 人的本能写法）。"""
    if claim_id in claims:  # 检查
        return claims[claim_id]  # 使用
    return None


def amount_eafp(claims: dict[str, int], claim_id: str) -> int | None:
    """Easier to Ask Forgiveness than Permission：直接用，出事再兜住。"""
    try:
        return claims[claim_id]  # 直接用
    except KeyError:  # 出事再兜
        return None


def amount_get(claims: dict[str, int], claim_id: str) -> int | None:
    """dict.get：EAFP 的常用语法糖（存在性检查内建了）。"""
    return claims.get(claim_id)


class RacyClaims(dict[str, int]):
    """模拟并发竞争：每次「检查存在性」，数据就被另一个执行流抢走一份。

    现实对应：LBYL 的 if key in d 与 d[key] 之间，另一个线程/协程把 key 删了。
    （L1.9 讲 asyncio 时会回来：检查与使用之间「让出」了执行权。）
    """

    def __contains__(self, key: object) -> bool:
        was_there = super().__contains__(key)
        if was_there and isinstance(key, str):
            self.pop(key, None)  # 另一个「线程」先到，把单据取走了
        return was_there


def pop_lbyl(claims: dict[str, int], claim_id: str) -> int | None:
    """LBYL 版取走：检查时还在、使用时没了 -> KeyError 直接炸出去。"""
    if claim_id in claims:
        return claims.pop(claim_id)
    return None


def pop_eafp(claims: dict[str, int], claim_id: str) -> int | None:
    """EAFP 版取走：检查与使用是同一个原子动作（pop 本身），竞争天然无害。"""
    try:
        return claims.pop(claim_id)
    except KeyError:
        return None


if __name__ == "__main__":
    print(amount_lbyl(CLAIMS, "CLM-2026-0001"))  # 1200——三种写法结果一致
    print(amount_eafp(CLAIMS, "CLM-2026-0002"), amount_get(CLAIMS, "CLM-2026-0002"))
    print(amount_lbyl(CLAIMS, "CLM-9999"))  # None——单号不存在

    # 竞争模拟：LBYL 在检查与使用之间被「抢」
    racy = RacyClaims(CLAIMS)
    print(pop_eafp(racy, "CLM-2026-0001"))  # 1200：EAFP 一次到位，安全
    try:
        pop_lbyl(racy, "CLM-2026-0002")  # 检查时在、pop 时没了
    except KeyError as exc:
        print(f"LBYL 炸了: KeyError: {exc}")  # 检查与使用之间状态变了——L1.9 并发的前菜
