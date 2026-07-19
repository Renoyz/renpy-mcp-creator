"""Tests for CLI startup wiring and dependency declarations."""

import tomllib
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from renpy_mcp.cli.app import main


def test_start_command_uses_unified_http_entry():
    """vn-creator start must call run_http (unified entry) instead of legacy web_main."""
    runner = CliRunner()
    run_http_result = object()

    with (
        patch(
            "renpy_mcp.cli.app.run_http",
            new=MagicMock(return_value=run_http_result),
        ) as mock_run_http,
        patch("renpy_mcp.cli.app.webbrowser.open") as mock_browser,
        patch("asyncio.run") as mock_asyncio_run,
        # SDK present → auto-provisioning takes the fast path and asyncio.run
        # is only used for run_http.
        patch("renpy_mcp.cli.app.SdkProvisioner.is_sdk_ready", return_value=True),
    ):
        # Ensure the legacy web_main is NOT imported / used
        result = runner.invoke(main, ["start", "--port", "9999", "--no-browser"])

    assert result.exit_code == 0, result.output
    # Browser should NOT open when --no-browser is passed
    mock_browser.assert_not_called()
    # run_http must be the target passed to asyncio.run
    mock_asyncio_run.assert_called_once_with(run_http_result)
    # Verify run_http was called with correct host/port
    call_args = mock_run_http.call_args
    assert call_args is not None
    assert call_args.kwargs.get("open_browser") is False


def test_http_dashboard_declares_session_middleware_dependency():
    """SessionMiddleware requires itsdangerous as a direct dependency."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]

    assert any(
        dep.split(">=")[0].split("[")[0] == "itsdangerous"
        for dep in dependencies
    ), "pyproject.toml must declare itsdangerous for FastAPI SessionMiddleware startup"


def test_doctor_missing_sdk_requires_manual_configuration():
    runner = CliRunner()

    with (
        patch("renpy_mcp.cli.app.SdkProvisioner.resolve_sdk_path", return_value=None),
        patch("renpy_mcp.cli.app.SdkProvisioner.is_sdk_ready", return_value=False),
    ):
        result = runner.invoke(main, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "auto-download" not in result.output
    assert "RENPY_SDK_PATH" in result.output


def test_start_downloads_sdk_when_missing():
    """vn-creator start must auto-provision the SDK when it is missing."""
    runner = CliRunner()
    ensure = MagicMock()

    with (
        patch("renpy_mcp.cli.app.run_http", new=MagicMock(return_value=object())),
        patch("renpy_mcp.cli.app.webbrowser.open"),
        patch("asyncio.run"),
        patch("renpy_mcp.cli.app.SdkProvisioner.resolve_sdk_path", return_value=None),
        patch("renpy_mcp.cli.app.SdkProvisioner.is_sdk_ready", return_value=False),
        patch("renpy_mcp.cli.app.SdkProvisioner.ensure_sdk", new=ensure),
    ):
        result = runner.invoke(main, ["start", "--port", "9999", "--no-browser"])

    assert result.exit_code == 0, result.output
    ensure.assert_called_once()


def test_start_skips_sdk_download_when_ready():
    """No download attempt when a usable SDK is already configured."""
    runner = CliRunner()
    ensure = MagicMock()

    with (
        patch("renpy_mcp.cli.app.run_http", new=MagicMock(return_value=object())),
        patch("renpy_mcp.cli.app.webbrowser.open"),
        patch("asyncio.run"),
        patch("renpy_mcp.cli.app.SdkProvisioner.resolve_sdk_path", return_value=None),
        patch("renpy_mcp.cli.app.SdkProvisioner.is_sdk_ready", return_value=True),
        patch("renpy_mcp.cli.app.SdkProvisioner.ensure_sdk", new=ensure),
    ):
        result = runner.invoke(main, ["start", "--port", "9999", "--no-browser"])

    assert result.exit_code == 0, result.output
    ensure.assert_not_called()


def test_start_continues_when_sdk_download_fails():
    """A failed SDK download warns but must not prevent the server from starting."""
    runner = CliRunner()

    with (
        patch("renpy_mcp.cli.app.run_http", new=MagicMock(return_value=object())),
        patch("renpy_mcp.cli.app.webbrowser.open"),
        patch("asyncio.run", side_effect=[RuntimeError("no network"), None]),
        patch("renpy_mcp.cli.app.SdkProvisioner.resolve_sdk_path", return_value=None),
        patch("renpy_mcp.cli.app.SdkProvisioner.is_sdk_ready", return_value=False),
        patch("renpy_mcp.cli.app.SdkProvisioner.ensure_sdk", new=MagicMock()),
    ):
        result = runner.invoke(main, ["start", "--port", "9999", "--no-browser"])

    assert result.exit_code == 0, result.output
    assert "SDK download failed" in result.output


def test_httpx_declared_as_runtime_dependency():
    """httpx is imported by runtime modules (sdk_provisioner, providers, image_service)."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]

    assert any(
        dep.split(">=")[0].split("[")[0] == "httpx"
        for dep in dependencies
    ), "pyproject.toml must declare httpx as a runtime dependency"
