"""参考答案（ex3）——先完成练习再看。

要点：keyword-only 参数由签名里的 * 把关（调用处按位置传直接 TypeError，无需自己抛）；
**kwargs 透传就是「调用侧 ** 摊开」——多余的键让 TypeError 自然炸出来，别吞。
签名惯例：透传用的 **kwargs 注解 Any（「什么键都可能来」），校验交给对岸的函数签名——
L2.2 会把对岸换成 Pydantic 模型，从根上收严这座桥。
"""

from typing import Any


def format_claim_line(submitter: str, total_cents: int, *, unit: str = "分", bracket: bool = False) -> str:
    if bracket:
        return f"[{submitter}] {total_cents} {unit}"
    return f"{submitter}: {total_cents} {unit}"


def format_from_config(submitter: str, total_cents: int, **options: Any) -> str:
    return format_claim_line(submitter, total_cents, **options)
