"""Live game integration tools — v2 file-based IPC with running game."""

import base64
import json
import shutil
from pathlib import Path

from ..bridge import BridgeClient
from ..config import RenPyConfig

_BRIDGE_SCRIPT = (Path(__file__).parent.parent / "bridge" / "bridge_script.rpy").resolve()


def register_live_tools(mcp, config: RenPyConfig):
    """Register live game integration MCP tools."""

    _bridge_client: BridgeClient | None = None

    def _get_bridge_client() -> BridgeClient:
        nonlocal _bridge_client
        if _bridge_client is None:
            if not config.project_path:
                raise ValueError("No project set.")
            _bridge_client = BridgeClient(config.project_path)
        return _bridge_client

    async def _send_command(cmd: dict, timeout: float = 5.0) -> dict:
        """Send a command and wait for response."""
        return await _get_bridge_client().send_command(cmd, timeout)

    @mcp.tool()
    async def install_bridge() -> str:
        """Install the MCP bridge script into the current project.

        This copies _mcp_bridge.rpy into the game directory, enabling
        live communication between the MCP server and a running game.
        The bridge uses interact_callbacks to poll for commands and
        enables autoreload for live script editing.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        dest = game_dir / "_mcp_bridge.rpy"

        if not _BRIDGE_SCRIPT.exists():
            return f"Error: Bridge script not found at {_BRIDGE_SCRIPT}"

        shutil.copy2(_BRIDGE_SCRIPT, dest)

        # Create _mcp directory
        mcp_dir = game_dir / "_mcp"
        mcp_dir.mkdir(exist_ok=True)

        return (
            f"Bridge installed: {dest}\n"
            f"IPC directory: {mcp_dir}\n\n"
            "Start the game normally — the bridge activates automatically.\n"
            "Use live_ping to verify the connection."
        )

    @mcp.tool()
    async def uninstall_bridge() -> str:
        """Remove the MCP bridge script and IPC files from the project.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        removed = []

        for f in [game_dir / "_mcp_bridge.rpy", game_dir / "_mcp_bridge.rpyc"]:
            if f.exists():
                f.unlink()
                removed.append(str(f.name))

        mcp_dir = game_dir / "_mcp"
        if mcp_dir.exists():
            shutil.rmtree(mcp_dir, ignore_errors=True)
            removed.append("_mcp/")

        if removed:
            return f"Removed: {', '.join(removed)}"
        return "Nothing to remove — bridge was not installed."

    @mcp.tool()
    async def live_ping() -> str:
        """Ping the running game to check if the bridge is active.

        Returns pong if the game is running and the bridge is responding.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        result = await _send_command({"action": "ping"})
        if result.get("success"):
            return "Bridge is active. Game is running and responding."
        return f"Bridge not responding: {result.get('error', 'unknown error')}"

    @mcp.tool()
    async def live_get_state() -> str:
        """Get the current game state from a running game.

        Returns current script location and all user-defined variables.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        result = await _send_command({"action": "get_state"})
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def live_screenshot() -> list[dict]:
        """Take a screenshot of the currently running game.

        Unlike screenshot_scene (which launches a new game instance),
        this captures the game as the player is currently seeing it.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return [{"type": "text", "text": "Error: No project set. Use set_project first."}]

        result = await _send_command({"action": "screenshot"}, timeout=10.0)

        if result.get("success"):
            screenshot_path = Path(result["path"])
            if screenshot_path.exists():
                data = screenshot_path.read_bytes()
                encoded = base64.b64encode(data).decode("ascii")
                return [
                    {"type": "text", "text": "Live screenshot captured."},
                    {"type": "image", "data": encoded, "mimeType": "image/png"},
                ]

        error = result.get("error", "Screenshot failed")
        return [{"type": "text", "text": f"Error: {error}"}]

    @mcp.tool()
    async def live_eval(expression: str) -> str:
        """Evaluate a Python expression in the running game context.

        Args:
            expression: Python expression to evaluate (e.g., "persistent.name",
                       "renpy.get_screen('say')", "store.book").

        Returns:
            The repr() of the expression result.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        result = await _send_command({"action": "eval", "expression": expression})
        if result.get("success"):
            return f"Result: {result.get('result')}"
        return f"Error: {result.get('error', 'eval failed')}"

    @mcp.tool()
    async def live_notify(message: str) -> str:
        """Show a notification message in the running game.

        Args:
            message: Text to display as a game notification.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        result = await _send_command({"action": "notify", "message": message})
        if result.get("success"):
            return f"Notification shown: {message}"
        return f"Error: {result.get('error', 'notify failed')}"

    @mcp.tool()
    async def live_jump(label: str) -> str:
        """Warp to a specific label in the running game.

        Uses Ren'Py's built-in warp mechanism to navigate to the target
        label with correct visual state (backgrounds, sprites, music).
        This triggers a full game restart with warp, executing scene/show
        nodes along the path to the target.

        Args:
            label: The label name to jump to (e.g., "start", "chapter2").

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        result = await _send_command({"action": "jump", "label": label})
        if result.get("success"):
            msg = result.get("message", f"Warp to '{label}' queued")
            return msg
        return f"Error: {result.get('error', 'jump failed')}"

    @mcp.tool()
    async def live_set_variable(name: str, value: str) -> str:
        """Set a game variable in the running game.

        Useful for testing different story branches by changing flags.

        Args:
            name: Variable name (e.g., "affection", "book", "chapter").
            value: Python literal value (e.g., "True", "42", "'hello'").
                   Will be evaluated as Python in the game context.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        # Validate variable name to prevent injection
        if not name.isidentifier():
            return f"Error: Invalid variable name: {name}"

        result = await _send_command({
            "action": "set_variable",
            "name": name,
            "value": value,
        })
        if result.get("success"):
            return f"Variable set: {result.get('result', name + ' = ' + value)}"
        return f"Error: {result.get('error', 'set_variable failed')}"

    @mcp.tool()
    async def style_inspector(style_name: str = "") -> str:
        """Inspect RenPy styles in the running game.

        Without arguments, lists all available style names.
        With a style name, shows all properties of that style.

        Args:
            style_name: Optional style name to inspect (e.g., "say_dialogue",
                       "button", "frame"). Leave empty to list all styles.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        result = await _send_command({"action": "get_styles", "target": style_name})
        if result.get("success"):
            if style_name:
                return json.dumps({
                    "style": result.get("style"),
                    "properties": result.get("properties", {}),
                }, indent=2, ensure_ascii=False)
            else:
                styles = result.get("styles", [])
                return f"Available styles ({len(styles)}):\n" + "\n".join(styles)
        return f"Error: {result.get('error', 'style inspection failed')}"

    @mcp.tool()
    async def save_inspector(slot: str = "") -> str:
        """Inspect save files in the running game.

        Without arguments, lists all save slots with metadata.
        With a slot name, shows detailed info for that save.

        Args:
            slot: Optional save slot to inspect (e.g., "1-1-LT1").
                  Leave empty to list all saves.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        if slot:
            result = await _send_command({"action": "load_save_info", "slot": slot})
            if result.get("success"):
                info = {
                    "slot": result.get("slot"),
                    "json_data": result.get("json_data"),
                    "has_screenshot": bool(result.get("screenshot_b64")),
                }
                return json.dumps(info, indent=2, ensure_ascii=False)
            return f"Error: {result.get('error', 'failed to load save info')}"
        else:
            result = await _send_command({"action": "list_saves"})
            if result.get("success"):
                saves = result.get("saves", [])
                if not saves:
                    return "No save files found."
                return json.dumps(saves, indent=2, ensure_ascii=False)
            return f"Error: {result.get('error', 'failed to list saves')}"

    @mcp.tool()
    async def screen_hierarchy(screen_name: str = "") -> str:
        """Inspect the widget hierarchy of a currently shown screen.

        Without arguments, lists all currently shown screens.
        With a screen name, shows the widget tree of that screen.

        Args:
            screen_name: Name of the screen to inspect (e.g., "main_menu",
                        "say", "navigation"). Leave empty to list shown screens.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        result = await _send_command({"action": "screen_hierarchy", "screen": screen_name})
        if result.get("success"):
            if screen_name:
                return json.dumps({
                    "screen": result.get("screen"),
                    "widget_count": result.get("widget_count", 0),
                    "tree": result.get("tree", []),
                }, indent=2, ensure_ascii=False)
            else:
                screens = result.get("shown_screens", [])
                if screens:
                    return "Currently shown screens:\n" + "\n".join(f"  - {s}" for s in screens)
                return "No screens currently shown."
        return f"Error: {result.get('error', 'screen inspection failed')}"
