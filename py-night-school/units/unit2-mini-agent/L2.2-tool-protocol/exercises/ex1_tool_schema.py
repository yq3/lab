# 练习 1（单变量编辑约束：只改本文件 TODO 标注的区域，其余不要动）
"""Pydantic 模型 → JSON Schema → OpenAI 工具载荷。

考察点：参数模型怎么声明（字段 + 约束 + 描述一次性写全）；
model_json_schema() 的产物长什么样（properties / required / 约束映射）；
tools 载荷的三层嵌套结构（type/function/{name,description,parameters}）。

完成判据：uv run pytest exercises/test_ex1.py 全绿——
  载荷结构逐键断言；两个约束（min_length、gt）在 schema 里各就各位；required 齐全。
提示：先跑 uv run python code/demo_schema.py 看一眼实物再动手。
"""

from __future__ import annotations

from pydantic import BaseModel


class OverArgs(BaseModel):
    """over_limit 工具的参数形状。"""

    # TODO(ex1): 声明两个字段——
    #   items_cents: list[int]，约束「至少 1 个元素」，描述「明细金额列表，单位分」
    #   limit_cents: int，约束「必须大于 0」，描述「单笔上限，单位分」


def openai_function(name: str, description: str, args_model: type[BaseModel]) -> dict:
    """把参数模型组装成 OpenAI tools 载荷里的一个工具条目。

    形状：{"type": "function", "function": {"name": ..., "description": ...,
           "parameters": <args_model 的 JSON Schema>}}
    """
    # TODO(ex1): 组装并返回这个三层嵌套 dict
    raise NotImplementedError("TODO(ex1): 补全 openai_function")
