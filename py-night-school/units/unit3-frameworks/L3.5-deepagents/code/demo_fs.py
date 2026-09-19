"""Step 2 讲义演示：虚拟文件系统——state["files"] 是 harness 的工作台。

三件事：
  A. 同题 demo 的底稿落盘：write_file 内置工具把审查底稿写进 state["files"]；
  B. FileData 的真实形态（content/encoding/时间戳）——它不是磁盘文件，是 state 的一个 channel；
  C. invoke 预置文件 + ls：agent 能「看见」我们塞进去的文件（run 前 files= 进去，
     run 后从 result 拿回来——同一条 channel，进出同门）。

源码对应：deepagents/backends/state.py 的 StateBackend 用 langgraph 的
channel 读写（CONFIG_KEY_READ / CONFIG_KEY_SEND）实现 _read_files/_send_files_update；
FilesystemState（middleware/filesystem.py）声明 files 字段。

用法：uv run python code/demo_fs.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deepagents import create_deep_agent  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import SecretStr  # noqa: E402

import demo  # noqa: E402
from mock_endpoint import MockLLMEndpoint  # noqa: E402


def part_a_b() -> None:
    print("== A. 同题 demo：write_file 落盘 ==")
    _, trace = asyncio.run(demo.run_review_with_trace("CLM-2026-0001"))
    state = trace["state"]
    print("最终 state 键:", sorted(state.keys()))
    print("\n== B. FileData 的真实形态 ==")
    for path, data in state["files"].items():
        print(f"  {path}:")
        print(f"    content 前 60 字: {data['content'][:60]!r}")
        print(f"    encoding: {data.get('encoding')}, created_at: {data.get('created_at', '')[:19]}")


async def part_c() -> None:
    print("\n== C. invoke 预置文件 + ls 取证 ==")
    with MockLLMEndpoint() as ep:
        model = ChatOpenAI(base_url=ep.url, api_key=SecretStr(ep.api_key), model=ep.model)
        agent = create_deep_agent(model=model)  # 零自定义工具：纯 harness 内置工具
        ep.script_tool_calls([{"id": "call_ls", "name": "ls", "arguments": {"path": "/review/"}}])
        ep.script_text("已列出 /review/ 目录。")
        result = await agent.ainvoke(
            demo.input_with_files(
                "列出 /review/ 目录",
                {  # run 前预置：StateBackend 把 files 当普通输入 channel
                    "/review/README.md": {"content": "# 人审清单目录\n审查底稿按单号归档。"},
                    "/review/CLM-2026-0001.md": {"content": "# 审查底稿 CLM-2026-0001\n…"},
                },
            )
        )
        from langchain_core.messages import ToolMessage  # noqa: PLC0415

        ls_result = next(m for m in result["messages"] if isinstance(m, ToolMessage) and m.tool_call_id == "call_ls")
        print("ls 工具回喂（模型看到的目录列表）:")
        for line in str(ls_result.content).splitlines():
            print("   ", line)
        print("run 结束后从 result 拿回同一份 files:", sorted(result["files"].keys()))
        print("磁盘上并没有这些文件——它们只活在 graph state 里（StateBackend 的 docstring：ephemeral）")


if __name__ == "__main__":
    part_a_b()
    asyncio.run(part_c())
