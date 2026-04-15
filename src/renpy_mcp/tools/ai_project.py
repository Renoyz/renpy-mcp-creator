"""AI project creation tools."""

import json

from renpy_mcp.config import Settings
from renpy_mcp.services.project_manager import ProjectManager


def register_ai_project_tools(mcp, settings: Settings):
    """Register AI project-related MCP tools."""
    project_manager = ProjectManager(settings)

    @mcp.tool()
    async def create_project(name: str, template: str = "") -> str:
        """Create a new Ren'Py project directory using the requested template.

        Args:
            name: Project name (used as directory name).
            template: Template to use. Defaults to the configured default_template.
        """
        template_name = template or settings.default_template
        project_dir = project_manager.ensure_project_dir(name)
        template_path = project_manager.find_template(template_name)
        project_manager.copy_template(project_dir, template_path)

        return json.dumps(
            {
                "name": name,
                "path": str(project_dir),
                "template": template_name,
            },
            indent=2,
            ensure_ascii=False,
        )
