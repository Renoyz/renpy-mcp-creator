"""Tests for AI-related config extensions."""

import os
from pathlib import Path

import pytest


def test_settings_ai_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings should have sensible defaults for AI fields."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("RENPY_MCP_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_IMAGE_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_TEXT_MODEL", raising=False)
    monkeypatch.delenv("RENPY_MCP_DEFAULT_TEMPLATE", raising=False)

    from renpy_mcp.config import Settings

    settings = Settings()

    assert settings.gemini_api_key is None
    assert settings.default_template == "basic"


def test_settings_ai_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """AI settings should read from environment variables."""
    monkeypatch.setenv("RENPY_MCP_GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("RENPY_MCP_GEMINI_IMAGE_MODEL", "custom-image-model")
    monkeypatch.setenv("RENPY_MCP_GEMINI_TEXT_MODEL", "custom-text-model")
    monkeypatch.setenv("RENPY_MCP_DEFAULT_TEMPLATE", "advanced")

    from renpy_mcp.config import Settings

    settings = Settings()

    assert settings.gemini_api_key == "test-gemini-key"
    assert settings.default_template == "advanced"
