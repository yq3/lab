"""申报 agent 的 deepagents 装配。

本 agent 展示的 deepagents 特性：
- backend=FilesystemBackend：申报表草稿落盘真实磁盘（agent 内置 read_file 可直接
  复核业务工具生成的草稿，与业务工具共享同一 workspace 目录）
- checkpointer=MemorySaver：同一线程内中断/续跑
- 内置文件工具与业务工具协同（generate 落盘 → read_file 复核 → submit）
"""

from __future__ import annotations

from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph

from shared.a2a_adapter.server import NEED_INPUT_PREFIX
from shared.llm import build_chat_model
from tax_filing.tools import FILING_TOOLS

# FilesystemBackend root：agent 的虚拟文件系统根 = 本包 workspace 目录
WORKSPACE_ROOT = str(Path(__file__).resolve().parent / "workspace")

SYSTEM_PROMPT = f"""你是企业税务系统的申报 agent（申报报送团队维护），只负责申报表生成/校验/提交，不做计税。

标准工作流（write_todos 规划多步任务）：
1. generate_return_draft：依据主 agent 转来的计税结论生成申报表草稿（JSON 落盘）。
2. read_file 复核草稿内容（不复核直接提交属于违规）。
3. validate_return_draft：勾稽校验 + 材料校验。
4. 校验通过后才能 submit_return（幂等键用 "taxpayer_id-year" 格式，如 T2025-001-2025）。
5. 提交成功后向调用方回报回执号；可按需 query_submission_status 确认受理状态。

材料缺失约定：
- validate_return_draft 返回 missing_evidence 非空时，禁止提交，最终回复必须以
  {NEED_INPUT_PREFIX} 开头，后接缺失材料清单与补办说明（系统会把任务置为"等待补充信息"，
  调用方会向用户转达；材料补齐后调用方会重新委派完整任务）。
- 勾稽错误（errors 非空）时不要提交：修正参数重新生成草稿再校验。

其他规范：
- 金额一律整数元；受理记录在内存中，server 重启即清空（demo 设定）。
- 回复要简洁：回执号、状态、下一步建议。"""


def build_graph(model: BaseChatModel | None = None) -> CompiledStateGraph:
    """构建申报 agent 图；model 可注入（契约测试用 fake）。"""
    return create_deep_agent(
        name="tax_filing_agent",
        model=model or build_chat_model(),
        system_prompt=SYSTEM_PROMPT,
        tools=FILING_TOOLS,
        backend=FilesystemBackend(root_dir=WORKSPACE_ROOT, virtual_mode=True),
        checkpointer=MemorySaver(),
    )
