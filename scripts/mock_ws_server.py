#!/usr/bin/env python3
"""Mock WebSocket server for deterministic dashboard E2E tests."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import websockets


WORKSPACE = Path(os.environ.get("RENPY_MCP_WORKSPACE", Path.home() / ".renpy-mcp" / "workspace"))
HOST = os.environ.get("MOCK_WS_HOST", "127.0.0.1")
PORT = int(os.environ.get("MOCK_WS_PORT", "8765"))


def _write_mock_background(project_name: str) -> str:
    project_dir = WORKSPACE / project_name
    output_dir = project_dir / "game" / "images" / "background"
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / "mock_courtyard.png"
    image_path.write_bytes(b"mock background data")
    return image_path.relative_to(project_dir).as_posix()


async def handler(websocket) -> None:
    pending: dict[str, str] | None = None
    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue

            msg_type = data.get("type")

            if msg_type == "user_message":
                project_name = data.get("project_name")
                if not project_name:
                    await websocket.send(
                        json.dumps({"type": "error", "message": "No active project selected."})
                    )
                    continue

                pending = {"project_name": project_name}
                await websocket.send(
                    json.dumps(
                        {
                            "type": "awaiting_confirmation",
                            "confirmation_id": "mock_conf_background",
                            "message": "Mock background ready to save.",
                            "candidates": [
                                {
                                    "type": "image",
                                    "path": f"game/images/background/{project_name}_preview.png",
                                }
                            ],
                            "project_name": project_name,
                        }
                    )
                )

            elif msg_type == "confirmation_response":
                approved = bool(data.get("approved"))
                if not pending:
                    await websocket.send(
                        json.dumps({"type": "error", "message": "No pending confirmation."})
                    )
                    continue

                project_name = pending["project_name"]
                if not approved:
                    await websocket.send(
                        json.dumps({"type": "assistant_delta", "delta": "Mock generation cancelled."})
                    )
                    pending = None
                    continue

                relative_path = _write_mock_background(project_name)
                from urllib.parse import quote
                preview_url = f"/api/projects/{quote(project_name, safe='')}/asset-file/{quote(relative_path.replace('game/', ''), safe='/')}"
                await websocket.send(
                    json.dumps({"type": "tool_start", "tool_name": "generate_background"})
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "tool_result",
                            "result": {
                                "success": True,
                                "content": json.dumps(
                                    {
                                        "success": True,
                                        "project": project_name,
                                        "image_type": "background",
                                        "relative_files": [relative_path],
                                        "preview_urls": [preview_url],
                                        "primary_preview_url": preview_url,
                                        "suggested_image_names": ["mock courtyard"],
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    )
                )
                pending = None

            else:
                await websocket.send(
                    json.dumps({"type": "error", "message": f"Unknown message type: {msg_type}"})
                )
    except websockets.exceptions.ConnectionClosed:
        return


async def main() -> None:
    print(f"Starting mock WS server on ws://{HOST}:{PORT}", flush=True)
    async with websockets.serve(handler, HOST, PORT):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
