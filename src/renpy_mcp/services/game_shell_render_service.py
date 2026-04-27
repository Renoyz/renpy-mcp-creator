"""Render deterministic Ren'Py game shell files from project metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from renpy_mcp.blueprint.models import (
    GameShellConfig,
    GameShellEndingItem,
    GameShellGalleryItem,
    GameShellRenderPreview,
)
from renpy_mcp.services.project_manager import ProjectManager


def _renpy_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _safe_id(value: str, fallback: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    return cleaned or fallback


class GameShellRenderService:
    """Derive and render the editable presentation shell for a prototype."""

    DEFAULT_STAGING_NAMESPACE = "shell"

    def __init__(self, pm: ProjectManager) -> None:
        self.pm = pm

    def validate_config(self, config: GameShellConfig) -> GameShellConfig:
        """Round-trip through Pydantic validation for callers with raw models."""
        return GameShellConfig.model_validate(config.model_dump(mode="json"))

    def read_or_derive_config(self, project_name: str) -> GameShellConfig:
        saved = self.pm.read_game_shell(project_name)
        if saved is not None:
            return saved
        return self.derive_config(project_name)

    def save_config(self, project_name: str, config: GameShellConfig) -> GameShellConfig:
        config = self.validate_config(config)
        self.pm.write_game_shell(project_name, config)
        saved = self.pm.read_game_shell(project_name)
        return saved or config

    def derive_and_save_config(self, project_name: str) -> GameShellConfig:
        config = self.derive_config(project_name)
        self.pm.write_game_shell(project_name, config)
        saved = self.pm.read_game_shell(project_name)
        return saved or config

    def derive_config(self, project_name: str) -> GameShellConfig:
        blueprint = self.pm.read_blueprint(project_name)
        meta = self.pm.read_project_meta(project_name)
        title = ""
        if blueprint is not None and blueprint.title:
            title = blueprint.title
        elif meta is not None and meta.name:
            title = meta.name
        else:
            title = project_name

        gallery_items = self._derive_gallery_items(project_name)
        ending_items = self._derive_ending_items(project_name)
        return GameShellConfig(
            title=title,
            subtitle=(blueprint.genre if blueprint is not None else ""),
            theme="default",
            show_gallery=True,
            show_endings=True,
            show_credits=True,
            gallery_items=gallery_items,
            ending_items=ending_items,
            credits=["Created with RenPy MCP Creator"],
        )

    def _derive_gallery_items(self, project_name: str) -> list[GameShellGalleryItem]:
        items: list[GameShellGalleryItem] = []
        seen: set[str] = set()

        state_path = self.pm._project_dir(project_name) / "meta" / "generation_state.json"
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                state = {}
            for collection, source in (("character_assets", "sprite"), ("background_assets", "background")):
                assets = state.get(collection, {})
                if not isinstance(assets, dict):
                    continue
                for slot in assets.values():
                    if not isinstance(slot, dict) or slot.get("status") != "accepted":
                        continue
                    path = slot.get("path") or slot.get("staging_path") or ""
                    target = str(slot.get("target") or slot.get("asset_id") or "Asset")
                    if not path or path in seen:
                        continue
                    seen.add(path)
                    items.append(GameShellGalleryItem(
                        id=_safe_id(str(slot.get("asset_id") or target), f"gallery_{len(items) + 1}"),
                        title=target,
                        image_path=str(path),
                        source=source,  # type: ignore[arg-type]
                    ))

        index = self.pm.read_project_index(project_name) or {}
        for scene_id, scene in (index.get("scenes") or {}).items():
            if not isinstance(scene, dict):
                continue
            for key, source in (("background_path", "background"), ("sprite_path", "sprite")):
                path = scene.get(key)
                if not isinstance(path, str) or not path or path in seen:
                    continue
                seen.add(path)
                title = str(scene.get("title") or scene_id)
                items.append(GameShellGalleryItem(
                    id=_safe_id(f"{scene_id}_{key}", f"gallery_{len(items) + 1}"),
                    title=title,
                    image_path=path,
                    source=source,  # type: ignore[arg-type]
                ))

        return items

    def _derive_ending_items(self, project_name: str) -> list[GameShellEndingItem]:
        scene_packages = self.pm.read_scene_packages(project_name)
        if scene_packages is not None:
            for chapter in reversed(scene_packages.chapters):
                if not chapter.scenes:
                    continue
                scene = chapter.scenes[-1]
                return [
                    GameShellEndingItem(
                        id=_safe_id(scene.scene_id, "ending_default"),
                        title=scene.title or chapter.chapter_name or "Prototype Ending",
                        description=scene.summary,
                    )
                ]
        return [
            GameShellEndingItem(
                id="prototype_ending",
                title="Prototype Ending",
                description="Complete the generated prototype.",
            )
        ]

    def _script_files(self, staging_namespace: str) -> dict[str, str]:
        namespace = _safe_id(staging_namespace, self.DEFAULT_STAGING_NAMESPACE)
        if namespace == self.DEFAULT_STAGING_NAMESPACE:
            base = "game/__staging__/shell"
        else:
            base = f"game/__staging__/{namespace}/shell"
        return {
            "shell": f"{base}/zz_generated_shell.rpy",
            "gallery": f"{base}/zz_generated_gallery.rpy",
            "endings": f"{base}/zz_generated_endings.rpy",
            "credits": f"{base}/zz_generated_credits.rpy",
        }

    def render_preview(
        self,
        project_name: str,
        config: GameShellConfig | None = None,
        *,
        staging_namespace: str = DEFAULT_STAGING_NAMESPACE,
    ) -> GameShellRenderPreview:
        config = self.validate_config(config or self.read_or_derive_config(project_name))
        project_dir = self.pm._project_dir(project_name)
        script_files = self._script_files(staging_namespace)
        rendered = {
            script_files["shell"]: self._render_shell(config),
            script_files["gallery"]: self._render_gallery(config),
            script_files["endings"]: self._render_endings(config),
            script_files["credits"]: self._render_credits(config),
        }

        for rel_path, content in rendered.items():
            path = project_dir / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        preview = "\n\n".join(rendered.values())
        return GameShellRenderPreview(
            script_files=list(rendered.keys()),
            preview=preview,
            gallery_count=len(config.gallery_items),
            ending_count=len(config.ending_items),
            preview_url="",
        )

    def _render_shell(self, config: GameShellConfig) -> str:
        title = _renpy_string(config.title or "Untitled VN")
        subtitle = _renpy_string(config.subtitle)
        background_line = (
            f"    add {_renpy_string(config.main_menu_background)}\n"
            if config.main_menu_background else
            '    add Solid("#111827")\n'
        )
        return (
            "# Auto-generated by RenPy MCP Creator. Do not edit by hand.\n"
            "screen navigation():\n"
            "    vbox:\n"
            "        style_prefix \"navigation\"\n"
            "        xpos gui.navigation_xpos\n"
            "        yalign 0.5\n"
            "        spacing gui.navigation_spacing\n"
            "        if main_menu:\n"
            "            textbutton _(\"Start\") action Start()\n"
            "        else:\n"
            "            textbutton _(\"History\") action ShowMenu(\"history\")\n"
            "            textbutton _(\"Save\") action ShowMenu(\"save\")\n"
            "        textbutton _(\"Load\") action ShowMenu(\"load\")\n"
            "        textbutton _(\"Preferences\") action ShowMenu(\"preferences\")\n"
            "        textbutton _(\"Extras\") action ShowMenu(\"mcp_extras\")\n"
            "        if not main_menu:\n"
            "            textbutton _(\"Main Menu\") action MainMenu()\n"
            "        textbutton _(\"Quit\") action Quit(confirm=not main_menu)\n\n"
            "screen main_menu():\n"
            "    tag menu\n"
            f"{background_line}"
            "    use navigation\n"
            "    vbox:\n"
            "        xalign 0.95\n"
            "        yalign 0.95\n"
            f"        text {title} size 56\n"
            f"        text {subtitle} size 24\n\n"
            "screen mcp_extras():\n"
            "    tag menu\n"
            "    add Solid(\"#111827\")\n"
            "    vbox:\n"
            "        xalign 0.5\n"
            "        yalign 0.5\n"
            "        spacing 18\n"
            "        text _(\"Extras\") size 48\n"
            + ('        textbutton _("Gallery") action ShowMenu("mcp_gallery")\n' if config.show_gallery else "")
            + ('        textbutton _("Ending Gallery") action ShowMenu("mcp_ending_gallery")\n' if config.show_endings else "")
            + ('        textbutton _("Credits") action ShowMenu("mcp_credits")\n' if config.show_credits else "")
            + "        textbutton _(\"Return\") action Return()\n"
        )

    def _render_gallery(self, config: GameShellConfig) -> str:
        lines = [
            "# Auto-generated gallery screen.",
            "screen mcp_gallery():",
            "    tag menu",
            '    add Solid("#0f172a")',
            "    viewport:",
            "        draggable True",
            "        mousewheel True",
            "        vbox:",
            "            xalign 0.5",
            "            spacing 16",
            '            text _("Gallery") size 42',
        ]
        if not config.gallery_items:
            lines.append('            text _("No gallery items yet.")')
        for item in config.gallery_items:
            title = _renpy_string(item.title)
            image_path = _renpy_string(item.image_path)
            lines.extend([
                "            frame:",
                "                vbox:",
                f"                    text {title} size 28",
                f"                    if renpy.loadable({image_path}):",
                f"                        add {image_path} xmaximum 640 ymaximum 360 fit \"contain\"",
                "                    else:",
                f"                        text {_renpy_string(item.image_path or 'No image')} size 16",
            ])
        lines.append('            textbutton _("Return") action ShowMenu("mcp_extras")')
        return "\n".join(lines) + "\n"

    def _render_endings(self, config: GameShellConfig) -> str:
        lines = [
            "# Auto-generated ending gallery screen.",
            "screen mcp_ending_gallery():",
            "    tag menu",
            '    add Solid("#111827")',
            "    vbox:",
            "        xalign 0.5",
            "        yalign 0.5",
            "        spacing 14",
            '        text _("Ending Gallery") size 42',
        ]
        if not config.ending_items:
            lines.append('        text _("No endings recorded yet.")')
        for item in config.ending_items:
            lines.append(f"        text {_renpy_string(item.title)} size 28")
            if item.description:
                lines.append(f"        text {_renpy_string(item.description)} size 18")
        lines.append('        textbutton _("Return") action ShowMenu("mcp_extras")')
        return "\n".join(lines) + "\n"

    def _render_credits(self, config: GameShellConfig) -> str:
        lines = [
            "# Auto-generated credits screen.",
            "screen mcp_credits():",
            "    tag menu",
            '    add Solid("#020617")',
            "    vbox:",
            "        xalign 0.5",
            "        yalign 0.5",
            "        spacing 12",
            '        text _("Credits") size 42',
        ]
        credits = config.credits or ["Created with RenPy MCP Creator"]
        for line in credits:
            lines.append(f"        text {_renpy_string(line)} size 22")
        lines.append('        textbutton _("Return") action ShowMenu("mcp_extras")')
        return "\n".join(lines) + "\n"
