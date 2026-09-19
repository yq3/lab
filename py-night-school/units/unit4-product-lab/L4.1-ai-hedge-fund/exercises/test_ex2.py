"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import json
from pathlib import Path

import ex2_cache as ex2


def test_second_review_is_zero_client_calls(tmp_path: Path) -> None:
    client = ex2.ScriptClient(['{"stance": "support", "confidence": 80}'])
    checker = ex2.MiniChecker("compliance", client, ex2.DecisionCache(tmp_path))
    first = checker.review("审查报销单 CLM-2026-0001")
    second = checker.review("审查报销单 CLM-2026-0001")
    assert client.calls == 1  # 第二次命中缓存，模型替身只被调了一次
    assert second == first
    assert len(list(tmp_path.glob("*.json"))) == 1  # 一决定一文件，重放不新增


def test_key_is_deterministic_and_content_addressed() -> None:
    a = ex2.decision_key("compliance", "mock-model", "system 文本", "user 文本")
    assert a == ex2.decision_key("compliance", "mock-model", "system 文本", "user 文本")
    assert len(a) == 24  # sha256 hex 截前 24 位
    assert a != ex2.decision_key("budget", "mock-model", "system 文本", "user 文本")
    assert a != ex2.decision_key("compliance", "other-model", "system 文本", "user 文本")
    assert a != ex2.decision_key("compliance", "mock-model", "system 文本 2", "user 文本")
    assert a != ex2.decision_key("compliance", "mock-model", "system 文本", "user 文本 2")


def test_put_get_roundtrip_and_created_at(tmp_path: Path) -> None:
    cache = ex2.DecisionCache(tmp_path)
    cache.put("abc", {"checker": "compliance", "response": "ok"})
    record = cache.get("abc")
    assert record is not None
    assert record["checker"] == "compliance"
    assert record["response"] == "ok"
    assert "created_at" in record  # created_at 由 put 补——审计字段不靠调用方自觉


def test_parse_error_keeps_raw_response_on_disk(tmp_path: Path) -> None:
    client = ex2.ScriptClient(["这单预算没问题，我同意。"])  # 无 JSON 的台词
    checker = ex2.MiniChecker("budget", client, ex2.DecisionCache(tmp_path))
    result = checker.review("审查报销单 CLM-2026-0002")
    assert result.get("abstained") is True
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8"))
    assert "parse_error" in record
    assert record["response"] == "这单预算没问题，我同意。"  # 原始响应原样留盘
    assert record["system"] == ex2.MiniChecker.SYSTEM  # 精确 prompt 也在——回放免费


def test_corrupt_cache_entry_is_a_miss(tmp_path: Path) -> None:
    cache = ex2.DecisionCache(tmp_path)
    (tmp_path / "badkey.json").write_text("{ 这不是 JSON", encoding="utf-8")
    assert cache.get("badkey") is None  # 损坏当 miss，不炸
    cache.put("badkey", {"response": "重写后的记录"})
    assert cache.get("badkey") is not None  # 下一次 put 重写了它
