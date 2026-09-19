# 练习 1（单变量编辑约束：只改本文件 TODO 标注的函数体与所需的顶部 import，其余不要动）
"""extract_json：把模型的「花式包裹」剥成 dict。

考察点：正则剥围栏（```json 与 ``` 两种）；首尾大括号兜底（散文夹带也认）；
两种失败（找不到对象 / 语法错误）都翻译成人话 ValueError。

完成判据：uv run pytest exercises/test_ex1.py 全绿——五种形态全过、两种失败各有各的报错。
提示：re.DOTALL 让 . 匹配换行；find/rfind 找首尾大括号；json.JSONDecodeError 要接住转译。
"""

from __future__ import annotations

SAMPLES: list[tuple[str, str]] = [
    ("干净的 JSON", '{"claim_id": "CLM-2026-0001", "verdict": "PASS", "reason": "明细合规"}'),
    ("```json 围栏", '```json\n{"claim_id": "CLM-2026-0002", "verdict": "REJECT:ITEM_OVER_LIMIT"}\n```'),
    ("无语言围栏", '```\n{"claim_id": "CLM-2026-0003", "verdict": "REJECT:INVALID_AMOUNT"}\n```'),
    ("散文夹带", '决策如下：{"claim_id": "CLM-2026-0001", "verdict": "PASS"} 请查收。'),
    ("根本没有 JSON", "我认为这张单据符合规定，可以直接通过。"),
]


def extract_json(text: str) -> dict:
    """三层剥壳：```json 围栏 → 无语言围栏 → 首尾大括号；全失败抛 ValueError。

    围栏内可能还有换行与缩进；散文夹带时 JSON 前后都是人话；语法错误（如键没加引号）
    要接住 JSONDecodeError 并转成 ValueError（信息里带行列号）。
    """
    # TODO(ex1): 先 strip；再用正则剥围栏（两种围栏一个模式搞定）；再 find/rfind 大括号
    # TODO(ex1): json.loads；JSONDecodeError 转 ValueError 后 raise from
    raise NotImplementedError("TODO(ex1): 补全 extract_json")
