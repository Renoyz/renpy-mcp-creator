"""RenPy MCP Server - AI-powered development workflow for Ren'Py."""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .config import RenPyConfig
from .renpy_runner import RenPyRunner
from .tools.project import register_project_tools
from .tools.preview import register_preview_tools
from .tools.testing import register_testing_tools
from .tools.analysis import register_analysis_tools
from .tools.assets import register_asset_tools
from .tools.translation import register_translation_tools
from .tools.live import register_live_tools
from .tools.refactor import register_refactor_tools
from .tools.web import register_web_tools
from .resources.docs import register_doc_resources

# Initialize MCP server
mcp = FastMCP(
    "renpy-mcp",
    instructions=(
        "MCP server for Ren'Py visual novel engine development. "
        "Provides tools for project management, visual preview, automated testing, "
        "story analysis, asset management, translation, and documentation search.\n\n"
        "When working with tool results, write down any important information you might "
        "need later in your response, as the original tool result may be cleared later.\n\n"
        "When making function calls using tools that accept array or object parameters "
        "ensure those are structured using JSON."
    ),
)

# Initialize config and runner
config = RenPyConfig(
    sdk_path=Path(os.environ.get("RENPY_SDK_PATH", ".")),
)
runner = RenPyRunner(config)

# Register all tool groups
register_project_tools(mcp, config, runner)
register_preview_tools(mcp, config, runner)
register_testing_tools(mcp, config, runner)
register_analysis_tools(mcp, config)
register_asset_tools(mcp, config)
register_translation_tools(mcp, config, runner)
register_live_tools(mcp, config)
register_refactor_tools(mcp, config)
register_web_tools(mcp, config)
register_doc_resources(mcp, config)


# --- Resources ---

@mcp.resource("renpy://status")
def get_status() -> str:
    """Get current RenPy MCP server status."""
    errors = config.validate()
    return (
        f"SDK: {config.sdk_path}\n"
        f"Project: {config.project_path or '(not set)'}\n"
        f"Status: {'ERROR: ' + '; '.join(errors) if errors else 'OK'}"
    )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
