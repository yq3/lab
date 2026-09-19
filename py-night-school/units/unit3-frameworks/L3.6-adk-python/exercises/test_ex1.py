"""练习 1 验收（不要改本文件——它就是你的判卷老师）。"""

import inspect

import ex1_tool as ex1


def test_lookup_policy_hits_known_key() -> None:
    assert ex1.lookup_policy("item_limit") == ex1.POLICIES["item_limit"]
    assert ex1.lookup_policy("invoice_rule") == ex1.POLICIES["invoice_rule"]


def test_lookup_policy_feeds_error_for_unknown_key() -> None:
    result = ex1.lookup_policy("no_such_key")  # 不 raise——错误回喂给模型
    assert "policy_not_found" in result
    assert "no_such_key" in result


def test_declaration_comes_from_docstring_and_signature() -> None:
    """meta：schema 不是配置出来的，是从函数身上长出来的（三个信息源逐一验证）。"""
    from google.adk.tools import FunctionTool

    decl = FunctionTool(func=ex1.lookup_policy)._get_declaration()
    assert decl is not None
    assert decl.name == "lookup_policy"  # 名字 ← 函数名
    # 描述 ← docstring（框架用 inspect.getdoc 的清洗口径：去缩进、去首尾空白）
    assert decl.description == inspect.getdoc(ex1.lookup_policy)
    assert decl.description and "政策" in decl.description  # 且是写给模型看的广告词
    schema = decl.parameters_json_schema  # 参数 ← 签名
    assert schema is not None
    assert schema["properties"]["policy_key"]["type"] == "string"
    assert schema["required"] == ["policy_key"]  # 无默认值 → required
