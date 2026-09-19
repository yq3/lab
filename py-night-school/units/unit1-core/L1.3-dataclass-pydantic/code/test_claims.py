"""讲义示例测试：Pydantic 构造即验证、嵌套、序列化三件套、替代构造。"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from claims import ClaimBatch, ExpenseClaim


def test_valid_claim_constructs() -> None:
    claim = ExpenseClaim(
        claim_id="CLM-2026-0001",
        items_cents=[1200, 3500],
        submitter="王工",
    )
    assert claim.claim_id == "CLM-2026-0001"
    assert claim.submitted_at is None  # 可选字段默认 None（对照 Java 的 Optional.empty）


def test_iso_string_coerced_to_datetime() -> None:
    # 类型收敛：喂 ISO 字符串，拿到的是 datetime 对象——Jackson 的反序列化在构造时顺带完成
    # （动态数据来自 dict / JSON，所以走 model_validate / model_validate_json 这两个入口）
    claim = ExpenseClaim.model_validate(
        {
            "claim_id": "CLM-2026-0001",
            "items_cents": [100],
            "submitter": "王工",
            "submitted_at": "2026-09-14T20:00:00",
        }
    )
    assert isinstance(claim.submitted_at, datetime)
    assert claim.submitted_at.year == 2026


@pytest.mark.parametrize(
    "payload,loc,type_hint",
    [
        ({"claim_id": "bad", "items_cents": [1], "submitter": "王工"}, "claim_id", "string_pattern_mismatch"),
        ({"claim_id": "CLM-2026-0001", "items_cents": [100, -5], "submitter": "王工"}, "items_cents", "greater_than"),
        ({"claim_id": "CLM-2026-0001", "items_cents": ["x"], "submitter": "王工"}, "items_cents", "int_parsing"),
        ({"claim_id": "CLM-2026-0001", "items_cents": [100], "submitter": ""}, "submitter", "string_too_short"),
    ],
)
def test_invalid_claims_rejected_at_construction(
    payload: dict[str, object], loc: tuple[str, ...] | str, type_hint: str
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        ExpenseClaim.model_validate(payload)
    errors = excinfo.value.errors()
    assert errors[0]["loc"][0] == loc  # loc：出事字段的路径（嵌套时是多级路径，见 test_nested）
    assert errors[0]["type"] == type_hint  # type：机器可判的错误类别，程序里按它分流处理


def test_nested_validation_error_carries_path() -> None:
    batch = {
        "batch_id": "BATCH-2026-09",
        "claims": [
            {"claim_id": "CLM-2026-0001", "items_cents": [100], "submitter": "王工"},
            {"claim_id": "bad-id", "items_cents": [100], "submitter": "李工"},
        ],
    }
    with pytest.raises(ValidationError) as excinfo:
        ClaimBatch.model_validate(batch)
    (error,) = excinfo.value.errors()
    assert error["loc"] == ("claims", 1, "claim_id")  # 路径直达第二张单的单号字段


def test_valid_batch_constructs_nested_models() -> None:
    batch = ClaimBatch.model_validate(
        {
            "batch_id": "BATCH-2026-09",
            "claims": [
                {"claim_id": "CLM-2026-0001", "items_cents": [1200], "submitter": "王工"},
                {"claim_id": "CLM-2026-0002", "items_cents": [8800], "submitter": "李工"},
            ],
        }
    )
    # 嵌套元素是真正的 ExpenseClaim 实例（不是 dict）——属性访问全程有类型
    assert isinstance(batch.claims[1], ExpenseClaim)
    assert batch.claims[1].submitter == "李工"


def test_from_cents_string_alternative_constructor() -> None:
    claim = ExpenseClaim.from_cents_string("CLM-2026-0001", "王工", "1200, 3500,2400")
    assert claim.items_cents == [1200, 3500, 2400]
    # 替代构造同样吃满校验：负数交给 gt=0 拒收
    with pytest.raises(ValidationError):
        ExpenseClaim.from_cents_string("CLM-2026-0001", "王工", "1200,-5")


def test_dump_and_roundtrip() -> None:
    claim = ExpenseClaim(
        claim_id="CLM-2026-0001",
        items_cents=[1200, 3500],
        submitter="王工",
        submitted_at=datetime(2026, 9, 14, 20, 0),
    )
    # model_dump() -> dict（≈ Jackson writeValueAsMap 的直觉，但拿到的是普通 Python dict）
    assert claim.model_dump() == {
        "claim_id": "CLM-2026-0001",
        "items_cents": [1200, 3500],
        "submitter": "王工",
        "submitted_at": datetime(2026, 9, 14, 20, 0),
    }
    # model_dump_json() -> JSON 字符串（datetime 自动转 ISO 格式）
    assert '"submitted_at":"2026-09-14T20:00:00"' in claim.model_dump_json()
    # 吃回：dict 用 model_validate()，JSON 字符串用 model_validate_json()——往返不丢信息
    assert ExpenseClaim.model_validate(claim.model_dump()) == claim
    assert ExpenseClaim.model_validate_json(claim.model_dump_json()) == claim


def test_default_list_is_per_instance() -> None:
    # Pydantic v2 对可变默认值做了「每实例拷贝」保护（dataclass 则是直接禁止裸默认值，§5 对照）
    a = ClaimBatch(batch_id="BATCH-2026-09")
    b = ClaimBatch(batch_id="BATCH-2026-10")
    assert a.claims == []
    assert a.claims is not b.claims
