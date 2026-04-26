"""TDD: Windows CJK font paths use SystemRoot env var, not hardcoded C:\\."""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def test_windows_cjk_fallbacks_use_system_root():
    """On Windows, _windows_cjk_fallbacks must be derived from SystemRoot env var."""
    from renpy_mcp.services.prototype_generation_service import resolve_cjk_font_path

    if os.name != "nt":
        pytest.skip("Windows-only test")

    with patch.dict(os.environ, {"SystemRoot": "D:\\Windows"}):
        with patch.object(Path, "exists", return_value=True):
            result = resolve_cjk_font_path()
            assert result is not None
            assert str(result).startswith("D:\\Windows"), (
                f"Expected D:\\Windows path, got {result}"
            )
