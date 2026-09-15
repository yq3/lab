"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状，接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        '字段的完整写法是 名字: 类型 = Field(约束..., description="...")；'
        "payload 的 parameters 直接放 args_model.model_json_schema() 的返回值。",
        '字段形状：items_cents: list[int] = Field(min_length=1, description="明细金额列表，单位分")；'
        'limit_cents: int = Field(gt=0, description="单笔上限，单位分")。'
        "openai_function 返回三层 dict，最里层三个键：name / description / parameters。",
        'openai_function 一行核心：{"type": "function", "function": {"name": name, '
        '"description": description, "parameters": args_model.model_json_schema()}}。',
    ],
    "ex2": [
        "对照 L1.5 的带参装饰器：外层函数收 args_model，返回 decorator；decorator 收 func，"
        "造 ToolSpec 存入 REGISTRY，返回 wrapper。",
        'docstring 处理：doc = (func.__doc__ or "").strip()；描述 = doc.splitlines()[0] if doc else ""。'
        "wrapper 用 functools.wraps(func) 装饰后直接 return func(*args, **kwargs)。",
        "内层骨架：spec = ToolSpec(name=func.__name__, description=..., args_model=args_model, func=func)；"
        "REGISTRY[spec.name] = spec；@functools.wraps(func) def wrapper(*args, **kwargs): "
        "return func(*args, **kwargs)；return wrapper。",
    ],
    "ex3": [
        "四步顺序：registry.get 查表 → try model_validate_json → try func(**args.model_dump()) → "
        "str 原样返回 / 否则 json.dumps(result, ensure_ascii=False)。",
        "三处 except 各回喂一个 error_result：unknown_tool 前缀 + 可用工具列表；"
        'invalid_arguments 前缀 + 首个错误的字段与 msg（loc 空元组时字段名记 "json"）；'
        "tool_error 前缀 + type(exc).__name__ 与异常信息。"
        "ValidationError 从 pydantic import；JSON 坏掉它也抛 ValidationError。",
        "完整骨架：spec = registry.get(name)；if spec is None: return error_result(...)；"
        "try: args = spec.args_model.model_validate_json(arguments_json)；"
        'except ValidationError as exc: first = exc.errors()[0]; field = first["loc"][0] '
        'if first["loc"] else "json"; return error_result(f"invalid_arguments: {field}: {first[\'msg\']}")；'
        "try: result = spec.func(**args.model_dump())；except Exception as exc: "
        'return error_result(f"tool_error: {type(exc).__name__}: {exc}")；'
        "return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)。",
    ],
}


def hint(exercise: str, level: int = 1) -> str:
    """返回某练习第 level 级提示；超过上限返回最后一级。"""
    levels = _HINTS[exercise]
    return levels[min(level, len(levels)) - 1]
