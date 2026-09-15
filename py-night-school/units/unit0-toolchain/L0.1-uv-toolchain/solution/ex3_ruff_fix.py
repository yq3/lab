"""参考答案（ex3）——删掉未用的 import 与变量；超长字符串字面量用括号内相邻字面量隐式拼接拆开。

知识点：ruff format 只能重排表达式，永远不会改写字符串内容——
长字符串（以及注释）的拆行只能靠人，这是「格式问题交给工具」的能力边界。
"""


def render_summary(receipt_id: str, items: list[int]) -> str:
    header = f"报销单 {receipt_id}，共 {len(items)} 笔、合计 {sum(items)} 分。"
    detail_prefix = "明细（分为单位）：" + ", ".join(str(c) for c in items)
    detail_suffix = (
        "；本行是一个完整的超长字符串字面量，ruff format 出于语义安全不会自动拆分字符串内容，"
        "因此这处 E501 必须由你亲手用括号内相邻字面量隐式拼接的方式拆行修复"
        "——体会一下「格式化器的能力边界」到底在哪里"
    )
    return header + detail_prefix + detail_suffix
