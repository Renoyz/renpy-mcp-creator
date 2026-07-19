#!/usr/bin/env python3
"""
Smoke test for Alibaba DashScope image generation API (native endpoint).
Tests DashScope image generation using the multimodal-generation endpoint.

Exit codes:
    0 - Image generation works.
    1 - Auth/config error or generation failed.

Environment variables:
    DASHSCOPE_API_KEY  - Required. DashScope API key.
    DASHSCOPE_BASE_URL - Optional. Default: https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation
"""

import json
import os
import sys
import traceback

import httpx

def main() -> int:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    base_url = os.environ.get(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
    )

    if not api_key:
        print("ERROR: DASHSCOPE_API_KEY environment variable is not set.")
        return 1

    model = os.environ.get("DASHSCOPE_IMAGE_MODEL", "qwen-image")
    print(f"Endpoint: {base_url}")
    print(f"Model:    {model}")
    print("-" * 60)

    payload = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": "A beautiful cherry blossom tree in a Japanese garden, soft pastel colors, anime style, high quality"
                        }
                    ]
                }
            ]
        },
        "parameters": {
            "size": "1024*1024",
            "watermark": False,
            "prompt_extend": True,
        },
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        print("Sending image generation request...")
        response = httpx.post(base_url, headers=headers, json=payload, timeout=120.0)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        print(f"[FAIL] HTTP error {exc.response.status_code}: {exc.response.text}")
        return 1
    except Exception as exc:
        print(f"[FAIL] Unexpected error: {traceback.format_exc()}")
        return 1

    data = response.json()
    print("\n[RESPONSE] JSON dump:")
    print(json.dumps(data, indent=2, ensure_ascii=False)[:1500])

    # Check for image URL in the response
    try:
        output = data.get("output", {})
        choices = output.get("choices", [])
        if not choices:
            print("\n[FAIL] No choices in response.")
            return 1

        message = choices[0].get("message", {})
        content_list = message.get("content", [])
        image_urls = [
            item.get("image")
            for item in content_list
            if item.get("image")
        ]

        if image_urls:
            print(f"\n[PASS] Image URL received successfully.")
            print(f"   URL: {image_urls[0]}")
        else:
            print("\n[FAIL] No image URL found in response content.")
            # Print full content to debug
            print(f"   content: {content_list}")
            return 1
    except Exception as exc:
        print(f"\n[FAIL] Failed to parse response: {traceback.format_exc()}")
        return 1

    print("\n" + "=" * 60)
    print("SUCCESS: DashScope image generation is working!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
