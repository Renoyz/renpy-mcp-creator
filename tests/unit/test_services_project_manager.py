"""Tests for project manager service."""

from pathlib import Path

import pytest

from renpy_mcp.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings with a temporary workspace."""
    return Settings().model_copy(update={"workspace": tmp_path / "workspace"})


class TestProjectManager:
    """Tests for ProjectManager."""

    def test_ensure_project_dir_creates_directory(self, settings: Settings, tmp_path: Path) -> None:
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        project_dir = pm.ensure_project_dir("my_vn")

        assert project_dir.exists()
        assert project_dir.name == "my_vn"
        assert project_dir.parent == settings.workspace

    def test_list_projects(self, settings: Settings, tmp_path: Path) -> None:
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        pm.ensure_project_dir("project_a")
        pm.ensure_project_dir("project_b")

        projects = pm.list_projects()
        names = [p.name for p in projects]
        assert "project_a" in names
        assert "project_b" in names

    def test_delete_project(self, settings: Settings, tmp_path: Path) -> None:
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        project_dir = pm.ensure_project_dir("to_delete")
        assert project_dir.exists()

        pm.delete_project("to_delete")
        assert not project_dir.exists()

    def test_copy_template_none(self, settings: Settings, tmp_path: Path) -> None:
        """copy_template with None should create a minimal game/script.rpy."""
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        dest = tmp_path / "minimal_project"
        pm.copy_template(dest, None)

        assert (dest / "game" / "script.rpy").exists()
        content = (dest / "game" / "script.rpy").read_text(encoding="utf-8")
        assert "label start:" in content

    def test_find_template_basic(self, settings: Settings) -> None:
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        path = pm.find_template("basic")

        assert path is not None
        assert path.name == "basic"
        assert (path / "game" / "script.rpy").exists()

    def test_find_template_missing(self, settings: Settings) -> None:
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        path = pm.find_template("nonexistent")
        assert path is None

    def test_copy_template_builtin(self, settings: Settings) -> None:
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        template_path = pm.find_template("basic")
        assert template_path is not None

        dest = tmp_path = settings.workspace / "copied_project"
        pm.copy_template(dest, template_path)

        assert (dest / "game" / "script.rpy").exists()
        assert (dest / "game" / "options.rpy").exists()
