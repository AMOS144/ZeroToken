"""ZeroToken MCP Server - 入口点"""
import asyncio
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from zerotoken.repository.sqlite import (
    new_connection, SQLiteScriptRepo, SQLiteTrajectoryRepo,
    SQLiteSessionRepo, SQLiteRuntimeRepo, SQLiteFingerprintRepo, SQLiteBindingRepo,
)
from zerotoken.services import BrowserService, TrajectoryService, ScriptService
from handlers.browser_handlers import browser_tools, handle_browser_tool
from handlers.trajectory_handlers import trajectory_tools, handle_trajectory_tool
from handlers.script_handlers import script_tools, handle_script_tool

server = Server("zerotoken")

_db_conn = None
_browser_svc = None
_trajectory_svc = None
_script_svc = None


def _init_services():
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


@server.list_tools()
async def list_tools():
    return browser_tools() + trajectory_tools() + script_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    _init_services()
    if name.startswith("browser_"):
        return await handle_browser_tool(name, arguments, _browser_svc, _trajectory_svc)
    elif name.startswith("trajectory_"):
        return await handle_trajectory_tool(name, arguments, _trajectory_svc)
    else:
        return await handle_script_tool(name, arguments, _script_svc)


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
