"""Full E2E: start local server in-thread, then WebSocket chat -> generate -> build."""

import asyncio
import json
import sys
import threading
import time

import httpx
import uvicorn
import websockets

from renpy_mcp.web.fastapi_app import create_app


def _start_server(host: str = "127.0.0.1", port: int = 8080):
    app = create_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    return server, t


async def wait_for_server(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return False


async def run_e2e():
    server, t = _start_server("127.0.0.1", 8080)
    ok = await wait_for_server("http://127.0.0.1:8080/api/status")
    if not ok:
        print("[FAIL] Server did not start")
        return 1
    print("[PASS] Server is up\n")

    ws_url = "ws://127.0.0.1:8080/ws/chat"
    async with websockets.connect(
        ws_url,
        ping_interval=None,
        ping_timeout=None,
        open_timeout=30,
        close_timeout=10,
    ) as ws:
        print(f"[PASS] WebSocket connected to {ws_url}\n")

        user_prompt = (
            "Create a visual novel project named websocket_e2e_test, "
            "generate a background of a Japanese courtyard with cherry blossoms, "
            "anime soft pastel style, then build the web version"
        )

        await ws.send(json.dumps({"type": "user_message", "content": user_prompt}))
        print(f"Sent: {user_prompt}\n")

        confirmation_count = 0
        max_confirmations = 10
        turn_started = time.time()

        while confirmation_count < max_confirmations:
            # Overall turn guard: if nothing for 180s, bail
            if time.time() - turn_started > 300:
                print("\n[ERROR] Overall turn timeout")
                return 1

            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=120.0)
            except asyncio.TimeoutError:
                print("\n[ERROR] Timeout waiting for server message")
                return 1

            if not raw:
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                print(f"\n[WARN] Non-JSON: {raw[:200]}")
                continue

            msg_type = msg.get("type")

            if msg_type == "assistant_delta":
                print(msg.get("delta", ""), end="", flush=True)

            elif msg_type == "tool_start":
                print(f"\n[TOOL START] {msg.get('tool_name')}")

            elif msg_type == "tool_result":
                result = msg.get("result", {})
                print(
                    f"\n[TOOL RESULT] success={result.get('success')} -> "
                    f"{str(result.get('content', ''))[:200]}"
                )

            elif msg_type == "awaiting_confirmation":
                cid = msg.get("confirmation_id")
                print(
                    f"\n[CONFIRMATION REQUIRED] id={cid} "
                    f"msg={msg.get('message', '')[:80]}"
                )
                await ws.send(
                    json.dumps(
                        {
                            "type": "confirmation_response",
                            "confirmation_id": cid,
                            "approved": True,
                        }
                    )
                )
                print(f"[APPROVED] {cid}")
                confirmation_count += 1

            elif msg_type == "error":
                print(f"\n[ERROR] {msg.get('message')}")
                return 1

            else:
                print(f"\n[INFO] msg_type={msg_type}")

        await asyncio.sleep(2)

    # Verify build output
    from pathlib import Path

    build_dir = (
        Path.home()
        / ".renpy-mcp"
        / "workspace"
        / "websocket_e2e_test-dists"
        / "websocket_e2e_test-web"
    )
    if build_dir.exists() and (build_dir / "index.html").exists():
        print(f"\n\n[PASS] Build output verified at {build_dir}")
        return 0
    else:
        print(f"\n\n[FAIL] Build output not found at {build_dir}")
        return 1


if __name__ == "__main__":
    code = asyncio.run(run_e2e())
    sys.exit(code)
