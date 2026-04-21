"""Global pytest fixtures for test isolation."""

import pytest

import renpy_mcp.config as config_module


_REAL_AI_ENV_VARS = (
    "RENPY_MCP_ANTHROPIC_API_KEY",
    "RENPY_MCP_DEEPSEEK_API_KEY",
    "RENPY_MCP_QWEN_API_KEY",
    "RENPY_MCP_JIMENG_API_KEY",
    "RENPY_MCP_TONGYI_API_KEY",
    "RENPY_MCP_GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "QWEN_API_KEY",
    "JIMENG_API_KEY",
    "TONGYI_API_KEY",
    "GEMINI_API_KEY",
)


@pytest.fixture(autouse=True)
def isolate_real_ai_credentials(monkeypatch: pytest.MonkeyPatch):
    """Prevent tests from inheriting local AI credentials or cached settings."""
    for env_var in _REAL_AI_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)

    config_module._settings = None
    try:
        yield
    finally:
        config_module._settings = None
