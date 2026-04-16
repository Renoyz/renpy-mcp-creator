"""Project management tools."""

import json
import re
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import Context

from ..config import RenPyConfig, get_settings
from ..renpy_runner import RenPyRunner
from ..services.project_manager import ProjectManager

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif"}
_DEFAULT_CHARACTER_LAYOUT_BLOCK = (
    "define left_pos = Position(xalign=0.2, yalign=1.0)\n"
    "define center_pos = Position(xalign=0.5, yalign=1.0)\n"
    "define right_pos = Position(xalign=0.8, yalign=1.0)\n"
    "\n"
    "transform scaled:\n"
    "    zoom 0.65\n"
)


def _normalize_image_lookup(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_\-]+", " ", value).strip().lower())


def _find_matching_image_path(project_dir: Path, image_name: str) -> Path | None:
    images_dir = project_dir / "game" / "images"
    if not images_dir.exists():
        return None

    target = _normalize_image_lookup(image_name)
    for file_path in images_dir.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if _normalize_image_lookup(file_path.stem) == target:
            return file_path
    return None


def _ensure_image_definition(
    lines: list[str], image_name: str, relative_asset_path: str
) -> tuple[list[str], bool]:
    definition_line = f'image {image_name} = "{relative_asset_path}"\n'
    definition_re = re.compile(rf'^\s*image\s+{re.escape(image_name)}\s*=')

    for idx, line in enumerate(lines):
        if definition_re.match(line):
            if line == definition_line:
                return lines, False
            lines[idx] = definition_line
            return lines, True

    insert_idx = 0
    while insert_idx < len(lines) and lines[insert_idx].strip().startswith("image "):
        insert_idx += 1
    lines.insert(insert_idx, definition_line)
    if insert_idx < len(lines) - 1 and lines[insert_idx + 1].strip():
        lines.insert(insert_idx + 1, "\n")
    return lines, True


def _normalize_show_statement(line: str) -> str:
    match = re.match(
        r"^(?P<prefix>\s*show\s+\S+)(?:\s+at\s+(?P<at>.*?))?(?P<with>\s+with\s+.*)?$",
        line.rstrip("\n"),
    )
    if not match:
        return line

    prefix = match.group("prefix")
    at_clause = (match.group("at") or "").strip()
    with_clause = match.group("with") or ""

    if at_clause in {"scaled, left_pos", "scaled, center_pos", "scaled, right_pos"}:
        return line

    position_map = {
        "left": "left_pos",
        "center": "center_pos",
        "right": "right_pos",
    }
    position = position_map.get(at_clause, "center_pos")
    normalized = f"{prefix} at scaled, {position}{with_clause}"
    return normalized + ("\n" if line.endswith("\n") else "")


def _ensure_default_character_layout(script_content: str) -> str:
    lines = script_content.splitlines(keepends=True)
    show_re = re.compile(r"^\s*show\s+\S+")
    if not any(show_re.match(line) for line in lines):
        return script_content

    lines = [_normalize_show_statement(line) if show_re.match(line) else line for line in lines]
    content = "".join(lines)

    if "transform scaled:" in content and "define center_pos = Position(" in content:
        return content

    insert_idx = 0
    while insert_idx < len(lines):
        stripped = lines[insert_idx].strip()
        if stripped.startswith("define ") or stripped.startswith("image ") or stripped == "":
            insert_idx += 1
            continue
        break

    block = _DEFAULT_CHARACTER_LAYOUT_BLOCK
    if insert_idx > 0 and lines[insert_idx - 1].strip():
        block = "\n" + block
    block += "\n"
    lines.insert(insert_idx, block)
    return "".join(lines)


def register_project_tools(mcp, config: RenPyConfig, runner: RenPyRunner):
    """Register project-related MCP tools."""
    settings = get_settings()
    project_manager = ProjectManager(settings)

    @mcp.tool()
    async def create_project(name: str, template: Optional[str] = None) -> str:
        """Create a new project directory using the requested template.

        Args:
            name: Project name (used as directory name).
            template: Template name to use (default: basic).
        """
        template_name = template or settings.default_template
        project_dir = project_manager.ensure_project_dir(name)
        template_path = project_manager.find_template(template_name)
        project_manager.copy_template(project_dir, template_path)

        return json.dumps(
            {"name": name, "path": str(project_dir), "template": template_name},
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def list_projects() -> str:
        """Return metadata for available projects in the workspace."""
        projects = [p.model_dump(mode="json") for p in project_manager.list_projects()]
        return json.dumps({"projects": projects}, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def list_project_files(project_name: str) -> str:
        """List all files in a project's game directory.

        Args:
            project_name: Name of the project.
        """
        project_dir = project_manager.ensure_project_dir(project_name)
        game_dir = project_dir / "game"

        if not game_dir.exists():
            return json.dumps(
                {"error": f"Project {project_name} game directory not found"},
                indent=2,
                ensure_ascii=False,
            )

        files = []
        for item in game_dir.rglob("*"):
            if item.is_file():
                rel_path = item.relative_to(game_dir)
                files.append(
                    {
                        "path": str(rel_path),
                        "full_path": str(item),
                        "size": item.stat().st_size,
                        "type": item.suffix,
                    }
                )

        return json.dumps(
            {
                "project": project_name,
                "game_dir": str(game_dir),
                "files": files,
                "count": len(files),
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def read_project_file(project_name: str, file_path: str) -> str:
        """Read the contents of a file in a project's game directory.

        Args:
            project_name: Name of the project.
            file_path: Relative path to file (e.g., "script.rpy").
        """
        project_dir = project_manager.ensure_project_dir(project_name)
        game_dir = project_dir / "game"
        target_file = game_dir / file_path

        if not target_file.exists():
            return json.dumps(
                {"error": f"File {file_path} not found in project {project_name}"},
                indent=2,
                ensure_ascii=False,
            )

        try:
            content = target_file.read_text(encoding="utf-8")
            return json.dumps(
                {
                    "project": project_name,
                    "file_path": file_path,
                    "full_path": str(target_file),
                    "content": content,
                    "size": len(content),
                    "lines": len(content.splitlines()),
                },
                indent=2,
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {"error": f"Failed to read file: {str(e)}"}, indent=2, ensure_ascii=False
            )

    @mcp.tool()
    async def edit_project_file(project_name: str, file_path: str, content: str) -> str:
        """Edit or create a file in a project's game directory.

        Args:
            project_name: Name of the project.
            file_path: Relative path to file (e.g., "script.rpy").
            content: New content for the file (will overwrite existing content).
        """
        project_dir = project_manager.ensure_project_dir(project_name)
        game_dir = project_dir / "game"
        target_file = game_dir / file_path

        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(content, encoding="utf-8")

            return json.dumps(
                {
                    "success": True,
                    "project": project_name,
                    "file_path": file_path,
                    "full_path": str(target_file),
                    "size": len(content),
                    "lines": len(content.splitlines()),
                    "message": f"File {file_path} updated successfully.",
                },
                indent=2,
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {"error": f"Failed to edit file: {str(e)}"}, indent=2, ensure_ascii=False
            )

    @mcp.tool()
    async def generate_script(
        project_name: str, script_name: str, script_content: str
    ) -> str:
        """Write a Ren'Py script file to the project.

        Args:
            project_name: Name of the project.
            script_name: Name for the script file (e.g., "intro" creates intro.rpy).
            script_content: Complete Ren'Py script content.
        """
        project_dir = project_manager.ensure_project_dir(project_name)

        safe_name = re.sub(r"[^a-z0-9_]+", "_", script_name.lower()).strip("_") or "scene"
        script_path = project_dir / "game" / f"{safe_name}.rpy"
        script_path.parent.mkdir(parents=True, exist_ok=True)

        normalized_script_content = _ensure_default_character_layout(script_content)
        script_path.write_text(normalized_script_content, encoding="utf-8")

        # Extract the label name from the script content
        label_name = None
        for line in normalized_script_content.split("\n"):
            line = line.strip()
            if line.startswith("label ") and ":" in line:
                label_name = line[6 : line.index(":")].strip()
                break

        # Update the main script.rpy to call this label
        main_script = project_dir / "game" / "script.rpy"
        if main_script.exists() and label_name:
            main_content = main_script.read_text(encoding="utf-8")

            if "Welcome to your new Ren'Py project!" in main_content:
                new_main_content = f"""label start:
    # Call the generated story
    call {label_name}
    
    # Return to main menu
    return
"""
                main_script.write_text(new_main_content, encoding="utf-8")

        preview_lines = "\n".join(normalized_script_content.split("\n")[:15])
        if len(normalized_script_content.split("\n")) > 15:
            preview_lines += "\n... (truncated)"

        message = f"Script saved to {script_path.relative_to(project_dir)}"
        if label_name:
            message += f" and main script.rpy updated to call '{label_name}'"

        return json.dumps(
            {
                "success": True,
                "project_name": project_name,
                "script_name": safe_name,
                "script_path": str(script_path.relative_to(project_dir)),
                "preview": preview_lines,
                "message": message,
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def attach_background_to_start(project_name: str, image_name: str) -> str:
        """Insert a scene statement for the given background image under label start in script.rpy.

        Args:
            project_name: Name of the project.
            image_name: Ren'Py image name to use in the scene statement (e.g., "bg room").
        """
        project_dir = project_manager.ensure_project_dir(project_name)
        script_path = project_dir / "game" / "script.rpy"
        if not script_path.exists():
            return json.dumps(
                {"success": False, "error": "script.rpy not found"},
                indent=2,
                ensure_ascii=False,
            )

        content = script_path.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        label_re = re.compile(r'^\s*label\s+start\s*:\s*$')
        matched_asset = _find_matching_image_path(project_dir, image_name)
        registration_changed = False

        if matched_asset is not None:
            asset_relative = str(matched_asset.relative_to(project_dir / "game")).replace("\\", "/")
            lines, registration_changed = _ensure_image_definition(lines, image_name, asset_relative)

        label_idx = -1
        for i, line in enumerate(lines):
            if label_re.match(line):
                label_idx = i
                break

        if label_idx == -1:
            return json.dumps(
                {"success": False, "error": "label start: not found in script.rpy"},
                indent=2,
                ensure_ascii=False,
            )

        scene_line = f"    scene {image_name}\n"
        first_statement_idx = None
        next_label_idx = len(lines)

        for j in range(label_idx + 1, len(lines)):
            line = lines[j]
            stripped = line.strip()
            if stripped.startswith("label ") and stripped.endswith(":"):
                next_label_idx = j
                break
            if stripped == "" or stripped.startswith("#"):
                continue
            if first_statement_idx is None:
                first_statement_idx = j

        cleanup_applied = False
        if first_statement_idx is not None and lines[first_statement_idx].strip() == scene_line.strip():
            cleanup_indices: list[int] = []
            for j in range(first_statement_idx + 1, next_label_idx):
                stripped = lines[j].strip()
                if stripped == "" or stripped.startswith("#"):
                    continue
                if stripped.startswith("scene "):
                    cleanup_indices.append(j)
                    continue
                break

            if cleanup_indices:
                for idx in reversed(cleanup_indices):
                    lines.pop(idx)
                script_path.write_text("".join(lines), encoding="utf-8")
                cleanup_applied = True
                return json.dumps(
                    {
                        "success": True,
                        "image_name": image_name,
                        "file": str(script_path.relative_to(project_dir)),
                        "message": "Removed stale opening scene statements after the selected background.",
                        "registered_asset": registration_changed,
                    },
                    indent=2,
                    ensure_ascii=False,
                )

        if first_statement_idx is not None and lines[first_statement_idx].strip() == scene_line.strip() and not cleanup_applied:
            return json.dumps(
                {
                    "success": True,
                    "image_name": image_name,
                    "file": str(script_path.relative_to(project_dir)),
                    "message": "scene already present; no changes made",
                    "registered_asset": registration_changed,
                },
                indent=2,
                ensure_ascii=False,
            )

        if first_statement_idx is None:
            lines.insert(label_idx + 1, scene_line)
            message = f"Inserted opening scene '{image_name}' into label start."
        elif lines[first_statement_idx].lstrip().startswith("scene "):
            lines[first_statement_idx] = scene_line
            message = f"Replaced opening scene with '{image_name}' in label start."
        else:
            lines.insert(first_statement_idx, scene_line)
            message = f"Inserted opening scene '{image_name}' before the first statement in label start."

        script_path.write_text("".join(lines), encoding="utf-8")
        return json.dumps(
            {
                "success": True,
                "image_name": image_name,
                "file": str(script_path.relative_to(project_dir)),
                "message": message,
                "registered_asset": registration_changed,
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def set_project(path: str) -> str:
        """Set the active RenPy project path.

        Args:
            path: Absolute path to the RenPy project directory.
        """
        project = Path(path)
        game_dir = project / "game"
        if not project.exists():
            return f"Error: Path does not exist: {path}"
        if not game_dir.exists():
            return f"Error: Not a valid RenPy project (no 'game' directory): {path}"
        config.project_path = project
        return f"Project set to: {path}"

    @mcp.tool()
    async def get_project_info() -> str:
        """Get information about the current RenPy project structure.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        info = {
            "project_path": str(config.project_path),
            "game_dir": str(game_dir),
            "rpy_files": [],
            "image_dirs": [],
            "audio_dirs": [],
        }

        if game_dir.exists():
            for f in sorted(game_dir.rglob("*.rpy")):
                info["rpy_files"].append(str(f.relative_to(config.project_path)))

            for subdir in ["images", "gui"]:
                d = game_dir / subdir
                if d.exists():
                    info["image_dirs"].append(str(d.relative_to(config.project_path)))

            for subdir in ["audio", "music", "sfx", "sound"]:
                d = game_dir / subdir
                if d.exists():
                    info["audio_dirs"].append(str(d.relative_to(config.project_path)))

        return json.dumps(info, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def lint_project() -> str:
        """Run RenPy lint to check the project for errors and warnings.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."
        return await runner.lint()

    @mcp.tool()
    async def compile_project() -> str:
        """Compile RenPy scripts (.rpy -> .rpyc).

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."
        return await runner.compile()

    @mcp.tool()
    async def dump_project_metadata() -> str:
        """Dump project metadata (characters, labels, screens, etc.) to JSON.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."
        output_file = await runner.json_dump()
        if output_file.exists():
            return output_file.read_text(encoding="utf-8")
        return "Error: JSON dump was not created."

    @mcp.tool()
    async def build_project(
        formats: str = "pc,mac",
        destination: str = "",
    ) -> str:
        """Build the project for distribution.

        Args:
            formats: Comma-separated build formats. Options: pc, mac, linux, web, all.
            destination: Output directory for builds (default: project/builds/).

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        if not destination:
            dest_dir = config.project_path / "builds"
            dest_dir.mkdir(exist_ok=True)
            destination = str(dest_dir)

        try:
            args = ["distribute", str(config.project_path), "--destination", destination]
            if formats != "all":
                format_map = {
                    "pc": "pc",
                    "win": "pc",
                    "windows": "pc",
                    "mac": "mac",
                    "linux": "linux",
                    "web": "web",
                    "android": "android",
                }
                for fmt in formats.split(","):
                    fmt = fmt.strip().lower()
                    if fmt in format_map:
                        args.extend(["--package", format_map[fmt]])

            result = await runner.run_command(
                *args,
                project_path=config.sdk_path / "launcher",
                timeout=300.0,
            )
            output = result.stdout + result.stderr
            if result.returncode == 0:
                return f"Build completed successfully.\nOutput: {destination}\n\n{output[:1000]}"
            return f"Build failed (exit code {result.returncode}):\n{output[:2000]}"
        except Exception as e:
            return f"Build error: {e}"

    @mcp.tool()
    async def package_info() -> str:
        """Show build/packaging configuration from the project.

        Reads build classification rules, file patterns, and
        distribution settings from options.rpy.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        options_file = game_dir / "options.rpy"

        if not options_file.exists():
            return "Error: options.rpy not found."

        try:
            content = options_file.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading options.rpy: {e}"

        info = {
            "config_values": {},
            "build_rules": [],
        }

        config_re = re.compile(r'^\s*define\s+(config\.\w+|build\.\w+)\s*=\s*(.+)')
        build_classify_re = re.compile(r'^\s*build\.classify\s*\(\s*["\'](.+?)["\']\s*,\s*["\'](.+?)["\']\s*\)')

        for line in content.splitlines():
            m = config_re.match(line)
            if m:
                key = m.group(1)
                value = m.group(2).strip()
                info["config_values"][key] = value

            m = build_classify_re.match(line)
            if m:
                info["build_rules"].append({
                    "pattern": m.group(1),
                    "target": m.group(2),
                })

        return json.dumps(info, indent=2, ensure_ascii=False)
