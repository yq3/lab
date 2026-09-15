# 练习 3（单变量编辑约束：只改本文件；验收 = uv run ruff check exercises/ex3_ruff_fix.py 通过）
"""修复 3 处 ruff 违规——夜校第一次「lint 当老师」。

本文件语法正确、类型正确，但 ruff 会报 3 处问题：
  1. 未使用的 import（F401）
  2. 未使用的变量（F841）
  3. 一行超过 120 列（E501）——注意这行是「单字符串字面量」，
     ruff format 出于语义安全不会自动拆分字符串内容，所以必须由你手工拆行。
先跑 uv run ruff check exercises/ex3_ruff_fix.py 看报什么，再逐一修复。
"""

import json


def render_summary(receipt_id: str, items: list[int]) -> str:
    backup = "我不会被用到"  # F841：赋值后从未使用
    header = f"报销单 {receipt_id}，共 {len(items)} 笔、合计 {sum(items)} 分。"
    detail_prefix = "明细（分为单位）：" + ", ".join(str(c) for c in items)
    detail_suffix = "；本行是一个完整的超长字符串字面量，ruff format 出于语义安全不会自动拆分字符串内容，因此这处 E501 必须由你亲手用括号内相邻字面量隐式拼接的方式拆行修复——体会一下「格式化器的能力边界」到底在哪里"
    return header + detail_prefix + detail_suffix
