"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

from ex2_protocol import AuditSink, ConsoleSink, TeamSink


def test_structural_isinstance_without_inheritance() -> None:
    """静态满足协议（没继承）：isinstance 通过——runtime_checkable 的功劳。"""
    for sink in (ConsoleSink(), TeamSink()):
        assert isinstance(sink, AuditSink)


def test_no_inheritance_at_all() -> None:
    """两个类不许显式继承任何类（__bases__ 应恰为 (object,)）。"""
    for cls in (ConsoleSink, TeamSink):
        assert cls.__bases__ == (object,)


def test_record_behavior() -> None:
    assert ConsoleSink().record("CLM-2026-0001", "PASS") == "[console] CLM-2026-0001 PASS"
    assert TeamSink().record("CLM-2026-0001", "PASS") == "[team] CLM-2026-0001 PASS"


def test_interchangeable_in_consumer() -> None:
    """消费方只依赖协议形状：两个实现可以互换着用（鸭子类型的静态版）。"""
    results: list[tuple[str, str]] = [
        ("CLM-2026-0001", "PASS"),
        ("CLM-2026-0002", "REJECT:ITEM_OVER_LIMIT"),
    ]
    for sink in (ConsoleSink(), TeamSink()):
        lines = [sink.record(claim_id, verdict) for claim_id, verdict in results]
        assert lines[0].endswith("CLM-2026-0001 PASS")
        assert lines[1].endswith("CLM-2026-0002 REJECT:ITEM_OVER_LIMIT")
