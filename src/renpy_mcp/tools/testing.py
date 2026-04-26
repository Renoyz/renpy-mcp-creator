"""Automated testing tools."""

import logging
from pathlib import Path

from ..config import RenPyConfig
from ..renpy_runner import RenPyRunner

logger = logging.getLogger(__name__)


def register_testing_tools(mcp, config: RenPyConfig, runner: RenPyRunner):
    """Register testing-related MCP tools."""

    @mcp.tool()
    async def run_test(testcase: str | None = None) -> str:
        """Run RenPy automated tests.

        Args:
            testcase: Name of a specific test case to run.
                     If None, runs all enabled tests.

        Returns:
            Test output including pass/fail results.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."
        return await runner.run_test(testcase=testcase)

    @mcp.tool()
    async def create_test(
        name: str,
        steps: list[str],
        description: str = "",
    ) -> str:
        """Create a RenPy test case file.

        Args:
            name: Test case name (used as identifier).
            steps: List of test steps in RenPy test syntax.
                   Examples: "click", "advance", 'type "hello"',
                   'assert renpy.get_screen("say")', "pause 0.5"
            description: Optional test description.

        Returns:
            Path to the created test file.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        test_dir = game_dir / "tests"
        test_dir.mkdir(exist_ok=True)
        test_file = test_dir / f"test_{name}.rpy"

        lines = [f'testcase {name}:']
        if description:
            lines.append(f'    description "{description}"')
        for step in steps:
            lines.append(f"    {step}")
        lines.append("")

        test_file.write_text("\n".join(lines), encoding="utf-8")
        return f"Test created: {test_file}"

    @mcp.tool()
    async def list_tests() -> str:
        """List all test cases defined in the project.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        tests = []

        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            try:
                lines = rpy_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                logger.warning("Failed to read test file: %s", rpy_file, exc_info=True)
                continue

            rel_path = rpy_file.relative_to(config.project_path)
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("testcase ") and stripped.endswith(":"):
                    test_name = stripped[9:-1].strip()
                    tests.append(f"{test_name}  ({rel_path}:{i})")

        if not tests:
            return "No test cases found."
        return "\n".join(tests)
