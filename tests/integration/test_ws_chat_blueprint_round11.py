"""Phase 5 Round 11: WebSocket streaming progress tests."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from renpy_mcp.web.fastapi_app import create_app


@pytest.fixture(autouse=True)
def _mock_interview_for_downstream_blueprint_flow(monkeypatch):
    """Drive downstream blueprint tests without invoking the real adaptive interview.

    These tests cover draft generation, refinement state, confirmation, outline,
    prototype, and rollback behavior. They are not intended to validate the
    interview model/prompt itself.
    """
    from renpy_mcp.services.refinement_logic import select_collecting_response

    async def _mock(self, user_message):
        if self.turn_count < 2:
            content, message_kind = select_collecting_response(
                self.turn_count, self.intake_mode, "zh"
            )
            return {
                "content": content,
                "message_kind": message_kind,
                "is_conclusion": False,
                "slot_updates": {},
            }
        return {"content": "Interview complete", "is_conclusion": True, "slot_updates": {}}

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws.BlueprintOrchestrator._conduct_interview_round",
        _mock,
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from renpy_mcp.config import RenPyConfig, get_settings
    from renpy_mcp.web.fastapi_app import set_config

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)
    set_config(RenPyConfig(sdk_path=Path(".")))
    app = create_app()
    return TestClient(app)


def _create_project(client: TestClient, tmp_path: Path, name: str) -> None:
    game_dir = tmp_path / name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")
    r = client.post("/api/projects", json={"name": name})
    assert r.status_code == 200


def _make_mock_blueprint_provider(title: str = "DEFAULT", **overrides) -> object:
    import json
    blueprint = {
        "title": title,
        "genre": "Test",
        "worldview": "Test",
        "themes": ["test"],
        "target_audience": "test",
        "estimated_play_time": "1h",
        "art_style": "test",
        "audio_style": "test",
        "characters": [
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall"},
        ],
        "chapters": [
            {
                "id": "ch1",
                "name": "Chapter1",
                "order": 1,
                "scenes": [{"id": "s1", "name": "Scene1", "order": 1}],
            }
        ],
    }
    blueprint.update(overrides)

    class MockProvider:
        tool_format = "anthropic"

        def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
            from renpy_mcp.chat_engine.providers import LLMResponse
            return LLMResponse(
                content_blocks=[{"type": "text", "text": json.dumps(blueprint, ensure_ascii=False)}],
                stop_reason="end_turn",
            )

    return MockProvider()


def _make_mock_smart_provider(title: str = "DEFAULT", **overrides) -> object:
    """Return a provider that can also handle prototype scene generation."""
    import json
    blueprint = {
        "title": title,
        "genre": "Test",
        "worldview": "Test",
        "themes": ["test"],
        "target_audience": "test",
        "estimated_play_time": "1h",
        "art_style": "test",
        "audio_style": "test",
        "characters": [
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall"},
        ],
        "chapters": [
            {
                "id": "ch1",
                "name": "Chapter1",
                "order": 1,
                "scenes": [{"id": "s1", "name": "Scene1", "order": 1}],
            }
        ],
    }
    blueprint.update(overrides)

    scenes = [
        {
            "scene_id": "proto-ch1-s1",
            "title": "Test",
            "summary": "Test scene.",
            "location": "library",
            "location_visual_brief": "Quiet library",
            "mood": "neutral",
            "characters_present": ["Alice"],
            "dialogue_beats": [
                {"speaker": "Alice", "intent": "test", "content_brief": "Hello"},
            ],
            "entry_label": "prototype_ch1_start",
            "next_scene_id": None,
        },
    ]

    class MockSmartProvider:
        tool_format = "anthropic"

        def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
            from renpy_mcp.chat_engine.providers import LLMResponse
            prompt = messages[0].get("content", "") if messages else ""
            if "Generate a JSON array of scenes" in prompt:
                return LLMResponse(
                    content_blocks=[{"type": "text", "text": json.dumps(scenes, ensure_ascii=False)}],
                    stop_reason="end_turn",
                )
            return LLMResponse(
                content_blocks=[{"type": "text", "text": json.dumps(blueprint, ensure_ascii=False)}],
                stop_reason="end_turn",
            )

    return MockSmartProvider()


def _drain_events(websocket, expected_count: int):
    events = []
    for _ in range(expected_count):
        events.append(websocket.receive_json())
    return events


# ---------------------------------------------------------------------------
# Round 11: Streaming progress tests
# ---------------------------------------------------------------------------


def test_confirmation_streams_progress_events_before_pipeline_completion(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """Progress events must be streamed before the full pipeline completes,
    not batched and sent only at the end."""
    import asyncio
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService

    project_name = "bp_stream_before_complete"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: _make_mock_smart_provider(title=project_name),
    )

    # Slow down generate_scenes so the pipeline takes noticeable time
    original_generate_scenes = PrototypeGenerationService.generate_scenes

    async def slow_generate_scenes(self, chapter, blueprint):
        await asyncio.sleep(1.5)
        return await original_generate_scenes(self, chapter, blueprint)

    monkeypatch.setattr(PrototypeGenerationService, "generate_scenes", slow_generate_scenes)

    confirmation_id = None
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({
            "type": "user_message",
            "content": "start_blueprint_collection",
            "project_name": project_name,
        })
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({
                "type": "user_message",
                "content": f"turn {turn}",
                "project_name": project_name,
            })
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                events = _drain_events(websocket, 3)
                req_event = next(e for e in events if e["type"] == "confirmation_request")
                confirmation_id = req_event["confirmation_id"]

        # Send confirmation
        websocket.send_json({
            "type": "confirmation_response",
            "confirmation_id": confirmation_id,
            "approved": True,
            "project_name": project_name,
        })

        # The first event must arrive quickly (< 1s) even though the whole pipeline sleeps 1.5s
        start = time.perf_counter()
        first_event = websocket.receive_json()
        elapsed = time.perf_counter() - start

        assert first_event["type"] == "progress", (
            f"Expected first event to be progress, got {first_event}"
        )
        assert first_event.get("pipeline_stage") == "generating", (
            f"Expected pipeline_stage generating, got {first_event}"
        )
        assert elapsed < 1.0, (
            f"First progress event took too long ({elapsed:.2f}s); "
            "it should be streamed immediately, not batched until pipeline end"
        )

        # Drain remaining events
        while True:
            data = websocket.receive_json()
            if data.get("pipeline_stage") == "editing" and data["type"] == "message":
                break


def test_confirmation_progress_first_event_arrives_without_waiting_for_build(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """The first progress event must reach the client before build starts,
    confirming that progress is truly streamed, not accumulated."""
    import asyncio
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services import build_manager as bm
    from renpy_mcp.models import BuildResult

    project_name = "bp_stream_before_build"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: _make_mock_smart_provider(title=project_name),
    )

    build_started = [False]

    async def slow_build(self, request):
        build_started[0] = True
        await asyncio.sleep(1.0)
        build_dir = tmp_path / f"{request.project_name}-dists" / f"{request.project_name}-web"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "index.html").write_text("<html>mock</html>", encoding="utf-8")
        return BuildResult(
            project_name=request.project_name,
            target=request.target,
            success=True,
            output_path=build_dir,
        )

    monkeypatch.setattr(bm.BuildManager, "build", slow_build)

    confirmation_id = None
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({
            "type": "user_message",
            "content": "start_blueprint_collection",
            "project_name": project_name,
        })
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({
                "type": "user_message",
                "content": f"turn {turn}",
                "project_name": project_name,
            })
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                events = _drain_events(websocket, 3)
                req_event = next(e for e in events if e["type"] == "confirmation_request")
                confirmation_id = req_event["confirmation_id"]

        websocket.send_json({
            "type": "confirmation_response",
            "confirmation_id": confirmation_id,
            "approved": True,
            "project_name": project_name,
        })

        # First progress must arrive before build starts
        start = time.perf_counter()
        first_event = websocket.receive_json()
        elapsed = time.perf_counter() - start

        assert first_event["type"] == "progress"
        assert elapsed < 1.0, (
            f"First progress took {elapsed:.2f}s; should arrive immediately"
        )
        # At this point build may or may not have started, but the first
        # progress definitely arrived before the whole operation finished.

        while True:
            data = websocket.receive_json()
            if data.get("pipeline_stage") == "editing" and data["type"] == "message":
                break
