"""讲义示例测试：@contextmanager（计时与临时目录）。"""

from pathlib import Path

import pytest

from ctx_tools import scratch_dir, timed_block


def test_timed_block_records_elapsed() -> None:
    timings: list[tuple[str, float]] = []
    with timed_block("预审", timings):
        sum([1200, 3500])
    assert len(timings) == 1
    assert timings[0][0] == "预审"
    assert timings[0][1] >= 0


def test_timed_block_records_even_on_exception() -> None:
    timings: list[tuple[str, float]] = []
    with pytest.raises(RuntimeError):
        with timed_block("会炸的批次", timings):
            raise RuntimeError("中途出事")
    assert [label for label, _ in timings] == ["会炸的批次"]  # finally 兜住了


def test_scratch_dir_lifecycle() -> None:
    with scratch_dir() as workdir:
        assert workdir.is_dir()
        marker = workdir / "marker.txt"
        marker.write_text("ok", encoding="utf-8")
        assert marker.exists()
    assert not workdir.exists()  # 正常退出：删除


def test_scratch_dir_cleans_up_on_exception() -> None:
    seen: list[Path] = []
    with pytest.raises(RuntimeError):
        with scratch_dir() as workdir:
            seen.append(workdir)
            raise RuntimeError("中途出事")
    assert not seen[0].exists()  # 异常退出：照样删除——清理必达
