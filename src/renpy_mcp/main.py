"""Unified entry point for RenPy MCP Server.

Supports:
  - stdio mode (for Claude Desktop / Cursor)
  - http mode (standalone FastAPI server)
"""

import argparse
import asyncio
import os
import threading
import webbrowser
from pathlib import Path

import uvicorn

from .config import RenPyConfig, get_settings
from .server import mcp
from .web.fastapi_app import create_app, set_config
from .web.server import _find_free_port


def _start_uvicorn_in_thread(app, host: str, port: int):
    """Start uvicorn in a background daemon thread."""
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server


async def run_stdio():
    """Run MCP over stdio, with embedded FastAPI for Dashboard."""
    settings = get_settings()
    config = RenPyConfig(
        sdk_path=settings.renpy_sdk_path or Path("."),
    )

    port = settings.port if settings.port else _find_free_port()
    set_config(config)
    app = create_app()
    _start_uvicorn_in_thread(app, "127.0.0.1", port)

    dashboard_url = f"http://127.0.0.1:{port}/dashboard"
    print(f"[RenPy MCP] Dashboard available at: {dashboard_url}", flush=True)

    await mcp.run_stdio_async()


async def run_http(host: str, port: int, open_browser: bool = True):
    """Run as a standalone HTTP server."""
    settings = get_settings()
    config = RenPyConfig(
        sdk_path=settings.renpy_sdk_path or Path("."),
    )

    set_config(config)
    app = create_app()

    url = f"http://{host}:{port}/dashboard"
    print(f"[RenPy MCP] HTTP server running at: http://{host}:{port}")
    print(f"[RenPy MCP] Opening: {url}")

    if open_browser:
        webbrowser.open(url)

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def main():
    parser = argparse.ArgumentParser(
        prog="renpy-mcp",
        description="Ren'Py MCP Unified Server",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP bind address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="HTTP port (default: auto for stdio, 8080 for http)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open browser in http mode",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        asyncio.run(run_stdio())
    else:
        port = args.port if args.port else 8080
        asyncio.run(run_http(args.host, port, open_browser=not args.no_browser))


if __name__ == "__main__":
    main()
