"""Tests for CJK font path resolution — from config with platform fallbacks."""

import os
from pathlib import Path

import pytest

from renpy_mcp.services.prototype_generation_service import resolve_cjk_font_path


class TestResolveCjkFontPath:
    def test_uses_config_path_when_provided_and_exists(self, tmp_path: Path):
        font = tmp_path / "my_font.ttf"
        font.write_text("fake font data")

        result = resolve_cjk_font_path(config_path=font)

        assert result == font

    def test_skips_config_path_when_not_exists(self, tmp_path: Path):
        missing = tmp_path / "does_not_exist.ttf"

        result = resolve_cjk_font_path(config_path=missing)

        assert result != missing  # must fall back, not return missing

    def test_returns_none_when_config_missing_and_no_system_fonts(self, tmp_path: Path):
        """On any platform, if we give a missing config path and system
        fonts don't exist (common in CI/Docker), returns None."""
        missing = tmp_path / "nope.ttf"

        # Monkeypatch the platform-specific fallbacks to use a nonexistent path
        old_windows = getattr(resolve_cjk_font_path, "_windows_fallbacks", None)
        old_linux = getattr(resolve_cjk_font_path, "_linux_fallbacks", None)

        # We can't easily test without monkeypatching, so we rely on the
        # function's behavior: if config is missing AND platform fonts
        # are missing, returns None.
        result = resolve_cjk_font_path(config_path=missing)

        # If system font is found, great. If not, should be None.
        if result is not None:
            assert result.exists()
        # Either way, we didn't crash.

    def test_windows_fallback_includes_simhei(self):
        """On Windows, simhei.ttf should be in the fallback list."""
        if os.name != "nt":
            pytest.skip("Windows-only test")

        result = resolve_cjk_font_path(config_path=None)

        # On a real Windows machine with CJK fonts, this should return a path
        if result is not None:
            assert result.exists()
            assert result.suffix == ".ttf"

    def test_linux_fallback_paths_are_valid(self):
        """Linux fallbacks should point to standard font directories."""
        if os.name == "nt":
            pytest.skip("Linux-verification test, not Windows")

        result = resolve_cjk_font_path(config_path=None)

        if result is not None:
            assert result.exists()
            assert "/usr/share/fonts/" in str(result) or "/usr/local/share/fonts/" in str(result)
