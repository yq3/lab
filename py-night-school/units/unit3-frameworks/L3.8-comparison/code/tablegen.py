"""L3.8 决策表数据生成器：mini-agent vs 四框架的「能力-成本-锁定性」数据页。

宪法纪律（讲义量化结论必须可复现）：本模块是决策表定量列的唯一数据源——
依赖数用 tomllib 解析 uv.lock（[[package]] 条目计数），行数用 ast 口径
（定位目标函数/类行区间，剔 docstring 行区间，数非空非注释行——L3.4 的
count_loc.py 先例重实现，禁止 shell grep 管道隐式口径）。

三个新知识点（首现，讲义 §2 展开）：
- tomllib：Python 3.11+ 标准库 TOML 解析器（只读二进制模式 rb）——解析 uv.lock；
- functools.cache：函数级记忆化装饰器——同一 demo.py 数多个函数只 parse 一次；
- dataclass(frozen=True)：行配置是不可变值对象（L1.3 复课）。

静态数字的诚实边界：「模型调用轮数」与 mini-agent 的「249 行」是各课讲义
实测过的数字，作为静态数据写在本模块（讲义数字本来就是实测过的——运行时
抓不到讲义）；其余定量列全部现场计算。

用法（uv run，跨平台）：
    uv run python code/tablegen.py                # 自动定位仓库根（向上找 CURRICULUM.md）
    uv run python code/tablegen.py <仓库根路径>    # 显式指定（如只 checkout 了本课时）

兄弟课时目录缺失时优雅降级：该行定量格标 missing（例如学员环境里只有本课时）。
"""

from __future__ import annotations

import ast
import sys
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

# ---------------------------------------------------------------------------
# 行配置：决策表成本表的六行（mini-agent + 五个课时装配代表；langgraph 两行代表
# L3.2 手装图与 L3.4 prebuilt 两种装配——题面相同，差异只在装配方式）。
# 路径全部相对仓库根；qualname 支持嵌套（ReActAgent.run 这种点分路径）。
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostRow:
    """成本表一行的全部配置：定量列的取数口径都在字段里。"""

    key: str
    lesson_rel: str  # 课时目录（相对仓库根）
    assembly: tuple[tuple[str, str], ...]  # (相对课时目录的文件, qualname) 装配/图构建函数
    nodes: tuple[tuple[str, str], ...]  # 自写节点/循环函数（框架全包的行留空）
    nodes_static: str  # 自写循环用讲义静态数字时的说明（空 = 用 ast 实测或 0）
    turns: int  # 模型调用轮数（讲义实测静态数字）
    turns_source: str  # 轮数出处（课次 + Step）


COST_ROWS: tuple[CostRow, ...] = (
    CostRow(
        key="mini-agent（milestone）",
        lesson_rel="units/unit2-mini-agent/milestone",
        assembly=(),  # 无框架可装配：构造调用散在 main.py 入口里（讲义 §3 Step2 导读）
        nodes=(),  # 发货态 run() 是 TODO 桩，不数桩——完成态数字用讲义口径（nodes_static）
        nodes_static="249*",
        turns=3,
        turns_source="milestone tests：查单→预审→回答三轮（test_t1_full_run_local_tools）",
    ),
    CostRow(
        key="openai-agents（L3.1）",
        lesson_rel="units/unit3-frameworks/L3.1-openai-agents",
        assembly=(
            ("code/demo.py", "_build_tools"),
            ("code/demo.py", "_build_model"),
            ("code/demo.py", "_build_agent"),
        ),
        nodes=(),
        nodes_static="",
        turns=2,
        turns_source="L3.1 Step 1：requests=2（output_type 不多花一轮）",
    ),
    CostRow(
        key="langgraph 手装（L3.2）",
        lesson_rel="units/unit3-frameworks/L3.2-langgraph-basics",
        assembly=(("code/demo.py", "build_graph"),),
        nodes=(  # 四个节点/路由函数是「循环内脏」——图引擎之外自己写的部分
            ("code/demo.py", "make_reviewer"),
            ("code/demo.py", "tools_node"),
            ("code/demo.py", "route_after_reviewer"),
            ("code/demo.py", "finalize"),
        ),
        nodes_static="",
        turns=2,
        turns_source="L3.2 Step 3：模型请求 2 次（reviewer 两轮）",
    ),
    CostRow(
        key="langgraph prebuilt（L3.4）",
        lesson_rel="units/unit3-frameworks/L3.4-langgraph-fanout",
        assembly=(("code/demo.py", "build_agent"),),
        nodes=(),
        nodes_static="",
        turns=2,
        turns_source="L3.4 Step 2：每单恰好 2 次模型请求",
    ),
    CostRow(
        key="deepagents（L3.5）",
        lesson_rel="units/unit3-frameworks/L3.5-deepagents",
        assembly=(("code/demo.py", "build_agent"),),
        nodes=(),
        nodes_static="",
        turns=5,
        turns_source="L3.5 Step 1：五轮（转交+查预算 → 子代理两轮 → 写底稿 → Advice 收尾）",
    ),
    CostRow(
        key="adk-python（L3.6）",
        lesson_rel="units/unit3-frameworks/L3.6-adk-python",
        assembly=(
            ("code/adk_review.py", "build_reviewer"),
            ("code/adk_review.py", "build_runner"),
        ),
        nodes=(),
        nodes_static="",
        turns=2,
        turns_source="L3.6 Step 1：request[0]/[1] 两次（litellm 中转后取证）",
    ),
)

# ---------------------------------------------------------------------------
# 能力表（事实）与锁定性表（定性 + 证据）：静态数据，每格注出处课次——
# 这些是各课讲义里实测/源码取证过的事实，运行时无法从代码里抓取。
# ---------------------------------------------------------------------------

CAPABILITY_FACETS = ("HITL", "检查点", "扇出", "子代理", "调试器", "eval")

CAPABILITY: dict[str, dict[str, str]] = {
    "mini-agent": {
        "HITL": "无——进程退出状态即丢，messages 是局部变量（milestone 对照表）",
        "检查点": "无——历史在调用栈里，跑完即忘（milestone 对照表）",
        "扇出": "无——并行要自己写（milestone）",
        "子代理": "无——转交要自己再造一个循环（milestone）",
        "调试器": "print_trace 手写轨迹打印（milestone main.py）",
        "eval": "pytest 手搓契约十一路取证（milestone tests）",
    },
    "openai-agents": {
        "HITL": "RunState 快照审批：needs_approval→to_state（约 18KB JSON）→批准恢复（L3.1 Step5）",
        "检查点": "RunState 即快照——会话对账/schema 版本/并发守卫在 run_state.py（5271 行，wc -l 口径）（L3.1 §2.8）",
        "扇出": "无并行原语——handoff 是串行换人接管（L3.1 Step3：ESCALATE 单 3 请求）",
        "子代理": "handoff-as-tool：专员包装成 transfer_to_* 工具，换 agent 不换对话（L3.1 Step3）",
        "调试器": "无 GUI；trace span 树默认外发 OpenAI，第一件事 set_tracing_disabled(True)（L3.1 Step2）",
        "eval": "无 eval 工具链，pytest 自理（L3.1）",
    },
    "langgraph": {
        "HITL": "interrupt()+Command(resume)：暂停→杀进程→恢复，payload 落盘（L3.3 Step2）",
        "检查点": "checkpointer 每 superstep 落盘；get_state_history 可回放每一步（L3.3 Step4）",
        "扇出": "Send 动态扇出：4 分支墙钟 229.7ms vs 分支合计 912.2ms（L3.4 Step4）",
        "子代理": "subgraph 图即节点（L3.2 Step5）；Send worker 内跑完整 agent（L3.4 Step4）",
        "调试器": "astream 流式轨迹免费；LangSmith 默认零外发（L3.2 §2.5、Step3）",
        "eval": "无内建（LangSmith 在平台侧，本单元未展开——诚实边界）（L3.2 延伸）",
    },
    "deepagents": {
        "HITL": "interrupt_on / permissions 规则表挂点（L3.5 §5 修复纪律）",
        "检查点": "复用 langgraph：files 也是 state channel，可 checkpoint（L3.5 Step2）",
        "扇出": "task 是串行派活收报告，非并行扇出（L3.5 Step3：子代理隔离对话）",
        "子代理": "声明式 SubAgent spec→task 工具；一个不声明也自动塞 general-purpose（L3.5 §2.4）",
        "调试器": "同 langgraph 谱系；虚拟文件系统可 ls/read_file 取证（L3.5 Step2）",
        "eval": "无内建（L3.5）",
    },
    "adk": {
        "HITL": "无内建 interrupt——四类 callback 可自造短路（L3.6 §2.3、Step4）",
        "检查点": "Session+state 由 SessionService 持久化；"
        "InMemory 是「testing and development」默认件（L3.6 §2.2、§5）",
        "扇出": "无一等扇出原语（本单元未展开——诚实边界）（L3.6）",
        "子代理": "无声明式子代理——LlmAgent 组合 transfer（本单元未展开）（L3.6 §6）",
        "调试器": "adk web：本地服务+浏览器调试器，事件流/会话/state 可视化（L3.6 Step5）",
        "eval": "AgentEvaluator+eval set+指标族；TrajectoryEvaluator 确定性轨迹比对（L3.6 Step5）",
    },
    "dify（平台）": {
        "HITL": "human-input 节点：表单+按钮即出边，平台生成 UI、自带超时（L3.7 §2.4）",
        "检查点": "工作流状态挂起在平台运行时——静态可解析、动态 pytest 够不着（L3.7 §1、Step2）",
        "扇出": "iteration / loop 画布节点（DSL 节点类型表 19 种之一）（L3.7 §2.3）",
        "子代理": "画布节点组合（agent-backend 是 v2 新组件，Pydantic AI 运行时）（L3.7 §2.2）",
        "调试器": "web 控制台：运行日志/标注/应用统计——运营视角（L3.7 Step4 能力清单）",
        "eval": "控制台标注，人工运营——对行为的断言进不了 CI（L3.7 Step4 能力清单）",
    },
}

LOCKIN_FACETS = ("端点中立", "私有格式依赖", "生态绑定")

LOCKIN: dict[str, dict[str, str]] = {
    "mini-agent": {
        "端点中立": "完全自控——client.py 自写直连任意 OpenAI 兼容端点（Unit 2 milestone）",
        "私有格式依赖": "无——messages/tools 载荷就是公共 chat-completions 协议（milestone client/tools）",
        "生态绑定": "无——httpx+pydantic+mcp 三件，44 个依赖全透明可数（milestone）",
    },
    "openai-agents": {
        "端点中立": "模型客户端可注入（OpenAIChatCompletionsModel 换端点）；"
        "但 trace 默认外发 api.openai.com，先关（L3.1 §2.7、Step2）",
        "私有格式依赖": "RunState 快照 JSON——schema 版本门禁与会话对账在框架内部（L3.1 §2.8）",
        "生态绑定": "openai 谱系轻绑定：span 协议、Responses API 默认路径（L3.1 §2.1）",
    },
    "langgraph": {
        "端点中立": "默认零外发——不设 LANGSMITH_* 即关（L3.2 §2.5）",
        "私有格式依赖": "Checkpoint=msgpack BLOB+serde 白名单——跨版本恢复要锁类型（L3.3 §2.4、Step4）",
        "生态绑定": "langchain 谱系（RunnableConfig/channels）；"
        "但它是 langgraph4j 同源上游——绑定即预习 Java 生产栈（L3.2 开场）",
    },
    "deepagents": {
        "端点中立": "同 langgraph：模型层任意 ChatModel 可换（L3.5 §2.3）",
        "私有格式依赖": "state['files'] channel——虚拟文件系统的存储形态绑图引擎（L3.5 Step2）",
        "生态绑定": "AgentMiddleware hook 族与中间件栈顺序是 deepagents 私有词汇（L3.5 §2.2）",
    },
    "adk": {
        "端点中立": "litellm 中转：openai/ 前缀是路由记号出网前剥掉；api_base/api_key 是 litellm 参数名（L3.6 §2.4）",
        "私有格式依赖": "Session/Event/state 作用域前缀（app:/user:）是 adk 私有词汇（L3.6 §2.2）",
        "生态绑定": "Google 生态：adk deploy 的 Cloud Run 一等公民、VertexAi* 服务件（L3.6 §2.1、对照表）",
    },
    "dify（平台）": {
        "端点中立": "模型供应商体系是平台数据库里的配置不是代码——换平台要重配全部路由（L3.7 Step4 能力清单）",
        "私有格式依赖": "App DSL 的 version 管导入策略不管行为兼容——minor 落后照常导入仅警告（L3.7 §5）",
        "生态绑定": "平台本体：插件市场/向量库/运行时——迁出=按 DSL 把画布重写成代码（L3.7 §2.1）",
    },
}

# ---------------------------------------------------------------------------
# ast 行数口径（L3.4 count_loc.py 先例的重实现，口径一字不差）
# ---------------------------------------------------------------------------


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


def count_nonblank_noncomment(source: str, skip_spans: list[tuple[int, int]], window: tuple[int, int]) -> int:
    """数 window 行区间内的非空非注释行；skip_spans 是行区间黑名单（docstring）。"""
    lines = source.splitlines()
    skip: set[int] = set()
    for start, end in skip_spans:
        skip.update(range(start, end + 1))
    count = 0
    for number, raw in enumerate(lines, start=1):
        if number < window[0] or number > window[1] or number in skip:
            continue
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def find_target(tree: ast.Module, qualname: str) -> ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | None:
    """按点分路径逐层找 def/class（逐层只找直接子节点，同名嵌套需写全路径）。"""
    parts = qualname.split(".")
    node: ast.AST = tree
    for part in parts:
        found = None
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and child.name == part:
                found = child
                break
        if found is None:
            return None
        node = found
    return node if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) else None


@cache
def parse_module(path: str) -> ast.Module:
    """解析并缓存模块（functools.cache：同一 demo.py 数多个函数只 parse 一次）。"""
    return ast.parse(Path(path).read_text(encoding="utf-8"), filename=path)


def def_loc(path: Path, qualname: str) -> int:
    """一个函数/方法的 ast 口径行数（剔 docstring 的非空非注释行）。目标缺失抛 LookupError。"""
    node = find_target(parse_module(str(path)), qualname)
    if node is None or node.end_lineno is None:
        raise LookupError(f"target not found: {path}#{qualname}")
    source = Path(path).read_text(encoding="utf-8")
    return count_nonblank_noncomment(source, _docstring_spans(node), (node.lineno, node.end_lineno))


def targets_loc(lesson_dir: Path, targets: tuple[tuple[str, str], ...]) -> int | None:
    """一组 (文件, qualname) 的 ast 行数合计；课时缺失返回 None（降级为 missing）。"""
    if not lesson_dir.is_dir():
        return None
    total = 0
    for rel, qualname in targets:
        total += def_loc(lesson_dir / rel, qualname)
    return total


def count_packages(lock_path: Path) -> int:
    """uv.lock 的 [[package]] 条目数（tomllib 解析；含本项目自身与 dev 组——口径写死在这里）。"""
    if not lock_path.is_file():
        raise LookupError(f"lock not found: {lock_path}")
    with lock_path.open("rb") as fh:
        data = tomllib.load(fh)
    return len(data.get("package", []))


# ---------------------------------------------------------------------------
# 渲染：三张 markdown 表 + 口径说明
# ---------------------------------------------------------------------------


def find_repo_root(start: Path) -> Path:
    """向上找仓库根（存在 CURRICULUM.md 与 units/ 的目录）。"""
    for candidate in (start, *start.parents):
        if (candidate / "CURRICULUM.md").is_file() and (candidate / "units").is_dir():
            return candidate
    raise LookupError(f"仓库根未找到（从 {start} 向上找 CURRICULUM.md）——可用参数显式指定")


def render_cost_table(root: Path) -> tuple[str, list[str]]:
    """成本表（定量）。返回 (markdown, 缺失行 key 列表)。"""
    lines = [
        "| 行 | 依赖数 | 装配 loc（ast） | 自写节点/循环 loc | 模型轮数（讲义实测） |",
        "|---|---|---|---|---|",
    ]
    missing: list[str] = []

    def mark_missing(row: CostRow, why: str) -> str:
        missing.append(row.key)
        return why

    for row in COST_ROWS:
        lesson_dir = root / row.lesson_rel
        if not lesson_dir.is_dir():
            deps = mark_missing(row, "missing")
        else:
            try:
                deps = str(count_packages(lesson_dir / "uv.lock"))
            except LookupError:
                deps = mark_missing(row, "missing")
        if not row.assembly:
            assembly = "—"
        else:
            try:
                loc = targets_loc(lesson_dir, row.assembly)
                assembly = "missing" if loc is None else str(loc)
            except (LookupError, OSError):
                assembly = mark_missing(row, "n/a（目标缺失）")
        if row.nodes:
            try:
                loc = targets_loc(lesson_dir, row.nodes)
                nodes = "missing" if loc is None else str(loc)
            except (LookupError, OSError):
                nodes = mark_missing(row, "n/a（目标缺失）")
        else:
            nodes = row.nodes_static or "0"
        lines.append(f"| {row.key} | {deps} | {assembly} | {nodes} | {row.turns} |")
    lines.append("")
    lines.append("注：依赖数 = uv.lock 的 [[package]] 条目数（tomllib）；装配/自写节点 loc = ast 口径")
    lines.append("（剔 docstring 的非空非注释行，L3.4 count_loc.py 同款）；「0」= 该层全部在框架内部；")
    lines.append("「—」= 无装配函数（无框架可装配，成本全在自写列）；* 249 = 完成态核心五模块裸逻辑")
    lines.append("（milestone README 的 ast 口径——发货态 run() 是 TODO 桩，生成器不数桩）；轮数为各课")
    lines.append("讲义 ep.requests 实测静态数字，出处见生成器 COST_ROWS.turns_source。")
    return "\n".join(lines), missing


def render_static_table(title: str, data: dict[str, dict[str, str]], facets: tuple[str, ...]) -> str:
    """能力表 / 锁定性表（静态事实，每格带出处课次）——逐框架块状输出，一格一行。"""
    lines = [f"### {title}", ""]
    for framework in data:
        lines.append(f"[{framework}]")
        for facet in facets:
            fact = data[framework].get(facet, "—")
            lines.append(f"  {facet} : {fact}")
    return "\n".join(lines)


def render_data_page(root: Path) -> str:
    """产出整页数据（讲义 §3 Step1 贴的就是它）。"""
    cost, missing = render_cost_table(root)
    parts = [
        "== L3.8 决策表数据页（code/tablegen.py 生成；重新运行本命令即可复现每一格） ==",
        "",
        cost,
        "",
        render_static_table("能力表（事实，每格注出处课次）", CAPABILITY, CAPABILITY_FACETS),
        "",
        render_static_table("锁定性表（定性 + 证据，每格注出处课次）", LOCKIN, LOCKIN_FACETS),
        "",
        f"== 生成完毕：成本表 {len(COST_ROWS)} 行 / 能力表 {len(CAPABILITY)} 行 / 锁定性表 {len(LOCKIN)} 行；"
        f"missing 格：{'、'.join(dict.fromkeys(missing)) if missing else '无'} ==",
    ]
    return "\n".join(parts)


def main(argv: list[str]) -> int:
    root = Path(argv[1]).resolve() if len(argv) > 1 else find_repo_root(Path(__file__).resolve())
    print(render_data_page(root))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
