"""ast 行数统计工具——讲义量化结论的口径（宪法纪律：行数统计必须写明工具与口径）。

口径：用 ast.parse 解析模块 → 定位目标 def/class 的行区间（node.lineno..node.end_lineno，
装饰器行不计入）→ 剔除该函数/类自己的 docstring 行区间（各级 docstring 的 lineno..end_lineno）
→ 数非空非注释行。比 shell grep 管道可复现：不依赖 grep 方言，空行/注释/文档串三类
在 ast 与 token 层面都有明确定义。

用法（uv run，跨平台）：
    uv run python code/count_loc.py module <file>            # 整模块：总行数 / 非空非注释行数
    uv run python code/count_loc.py def <file> <qualname>    # 函数或类：非空非注释行数（剔 docstring）
    uv run python code/count_loc.py range <file> <start> <end>  # 显式行区间：非空非注释行数

qualname 支持嵌套（如 ToolNode._func）。exit 1 + 报错 = 目标不存在，防止拿错文件静默数错。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

TargetNode = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def _docstring_spans(node: ast.AST) -> list[tuple[int, int]]:
    """收集节点体内所有「独立表达式语句的字符串字面量」（即各级 docstring）的行区间。"""
    spans: list[tuple[int, int]] = []
    body = getattr(node, "body", [])
    if (
        len(body) >= 1
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        first = body[0]
        spans.append((first.lineno, first.end_lineno))
    for child in body:
        spans.extend(_docstring_spans(child))
    return spans


def count_nonblank_noncomment(
    source: str, skip_spans: list[tuple[int, int]], window: tuple[int, int] | None = None
) -> int:
    """数 [window] 行区间内的非空非注释行；skip_spans 是行区间黑名单（如 docstring）。"""
    lines = source.splitlines()
    start, end = window if window else (1, len(lines))
    skip: set[int] = set()
    for skip_start, skip_end in skip_spans:
        skip.update(range(skip_start, skip_end + 1))
    count = 0
    for number, raw in enumerate(lines, start=1):
        if number < start or number > end or number in skip:
            continue
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def find_target(tree: ast.Module, qualname: str) -> TargetNode | None:
    """按点分路径逐层找 def/class（逐层只找直接子节点，同名嵌套需写全路径）。"""
    parts = qualname.split(".")
    node: ast.AST = tree
    for part in parts:
        found: TargetNode | None = None
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and child.name == part:
                found = child
                break
        if found is None:
            return None
        node = found
    return node if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) else None


def main() -> None:
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    mode, path_str = sys.argv[1], sys.argv[2]
    path = Path(path_str).expanduser()  # 支持 ~ 家目录写法：Windows 的 PowerShell 不为参数展开 ~
    if not path.is_file():
        print(f"file not found: {path}")
        sys.exit(1)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    if mode == "module":
        total = len(source.splitlines())
        loc = count_nonblank_noncomment(source, [])
        print(f"{path}: total={total} loc={loc}")
    elif mode == "def":
        if len(sys.argv) < 4:
            print("usage: def <file> <qualname>")
            sys.exit(2)
        qualname = sys.argv[3]
        node = find_target(tree, qualname)
        if node is None or node.end_lineno is None:
            print(f"target not found: {qualname}")
            sys.exit(1)
        loc = count_nonblank_noncomment(source, _docstring_spans(node), (node.lineno, node.end_lineno))
        print(f"{path}#{qualname}: lines={node.lineno}-{node.end_lineno} loc={loc} (docstring 已剔除)")
    elif mode == "range":
        if len(sys.argv) < 5:
            print("usage: range <file> <start> <end>")
            sys.exit(2)
        start, end = int(sys.argv[3]), int(sys.argv[4])
        loc = count_nonblank_noncomment(source, [], (start, end))
        print(f"{path}:{start}-{end}: loc={loc}")
    else:
        print(f"unknown mode: {mode}")
        sys.exit(2)


if __name__ == "__main__":
    main()
