"""Blueprint generation service — LLM-based blueprint drafting.

Extracted from ``BlueprintOrchestrator._generate_draft_via_llm`` (P2-3) so that
blueprint generation can be:

* unit-tested with a mocked provider (no WebSocket)
* reused outside the chat interview flow
* reasoned about independently of transport
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import ValidationError

from ..blueprint.models import ProjectBlueprint

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def build_transcript(messages: list[dict[str, Any]]) -> str:
    """Build a labelled interview transcript from chat messages."""
    lines: list[str] = []
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str) and content.strip():
            role_label = "User" if m["role"] == "user" else "Assistant"
            lines.append(f"{role_label}: {content}")
    return "\n".join(lines)


def build_generation_prompts(
    project_name: str,
    transcript: str,
    lang: str,
) -> tuple[str, str]:
    """Return ``(system_prompt, user_prompt)`` for blueprint generation."""
    from ..utils.i18n import _language_instruction, _localized_text

    system_prompt = (
        "You are an expert visual novel blueprint designer. "
        "You create structured project blueprints based on user interviews. "
        "You MUST respond with ONLY a valid JSON object. No markdown, no explanations. "
        f"{_language_instruction(lang)}"
    )

    user_prompt = f"""Based on the following interview, design a complete visual novel blueprint.

Project Name: {project_name}

Interview Transcript:
{transcript}

Respond with ONLY a JSON object matching this exact structure:
{{
  "title": "string (use project name or a creative title)",
  "genre": "string",
  "worldview": "string",
  "themes": ["string"],
  "target_audience": "string",
  "estimated_play_time": "string",
  "art_style": "string",
  "audio_style": "string",
  "characters": [
    {{
      "name": "string",
      "role": "string",
      "personality": "string",
      "appearance": "string"
    }}
  ],
  "chapters": [
    {{
      "id": "string",
      "name": "string",
      "order": 1,
      "scenes": [
        {{
          "id": "string",
          "name": "string",
          "order": 1
        }}
      ]
    }}
  ]
}}

Requirements:
- 2-4 chapters, each with 2-4 scenes
- At least 2 well-defined characters
- Themes must match the described tone
- All user-visible string values in the JSON must be written in {_localized_text(lang, "Simplified Chinese", "English")}
- Output ONLY the JSON object, nothing else.
"""
    return system_prompt, user_prompt


def extract_and_validate_blueprint(raw_text: str) -> ProjectBlueprint:
    """Extract JSON from LLM response text, repair if needed, validate schema.

    Raises ``json.JSONDecodeError`` or ``ValueError`` on failure.
    """
    from ..utils.json_repair import _repair_json_text

    text = raw_text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        repaired = _repair_json_text(text)
        data = json.loads(repaired)  # may raise

    try:
        return ProjectBlueprint(**data)
    except ValidationError as exc:
        raise ValueError(f"Blueprint schema validation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Service class
# ---------------------------------------------------------------------------


class BlueprintGenerationService:
    """LLM-based blueprint generation with retry and JSON repair."""

    def __init__(self, provider: Any | None) -> None:
        self.provider = provider

    async def generate_draft(
        self,
        project_name: str,
        messages: list[dict[str, Any]],
        intake_mode: bool = False,
        turn_count: int = 0,
    ) -> ProjectBlueprint:
        """Generate a blueprint draft via LLM with up to 2 retries."""
        if self.provider is None:
            raise RuntimeError(
                "No LLM provider configured. Set ANTHROPIC_API_KEY or deepseek/qwen API key."
            )

        from ..utils.i18n import _preferred_output_language_from_messages
        from ..web.chat_ws import _append_refinement_flow_log

        logger.info(
            "Starting draft generation via LLM for project %s (intake_mode=%s, turn_count=%d)",
            project_name, intake_mode, turn_count,
        )
        _append_refinement_flow_log(
            project_name, "INFO",
            "Starting draft generation via LLM for project %s (intake_mode=%s, turn_count=%d)",
            project_name, intake_mode, turn_count,
        )

        transcript = build_transcript(messages)
        lang = _preferred_output_language_from_messages(messages)
        system_prompt, prompt = build_generation_prompts(project_name, transcript, lang)

        from ..utils.retry import with_async_retry

        async def _attempt() -> ProjectBlueprint:
            try:
                response = await asyncio.to_thread(
                    self.provider.chat,
                    messages=[{"role": "user", "content": prompt}],
                    system=system_prompt,
                    max_tokens=4096,
                )
            except Exception as e:
                logger.exception("Draft generation provider error for project %s", project_name)
                raise RuntimeError(f"Blueprint generation provider error: {e}") from e
            return extract_and_validate_blueprint(response.text)

        def _on_retry(exc: Exception, attempt: int) -> None:
            nonlocal prompt
            logger.warning(
                "Draft generation parse/validation failed for project %s on attempt %d/%d: %s",
                project_name, attempt + 1, 3, exc,
            )
            _append_refinement_flow_log(
                project_name, "WARNING",
                "Draft generation parse/validation failed for project %s on attempt %d/%d: %s",
                project_name, attempt + 1, 3, exc,
            )
            prompt += f"\n\nERROR: Your previous response was not valid ({exc}). Return ONLY valid JSON."

        try:
            blueprint = await with_async_retry(
                _attempt,
                max_retries=2,
                retryable=(json.JSONDecodeError, ValueError),
                on_retry=_on_retry,
            )
        except Exception as exc:
            logger.error(
                "Draft generation exhausted retries for project %s: %s",
                project_name, exc,
            )
            _append_refinement_flow_log(
                project_name, "ERROR",
                "Draft generation exhausted retries for project %s: %s",
                project_name, exc,
            )
            raise RuntimeError(
                f"Blueprint generation failed after 3 attempts. {exc}"
            ) from exc

        logger.info(
            "Draft generation succeeded for project %s with %d chapters",
            project_name, len(blueprint.chapters),
        )
        _append_refinement_flow_log(
            project_name, "INFO",
            "Draft generation succeeded for project %s with %d chapters",
            project_name, len(blueprint.chapters),
        )
        return blueprint
