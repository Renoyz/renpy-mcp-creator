#!/usr/bin/env python3
"""
Smoke test for Kimi Code (Anthropic-compatible) tool_use support.

Exit codes:
    0 - All checks passed, tool_use is fully supported.
    1 - Critical failure (connection/auth/format error or no tool_use).
    2 - Partial failure (tool_use works but tool_result follow-up fails).

Environment variables:
    ANTHROPIC_API_KEY  - Required. Kimi Code API key.
    ANTHROPIC_BASE_URL - Optional. Default: https://api.kimi.com/coding/
    KIMI_MODEL         - Optional. Default: claude-3-5-sonnet
"""

import json
import os
import sys
import traceback

from anthropic import Anthropic, APIError, AuthenticationError

def log_step(step: str, ok: bool, detail: str = ""):
    icon = "[PASS]" if ok else "[FAIL]"
    print(f"{icon} {step}")
    if detail:
        print(f"   -> {detail}")


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.kimi.com/coding/")
    model = os.environ.get("KIMI_MODEL", "claude-3-5-sonnet")

    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable is not set.")
        return 1

    print(f"Base URL: {base_url}")
    print(f"Model:    {model}")
    print("-" * 60)

    client = Anthropic(api_key=api_key, base_url=base_url)

    tools = [
        {
            "name": "add_numbers",
            "description": "Add two integers and return the sum.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer", "description": "First number"},
                    "b": {"type": "integer", "description": "Second number"},
                },
                "required": ["a", "b"],
            },
        }
    ]

    system_prompt = (
        "You are a helpful assistant. When the user asks you to perform a calculation, "
        "you MUST use the provided tool. Do not calculate in your head."
    )

    messages = [
        {
            "role": "user",
            "content": "请计算 13 + 29 等于多少，必须使用 add_numbers 工具计算。",
        }
    ]

    # ------------------------------------------------------------------
    # Step 1: First call – expect tool_use
    # ------------------------------------------------------------------
    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )
    except AuthenticationError as exc:
        log_step("Authentication", False, str(exc))
        return 1
    except APIError as exc:
        log_step("API call failed", False, f"{type(exc).__name__}: {exc}")
        return 1
    except Exception as exc:
        log_step("Unexpected error", False, traceback.format_exc())
        return 1

    print("\n[RESPONSE] First response dump:")
    print(f"   stop_reason: {response.stop_reason}")
    for idx, block in enumerate(response.content):
        print(f"   content[{idx}].type: {block.type}")
        if block.type == "tool_use":
            print(f"   content[{idx}].name:  {block.name}")
            print(f"   content[{idx}].input: {block.input}")

    tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
    if not tool_use_blocks:
        log_step("tool_use presence", False, "No tool_use block found in first response.")
        return 1

    tool_use = tool_use_blocks[0]
    if tool_use.name != "add_numbers":
        log_step("tool_use name", False, f"Expected 'add_numbers', got '{tool_use.name}'")
        return 1

    try:
        a = int(tool_use.input.get("a"))
        b = int(tool_use.input.get("b"))
    except (TypeError, ValueError) as exc:
        log_step("tool_use parameters", False, f"Invalid parameters: {tool_use.input}")
        return 1

    if a != 13 or b != 29:
        log_step("tool_use parameters", False, f"Expected a=13, b=29; got a={a}, b={b}")
        return 1

    log_step("tool_use triggered with correct parameters", True, json.dumps(tool_use.input, ensure_ascii=False))

    # ------------------------------------------------------------------
    # Step 2: Send tool_result back
    # ------------------------------------------------------------------
    messages.append({"role": "assistant", "content": response.content})
    messages.append(
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": str(a + b),
                }
            ],
        }
    )

    try:
        response2 = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )
    except Exception as exc:
        log_step("Second API call (tool_result)", False, traceback.format_exc())
        return 2

    print("\n[RESPONSE] Second response dump:")
    print(f"   stop_reason: {response2.stop_reason}")
    final_text = ""
    for idx, block in enumerate(response2.content):
        print(f"   content[{idx}].type: {block.type}")
        if block.type == "text":
            final_text += block.text
            print(f"   content[{idx}].text (truncated): {block.text[:120]}...")

    if response2.stop_reason != "end_turn":
        log_step("end_turn after tool_result", False, f"stop_reason={response2.stop_reason}")
        return 2

    if "42" not in final_text:
        log_step("Final answer contains 42", False, f"Answer: {final_text[:200]}")
        return 2

    log_step("Final natural-language answer after tool_result", True, final_text.strip()[:120])

    print("\n" + "=" * 60)
    print("SUCCESS: Kimi Code fully supports Anthropic-style tool_use!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
