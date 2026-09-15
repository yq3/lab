"""实验③：stdout 串台坑实测（§5 坑位的取证台）。

stdio 传输上 stdout 是 JSON-RPC 协议通道——server 进程里任何 print 到 stdout 的字节
都是垃圾帧。本演示实测两种最常见的污染：启动日志与工具内调试日志。

实测结论（2026-09，mcp SDK 2.2.0）：client 对垃圾帧「跳过并报错」——
你会看到 Failed to parse JSONRPC message 噪声刷屏，但调用侥幸没断。
这不是协议的许可，是 client 的宽容：垃圾帧若赶上握手期/通知帧，或对端换一个
更严格的 client 实现（IDE、别的 SDK 版本），会话直接打崩。
纪律不变：server 进程里一切日志走 stderr（print(..., file=sys.stderr) 或 logging）。
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

HERE = Path(__file__).resolve().parent
POLLUTED_SERVER = HERE / "_polluted_server.py"
CLEAN_SERVER = HERE / "finance_server.py"


async def try_call_tool(server_path: Path, label: str) -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(server_path)])
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=5.0)
                result = await asyncio.wait_for(
                    session.call_tool("preapprove", arguments={"items_cents": [1200]}), timeout=5.0
                )
                assert isinstance(result, CallToolResult)
                text = next(part.text for part in result.content if isinstance(part, TextContent))
                print(f"[{label}] 调用成功: {text}（侥幸——看上面/下面的解析错误噪声）")
    except Exception as exc:  # noqa: BLE001 —— 演示脚本：任何失败都要活着报告
        print(f"[{label}] 会话失败: {type(exc).__name__}: {str(exc)[:80]}")


def write_polluted_server() -> None:
    POLLUTED_SERVER.write_text(
        textwrap.dedent(
            """
            from mcp.server.mcpserver import MCPServer

            print("server starting up...", flush=True)  # 污染①：启动日志（最常见的好心 print）

            server = MCPServer("polluted")

            @server.tool()
            def preapprove(items_cents: list[int]) -> str:
                \"\"\"预审。\"\"\"
                print(f"调试: 收到 {items_cents}", flush=True)  # 污染②：工具内调试日志
                return "PASS"

            if __name__ == "__main__":
                server.run("stdio")
            """
        ).lstrip(),
        encoding="utf-8",
    )


def main() -> None:
    write_polluted_server()
    try:
        print("== 对照组：干净的 server ==")
        asyncio.run(try_call_tool(CLEAN_SERVER, "干净"))
        print("== 实验组：启动日志 + 工具调试日志都打到 stdout 的 server ==")
        asyncio.run(try_call_tool(POLLUTED_SERVER, "污染"))
        print("结论：client 日志里出现 Failed to parse JSONRPC message —— 垃圾帧进了协议通道。")
        print("本版 client 跳过坏行侥幸存活；换严格实现或赶上握手期就是会话崩溃。")
        print("修复：server 里一切日志 print(..., file=sys.stderr)，或用 logging（默认 stderr）。")
    finally:
        POLLUTED_SERVER.unlink(missing_ok=True)  # 临时文件用完即弃


if __name__ == "__main__":
    main()
