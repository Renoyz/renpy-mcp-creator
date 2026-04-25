"""TDD tests for BlueprintGenerationService (P2-3 extraction).

Tests cover:
* Transcript building from chat messages (pure)
* Prompt construction (pure)
* JSON extraction + repair + validation (pure)
* Full generate_draft flow with mocked LLM provider (async)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from renpy_mcp.blueprint.models import ProjectBlueprint


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _valid_blueprint_json() -> dict:
    return {
        "title": "Test Story",
        "genre": "Fantasy",
        "worldview": "Medieval",
        "themes": ["friendship"],
        "target_audience": "Young Adult",
        "estimated_play_time": "1hr",
        "art_style": "Anime",
        "audio_style": "Orchestral",
        "characters": [
            {"name": "Alice", "role": "protagonist", "personality": "brave", "appearance": "tall"},
            {"name": "Bob", "role": "antagonist", "personality": "cunning", "appearance": "dark"},
        ],
        "chapters": [
            {
                "id": "ch1",
                "name": "Beginning",
                "order": 1,
                "scenes": [{"id": "s1", "name": "Intro", "order": 1}],
            },
            {
                "id": "ch2",
                "name": "Climax",
                "order": 2,
                "scenes": [{"id": "s2", "name": "Confrontation", "order": 1}],
            },
        ],
    }


# ---------------------------------------------------------------------------
# build_transcript
# ---------------------------------------------------------------------------

class TestBuildTranscript:
    def test_builds_labeled_lines_from_messages(self):
        from renpy_mcp.services.blueprint_generation import build_transcript

        messages = [
            {"role": "user", "content": "I want a fantasy story"},
            {"role": "assistant", "content": "Great idea!"},
            {"role": "user", "content": "With 3 chapters"},
        ]
        result = build_transcript(messages)
        assert "User: I want a fantasy story" in result
        assert "Assistant: Great idea!" in result
        assert "User: With 3 chapters" in result

    def test_skips_non_string_content(self):
        from renpy_mcp.services.blueprint_generation import build_transcript

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": {"key": "value"}},
            {"role": "user", "content": ""},
            {"role": "user", "content": "   "},
        ]
        result = build_transcript(messages)
        assert "User: Hello" in result
        assert "key" not in result
        lines = [l for l in result.strip().splitlines() if l.strip()]
        assert len(lines) == 1

    def test_empty_messages_returns_empty_string(self):
        from renpy_mcp.services.blueprint_generation import build_transcript

        assert build_transcript([]) == ""


# ---------------------------------------------------------------------------
# build_generation_prompts
# ---------------------------------------------------------------------------

class TestBuildGenerationPrompts:
    def test_includes_project_name_in_user_prompt(self):
        from renpy_mcp.services.blueprint_generation import build_generation_prompts

        sys_prompt, user_prompt = build_generation_prompts("my_project", "User: Hello", "zh")
        assert "my_project" in user_prompt

    def test_system_prompt_mentions_json(self):
        from renpy_mcp.services.blueprint_generation import build_generation_prompts

        sys_prompt, _ = build_generation_prompts("p", "t", "en")
        assert "JSON" in sys_prompt

    def test_includes_transcript_in_user_prompt(self):
        from renpy_mcp.services.blueprint_generation import build_generation_prompts

        _, user_prompt = build_generation_prompts("p", "User: I want a romance", "en")
        assert "User: I want a romance" in user_prompt

    def test_language_instruction_zh(self):
        from renpy_mcp.services.blueprint_generation import build_generation_prompts

        sys_prompt, user_prompt = build_generation_prompts("p", "t", "zh")
        assert "Simplified Chinese" in sys_prompt or "Chinese" in user_prompt

    def test_language_instruction_en(self):
        from renpy_mcp.services.blueprint_generation import build_generation_prompts

        sys_prompt, user_prompt = build_generation_prompts("p", "t", "en")
        assert "English" in sys_prompt or "English" in user_prompt


# ---------------------------------------------------------------------------
# extract_and_validate_blueprint
# ---------------------------------------------------------------------------

class TestExtractAndValidateBlueprint:
    def test_valid_json_returns_blueprint(self):
        from renpy_mcp.services.blueprint_generation import extract_and_validate_blueprint

        raw = json.dumps(_valid_blueprint_json())
        bp = extract_and_validate_blueprint(raw)
        assert isinstance(bp, ProjectBlueprint)
        assert bp.title == "Test Story"
        assert len(bp.chapters) == 2

    def test_extracts_from_markdown_code_block(self):
        from renpy_mcp.services.blueprint_generation import extract_and_validate_blueprint

        raw = "```json\n" + json.dumps(_valid_blueprint_json()) + "\n```"
        bp = extract_and_validate_blueprint(raw)
        assert bp.title == "Test Story"

    def test_repairs_trailing_commas(self):
        from renpy_mcp.services.blueprint_generation import extract_and_validate_blueprint

        data = _valid_blueprint_json()
        raw = json.dumps(data)
        # Insert a trailing comma before the last }
        raw = raw[:-1] + ",}"
        bp = extract_and_validate_blueprint(raw)
        assert bp.title == "Test Story"

    def test_raises_on_completely_invalid_text(self):
        from renpy_mcp.services.blueprint_generation import extract_and_validate_blueprint

        with pytest.raises((json.JSONDecodeError, ValueError)):
            extract_and_validate_blueprint("This is not JSON at all")

    def test_raises_on_valid_json_but_invalid_schema(self):
        from renpy_mcp.services.blueprint_generation import extract_and_validate_blueprint

        raw = json.dumps({"invalid": "schema"})
        with pytest.raises((ValueError, Exception)):
            extract_and_validate_blueprint(raw)


# ---------------------------------------------------------------------------
# BlueprintGenerationService.generate_draft
# ---------------------------------------------------------------------------

class TestBlueprintGenerationServiceGenerateDraft:
    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        response = MagicMock()
        response.text = json.dumps(_valid_blueprint_json())
        provider.chat = MagicMock(return_value=response)
        return provider

    @pytest.mark.asyncio
    async def test_generate_draft_returns_blueprint(self, mock_provider):
        from renpy_mcp.services.blueprint_generation import BlueprintGenerationService

        svc = BlueprintGenerationService(mock_provider)
        messages = [
            {"role": "user", "content": "I want a fantasy story"},
            {"role": "assistant", "content": "OK"},
        ]
        bp = await svc.generate_draft("test_proj", messages)
        assert isinstance(bp, ProjectBlueprint)
        assert bp.title == "Test Story"
        mock_provider.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_draft_retries_on_json_error(self):
        from renpy_mcp.services.blueprint_generation import BlueprintGenerationService

        provider = MagicMock()
        bad_response = MagicMock()
        bad_response.text = "not valid json at all"
        good_response = MagicMock()
        good_response.text = json.dumps(_valid_blueprint_json())
        provider.chat = MagicMock(side_effect=[bad_response, good_response])

        svc = BlueprintGenerationService(provider)
        bp = await svc.generate_draft("retry_proj", [{"role": "user", "content": "hello"}])
        assert isinstance(bp, ProjectBlueprint)
        assert provider.chat.call_count == 2

    @pytest.mark.asyncio
    async def test_generate_draft_raises_after_max_retries(self):
        from renpy_mcp.services.blueprint_generation import BlueprintGenerationService

        provider = MagicMock()
        bad_response = MagicMock()
        bad_response.text = "not json"
        provider.chat = MagicMock(return_value=bad_response)

        svc = BlueprintGenerationService(provider)
        with pytest.raises(RuntimeError, match="failed after"):
            await svc.generate_draft("fail_proj", [{"role": "user", "content": "hello"}])
        assert provider.chat.call_count == 3  # initial + 2 retries

    @pytest.mark.asyncio
    async def test_generate_draft_raises_on_provider_error(self):
        from renpy_mcp.services.blueprint_generation import BlueprintGenerationService

        provider = MagicMock()
        provider.chat = MagicMock(side_effect=ConnectionError("network error"))

        svc = BlueprintGenerationService(provider)
        with pytest.raises(RuntimeError, match="provider error"):
            await svc.generate_draft("err_proj", [{"role": "user", "content": "hello"}])

    @pytest.mark.asyncio
    async def test_generate_draft_with_no_provider_raises(self):
        from renpy_mcp.services.blueprint_generation import BlueprintGenerationService

        svc = BlueprintGenerationService(None)
        with pytest.raises(RuntimeError, match="[Nn]o.*provider"):
            await svc.generate_draft("no_prov", [{"role": "user", "content": "hello"}])
