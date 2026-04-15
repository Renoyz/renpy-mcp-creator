"""Standalone CLI entry point for the Ren'Py Web UI.

Usage:
    renpy-webui --project /path/to/my-game
    renpy-webui -p /path/to/my-game --page /story-map --port 8080
"""

import argparse
import os
import sys
import webbrowser
from http.server import HTTPServer
from pathlib import Path

from ..config import RenPyConfig
from .server import _find_free_port, _make_handler


def main():
    parser = argparse.ArgumentParser(
        prog="renpy-webui",
        description="Launch the Ren'Py visual development dashboard in your browser.",
    )
    parser.add_argument(
        "--project", "-p",
        required=True,
        help="Path to the Ren'Py project directory (containing game/)",
    )
    parser.add_argument(
        "--sdk",
        default=os.environ.get("RENPY_SDK_PATH", ""),
        help="Path to Ren'Py SDK (default: $RENPY_SDK_PATH)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port to listen on (default: auto-select free port)",
    )
    parser.add_argument(
        "--page",
        default="/dashboard",
        choices=["/dashboard", "/story-map", "/script-editor", "/heatmap", "/assets"],
        help="Page to open (default: /dashboard)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't auto-open browser",
    )
    args = parser.parse_args()

    # Validate project path
    project_path = Path(args.project).resolve()
    if not (project_path / "game").is_dir():
        print(f"Error: {project_path} does not contain a game/ directory.", file=sys.stderr)
        sys.exit(1)

    # Build config
    sdk_path = Path(args.sdk) if args.sdk else Path(".")
    config = RenPyConfig(sdk_path=sdk_path, project_path=project_path)

    # Start server
    port = args.port if args.port else _find_free_port()
    handler = _make_handler(config)
    server = HTTPServer(("127.0.0.1", port), handler)

    url = f"http://127.0.0.1:{port}{args.page}"
    print(f"Ren'Py Web UI running at: http://127.0.0.1:{port}")
    print(f"Opening: {url}")
    print("Press Ctrl+C to stop.")

    if not args.no_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
