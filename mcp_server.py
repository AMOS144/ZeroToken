"""ZeroToken MCP Server - 入口点"""
import asyncio
import os
import time

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from zerotoken.repository.sqlite import (
    new_connection, SQLiteScriptRepo, SQLiteTrajectoryRepo,
    SQLiteSessionRepo, SQLiteRuntimeRepo, SQLiteFingerprintRepo, SQLiteBindingRepo,
)
from zerotoken.services import BrowserService, TrajectoryService, ScriptService
from zerotoken.benchmark import BenchmarkRecorder
from handlers.browser_handlers import browser_tools, handle_browser_tool
from handlers.trajectory_handlers import trajectory_tools, handle_trajectory_tool
from handlers.script_handlers import script_tools, handle_script_tool

server = Server("zerotoken")

_db_conn = None
_browser_svc = None
_trajectory_svc = None
_script_svc = None

_benchmark_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmarks")
_recorder = BenchmarkRecorder(output_dir=_benchmark_dir)


def init_services():
    global _db_conn, _browser_svc, _trajectory_svc, _script_svc
    if _db_conn is not None:
        return
    db_path = os.environ.get("ZEROTOKEN_DB") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "zerotoken.db"
    )
    _db_conn = new_connection(db_path)
    fp_repo = SQLiteFingerprintRepo(_db_conn)
    traj_repo = SQLiteTrajectoryRepo(_db_conn)
    _browser_svc = BrowserService(fingerprint_repo=fp_repo)
    _trajectory_svc = TrajectoryService(trajectory_repo=traj_repo)
    _script_svc = ScriptService(
        script_repo=SQLiteScriptRepo(_db_conn),
        trajectory_repo=traj_repo,
        session_repo=SQLiteSessionRepo(_db_conn),
        runtime_repo=SQLiteRuntimeRepo(_db_conn),
        binding_repo=SQLiteBindingRepo(_db_conn),
    )


def get_recorder() -> BenchmarkRecorder:
    """返回模块级 BenchmarkRecorder 实例"""
    return _recorder


@server.list_tools()
async def list_tools():
    return browser_tools() + trajectory_tools() + script_tools()


async def dispatch(name: str, arguments: dict):
    """工具分发（经 handler -> service -> pipeline 完整路径）"""
    if name.startswith("browser_"):
        return await handle_browser_tool(name, arguments, _browser_svc, _trajectory_svc)
    elif name.startswith("trajectory_"):
        return await handle_trajectory_tool(name, arguments, _trajectory_svc)
    else:
        return await handle_script_tool(name, arguments, _script_svc, browser_svc=_browser_svc)


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    init_services()
    start = time.monotonic()
    result = None
    error = None
    try:
        result = await dispatch(name, arguments)
        return result
    except Exception as e:
        error = e
        raise
    finally:
        duration_ms = (time.monotonic() - start) * 1000
        _recorder.record(name, arguments, result, duration_ms, error)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run(transport: str = "stdio"):
    """入口：支持 stdio 和 streamable-http 两种传输"""
    if transport == "streamable-http":
        from mcp_server_http import run as run_http
        run_http()
    else:
        asyncio.run(main())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ZeroToken MCP Server")
    parser.add_argument(
        "--transport", choices=["stdio", "streamable-http"],
        default=os.environ.get("ZEROTOKEN_MCP_TRANSPORT", "stdio"),
    )
    args = parser.parse_args()
    run(transport=args.transport)
