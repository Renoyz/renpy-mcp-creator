"""End-to-end test: Dashboard WebSocket chat -> generate -> build."""

import asyncio
import json
import sys

import websockets

WS_URL = "ws://localhost:8080/ws/chat"
RECV_TIMEOUT = 300  # seconds: LLM may take a while


async def run_e2e():
    print("Connecting to WebSocket...", WS_URL)
    async with websockets.connect(
        WS_URL,
        ping_interval=None,  # disable keepalive to survive long LLM turns
        ping_timeout=None,
        open_timeout=30,
        close_timeout=10,
    ) as ws:
        print("Connected.\n")

        user_prompt = (
            "Create a visual novel project named websocket_e2e_test, "
            "generate a background of a Japanese courtyard with cherry blossoms, "
            "anime soft pastel style, then build the web version"
        )

        await ws.send(json.dumps({"type": "user_message", "content": user_prompt}))
        print(f"Sent: {user_prompt}\n")

        confirmation_count = 0
        max_confirmations = 10
        last_confirmation_id = None

        while confirmation_count < max_confirmations:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT)
            except asyncio.TimeoutError:
                print("\n[ERROR] Timeout waiting for server message")
                return 1

            if not raw:
                print("\n[WARN] Empty message received")
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                print(f"\n[WARN] Non-JSON message: {raw[:200]}")
                continue

            msg_type = msg.get("type")

            if msg_type == "assistant_delta":
                print(msg.get("delta", ""), end="", flush=True)

            elif msg_type == "tool_start":
                print(f"\n[TOOL START] {msg.get('tool_name')}")

            elif msg_type == "tool_result":
                result = msg.get("result", {})
                success = result.get("success", False)
                content = str(result.get("content", ""))[:300]
                print(f"\n[TOOL RESULT] success={success} -> {content}")

            elif msg_type == "awaiting_confirmation":
                last_confirmation_id = msg.get("confirmation_id")
                print(
                    f"\n[CONFIRMATION REQUIRED] id={last_confirmation_id} "
                    f"msg={msg.get('message', '')[:100]}"
                )
                await ws.send(
                    json.dumps(
                        {
                            "type": "confirmation_response",
                            "confirmation_id": last_confirmation_id,
                            "approved": True,
                        }
                    )
                )
                print(f"[APPROVED] {last_confirmation_id}")
                confirmation_count += 1

            elif msg_type == "error":
                print(f"\n[ERROR] {msg.get('message')}")
                return 1

            else:
                print(f"\n[WARN] Unknown message type: {msg_type} | {msg}")

        # After handling confirmations, wait a bit and verify build output
        await asyncio.sleep(2)

        import httpx
        from pathlib import Path

        status_resp = httpx.get("http://localhost:8080/api/status")
        print(f"\n\nAPI status: {status_resp.status_code} {status_resp.text}")

        build_dir = (
            Path.home()
            / ".renpy-mcp"
            / "workspace"
            / "websocket_e2e_test-dists"
            / "websocket_e2e_test-web"
        )
        if build_dir.exists() and (build_dir / "index.html").exists():
            print(f"\n[PASS] Build output verified at {build_dir}")
            return 0
        else:
            print(f"\n[FAIL] Build output not found at {build_dir}")
            return 1


if __name__ == "__main__":
    code = asyncio.run(run_e2e())
    sys.exit(code)
