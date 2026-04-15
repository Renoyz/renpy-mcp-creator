"""Web UI tools — browser-based visual development interface."""

from ..config import RenPyConfig
from ..web.server import start_web, start_server


def register_web_tools(mcp, config: RenPyConfig):
    """Register web UI MCP tools."""

    @mcp.tool()
    async def open_story_map() -> str:
        """Open the visual story map in a browser.

        Displays an interactive graph of all labels and their connections
        (jumps, calls, menus). Click any node to jump to that label in
        the running game (requires bridge installed).

        Node colors:
        - Green: start label
        - Blue: normal labels
        - Orange: labels with choices (menus)
        - Red: dead ends (no exit)
        - Gray: orphaned (unreachable) labels

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        url = start_web(config, "/story-map")
        return (
            f"Story map opened: {url}\n\n"
            "Click any node to jump to that label in the running game.\n"
            "Hover over nodes to see file location and dialogue count.\n"
            "Use mouse wheel to zoom, drag to pan."
        )

    @mcp.tool()
    async def open_dashboard() -> str:
        """Open the real-time development dashboard in a browser.

        Provides a live view of the running game with:
        - Game state: current label and script position
        - Variable watcher: view and edit game variables in real-time
        - Live preview: periodic screenshot of the running game
        - Quick actions: jump to labels, send notifications, evaluate
          expressions, and set variables

        Requires the bridge to be installed and the game to be running.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        url = start_web(config, "/dashboard")
        return (
            f"Dashboard opened: {url}\n\n"
            "The dashboard polls the running game every 2-3 seconds.\n"
            "Make sure the bridge is installed and the game is running."
        )

    @mcp.tool()
    async def open_script_editor() -> str:
        """Open the visual script editor in a browser.

        Provides a flowchart-style view of .rpy script files where you can:
        - See dialogue, menus, jumps, and scene changes as visual blocks
        - Edit dialogue text and character assignments inline
        - Modify menu choices and jump targets
        - Add new dialogue or narration blocks
        - Save changes back to the .rpy file

        Does NOT require the bridge — works directly with script files.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        url = start_web(config, "/script-editor")
        return (
            f"Script editor opened: {url}\n\n"
            "Select a .rpy file to view its structure as a flowchart.\n"
            "Click any block to edit it inline."
        )

    @mcp.tool()
    async def open_heatmap() -> str:
        """Open the playtest heatmap in a browser.

        Visualizes playtest data on top of the story flow graph:
        - Node size and color show visit frequency (heat map)
        - Edge thickness shows transition counts between labels
        - Bar charts show visits and time spent per label
        - Session timelines show the path through the story

        Use "Start Recording" to begin tracking, then play through the
        game. Stop recording to analyze the data. Multiple sessions
        can be recorded and compared.

        Requires the bridge to be installed and the game to be running.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        url = start_web(config, "/heatmap")
        return (
            f"Heatmap opened: {url}\n\n"
            "Click 'Start Recording' then play through the game.\n"
            "The heatmap updates in real-time while recording.\n"
            "Stop recording to freeze the data for analysis."
        )

    @mcp.tool()
    async def open_asset_manager() -> str:
        """Open the asset manager in a browser.

        Provides a visual overview of all project assets:
        - Thumbnail grid for images with lazy loading
        - Audio player for music and sound effects
        - Filter by type (image/audio/video) and usage status
        - Search by filename
        - Size analysis and oversized image warnings
        - Unused asset detection with red highlight
        - Click any asset for detailed info and script references

        Does NOT require the bridge — works directly with project files.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        url = start_web(config, "/assets")
        return (
            f"Asset manager opened: {url}\n\n"
            "Browse all project assets with thumbnails and audio preview.\n"
            "Use filters to find unused assets or sort by size."
        )
