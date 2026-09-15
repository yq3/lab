"""**kwargs 适配器：把 dict 展开成关键字参数——LLM function calling 的桥。

场景（L2.2 的预演）：模型选了工具后，吐给你的是一段 JSON——在 Python 里解析出来就是 dict。
从「一个 dict」到「调用真正的 Python 函数」，桥就一行：func(**params)。

定义侧与调用侧的 ** 是两个不同的东西（讲义 §2.2 图解）：
  定义侧 def f(**options)   ：把调用时的多余关键字参数「收拢」成一个 dict；
  调用侧 f(**params)        ：把一个 dict「摊开」成关键字参数。
一收一摊，正好互逆。
"""

from collections.abc import Callable


def render_verdict(claim_id: str, verdict: str, *, reviewer: str = "auto") -> str:
    """渲染审查结论。`*` 之后的 reviewer 是 keyword-only 参数：只能 reviewer=... 传，不能按位置传。

    框架 API 大量使用这个语法保护「易混位置参数」——调用方必须写出参数名，签名演进不再破坏调用点。
    """
    return f"{claim_id} -> {verdict}（reviewer: {reviewer}）"


def invoke_tool(func: Callable[..., str], params: dict[str, object]) -> str:
    """dict -> 关键字参数 的桥：func(**params) 把 dict 摊开成 func(k1=v1, k2=v2, ...)。

    参数校验全靠函数签名自己：多余 / 缺失的键都会在调用这一行抛 TypeError——
    L2.2 我们会给它套上 Pydantic，把 TypeError 升级成带字段路径的 ValidationError。
    """
    return func(**params)
