"""Step 2：FunctionTool 的 declaration 自动生成——对照 L2.2 手写 JSON Schema。

L2.2 我们用 Pydantic 模型手搓工具 schema（model_json_schema → 注册表）；
adk 的 FunctionTool 走另一条路：**从函数自己身上长出 schema**——
  名字   ← 函数名；
  描述   ← docstring；
  参数   ← 签名 + docstring 的 Args 段（类型注解 → JSON Schema 类型；无默认值 → required；
         连 schema 里的 title "check_budgetParams" 都是框架内部 create_model 的痕迹）。
工具作者只维护一份 Python 代码，schema 与实现不会漂移——Java 人可以理解为
「注解处理器在运行时替你生成了接口描述」，只是信息源是 docstring 而不是注解。

运行：uv run python code/demo_schema.py
"""

from __future__ import annotations

import asyncio
import json
import warnings

from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext

import mock_tools
import review_rules
from adk_review import ask, build_reviewer, build_runner, new_session
from mock_endpoint import MockLLMEndpoint

warnings.filterwarnings(  # adk 2.9.0 的新 schema 特性公告（实验特性提示，与本课无关）
    "ignore", message=".*JSON_SCHEMA_FOR_FUNC_DECL.*", category=UserWarning
)


def check_budget_stateful(dept: str, tool_context: ToolContext) -> dict:
    """查预算余额：返回部门的预算 / 已花 / 剩余，单位都是分。

    Args:
        dept: 部门码，如 SALES / DEV
        tool_context: 框架注入的会话上下文（不会出现在 declaration 里）
    """
    return mock_tools.check_budget(dept)


def main() -> None:
    print("== FunctionTool 自动生成的 declaration ==")
    for tool_src in (mock_tools.check_budget, check_budget_stateful):
        tool = FunctionTool(func=tool_src)
        # _get_declaration 是框架装配请求时自己调用的方法（前缀下划线≈Java 包私有）
        decl = tool._get_declaration()
        assert decl is not None
        print(f"\n-- {decl.name} --")
        print(f"description: {decl.description}")
        print(f"parameters_json_schema: {json.dumps(decl.parameters_json_schema, ensure_ascii=False)}")
    print()
    print("注意两点：check_budget_stateful 的 ToolContext 参数被自动剔除——")
    print("模型永远看不见框架上下文参数；parameters_json_schema 用的就是 L2.2 教的")
    print("JSON Schema 方言（title 里的 check_budgetParams 是框架内部 create_model 的痕迹）。")


async def wire_proof() -> None:
    print()
    print("== 出网取证：declaration 到了 litellm 请求里长什么样 ==")
    first_turn, final_json, _expected = review_rules.script_for("CLM-2026-0001")
    with MockLLMEndpoint() as ep:
        ep.script_tool_calls(first_turn)
        ep.script_text(final_json)
        runner = build_runner(build_reviewer(ep))
        session_id = await new_session(runner)
        async for _event in ask(runner, session_id, "请审查报销单 CLM-2026-0001"):
            pass
        print(json.dumps(ep.requests[0]["tools"][0], ensure_ascii=False, indent=1))
    print("OpenAI function 工具格式：name / description / parameters——与 L2.2 手写版同构，")
    print("只是这一版是框架从签名+docstring 生成的，你抄都不会抄错。")


if __name__ == "__main__":
    main()
    asyncio.run(wire_proof())
