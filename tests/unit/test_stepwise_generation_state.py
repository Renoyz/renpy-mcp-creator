"""Unit tests for stepwise generation state persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def pm(tmp_path, monkeypatch):
    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)
    return ProjectManager(settings)


@pytest.fixture()
def project(pm):
    project_name = "state_project"
    project_dir = pm.ensure_project_dir(project_name)
    return project_name, project_dir


class TestStepwiseGenerationState:
    @pytest.fixture()
    def service(self, pm):
        from renpy_mcp.services.stepwise_generation_service import StepwiseGenerationService
        return StepwiseGenerationService(pm)

    def test_default_state_when_file_missing(self, service, project):
        project_name, _ = project
        state = service.get_state(project_name)

        assert state["state"] == "idle"
        assert state["round_id"] is None
        assert state["character_assets"] == {}
        assert state["background_assets"] == {}

    def test_new_round_id_skips_existing_round_directories(self, service, project):
        project_name, project_dir = project
        staging_root = project_dir / "game" / "__staging__"
        (staging_root / "r0001").mkdir(parents=True, exist_ok=True)
        (staging_root / "r0002").mkdir(parents=True, exist_ok=True)
        assert service._new_round_id(project_dir) == "r0003"

    def test_save_and_load_state(self, service, project):
        project_name, project_dir = project
        state_file = project_dir / "meta" / "generation_state.json"

        payload = {
            "state": "scene_outline_confirmed",
            "round_id": "r1",
            "character_assets": {},
            "background_assets": {},
        }
        service.save_state(project_name, payload)

        assert state_file.exists()
        loaded = service.get_state(project_name)
        assert loaded["state"] == "scene_outline_confirmed"
        assert loaded["round_id"] == "r1"

    def test_state_file_must_be_valid_json(self, service, project):
        project_name, project_dir = project
        meta_dir = project_dir / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        state_path = meta_dir / "generation_state.json"
        state_path.write_text("{bad json", encoding="utf-8")

        with pytest.raises(ValueError, match="invalid"):
            service.get_state(project_name)

    def test_valid_states_are_exposed(self, service):
        valid_states = set(service.VALID_STATES)
        assert "idle" in valid_states
        assert "scene_outline_draft" in valid_states
        assert "committed" in valid_states
