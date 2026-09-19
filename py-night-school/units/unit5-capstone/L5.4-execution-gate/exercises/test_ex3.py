"""练习 3 验收（不要改本文件——它就是你的判卷老师）。只查结构与统计，不硬造内容判分。"""

from __future__ import annotations

from pathlib import Path

import ex3_mapping as ex3

GOOD_ROWS = [
    ["StateGraph 装配", "graph.build_graph", "langgraph4j StateGraph#addNode/addEdge/compile", "节点动作返回 Map"],
    ["图版本绑定", "versioning.topology_signature", "需自建——两边都没有签名 API", "签拓扑不签字节码"],
    ["当日账本", "graph.PaymentLedger", "需自建——SQL 视图或 CQRS 读模型", "别建第二张 payments 表"],
]


def _md(rows: list[list[str]]) -> str:
    """拼一张三列/四列可调的最小 markdown 表（带标题节）。"""
    width = len(rows[0]) if rows else 3
    header = ["模式", "Python 侧", "Java 对应物", "翻译坑"][:width]
    sep = "|" + "---|" * width
    body = "\n".join("| " + " | ".join(row) + " |" for row in rows)
    head = "|" + "|".join(header) + "|"
    return f"## 主表\n\n{head}\n{sep}\n{body}\n"


def test_split_tables_returns_data_rows_only() -> None:
    """given 的切表器：跳过表头与 --- 分隔行、单元格已 strip、按标题分节。"""
    text = _md(GOOD_ROWS) + "\n## 词汇表\n\n| a | b |\n|---|---|\n| x | y |\n"
    tables = ex3.split_tables(text)
    assert set(tables) == {"主表", "词汇表"}
    assert tables["主表"] == GOOD_ROWS
    assert tables["词汇表"] == [["x", "y"]]  # 词汇表自己的表头（a/b）同样被跳过


def test_validate_passes_good_table() -> None:
    """好表零问题：四列齐、Java 列非空、「需自建」是合法值。"""
    assert ex3.validate({"主表": GOOD_ROWS}) == []


def test_validate_flags_missing_column() -> None:
    """缺列报错：三列表（少了翻译坑列）——问题信息能定位到行号（1 起计数）。"""
    rows = [
        ["StateGraph 装配", "graph.build_graph", "langgraph4j StateGraph"],
        ["条件边路由", "route_after_gate", "addConditionalEdges + mappings"],
    ]
    problems = ex3.validate({"主表": rows})
    assert len(problems) == 2  # 每行都缺列
    assert any("1" in p for p in problems) and any("2" in p for p in problems)


def test_validate_flags_empty_java_cell_and_todo_mark() -> None:
    """Java 列空与 TODO 未填是两种问题：空列报「为空」，TODO 标记报「未填」。"""
    rows = [
        ["模式甲", "py 甲", "", "坑甲"],
        ["模式乙", "py 乙", "TODO(ex3)：补全", "坑乙"],
    ]
    problems = ex3.validate({"主表": rows})
    assert len(problems) == 2
    assert any("为空" in p for p in problems)
    assert any("未填" in p for p in problems)


def test_count_rows_counts_data_rows_only() -> None:
    """统计：只数数据行（表头/分隔行已在切表时剔除），多节相加。"""
    tables = {"主表": GOOD_ROWS, "词汇表": [["a", "b"], ["x", "y"]]}
    assert ex3.count_rows(tables) == 5


def test_live_audit_of_shipped_mapping_doc() -> None:
    """活检：对 code/JAVA-MAPPING.md 跑 audit_file——未填报告数与文中 TODO 标记数一致
    （学员每补全一行两边同步减一；主表 ≥ 10 行是结业口径）。"""
    doc = Path(__file__).resolve().parents[1] / "code" / "JAVA-MAPPING.md"
    receipt = ex3.audit_file(str(doc))
    unfilled = sum(1 for p in receipt["problems"] if "未填" in p)
    assert unfilled == receipt["todo_marks_in_text"]  # 校验器与 TODO 标记互证
    main_rows = receipt["rows"] - 7  # 去掉词汇表 7 行——主表行数
    assert main_rows >= 10  # 结业口径：主表至少 10 个模式
