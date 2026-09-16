"""选型工作台第三件（本里程碑唯一的编码 TODO）：决策表定稿——聚合三路证据。

三路输入：
- bench.py 的重验结果（LessonResult 列表：五课时 contract 全绿才算数）；
- tablegen.py 的定量数据（MetricRow 列表：依赖数 + 手写总行数——装配+节点+胶水）；
- notes/ 五页对照笔记的「锁定性一句话」小节（你的定性结论，一页一句）。

你的任务：补全 ``aggregate()``——按框架 key 把三路证据 join 成 DecisionRow 列表。
给定件（不要改）：FRAMEWORKS / NOTES_SECTIONS / PLACEHOLDER / section_body /
render_final_table / notes_status / main。

用法（学员命令，跨平台；TODO 填完前会打印设计内报错）：
    uv run python summary.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import bench
import tablegen

NOTES_DIR = Path(__file__).resolve().parent / "notes"

# 五个框架 key → 展示名（notes/<key>.md 一一对应；langgraph 一行由 L3.2/L3.4 两课时合并）
FRAMEWORKS: dict[str, str] = {
    "mini-agent": "mini-agent（Unit 2 对照组）",
    "openai-agents": "openai-agents 0.22.2",
    "langgraph": "langgraph 1.2.11（L3.2 手装 + L3.4 prebuilt）",
    "deepagents": "deepagents 0.7.13",
    "adk-python": "google-adk 2.9.0",
}

# 五页笔记的固定小节（tests/test_notes_meta.py 按它把关；顺序即页面顺序）
NOTES_SECTIONS: tuple[str, ...] = (
    "它替 mini-agent 付掉了什么",
    "它没替你付什么",
    "最惊讶的一个机制",
    "锁定性一句话",
    "什么时候选它",
)

PLACEHOLDER = "TODO(笔记)"  # 模板占位符：出现在笔记小节里 = 该小节还没写
MISSING_NOTE = "（未完成：笔记占位符未替换）"


@dataclass(frozen=True)
class DecisionRow:
    """决策表的一行（展示单元格都是 str，缺失时用「缺」/「—」如实标注）。"""

    framework: str  # 展示名
    bench: str  # "PASS" / "FAIL" / "—"（对照组没有 contract 重验）
    deps: str  # 依赖数（lock 包）；缺数据 = "缺"
    handwritten: str  # 手写总行数（装配+节点+胶水）；langgraph 两种装配 = "63 / 28" 这种并列
    lock_line: str  # 笔记「锁定性一句话」小节的第一句；未写完 = MISSING_NOTE


def section_body(note_text: str, heading: str) -> str:
    """给定笔记全文与小节标题，返回该小节正文（到下一个 ``## `` 为止）——纯函数（给定）。

    小节标题匹配 ``## 标题`` 行（strip 后全等）；找不到返回空串。
    """
    lines = note_text.splitlines()
    body: list[str] = []
    collecting = False
    for line in lines:
        if line.startswith("## "):
            if collecting:
                break
            collecting = line[3:].strip() == heading
            continue
        if collecting:
            body.append(line)
    return "\n".join(body).strip()


def first_meaningful_line(body: str) -> str:
    """小节正文里第一个非空段落（连续非空行合成一句，去掉列表前缀 ``- ``）——锁定性一句话取它（给定）。

    按「段落」而不是物理行取：笔记源文件换行只是排版，「一句话」以空行分界。
    """
    paragraph: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            if paragraph:
                break  # 段落结束
            continue  # 跳过段前空行
        paragraph.append(line)
    if not paragraph:
        return ""
    return " ".join(paragraph).removeprefix("- ").strip()


# ---- TODO 区（学员作答处；实现所需的顶部 import 可以补） ----


def aggregate(
    bench_rows: list[bench.LessonResult],
    metric_rows: list[tablegen.MetricRow],
    notes: dict[str, str],
) -> list[DecisionRow]:
    """按 FRAMEWORKS 的顺序把三路证据聚合成决策表行（TODO(s1)：你写）。

    判定规则（题目口径，hints 只复述不放松）：
    - bench：该框架的所有课时结果全 PASS 才 PASS，任一 FAIL 则 FAIL，没有重验记录为 "—"；
    - deps / handwritten（手写总行数）：从该框架的 MetricRow 取。handwritten 并列规则——
      同一框架多条定量行（langgraph 的手装/prebuilt）按出现顺序用 " / " 连接各自行数；
      没有数据为 "缺"；
    - lock_line：notes[框架 key] 的「锁定性一句话」小节第一句；该小节缺失、整页缺失、
      或正文含 PLACEHOLDER 时为 MISSING_NOTE；
    - 行顺序与 FRAMEWORKS 的键序一致（mini-agent 打头做对照组）。
    """
    # TODO(s1): 先处理 bench：按 r.framework 分组，组内全 PASS -> "PASS"，任一 FAIL -> "FAIL"，空组 -> "—"
    # TODO(s1): 再处理定量：按 m.framework 分组；deps 取第一条非 None（同框架同 lock）；
    #           handwritten 把组内各行的 handwritten_loc（None 跳过）按序拼成 "a / b"，全 None 或空组 -> "缺"
    # TODO(s1): 最后笔记：section_body(notes.get(key, ""), "锁定性一句话") -> first_meaningful_line；
    #           正文为空或含 PLACEHOLDER -> MISSING_NOTE（用 section 级判断，别整页判断）
    # TODO(s1): 按 FRAMEWORKS 键序组装 DecisionRow（展示名用 FRAMEWORKS[key]）
    raise NotImplementedError("TODO(s1): 补全 aggregate")


# ---- 给定件（不要改） ----


def render_final_table(rows: list[DecisionRow]) -> str:
    """决策表定稿（markdown）——渲染是给定的，判定语义全在 aggregate 里。"""
    lines = [
        "# 决策表定稿（summary.py 聚合 bench + tablegen + notes 生成）",
        "",
        "| 框架 | contract 重验 | 依赖数（lock 包） | 手写总行数（装配+节点+胶水） | 锁定性一句话 |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| {row.framework} | {row.bench} | {row.deps} | {row.handwritten} | {row.lock_line} |")
    return "\n".join(lines)


def notes_status(notes: dict[str, str]) -> list[tuple[str, str]]:
    """五页笔记的完成度检查（给定）：每页 = 固定小节齐 且 无占位符 =「五节齐」。"""
    statuses: list[tuple[str, str]] = []
    for key in FRAMEWORKS:
        text = notes.get(key, "")
        if not text:
            statuses.append((key, "缺页"))
            continue
        missing = [h for h in NOTES_SECTIONS if not section_body(text, h)]
        if missing:
            statuses.append((key, f"缺小节: {', '.join(missing)}"))
        elif PLACEHOLDER in text:
            statuses.append((key, "占位符未替换"))
        else:
            statuses.append((key, "五节齐"))
    return statuses


def main() -> None:
    notes = {key: (NOTES_DIR / f"{key}.md").read_text(encoding="utf-8") for key in FRAMEWORKS}
    rows = aggregate(bench.collect_results(bench.UNIT3_DIR), tablegen.collect_rows(tablegen.UNITS_DIR), notes)
    print(render_final_table(rows))
    print("\n笔记完成度（tests/test_notes_meta.py 把关结构，这里只报状态）：")
    for key, status in notes_status(notes):
        print(f"  {key:<15} {status}")


if __name__ == "__main__":
    main()
