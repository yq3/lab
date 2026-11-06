"""主 agent 的 deepagents 全特性装配（demo 的特性展示重点）。

create_deep_agent 参数 → 特性映射：
- model                    端点中立工厂（shared.llm）
- system_prompt            入口路由与委派纪律
- tools                    本地工具 + A2A 委派工具（handoff-as-tool 跨进程版）
- middleware               TodoListMiddleware（write_todos，0.7.13 已移出默认栈，显式加回）
- subagents                in-process 声明式 subagent（资料整理员），与 A2A 远端对照
- skills                   SkillsMiddleware 懒加载技能（SKILL.md 目录）
- memory                   MemoryMiddleware（AGENTS.md 启动载入）
- backend                  CompositeBackend：workspace 真实文件 + /memories/ 长期记忆
- permissions              FilesystemPermission：技能目录防篡改（deny 写）
- interrupt_on             HITL：委派申报（跨系统写操作）前人工审批
- state_schema             业务状态扩展（last_tax_result）
- context_schema           企业会话上下文（操作员/在办纳税人）
- checkpointer             MemorySaver（interrupt 恢复必需）
- store                    InMemoryStore（/memories/ 路由的落点）

SummarizationMiddleware / PatchToolCallsMiddleware 为内置默认栈，无需显式配置。
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StoreBackend
from deepagents.middleware.filesystem import FilesystemPermission
from deepagents.middleware.subagents import SubAgent
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from shared.a2a_adapter import build_delegate_tools
from shared.config import AGENT_REGISTRY
from shared.llm import build_chat_model
from tax_main.state import TaxContext, TaxMainState
from tax_main.tools import MAIN_TOOLS

# backend root = 本包目录：skills/、memory/ 相对它解析；workspace/ 是 agent 工作区
TAX_MAIN_ROOT = str(Path(__file__).resolve().parent)

SYSTEM_PROMPT = """你是企业税务系统的总入口 agent「计税申报助手」，面向企业税务专员，负责理解意图、路由任务、汇总结果。

## 路由规则
- 计税、扣除校验、税率问题 → delegate_to_tax_calc（跨团队远端服务，A2A 协议）
- 申报表生成/校验/提交/回执/申报状态 → delegate_to_tax_filing（跨团队远端服务；提交申报是高风险操作，会触发人工审批）
- 「帮我整理 XX 的申报资料」类请求 → task 工具委派同进程的 material-organizer（资料整理员）
- 档案速览、操作员确认、计税结论存档 → 本地工具

## 委派纪律（跨团队调用的硬规矩）
1. 远端 agent 是无状态首触的：一次委派必须给全所需信息（纳税人编号、年度、计税数据、要求），不要指望对方记住上一次。
2. delegate_to_tax_calc 返回结论后，立即用 save_calc_result 存档；委派申报时把存档的完整计税数据传给对方。
3. 收到 [INPUT_REQUIRED] 开头的委派结果：远端在等补充信息——向用户转达缺失清单，收集齐后重新完整委派，不要编造缺失材料。
4. 收到 [DELEGATE_*] 开头的结果：远端异常，如实向用户说明，不要重试超过一次。

## 申报提交红线
- 只允许在用户明确要求"提交申报"且计税结论已确认后才委派申报（人工审批是系统强制的，不要绕过）。
- 用户否决审批后，记录用户顾虑并汇报，不要换措辞重试。

## 其他
- 沟通用中文，金额一律整数元；涉及税额计算口径的问题一律以计税 agent 的结论为准，不自行心算。
- 工作区文件放 workspace/ 下；长期记忆放 /memories/ 下（跨会话可见）。"""


# in-process 声明式 subagent（SubAgentMiddleware 的 task 工具调用）。
# 最小权限示范：显式收窄 tools 为本地档案查询 + 内置文件工具，
# **不继承**主 agent 的 A2A 委派工具（避免 subagent 再跨进程委派）。
MATERIAL_ORGANIZER_SUBAGENT = {
    "name": "material-organizer",
    "description": (
        "资料整理员（本进程 subagent）：读取纳税人档案，整理申报资料清单并写入工作区文件。"
        "适用于「帮我整理 XX 的申报资料」「生成资料核对清单」类请求。"
    ),
    "system_prompt": (
        "你是资料整理员。用 lookup_taxpayer_profile 读取档案，把收入构成、扣除项（标注材料是否齐全）、"
        "已预缴税额整理成一份 Markdown 清单，写入 workspace/ 下的文件并返回文件路径与要点摘要。"
        "金额整数元。材料缺失项要醒目标注（申报前需补办）。"
    ),
    "tools": [MAIN_TOOLS[1]],  # lookup_taxpayer_profile（显式收窄权限）
}

# FilesystemPermission 演示：技能目录只读（防 prompt 注入篡改技能内容）。
# deepagents 内置规则：未匹配的路径默认放行；首条命中生效。
SKILL_DIR_READONLY = FilesystemPermission(
    operations=["write"],
    paths=["/skills/**"],
    mode="deny",
)


def build_backend() -> CompositeBackend:
    """主 agent 存储后端：workspace 走真实磁盘，/memories/ 走 Store 长期记忆。

    demo 里 Store 用 InMemoryStore（进程生命周期）；生产换 PostgresStore，
    只改这里（README「演进点」）。
    """
    return CompositeBackend(
        default=FilesystemBackend(root_dir=TAX_MAIN_ROOT, virtual_mode=True),
        routes={"/memories/": StoreBackend(namespace=lambda _rt: ("tax_main_memories",))},
    )


def build_tools() -> list[BaseTool]:
    """本地工具 + 按注册表生成的 A2A 委派工具。"""
    return [*MAIN_TOOLS, *build_delegate_tools(AGENT_REGISTRY)]


def build_graph(model: BaseChatModel | None = None):
    """构建主 agent 图。model 可注入 fake（测试零 key 用）。"""
    return create_deep_agent(
        name="tax_main_agent",
        model=model or build_chat_model(),
        system_prompt=SYSTEM_PROMPT,
        tools=build_tools(),
        middleware=[TodoListMiddleware()],  # write_todos：0.7.13 起移出默认栈，显式装配
        subagents=[cast("SubAgent", MATERIAL_ORGANIZER_SUBAGENT)],
        skills=["skills/"],  # 相对 backend root
        memory=["memory/AGENTS.md"],  # 相对 backend root，启动时载入 system prompt
        backend=build_backend(),
        permissions=[SKILL_DIR_READONLY],
        interrupt_on={"delegate_to_tax_filing": {"allowed_decisions": ["approve", "reject"]}},
        state_schema=TaxMainState,
        context_schema=TaxContext,
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )
