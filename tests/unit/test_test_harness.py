"""Regression tests for test-suite isolation from local AI credentials."""

from renpy_mcp.config import get_settings


def test_test_suite_does_not_inherit_real_dashscope_image_credentials() -> None:
    """Automated tests must not inherit local DashScope credentials by default."""
    settings = get_settings()
    assert settings.qwen_api_key is None
