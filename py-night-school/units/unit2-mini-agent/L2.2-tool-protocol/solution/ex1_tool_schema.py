# 参考答案：ex1_tool_schema（练习文件的完整解法——完成前别看）
"""Pydantic 模型 → JSON Schema → OpenAI 工具载荷。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OverArgs(BaseModel):
    """over_limit 工具的参数形状。"""

    items_cents: list[int] = Field(min_length=1, description="明细金额列表，单位分")
    limit_cents: int = Field(gt=0, description="单笔上限，单位分")


def openai_function(name: str, description: str, args_model: type[BaseModel]) -> dict:
    """把参数模型组装成 OpenAI tools 载荷里的一个工具条目。"""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": args_model.model_json_schema(),
        },
    }
