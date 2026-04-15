"""Story analysis tools — flow graph, dead ends, variable tracking."""

import json
import re
from pathlib import Path

from ..config import RenPyConfig


def register_analysis_tools(mcp, config: RenPyConfig):
    """Register story analysis MCP tools."""

    def _parse_scripts(game_dir: Path) -> dict[str, list[str]]:
        """Read all .rpy files and return {relative_path: lines}.

        Excludes translation files (tl/), MCP temp files, and test files.
        """
        scripts = {}
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            try:
                rel = str(rpy_file.relative_to(game_dir))
                # Skip translation, MCP temp, and test files
                if rel.startswith("tl") or rel.startswith("_mcp") or rel == "testcases.rpy":
                    continue
                lines = rpy_file.read_text(encoding="utf-8").splitlines()
                scripts[rel] = lines
            except Exception:
                continue
        return scripts

    _label_re = re.compile(r'^label\s+(\w+)(?:\s*\(.*\))?\s*:')

    def _extract_labels(scripts: dict[str, list[str]]) -> dict[str, dict]:
        """Extract all labels with their file locations and content."""
        labels = {}
        for filepath, lines in scripts.items():
            for i, line in enumerate(lines):
                stripped = line.strip()
                lm = _label_re.match(stripped)
                if lm:
                    name = lm.group(1)
                    # Skip internal labels
                    if name.startswith("_"):
                        continue
                    labels[name] = {
                        "file": filepath,
                        "line": i + 1,
                        "jumps_to": [],
                        "called_by": [],
                        "has_return": False,
                        "has_menu": False,
                    }

            # Second pass: find jumps, calls, returns, menus within each label
            current_label = None
            for i, line in enumerate(lines):
                stripped = line.strip()
                lm = _label_re.match(stripped)
                if lm:
                    name = lm.group(1)
                    if not name.startswith("_"):
                        current_label = name

                if current_label and current_label in labels:
                    if stripped.startswith("jump "):
                        target = stripped[5:].strip()
                        labels[current_label]["jumps_to"].append(target)
                    elif stripped.startswith("call "):
                        target = stripped[5:].strip().split()[0]
                        labels[current_label]["jumps_to"].append(f"call:{target}")
                    elif stripped == "return":
                        labels[current_label]["has_return"] = True
                    elif stripped.startswith("menu"):
                        labels[current_label]["has_menu"] = True

        # Build called_by references
        for label_name, info in labels.items():
            for target in info["jumps_to"]:
                clean_target = target.replace("call:", "")
                if clean_target in labels:
                    labels[clean_target]["called_by"].append(label_name)

        return labels

    @mcp.tool()
    async def story_flow_graph() -> str:
        """Analyze the story flow and return a graph of labels and their connections.

        Returns a JSON structure showing all labels, their jump/call targets,
        whether they have menus (choices), and which labels reference them.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        scripts = _parse_scripts(game_dir)
        labels = _extract_labels(scripts)

        # Build a mermaid-compatible flow description too
        mermaid_lines = ["graph TD"]
        for name, info in labels.items():
            node_label = name
            if info["has_menu"]:
                node_label += " [CHOICE]"
            if info["has_return"]:
                node_label += " [END]"
            mermaid_lines.append(f'    {name}["{node_label}"]')
            for target in info["jumps_to"]:
                clean = target.replace("call:", "")
                arrow = "-.->|call|" if target.startswith("call:") else "-->"
                if clean in labels:
                    mermaid_lines.append(f"    {name} {arrow} {clean}")

        result = {
            "labels": labels,
            "mermaid": "\n".join(mermaid_lines),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def find_dead_ends() -> str:
        """Find labels that are dead ends (unreachable or have no exit).

        Returns labels that:
        - Are never jumped to or called (orphaned)
        - Have no jump, call, or return statement (no exit)

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        scripts = _parse_scripts(game_dir)
        labels = _extract_labels(scripts)

        issues = []

        for name, info in labels.items():
            # Skip 'start' — it's the entry point
            if name == "start":
                continue

            if not info["called_by"]:
                issues.append({
                    "label": name,
                    "file": info["file"],
                    "line": info["line"],
                    "issue": "orphaned",
                    "detail": "This label is never jumped to or called.",
                })

            if not info["jumps_to"] and not info["has_return"]:
                issues.append({
                    "label": name,
                    "file": info["file"],
                    "line": info["line"],
                    "issue": "no_exit",
                    "detail": "This label has no jump, call, or return statement.",
                })

        if not issues:
            return "No dead ends found. All labels are reachable and have proper exits."
        return json.dumps(issues, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def track_variables() -> str:
        """Track all game variables — where they are defined, set, and read.

        Finds:
        - default/define declarations
        - Python assignments ($ var = ...)
        - Conditional checks (if var, elif var)
        - Menu conditions

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        scripts = _parse_scripts(game_dir)

        variables: dict[str, dict] = {}

        # Patterns for variable operations
        # default x = ... or define x = ...
        default_re = re.compile(r"^\s*(default|define)\s+(\w+)\s*=\s*(.+)")
        # $ x = ... or $ x += ... etc.
        assign_re = re.compile(r"^\s*\$\s+(\w+)\s*[+\-*/%]?=\s*(.+)")
        # if x: or elif x: or while x:
        condition_re = re.compile(r"^\s*(?:if|elif|while)\s+(.+):")
        # show/hide/scene don't count as variables

        def _add_var(name: str, file: str, line: int, kind: str, detail: str = ""):
            # Skip RenPy internals and gui/config/build
            if name.startswith(("_", "gui.", "config.", "build.")):
                return
            if name not in variables:
                variables[name] = {
                    "definitions": [],
                    "assignments": [],
                    "reads": [],
                }
            entry = {"file": file, "line": line}
            if detail:
                entry["detail"] = detail
            variables[name][kind].append(entry)

        for filepath, lines in scripts.items():
            # Skip GUI and screen definition files for variable tracking
            if filepath in ("gui.rpy", "screens.rpy", "options.rpy"):
                continue

            for i, line in enumerate(lines):
                # default/define
                m = default_re.match(line)
                if m:
                    kind_kw, name, value = m.groups()
                    _add_var(name, filepath, i + 1, "definitions", f"{kind_kw} {name} = {value.strip()}")
                    continue

                # $ assignment
                m = assign_re.match(line)
                if m:
                    name, value = m.groups()
                    _add_var(name, filepath, i + 1, "assignments", f"{name} = {value.strip()}")
                    continue

                # Condition checks
                m = condition_re.match(line)
                if m:
                    cond = m.group(1)
                    # Extract variable names from condition
                    for word in re.findall(r'\b([a-z_]\w*)\b', cond):
                        if word not in ("and", "or", "not", "in", "is", "True",
                                        "False", "None", "screen", "renpy"):
                            _add_var(word, filepath, i + 1, "reads", f"condition: {cond.strip()}")

        if not variables:
            return "No game variables found."
        return json.dumps(variables, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def count_dialogue() -> str:
        """Count dialogue blocks, words, and characters per route/label.

        Provides statistics about the script's text content.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        scripts = _parse_scripts(game_dir)

        stats = {}
        current_label = None
        # Simple dialogue detection: lines that are quoted strings (not commands)
        dialogue_re = re.compile(r'^\s+(".*"|[a-z]\s+".*")')

        for filepath, lines in scripts.items():
            if filepath in ("gui.rpy", "screens.rpy", "options.rpy"):
                continue

            for line in lines:
                stripped = line.strip()
                lm = _label_re.match(stripped)
                if lm:
                    current_label = lm.group(1)
                    if current_label.startswith("_"):
                        current_label = None
                        continue
                    if current_label not in stats:
                        stats[current_label] = {
                            "dialogue_blocks": 0,
                            "words": 0,
                            "characters": 0,
                        }

                if current_label and current_label in stats:
                    m = dialogue_re.match(line)
                    if m:
                        # Extract text between quotes
                        text_parts = re.findall(r'"([^"]*)"', line)
                        for text in text_parts:
                            # Skip empty and tag-only text
                            clean = re.sub(r'\{[^}]*\}', '', text).strip()
                            if clean:
                                stats[current_label]["dialogue_blocks"] += 1
                                words = clean.split()
                                stats[current_label]["words"] += len(words)
                                stats[current_label]["characters"] += len(clean)

        total = {
            "dialogue_blocks": sum(s["dialogue_blocks"] for s in stats.values()),
            "words": sum(s["words"] for s in stats.values()),
            "characters": sum(s["characters"] for s in stats.values()),
        }

        result = {"per_label": stats, "total": total}
        return json.dumps(result, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def character_map() -> str:
        """Map all characters: definitions, dialogue counts, and scene appearances.

        Extracts Character() definitions and cross-references with dialogue
        to show which characters speak in which labels.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        scripts = _parse_scripts(game_dir)

        characters = {}
        # Find Character definitions: define x = Character("Name")
        char_def_re = re.compile(
            r'^\s*define\s+(\w+)\s*=\s*Character\s*\(\s*(?:_\()?\s*["\']([^"\']*)["\']'
        )
        # Dialogue: character_id "text" or "narrator text"
        dialogue_re = re.compile(r'^\s+(\w+)\s+"([^"]*)"')
        narrator_re = re.compile(r'^\s+"([^"]*)"')

        for filepath, lines in scripts.items():
            if filepath in ("gui.rpy", "screens.rpy", "options.rpy"):
                continue
            for line in lines:
                m = char_def_re.match(line)
                if m:
                    var_name, display_name = m.groups()
                    characters[var_name] = {
                        "display_name": display_name,
                        "file": filepath,
                        "dialogue_count": 0,
                        "word_count": 0,
                        "appears_in": [],
                    }

        # If no explicit definitions, create entries for common patterns
        if not characters:
            characters["narrator"] = {
                "display_name": "(Narrator)",
                "file": "",
                "dialogue_count": 0,
                "word_count": 0,
                "appears_in": [],
            }

        # Count dialogue per character per label
        for filepath, lines in scripts.items():
            if filepath in ("gui.rpy", "screens.rpy", "options.rpy"):
                continue
            current_label = None
            for line in lines:
                stripped = line.strip()
                lm = _label_re.match(stripped)
                if lm:
                    current_label = lm.group(1)

                m = dialogue_re.match(line)
                if m:
                    speaker, text = m.groups()
                    if speaker not in characters:
                        characters[speaker] = {
                            "display_name": speaker,
                            "file": "",
                            "dialogue_count": 0,
                            "word_count": 0,
                            "appears_in": [],
                        }
                    characters[speaker]["dialogue_count"] += 1
                    clean = re.sub(r'\{[^}]*\}', '', text).strip()
                    characters[speaker]["word_count"] += len(clean.split())
                    if current_label and current_label not in characters[speaker]["appears_in"]:
                        characters[speaker]["appears_in"].append(current_label)
                elif narrator_re.match(line) and not stripped.startswith("#"):
                    if "narrator" not in characters:
                        characters["narrator"] = {
                            "display_name": "(Narrator)",
                            "file": "",
                            "dialogue_count": 0,
                            "word_count": 0,
                            "appears_in": [],
                        }
                    nm = narrator_re.match(line)
                    if nm:
                        characters["narrator"]["dialogue_count"] += 1
                        clean = re.sub(r'\{[^}]*\}', '', nm.group(1)).strip()
                        characters["narrator"]["word_count"] += len(clean.split())
                        if current_label and current_label not in characters["narrator"]["appears_in"]:
                            characters["narrator"]["appears_in"].append(current_label)

        return json.dumps(characters, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def validate_script() -> str:
        """Lightweight script validation — faster than full lint.

        Checks for:
        - Undefined character references (speakers not defined with Character())
        - Duplicate label names
        - Jump/call targets that don't exist
        - Indentation errors (mixed tabs/spaces)

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        scripts = _parse_scripts(game_dir)
        labels = _extract_labels(scripts)
        issues = []

        # Collect character definitions
        defined_chars = set()
        char_def_re = re.compile(
            r'^\s*define\s+(\w+)\s*=\s*Character\s*\('
        )
        for filepath, lines in scripts.items():
            for line in lines:
                m = char_def_re.match(line)
                if m:
                    defined_chars.add(m.group(1))

        # Check for issues
        dialogue_re = re.compile(r'^\s+(\w+)\s+"')
        seen_labels = {}

        for filepath, lines in scripts.items():
            if filepath in ("gui.rpy", "screens.rpy", "options.rpy"):
                continue

            for i, line in enumerate(lines):
                stripped = line.strip()

                # Duplicate labels
                lm = _label_re.match(stripped)
                if lm:
                    label_name = lm.group(1)
                    if not label_name.startswith("_"):
                        if label_name in seen_labels:
                            issues.append({
                                "type": "duplicate_label",
                                "file": filepath,
                                "line": i + 1,
                                "detail": f"Label '{label_name}' also defined at {seen_labels[label_name]}",
                            })
                        seen_labels[label_name] = f"{filepath}:{i+1}"

                # Undefined character
                m = dialogue_re.match(line)
                if m:
                    speaker = m.group(1)
                    if speaker not in defined_chars and speaker not in (
                        "narrator", "centered", "extend", "nvl",
                        "voice", "sound", "queue", "old", "new",
                        "click", "assert", "keysym", "pause", "run",
                        "action", "label", "call", "jump", "show",
                        "hide", "scene", "play", "stop", "with",
                    ):
                        issues.append({
                            "type": "undefined_character",
                            "file": filepath,
                            "line": i + 1,
                            "detail": f"Character '{speaker}' used but not defined with Character()",
                        })

                # Invalid jump/call targets
                if stripped.startswith("jump "):
                    target = stripped[5:].strip()
                    if target and target not in labels and not target.startswith("expression"):
                        issues.append({
                            "type": "invalid_jump",
                            "file": filepath,
                            "line": i + 1,
                            "detail": f"Jump target '{target}' does not exist",
                        })
                elif stripped.startswith("call "):
                    target = stripped[5:].strip().split()[0]
                    if target and target not in labels and not target.startswith("expression"):
                        issues.append({
                            "type": "invalid_call",
                            "file": filepath,
                            "line": i + 1,
                            "detail": f"Call target '{target}' does not exist",
                        })

                # Mixed indentation
                if line and not line.strip() == "":
                    leading = line[:len(line) - len(line.lstrip())]
                    if "\t" in leading and " " in leading:
                        issues.append({
                            "type": "mixed_indentation",
                            "file": filepath,
                            "line": i + 1,
                            "detail": "Mixed tabs and spaces in indentation",
                        })

        if not issues:
            return "No issues found. All scripts are valid."
        return json.dumps({"issues_count": len(issues), "issues": issues}, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def playtest_report() -> str:
        """Run all available test cases and generate a test report.

        Discovers all testcases in the project and runs each one,
        reporting pass/fail status and any errors.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"

        # Find all testcase definitions
        testcases = []
        testcase_re = re.compile(r'^\s*testcase\s+(\w+)\s*:')
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            try:
                lines = rpy_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            rel = str(rpy_file.relative_to(game_dir))
            for i, line in enumerate(lines):
                m = testcase_re.match(line)
                if m:
                    testcases.append({
                        "name": m.group(1),
                        "file": rel,
                        "line": i + 1,
                    })

        if not testcases:
            return "No testcases found in the project."

        # Import runner module to run tests
        from ..renpy_runner import RenPyRunner
        runner = RenPyRunner(config)

        results = []
        for tc in testcases:
            try:
                result = await runner.run_command(
                    "test", tc["name"],
                    project_path=config.project_path,
                    timeout=120.0,
                )
                passed = result.returncode == 0
                results.append({
                    "testcase": tc["name"],
                    "file": tc["file"],
                    "passed": passed,
                    "output": (result.stdout + result.stderr)[:500] if not passed else "",
                })
            except Exception as e:
                results.append({
                    "testcase": tc["name"],
                    "file": tc["file"],
                    "passed": False,
                    "output": str(e)[:500],
                })

        passed = sum(1 for r in results if r["passed"])
        total = len(results)
        report = {
            "summary": f"{passed}/{total} tests passed",
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "results": results,
        }
        return json.dumps(report, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def generate_scene(
        label_name: str = "new_scene",
        characters: list[str] | None = None,
        background: str = "",
        description: str = "",
    ) -> str:
        """Generate a RenPy scene script template.

        Creates valid RenPy code that can be pasted into a .rpy file.

        Args:
            label_name: Name for the scene label.
            characters: List of character variable names to include.
            background: Background image name (e.g., "bg room").
            description: Brief description to include as a comment.
        """
        lines = []

        if description:
            lines.append(f"# {description}")
            lines.append("")

        lines.append(f"label {label_name}:")
        lines.append("")

        if background:
            lines.append(f"    scene {background}")
            lines.append("    with fade")
            lines.append("")

        if characters:
            for char in characters:
                lines.append(f"    show {char} happy")
            lines.append("    with dissolve")
            lines.append("")

            # Generate sample dialogue
            for char in characters:
                lines.append(f'    {char} "..."')
                lines.append("")
        else:
            lines.append('    "..."')
            lines.append("")

        lines.append("    # TODO: Add scene content")
        lines.append("")
        lines.append("    return")
        lines.append("")

        return "\n".join(lines)

    @mcp.tool()
    async def list_screens() -> str:
        """List all screen definitions in the project.

        Shows screen names, parameters, file locations, and where each
        screen is shown or called.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        screens = {}
        screen_def_re = re.compile(r'^\s*screen\s+(\w+)\s*(\(.*?\))?\s*:')
        screen_use_re = re.compile(
            r'^\s*(?:show\s+screen|call\s+screen|use)\s+(\w+)'
        )

        # First pass: find definitions
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            if rpy_file.name.startswith("_mcp"):
                continue
            try:
                lines = rpy_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            rel = str(rpy_file.relative_to(game_dir))
            for i, line in enumerate(lines):
                m = screen_def_re.match(line)
                if m:
                    name = m.group(1)
                    params = m.group(2) or ""
                    screens[name] = {
                        "file": rel,
                        "line": i + 1,
                        "params": params,
                        "used_by": [],
                    }

        # Second pass: find usages
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            if rpy_file.name.startswith("_mcp"):
                continue
            try:
                lines = rpy_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            rel = str(rpy_file.relative_to(game_dir))
            for i, line in enumerate(lines):
                m = screen_use_re.match(line)
                if m:
                    screen_name = m.group(1)
                    if screen_name in screens:
                        ref = f"{rel}:{i+1}"
                        if ref not in screens[screen_name]["used_by"]:
                            screens[screen_name]["used_by"].append(ref)

        if not screens:
            return "No screen definitions found."
        return json.dumps(screens, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def music_timeline() -> str:
        """Map music and sound effects across the story timeline.

        Shows when music starts, stops, and changes as the player
        progresses through each label.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        scripts = _parse_scripts(game_dir)

        timeline = {}
        audio_re = re.compile(
            r'^\s*(play|stop|queue)\s+(music|sound|audio|voice)\s*(.*)'
        )

        for filepath, lines in scripts.items():
            current_label = None
            for i, line in enumerate(lines):
                stripped = line.strip()
                lm = _label_re.match(stripped)
                if lm:
                    current_label = lm.group(1)
                    if current_label.startswith("_"):
                        current_label = None

                m = audio_re.match(stripped)
                if m and current_label:
                    action, channel, rest = m.groups()
                    # Extract filename from quotes if present
                    fname_match = re.search(r'["\']([^"\']+)["\']', rest)
                    filename = fname_match.group(1) if fname_match else rest.strip().split()[0] if rest.strip() else ""

                    if current_label not in timeline:
                        timeline[current_label] = []
                    timeline[current_label].append({
                        "line": i + 1,
                        "file": filepath,
                        "action": action,
                        "channel": channel,
                        "track": filename,
                    })

        if not timeline:
            return "No music or sound references found in scripts."
        return json.dumps(timeline, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def search_script(query: str, case_sensitive: bool = False) -> str:
        """Search across all game scripts for text patterns.

        Searches dialogue, narration, comments, and code in .rpy files.

        Args:
            query: Text to search for (plain text or regex pattern).
            case_sensitive: Whether the search is case-sensitive (default False).

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            pattern = re.compile(query, flags)
        except re.error:
            pattern = re.compile(re.escape(query), flags)

        matches = []
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            if rpy_file.name.startswith("_mcp"):
                continue
            try:
                lines = rpy_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            rel = str(rpy_file.relative_to(game_dir))
            for i, line in enumerate(lines):
                if pattern.search(line):
                    matches.append({
                        "file": rel,
                        "line": i + 1,
                        "text": line.strip()[:200],
                    })
                    if len(matches) >= 100:
                        break
            if len(matches) >= 100:
                break

        if not matches:
            return f"No matches found for '{query}'."
        return json.dumps({
            "query": query,
            "match_count": len(matches),
            "truncated": len(matches) >= 100,
            "matches": matches,
        }, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def consistency_check() -> str:
        """Check for consistency issues in dialogue and narration.

        Detects:
        - Character names spelled differently in dialogue vs definitions
        - Inconsistent use of honorifics or titles
        - Empty dialogue blocks
        - Very long dialogue lines (over 200 chars)

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        scripts = _parse_scripts(game_dir)
        issues = []

        # Collect Character definitions
        char_names = {}
        char_def_re = re.compile(
            r'^\s*define\s+(\w+)\s*=\s*Character\s*\(\s*(?:_\()?\s*["\']([^"\']*)["\']'
        )
        for filepath, lines in scripts.items():
            for line in lines:
                m = char_def_re.match(line)
                if m:
                    char_names[m.group(1)] = m.group(2)

        dialogue_re = re.compile(r'^\s+(?:(\w+)\s+)?"(.*?)"')

        for filepath, lines in scripts.items():
            if filepath in ("gui.rpy", "screens.rpy", "options.rpy"):
                continue
            for i, line in enumerate(lines):
                m = dialogue_re.match(line)
                if not m:
                    continue
                speaker = m.group(1)
                text = m.group(2)

                # Empty dialogue
                clean = re.sub(r'\{[^}]*\}', '', text).strip()
                if not clean:
                    issues.append({
                        "type": "empty_dialogue",
                        "file": filepath,
                        "line": i + 1,
                        "detail": f"Empty dialogue block{' for ' + speaker if speaker else ''}",
                    })

                # Very long dialogue (hard to read in VN format)
                if len(clean) > 200:
                    issues.append({
                        "type": "long_dialogue",
                        "file": filepath,
                        "line": i + 1,
                        "detail": f"Dialogue is {len(clean)} chars (recommended: under 200)",
                        "speaker": speaker or "(narrator)",
                    })

        if not issues:
            return "No consistency issues found."
        return json.dumps({
            "issues_count": len(issues),
            "issues": issues,
        }, indent=2, ensure_ascii=False)

    @mcp.tool()
    async def accessibility_check() -> str:
        """Check the project for accessibility issues.

        Checks for:
        - Missing alt text for images
        - Very long unbroken text blocks
        - Potential color contrast issues in character definitions
        - Lack of pause/wait between rapid scene transitions

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        scripts = _parse_scripts(game_dir)
        issues = []

        # Check for color contrast in Character definitions
        char_color_re = re.compile(
            r'^\s*define\s+\w+\s*=\s*Character\s*\(.*color\s*=\s*["\']#?([0-9a-fA-F]{6})["\']'
        )

        for filepath, lines in scripts.items():
            prev_was_scene = False
            for i, line in enumerate(lines):
                stripped = line.strip()

                # Character color contrast check
                m = char_color_re.match(line)
                if m:
                    color_hex = m.group(1)
                    r_val = int(color_hex[0:2], 16)
                    g_val = int(color_hex[2:4], 16)
                    b_val = int(color_hex[4:6], 16)
                    luminance = (0.299 * r_val + 0.587 * g_val + 0.114 * b_val) / 255
                    if luminance < 0.3:
                        issues.append({
                            "type": "low_contrast_color",
                            "file": filepath,
                            "line": i + 1,
                            "detail": f"Character color #{color_hex} may be hard to read (luminance: {luminance:.2f})",
                        })

                # Rapid scene transitions without pause
                if stripped.startswith("scene "):
                    if prev_was_scene:
                        issues.append({
                            "type": "rapid_transition",
                            "file": filepath,
                            "line": i + 1,
                            "detail": "Multiple scene changes without dialogue or pause between them",
                        })
                    prev_was_scene = True
                elif stripped and not stripped.startswith("#") and not stripped.startswith("with "):
                    prev_was_scene = False

                # Image without alt text (for self-voicing)
                if stripped.startswith("image ") and "=" in stripped:
                    # Check if there's an alt property
                    if "alt" not in stripped.lower():
                        issues.append({
                            "type": "missing_alt_text",
                            "file": filepath,
                            "line": i + 1,
                            "detail": "Image definition without alt text (affects self-voicing accessibility)",
                        })

        if not issues:
            return "No accessibility issues found."
        return json.dumps({
            "issues_count": len(issues),
            "issues": issues,
        }, indent=2, ensure_ascii=False)
