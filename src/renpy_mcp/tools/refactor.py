"""Refactoring tools — rename, extract, insert operations on RenPy scripts."""

import json
import re
from pathlib import Path

_label_re = re.compile(r'^label\s+(\w+)(?:\s*\(.*\))?\s*:')

from ..config import RenPyConfig


def register_refactor_tools(mcp, config: RenPyConfig):
    """Register refactoring MCP tools."""

    def _get_game_dir() -> Path:
        if not config.project_path:
            raise ValueError("No project set.")
        return config.project_path / "game"

    @mcp.tool()
    async def rename_character(old_name: str, new_name: str, dry_run: bool = True) -> str:
        """Rename a character variable across all script files.

        Updates the define statement, all dialogue lines, show/hide statements,
        and condition checks that reference the character.

        Args:
            old_name: Current character variable name (e.g., "s").
            new_name: New character variable name (e.g., "sylvie").
            dry_run: If True, preview changes without modifying files (default True).

        Requires set_project to be called first.
        """
        try:
            game_dir = _get_game_dir()
        except ValueError as e:
            return str(e)

        changes = []
        # Patterns to match the old character name in various contexts
        patterns = [
            # define old = Character(...)
            (re.compile(r'^(\s*define\s+)' + re.escape(old_name) + r'(\s*=\s*Character\s*\()'), r'\g<1>' + new_name + r'\2'),
            # old "dialogue"
            (re.compile(r'^(\s+)' + re.escape(old_name) + r'(\s+".*")'), r'\1' + new_name + r'\2'),
            # show old, hide old
            (re.compile(r'^(\s*(?:show|hide)\s+)' + re.escape(old_name) + r'(\s|$)'), r'\1' + new_name + r'\2'),
            # if old, elif old (in conditions)
            (re.compile(r'^(\s*(?:if|elif|while)\s+.*)' + r'\b' + re.escape(old_name) + r'\b'), None),
        ]

        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            if rpy_file.name.startswith("_mcp"):
                continue
            try:
                content = rpy_file.read_text(encoding="utf-8")
            except Exception:
                continue

            rel = str(rpy_file.relative_to(game_dir))
            lines = content.splitlines()
            modified = False
            new_lines = []

            for i, line in enumerate(lines):
                original_line = line
                for pattern, replacement in patterns:
                    if replacement is not None:
                        new_line = pattern.sub(replacement, line)
                        if new_line != line:
                            changes.append({
                                "file": rel,
                                "line": i + 1,
                                "old": line.rstrip(),
                                "new": new_line.rstrip(),
                            })
                            line = new_line
                            modified = True

                new_lines.append(line)

            if modified and not dry_run:
                new_text = "\n".join(new_lines)
                if content.endswith("\n"):
                    new_text += "\n"
                rpy_file.write_text(new_text, encoding="utf-8")

        if not changes:
            return f"No references to character '{old_name}' found."

        result = {
            "old_name": old_name,
            "new_name": new_name,
            "dry_run": dry_run,
            "changes_count": len(changes),
            "changes": changes[:50],
        }
        if dry_run:
            result["instruction"] = "Set dry_run=False to apply these changes."
        else:
            result["status"] = "Changes applied successfully."
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def rename_label(old_name: str, new_name: str, dry_run: bool = True) -> str:
        """Rename a label and update all jump/call references.

        Args:
            old_name: Current label name.
            new_name: New label name.
            dry_run: If True, preview changes without modifying files (default True).

        Requires set_project to be called first.
        """
        try:
            game_dir = _get_game_dir()
        except ValueError as e:
            return str(e)

        changes = []
        patterns = [
            # label old_name:
            (re.compile(r'^(\s*label\s+)' + re.escape(old_name) + r'(\s*:)'), r'\g<1>' + new_name + r'\2'),
            # jump old_name
            (re.compile(r'^(\s*jump\s+)' + re.escape(old_name) + r'(\s*$)'), r'\g<1>' + new_name + r'\2'),
            # call old_name
            (re.compile(r'^(\s*call\s+)' + re.escape(old_name) + r'(\s|$)'), r'\g<1>' + new_name + r'\2'),
        ]

        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            if rpy_file.name.startswith("_mcp"):
                continue
            try:
                content = rpy_file.read_text(encoding="utf-8")
            except Exception:
                continue

            rel = str(rpy_file.relative_to(game_dir))
            lines = content.splitlines()
            modified = False
            new_lines = []

            for i, line in enumerate(lines):
                original_line = line
                for pattern, replacement in patterns:
                    new_line = pattern.sub(replacement, line)
                    if new_line != line:
                        changes.append({
                            "file": rel,
                            "line": i + 1,
                            "old": line.rstrip(),
                            "new": new_line.rstrip(),
                        })
                        line = new_line
                        modified = True
                new_lines.append(line)

            if modified and not dry_run:
                new_text = "\n".join(new_lines)
                if content.endswith("\n"):
                    new_text += "\n"
                rpy_file.write_text(new_text, encoding="utf-8")

        if not changes:
            return f"No references to label '{old_name}' found."

        result = {
            "old_name": old_name,
            "new_name": new_name,
            "dry_run": dry_run,
            "changes_count": len(changes),
            "changes": changes[:50],
        }
        if dry_run:
            result["instruction"] = "Set dry_run=False to apply these changes."
        else:
            result["status"] = "Changes applied successfully."
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def extract_route(
        start_label: str,
        output_file: str = "",
    ) -> str:
        """Extract a complete story route into a separate file.

        Follows jumps and calls from the start label to collect all
        labels in that route, then outputs them as a standalone script.

        Args:
            start_label: Label to start tracing from.
            output_file: Optional output .rpy filename (relative to game/).
                        If empty, returns the extracted code as text.

        Requires set_project to be called first.
        """
        try:
            game_dir = _get_game_dir()
        except ValueError as e:
            return str(e)

        # Parse all scripts to find labels and their content
        all_labels = {}
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            if rpy_file.name.startswith("_mcp") or str(rpy_file.relative_to(game_dir)).startswith("tl"):
                continue
            try:
                lines = rpy_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue

            current_label = None
            label_lines = []
            for i, line in enumerate(lines):
                stripped = line.strip()
                lm = _label_re.match(stripped)
                if lm:
                    if current_label and label_lines:
                        all_labels[current_label] = {
                            "lines": label_lines,
                            "jumps": [],
                        }
                    current_label = lm.group(1)
                    label_lines = [line]
                elif current_label is not None:
                    label_lines.append(line)
                    if stripped.startswith("jump "):
                        target = stripped[5:].strip()
                        all_labels.setdefault(current_label, {"lines": [], "jumps": []})
                        all_labels[current_label]["jumps"].append(target)
                    elif stripped.startswith("call "):
                        target = stripped[5:].strip().split()[0]
                        all_labels.setdefault(current_label, {"lines": [], "jumps": []})
                        all_labels[current_label]["jumps"].append(target)

            if current_label and label_lines:
                all_labels[current_label] = all_labels.get(current_label, {"lines": [], "jumps": []})
                all_labels[current_label]["lines"] = label_lines

        if start_label not in all_labels:
            return f"Error: Label '{start_label}' not found."

        # BFS to collect all reachable labels
        visited = set()
        queue = [start_label]
        route_labels = []

        while queue:
            label = queue.pop(0)
            if label in visited:
                continue
            visited.add(label)
            if label in all_labels:
                route_labels.append(label)
                for jump_target in all_labels[label].get("jumps", []):
                    if jump_target not in visited:
                        queue.append(jump_target)

        # Build output
        output_lines = [f"# Route extracted from label '{start_label}'", f"# Labels: {', '.join(route_labels)}", ""]
        for label in route_labels:
            if label in all_labels:
                output_lines.extend(all_labels[label]["lines"])
                output_lines.append("")

        code = "\n".join(output_lines)

        if output_file:
            out_path = game_dir / output_file
            out_path.write_text(code, encoding="utf-8")
            return f"Route extracted to: {out_path}\nLabels: {', '.join(route_labels)}\nLines: {len(output_lines)}"

        return code

    @mcp.tool()
    async def insert_dialogue(
        file_path: str,
        line_number: int,
        character: str = "",
        text: str = "",
        raw_lines: str = "",
    ) -> str:
        """Insert dialogue or script lines at a specific position.

        Args:
            file_path: Path to .rpy file relative to game/ directory.
            line_number: Line number to insert AFTER.
            character: Character variable name for dialogue (e.g., "s").
            text: Dialogue text (used with character).
            raw_lines: Raw RenPy script lines to insert (alternative to character+text).
                       Use newlines to separate multiple lines.

        Requires set_project to be called first.
        """
        try:
            game_dir = _get_game_dir()
        except ValueError as e:
            return str(e)

        target = game_dir / file_path
        if not target.exists():
            return f"Error: File not found: {file_path}"

        try:
            content = target.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading file: {e}"

        lines = content.splitlines()
        if line_number < 0 or line_number > len(lines):
            return f"Error: Line number {line_number} out of range (1-{len(lines)})."

        # Build insertion content
        if raw_lines:
            new_content = raw_lines.splitlines()
        elif character and text:
            new_content = [f'    {character} "{text}"']
        elif text:
            new_content = [f'    "{text}"']
        else:
            return "Error: Provide either 'text' (with optional 'character') or 'raw_lines'."

        # Insert
        for i, new_line in enumerate(new_content):
            lines.insert(line_number + i, new_line)

        new_text = "\n".join(lines)
        if content.endswith("\n"):
            new_text += "\n"
        target.write_text(new_text, encoding="utf-8")

        return json.dumps({
            "file": file_path,
            "inserted_at": line_number + 1,
            "lines_inserted": len(new_content),
            "content": "\n".join(new_content),
        }, indent=2, ensure_ascii=False)
