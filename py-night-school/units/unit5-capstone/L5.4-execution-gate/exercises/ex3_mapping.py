# 练习 3（单变量编辑约束：只改本文件 TODO 标注的函数体/区域**与所需的顶部 import**，其余不要动）
"""JAVA-MAPPING.md 的补全器/校验器（开放设计题·诚实降级）——本课结业兑现物的质检工装。

code/JAVA-MAPPING.md 有 4 行 Java 对应物留了 TODO(ex3)——你的任务是把它们补全
（对照本地克隆 ~/develop/opensource/ 的 langgraph4j / spring-ai-alibaba 核实后填），
本题写的则是**质检工装**：validate 检查映射表的结构纪律，count_rows 统计行数。

纪律红线（映射表的诚实性，本题把它工程化）：
- 每行必备四列（模式 / Python 侧 / Java 对应物 / 翻译坑）——少列 = 结构破损；
- Java 对应物列非空——空着 = 没翻译，不算映射；含 TODO 标记 = 未填，校验要报；
- 「需自建」是合法取值（克隆里没有对应物时的诚实写法）——不算未填。

完成判据：uv run pytest exercises/test_ex3.py 全绿——6 个测试：
  split_tables（given）把 markdown 切成 {表名: 数据行单元格}；
  validate：好表零问题 / 缺列报错 / Java 列空报错 / TODO 标记报「未填」；
  count_rows：只数数据行（表头与 --- 分隔行不算）；
  活检：对 code/JAVA-MAPPING.md 跑 validate——报告的未填行数与文中 TODO 标记数一致
  （你每补全一行，两边同步减一；全填完两边归零——结构自证，不硬造内容判分）。
"""

from __future__ import annotations

import re

COLUMNS = ("模式", "Python 侧", "Java 对应物", "翻译坑")  # 主表必备四列
TODO_MARK = "TODO(ex3)"  # 学员未填标记（code/JAVA-MAPPING.md 的约定）


def split_tables(text: str) -> dict[str, list[list[str]]]:
    """（given）markdown → {表名: [数据行的单元格列表…]}。

    按 ##/### 标题分节，节内以首条表头行为界取表格；返回**数据行**（跳过表头行与
    `|---|---|` 分隔行），单元格已 strip。没有表格的节不产出。
    """

    def _cells(line: str) -> list[str]:
        parts = re.split(r"(?<!\\)\|", line.strip())  # 未转义的 | 才是列界（\| 是单元格内的字面管道）
        cells = [cell.strip().replace("\\|", "|") for cell in parts]
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        return cells

    def _is_separator(line: str) -> bool:
        return bool(re.fullmatch(r"\|?[\s:|-]+\|?", line.strip())) and "-" in line

    tables: dict[str, list[list[str]]] = {}
    section = ""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#"):
            section = line.lstrip("#").strip()
        elif line.strip().startswith("|"):
            rows: list[list[str]] = []  # 表头行只用于探位（i += 1 跳过），不进数据
            i += 1
            if i < len(lines) and _is_separator(lines[i]):
                i += 1
                while i < len(lines) and lines[i].strip().startswith("|"):
                    rows.append(_cells(lines[i]))
                    i += 1
            if rows:
                tables.setdefault(section, []).extend(rows)
            continue
        i += 1
    return tables


def validate(tables: dict[str, list[list[str]]]) -> list[str]:
    """校验主表的结构纪律（你的 TODO）：四列齐 + Java 对应物非空 + TODO 标记报「未填」。

    输入是 split_tables 的返回；输出是问题清单（空列表 = 通过）。判什么：
    - 每行 len(行) 必须 == 4（COLUMNS 的长度）——缺列报「第 N 行缺列」；
    - 第 3 列（Java 对应物，下标 2）为空串 → 报「第 N 行 Java 对应物为空」；
    - 第 3 列含 TODO_MARK → 报「第 N 行未填（TODO 未补全）」——它与空列是两种问题；
    - 「需自建」是合法值，不报。
    问题信息要能定位到行（1 起计数）。
    """
    # TODO(ex3): 逐行校验四列长度与 Java 列内容，收集问题清单并返回
    raise NotImplementedError("TODO(ex3): validate")


def count_rows(tables: dict[str, list[list[str]]]) -> int:
    """统计主表数据行数（你的 TODO）：split_tables 已跳过表头与分隔行——直接数。

    返回所有节数据行的总数（主表 + 词汇表都算——口径写死：数的就是 split_tables 的产出）。
    """
    # TODO(ex3): 数出全部数据行
    raise NotImplementedError("TODO(ex3): count_rows")


def audit_file(path: str) -> dict:
    """（given）对一份 JAVA-MAPPING.md 跑全流程：切表 → 校验 → 统计，返回回执。

    学员工装入口：uv run python -c "from ex3_mapping import audit_file; print(audit_file('../code/JAVA-MAPPING.md'))"
    """
    text = open(path, encoding="utf-8").read()
    tables = split_tables(text)
    return {
        "rows": count_rows(tables),
        "problems": validate(tables),
        "todo_marks_in_text": text.count(TODO_MARK),
    }
