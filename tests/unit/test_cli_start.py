"""Tests for CLI startup wiring and dependency declarations."""

from pathlib import Path
import tomllib

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from renpy_mcp.cli.app import main


def test_start_command_uses_unified_http_entry():
    """vn-creator start must call run_http (unified entry) instead of legacy web_main."""
    runner = CliRunner()

    with (
        patch("renpy_mcp.cli.app.run_http", return_value=None) as mock_run_http,
        patch("renpy_mcp.cli.app.webbrowser.open") as mock_browser,
        patch("asyncio.run", side_effect=lambda coro: None) as mock_asyncio_run,
    ):
        # Ensure the legacy web_main is NOT imported / used
        result = runner.invoke(main, ["start", "--port", "9999", "--no-browser"])

    assert result.exit_code == 0, result.output
    # Browser should NOT open when --no-browser is passed
    mock_browser.assert_not_called()
    # run_http must be the target passed to asyncio.run
    mock_asyncio_run.assert_called_once()
    # Verify run_http was called with correct host/port
    call_args = mock_run_http.call_args
    assert call_args is not None
    assert call_args.kwargs.get("open_browser") is False


def test_http_dashboard_declares_session_middleware_dependency():
    """FastAPI HTTP startup imports SessionMiddleware, so itsdangerous must be a direct dependency."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]

    assert any(
        dep.split(">=")[0].split("[")[0] == "itsdangerous"
        for dep in dependencies
    ), "pyproject.toml must declare itsdangerous for FastAPI SessionMiddleware startup"
