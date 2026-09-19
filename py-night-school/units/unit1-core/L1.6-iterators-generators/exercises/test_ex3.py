"""练习 3 验收（不要改本文件——它就是你的判卷老师）。"""

from ex3_oneshot import read_amounts, total_pass_1, total_pass_2

EXPECTED_TOTAL = 1200 + 3500 + 480 + 18600 + 2400  # 26180


def test_ex3_both_passes_return_same_correct_total() -> None:
    first = total_pass_1()
    second = total_pass_2()
    assert first == second == EXPECTED_TOTAL  # 修复后两遍结果一致且正确


def test_ex3_evidence_of_the_bug_mechanism() -> None:
    # 对照组：生成器第二次消费就是静默空——陷阱机制本身（与本练习的修复互为印证）
    gen = read_amounts(["CLM-9001,meal,100", "CLM-9002,meal,200"])
    assert list(gen) == [100, 200]
    assert list(gen) == []  # 静默排空，无异常
