"""工具注册表：Pydantic 模型 → JSON Schema → OpenAI tools 载荷 → 分发执行。

L2.1 我们手写了工具契约（dict）并手工回喂；本课把它升级为「单一事实源」的注册表：
    参数的形状用 Pydantic 模型声明一次 →
    对外：model_json_schema() 生成 tools 载荷（给模型看的契约）
    对内：model_validate_json() 解析模型给的 arguments（字符串套娃坑一步拆封 + 校验）
错误三态（unknown / invalid / tool_error）一律「回喂不抛」——错误信息是给模型的修复指令。
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError


@dataclass(frozen=True)
class ToolSpec:
    """一个工具的全部元数据：名字、描述、参数模型、实现函数。

    frozen=True（L1.3）：注册表是运行期契约，不该被中途改写。
    """

    name: str
    description: str
    args_model: type[BaseModel]
    func: Callable[..., str | int]


def error_result(message: str) -> str:
    """工具级错误的标准形状：JSON 字符串（模型可读、可据此重试）。"""
    return json.dumps({"error": message}, ensure_ascii=False)


def tool(args_model: type[BaseModel]) -> Callable[[Callable[..., str | int]], Callable[..., str | int]]:
    """带参装饰器（L1.5 三层结构）：@tool(PreapproveArgs) 登记函数进全局注册表。

    名字取函数名，描述取 docstring 第一行——「文档即数据」是 Python 生态的普遍约定
    （对照 Java：Javadoc 不进运行时，注解才进）。
    """
    registry: dict[str, ToolSpec] = TOOL_REGISTRY

    def decorator(func: Callable[..., str | int]) -> Callable[..., str | int]:
        doc = (func.__doc__ or "").strip()
        spec = ToolSpec(
            name=func.__name__,
            description=doc.splitlines()[0] if doc else "",
            args_model=args_model,
            func=func,
        )
        registry[spec.name] = spec

        @functools.wraps(func)  # 保住 __name__/__doc__——注册表之外的调用者看到的还是原函数
        def wrapper(*args: object, **kwargs: object) -> str | int:
            return func(*args, **kwargs)

        return wrapper

    return decorator


# 全局注册表：dict[str, ToolSpec]——工具发现就是查这张表（对照 Spring 的 Map<String, Method> 白名单）
TOOL_REGISTRY: dict[str, ToolSpec] = {}


def to_openai_tools(registry: dict[str, ToolSpec] = TOOL_REGISTRY) -> list[dict]:
    """注册表 → OpenAI tools 载荷：每个工具的 parameters 就是 args_model 的 JSON Schema。"""
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.args_model.model_json_schema(),
            },
        }
        for spec in registry.values()
    ]


def run_tool(name: str, arguments_json: str, registry: dict[str, ToolSpec] = TOOL_REGISTRY) -> str:
    """分发执行一个 tool_call：查表 → 解析校验 → 解包调用 → 字符串化。

    三种失败都不抛异常，返回 error JSON（回喂给模型，让它自己修）：
    unknown_tool（模型幻觉出不存在的工具）/ invalid_arguments（JSON 坏或校验不过）/
    tool_error（工具实现自己炸了）。
    """
    spec = registry.get(name)
    if spec is None:
        return error_result(f"unknown_tool: {name}（可用工具：{', '.join(sorted(registry))}）")
    try:
        args = spec.args_model.model_validate_json(arguments_json)  # 解析 + 校验 + 类型收敛一步到位
    except ValidationError as exc:
        first = exc.errors()[0]
        field = first["loc"][0] if first["loc"] else "json"  # JSON 本身坏掉时 loc 为空元组（json_invalid）
        return error_result(
            f"invalid_arguments: {field}: {first['msg']}（input={json.dumps(first['input'], ensure_ascii=False)}）"
        )
    try:
        result = spec.func(**args.model_dump())  # 解包调用：字段名 = 形参名，模型字段就是函数签名
    except Exception as exc:  # noqa: BLE001 —— 工具内部任何异常都转成回喂信息，不炸循环
        return error_result(f"tool_error: {type(exc).__name__}: {exc}")
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
