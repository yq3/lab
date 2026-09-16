"""选型工作台第二件：决策表数据页——从六份依赖清单与六组手写函数里提取定量列。

两个口径（都写明工具，可复现——宪法纪律：量化结论禁止 shell grep 管道的隐式口径）：

1. **依赖数**：tomllib（3.11+ 进标准库的 TOML 解析器，≈ Java 的 TOML 配置读取）
   解析各课 uv.lock，数 ``[[package]]`` 条目数。口径注意：含 dev 四件套
   （pytest/ruff/pyright/nodejs-wheel-binaries）及其传递依赖——各课同口径，可比。
2. **手写总行数（装配+节点+胶水）**：ast.parse 定位目标 def/class 的行区间
   （node.lineno..end_lineno，装饰器行不计），剔除各级 docstring 行区间后数非空、
   非 ``#`` 注释行——与 L3.4 count_loc.py 同款纪律（Unit 2「292→249」先例的同源
   做法，本文件自带实现）。数的是「同题 demo 里你亲手写的**全部**函数」：
   装配函数 + 自写节点函数 + 胶水（入口消息、模型客户端、run_review 运行编排）。

**与 L3.8 决策表的列名刻意不同**（防撞名，两页放一起看必须能对上账）：
L3.8（L3.8-comparison/README.md 的数据页）拆两列——「装配 loc」（装进框架的行）与
「自写节点/循环 loc」（框架没替你付的循环内脏）。本列数全量，恒等式：

    手写总行数 = L3.8 装配 loc + L3.8 自写节点/循环 loc + 胶水 loc

发货态对账（ast 同口径逐格可复现）：L3.1 29=15+0+14；L3.2 63=10+20+33；
L3.4 28=6+0+22；L3.5 71=8+0+63；L3.6 33=9+0+24。两页回答不同的问题：
工作台答「我一共要写多少行」（预算），决策表答「框架替我写了哪部分」（归因）。

每行数了**哪些**目标函数在 render_markdown 的「口径明细」里逐条列出——口径透明，
任何人拿同样目标能复现出同样数字。

对照行（mini-agent）的目标是「四框架替你付掉的四个零件」：ReAct 循环、工具 schema
生成、注册表分发、结构化校验回喂。行数取参考答案口径（solution/ 优先于学员件），
与 Unit 2 里程碑 README 的「五模块全量 249 行」是**不同口径**——这里只数被框架替掉的
那部分，所以更小；两个数字都真，回答的是两个问题。

用法（学员命令，跨平台）：
    uv run python tablegen.py            # 打印决策表数据页
    uv run python tablegen.py --out decision-table-data.md   # 另写文件
"""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

UNITS_DIR = Path(__file__).resolve().parents[2]  # py-night-school/units（六行数据的公共根）


@dataclass(frozen=True)
class LessonSpec:
    """一行数据：课时目录 + 框架 key（summary 聚合用）+ 展示名 + 手写目标清单。"""

    lesson: str  # 相对 unit3-frameworks/（对照行相对 units/，用绝对前缀区分见下）
    framework: str
    label: str
    targets: tuple[str, ...]  # "文件::qualname"，qualname 支持嵌套（ReActAgent.run）
    detail: str  # 口径的一句话说明


# 六行数据。框架行的目标=「同题 demo 你亲手写的全部函数」（手写总行数口径：
# 工具包装/模型绑定/图或 agent 构建/入口消息/节点函数/运行编排）；对照行的目标=四个被替掉的零件。
# 其中「装进框架的行」与「自写的节点/循环内脏」在 L3.8 决策表里拆成两列（装配 loc /
# 自写节点 loc）——本页数全量，各行 detail 尾注给出三层拆分，两页逐行能对账；
# L3.2 的行含状态 schema（ClaimState）与节点函数，L3.4 的 prebuilt 一个调用换掉
# 整张图，总行数差就是「约定优于配置」的量化。
SPECS: tuple[LessonSpec, ...] = (
    LessonSpec(
        "unit3-frameworks/L3.1-openai-agents",
        "openai-agents",
        "openai-agents 0.22.2",
        (
            "code/demo.py::_build_tools",
            "code/demo.py::_build_model",
            "code/demo.py::_build_agent",
            "code/demo.py::_user_message",
            "code/demo.py::run_review",
        ),
        "原语层手写件：工具直包 + 模型注入 + Agent 实例 + 入口消息 + 运行（= L3.8 装配 15 + 节点 0 + 胶水 14）",
    ),
    LessonSpec(
        "unit3-frameworks/L3.2-langgraph-basics",
        "langgraph",
        "langgraph 1.2.11（手装图）",
        (
            "code/demo.py::ClaimState",
            "code/demo.py::make_reviewer",
            "code/demo.py::tools_node",
            "code/demo.py::route_after_reviewer",
            "code/demo.py::finalize",
            "code/demo.py::build_graph",
            "code/demo.py::model_for_url",
            "code/demo.py::initial_messages",
            "code/demo.py::run_review",
        ),
        "手装图全套：状态 schema + 3 节点 + 条件边 + 图装配 + 入口消息 + 运行（= L3.8 装配 10 + 节点 20 + 胶水 33）",
    ),
    LessonSpec(
        "unit3-frameworks/L3.4-langgraph-fanout",
        "langgraph",
        "langgraph 1.2.11（prebuilt）",
        (
            "code/demo.py::build_agent",
            "code/demo.py::model_for_url",
            "code/demo.py::user_brief",
            "code/demo.py::run_review",
        ),
        "prebuilt 手写件：create_react_agent 一个调用 + 模型 + 入口消息 + 运行（= L3.8 装配 6 + 节点 0 + 胶水 22）",
    ),
    LessonSpec(
        "unit3-frameworks/L3.5-deepagents",
        "deepagents",
        "deepagents 0.7.13",
        (
            "code/demo.py::build_agent",
            "code/demo.py::input_with_files",
            "code/demo.py::run_review_with_trace",
            "code/demo.py::run_review",
        ),
        "harness 手写件：create_deep_agent + 输入组装 + 五轮剧本编排运行（含子代理/落盘/收尾）"
        "（= L3.8 装配 8 + 节点 0 + 胶水 63——胶水厚是 harness 默认行为多的编排代价）",
    ),
    LessonSpec(
        "unit3-frameworks/L3.6-adk-python",
        "adk-python",
        "google-adk 2.9.0",
        (
            "code/adk_review.py::build_reviewer",
            "code/adk_review.py::build_runner",
            "code/adk_review.py::new_session",
            "code/adk_review.py::ask",
            "code/adk_review.py::final_text",
            "code/demo.py::run_review",
        ),
        "全家桶手写件：LlmAgent + Runner/会话 + 发问事件流 + 收尾解析 + 运行（= L3.8 装配 9 + 节点 0 + 胶水 24）",
    ),
    LessonSpec(
        "unit2-mini-agent/milestone",
        "mini-agent",
        "mini-agent（Unit 2 对照组）",
        (
            "agent.py::ReActAgent.run",
            "tools.py::tool",
            "tools.py::to_openai_tools",
            "tools.py::run_tool",
            "structured.py::ask_structured",
        ),
        "对照行=被四框架替掉的四个零件：ReAct 循环 + 工具 schema 生成 + 注册表分发 + 结构化校验回喂"
        "（行数取 solution/ 参考答案口径，与「五模块全量 249 行」不同口径；"
        "对照行无「装配/节点」拆分——它的全部行都是自写，L3.8 的自写列记 249*）",
    ),
)


@dataclass(frozen=True)
class MetricRow:
    """一行定量数据；课时/文件缺失时 deps 与 handwritten_loc 为 None（优雅降级，不炸）。"""

    framework: str
    label: str
    deps: int | None
    # 手写总行数（装配+节点+胶水）：ast 口径数「同题 demo 你亲手写的全部函数」。
    # 与 L3.8 决策表的「装配 loc / 自写节点/循环 loc」两列刻意不同名——那两列之和
    # 再加胶水才等于本列（恒等式与逐课对账见模块 docstring）：两页能对账、不撞名。
    handwritten_loc: int | None
    targets: tuple[str, ...]
    detail: str


# ---- 解析层（纯函数，tests 用合成夹具离线测） ----


def count_lock_packages(lock_path: Path) -> int:
    """tomllib 数 uv.lock 的 [[package]] 条目数（含 dev 组及其传递依赖，各课同口径）。"""
    with lock_path.open("rb") as fh:
        data = tomllib.load(fh)
    return len(data.get("package", []))


TargetNode = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def _docstring_spans(node: ast.AST) -> list[tuple[int, int]]:
    """收集节点体内所有「独立表达式语句的字符串字面量」（各级 docstring）的行区间。"""
    spans: list[tuple[int, int]] = []
    body = getattr(node, "body", [])
    if (
        len(body) >= 1
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        spans.append((body[0].lineno, body[0].end_lineno))
    for child in body:
        spans.extend(_docstring_spans(child))
    return spans


def _find_target(tree: ast.Module, qualname: str) -> TargetNode | None:
    """按点分路径逐层找 def/class（逐层只找直接子节点，同名嵌套需写全路径）。"""
    node: ast.AST = tree
    for part in qualname.split("."):
        found: TargetNode | None = None
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and child.name == part:
                found = child
                break
        if found is None:
            return None
        node = found
    return node if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) else None


def count_target_loc(source: str, qualname: str) -> int:
    """ast 口径数一个 def/class 的非空非注释行（剔 docstring，装饰器行不计入）。

    目标不存在时抛 KeyError（对照 L3.4 count_loc 的 exit 1：拿错文件必须响，不能静默数错）。
    """
    tree = ast.parse(source)
    node = _find_target(tree, qualname)
    if node is None or node.end_lineno is None:
        raise KeyError(f"target not found: {qualname}")
    lines = source.splitlines()
    skip: set[int] = set()
    for start, end in _docstring_spans(node):
        skip.update(range(start, end + 1))
    count = 0
    for number in range(node.lineno, node.end_lineno + 1):
        if number in skip or number > len(lines):
            continue
        stripped = lines[number - 1].strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def _resolve_source(lesson_dir: Path, file_rel: str, prefer_solution: bool) -> str:
    """读目标文件源码；对照行优先 solution/（参考答案口径），不存在退回学员件。"""
    if prefer_solution:
        candidates = [lesson_dir / "solution" / file_rel, lesson_dir / file_rel]
    else:
        candidates = [lesson_dir / file_rel]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError(f"file not found under {lesson_dir}: {file_rel}")


def collect_row(spec: LessonSpec, units_dir: Path) -> MetricRow:
    """提取一行数据；课时/文件缺失时优雅降级（None + detail 注明原因）。"""
    lesson_dir = units_dir / spec.lesson
    missing: list[str] = []
    deps: int | None = None
    lock_path = lesson_dir / "uv.lock"
    if lock_path.is_file():
        deps = count_lock_packages(lock_path)
    else:
        missing.append("uv.lock")
    loc: int | None = None
    try:
        loc = 0
        for target in spec.targets:
            file_rel, _, qualname = target.partition("::")
            source = _resolve_source(lesson_dir, file_rel, prefer_solution=spec.framework == "mini-agent")
            loc += count_target_loc(source, qualname)
    except (FileNotFoundError, KeyError, SyntaxError) as exc:
        loc = None
        missing.append(str(exc))
    detail = spec.detail if not missing else f"{spec.detail}；数据缺失: {'; '.join(missing)}"
    return MetricRow(spec.framework, spec.label, deps, loc, spec.targets, detail)


def collect_rows(units_dir: Path) -> list[MetricRow]:
    """六行全收集。目录作参数（而非读全局常量），tests 用 tmp_path 合成夹具传入。"""
    return [collect_row(spec, units_dir) for spec in SPECS]


def render_markdown(rows: list[MetricRow]) -> str:
    """决策表数据页（markdown）：口径头 + 表 + 逐行口径明细。"""
    lines = [
        "# 决策表数据页（tablegen 自动生成——口径可复现，勿手改数字）",
        "",
        "- 依赖数：tomllib 解析各课 uv.lock 的 `[[package]]` 条目数（含 dev 四件套及其传递依赖，六行同口径）；",
        "- 手写总行数（装配+节点+胶水）：ast 定位各课手写函数（对照行是被框架替掉的四个零件），"
        "剔 docstring 后数非空非注释行。与 L3.8 决策表数据页的「装配 loc / 自写节点/循环 loc」"
        "两列刻意不同名：本列 = 那两列之和 + 胶水（入口消息 / 模型客户端 / run_review 运行编排），"
        "发货态对账 29=15+0+14、63=10+20+33、28=6+0+22、71=8+0+63、33=9+0+24；",
        "- 缺失课时对应格子为「缺」（目录/文件不在时优雅降级，不中断生成）。",
        "",
        "| 框架与装配 | 依赖数（uv.lock 包） | 手写总行数（装配+节点+胶水，ast 口径） |",
        "|---|---|---|",
    ]
    for row in rows:
        deps = str(row.deps) if row.deps is not None else "缺"
        loc = str(row.handwritten_loc) if row.handwritten_loc is not None else "缺"
        lines.append(f"| {row.label} | {deps} | {loc} |")
    lines.append("")
    lines.append("口径明细（每行数了哪些目标，`文件::qualname`）：")
    for row in rows:
        lines.append(f"- **{row.label}**：{row.detail}")
        for target in row.targets:
            lines.append(f"  - `{target}`")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成决策表数据页（依赖数 + 手写总行数）")
    parser.add_argument("--out", type=Path, default=None, help="可选：把数据页写到文件（默认只打印）")
    args = parser.parse_args()
    page = render_markdown(collect_rows(UNITS_DIR))
    print(page)
    if args.out is not None:
        args.out.write_text(page + "\n", encoding="utf-8")
        print(f"\n（已写入 {args.out}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
