"""Unit tests for PrototypeActivationService — extracted from PrototypeGenerationService.

Covers: wire_main_script, backup/restore, commit, rollback, update_index,
read_managed_entry_label, get_prototype_runtime_status.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from renpy_mcp.blueprint.models import ChapterSummary
from renpy_mcp.services.prototype_generation_service import PrototypeScene


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chapter() -> ChapterSummary:
    return ChapterSummary(
        id="ch1",
        name="Chapter One",
        order=1,
        scenes=[{"id": "s1", "name": "Opening", "order": 1}],
    )


def _make_scenes() -> list[PrototypeScene]:
    return [
        PrototypeScene(
            scene_id="proto-ch1-s1",
            title="First Meeting",
            summary="Hero meets friend.",
            location="library",
            location_visual_brief="quiet library",
            mood="warm",
            characters_present=["Hero"],
            dialogue_beats=[
                {"speaker": "Hero", "intent": "greeting", "content_brief": "Hello!"},
            ],
            entry_label="prototype_ch1_start",
            next_scene_id=None,
        ),
    ]


@pytest.fixture
def project_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Set up a minimal project directory with game/script.rpy."""
    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.services.prototype_activation_service import PrototypeActivationService

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)
    pm = ProjectManager(settings)

    project_name = "test_project"
    game_dir = tmp_path / project_name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text(
        'label start:\n    "Hello from the Ren\'Py MCP server!"\n    return\n',
        encoding="utf-8",
    )

    service = PrototypeActivationService(pm)
    return service, pm, project_name, tmp_path


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

class TestImport:
    def test_can_import_class(self):
        from renpy_mcp.services.prototype_activation_service import PrototypeActivationService
        assert PrototypeActivationService is not None

    def test_can_instantiate(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from renpy_mcp.config import get_settings
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.services.prototype_activation_service import PrototypeActivationService

        settings = get_settings()
        monkeypatch.setattr(settings, "workspace", tmp_path)
        pm = ProjectManager(settings)
        svc = PrototypeActivationService(pm)
        assert svc.pm is pm


# ---------------------------------------------------------------------------
# wire_main_script_to_prototype
# ---------------------------------------------------------------------------

class TestWireMainScript:
    def test_replaces_default_template_with_managed_region(self, project_env):
        service, pm, project_name, tmp_path = project_env
        service.wire_main_script_to_prototype(project_name, "prototype_ch1_start")

        content = (tmp_path / project_name / "game" / "script.rpy").read_text(encoding="utf-8")
        assert "call prototype_ch1_start" in content
        assert "PROTOTYPE START (managed)" in content
        assert "PROTOTYPE END (managed)" in content

    def test_updates_managed_region_only(self, project_env):
        service, pm, project_name, tmp_path = project_env
        script_path = tmp_path / project_name / "game" / "script.rpy"

        # First: create a managed region
        service.wire_main_script_to_prototype(project_name, "prototype_ch1_start")
        content1 = script_path.read_text(encoding="utf-8")
        assert "call prototype_ch1_start" in content1

        # Second: update the managed region
        service.wire_main_script_to_prototype(project_name, "prototype_ch1_new")
        content2 = script_path.read_text(encoding="utf-8")
        assert "call prototype_ch1_new" in content2
        assert "call prototype_ch1_start" not in content2

    def test_rejects_non_template_custom_content(self, project_env):
        service, pm, project_name, tmp_path = project_env
        script_path = tmp_path / project_name / "game" / "script.rpy"
        script_path.write_text(
            'label start:\n    "Custom game logic"\n    jump chapter1\n', encoding="utf-8"
        )

        with pytest.raises(RuntimeError, match="unrecognized content"):
            service.wire_main_script_to_prototype(project_name, "prototype_ch1_start")

    def test_raises_when_no_pm(self):
        from renpy_mcp.services.prototype_activation_service import PrototypeActivationService
        service = PrototypeActivationService(pm=None)
        with pytest.raises(RuntimeError, match="ProjectManager"):
            service.wire_main_script_to_prototype("test", "label")


# ---------------------------------------------------------------------------
# backup / restore
# ---------------------------------------------------------------------------

class TestBackupRestore:
    def test_backup_returns_content(self, project_env):
        service, pm, project_name, tmp_path = project_env
        content = service.backup_main_script(project_name)
        assert content is not None
        assert "Hello from the Ren'Py MCP server!" in content

    def test_backup_returns_none_when_missing(self, project_env):
        service, pm, project_name, tmp_path = project_env
        (tmp_path / project_name / "game" / "script.rpy").unlink()
        content = service.backup_main_script(project_name)
        assert content is None

    def test_restore_writes_content_back(self, project_env):
        service, pm, project_name, tmp_path = project_env
        original = service.backup_main_script(project_name)

        # Overwrite
        script_path = tmp_path / project_name / "game" / "script.rpy"
        script_path.write_text("OVERWRITTEN", encoding="utf-8")

        # Restore
        service.restore_main_script(project_name, original)
        assert script_path.read_text(encoding="utf-8") == original

    def test_restore_does_nothing_when_content_is_none(self, project_env):
        service, pm, project_name, tmp_path = project_env
        script_path = tmp_path / project_name / "game" / "script.rpy"
        before = script_path.read_text(encoding="utf-8")
        service.restore_main_script(project_name, None)
        assert script_path.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------------------
# commit_prototype_replacement
# ---------------------------------------------------------------------------

class TestCommitPrototypeReplacement:
    def test_promotes_staging_to_final(self, project_env):
        service, pm, project_name, tmp_path = project_env
        game_dir = tmp_path / project_name / "game"
        staging_file = game_dir / "prototype_ch1_Test.__staging__.rpy"
        staging_file.write_text("# staged script", encoding="utf-8")

        service.commit_prototype_replacement(
            project_name,
            new_scene_ids=["s1"],
            staging_script_path="game/prototype_ch1_Test.__staging__.rpy",
        )

        final = game_dir / "prototype_ch1_Test.rpy"
        assert final.exists()
        assert not staging_file.exists()
        assert final.read_text(encoding="utf-8") == "# staged script"

    def test_removes_old_prototype_files(self, project_env):
        service, pm, project_name, tmp_path = project_env
        game_dir = tmp_path / project_name / "game"

        # Create old prototype file
        old_proto = game_dir / "prototype_ch0_Old.rpy"
        old_proto.write_text("# old", encoding="utf-8")

        # Create staging file for new prototype
        staging_file = game_dir / "prototype_ch1_New.__staging__.rpy"
        staging_file.write_text("# new", encoding="utf-8")

        service.commit_prototype_replacement(
            project_name,
            new_scene_ids=["s1"],
            staging_script_path="game/prototype_ch1_New.__staging__.rpy",
        )

        assert not old_proto.exists()
        assert (game_dir / "prototype_ch1_New.rpy").exists()


# ---------------------------------------------------------------------------
# rollback_prototype_generation
# ---------------------------------------------------------------------------

class TestRollbackPrototypeGeneration:
    def test_removes_staging_file(self, project_env):
        service, pm, project_name, tmp_path = project_env
        game_dir = tmp_path / project_name / "game"
        staging_file = game_dir / "prototype_ch1_Test.__staging__.rpy"
        staging_file.write_text("# staged", encoding="utf-8")

        service.rollback_prototype_generation(
            project_name,
            staging_script_path="game/prototype_ch1_Test.__staging__.rpy",
            new_scene_ids=[],
            old_script_content=None,
        )
        assert not staging_file.exists()

    def test_does_not_remove_stable_final_file(self, project_env):
        service, pm, project_name, tmp_path = project_env
        game_dir = tmp_path / project_name / "game"
        final_file = game_dir / "prototype_ch1_Test.rpy"
        final_file.write_text("# stable", encoding="utf-8")
        staging_file = game_dir / "prototype_ch1_Test.__staging__.rpy"
        staging_file.write_text("# staged", encoding="utf-8")

        service.rollback_prototype_generation(
            project_name,
            staging_script_path="game/prototype_ch1_Test.__staging__.rpy",
            new_scene_ids=[],
            old_script_content=None,
        )
        assert final_file.exists()
        assert final_file.read_text(encoding="utf-8") == "# stable"

    def test_restores_main_script(self, project_env):
        service, pm, project_name, tmp_path = project_env
        script_path = tmp_path / project_name / "game" / "script.rpy"
        original = script_path.read_text(encoding="utf-8")

        script_path.write_text("OVERWRITTEN", encoding="utf-8")

        service.rollback_prototype_generation(
            project_name,
            staging_script_path=None,
            new_scene_ids=[],
            old_script_content=original,
        )
        assert script_path.read_text(encoding="utf-8") == original

    def test_removes_round_staging_dir(self, project_env):
        service, pm, project_name, tmp_path = project_env
        staging_dir = tmp_path / project_name / "game" / "__staging__" / "round1"
        staging_dir.mkdir(parents=True)
        (staging_dir / "test_file.txt").write_text("test", encoding="utf-8")

        service.rollback_prototype_generation(
            project_name,
            staging_script_path=None,
            new_scene_ids=[],
            old_script_content=None,
            round_id="round1",
        )
        assert not staging_dir.exists()


# ---------------------------------------------------------------------------
# update_index
# ---------------------------------------------------------------------------

class TestUpdateIndex:
    def test_writes_scene_metadata_to_index(self, project_env):
        service, pm, project_name, tmp_path = project_env
        chapter = _make_chapter()
        scenes = _make_scenes()
        scenes[0].sprite_plan = []

        service.update_index(
            project_name, chapter, scenes, "game/prototype_ch1.rpy"
        )

        index = pm.read_project_index(project_name)
        assert index is not None
        assert "proto-ch1-s1" in index["scenes"]
        entry = index["scenes"]["proto-ch1-s1"]
        assert entry["source"] == "prototype"
        assert entry["chapter_id"] == "ch1"
        assert entry["title"] == "First Meeting"
        assert entry["label"] == "prototype_ch1_start"

    def test_preserves_existing_index_entries(self, project_env):
        service, pm, project_name, tmp_path = project_env
        # Write an existing entry
        pm.write_project_index(project_name, {
            "scenes": {"existing_scene": {"title": "Existing"}}
        })

        chapter = _make_chapter()
        scenes = _make_scenes()
        scenes[0].sprite_plan = []

        service.update_index(
            project_name, chapter, scenes, "game/prototype_ch1.rpy"
        )

        index = pm.read_project_index(project_name)
        assert "existing_scene" in index["scenes"]
        assert "proto-ch1-s1" in index["scenes"]


# ---------------------------------------------------------------------------
# _read_managed_entry_label
# ---------------------------------------------------------------------------

class TestReadManagedEntryLabel:
    def test_reads_label_from_managed_region(self, project_env):
        service, pm, project_name, tmp_path = project_env
        service.wire_main_script_to_prototype(project_name, "prototype_ch1_start")

        label = service.read_managed_entry_label(project_name)
        assert label == "prototype_ch1_start"

    def test_returns_none_when_no_managed_region(self, project_env):
        service, pm, project_name, tmp_path = project_env
        label = service.read_managed_entry_label(project_name)
        assert label is None

    def test_returns_none_when_script_missing(self, project_env):
        service, pm, project_name, tmp_path = project_env
        (tmp_path / project_name / "game" / "script.rpy").unlink()
        label = service.read_managed_entry_label(project_name)
        assert label is None
