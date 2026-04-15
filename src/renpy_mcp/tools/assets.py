"""Asset management tools — images, audio, unused asset detection."""

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

from ..ai.background_remover import BackgroundRemover
from ..ai.image_service import ImageService, _normalize_character_sizes
from ..config import RenPyConfig, get_settings
from ..services.project_manager import ProjectManager

# Asset file extensions
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif"}
AUDIO_EXTS = {".opus", ".ogg", ".mp3", ".wav", ".flac", ".aac"}
VIDEO_EXTS = {".webm", ".mp4", ".avi", ".ogv", ".mkv"}
ALL_ASSET_EXTS = IMAGE_EXTS | AUDIO_EXTS | VIDEO_EXTS


# Module-level references for testability
image_service: ImageService | None = None
background_remover: BackgroundRemover | None = None
_project_manager: ProjectManager | None = None


def register_asset_tools(mcp, config: RenPyConfig):
    """Register asset management MCP tools."""
    global image_service, background_remover, _project_manager
    settings = get_settings()
    _project_manager = ProjectManager(settings)
    image_service = ImageService(settings)
    background_remover = BackgroundRemover()

    @mcp.tool()
    async def generate_background(
        project_name: str,
        description: str,
        style: Optional[str] = None,
        base_filename: Optional[str] = None,
    ) -> str:
        """Generate a background image asset using Gemini.

        Args:
            project_name: Name of the project.
            description: Detailed scene description.
            style: Art style (optional).
            base_filename: Optional custom filename.
        """
        if not image_service.is_available():
            return json.dumps(
                {
                    "success": False,
                    "error": "Image generation service is not configured. Set RENPY_MCP_QWEN_API_KEY to enable image generation.",
                },
                indent=2,
                ensure_ascii=False,
            )

        project_dir = _project_manager.ensure_project_dir(project_name)
        prompt_parts = [
            description,
            "Create a detailed visual novel background scene, 16:9 ratio.",
        ]
        if style:
            prompt_parts.append(f"Style: {style}.")

        prompt = " ".join(prompt_parts)
        result = await image_service.generate_image(
            project_dir, prompt, "background", base_filename
        )

        relative_files = (
            [str(path.relative_to(project_dir)) for path in result.files]
            if result.success
            else []
        )
        payload = result.model_dump(mode="json")
        payload["project"] = project_name
        if relative_files:
            payload["relative_files"] = relative_files
        return json.dumps(payload, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def generate_character(
        project_name: str,
        character_name: str,
        description: str,
        pose: Optional[str] = None,
        emotion: Optional[str] = None,
        style: Optional[str] = None,
        generate_emotions: bool = False,
    ) -> str:
        """Generate a character sprite using Gemini.

        Args:
            project_name: Name of the project.
            character_name: Name of the character (lowercase, used for filename).
            description: Detailed visual description.
            pose: Character's pose (optional).
            emotion: Character's emotion/expression (optional).
            style: Art style (optional).
            generate_emotions: If True, create 5 emotion variants.
        """
        if not image_service.is_available():
            return json.dumps(
                {
                    "success": False,
                    "error": "Image generation service is not configured. Set RENPY_MCP_QWEN_API_KEY to enable image generation.",
                },
                indent=2,
                ensure_ascii=False,
            )

        project_dir = _project_manager.ensure_project_dir(project_name)
        prompt_parts = [
            f"Character name: {character_name}.",
            description,
            "Create a full body character sprite suitable for a Ren'Py visual novel with transparent background.",
            "IMPORTANT FRAMING: Character should fill approximately 70-75% of the vertical frame height, centered, with head near top and feet near bottom.",
            "Leave some empty space above the head and below the feet for consistent sizing across all characters.",
            "The character should be drawn at a consistent scale - not too close (filling entire frame) and not too far (tiny in frame).",
        ]
        if pose:
            prompt_parts.append(f"Pose: {pose}.")
        if emotion:
            prompt_parts.append(f"Emotion: {emotion}.")
        if style:
            prompt_parts.append(f"Art style: {style}.")

        prompt = " ".join(prompt_parts)
        result = await image_service.generate_image(
            project_dir,
            prompt,
            "character",
            base_name=character_name,
            generate_emotions=generate_emotions,
        )

        relative_files = (
            [str(path.relative_to(project_dir)) for path in result.files]
            if result.success
            else []
        )
        transparent_files: list[str] = []

        if result.success:
            for original_path in result.files:
                transparent_path = await asyncio.to_thread(
                    background_remover.remove_background, original_path
                )
                if transparent_path is not None:
                    try:
                        transparent_files.append(
                            str(transparent_path.relative_to(project_dir))
                        )
                    except ValueError:
                        transparent_files.append(str(transparent_path))

            character_assets_dir = project_dir / "assets" / "character"
            if character_assets_dir.exists():
                await asyncio.to_thread(
                    _normalize_character_sizes, character_assets_dir, target_height=750
                )

        payload = result.model_dump(mode="json")
        payload["project"] = project_name
        payload["character"] = character_name
        if relative_files:
            payload["relative_files"] = relative_files
        if transparent_files:
            payload["transparent_files"] = transparent_files
        return json.dumps(payload, indent=2, ensure_ascii=False)

    def _collect_assets(game_dir: Path) -> dict[str, list[dict]]:
        """Collect all asset files under game directory."""
        assets: dict[str, list[dict]] = {
            "images": [],
            "audio": [],
            "video": [],
        }
        for f in sorted(game_dir.rglob("*")):
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            rel = str(f.relative_to(game_dir)).replace("\\", "/")
            entry = {
                "path": rel,
                "name": f.stem,
                "size_kb": round(f.stat().st_size / 1024, 1),
            }
            if ext in IMAGE_EXTS:
                assets["images"].append(entry)
            elif ext in AUDIO_EXTS:
                assets["audio"].append(entry)
            elif ext in VIDEO_EXTS:
                assets["video"].append(entry)
        return assets

    def _collect_references(game_dir: Path) -> set[str]:
        """Collect all asset references from .rpy scripts."""
        refs = set()
        # Patterns that reference assets
        patterns = [
            # scene bg_name, show char_name
            re.compile(r'^\s*(?:scene|show|hide)\s+(.+?)(?:\s+(?:with|at|behind|onlayer|as|zorder)\s|$|:)'),
            # play music/sound "file"
            re.compile(r'^\s*(?:play|queue)\s+(?:music|sound|audio|voice)\s+["\']([^"\']+)["\']'),
            # play music/sound file (without quotes)
            re.compile(r'^\s*(?:play|queue)\s+(?:music|sound|audio|voice)\s+(\S+)'),
            # image x = "file"
            re.compile(r'^\s*image\s+.+\s*=\s*["\']([^"\']+)["\']'),
            # Quoted filenames with asset extensions
            re.compile(r'["\']([^"\']*\.(?:png|jpg|jpeg|webp|gif|opus|ogg|mp3|wav|webm|mp4))["\']'),
        ]

        for rpy_file in game_dir.rglob("*.rpy"):
            try:
                text = rpy_file.read_text(encoding="utf-8")
            except Exception:
                continue
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for pat in patterns:
                    for m in pat.finditer(line):
                        ref = m.group(1).strip()
                        refs.add(ref)
                        # Also add without path for image name matching
                        # "bg club" from "scene bg club"
                        refs.add(ref.replace("/", " "))
        return refs

    @mcp.tool()
    async def list_assets() -> str:
        """List all image, audio, and video assets in the project.

        Returns categorized asset list with file sizes.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        assets = _collect_assets(game_dir)

        summary = {
            "images_count": len(assets["images"]),
            "audio_count": len(assets["audio"]),
            "video_count": len(assets["video"]),
            "total_size_kb": round(sum(
                a["size_kb"]
                for cat in assets.values()
                for a in cat
            ), 1),
        }

        return json.dumps({"summary": summary, **assets}, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def find_unused_assets() -> str:
        """Find asset files that are not referenced in any .rpy script.

        Checks images, audio, and video files against scene/show/play statements
        and quoted filenames in scripts.

        Note: GUI assets (gui/ directory) are excluded as they are
        referenced by the framework implicitly.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        assets = _collect_assets(game_dir)
        refs = _collect_references(game_dir)

        # Normalize references for matching
        refs_lower = {r.lower() for r in refs}

        unused = []
        for category, items in assets.items():
            for asset in items:
                path = asset["path"]
                # Skip GUI assets — implicitly used by RenPy
                if path.startswith("gui/"):
                    continue
                # Skip cache and tl directories
                if path.startswith(("cache/", "tl/", "saves/")):
                    continue

                # Check if referenced by path, name, or RenPy image name
                name = asset["name"]
                # RenPy auto-discovers images: "images/bg club.jpg" → "bg club"
                renpy_name = name.lower()
                path_lower = path.lower()
                filename = Path(path).name.lower()

                is_used = any([
                    renpy_name in refs_lower,
                    path_lower in refs_lower,
                    filename in refs_lower,
                    # Check if any reference is a substring match for image names
                    any(renpy_name in r for r in refs_lower),
                    any(r in renpy_name for r in refs_lower if len(r) > 3),
                ])

                if not is_used:
                    unused.append({
                        "path": path,
                        "category": category,
                        "size_kb": asset["size_kb"],
                    })

        if not unused:
            return "No unused assets found. All assets are referenced in scripts."

        total_waste = round(sum(u["size_kb"] for u in unused), 1)
        result = {
            "unused_count": len(unused),
            "total_wasted_kb": total_waste,
            "unused": unused,
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def list_audio() -> str:
        """List all audio files with their usage in scripts.

        Shows music, sound effects, and voice files along with where
        they are played in the game scripts.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        assets = _collect_assets(game_dir)
        refs = _collect_references(game_dir)

        # Collect play/queue references with their locations
        audio_usage = {}
        play_re = re.compile(
            r'^\s*(?:play|queue)\s+(?:music|sound|audio|voice)\s+["\']?([^"\']+?)["\']?\s*(?:$|fadein|fadeout|loop|noloop|if_changed)'
        )

        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            if rpy_file.name.startswith("_mcp"):
                continue
            try:
                lines = rpy_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            rel = str(rpy_file.relative_to(game_dir))
            for i, line in enumerate(lines):
                m = play_re.match(line.strip())
                if m:
                    track = m.group(1).strip()
                    if track not in audio_usage:
                        audio_usage[track] = []
                    audio_usage[track].append(f"{rel}:{i+1}")

        audio_files = []
        for asset in assets["audio"]:
            path = asset["path"]
            name = asset["name"]
            used_at = audio_usage.get(path, [])
            # Also check by name
            if not used_at:
                used_at = audio_usage.get(name, [])
            audio_files.append({
                "path": path,
                "name": name,
                "size_kb": asset["size_kb"],
                "used_at": used_at,
                "is_used": bool(used_at),
            })

        result = {
            "total_files": len(audio_files),
            "used": sum(1 for a in audio_files if a["is_used"]),
            "unused": sum(1 for a in audio_files if not a["is_used"]),
            "audio_references": {k: v for k, v in audio_usage.items()},
            "files": audio_files,
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def image_size_check() -> str:
        """Check image dimensions against project resolution.

        Verifies that background images match the game's configured
        screen dimensions and flags oversized or undersized images.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"

        # Try to get screen dimensions from gui.rpy or options.rpy
        screen_width, screen_height = 1280, 720  # defaults
        for cfg_file in ["gui.rpy", "options.rpy"]:
            cfg_path = game_dir / cfg_file
            if cfg_path.exists():
                try:
                    text = cfg_path.read_text(encoding="utf-8")
                    w_match = re.search(r'config\.screen_width\s*=\s*(\d+)', text)
                    h_match = re.search(r'config\.screen_height\s*=\s*(\d+)', text)
                    if w_match:
                        screen_width = int(w_match.group(1))
                    if h_match:
                        screen_height = int(h_match.group(1))
                except Exception:
                    pass

        import struct
        issues = []
        checked = 0

        for img_file in sorted(game_dir.rglob("*")):
            if not img_file.is_file():
                continue
            ext = img_file.suffix.lower()
            if ext not in IMAGE_EXTS:
                continue

            rel = str(img_file.relative_to(game_dir)).replace("\\", "/")
            # Skip GUI assets
            if rel.startswith("gui/"):
                continue

            width, height = None, None

            try:
                with open(img_file, "rb") as f:
                    header = f.read(32)

                    # PNG
                    if header[:8] == b'\x89PNG\r\n\x1a\n':
                        if len(header) >= 24:
                            width = struct.unpack('>I', header[16:20])[0]
                            height = struct.unpack('>I', header[20:24])[0]

                    # JPEG
                    elif header[:2] == b'\xff\xd8':
                        f.seek(0)
                        data = f.read()
                        i = 2
                        while i < len(data) - 9:
                            if data[i] == 0xFF:
                                marker = data[i + 1]
                                if marker in (0xC0, 0xC1, 0xC2):
                                    height = struct.unpack('>H', data[i+5:i+7])[0]
                                    width = struct.unpack('>H', data[i+7:i+9])[0]
                                    break
                                elif marker == 0xD9:
                                    break
                                elif marker in (0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0x01):
                                    i += 2
                                else:
                                    length = struct.unpack('>H', data[i+2:i+4])[0]
                                    i += 2 + length
                            else:
                                i += 1

                    # WebP
                    elif header[:4] == b'RIFF' and header[8:12] == b'WEBP':
                        if header[12:16] == b'VP8 ':
                            if len(header) >= 30:
                                width = struct.unpack('<H', header[26:28])[0] & 0x3FFF
                                height = struct.unpack('<H', header[28:30])[0] & 0x3FFF

            except Exception:
                continue

            if width is None or height is None:
                continue

            checked += 1
            # Check for issues
            is_bg = "bg" in rel.lower() or "background" in rel.lower()

            if is_bg:
                if width != screen_width or height != screen_height:
                    severity = "warning"
                    if width < screen_width or height < screen_height:
                        severity = "error"
                    issues.append({
                        "file": rel,
                        "width": width,
                        "height": height,
                        "expected": f"{screen_width}x{screen_height}",
                        "severity": severity,
                        "detail": f"Background image is {width}x{height}, expected {screen_width}x{screen_height}",
                    })
            elif width > screen_width * 2 or height > screen_height * 2:
                issues.append({
                    "file": rel,
                    "width": width,
                    "height": height,
                    "severity": "warning",
                    "detail": f"Image is very large ({width}x{height}), may waste memory",
                })

        result = {
            "screen_resolution": f"{screen_width}x{screen_height}",
            "images_checked": checked,
            "issues_count": len(issues),
            "issues": issues,
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
