"""练习 2 验收（不要改本文件——它就是你的判卷老师）。"""

from __future__ import annotations

import re

import ex2_scenario_map as ex2

# 期望映射（讲义 §3 Step4「何时选谁」的操作性检验；每格的显著优势见 test 断言注释）
EXPECTED = {
    "s1": "langgraph",  # 断电恢复 = interrupt+checkpoint 落盘（L3.3 压轴实验）
    "s2": "mini-agent",  # 一次性即弃 = 249 行零锁定、零装配（milestone）
    "s3": "deepagents",  # 子代理+虚拟文件台+记忆 = harness 三件套（L3.5）
    "s4": "adk",  # Google 栈+调试器+eval = 全家桶独有件（L3.6 Step5）
    "s5": "dify",  # 业务同学画布自改+表单 = 平台形态题眼（L3.7）
    "s6": "openai-agents",  # 极简原语+handoff 换人不换对话（L3.1）
}

CITATION = re.compile(r"(L3\.[1-7]|Unit 2|milestone|mini-agent)")


def test_choices_match_expected_mapping() -> None:
    assert set(ex2.CHOICES) == set(ex2.SCENARIOS)  # 六个场景一个不漏
    assert set(ex2.CHOICES.values()) <= set(ex2.FRAMEWORKS)  # 值只能从六个框架里选
    assert ex2.CHOICES == EXPECTED  # 逐格一致——选型理由见 REASONS


def test_reasons_are_nonempty_and_substantive() -> None:
    assert set(ex2.REASONS) == set(ex2.SCENARIOS)
    for sid, reason in ex2.REASONS.items():
        assert len(reason.strip()) >= 15, (sid, reason)  # 一段话，不是一个词
        assert CITATION.search(reason), (sid, reason)  # 理由必须带课次证据，能回指数据页


def test_no_placeholder_left() -> None:
    for mapping in (ex2.CHOICES, ex2.REASONS):
        assert all(value.strip() for value in mapping.values())  # 留空 = 没做完
