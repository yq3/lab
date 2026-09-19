"""讲义示例测试：with 协议（commit/rollback/异常传播/吞异常）。"""

import pytest

from approval_session import ApprovalSession, SwallowingSession


def test_normal_path_commits() -> None:
    log: list[str] = []
    with ApprovalSession("CLM-1", log):
        pass
    assert log == ["BEGIN CLM-1", "COMMIT CLM-1"]


def test_exception_path_rolls_back_and_propagates() -> None:
    log: list[str] = []
    with pytest.raises(ValueError, match="金额为负"):
        with ApprovalSession("CLM-2", log):
            raise ValueError("金额为负")
    assert log == ["BEGIN CLM-2", "ROLLBACK CLM-2"]


def test_enter_returns_session_object() -> None:
    log: list[str] = []
    with ApprovalSession("CLM-3", log) as session:
        assert session.claim_id == "CLM-3"
    assert log == ["BEGIN CLM-3", "COMMIT CLM-3"]


def test_exit_true_swallows_exception() -> None:
    log: list[str] = []
    with SwallowingSession("CLM-4", log):  # 不应抛出
        raise ValueError("被 __exit__ 返回 True 吞掉了")
    assert log == ["BEGIN CLM-4", "ROLLBACK CLM-4"]
