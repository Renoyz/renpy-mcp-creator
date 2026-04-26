"""Tests for config module."""

import os
from pathlib import Path

import pytest


def test_settings_default_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings should have sensible defaults."""
    # Ensure environment is clean
    monkeypatch.delenv("RENPY_MCP_WORKSPACE", raising=False)
    monkeypatch.delenv("RENPY_MCP_PORT", raising=False)
    monkeypatch.delenv("RENPY_SDK_PATH", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from renpy_mcp.config import Settings

    settings = Settings()

    assert settings.port == 8080
    assert settings.workspace is not None
    assert isinstance(settings.workspace, Path)
    assert settings.renpy_sdk_path is None
    assert settings.deepseek_api_key is None


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings should read from environment variables."""
    monkeypatch.setenv("RENPY_MCP_WORKSPACE", "/tmp/test_workspace")
    monkeypatch.setenv("RENPY_MCP_PORT", "9000")
    monkeypatch.setenv("RENPY_SDK_PATH", "/tmp/renpy-sdk")
    monkeypatch.setenv("RENPY_MCP_DEEPSEEK_API_KEY", "sk-test-deepseek")

    from renpy_mcp.config import Settings

    settings = Settings()

    assert settings.workspace == Path("/tmp/test_workspace")
    assert settings.port == 9000
    assert settings.renpy_sdk_path == Path("/tmp/renpy-sdk")
    assert settings.deepseek_api_key == "sk-test-deepseek"
