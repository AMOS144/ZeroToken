"""
ZeroToken MCP Server - Streamable HTTP transport.
Runs the same MCP server as stdio mode but over HTTP for OpenClaw/MCPorter.
Service stays resident so browser state is preserved across tool calls.
"""

import asyncio
import contextlib
import os

from starlette.applications import Starlette
from starlette.routing import Route

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from mcp_server import server


class _StreamableHTTPASGIApp:
    """ASGI app that delegates to StreamableHTTPSessionManager."""

    def __init__(self, session_manager: StreamableHTTPSessionManager):
        self.session_manager = session_manager

    async def __call__(self, scope, receive, send):
        await self.session_manager.handle_request(scope, receive, send)


def _create_app() -> Starlette:
    """Create Starlette app with Streamable HTTP MCP endpoint."""
    session_manager = StreamableHTTPSessionManager(
        app=server,
        event_store=None,
        json_response=True,
        stateless=False,
        security_settings=None,
        retry_interval=None,
    )
    mcp_app = _StreamableHTTPASGIApp(session_manager)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        async with session_manager.run():
            yield

    return Starlette(
        routes=[
            Route("/mcp", endpoint=mcp_app, methods=["GET", "POST", "DELETE"]),
        ],
        lifespan=lifespan,
    )


def run(host: str | None = None, port: int | None = None):
    """Entry point for zerotoken-mcp-http console script."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="ZeroToken MCP over Streamable HTTP")
    parser.add_argument("--host", default=None, help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="Port (default: 8000)")
    args, _ = parser.parse_known_args(sys.argv[1:])
    host = host or args.host or os.environ.get("ZEROTOKEN_HTTP_HOST", "0.0.0.0")
    port = port or args.port or int(os.environ.get("ZEROTOKEN_HTTP_PORT", "8000"))

    app = _create_app()

    async def serve():
        import uvicorn

        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
        )
        server_instance = uvicorn.Server(config)
        await server_instance.serve()

    asyncio.run(serve())


if __name__ == "__main__":
    run()
