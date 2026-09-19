"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

import ex1_tool_schema as ex1


def test_payload_structure() -> None:
    payload = ex1.openai_function("over_limit", "判断是否单笔超限。", ex1.OverArgs)
    assert payload["type"] == "function"
    assert payload["function"]["name"] == "over_limit"
    assert payload["function"]["description"] == "判断是否单笔超限。"
    assert set(payload["function"]) == {"name", "description", "parameters"}


def test_parameters_is_model_schema_with_constraints() -> None:
    payload = ex1.openai_function("over_limit", "判断是否单笔超限。", ex1.OverArgs)
    schema = payload["function"]["parameters"]
    assert schema == ex1.OverArgs.model_json_schema()  # 单一事实源：parameters 就是模型自己的 schema
    items = schema["properties"]["items_cents"]
    assert items["type"] == "array"
    assert items["minItems"] == 1  # min_length=1 的映射
    assert schema["properties"]["limit_cents"]["exclusiveMinimum"] == 0  # gt=0 的映射
    assert sorted(schema["required"]) == ["items_cents", "limit_cents"]  # 无默认值 → 都在 required
