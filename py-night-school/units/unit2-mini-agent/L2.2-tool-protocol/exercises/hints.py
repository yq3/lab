"""渐进提示（借鉴 Anthropic 官方课的 hints 机制）：先自己想 5 分钟再看，每次只看一级。

第 1 级只给方向，第 2 级给形状（伪代码/签名级，无成行可抄的答案代码），接近完整的做法在最后一级。
用法（在本目录下，uv run 跨平台）：
    uv run python -c "from hints import hint; print(hint('ex1', 1))"
"""

_HINTS: dict[str, list[str]] = {
    "ex1": [
        "字段的完整写法一次写全：类型、约束、描述；payload 的三层嵌套与讲义 demo_schema 的输出"
        "对得上——parameters 的来源就是那个生成 JSON Schema 的模型方法。",
        "形状级：items_cents 需要「至少一个元素」的约束、limit_cents 需要「必须大于 0」的约束——"
        "两个 Field 关键词回讲义 §2.2 的映射表找；openai_function 最里层三个键的名字与值的来源"
        "（两个来自参数，一个来自模型方法调用）。",
        '字段：items_cents: list[int] = Field(min_length=1, description="明细金额列表，单位分")；'
        'limit_cents: int = Field(gt=0, description="单笔上限，单位分")。'
        'openai_function 一行核心：{"type": "function", "function": {"name": name, '
        '"description": description, "parameters": args_model.model_json_schema()}}。',
    ],
    "ex2": [
        "L1.5 的带参装饰器三层结构：外层收 args_model、中层收函数、内层 wrapper 转发调用。"
        "多做的只有一件事：在中层造 ToolSpec 存进 REGISTRY。",
        "形状级三问：名字和描述分别从函数对象的哪两个属性提取（docstring 可能为 None 或有缩进空白，"
        "先怎么处理）？存表用哪个键？wrapper 用哪个装饰器保住原函数身份？",
        '内层骨架：doc = (func.__doc__ or "").strip()；spec = ToolSpec(name=func.__name__, '
        'description=doc.splitlines()[0] if doc else "", args_model=args_model, func=func)；'
        "REGISTRY[spec.name] = spec；@functools.wraps(func) def wrapper(*args, **kwargs): "
        "return func(*args, **kwargs)；return wrapper。",
    ],
    "ex3": [
        "四步顺序：查表 → 解析校验 → 解包调用 → 字符串化。三种失败（unknown_tool / "
        "invalid_arguments / tool_error）各回喂一个 error JSON，不抛异常。",
        "形状级四问：查表用 dict 的哪个方法区分「没有」与「有」？解析校验用 args_model 的哪个类方法"
        "（L1.3 讲过它的执行时机）？调用时 dict 怎么进形参？ValidationError 的 exc.errors()[0] 里 "
        "loc 与 msg 怎么取——loc 可能为空元组，字段名给什么兜底？",
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
