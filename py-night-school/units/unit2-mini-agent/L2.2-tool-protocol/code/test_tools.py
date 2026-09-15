"""讲义代码验收（发货态必须全绿；练习区的红在 exercises/）。"""

from __future__ import annotations

import json

import finance  # noqa: F401 —— import 即注册（装饰器副作用）
from finance import GetClaimArgs, PreapproveArgs
from tools import TOOL_REGISTRY, run_tool, to_openai_tools


def test_registry_contains_finance_tools() -> None:
    assert set(TOOL_REGISTRY) == {"preapprove", "get_claim"}
    assert TOOL_REGISTRY["preapprove"].description.startswith("对报销单明细金额做规则预审")  # docstring 第一行


def test_openai_payload_parameters_is_model_schema() -> None:
    payload = to_openai_tools()
    by_name = {item["function"]["name"]: item["function"] for item in payload}
    assert set(by_name) == {"preapprove", "get_claim"}
    assert by_name["get_claim"]["parameters"] == GetClaimArgs.model_json_schema()  # 单一事实源：schema 即模型
    assert by_name["preapprove"]["parameters"] == PreapproveArgs.model_json_schema()


def test_schema_required_and_pattern_advertised() -> None:
    schema = GetClaimArgs.model_json_schema()
    assert schema["required"] == ["claim_id"]  # 无默认值 → required；给了默认值会从这里消失（讲义 §2.2）
    assert schema["properties"]["claim_id"]["pattern"] == r"^CLM-\d{4}-\d{4}$"


def test_run_tool_happy_paths() -> None:
    assert run_tool("preapprove", '{"items_cents": [1200, 3500, 2400]}') == "PASS"
    claim = json.loads(run_tool("get_claim", '{"claim_id": "CLM-2026-0002"}'))
    assert claim["items_cents"] == [8800]
    assert claim["purpose"].startswith("项目验收宴请")


def test_run_tool_validation_vs_business_layering() -> None:
    # 负数能通过 schema（形状合法），被业务规则拒绝——校验分层的关键一测
    assert run_tool("preapprove", '{"items_cents": [-500]}') == "REJECT:INVALID_AMOUNT"
    # 空列表在 schema 层就被拦下（min_length=1）——错误回喂，不抛异常
    error = json.loads(run_tool("preapprove", '{"items_cents": []}'))
    assert error["error"].startswith("invalid_arguments")


def test_run_tool_error_results_are_feedable_json() -> None:
    unknown = json.loads(run_tool("no_such_tool", "{}"))
    assert unknown["error"].startswith("unknown_tool")
    assert "preapprove" in unknown["error"]  # 错误里带可用工具清单——给模型的修复提示

    bad_pattern = json.loads(run_tool("get_claim", '{"claim_id": "CLM-99"}'))
    assert bad_pattern["error"].startswith("invalid_arguments")
    assert "claim_id" in bad_pattern["error"]

    not_json = json.loads(run_tool("preapprove", "不是 JSON"))
    assert not_json["error"].startswith("invalid_arguments")

    not_found = json.loads(run_tool("get_claim", '{"claim_id": "CLM-2026-9999"}'))
    assert not_found["error"] == "claim_not_found: CLM-2026-9999"  # 工具内部返回的 error JSON 原样回喂
