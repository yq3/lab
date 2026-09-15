"""讲义示例测试：**kwargs 适配器——dict 摊开成关键字参数，签名当校验器。"""

import pytest

from tool_bridge import invoke_tool, render_verdict


def test_invoke_with_dict() -> None:
    # L2.2 预演：模型吐的 JSON 解析成 dict，一行摊开成真正的函数调用
    params: dict[str, object] = {"claim_id": "CLM-2026-0002", "verdict": "REJECT:ITEM_OVER_LIMIT"}
    assert invoke_tool(render_verdict, params) == "CLM-2026-0002 -> REJECT:ITEM_OVER_LIMIT（reviewer: auto）"


def test_invoke_with_extra_option() -> None:
    params: dict[str, object] = {
        "claim_id": "CLM-2026-0001",
        "verdict": "PASS",
        "reviewer": "夜校预审",
    }
    assert invoke_tool(render_verdict, params) == "CLM-2026-0001 -> PASS（reviewer: 夜校预审）"


def test_unknown_key_blows_up_at_the_call() -> None:
    # 签名即校验：dict 里多出的键，在 func(**params) 这一行抛 TypeError
    params: dict[str, object] = {"claim_id": "CLM-2026-0001", "verdict": "PASS", "typo_key": 1}
    with pytest.raises(TypeError):
        invoke_tool(render_verdict, params)


def test_missing_required_key_also_blows_up() -> None:
    params: dict[str, object] = {"claim_id": "CLM-2026-0001"}
    with pytest.raises(TypeError):
        invoke_tool(render_verdict, params)


def test_keyword_only_reviewer_cannot_be_positional() -> None:
    with pytest.raises(TypeError):
        render_verdict("CLM-2026-0001", "PASS", "人类审查")  # type: ignore[arg-type]  # 第 3 个位置参数不存在
