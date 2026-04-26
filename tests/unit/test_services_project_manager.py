"""Tests for project manager service."""

from pathlib import Path

import pytest

from renpy_mcp.blueprint.models import PipelineStage, ProjectBlueprint, ProjectMeta, ProjectStatus
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

        result = pm.list_projects()
        names = [p.name for p in result.projects]
        assert "project_a" in names
        assert "project_b" in names
        assert result.errors == []

    def test_delete_project(self, settings: Settings, tmp_path: Path) -> None:
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        project_dir = pm.ensure_project_dir("to_delete")
        assert project_dir.exists()

        pm.delete_project("to_delete")
        assert not project_dir.exists()

    def test_copy_template_none(self, settings: Settings, tmp_path: Path) -> None:
        """copy_template with None should create a minimal game/script.rpy and meta/project.json."""
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        dest = settings.workspace / "minimal_project"
        pm.copy_template(dest, None)

        assert (dest / "game" / "script.rpy").exists()
        content = (dest / "game" / "script.rpy").read_text(encoding="utf-8")
        assert "label start:" in content

        # Phase 1: meta/ and default project.json must exist.
        assert (dest / "meta" / "project.json").exists()
        meta = pm.read_project_meta(dest.name)
        assert meta is not None
        assert meta.status == ProjectStatus.DRAFT
        assert meta.pipeline_stage == PipelineStage.IDLE
        assert meta.chapter_count == 0
        assert meta.scene_count == 0

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

        dest = settings.workspace / "copied_project"
        pm.copy_template(dest, template_path)

        assert (dest / "game" / "script.rpy").exists()
        assert (dest / "game" / "options.rpy").exists()
        # Phase 1: built-in template copies should also get meta/.
        assert (dest / "meta" / "project.json").exists()


class TestProjectManagerPersistence:
    """Tests for Phase 1 meta/blueprint/index persistence."""

    def test_project_meta_roundtrip(self, settings: Settings) -> None:
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        pm.ensure_project_dir("roundtrip")

        meta = ProjectMeta(
            name="roundtrip",
            path=settings.workspace / "roundtrip",
            status=ProjectStatus.DRAFT,
            pipeline_stage=PipelineStage.COLLECTING,
            chapter_count=3,
            scene_count=12,
            confirmed_scenes=5,
        )
        pm.write_project_meta("roundtrip", meta)

        read = pm.read_project_meta("roundtrip")
        assert read is not None
        assert read.name == "roundtrip"
        assert read.status == ProjectStatus.DRAFT
        assert read.pipeline_stage == PipelineStage.COLLECTING
        assert read.chapter_count == 3
        assert read.scene_count == 12
        assert read.confirmed_scenes == 5

    def test_blueprint_roundtrip(self, settings: Settings) -> None:
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        pm.ensure_project_dir("bp_project")

        blueprint = ProjectBlueprint(
            title="Test VN",
            genre="sci-fi",
            worldview="cyberpunk",
            themes=["identity", "freedom"],
        )
        pm.write_blueprint("bp_project", blueprint)

        read = pm.read_blueprint("bp_project")
        assert read is not None
        assert read.title == "Test VN"
        assert read.genre == "sci-fi"
        assert read.themes == ["identity", "freedom"]

    def test_index_roundtrip(self, settings: Settings) -> None:
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        pm.ensure_project_dir("idx_project")

        index = {"scenes": {"s1": {"file": "intro.rpy", "label": "start"}}}
        pm.write_project_index("idx_project", index)

        read = pm.read_project_index("idx_project")
        assert read is not None
        assert read["scenes"]["s1"]["file"] == "intro.rpy"

    def test_legacy_project_fallback(self, settings: Settings) -> None:
        """Projects without meta/project.json should still appear in list_projects."""
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        legacy_dir = settings.workspace / "legacy"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        (legacy_dir / "game").mkdir(parents=True, exist_ok=True)
        (legacy_dir / "game" / "script.rpy").write_text("label start:\n    pass\n")

        result = pm.list_projects()
        names = [p.name for p in result.projects]
        assert "legacy" in names
        assert result.errors == []

        legacy_meta = next(p for p in result.projects if p.name == "legacy")
        assert legacy_meta.status == ProjectStatus.DRAFT
        assert legacy_meta.pipeline_stage == PipelineStage.IDLE
        assert legacy_meta.chapter_count == 0
        assert legacy_meta.scene_count == 0

    def test_read_project_meta_returns_none_for_missing_meta(self, settings: Settings) -> None:
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        pm.ensure_project_dir("no_meta")
        assert pm.read_project_meta("no_meta") is None

    def test_read_blueprint_real_yaml(self, settings: Settings) -> None:
        """read_blueprint() must parse genuine YAML, not just JSON."""
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        pm.ensure_project_dir("yaml_bp")

        yaml_text = (
            "title: Test VN\n"
            "genre: romance\n"
            "worldview: high school\n"
            "themes:\n"
            "  - love\n"
            "  - friendship\n"
        )
        meta_dir = settings.workspace / "yaml_bp" / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "blueprint.yaml").write_text(yaml_text, encoding="utf-8")

        read = pm.read_blueprint("yaml_bp")
        assert read is not None
        assert read.title == "Test VN"
        assert read.genre == "romance"
        assert read.themes == ["love", "friendship"]

    def test_write_blueprint_emits_yaml(self, settings: Settings) -> None:
        """write_blueprint() must persist real YAML, not JSON text."""
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        pm.ensure_project_dir("yaml_bp")

        blueprint = ProjectBlueprint(
            title="Test VN",
            genre="sci-fi",
            worldview="cyberpunk",
            themes=["identity", "freedom"],
        )
        pm.write_blueprint("yaml_bp", blueprint)

        raw = (settings.workspace / "yaml_bp" / "meta" / "blueprint.yaml").read_text(
            encoding="utf-8"
        )
        assert not raw.strip().startswith("{")
        assert "title: Test VN" in raw

    def test_read_blueprint_compat_json(self, settings: Settings) -> None:
        """Historical JSON-in-YAML files should still be readable."""
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        pm.ensure_project_dir("json_bp")

        json_text = (
            '{\n'
            '  "title": "Legacy JSON",\n'
            '  "genre": "horror",\n'
            '  "worldview": "dark",\n'
            '  "themes": ["fear"]\n'
            '}\n'
        )
        meta_dir = settings.workspace / "json_bp" / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "blueprint.yaml").write_text(json_text, encoding="utf-8")

        read = pm.read_blueprint("json_bp")
        assert read is not None
        assert read.title == "Legacy JSON"
        assert read.genre == "horror"

    def test_corrupt_project_meta_no_legacy_fallback(self, settings: Settings) -> None:
        """A corrupt meta/project.json must not be silently treated as a legacy project."""
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        project_dir = settings.workspace / "corrupt"
        project_dir.mkdir(parents=True, exist_ok=True)
        meta_dir = project_dir / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "project.json").write_text("not json at all", encoding="utf-8")

        with pytest.raises(ValueError):
            pm.read_project_meta("corrupt")

        result = pm.list_projects()
        names = [p.name for p in result.projects]
        assert "corrupt" not in names
        assert any("corrupt" in err and "meta/project.json" in err for err in result.errors)

    def test_read_blueprint_invalid_yaml_raises_value_error(self, settings: Settings) -> None:
        """read_blueprint() must raise ValueError for syntactically invalid YAML."""
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        pm.ensure_project_dir("bad_yaml")
        meta_dir = settings.workspace / "bad_yaml" / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "blueprint.yaml").write_text("title: [unclosed bracket", encoding="utf-8")

        with pytest.raises(ValueError) as exc_info:
            pm.read_blueprint("bad_yaml")
        assert "bad_yaml" in str(exc_info.value)
        assert "blueprint.yaml" in str(exc_info.value)

    def test_read_blueprint_wrong_structure_raises_value_error(self, settings: Settings) -> None:
        """read_blueprint() must raise ValueError when YAML is valid but schema is wrong."""
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        pm.ensure_project_dir("wrong_schema")
        meta_dir = settings.workspace / "wrong_schema" / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "blueprint.yaml").write_text(
            "completely_unrelated_field: 123\n", encoding="utf-8"
        )

        with pytest.raises(ValueError) as exc_info:
            pm.read_blueprint("wrong_schema")
        assert "wrong_schema" in str(exc_info.value)
        assert "blueprint.yaml" in str(exc_info.value)

    def test_read_blueprint_empty_file_raises_value_error(self, settings: Settings) -> None:
        """read_blueprint() must raise ValueError for an empty blueprint.yaml."""
        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        pm.ensure_project_dir("empty_bp")
        meta_dir = settings.workspace / "empty_bp" / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "blueprint.yaml").write_text("", encoding="utf-8")

        with pytest.raises(ValueError) as exc_info:
            pm.read_blueprint("empty_bp")
        assert "empty_bp" in str(exc_info.value)
        assert "blueprint.yaml" in str(exc_info.value)

    def test_write_project_meta_refreshes_updated_at(self, settings: Settings) -> None:
        """write_project_meta() should always refresh updated_at to current UTC time."""
        from datetime import datetime, timedelta

        from renpy_mcp.services.project_manager import ProjectManager

        pm = ProjectManager(settings)
        pm.ensure_project_dir("refresh_at")

        old_time = datetime.utcnow() - timedelta(days=7)
        meta = ProjectMeta(
            name="refresh_at",
            path=settings.workspace / "refresh_at",
            status=ProjectStatus.DRAFT,
            updated_at=old_time,
        )
        pm.write_project_meta("refresh_at", meta)

        read = pm.read_project_meta("refresh_at")
        assert read is not None
        assert read.updated_at > old_time
        assert (datetime.utcnow() - read.updated_at).total_seconds() < 5
