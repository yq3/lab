# 练习 3（单变量编辑约束：只改 TODO 标注的两个函数体，其余不要动）
"""keyword-only 参数的报表函数 + **kwargs 透传。

判据（test_ex3.py 逐条验收，含「调用形态断言」）：
  1. format_claim_line 的 unit / bracket 只能关键字传——按位置传必须 TypeError；
  2. format_from_config 把收到的 **options 原样摊开转发给 format_claim_line；
  3. 不认识的 option 名会顺着 ** 摊开在调用处炸 TypeError（不许偷偷吞掉）。
完成后：uv run pytest exercises/test_ex3.py 全绿。
"""

from typing import Any


def format_claim_line(submitter: str, total_cents: int, *, unit: str = "分", bracket: bool = False) -> str:
    """TODO(ex3a): 渲染报销单摘要行。

    格式：bracket=False 时 "{submitter}: {total_cents} {unit}"；
    bracket=True 时 "[{submitter}] {total_cents} {unit}"。
    注意：签名已给全（含 * 号），不要改签名——你只写函数体。
    """
    raise NotImplementedError("TODO(ex3a): 按 docstring 格式渲染并返回")


def format_from_config(submitter: str, total_cents: int, **options: Any) -> str:
    """TODO(ex3b): **kwargs 透传——把 options 原样摊开转发给 format_claim_line。

    场景：配置来自 dict（如 {"unit": "元", "bracket": True}），经 ** 摊开成关键字参数。
    """
    raise NotImplementedError("TODO(ex3b): 一行 return，用 ** 摊开转发")
