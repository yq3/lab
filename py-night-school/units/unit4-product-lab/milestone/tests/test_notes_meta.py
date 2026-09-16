"""notes/ 三份改造说明模板的结构把关（meta-test，L0.1 ex2 先例：验收直接检查交付物本身）。

不要改本文件。判定规则：
- 三页齐（文件名与 verify.PRODUCTS 一一对应）；
- 每页五个固定小节（verify.NOTES_SECTIONS）齐且正文非空；
- 模板态（页含 ``TODO(改造)`` 占位符）时：五个小节**每节**都要有占位符——任何一节
  预填了答案都算结构红；且 solution/notes 对应页必须是完成版（无占位符、五节齐）。
  学员完成里程碑 = 把三页的 ``TODO(改造)`` 全部替换为自己的内容；誊写完成后整页无
  占位符，本文件全部测试照常绿（完成态由小节测试接管）；
- 每页的「改造要求」清单必须点中该课加餐指定的关键物（配置项 / 文件路径 / env 名 /
  锚定 commit）——关键词表是发货时从三课讲义 §3 加餐提炼的**合成夹具**，不 import
  兄弟课时的任何代码（毕业态镜像里没有它们）。
"""

from __future__ import annotations

from pathlib import Path

from verify import NOTES_SECTIONS, PLACEHOLDER, PRODUCTS, section_body

MILESTONE_DIR = Path(__file__).resolve().parent.parent
NOTES_DIR = MILESTONE_DIR / "notes"
SOLUTION_NOTES_DIR = MILESTONE_DIR / "solution" / "notes"

# 改造要求清单的「关键物」关键词（发货时从三课 README §3 加餐提炼的合成夹具；
# 断言它们出现在对应模板页里 = 任务卡写准了产品路径与配置项名，不是空话）。
REQUIREMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ai-hedge-fund": (
        "buffett.py",  # 改造 A 的人格 prompt 文件
        "weight:",  # 改造 B 的 mandate YAML 权重字段
        "deep-value.yaml",  # 产品权重写法的参照文件
        "HEDGE_FUND_LLM_MODEL",  # 模型 id env
        "OPENAI_API_BASE",  # 兼容端点覆盖 env
        "fc1bf25",  # 锚定 commit
    ),
    "tradingagents": (
        "max_debate_llm_calls",  # 改造二的新配置项（本里程碑的真改造）
        "max_debate_rounds",  # 改造一的既有轮次配置
        "default_config.py",  # 配置项与 env 映射的落点
        "conditional_logic.py",  # 计数终止路由器（贯穿点）
        "TRADINGAGENTS_",  # 产品 env 前缀（provider/backend/deep/quick 四项）
        "be952b8",  # 锚定 commit
    ),
    "vibe-trading": (
        "check_mandate",  # 要抄改的检查链函数
        "enforcement.py",  # 检查链所在文件
        "test_mandate_enforcement.py",  # per-limit 测试思想的出处
        "per-limit",  # 用例组织思想
        "f84b2977",  # 锚定 commit
    ),
}


def _sections_complete(text: str) -> list[str]:
    """返回缺失的固定小节标题列表（小节存在且正文非空才算齐）。"""
    return [h for h in NOTES_SECTIONS if not section_body(text, h)]


def missing_keywords(text: str, keywords: tuple[str, ...]) -> list[str]:
    """返回 text 里没出现的关键词（纯函数：改造要求清单的对齐检查就用它）。"""
    return [k for k in keywords if k not in text]


def _read_notes(dir_: Path) -> dict[str, str]:
    return {key: (dir_ / f"{key}.md").read_text(encoding="utf-8") for key in PRODUCTS}


# ---- 页面齐全与小节结构 ----


def test_three_pages_present() -> None:
    for key in PRODUCTS:
        assert (NOTES_DIR / f"{key}.md").is_file(), f"缺改造说明页: notes/{key}.md"


def test_template_sections_present() -> None:
    for key, text in _read_notes(NOTES_DIR).items():
        missing = _sections_complete(text)
        assert not missing, f"notes/{key}.md 缺小节: {missing}"


def test_template_state_every_section_has_todo() -> None:
    """模板态判定：页含占位符时，五个小节每节都要有 TODO(改造)——防任何一节预填答案。

    学员誊写完成后整页无占位符，本测试对完成页自然通过（不再有「模板态」义务）。
    """
    for key, text in _read_notes(NOTES_DIR).items():
        if PLACEHOLDER not in text:
            continue  # 完成态：由小节结构与 solution 对照测试接管
        untouched = [h for h in NOTES_SECTIONS if PLACEHOLDER not in section_body(text, h)]
        assert not untouched, f"notes/{key}.md 的小节预填了内容（无占位符）: {untouched}"


def test_placeholder_pages_have_completed_solution() -> None:
    """占位符页的完成态以 solution/notes 为准：答案页必须存在、小节齐、无占位符。

    学员完成里程碑 = 把三页的 ``TODO(改造)`` 全部替换为自己的结论；本测试不判
    「你写得好不好」（那没有机器判据），只判结构上「有完成版可对照收口」。
    """
    for key, text in _read_notes(NOTES_DIR).items():
        if PLACEHOLDER not in text:
            continue  # 已完成誊写的页：结构测试直接管（上一条）
        solution_page = SOLUTION_NOTES_DIR / f"{key}.md"
        assert solution_page.is_file(), f"notes/{key}.md 含占位符，但 solution/notes/{key}.md 缺失"
        done = solution_page.read_text(encoding="utf-8")
        missing = _sections_complete(done)
        assert not missing, f"solution/notes/{key}.md 缺小节: {missing}"
        assert PLACEHOLDER not in done, f"solution/notes/{key}.md 仍含占位符（答案不是完成态）"


# ---- 改造要求清单的关键物对齐（关键词来自三课 README §3 加餐的提炼，合成夹具） ----


def test_requirement_checklists_name_real_things() -> None:
    for key, text in _read_notes(NOTES_DIR).items():
        missing = missing_keywords(text, REQUIREMENT_KEYWORDS[key])
        assert not missing, f"notes/{key}.md 的改造要求清单漏了关键物: {missing}"


def test_missing_keywords_on_synthetic_fixtures() -> None:
    # 合成字符串夹具：对齐检查自身的判定逻辑（不依赖真页面）
    assert missing_keywords("a b c", ("a", "c")) == []
    assert missing_keywords("a b", ("a", "c")) == ["c"]
    assert missing_keywords("", ("x",)) == ["x"]
    assert missing_keywords("weight: 2.0", ("weight:",)) == []
    assert missing_keywords("weight 2.0", ("weight:",)) == ["weight:"]  # 冒号是关键词的一部分
