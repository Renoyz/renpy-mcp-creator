#!/usr/bin/env python3
"""Mock WebSocket server for testing Chat Drawer without real backend."""

import asyncio
import json
import sys

import websockets


async def handler(websocket):
    print(f"Client connected: {websocket.remote_address}")
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                continue

            if data.get("type") == "user_message":
                content = data.get("content", "")

                # Simulate assistant thinking
                await websocket.send(
                    json.dumps(
                        {
                            "type": "assistant_delta",
                            "delta": f"收到你的消息：{content}\n正在调用工具...",
                        }
                    )
                )

                await asyncio.sleep(0.5)

                # Simulate tool_start
                await websocket.send(
                    json.dumps(
                        {
                            "type": "tool_start",
                            "tool_name": "echo",
                        }
                    )
                )

                await asyncio.sleep(0.5)

                # Simulate tool_result
                await websocket.send(
                    json.dumps(
                        {
                            "type": "tool_result",
                            "result": {"content": f"Echo: {content}"},
                        }
                    )
                )

                await asyncio.sleep(0.3)

                # Final assistant message
                await websocket.send(
                    json.dumps(
                        {
                            "type": "assistant_delta",
                            "delta": "工具执行完成。",
                        }
                    )
                )
    except websockets.exceptions.ConnectionClosed:
        print(f"Client disconnected: {websocket.remote_address}")


async def main():
    host = "localhost"
    port = 8765
    print(f"Starting mock WS server on ws://{host}:{port}")
    async with websockets.serve(handler, host, port):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down.")
        sys.exit(0)
