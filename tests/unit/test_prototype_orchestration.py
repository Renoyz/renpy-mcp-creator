"""TDD tests for PrototypeOrchestrationService (P2-3 extraction).

Tests cover:
* Pipeline runs all steps and reports progress
* Pipeline returns success/error correctly
* Rollback on failure
* Auto-build behavior
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from renpy_mcp.blueprint.models import ProjectBlueprint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_draft() -> ProjectBlueprint:
    return ProjectBlueprint(
        title="Test",
        genre="Fantasy",
        worldview="Medieval",
        themes=["adventure"],
        target_audience="YA",
        estimated_play_time="1hr",
        art_style="Anime",
        audio_style="Orchestral",
        characters=[
            {"name": "Alice", "role": "protagonist", "personality": "brave", "appearance": "tall"},
        ],
        chapters=[
            {
                "id": "ch1",
                "name": "Chapter One",
                "order": 1,
                "scenes": [{"id": "s1", "name": "Scene 1", "order": 1}],
            },
        ],
    )


def _make_mock_pm():
    pm = MagicMock()
    pm.read_project_meta.return_value = MagicMock(
        pipeline_stage="idle",
        status="draft",
        chapter_count=0,
        scene_count=0,
    )
    pm.write_blueprint = MagicMock()
    pm.write_project_meta = MagicMock()
    return pm


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPrototypeOrchestrationService:
    @pytest.mark.asyncio
    async def test_importable(self):
        from renpy_mcp.services.prototype_orchestration import PrototypeOrchestrationService
        assert PrototypeOrchestrationService is not None

    @pytest.mark.asyncio
    async def test_pipeline_result_dataclass(self):
        from renpy_mcp.services.prototype_orchestration import PipelineResult

        result = PipelineResult(success=True)
        assert result.success is True
        assert result.prototype_error is None
        assert result.build_error is None

    @pytest.mark.asyncio
    async def test_run_pipeline_calls_progress_callback(self):
        from renpy_mcp.services.prototype_orchestration import PrototypeOrchestrationService

        pm = _make_mock_pm()
        svc = PrototypeOrchestrationService(pm)

        progress_steps: list[tuple[str, int]] = []

        async def on_progress(step: str, percent: int):
            progress_steps.append((step, percent))

        mock_provider = MagicMock()
        mock_scenes = [MagicMock(scene_id="s1", entry_label="proto_start")]

        with patch.object(svc, '_run_generation_steps', new_callable=AsyncMock) as mock_gen, \
             patch.object(svc, '_run_auto_build', new_callable=AsyncMock) as mock_build:
            mock_gen.return_value = (None, [], None, None, None, None, None, None)
            mock_build.return_value = None

            result = await svc.run_pipeline(
                "test_proj", _make_draft(),
                on_progress=on_progress,
            )
            # Progress should have been called at least once
            assert len(progress_steps) > 0
            # Percentages should be monotonically increasing
            percents = [p[1] for p in progress_steps]
            assert percents == sorted(percents)

    @pytest.mark.asyncio
    async def test_run_pipeline_returns_success_on_happy_path(self):
        from renpy_mcp.services.prototype_orchestration import PrototypeOrchestrationService

        pm = _make_mock_pm()
        svc = PrototypeOrchestrationService(pm)

        with patch.object(svc, '_run_generation_steps', new_callable=AsyncMock) as mock_gen, \
             patch.object(svc, '_run_auto_build', new_callable=AsyncMock) as mock_build:
            mock_gen.return_value = (None, [], None, None, None, None, None, None)
            mock_build.return_value = None

            result = await svc.run_pipeline("test_proj", _make_draft())
            assert result.success is True
            assert result.prototype_error is None

    @pytest.mark.asyncio
    async def test_run_pipeline_returns_error_on_generation_failure(self):
        from renpy_mcp.services.prototype_orchestration import PrototypeOrchestrationService

        pm = _make_mock_pm()
        svc = PrototypeOrchestrationService(pm)

        with patch.object(svc, '_run_generation_steps', new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = RuntimeError("Scene generation exploded")

            result = await svc.run_pipeline("test_proj", _make_draft())
            assert result.success is False
            assert "exploded" in result.prototype_error

    @pytest.mark.asyncio
    async def test_run_pipeline_reports_build_error_separately(self):
        from renpy_mcp.services.prototype_orchestration import PrototypeOrchestrationService

        pm = _make_mock_pm()
        svc = PrototypeOrchestrationService(pm)

        with patch.object(svc, '_run_generation_steps', new_callable=AsyncMock) as mock_gen, \
             patch.object(svc, '_run_auto_build', new_callable=AsyncMock) as mock_build:
            mock_gen.return_value = (None, [], None, None, None, None, None, None)
            mock_build.side_effect = RuntimeError("Build failed")

            result = await svc.run_pipeline("test_proj", _make_draft())
            # Generation succeeded but build failed
            assert result.prototype_error is None
            assert result.build_error is not None
            assert "Build failed" in result.build_error
