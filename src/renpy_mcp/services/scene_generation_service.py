"""Scene generation service: LLM scene generation + validation.

Extracted from PrototypeGenerationService (P2-1) to isolate the LLM
scene generation, consistency validation, and style-contract assembly
into a focused, testable unit.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from renpy_mcp.blueprint.models import (
    ChapterStyleProfile,
    ChapterStyleProfiles,
    ChapterSummary,
    CharacterBible,
    CharacterContract,
    CharacterStyleEntry,
    ContinuityBible,
    ContinuityContract,
    DialogueBeat,
    GenerationContract,
    ProjectBlueprint,
    ProjectStyleBible,
    ScenePackageChapter,
    ScenePackageScene,
    ScenePackageSpritePlanItem,
    ScenePackagesSnapshot,
    ToneBible,
    ToneContract,
    VisualBible,
    VisualContract,
)
from renpy_mcp.services.project_manager import ProjectManager

logger = logging.getLogger(__name__)


class SceneGenerationService:
    """LLM-driven scene generation and post-generation validation.

    Responsibilities:
    - Build generation contracts from style bibles / chapter profiles
    - Call the LLM provider to produce scene JSON
    - Parse and validate LLM output into PrototypeScene objects
    - Orchestrate multi-chapter scene generation
    - Persist ScenePackagesSnapshot
    """

    def __init__(self, pm: ProjectManager | None, provider: Any | None) -> None:
        self.pm = pm
        self.provider = provider

    # ------------------------------------------------------------------
    # Incremental scene package progress
    # ------------------------------------------------------------------

    def _progress_path(self, project_name: str):
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for scene generation progress")
        return self.pm._project_dir(project_name) / "meta" / "scene_generation_progress.json"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _chapter_progress_from_blueprint(blueprint: ProjectBlueprint) -> list[dict[str, Any]]:
        return [
            {
                "chapter_id": chapter.id,
                "chapter_name": chapter.name,
                "chapter_order": chapter.order,
                "status": "pending",
                "scene_count": 0,
            }
            for chapter in blueprint.chapters
        ]

    def _empty_progress(self, blueprint: ProjectBlueprint) -> dict[str, Any]:
        return {
            "status": "idle",
            "current_chapter_id": None,
            "completed_count": 0,
            "total_count": len(blueprint.chapters),
            "chapters": self._chapter_progress_from_blueprint(blueprint),
            "generated_chapters": {},
            "updated_at": self._now_iso(),
        }

    @staticmethod
    def _public_progress(progress: dict[str, Any]) -> dict[str, Any]:
        chapters = []
        for chapter in progress.get("chapters", []):
            if not isinstance(chapter, dict):
                continue
            safe = {
                "chapter_id": chapter.get("chapter_id"),
                "chapter_name": chapter.get("chapter_name"),
                "chapter_order": chapter.get("chapter_order"),
                "status": chapter.get("status", "pending"),
                "scene_count": chapter.get("scene_count", 0),
            }
            if chapter.get("error"):
                safe["error"] = chapter.get("error")
            chapters.append(safe)
        return {
            "status": progress.get("status", "idle"),
            "current_chapter_id": progress.get("current_chapter_id"),
            "completed_count": progress.get("completed_count", 0),
            "total_count": progress.get("total_count", len(chapters)),
            "chapters": chapters,
            "updated_at": progress.get("updated_at"),
        }

    def _read_progress(self, project_name: str, blueprint: ProjectBlueprint) -> dict[str, Any]:
        if self.pm is None:
            return self._empty_progress(blueprint)

        path = self._progress_path(project_name)
        if not path.exists():
            snapshot = self.pm.read_scene_packages(project_name)
            if snapshot is not None:
                generated_chapters: dict[str, list[dict[str, Any]]] = {}
                chapters: list[dict[str, Any]] = []
                for chapter in sorted(snapshot.chapters, key=lambda ch: ch.chapter_order):
                    generated_chapters[chapter.chapter_id] = [
                        scene.model_dump(mode="json") for scene in chapter.scenes
                    ]
                    chapters.append({
                        "chapter_id": chapter.chapter_id,
                        "chapter_name": chapter.chapter_name,
                        "chapter_order": chapter.chapter_order,
                        "status": "complete",
                        "scene_count": len(chapter.scenes),
                    })
                return {
                    "status": "complete",
                    "current_chapter_id": None,
                    "completed_count": len(chapters),
                    "total_count": len(chapters),
                    "chapters": chapters,
                    "generated_chapters": generated_chapters,
                    "updated_at": self._now_iso(),
                }
            return self._empty_progress(blueprint)

        try:
            progress = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"scene_generation_progress.json for {project_name!r} is invalid") from exc
        if not isinstance(progress, dict):
            raise ValueError(f"scene_generation_progress.json for {project_name!r} is invalid")

        expected_ids = [chapter.id for chapter in blueprint.chapters]
        existing_ids = [
            chapter.get("chapter_id")
            for chapter in progress.get("chapters", [])
            if isinstance(chapter, dict)
        ]
        if existing_ids != expected_ids:
            return self._empty_progress(blueprint)
        progress.setdefault("generated_chapters", {})
        return progress

    def _write_progress(self, project_name: str, progress: dict[str, Any]) -> None:
        path = self._progress_path(project_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        progress["updated_at"] = self._now_iso()
        path.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_scene_generation_status(self, project_name: str, blueprint: ProjectBlueprint) -> dict[str, Any]:
        """Return persisted chapter-level scene generation progress without scene payloads."""
        return self._public_progress(self._read_progress(project_name, blueprint))

    def _chapter_by_id(self, blueprint: ProjectBlueprint, chapter_id: str) -> ChapterSummary:
        for chapter in blueprint.chapters:
            if chapter.id == chapter_id:
                return chapter
        raise ValueError(f"Unknown chapter_id in scene generation progress: {chapter_id}")

    @staticmethod
    def _previous_summaries_from_progress(progress: dict[str, Any], blueprint: ProjectBlueprint, before_chapter_id: str) -> list[str]:
        generated = progress.get("generated_chapters", {})
        if not isinstance(generated, dict):
            return []
        summaries: list[str] = []
        for chapter in blueprint.chapters:
            if chapter.id == before_chapter_id:
                break
            scenes = generated.get(chapter.id)
            if not isinstance(scenes, list):
                continue
            parts = [f"Chapter {chapter.order}: {chapter.name}"]
            for scene in scenes:
                if not isinstance(scene, dict):
                    continue
                parts.append(f"  - {scene.get('scene_id')}: {scene.get('summary')}")
            summaries.append("\n".join(parts))
        return summaries

    def _outline_lookup(self, project_name: str) -> dict[str, dict]:
        outline_lookup: dict[str, dict] = {}
        if self.pm is None:
            return outline_lookup
        try:
            outline = self.pm.read_chapter_outline(project_name)
            if outline:
                for entry in outline.chapters:
                    outline_lookup[entry.chapter_id] = entry.model_dump()
        except Exception as exc:
            logger.warning(
                "Failed to read chapter outline for project %s; continuing without narrative direction: %s",
                project_name,
                exc,
                exc_info=True,
            )
        return outline_lookup

    def _persist_scene_packages_from_progress(
        self,
        project_name: str,
        blueprint: ProjectBlueprint,
        progress: dict[str, Any],
    ) -> dict[str, list]:
        from renpy_mcp.services.prototype_generation_service import PrototypeScene

        generated = progress.get("generated_chapters", {})
        if not isinstance(generated, dict):
            raise RuntimeError("Scene generation progress is missing generated chapters")

        packages: dict[str, list] = {}
        chapter_map = {chapter.id: chapter for chapter in blueprint.chapters}
        for chapter in blueprint.chapters:
            raw_scenes = generated.get(chapter.id)
            if not isinstance(raw_scenes, list):
                raise RuntimeError(f"Scene generation progress is missing chapter {chapter.id!r}")
            packages[chapter.id] = [PrototypeScene(**item) for item in raw_scenes]

        if self.pm is not None:
            snapshot = ScenePackagesSnapshot(
                chapters=[
                    ScenePackageChapter(
                        chapter_id=ch_id,
                        chapter_name=chapter_map[ch_id].name,
                        chapter_order=chapter_map[ch_id].order,
                        scenes=[
                            ScenePackageScene(
                                scene_id=s.scene_id,
                                title=s.title,
                                summary=s.summary,
                                location=s.location,
                                location_visual_brief=s.location_visual_brief,
                                mood=s.mood,
                                characters_present=s.characters_present,
                                dialogue_beats=s.dialogue_beats,
                                sprite_plan=[
                                    ScenePackageSpritePlanItem(
                                        character_name=sp.character_name,
                                        character_id=sp.character_id,
                                        sprite_path=sp.sprite_path,
                                        sprite_placeholder=sp.sprite_placeholder,
                                        sprite_renderable=sp.sprite_renderable,
                                        sprite_quality_reason=sp.sprite_quality_reason,
                                        position=sp.position,
                                        expression=sp.expression,
                                        layout_mode=sp.layout_mode,
                                        transform_name=sp.transform_name,
                                    )
                                    for sp in s.sprite_plan
                                ],
                                entry_label=s.entry_label,
                                next_scene_id=s.next_scene_id,
                                scene_order=idx + 1,
                            )
                            for idx, s in enumerate(sc_list)
                        ],
                    )
                    for ch_id, sc_list in packages.items()
                ]
            )
            self.pm.write_scene_packages(project_name, snapshot)

        return packages

    # ------------------------------------------------------------------
    # Style bible inference and contract assembly
    # ------------------------------------------------------------------

    @staticmethod
    def infer_style_bible_from_blueprint(blueprint: ProjectBlueprint) -> ProjectStyleBible:
        """Infer a minimal project style bible from blueprint data.

        This is used as a safe fallback when no style_bible.json exists.
        The inferred data is marked as generated defaults, not user-authored truth.
        """
        characters = []
        for c in blueprint.characters:
            characters.append(CharacterStyleEntry(
                name=c.name,
                identity_anchors=[c.appearance] if c.appearance else [],
                default_costume="casual",
                forbidden_drift=[],
            ))
        return ProjectStyleBible(
            visual_bible=VisualBible(
                art_direction=blueprint.art_style or "anime visual novel style",
                palette_baseline="neutral",
                camera_language="mid-distance readable staging",
                background_complexity_budget="medium",
                forbidden_visual_drift=[],
            ),
            character_bible=CharacterBible(characters=characters),
            tone_bible=ToneBible(
                narration_style="clean, readable",
                dialogue_style="direct spoken dialogue",
                dialogue_density="short to medium",
                forbidden_tone_drift=[],
            ),
            continuity_bible=ContinuityBible(
                world_rules=[blueprint.worldview] if blueprint.worldview else [],
                relationship_baselines=[],
                must_preserve_facts=[],
            ),
        )

    @staticmethod
    def infer_chapter_profiles_from_blueprint(blueprint: ProjectBlueprint) -> ChapterStyleProfiles:
        """Infer minimal chapter style profiles from blueprint chapter summaries."""
        profiles = []
        for ch in blueprint.chapters:
            profiles.append(ChapterStyleProfile(
                chapter_id=ch.id,
                mood_target="neutral",
                temperature_bias="neutral",
                lighting_bias="neutral",
                pacing_bias="measured",
                emotional_bias="neutral",
                location_motifs=[],
                allowed_variation={
                    "palette_shift_max": "small",
                    "contrast_shift_max": "small",
                    "dialogue_intensity_shift_max": "small",
                },
            ))
        return ChapterStyleProfiles(chapters=profiles)

    def build_generation_contract(
        self,
        project_name: str,
        blueprint: ProjectBlueprint,
        chapter: ChapterSummary,
    ) -> GenerationContract:
        """Assemble a GenerationContract for a specific chapter.

        Loads or infers the project style bible and chapter profiles,
        then merges project-level hard constraints with chapter-level
        soft overrides into visual / character / tone / continuity
        sub-contracts.
        """
        # Load or infer project style bible
        bible: ProjectStyleBible
        if self.pm is not None:
            loaded_bible = self.pm.read_style_bible(project_name)
            bible = loaded_bible if loaded_bible is not None else self.infer_style_bible_from_blueprint(blueprint)
        else:
            bible = self.infer_style_bible_from_blueprint(blueprint)

        # Load or infer chapter profiles
        profiles: ChapterStyleProfiles
        if self.pm is not None:
            loaded_profiles = self.pm.read_chapter_style_profiles(project_name)
            profiles = loaded_profiles if loaded_profiles is not None else self.infer_chapter_profiles_from_blueprint(blueprint)
        else:
            profiles = self.infer_chapter_profiles_from_blueprint(blueprint)

        # Find chapter profile for this chapter
        chapter_profile: ChapterStyleProfile | None = None
        for cp in profiles.chapters:
            if cp.chapter_id == chapter.id:
                chapter_profile = cp
                break
        if chapter_profile is None:
            chapter_profile = ChapterStyleProfile(chapter_id=chapter.id)

        vb = bible.visual_bible
        cb = bible.character_bible
        tb = bible.tone_bible
        ctb = bible.continuity_bible

        # Build visual contract: project hard + chapter soft
        visual_contract = VisualContract(
            art_direction=vb.art_direction,
            palette_baseline=vb.palette_baseline,
            camera_language=vb.camera_language,
            background_complexity_budget=vb.background_complexity_budget,
            forbidden_visual_drift=vb.forbidden_visual_drift,
            # Chapter soft overrides
            mood_target=chapter_profile.mood_target or vb.mood_target,
            temperature_bias=chapter_profile.temperature_bias or vb.temperature_bias,
            lighting_bias=chapter_profile.lighting_bias or vb.lighting_bias,
            location_motifs=chapter_profile.location_motifs or vb.location_motifs,
        )

        # Build character contract: project hard only; chapter cannot override identity
        character_contract = CharacterContract(characters=cb.characters)

        # Build tone contract: project hard + chapter soft (pacing, emotional)
        tone_contract = ToneContract(
            dialogue_style=tb.dialogue_style,
            dialogue_density=tb.dialogue_density,
            narration_style=tb.narration_style,
            forbidden_tone_drift=tb.forbidden_tone_drift,
            # Chapter soft overrides
            pacing_bias=chapter_profile.pacing_bias or tb.pacing_bias,
            emotional_bias=chapter_profile.emotional_bias or tb.emotional_bias,
            mood_target=chapter_profile.mood_target or tb.mood_target,
        )

        # Continuity contract: project-level only
        continuity_contract = ContinuityContract(
            must_preserve_facts=ctb.must_preserve_facts,
            relationship_state=ctb.relationship_baselines,
            world_rules=ctb.world_rules,
        )

        return GenerationContract(
            chapter_id=chapter.id,
            visual_contract=visual_contract,
            character_contract=character_contract,
            tone_contract=tone_contract,
            continuity_contract=continuity_contract,
        )

    # ------------------------------------------------------------------
    # Scene consistency validation
    # ------------------------------------------------------------------

    def _validate_scene_consistency(self, scenes: list) -> None:
        """Validate and auto-correct scene consistency rules.

        Rules enforced:
        1. dialogue_beats.speaker must belong to characters_present.
        2. location_visual_brief must not be empty.
        3. mood must not be empty.
        """
        for scene in scenes:
            # Rule 1: speakers must be in characters_present
            valid_speakers = set(scene.characters_present)
            filtered_beats: list[DialogueBeat] = []
            for beat in scene.dialogue_beats:
                if beat.speaker in valid_speakers:
                    filtered_beats.append(beat)
            scene.dialogue_beats = filtered_beats

            # Rule 2: location_visual_brief fallback
            if not scene.location_visual_brief.strip():
                scene.location_visual_brief = scene.location

            # Rule 3: mood fallback
            if not scene.mood.strip():
                scene.mood = "neutral"

        # Beat count warning (soft check)
        for scene in scenes:
            beats = getattr(scene, "dialogue_beats", []) or []
            if len(beats) < 4:
                logger.warning(
                    "Scene %s has only %d dialogue_beats (recommended >= 4). This may result in sparse narrative.",
                    getattr(scene, "scene_id", "?"), len(beats)
                )

    # ------------------------------------------------------------------
    # LLM scene generation
    # ------------------------------------------------------------------

    async def generate_scenes(
        self,
        chapter: ChapterSummary,
        blueprint: ProjectBlueprint,
        contract: GenerationContract | None = None,
        outline_entry: dict | None = None,
        previous_chapter_summaries: list[str] | None = None,
        min_beats_per_scene: int = 4,
        max_beats_per_scene: int = 8,
    ) -> list:
        """Generate 2-4 structured scenes for the prototype chapter via LLM.

        Args:
            chapter: The prototype chapter selected from the blueprint.
            blueprint: The full confirmed blueprint.
            contract: Optional generation contract with style constraints.

        Returns:
            List of structured PrototypeScene objects.

        Raises:
            RuntimeError: If the provider is not configured or fails.
            ValueError: If the provider response cannot be parsed into valid scenes.
        """
        # Deferred import to avoid circular dependency at module level
        from renpy_mcp.services.prototype_generation_service import PrototypeScene

        if self.provider is None:
            raise RuntimeError("No LLM provider configured for prototype generation.")

        characters_desc = "\n".join(
            f"- {c.name} ({c.role}): {c.personality}, {c.appearance}"
            for c in blueprint.characters
        )

        # Build style constraints block from contract when available
        style_block = ""
        if contract is not None:
            vc = contract.visual_contract
            tc = contract.tone_contract
            cc = contract.continuity_contract
            style_lines: list[str] = []
            style_lines.append("Style Constraints (MUST be respected):")
            if vc.art_direction:
                style_lines.append(f'- Art direction: {vc.art_direction}')
            if vc.palette_baseline:
                style_lines.append(f'- Palette baseline: {vc.palette_baseline}')
            if vc.camera_language:
                style_lines.append(f'- Camera language: {vc.camera_language}')
            if vc.mood_target:
                style_lines.append(f'- Mood target: {vc.mood_target}')
            if vc.lighting_bias:
                style_lines.append(f'- Lighting bias: {vc.lighting_bias}')
            if vc.temperature_bias:
                style_lines.append(f'- Temperature bias: {vc.temperature_bias}')
            if tc.dialogue_style:
                style_lines.append(f'- Dialogue style: {tc.dialogue_style}')
            if tc.pacing_bias:
                style_lines.append(f'- Pacing bias: {tc.pacing_bias}')
            if cc.must_preserve_facts:
                for fact in cc.must_preserve_facts:
                    style_lines.append(f'- Continuity fact: {fact}')
            if vc.forbidden_visual_drift:
                for forbidden in vc.forbidden_visual_drift:
                    style_lines.append(f'- Forbidden visual drift: {forbidden}')
            if tc.forbidden_tone_drift:
                for forbidden in tc.forbidden_tone_drift:
                    style_lines.append(f'- Forbidden tone drift: {forbidden}')
            style_block = "\n".join(style_lines) + "\n\n"

        # Construct narrative block from chapter outline
        narrative_lines = []
        if outline_entry:
            narrative_lines.append("Chapter Narrative Direction:")
            if outline_entry.get("chapter_goal"):
                narrative_lines.append(f"- Chapter Goal: {outline_entry['chapter_goal']}")
            if outline_entry.get("emotional_arc"):
                narrative_lines.append(f"- Emotional Arc: {outline_entry['emotional_arc']}")
                if "climax -> resolution" in outline_entry["emotional_arc"]:
                    narrative_lines.append(
                        "- Prefer a concrete story-state resolution when compatible with the "
                        "requested ending; avoid relying only on reflective/philosophical "
                        "closure. Whenever possible, include irreversible progression in "
                        "relationships or world-state."
                    )
            if outline_entry.get("key_conflict"):
                narrative_lines.append(f"- Key Conflict: {outline_entry['key_conflict']}")
            if outline_entry.get("character_focus"):
                chars = ", ".join(outline_entry["character_focus"])
                narrative_lines.append(f"- Character Focus: {chars}")
            if outline_entry.get("relationship_shift"):
                narrative_lines.append(f"- Relationship Shift: {outline_entry['relationship_shift']}")
            if outline_entry.get("reveals"):
                narrative_lines.append(f"- Key Reveals: {outline_entry['reveals']}")
            if outline_entry.get("end_state"):
                narrative_lines.append(f"- Desired End State: {outline_entry['end_state']}")
            if outline_entry.get("mood_or_pacing_bias"):
                narrative_lines.append(f"- Mood / Pacing: {outline_entry['mood_or_pacing_bias']}")
            narrative_lines.append("")
        narrative_block = "\n".join(narrative_lines)

        # Construct continuity block from previous chapters
        continuity_lines = []
        if previous_chapter_summaries:
            continuity_lines.append("Previously Established (DO NOT REPEAT):")
            for prev in previous_chapter_summaries:
                continuity_lines.append(prev)
            continuity_lines.append(
                "Ensure this chapter starts from a different location and situation than "
                "previous chapters. Do NOT repeat the same arrival/introduction pattern."
            )
            continuity_lines.append("")
        continuity_block = "\n".join(continuity_lines)

        prompt = f"""Based on the following blueprint, generate 2-4 detailed scenes for the prototype chapter.

Project: {blueprint.title}
Genre: {blueprint.genre}
Worldview: {blueprint.worldview}
Themes: {', '.join(blueprint.themes)}

Characters:
{characters_desc}

Prototype Chapter: {chapter.name} (chapter_id: "{chapter.id}")

{narrative_block}{continuity_block}{style_block}Generate a JSON array of scenes. Each scene must have these fields:
- scene_id: unique identifier string (prefixed with the chapter_id, e.g., "{chapter.id}-s1")
- title: scene title
- summary: 1-2 sentence narration summary
- location: setting name (e.g., "library", "cafe")
- location_visual_brief: visual description for background generation (e.g., "\u88ab\u706b\u7130\u541e\u566c\u7684\u6751\u5e84\u5e9f\u589f\uff0c\u591c\u8272\u3001\u6b8b\u5899\u3001\u4f59\u70ec\u3001\u4f4e\u80fd\u89c1\u5ea6")
- mood: emotional tone of the scene (e.g., "\u60b2\u6006", "\u7d27\u5f20", "\u538b\u8feb", "\u77ed\u6682\u6e29\u6696", "\u6000\u7591")
- characters_present: list of character names appearing in this scene
- dialogue_beats: array of dialogue beats, each with:
  - speaker: character name (must be in characters_present)
  - intent: what the character is trying to do or feel
  - content_brief: brief description of what they say
  - spoken_line: the final in-character spoken dialogue line for the game UI
- entry_label: Ren'Py label name for this scene. MUST use the chapter_id "{chapter.id}". Use "prototype_{chapter.id}_start" for the first scene, "prototype_{chapter.id}_scene_2" for the second, etc. Never use a different chapter_id (like "ch1") for this chapter.
- next_scene_id: scene_id of the next scene, or null for the last scene

Consistency rules:
- Every dialogue_beats.speaker MUST be in characters_present.
- The mood must be reflected in both the location_visual_brief and the dialogue beats.
- If the location changes between scenes, the visual brief must also change.
- spoken_line must be direct spoken dialogue, not narration or a third-person summary.
- Do NOT write spoken_line like "\u8be2\u95ee\u5bf9\u65b9...", "\u4f4e\u58f0\u81ea\u8bed...", "\u5c55\u5f00\u53cc\u81c2\u8bf4...".
- spoken_line should read like natural VN dialogue the character can say aloud in Chinese, 1-2 sentences max.
- All entry_label values must use chapter_id "{chapter.id}" \u2014 never copy labels from other chapters.

Requirements:
- 2 to 4 scenes total
- Linear flow: each scene (except last) points to the next
- Last scene has next_scene_id = null
- Each scene MUST have between {min_beats_per_scene} and {max_beats_per_scene} dialogue_beats
- Each dialogue beat should feel like a complete emotional exchange, not a single-line reply
- Build mini-arcs within the scene's beats: setup -> tension -> release/follow-through
- Output ONLY the JSON array, nothing else.
"""

        from ..utils.retry import with_async_retry

        async def _attempt() -> list[PrototypeScene]:
            try:
                response = await asyncio.to_thread(
                    self.provider.chat,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4096,
                )
            except Exception as e:
                raise RuntimeError(f"Prototype generation provider error: {e}") from e

            text = response.text.strip()
            # Extract JSON from markdown code blocks if present
            if text.startswith("```"):
                lines = text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines).strip()

            data = json.loads(text)
            if not isinstance(data, list):
                raise ValueError("Expected JSON array of scenes")

            scenes = [PrototypeScene(**item) for item in data]
            self._validate_scene_consistency(scenes)
            # Override entry_labels with chapter-correct values to prevent
            # cross-chapter label duplication when the LLM copies the ch1 example.
            for i, scene in enumerate(scenes):
                scene.entry_label = (
                    f"prototype_{chapter.id}_start"
                    if i == 0
                    else f"prototype_{chapter.id}_scene_{i + 1}"
                )
            return scenes

        def _on_retry(exc: Exception, attempt: int) -> None:
            nonlocal prompt
            if isinstance(exc, json.JSONDecodeError):
                prompt += f"\n\nERROR: Your previous response was not valid JSON ({exc}). Return ONLY a valid JSON array."
            else:
                prompt += f"\n\nERROR: Your previous response did not match the required scene schema ({exc}). Fix and return a valid JSON array."

        try:
            return await with_async_retry(
                _attempt,
                max_retries=2,
                retryable=(json.JSONDecodeError, ValidationError, ValueError),
                on_retry=_on_retry,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Scene generation failed after 3 attempts. {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Multi-chapter scene generation
    # ------------------------------------------------------------------

    async def generate_next_chapter_scene_package(
        self,
        project_name: str,
        blueprint: ProjectBlueprint,
    ) -> dict[str, Any]:
        """Generate exactly one pending/failed chapter and persist progress.

        The official ``scene_packages.json`` is written only after every chapter
        succeeds, so downstream prototype/script generation never consumes a
        partial scene package snapshot.
        """
        if self.provider is None:
            raise RuntimeError("No LLM provider configured for prototype generation.")

        progress = self._read_progress(project_name, blueprint)
        if progress.get("status") == "complete":
            return self._public_progress(progress)

        chapters = progress.get("chapters", [])
        if not isinstance(chapters, list):
            progress = self._empty_progress(blueprint)
            chapters = progress["chapters"]

        next_entry: dict[str, Any] | None = None
        for entry in chapters:
            if isinstance(entry, dict) and entry.get("status") in {"pending", "failed"}:
                next_entry = entry
                break
        if next_entry is None:
            progress["status"] = "complete"
            progress["current_chapter_id"] = None
            self._persist_scene_packages_from_progress(project_name, blueprint, progress)
            self._write_progress(project_name, progress)
            return self._public_progress(progress)

        chapter_id = str(next_entry.get("chapter_id"))
        chapter = self._chapter_by_id(blueprint, chapter_id)
        next_entry["status"] = "generating"
        next_entry.pop("error", None)
        progress["status"] = "in_progress"
        progress["current_chapter_id"] = chapter_id
        self._write_progress(project_name, progress)

        outline_lookup = self._outline_lookup(project_name)
        contract = self.build_generation_contract(project_name, blueprint, chapter)
        previous_chapter_summaries = self._previous_summaries_from_progress(progress, blueprint, chapter_id)

        try:
            scenes = await self.generate_scenes(
                chapter,
                blueprint,
                contract=contract,
                outline_entry=outline_lookup.get(chapter.id),
                previous_chapter_summaries=previous_chapter_summaries,
                min_beats_per_scene=4,
                max_beats_per_scene=8,
            )
        except Exception as exc:
            next_entry["status"] = "failed"
            next_entry["error"] = str(exc)
            progress["status"] = "failed"
            progress["current_chapter_id"] = chapter_id
            self._write_progress(project_name, progress)
            raise

        generated = progress.setdefault("generated_chapters", {})
        if not isinstance(generated, dict):
            generated = {}
            progress["generated_chapters"] = generated
        generated[chapter_id] = [scene.model_dump(mode="json") for scene in scenes]
        next_entry["status"] = "complete"
        next_entry["scene_count"] = len(scenes)
        next_entry.pop("error", None)

        completed = sum(
            1 for entry in chapters
            if isinstance(entry, dict) and entry.get("status") == "complete"
        )
        progress["completed_count"] = completed
        progress["total_count"] = len(chapters)
        if completed == len(chapters):
            progress["status"] = "complete"
            progress["current_chapter_id"] = None
            self._persist_scene_packages_from_progress(project_name, blueprint, progress)
        else:
            progress["status"] = "in_progress"
            progress["current_chapter_id"] = chapter_id
        self._write_progress(project_name, progress)
        return self._public_progress(progress)

    async def generate_all_chapter_scenes(
        self, project_name: str, blueprint: ProjectBlueprint
    ) -> dict[str, list]:
        """Generate structured scene packages for all chapters in the blueprint.

        Each chapter gets its own generation contract so that project-level
        style remains stable while chapter-level mood/lighting/pacing can vary.

        The result is persisted to ``meta/scene_packages.json`` so that
        multi-chapter data is available to API consumers.

        Returns:
            Mapping chapter_id -> list[PrototypeScene].
        """
        if self.provider is None:
            raise RuntimeError("No LLM provider configured for prototype generation.")

        while True:
            status = await self.generate_next_chapter_scene_package(project_name, blueprint)
            if status.get("status") == "complete":
                break

        progress = self._read_progress(project_name, blueprint)
        return self._persist_scene_packages_from_progress(project_name, blueprint, progress)
