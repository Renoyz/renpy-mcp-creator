"""RenPy documentation resource — searchable docs for AI context."""

import asyncio
import logging
import re
from html.parser import HTMLParser
from pathlib import Path

from ..config import RenPyConfig

logger = logging.getLogger(__name__)


class _HTMLTextExtractor(HTMLParser):
    """Extract clean text from HTML, preserving code blocks."""

    def __init__(self):
        super().__init__()
        self._text: list[str] = []
        self._in_main = False
        self._depth = 0
        self._skip_tags = {"script", "style", "nav"}
        self._skip_depth = 0
        self._in_code = False
        self._in_pre = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if attrs_dict.get("itemprop") == "articleBody" or attrs_dict.get("role") == "main":
            self._in_main = True
            self._depth = 0

        if self._in_main:
            self._depth += 1

        if tag in self._skip_tags:
            self._skip_depth += 1

        if tag == "pre":
            self._in_pre = True
            self._text.append("\n```\n")
        elif tag == "code" and not self._in_pre:
            self._in_code = True
            self._text.append("`")
        elif tag in ("h1", "h2", "h3", "h4"):
            level = int(tag[1])
            self._text.append("\n" + "#" * level + " ")
        elif tag == "p":
            self._text.append("\n\n")
        elif tag == "li":
            self._text.append("\n- ")
        elif tag == "br":
            self._text.append("\n")
        elif tag == "dt":
            self._text.append("\n**")

    def handle_endtag(self, tag):
        if self._in_main:
            self._depth -= 1
            if self._depth <= 0:
                self._in_main = False

        if tag in self._skip_tags:
            self._skip_depth = max(0, self._skip_depth - 1)

        if tag == "pre":
            self._in_pre = False
            self._text.append("\n```\n")
        elif tag == "code" and not self._in_pre:
            self._in_code = False
            self._text.append("`")
        elif tag == "dt":
            self._text.append("**\n")

    def handle_data(self, data):
        if self._in_main and self._skip_depth == 0:
            self._text.append(data)

    def get_text(self) -> str:
        return "".join(self._text).strip()


async def _extract_doc_text(html_path: Path) -> str:
    """Extract clean text from a RenPy doc HTML file."""
    try:
        html = await asyncio.to_thread(
            lambda: html_path.read_text(encoding="utf-8")
        )
    except Exception:
        logger.warning("Failed to read doc text from %s", html_path, exc_info=True)
        return ""

    parser = _HTMLTextExtractor()
    parser.feed(html)
    text = parser.get_text()

    # Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


# Topic mapping: friendly names → HTML filenames
TOPIC_MAP = {
    # Basics
    "quickstart": "quickstart",
    "language": "language_basics",
    "labels": "label",
    "dialogue": "dialogue",
    "menus": "menus",
    "choices": "menus",

    # Display
    "images": "displaying_images",
    "displayables": "displayables",
    "atl": "atl",
    "transforms": "atl",
    "transitions": "atl",
    "layeredimage": "layeredimage",
    "3d": "3dstage",

    # Screens
    "screens": "screens",
    "screen_actions": "screen_actions",
    "screen_special": "screen_special",
    "screen_optimization": "screen_optimization",
    "screen_python": "screen_python",

    # Audio
    "audio": "audio",
    "music": "audio",
    "sound": "audio",
    "voice": "audio",
    "audio_filters": "audio_filters",

    # Python
    "python": "python",
    "conditional": "conditional",
    "config": "config",
    "preferences": "preferences",
    "persistent": "persistent",
    "save": "save_load_rollback",
    "load": "save_load_rollback",

    # Input
    "input": "input",
    "drag_drop": "drag_drop",
    "gesture": "gesture",
    "keymap": "keymap",

    # Characters
    "characters": "dialogue",
    "nvl": "nvl_mode",
    "history": "history",
    "side_image": "side_image",
    "bubble": "bubble",

    # Style
    "style": "style",
    "style_properties": "style_properties",
    "gui": "gui",
    "gui_advanced": "gui_advanced",

    # Advanced
    "cdd": "cdd",
    "cds": "cds",
    "custom_text_tags": "custom_text_tags",
    "sprites": "sprites",
    "movie": "movie",
    "model": "model",
    "shader": "shader_parts",
    "matrix": "matrixcolor",

    # Testing & Dev
    "testcases": "testcases",
    "developer_tools": "developer_tools",
    "cli": "cli",
    "screenshot": "screenshot",
    "lint": "cli",

    # Build & Deploy
    "build": "build",
    "android": "android",
    "ios": "ios",
    "web": "fetch",
    "distributor": "distributor",
    "multiple": "multiple",

    # Translation
    "translation": "translation",
    "translating": "translating_renpy",

    # Text
    "text": "text",
    "text_tags": "custom_text_tags",
    "textshaders": "textshaders",

    # Lifecycle
    "lifecycle": "lifecycle",
    "splashscreen": "splashscreen_presplash",
    "store_variables": "store_variables",
    "namespaces": "namespaces",
    "modes": "modes",
    "mouse": "mouse",

    # Other
    "achievement": "achievement",
    "live2d": "live2d",
    "rooms": "rooms",
    "color": "color_class",
    "security": "security",
    "changelog": "changelog",
    "reserved": "reserved",
    "statement_equivalents": "statement_equivalents",
    "file_python": "file_python",
    "environment_variables": "environment_variables",
    "director": "director",
    "transforms": "transforms",
    "transitions": "transitions",
    "transform_properties": "transform_properties",
    "voice": "voice",
    "updater": "updater",
    "web": "web",
    "android_packaging": "android-packaging",
    "character_callbacks": "character_callbacks",
    "self_voicing": "self_voicing",
}


def register_doc_resources(mcp, config: RenPyConfig):
    """Register documentation resources and tools."""

    def _doc_dir() -> Path:
        return config.sdk_path / "doc"

    @mcp.tool()
    async def search_docs(query: str) -> str:
        """Search RenPy documentation for a topic or keyword.

        Args:
            query: Topic name (e.g., "dialogue", "screens", "atl", "audio",
                   "testcases", "config") or a keyword to search across all docs.

        Returns:
            Relevant documentation text extracted from RenPy's official docs.
        """
        doc_dir = _doc_dir()
        if not doc_dir.exists():
            return "Error: RenPy documentation not found at SDK path."

        query_lower = query.lower().strip()

        # Try exact topic match first
        if query_lower in TOPIC_MAP:
            html_file = doc_dir / f"{TOPIC_MAP[query_lower]}.html"
            if html_file.exists():
                text = await _extract_doc_text(html_file)
                if text:
                    # Truncate very long docs
                    if len(text) > 15000:
                        text = text[:15000] + "\n\n... (truncated, use a more specific query)"
                    return f"# RenPy Documentation: {query}\n\n{text}"

        # Keyword search across all docs
        results = []
        for html_file in sorted(doc_dir.glob("*.html")):
            if html_file.name in ("genindex.html", "search.html", "py-function-class-index.html"):
                continue
            text = await _extract_doc_text(html_file)
            if not text:
                continue

            # Search for query in text (case-insensitive)
            lower_text = text.lower()
            if query_lower in lower_text:
                # Find relevant paragraphs
                paragraphs = text.split("\n\n")
                matches = []
                for para in paragraphs:
                    if query_lower in para.lower():
                        matches.append(para.strip())
                if matches:
                    topic_name = html_file.stem.replace("_", " ").title()
                    result_text = "\n\n".join(matches[:5])
                    results.append(f"## {topic_name}\n\n{result_text}")

        if results:
            combined = "\n\n---\n\n".join(results[:5])
            if len(combined) > 15000:
                combined = combined[:15000] + "\n\n... (truncated)"
            return f"# Search results for: {query}\n\n{combined}"

        return f"No documentation found for '{query}'. Try: {', '.join(sorted(TOPIC_MAP.keys())[:20])}, ..."

    @mcp.tool()
    async def list_doc_topics() -> str:
        """List all available RenPy documentation topics."""
        categories = {
            "Basics": ["quickstart", "language", "labels", "dialogue", "menus", "text"],
            "Display": ["images", "displayables", "atl", "transforms", "transitions",
                        "transform_properties", "layeredimage", "3d"],
            "Screens": ["screens", "screen_actions", "screen_special", "screen_python"],
            "Audio": ["audio", "audio_filters", "voice"],
            "Python": ["python", "conditional", "config", "preferences",
                        "persistent", "save", "store_variables", "file_python"],
            "Characters": ["characters", "nvl", "history", "side_image", "bubble",
                           "character_callbacks"],
            "Style & GUI": ["style", "style_properties", "gui", "gui_advanced"],
            "Input": ["input", "drag_drop", "keymap", "mouse"],
            "Advanced": ["cdd", "cds", "custom_text_tags", "textshaders",
                         "sprites", "movie", "shader", "model"],
            "Testing & Dev": ["testcases", "developer_tools", "cli", "screenshot",
                              "director", "lifecycle"],
            "Build & Deploy": ["build", "android", "android_packaging", "ios",
                               "web", "distributor", "updater"],
            "Translation": ["translation", "translating"],
            "Other": ["achievement", "live2d", "rooms", "color", "security",
                       "self_voicing", "environment_variables"],
        }

        lines = ["# RenPy Documentation Topics\n"]
        lines.append("Use search_docs(topic) to read any topic.\n")
        for cat, topics in categories.items():
            lines.append(f"\n## {cat}")
            for t in topics:
                lines.append(f"  - {t}")

        return "\n".join(lines)
