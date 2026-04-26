"""Internationalization and language-detection utilities."""

import re
from typing import Any

_START_TRIGGERS = frozenset([
    "start_blueprint_collection",
    "让 AI 生成蓝图",
])


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[一-鿿]", text))


def _is_clearly_english(text: str) -> bool:
    if not text.strip() or _contains_cjk(text):
        return False
    words = re.findall(r"[A-Za-z]{2,}", text)
    letters = sum(len(word) for word in words)
    return len(words) >= 3 or letters >= 18


def _preferred_output_language_from_texts(texts: list[str]) -> str:
    for text in reversed(texts):
        stripped = text.strip()
        if not stripped or stripped in _START_TRIGGERS:
            continue
        if _contains_cjk(stripped):
            return "zh"
        if _is_clearly_english(stripped):
            return "en"
    return "zh"


def _preferred_output_language_from_messages(messages: list[dict[str, Any]]) -> str:
    texts: list[str] = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            texts.append(content)
    return _preferred_output_language_from_texts(texts)


def _localized_text(lang: str, zh: str, en: str) -> str:
    return en if lang == "en" else zh


def _language_instruction(lang: str) -> str:
    return _localized_text(
        lang,
        "Preferred output language for all user-visible content: Simplified Chinese.",
        "Preferred output language for all user-visible content: English.",
    )


def _localized_confirmation_message(tool_name: str | None, lang: str, fallback: str) -> str:
    if lang != "en":
        return fallback
    if tool_name == "generate_background":
        return "Generated a background image. Save it?"
    if tool_name == "generate_character":
        return "Generated a character image. Save it?"
    if tool_name == "delete_project":
        return "Delete this project?"
    if tool_name == "build_project":
        return "Build this project now?"
    return f"Run {tool_name or 'this action'}?"
