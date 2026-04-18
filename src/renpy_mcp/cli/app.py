"""CLI entry point for vn-creator."""

import asyncio
import os
import sys
import webbrowser
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from renpy_mcp.config import get_settings
from renpy_mcp.main import run_http
from renpy_mcp.services.sdk_provisioner import SdkProvisioner

console = Console()


@click.group()
def main():
    """vn-creator CLI — AI visual novel generator."""
    pass


@main.command()
def version():
    """Show version."""
    click.echo("vn-creator 0.1.0")


@main.command()
@click.option("--port", default=8080, help="HTTP server port")
@click.option("--no-browser", is_flag=True, help="Do not open browser automatically")
def start(port: int, no_browser: bool):
    """Start the RenPy MCP server and open Dashboard."""
    url = f"http://localhost:{port}/dashboard"
    if not no_browser:
        console.print(f"[green]Opening Dashboard at {url}...[/green]")
        webbrowser.open(url)
    else:
        console.print(f"[green]Dashboard will be available at {url}[/green]")

    # Run the unified HTTP server (blocks)
    try:
        asyncio.run(run_http("127.0.0.1", port, open_browser=False))
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped.[/yellow]")


@main.command()
def doctor():
    """Run environment diagnostics."""
    settings = get_settings()
    table = Table(title="vn-creator Doctor Report")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Detail")

    # Python version
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11):
        table.add_row("Python version", "[green]PASS", py_version)
    else:
        table.add_row("Python version", "[red]FAIL", f"{py_version} (need >= 3.11)")

    # SDK check
    provisioner = SdkProvisioner(settings)
    sdk_path = provisioner.resolve_sdk_path()
    if provisioner.is_sdk_ready(sdk_path):
        table.add_row("RenPy SDK", "[green]PASS", str(sdk_path))
    else:
        table.add_row("RenPy SDK", "[yellow]MISSING", "Not found. Run `vn-creator start` to auto-download.")

    # API keys
    keys = {
        "Anthropic (Kimi)": os.environ.get("ANTHROPIC_API_KEY") or settings.anthropic_api_key,
        "DeepSeek": settings.deepseek_api_key,
        "Qwen": settings.qwen_api_key,
        "Gemini": settings.gemini_api_key,
    }
    for name, key in keys.items():
        if key:
            masked = key[:4] + "..." + key[-4:] if len(key) > 8 else "****"
            table.add_row(f"API Key: {name}", "[green]PASS", masked)
        else:
            table.add_row(f"API Key: {name}", "[yellow]MISSING", "Not configured")

    # Port check
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", settings.port))
        table.add_row(f"Port {settings.port}", "[green]AVAILABLE", "Ready to use")
    except OSError:
        table.add_row(f"Port {settings.port}", "[red]IN USE", "Another process is using this port")
    finally:
        sock.close()

    console.print(table)


if __name__ == "__main__":
    main()
