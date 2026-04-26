"""Translation management tools."""

import json
import logging
import re
from pathlib import Path

from ..config import RenPyConfig
from ..renpy_runner import RenPyRunner

logger = logging.getLogger(__name__)


def register_translation_tools(mcp, config: RenPyConfig, runner: RenPyRunner):
    """Register translation management MCP tools."""

    def _get_tl_dir(game_dir: Path) -> Path:
        return game_dir / "tl"

    def _parse_translation_file(filepath: Path) -> list[dict]:
        """Parse a RenPy translation file and extract entries.

        Handles two formats:
        1. Dialogue: translate <lang> <id>:  (followed by # comment + translated line)
        2. Strings:  translate <lang> strings:  (followed by old/new pairs)
        """
        entries = []
        try:
            lines = filepath.read_text(encoding="utf-8").splitlines()
        except Exception:
            logger.warning("Failed to read translation file: %s", filepath, exc_info=True)
            return entries

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Format 2: String translations — translate <lang> strings:
            m = re.match(r'^translate\s+(\w+)\s+strings:', line)
            if m:
                lang = m.group(1)
                j = i + 1
                old_text = ""
                while j < len(lines):
                    sline = lines[j].strip()
                    # Stop at next translate block
                    if sline.startswith("translate ") and sline.endswith(":"):
                        break
                    if sline.startswith('old "') or sline.startswith("old '"):
                        old_text = sline[4:].strip().strip('"').strip("'")
                    elif sline.startswith('new "') or sline.startswith("new '"):
                        new_text = sline[4:].strip().strip('"').strip("'")
                        is_done = bool(new_text and new_text != old_text)
                        entries.append({
                            "id": f"string_{len(entries)}",
                            "language": lang,
                            "original": old_text,
                            "translated": new_text,
                            "line": j + 1,
                            "is_translated": is_done,
                        })
                        old_text = ""
                    j += 1
                i = j
                continue

            # Format 1: Dialogue translations — translate <lang> <hash_id>:
            m = re.match(r'^translate\s+(\w+)\s+(\w+):', line)
            if m:
                lang = m.group(1)
                entry_id = m.group(2)

                original = ""
                translated = ""

                # Scan ahead, skipping blank lines within the block
                j = i + 1
                while j < len(lines):
                    sline = lines[j].strip()
                    # Stop at next translate block or file reference comment
                    if sline.startswith("translate ") and sline.endswith(":"):
                        break
                    # Source reference comment like "# game/script.rpy:19"
                    if re.match(r'^#\s*game/', sline):
                        break

                    if sline.startswith("# ") and not re.match(r'^#\s*game/', sline):
                        # Original text in comment
                        original = sline[2:]
                    elif sline and not sline.startswith("#"):
                        # Translated line (may start with character name or quote)
                        translated = sline
                    j += 1

                # Determine if translated: translated line exists and differs from original
                is_done = bool(translated and translated != original)
                entries.append({
                    "id": entry_id,
                    "language": lang,
                    "original": original,
                    "translated": translated,
                    "line": i + 1,
                    "is_translated": is_done,
                })
                i = j
                continue
            i += 1

        return entries

    @mcp.tool()
    async def list_translations(use_renpy_count: bool = False) -> str:
        """List all available translation languages and their completion status.

        Args:
            use_renpy_count: If True, use RenPy's built-in --count for
                accurate missing translation counts (slower but precise).
                If False, parse translation files directly (faster).

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        tl_dir = _get_tl_dir(game_dir)
        if not tl_dir.exists():
            return "No translations directory found (game/tl/)."

        languages = {}

        if use_renpy_count:
            # Use RenPy's --count flag for accurate counts
            for lang_dir in sorted(tl_dir.iterdir()):
                if not lang_dir.is_dir() or lang_dir.name == "None":
                    continue
                lang = lang_dir.name
                try:
                    result = await runner.run_command(
                        "translate", lang, "--count",
                        project_path=config.project_path,
                        timeout=30.0,
                    )
                    output = result.stdout + result.stderr
                    # Parse: "lang: X missing dialogue translations, Y missing string translations."
                    m = re.search(
                        r'(\d+)\s+missing dialogue.*?(\d+)\s+missing string',
                        output
                    )
                    if m:
                        languages[lang] = {
                            "missing_dialogue": int(m.group(1)),
                            "missing_strings": int(m.group(2)),
                        }
                    else:
                        languages[lang] = {"raw_output": output.strip()[:200]}
                except Exception as e:
                    logger.warning("Failed to count translations for language '%s': %s", lang, e, exc_info=True)
                    languages[lang] = {"error": str(e)[:200]}
        else:
            # Fast: parse translation files directly
            for lang_dir in sorted(tl_dir.iterdir()):
                if not lang_dir.is_dir() or lang_dir.name == "None":
                    continue
                lang = lang_dir.name
                total = 0
                translated = 0
                for rpy_file in lang_dir.rglob("*.rpy"):
                    entries = _parse_translation_file(rpy_file)
                    total += len(entries)
                    translated += sum(1 for e in entries if e["is_translated"])

                languages[lang] = {
                    "total_strings": total,
                    "translated": translated,
                    "untranslated": total - translated,
                    "completion_pct": round(translated / total * 100, 1) if total > 0 else 0,
                }

        if not languages:
            return "No translation languages found."
        return json.dumps(languages, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def find_untranslated(language: str) -> str:
        """Find untranslated strings for a specific language.

        Args:
            language: Language code (e.g., "japanese", "french", "spanish").

        Returns:
            List of untranslated entries with original text and file locations.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        lang_dir = _get_tl_dir(game_dir) / language
        if not lang_dir.exists():
            available = [
                d.name for d in _get_tl_dir(game_dir).iterdir()
                if d.is_dir() and d.name != "None"
            ]
            return f"Error: Language '{language}' not found. Available: {', '.join(available)}"

        untranslated = []
        for rpy_file in sorted(lang_dir.rglob("*.rpy")):
            rel_path = str(rpy_file.relative_to(lang_dir))
            entries = _parse_translation_file(rpy_file)
            for entry in entries:
                if not entry["is_translated"]:
                    untranslated.append({
                        "file": rel_path,
                        "line": entry["line"],
                        "id": entry["id"],
                        "original": entry["original"],
                        "current": entry["translated"],
                    })

        if not untranslated:
            return f"All strings are translated for '{language}'."

        result = {
            "language": language,
            "untranslated_count": len(untranslated),
            "entries": untranslated,
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def translation_diff(language: str) -> str:
        """Find translation entries where the original text may have changed.

        Compares the commented original text in translation files against
        the current source script to detect outdated translations.

        Args:
            language: Language code to check.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        lang_dir = _get_tl_dir(game_dir) / language
        if not lang_dir.exists():
            return f"Error: Language '{language}' not found."

        # Build a map of current source dialogue lines by hash/ID
        # The translation IDs are hashes of the original text location
        # We can compare the commented originals in tl files with current source

        outdated = []
        for rpy_file in sorted(lang_dir.rglob("*.rpy")):
            rel_path = str(rpy_file.relative_to(lang_dir))
            try:
                lines = rpy_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                logger.warning("Failed to read translation file for diff: %s", rpy_file, exc_info=True)
                continue

            for i, line in enumerate(lines):
                stripped = line.strip()
                # Look for source file references: # game/script.rpy:19
                ref_match = re.match(r'^#\s*(game/.+\.rpy):(\d+)', stripped)
                if ref_match:
                    src_file = game_dir / ref_match.group(1).replace("game/", "")
                    src_line = int(ref_match.group(2))

                    # Get the original text from comment on next lines
                    orig_text = ""
                    for j in range(i + 2, min(i + 5, len(lines))):
                        cline = lines[j].strip()
                        if cline.startswith("# "):
                            orig_text = cline[2:]
                            break

                    if not orig_text or not src_file.exists():
                        continue

                    # Check current source
                    try:
                        src_lines = src_file.read_text(encoding="utf-8").splitlines()
                        if src_line - 1 < len(src_lines):
                            current = src_lines[src_line - 1].strip()
                            if orig_text != current and current:
                                outdated.append({
                                    "file": rel_path,
                                    "line": i + 1,
                                    "source_file": ref_match.group(1),
                                    "source_line": src_line,
                                    "original_in_tl": orig_text,
                                    "current_in_source": current,
                                })
                    except Exception:
                        logger.warning("Failed to compare translation source file: %s", src_file, exc_info=True)
                        continue

        if not outdated:
            return f"No outdated translations found for '{language}'."

        result = {
            "language": language,
            "outdated_count": len(outdated),
            "entries": outdated,
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def generate_translations(language: str) -> str:
        """Generate translation files for a new language using RenPy CLI.

        This creates stub translation files that can then be filled in.

        Args:
            language: Language code for the new translation (e.g., "german").

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        lang_dir = _get_tl_dir(game_dir) / language

        # RenPy generate translations command
        try:
            result = await runner.run_command(
                "translate", language,
                project_path=config.project_path,
                timeout=60.0,
            )
            output = result.stdout + result.stderr
        except Exception as e:
            logger.warning("Failed to generate translations for '%s': %s", language, e, exc_info=True)
            output = str(e)

        if lang_dir.exists():
            file_count = sum(1 for _ in lang_dir.rglob("*.rpy"))
            return (
                f"Translation files generated for '{language}'.\n"
                f"Location: {lang_dir}\n"
                f"Files created: {file_count}\n"
                f"Output: {output[:500]}"
            )
        return f"Translation generation output:\n{output[:1000]}"

    @mcp.tool()
    async def extract_translation_strings(language: str) -> str:
        """Extract translatable strings to JSON for external translation tools.

        Exports all translatable strings for a language to a JSON file
        that can be sent to translators or translation services.

        Args:
            language: Language code to extract strings for.

        Returns:
            Path to the generated JSON file and a preview of its content.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        output_file = game_dir / f"tl_{language}_strings.json"

        try:
            result = await runner.run_command(
                "extract_strings", language, str(output_file),
                project_path=config.project_path,
                timeout=60.0,
            )
            output = result.stdout + result.stderr
        except Exception as e:
            logger.warning("Failed to extract strings for '%s': %s", language, e, exc_info=True)
            return f"Error extracting strings: {e}"

        if output_file.exists():
            content = output_file.read_text(encoding="utf-8")
            preview = content[:2000]
            return (
                f"Strings extracted to: {output_file}\n"
                f"Size: {len(content)} chars\n\n"
                f"Preview:\n{preview}"
            )
        return f"Extract output:\n{output[:1000]}"

    @mcp.tool()
    async def merge_translation_strings(language: str, json_file: str) -> str:
        """Merge translated strings from JSON back into RenPy translation files.

        Args:
            language: Target language code.
            json_file: Path to JSON file with translations.

        Returns:
            Merge result output.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        json_path = Path(json_file)
        if not json_path.exists():
            return f"Error: JSON file not found: {json_file}"

        try:
            result = await runner.run_command(
                "merge_strings", language, str(json_path),
                project_path=config.project_path,
                timeout=60.0,
            )
            return result.stdout + result.stderr or "Merge completed successfully."
        except Exception as e:
            logger.warning("Failed to merge translation strings for '%s': %s", language, e, exc_info=True)
            return f"Error merging strings: {e}"

    @mcp.tool()
    async def auto_translate(language: str, max_entries: int = 50) -> str:
        """Prepare untranslated strings for AI-assisted translation.

        Extracts untranslated entries with surrounding context, formatted
        so the AI can translate them. After translation, use
        merge_translation_strings to write them back.

        Args:
            language: Language code (e.g., "japanese", "french").
            max_entries: Maximum number of entries to return (default 50).

        Returns:
            JSON with untranslated entries and context, ready for AI translation.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        lang_dir = _get_tl_dir(game_dir) / language
        if not lang_dir.exists():
            available = [
                d.name for d in _get_tl_dir(game_dir).iterdir()
                if d.is_dir() and d.name != "None"
            ]
            return f"Error: Language '{language}' not found. Available: {', '.join(available)}"

        entries = []
        for rpy_file in sorted(lang_dir.rglob("*.rpy")):
            rel_path = str(rpy_file.relative_to(lang_dir))
            parsed = _parse_translation_file(rpy_file)

            # Read original source for context
            try:
                tl_lines = rpy_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                logger.warning("Failed to read translation file for auto-translate: %s", rpy_file, exc_info=True)
                tl_lines = []

            for entry in parsed:
                if entry["is_translated"]:
                    continue
                if len(entries) >= max_entries:
                    break

                # Get surrounding context (2 lines before and after in the tl file)
                line_idx = entry["line"] - 1
                context_start = max(0, line_idx - 2)
                context_end = min(len(tl_lines), line_idx + 3)
                context = "\n".join(tl_lines[context_start:context_end])

                entries.append({
                    "file": rel_path,
                    "line": entry["line"],
                    "id": entry["id"],
                    "original": entry["original"],
                    "current_translation": entry["translated"],
                    "context": context,
                })

            if len(entries) >= max_entries:
                break

        if not entries:
            return f"All strings are translated for '{language}'."

        result = {
            "language": language,
            "total_untranslated": len(entries),
            "instruction": (
                f"Translate the following {len(entries)} entries to {language}. "
                "For each entry, provide the translated text. "
                "Preserve any RenPy tags like {b}, {i}, {color}, etc. "
                "Keep character names in their original form unless a localized name exists."
            ),
            "entries": entries,
        }
        return json.dumps(result, indent=2, ensure_ascii=False)
