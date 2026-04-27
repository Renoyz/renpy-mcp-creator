"""Unit tests for StepwiseGenerationService (TDD)."""

from __future__ import annotations

import io
import json
import asyncio

from pathlib import Path

import pytest
from PIL import Image


def _rgba_png_bytes(color=(64, 128, 255, 255), size=(640, 360)) -> bytes:
    image = Image.new("RGBA", size=size, color=color)
    buff = io.BytesIO()
    image.save(buff, format="PNG")
    return buff.getvalue()


def _rgb_png_bytes(color=(64, 128, 255), size=(640, 360)) -> bytes:
    image = Image.new("RGB", size=size, color=color)
    buff = io.BytesIO()
    image.save(buff, format="PNG")
    return buff.getvalue()


def _seed_scene_packages(pm, project_name: str) -> None:
    from renpy_mcp.blueprint.models import ScenePackageChapter, ScenePackageScene, ScenePackagesSnapshot

    pm.write_scene_packages(
        project_name,
        ScenePackagesSnapshot(
            chapters=[
                ScenePackageChapter(
                    chapter_id="ch1",
                    chapter_name="Chapter 1",
                    chapter_order=1,
                    scenes=[
                        ScenePackageScene(
                            scene_id="scene_01",
                            title="Rooftop Meeting",
                            summary="Characters talk under the moonlight.",
                            location="rooftop",
                            location_visual_brief="wide street and cafe",
                            mood="calm",
                            characters_present=["Alice", "Bob"],
                            dialogue_beats=[],
                            scene_order=1,
                        )
                    ],
                )
            ]
        ),
    )


def _seed_two_chapter_scene_packages(pm, project_name: str) -> None:
    from renpy_mcp.blueprint.models import ScenePackageChapter, ScenePackageScene, ScenePackagesSnapshot

    pm.write_scene_packages(
        project_name,
        ScenePackagesSnapshot(
            chapters=[
                ScenePackageChapter(
                    chapter_id="ch1",
                    chapter_name="Chapter One",
                    chapter_order=1,
                    scenes=[
                        ScenePackageScene(
                            scene_id="scene_01",
                            title="Rooftop Meeting",
                            summary="Characters talk under the moonlight.",
                            location="rooftop",
                            location_visual_brief="wide street and cafe",
                            mood="calm",
                            characters_present=["Alice", "Bob"],
                            dialogue_beats=[],
                            scene_order=1,
                        )
                    ],
                ),
                ScenePackageChapter(
                    chapter_id="ch2",
                    chapter_name="Chapter Two",
                    chapter_order=2,
                    scenes=[
                        ScenePackageScene(
                            scene_id="scene_02",
                            title="Quiet Office",
                            summary="The conversation gets tense.",
                            location="office",
                            location_visual_brief="focusing lights and papers",
                            mood="tense",
                            characters_present=["Bob", "Carol"],
                            dialogue_beats=[],
                            scene_order=1,
                        )
                    ],
                ),
            ]
        ),
    )


class FakeImageService:
    def __init__(self, color=(21, 42, 84, 255), size=(640, 360)):
        self.color = color
        self.size = size
        self.calls = []

    def is_available(self) -> bool:
        return True

    async def generate_image(
        self,
        *,
        project_dir: Path,
        prompt: str,
        image_type: str,
        base_name: str | None = None,
        generate_emotions: bool = False,
    ):
        from renpy_mcp.models import ImageGenerationResult

        self.calls.append(
            {
                "project_dir": project_dir,
                "prompt": prompt,
                "image_type": image_type,
                "base_name": base_name,
                "generate_emotions": generate_emotions,
            }
        )
        output_dir = project_dir / "game" / "images" / image_type
        output_dir.mkdir(parents=True, exist_ok=True)
        primary = output_dir / f"{base_name or 'generated'}.png"
        primary.write_bytes(_rgba_png_bytes(color=self.color, size=self.size))
        return ImageGenerationResult(
            success=True,
            prompt=prompt,
            image_type=image_type,
            files=[primary],
            primary_file=primary,
        )


@pytest.fixture()
def pm(tmp_path, monkeypatch):
    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)
    return ProjectManager(settings)


@pytest.fixture()
def project(pm):
    project_name = "stepwise_service_proj"
    project_dir = pm.ensure_project_dir(project_name)
    game_dir = project_dir / "game"
    game_dir.mkdir(parents=True, exist_ok=True)
    (game_dir / "script.rpy").write_text(
        'label start:\\n    "existing script"\\n    return\\n',
        encoding="utf-8",
    )
    return project_name, project_dir


class TestStepwiseService:
    @pytest.fixture()
    def service(self, pm):
        from renpy_mcp.services.stepwise_generation_service import StepwiseGenerationService

        return StepwiseGenerationService(pm)

    def test_accept_asset_only_updates_one_item(self, service, project):
        project_name, _ = project
        service.start_characters(project_name)

        char_a = service.upload_character_asset(
            project_name=project_name,
            character_id="alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        char_b = service.upload_character_asset(
            project_name=project_name,
            character_id="bob",
            variant="normal",
            filename="bob.png",
            file_bytes=_rgba_png_bytes(),
        )

        result = service.accept_asset(project_name, char_a["asset_id"])
        assert result["asset_id"] == char_a["asset_id"]
        assert result["status"] == "accepted"

        state = service.get_state(project_name)
        assert state["character_assets"][char_a["asset_id"]]["status"] == "accepted"
        assert state["character_assets"][char_b["asset_id"]]["status"] == "uploaded"

    def test_accepted_item_not_overwritten_without_replace(self, service, project):
        project_name, project_dir = project
        service.start_characters(project_name)
        first = service.upload_character_asset(
            project_name=project_name,
            character_id="alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(color=(10, 20, 30, 255)),
        )
        service.accept_asset(project_name, first["asset_id"])

        with pytest.raises(ValueError, match="accepted"):
            service.upload_character_asset(
                project_name=project_name,
                character_id="alice",
                variant="normal",
                filename="alice.png",
                file_bytes=_rgba_png_bytes(color=(90, 80, 70, 255)),
            )

        state = service.get_state(project_name)
        path = project_dir / state["character_assets"][first["asset_id"]]["staging_path"]
        assert path.exists()

        second = service.upload_character_asset(
            project_name=project_name,
            character_id="alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(color=(90, 80, 70, 255)),
            replace=True,
        )
        assert second["asset_id"] == first["asset_id"]
        assert second["status"] == "uploaded"

    def test_character_reupload_rejects_accepted_slot_without_replace_and_keeps_staging_file(self, service, project):
        project_name, project_dir = project
        service.start_characters(project_name)

        first_upload = service.upload_character_asset(
            project_name=project_name,
            character_id="alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(color=(1, 2, 3, 255)),
        )
        service.accept_asset(project_name, first_upload["asset_id"])

        slot_path = project_dir / first_upload["staging_path"]
        original_staging_bytes = slot_path.read_bytes()

        with pytest.raises(ValueError, match="already accepted"):
            service.upload_character_asset(
                project_name=project_name,
                character_id="alice",
                variant="normal",
                filename="alice.png",
                file_bytes=_rgba_png_bytes(color=(9, 9, 9, 255)),
            )

        assert slot_path.read_bytes() == original_staging_bytes

    def test_generated_character_slot_can_be_accepted_and_keeps_prompt(self, pm, project):
        from renpy_mcp.services.stepwise_generation_service import StepwiseGenerationService

        project_name, project_dir = project
        fake_image_service = FakeImageService()
        service = StepwiseGenerationService(pm, image_service=fake_image_service)
        service.start_characters(project_name)

        slot = asyncio.run(
            service.generate_character_asset(
                project_name=project_name,
                character_id="alice",
                variant="normal",
                prompt="ink vampire hunter sprite",
            )
        )

        assert slot["asset_id"] == "char_alice_normal"
        assert slot["source"] == "generated"
        assert slot["status"] == "generated"
        assert slot["generation_prompt"] == "ink vampire hunter sprite"
        assert slot["preview_url"].startswith(f"/api/projects/{project_name}/asset-file/__staging__/")
        assert not Path(slot["staging_path"]).is_absolute()
        assert (project_dir / slot["staging_path"]).exists()
        assert not fake_image_service.calls[0]["project_dir"].joinpath("game/images/character/alice_normal.png").exists()

        accepted = service.accept_asset(project_name, slot["asset_id"])
        assert accepted["status"] == "accepted"

    def test_generate_replaces_draft_slot_with_new_prompt(self, pm, project):
        from renpy_mcp.services.stepwise_generation_service import StepwiseGenerationService

        project_name, _ = project
        fake_image_service = FakeImageService()
        service = StepwiseGenerationService(pm, image_service=fake_image_service)
        service.start_characters(project_name)

        first = asyncio.run(
            service.generate_character_asset(
                project_name=project_name,
                character_id="alice",
                variant="normal",
                prompt="first prompt",
            )
        )
        second = asyncio.run(
            service.generate_character_asset(
                project_name=project_name,
                character_id="alice",
                variant="normal",
                prompt="second prompt",
            )
        )

        assert second["asset_id"] == first["asset_id"]
        assert second["generation_prompt"] == "second prompt"
        state = service.get_state(project_name)
        assert state["character_assets"][first["asset_id"]]["generation_prompt"] == "second prompt"

    def test_generate_rejects_accepted_slot_without_replace_and_keeps_staging_file(self, pm, project):
        from renpy_mcp.services.stepwise_generation_service import StepwiseGenerationService

        project_name, project_dir = project
        fake_image_service = FakeImageService()
        service = StepwiseGenerationService(pm, image_service=fake_image_service)
        service.start_characters(project_name)
        first = asyncio.run(
            service.generate_character_asset(
                project_name=project_name,
                character_id="alice",
                variant="normal",
                prompt="first prompt",
            )
        )
        service.accept_asset(project_name, first["asset_id"])
        slot_path = project_dir / first["staging_path"]
        original_staging_bytes = slot_path.read_bytes()

        with pytest.raises(ValueError, match="already accepted"):
            asyncio.run(
                service.generate_character_asset(
                    project_name=project_name,
                    character_id="alice",
                    variant="normal",
                    prompt="second prompt",
                )
            )

        assert slot_path.read_bytes() == original_staging_bytes
        assert len(fake_image_service.calls) == 1

    def test_generate_can_replace_accepted_slot_when_requested(self, pm, project):
        from renpy_mcp.services.stepwise_generation_service import StepwiseGenerationService

        project_name, _ = project
        fake_image_service = FakeImageService()
        service = StepwiseGenerationService(pm, image_service=fake_image_service)
        service.start_characters(project_name)
        first = asyncio.run(
            service.generate_character_asset(
                project_name=project_name,
                character_id="alice",
                variant="normal",
                prompt="first prompt",
            )
        )
        service.accept_asset(project_name, first["asset_id"])

        second = asyncio.run(
            service.generate_character_asset(
                project_name=project_name,
                character_id="alice",
                variant="normal",
                prompt="replacement prompt",
                replace=True,
            )
        )

        assert second["asset_id"] == first["asset_id"]
        assert second["status"] == "generated"
        assert second["generation_prompt"] == "replacement prompt"
        state = service.get_state(project_name)
        assert state["character_assets"][first["asset_id"]]["status"] == "generated"
        assert len(fake_image_service.calls) == 2

    def test_background_reupload_rejects_accepted_slot_without_replace_and_keeps_staging_file(self, service, project):
        project_name, project_dir = project
        service.start_characters(project_name)
        service.start_backgrounds(project_name)

        first_upload = service.upload_background_asset(
            project_name=project_name,
            location_id="rooftop",
            variant="main",
            filename="roof.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, first_upload["asset_id"])

        slot_path = project_dir / first_upload["staging_path"]
        original_staging_bytes = slot_path.read_bytes()

        with pytest.raises(ValueError, match="already accepted"):
            service.upload_background_asset(
                project_name=project_name,
                location_id="rooftop",
                variant="main",
                filename="roof.png",
                file_bytes=_rgba_png_bytes(size=(1280, 720), color=(9, 9, 9, 255)),
            )

        assert slot_path.read_bytes() == original_staging_bytes

    def test_required_background_slots_include_scene_description(self, service, project):
        project_name, _ = project
        _seed_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        state = service.start_backgrounds(project_name)

        slot = state["background_assets"]["bg_scene_01_main"]
        assert slot["description"] == "wide street and cafe"
        assert slot["description_source"] == "scene_package"

    def test_generated_background_default_prompt_uses_scene_description(self, pm, project):
        from renpy_mcp.services.stepwise_generation_service import StepwiseGenerationService

        project_name, _ = project
        _seed_scene_packages(pm, project_name)
        fake_image_service = FakeImageService(size=(1280, 720))
        service = StepwiseGenerationService(pm, image_service=fake_image_service)
        service.start_characters(project_name)
        service.start_backgrounds(project_name)

        slot = asyncio.run(
            service.generate_background_asset(
                project_name=project_name,
                location_id="scene_01",
                variant="main",
                prompt="",
            )
        )

        assert slot["description"] == "wide street and cafe"
        assert slot["description_source"] == "scene_package"
        assert "wide street and cafe" in fake_image_service.calls[0]["prompt"]

    def test_generated_background_can_use_user_description_override(self, pm, project):
        from renpy_mcp.services.stepwise_generation_service import StepwiseGenerationService

        project_name, _ = project
        _seed_scene_packages(pm, project_name)
        fake_image_service = FakeImageService(size=(1280, 720))
        service = StepwiseGenerationService(pm, image_service=fake_image_service)
        service.start_characters(project_name)
        service.start_backgrounds(project_name)

        slot = asyncio.run(
            service.generate_background_asset(
                project_name=project_name,
                location_id="scene_01",
                variant="main",
                prompt="",
                description="neon alley at night",
            )
        )

        assert slot["description"] == "neon alley at night"
        assert slot["description_source"] == "user"
        assert "neon alley at night" in fake_image_service.calls[0]["prompt"]

    def test_script_preview_does_not_write_final_game_script(self, service, project):
        project_name, project_dir = project
        script_file = project_dir / "game" / "script.rpy"
        original = script_file.read_text(encoding="utf-8")

        service.start_characters(project_name)
        alice = service.upload_character_asset(
            project_name=project_name,
            character_id="alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, alice["asset_id"])
        service.start_backgrounds(project_name)
        bg = service.upload_background_asset(
            project_name=project_name,
            location_id="rooftop",
            variant="main",
            filename="roof.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, bg["asset_id"])
        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)

        preview = service.preview_script(project_name)
        assert preview["label"] == "script_preview"
        assert "alice" in preview["script"]
        assert "script.rpy" not in preview["script"]
        assert script_file.read_text(encoding="utf-8") == original

    def test_start_characters_and_backgrounds_create_required_slots_from_scene_packages(self, service, project):
        project_name, _ = project
        _seed_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        state = service.get_state(project_name)
        assert set(state["character_assets"]) == {"char_Alice_normal", "char_Bob_normal"}
        assert state["character_assets"]["char_Alice_normal"]["status"] == "empty"
        assert state["character_assets"]["char_Bob_normal"]["status"] == "empty"
        assert state["background_assets"] == {}

        service.start_backgrounds(project_name)
        state = service.get_state(project_name)
        assert set(state["background_assets"]) == {"bg_scene_01_main"}
        assert state["background_assets"]["bg_scene_01_main"]["status"] == "empty"

    def test_upload_character_asset_updates_required_slot_metadata(self, service, project):
        project_name, _ = project
        _seed_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        assert set(service.get_state(project_name)["character_assets"]) == {"char_Alice_normal", "char_Bob_normal"}

        uploaded = service.upload_character_asset(
            project_name=project_name,
            character_id="Alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )

        state = service.get_state(project_name)
        assert uploaded["asset_id"] == "char_Alice_normal"
        assert set(state["character_assets"]) == {"char_Alice_normal", "char_Bob_normal"}
        assert state["character_assets"]["char_Alice_normal"]["status"] == "uploaded"

    def test_upload_character_asset_distinguishes_variants(self, service, project):
        project_name, _ = project
        _seed_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        normal = service.upload_character_asset(
            project_name=project_name,
            character_id="Alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        happy = service.upload_character_asset(
            project_name=project_name,
            character_id="Alice",
            variant="happy",
            filename="alice-happy.png",
            file_bytes=_rgba_png_bytes(),
        )

        state = service.get_state(project_name)
        assert normal["asset_id"] == "char_Alice_normal"
        assert happy["asset_id"] == "char_Alice_happy"
        assert set(state["character_assets"]) == {
            "char_Alice_normal",
            "char_Alice_happy",
            "char_Bob_normal",
        }
        assert state["character_assets"]["char_Alice_normal"]["variant"] == "normal"
        assert state["character_assets"]["char_Alice_happy"]["variant"] == "happy"
        assert state["character_assets"]["char_Alice_happy"]["path"] == "game/images/sprites/char_Alice_happy.png"

    def test_preview_script_rejects_multiple_accepted_variants_for_same_character(self, service, project):
        project_name, _ = project
        _seed_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        normal = service.upload_character_asset(
            project_name=project_name,
            character_id="Alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        happy = service.upload_character_asset(
            project_name=project_name,
            character_id="Alice",
            variant="happy",
            filename="alice-happy.png",
            file_bytes=_rgba_png_bytes(),
        )
        bob = service.upload_character_asset(
            project_name=project_name,
            character_id="Bob",
            variant="normal",
            filename="bob.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, normal["asset_id"])
        service.accept_asset(project_name, happy["asset_id"])
        service.accept_asset(project_name, bob["asset_id"])

        service.start_backgrounds(project_name)
        bg = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_01",
            variant="main",
            filename="scene_01.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, bg["asset_id"])

        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)

        with pytest.raises(ValueError, match="multiple variants"):
            service.preview_script(project_name)

    def test_upload_background_asset_distinguishes_variants(self, service, project):
        project_name, _ = project
        _seed_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        service.start_backgrounds(project_name)
        main_bg = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_01",
            variant="main",
            filename="bg-main.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        alt_bg = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_01",
            variant="alt",
            filename="bg-alt.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )

        state = service.get_state(project_name)
        assert main_bg["asset_id"] == "bg_scene_01_main"
        assert alt_bg["asset_id"] == "bg_scene_01_alt"
        assert set(state["background_assets"]) == {"bg_scene_01_main", "bg_scene_01_alt"}
        assert state["background_assets"]["bg_scene_01_main"]["variant"] == "main"
        assert state["background_assets"]["bg_scene_01_alt"]["variant"] == "alt"
        assert state["background_assets"]["bg_scene_01_alt"]["path"] == "game/images/background/bg_scene_01_alt.png"

    def test_preview_script_rejects_multiple_accepted_background_variants_for_same_scene(self, service, project):
        project_name, _ = project
        _seed_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        alice = service.upload_character_asset(
            project_name=project_name,
            character_id="Alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        bob = service.upload_character_asset(
            project_name=project_name,
            character_id="Bob",
            variant="normal",
            filename="bob.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, alice["asset_id"])
        service.accept_asset(project_name, bob["asset_id"])

        service.start_backgrounds(project_name)
        main = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_01",
            variant="main",
            filename="scene_01.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        alt = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_01",
            variant="alt",
            filename="scene_01_alt.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, main["asset_id"])
        service.accept_asset(project_name, alt["asset_id"])

        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)

        with pytest.raises(ValueError, match="multiple variants"):
            service.preview_script(project_name)

    def test_upload_background_asset_updates_required_slot_metadata(self, service, project):
        project_name, _ = project
        _seed_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        service.start_backgrounds(project_name)
        assert set(service.get_state(project_name)["background_assets"]) == {"bg_scene_01_main"}

        uploaded = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_01",
            variant="main",
            filename="bg.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )

        state = service.get_state(project_name)
        assert uploaded["asset_id"] == "bg_scene_01_main"
        assert set(state["background_assets"]) == {"bg_scene_01_main"}
        assert state["background_assets"]["bg_scene_01_main"]["status"] == "uploaded"

    def test_upload_background_asset_keeps_existing_description(self, service, project):
        project_name, _ = project
        _seed_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        state = service.start_backgrounds(project_name)

        assert state["background_assets"]["bg_scene_01_main"]["description"] == "wide street and cafe"
        assert state["background_assets"]["bg_scene_01_main"]["description_source"] == "scene_package"

        uploaded = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_01",
            variant="main",
            filename="bg.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )

        assert uploaded["description"] == "wide street and cafe"
        assert uploaded["description_source"] == "scene_package"

    def test_generate_background_preserves_existing_description(self, pm, project):
        from renpy_mcp.services.stepwise_generation_service import StepwiseGenerationService

        project_name, _ = project
        _seed_scene_packages(pm, project_name)
        fake_image_service = FakeImageService(size=(1280, 720))
        service = StepwiseGenerationService(pm, image_service=fake_image_service)
        service.start_characters(project_name)
        service.start_backgrounds(project_name)

        service.upload_background_asset(
            project_name=project_name,
            location_id="scene_01",
            variant="main",
            filename="bg.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )

        slot = asyncio.run(
            service.generate_background_asset(
                project_name=project_name,
                location_id="scene_01",
                variant="main",
                prompt="moonlit city background",
            )
        )

        assert slot["description"] == "wide street and cafe"
        assert slot["description_source"] == "scene_package"
        assert slot["generation_prompt"] == "moonlit city background"
        assert "wide street and cafe" in fake_image_service.calls[0]["prompt"]

    def test_generate_background_defaults_to_target_description_when_no_scene_package(self, pm, project):
        from renpy_mcp.services.stepwise_generation_service import StepwiseGenerationService

        project_name, _ = project
        fake_image_service = FakeImageService(size=(1280, 720))
        service = StepwiseGenerationService(pm, image_service=fake_image_service)
        service.start_characters(project_name)
        service.start_backgrounds(project_name)

        slot = asyncio.run(
            service.generate_background_asset(
                project_name=project_name,
                location_id="rooftop",
                variant="main",
                prompt="",
            )
        )

        assert slot["description"] == "rooftop"
        assert slot["description_source"] == "target"
        assert "rooftop" in fake_image_service.calls[0]["prompt"]

    def test_accept_asset_rejects_non_renderable_characters_by_default(self, service, project):
        project_name, _ = project
        service.start_characters(project_name)
        char = service.upload_character_asset(
            project_name=project_name,
            character_id="alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgb_png_bytes(),
        )
        assert char["renderable"] is False

        with pytest.raises(ValueError, match="renderable"):
            service.accept_asset(project_name, char["asset_id"])

    def test_accept_asset_can_override_non_renderable_character(self, service, project):
        project_name, _ = project
        service.start_characters(project_name)
        char = service.upload_character_asset(
            project_name=project_name,
            character_id="alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgb_png_bytes(),
        )
        accepted = service.accept_asset(project_name, char["asset_id"], allow_non_renderable=True)
        assert accepted["status"] == "accepted"

    def test_accept_asset_rejects_empty_slot_even_with_non_renderable_override(self, service, project):
        project_name, _ = project
        _seed_scene_packages(service.pm, project_name)
        service.start_characters(project_name)

        with pytest.raises(ValueError, match="uploaded or generated"):
            service.accept_asset(project_name, "char_Alice_normal", allow_non_renderable=True)

    def test_accept_asset_requires_real_asset_status_source_and_path(self, service, project):
        project_name, _ = project
        service.start_characters(project_name)
        char = service.upload_character_asset(
            project_name=project_name,
            character_id="alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        state = service.get_state(project_name)
        state["character_assets"][char["asset_id"]]["status"] = "generated"
        state["character_assets"][char["asset_id"]]["source"] = "bad-source"
        state["character_assets"][char["asset_id"]]["path"] = None
        state["character_assets"][char["asset_id"]]["staging_path"] = None
        service.save_state(project_name, state)

        with pytest.raises(ValueError, match="source"):
            service.accept_asset(project_name, char["asset_id"])

        state = service.get_state(project_name)
        state["character_assets"][char["asset_id"]]["source"] = "generated"
        state["character_assets"][char["asset_id"]]["status"] = "generated"
        state["character_assets"][char["asset_id"]]["path"] = None
        state["character_assets"][char["asset_id"]]["staging_path"] = None
        service.save_state(project_name, state)

        with pytest.raises(ValueError, match="path"):
            service.accept_asset(project_name, char["asset_id"])

    def test_commit_requires_script_preview_state(self, service, project):
        project_name, _ = project
        service.start_characters(project_name)
        char = service.upload_character_asset(
            project_name=project_name,
            character_id="alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, char["asset_id"])

        service.start_backgrounds(project_name)
        bg = service.upload_background_asset(
            project_name=project_name,
            location_id="rooftop",
            variant="main",
            filename="roof.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, bg["asset_id"])
        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)

        with pytest.raises(ValueError, match="script preview"):
            service.commit(project_name)

        state = service.get_state(project_name)
        assert state["state"] != "committed"

    def test_commit_requires_non_empty_script_preview_payload(self, service, project):
        project_name, _ = project
        state = service.get_state(project_name)
        state["state"] = "script_preview"
        state["script_preview"] = {}
        state["round_id"] = "r0001"
        service.save_state(project_name, state)

        with pytest.raises(ValueError, match="preview script"):
            service.commit(project_name)

    def test_confirm_actions_are_not_allowed_after_script_preview(self, service, project):
        project_name, _ = project
        service.start_characters(project_name)
        char = service.upload_character_asset(
            project_name=project_name,
            character_id="alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, char["asset_id"])

        service.start_backgrounds(project_name)
        bg = service.upload_background_asset(
            project_name=project_name,
            location_id="rooftop",
            variant="main",
            filename="roof.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, bg["asset_id"])
        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)
        service.preview_script(project_name)

        with pytest.raises(ValueError, match="Cannot confirm characters"):
            service.confirm_characters(project_name)

        with pytest.raises(ValueError, match="Cannot confirm backgrounds"):
            service.confirm_backgrounds(project_name)

    def test_confirm_and_commit_block_until_required_slots_are_accepted(self, service, project):
        project_name, project_dir = project
        _seed_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        state = service.get_state(project_name)
        assert state["character_assets"]["char_Alice_normal"]["status"] == "empty"
        assert state["character_assets"]["char_Bob_normal"]["status"] == "empty"
        assert state["background_assets"] == {}

        with pytest.raises(ValueError, match="must be accepted"):
            service.confirm_characters(project_name)

        alice = service.upload_character_asset(
            project_name=project_name,
            character_id="Alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, alice["asset_id"])
        service.start_backgrounds(project_name)

        with pytest.raises(ValueError, match="must be accepted"):
            service.confirm_backgrounds(project_name)

        bob = service.upload_character_asset(
            project_name=project_name,
            character_id="Bob",
            variant="normal",
            filename="bob.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, bob["asset_id"])

        bg = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_01",
            variant="main",
            filename="roof.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, bg["asset_id"])

        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)
        (project_dir / "game" / "script.rpy").write_text(
            "Hello from the Ren'Py MCP server!\\n",
            encoding="utf-8",
        )
        preview = service.preview_script(project_name)
        assert "staging_path" in preview

        result = service.commit(project_name)
        assert result["state"] == "committed"

        assert service.get_state(project_name)["state"] == "committed"
        for slot in (alice, bob, bg):
            assert (project_dir / slot["path"]).exists()

    def test_commit_promotes_accepted_staging_files(self, service, project):
        project_name, project_dir = project
        service.start_characters(project_name)
        alice = service.upload_character_asset(
            project_name=project_name,
            character_id="alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, alice["asset_id"])

        service.start_backgrounds(project_name)
        bg = service.upload_background_asset(
            project_name=project_name,
            location_id="rooftop",
            variant="main",
            filename="roof.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, bg["asset_id"])
        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)

        (project_dir / "game" / "script.rpy").write_text(
            "Hello from the Ren'Py MCP server!\\n",
            encoding="utf-8",
        )
        service.preview_script(project_name)

        result = service.commit(project_name)
        assert result["state"] == "committed"

        state = service.get_state(project_name)
        assert state["state"] == "committed"
        for slot in (alice, bg):
            final_path = project_dir / slot["path"]
            assert final_path.exists()
            assert final_path.is_file()
            final_bytes = final_path.read_bytes()
            assert final_bytes

        script_file = project_dir / "game" / "script.rpy"
        wired = script_file.read_text(encoding="utf-8")
        assert "# PROTOTYPE START (managed)" in wired
        assert "call" in wired

        index = json.loads((project_dir / "meta" / "index.json").read_text(encoding="utf-8"))
        assert "scenes" in index
        assert "stepwise" not in index

        manifest = service.pm.read_prototype_manifest(project_name)
        assert manifest is not None
        assert manifest.mode is None or manifest.mode == "single_chapter"
        assert not (project_dir / "meta" / "manifest.json").exists()

    def test_preview_and_commit_supports_multiple_chapters(self, service, project):
        project_name, project_dir = project
        _seed_two_chapter_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        alice = service.upload_character_asset(
            project_name=project_name,
            character_id="Alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        bob = service.upload_character_asset(
            project_name=project_name,
            character_id="Bob",
            variant="normal",
            filename="bob.png",
            file_bytes=_rgba_png_bytes(),
        )
        carol = service.upload_character_asset(
            project_name=project_name,
            character_id="Carol",
            variant="normal",
            filename="carol.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, alice["asset_id"])
        service.accept_asset(project_name, bob["asset_id"])
        service.accept_asset(project_name, carol["asset_id"])

        service.start_backgrounds(project_name)
        scene_01_bg = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_01",
            variant="main",
            filename="scene_01.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        scene_02_bg = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_02",
            variant="main",
            filename="scene_02.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, scene_01_bg["asset_id"])
        service.accept_asset(project_name, scene_02_bg["asset_id"])

        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)

        (project_dir / "game" / "script.rpy").write_text(
            "label start:\\n    \"Hello from the Ren'Py MCP server!\"\\n",
            encoding="utf-8",
        )

        preview = service.preview_script(project_name)
        assert preview["label"] == "script_preview"
        assert preview.get("staging_paths") is not None
        assert len(preview["staging_paths"]) == 2
        assert len(preview["script_files"]) == 2
        assert preview["staging_paths"][0] != preview["staging_paths"][1]

        result = service.commit(project_name)
        assert result["state"] == "committed"

        manifest = service.pm.read_prototype_manifest(project_name)
        assert manifest is not None
        assert manifest.mode == "multi_chapter"
        assert len(manifest.script_files) == 2
        assert manifest.script_files[0] != manifest.script_files[1]
        for script_path in manifest.script_files:
            assert (project_dir / script_path).exists()

        index = json.loads((project_dir / "meta" / "index.json").read_text(encoding="utf-8"))
        assert "scene_01" in index["scenes"]
        assert "scene_02" in index["scenes"]

    def test_commit_multi_chapter_removes_stale_prototype_index_scenes(self, service, project):
        project_name, project_dir = project
        _seed_two_chapter_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        alice = service.upload_character_asset(
            project_name=project_name,
            character_id="Alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        bob = service.upload_character_asset(
            project_name=project_name,
            character_id="Bob",
            variant="normal",
            filename="bob.png",
            file_bytes=_rgba_png_bytes(),
        )
        carol = service.upload_character_asset(
            project_name=project_name,
            character_id="Carol",
            variant="normal",
            filename="carol.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, alice["asset_id"])
        service.accept_asset(project_name, bob["asset_id"])
        service.accept_asset(project_name, carol["asset_id"])

        service.start_backgrounds(project_name)
        scene_01_bg = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_01",
            variant="main",
            filename="scene_01.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        scene_02_bg = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_02",
            variant="main",
            filename="scene_02.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, scene_01_bg["asset_id"])
        service.accept_asset(project_name, scene_02_bg["asset_id"])
        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)

        (project_dir / "game" / "script.rpy").write_text(
            "label start:\\n    \"Hello from the Ren'Py MCP server!\"\\n",
            encoding="utf-8",
        )

        legacy_index = {
            "scenes": {
                "old_scene": {
                    "source": "prototype",
                    "scene_id": "old_scene",
                    "title": "Old Scene",
                    "chapter_id": "legacy",
                    "file_path": "game/prototype_old.rpy",
                    "label": "prototype_legacy_start",
                },
                "chapterless_note": {
                    "source": "note",
                    "note": "keep this unrelated entry",
                },
            }
        }
        (project_dir / "meta" / "index.json").write_text(
            json.dumps(legacy_index, ensure_ascii=False),
            encoding="utf-8",
        )

        service.preview_script(project_name)
        service.commit(project_name)

        index = json.loads((project_dir / "meta" / "index.json").read_text(encoding="utf-8"))
        assert "old_scene" not in index["scenes"]
        assert "scene_01" in index["scenes"]
        assert "scene_02" in index["scenes"]
        assert index["scenes"]["scene_01"]["source"] == "prototype"
        assert index["scenes"]["scene_02"]["source"] == "prototype"
        assert index["scenes"]["chapterless_note"] == legacy_index["scenes"]["chapterless_note"]

    def test_multi_chapter_commit_rolls_back_stale_prototype_files_on_manifest_failure(self, service, project, monkeypatch):
        project_name, project_dir = project
        _seed_two_chapter_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        alice = service.upload_character_asset(
            project_name=project_name,
            character_id="Alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        bob = service.upload_character_asset(
            project_name=project_name,
            character_id="Bob",
            variant="normal",
            filename="bob.png",
            file_bytes=_rgba_png_bytes(),
        )
        carol = service.upload_character_asset(
            project_name=project_name,
            character_id="Carol",
            variant="normal",
            filename="carol.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, alice["asset_id"])
        service.accept_asset(project_name, bob["asset_id"])
        service.accept_asset(project_name, carol["asset_id"])

        service.start_backgrounds(project_name)
        scene_01_bg = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_01",
            variant="main",
            filename="scene_01.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        scene_02_bg = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_02",
            variant="main",
            filename="scene_02.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, scene_01_bg["asset_id"])
        service.accept_asset(project_name, scene_02_bg["asset_id"])
        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)

        (project_dir / "game" / "script.rpy").write_text(
            "label start:\\n    \"Hello from the Ren'Py MCP server!\"\\n",
            encoding="utf-8",
        )
        legacy_script = "legacy prototype"
        legacy_script_path = project_dir / "game" / "prototype_old.rpy"
        legacy_script_path.write_text(legacy_script, encoding="utf-8")

        legacy_index = {
            "scenes": {
                "old_scene": {
                    "source": "prototype",
                    "scene_id": "old_scene",
                    "title": "Old Scene",
                    "chapter_id": "legacy",
                    "file_path": "game/prototype_old.rpy",
                    "label": "prototype_legacy_start",
                }
            }
        }
        (project_dir / "meta" / "index.json").write_text(
            json.dumps(legacy_index, ensure_ascii=False),
            encoding="utf-8",
        )
        old_index_text = (project_dir / "meta" / "index.json").read_text(encoding="utf-8")
        old_script_text = (project_dir / "game" / "prototype_old.rpy").read_text(encoding="utf-8")

        from renpy_mcp.blueprint.models import PrototypeManifest

        old_manifest = PrototypeManifest(
            mode="single_chapter",
            entry_label="legacy_entry",
            entry_file="game/prototype_old.rpy",
            chapter_ids=["legacy"],
            script_files=["game/prototype_old.rpy"],
            updated_at="legacy",
        )
        service.pm.write_prototype_manifest(project_name, old_manifest)
        old_manifest_text = (project_dir / "meta" / "prototype_manifest.json").read_text(encoding="utf-8")

        monkeypatch.setattr(
            service.pm,
            "write_prototype_manifest",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("simulated manifest write failure"),
            ),
        )

        preview = service.preview_script(project_name)
        new_script_files = list(preview["script_files"])
        were_missing_before = {
            script_file: not (project_dir / script_file).exists()
            for script_file in new_script_files
        }

        with pytest.raises(RuntimeError, match="simulated manifest write failure"):
            service.commit(project_name)

        assert legacy_script_path.exists()
        assert legacy_script_path.read_text(encoding="utf-8") == old_script_text
        assert (project_dir / "meta" / "index.json").read_text(encoding="utf-8") == old_index_text
        assert (project_dir / "meta" / "prototype_manifest.json").read_text(encoding="utf-8") == old_manifest_text
        for script_file in new_script_files:
            if were_missing_before[script_file]:
                assert not (project_dir / script_file).exists()
        assert service.get_state(project_name)["state"] == "failed"

    def test_commit_rolls_back_final_script_when_failure_occurs_after_promotion(
        self, service, project, monkeypatch
    ):
        project_name, project_dir = project
        service.start_characters(project_name)
        alice = service.upload_character_asset(
            project_name=project_name,
            character_id="alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, alice["asset_id"])
        service.start_backgrounds(project_name)
        bg = service.upload_background_asset(
            project_name=project_name,
            location_id="rooftop",
            variant="main",
            filename="roof.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, bg["asset_id"])
        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)

        old_stepwise_script = "legacy-stepwise-prototype\\n"
        (project_dir / "game" / "script.rpy").write_text(
            "label start:\\n    \"Hello from the Ren'Py MCP server!\"\\n",
            encoding="utf-8",
        )
        preview = service.preview_script(project_name)
        old_script_path = project_dir / preview["script_files"][0]
        old_script_path.write_text(old_stepwise_script, encoding="utf-8")

        old_manifest = (
            (project_dir / "meta" / "prototype_manifest.json").read_text(encoding="utf-8")
            if (project_dir / "meta" / "prototype_manifest.json").exists()
            else None
        )
        old_index = (
            (project_dir / "meta" / "index.json").read_text(encoding="utf-8")
            if (project_dir / "meta" / "index.json").exists()
            else None
        )

        original_commit = service._prototype_activation.commit_prototype_replacement

        def failing_commit(*args, **kwargs):
            original_commit(*args, **kwargs)
            raise RuntimeError("simulated replacement failure after promotion")

        monkeypatch.setattr(
            service._prototype_activation,
            "commit_prototype_replacement",
            failing_commit,
        )

        with pytest.raises(RuntimeError, match="simulated replacement failure after promotion"):
            service.commit(project_name)

        assert (project_dir / "game" / "script.rpy").read_text(
            encoding="utf-8"
        ) == "label start:\\n    \"Hello from the Ren'Py MCP server!\"\\n"
        assert old_script_path.read_text(
            encoding="utf-8"
        ) == old_stepwise_script
        if old_index is None:
            assert not (project_dir / "meta" / "index.json").exists()
        else:
            assert (project_dir / "meta" / "index.json").read_text(encoding="utf-8") == old_index
        if old_manifest is None:
            assert not (project_dir / "meta" / "prototype_manifest.json").exists()
        else:
            assert (project_dir / "meta" / "prototype_manifest.json").read_text(
                encoding="utf-8"
            ) == old_manifest
        assert service.get_state(project_name)["state"] == "failed"

    def test_failed_commit_does_not_promote_unaccepted_same_round_uploads(self, service, project, monkeypatch):
        project_name, project_dir = project
        _seed_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        alice = service.upload_character_asset(
            project_name=project_name,
            character_id="Alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        bob = service.upload_character_asset(
            project_name=project_name,
            character_id="Bob",
            variant="normal",
            filename="bob.png",
            file_bytes=_rgba_png_bytes(),
        )
        unaccepted = service.upload_character_asset(
            project_name=project_name,
            character_id="dave",
            variant="happy",
            filename="dave.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, alice["asset_id"])
        service.accept_asset(project_name, bob["asset_id"])

        service.start_backgrounds(project_name)
        bg = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_01",
            variant="main",
            filename="roof.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, bg["asset_id"])
        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)
        (project_dir / "game" / "script.rpy").write_text(
            "label start:\n    \"Hello from the Ren'Py MCP server!\"\n",
            encoding="utf-8",
        )
        service.preview_script(project_name)
        assert (project_dir / alice["staging_path"]).exists()
        assert (project_dir / bg["staging_path"]).exists()

        monkeypatch.setattr(
            service.pm,
            "write_prototype_manifest",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("simulated manifest write failure")),
        )

        with pytest.raises(RuntimeError, match="simulated manifest write failure"):
            service.commit(project_name)

        assert not (project_dir / unaccepted["path"]).exists()
        assert (project_dir / alice["staging_path"]).exists()
        assert (project_dir / bg["staging_path"]).exists()

    def test_failed_state_save_after_commit_keeps_accepted_staging_assets(self, service, project, monkeypatch):
        project_name, project_dir = project
        _seed_scene_packages(service.pm, project_name)

        service.start_characters(project_name)
        alice = service.upload_character_asset(
            project_name=project_name,
            character_id="Alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        bob = service.upload_character_asset(
            project_name=project_name,
            character_id="Bob",
            variant="normal",
            filename="bob.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, alice["asset_id"])
        service.accept_asset(project_name, bob["asset_id"])

        service.start_backgrounds(project_name)
        bg = service.upload_background_asset(
            project_name=project_name,
            location_id="scene_01",
            variant="main",
            filename="roof.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, bg["asset_id"])
        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)
        (project_dir / "game" / "script.rpy").write_text(
            "label start:\n    \"Hello from the Ren'Py MCP server!\"\n",
            encoding="utf-8",
        )
        service.preview_script(project_name)

        original_save_state = service.save_state

        def fail_committed_save(name, state):
            if state.get("state") == "committed":
                raise RuntimeError("simulated committed state save failure")
            original_save_state(name, state)

        monkeypatch.setattr(service, "save_state", fail_committed_save)

        with pytest.raises(RuntimeError, match="simulated committed state save failure"):
            service.commit(project_name)

        assert (project_dir / alice["staging_path"]).exists()
        assert (project_dir / bg["staging_path"]).exists()

    def test_commit_rejects_unrecognized_runtime_script_and_rolls_back(self, service, project):
        project_name, project_dir = project
        service.start_characters(project_name)
        alice = service.upload_character_asset(
            project_name=project_name,
            character_id="alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, alice["asset_id"])
        service.start_backgrounds(project_name)
        bg = service.upload_background_asset(
            project_name=project_name,
            location_id="rooftop",
            variant="main",
            filename="roof.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, bg["asset_id"])
        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)
        service.preview_script(project_name)

        original = (project_dir / "game" / "script.rpy").read_text(encoding="utf-8")
        with pytest.raises(RuntimeError, match="Cannot safely wire prototype"):
            service.commit(project_name)

        assert (project_dir / "game" / "script.rpy").read_text(encoding="utf-8") == original
        assert service.get_state(project_name)["state"] != "committed"
        assert not (project_dir / "meta" / "prototype_manifest.json").exists()

    def test_commit_rolls_back_when_commit_prototype_replacement_fails(self, service, project, monkeypatch):
        project_name, project_dir = project
        service.start_characters(project_name)
        alice = service.upload_character_asset(
            project_name=project_name,
            character_id="alice",
            variant="normal",
            filename="alice.png",
            file_bytes=_rgba_png_bytes(),
        )
        service.accept_asset(project_name, alice["asset_id"])
        service.start_backgrounds(project_name)
        bg = service.upload_background_asset(
            project_name=project_name,
            location_id="rooftop",
            variant="main",
            filename="roof.png",
            file_bytes=_rgba_png_bytes(size=(1280, 720)),
        )
        service.accept_asset(project_name, bg["asset_id"])
        service.confirm_characters(project_name)
        service.confirm_backgrounds(project_name)

        from renpy_mcp.blueprint.models import PrototypeManifest

        (project_dir / "game" / "script.rpy").write_text(
            "Hello from the Ren'Py MCP server!\\n",
            encoding="utf-8",
        )
        (project_dir / "meta" / "index.json").write_text(
            "{\"scenes\": {\"old\": {\"source\": \"prototype\", \"title\": \"old\"}}}",
            encoding="utf-8",
        )
        service.pm.write_prototype_manifest(
            project_name,
            PrototypeManifest(
                mode="single_chapter",
                entry_label="legacy_entry",
                entry_file="game/legacy.rpy",
                chapter_ids=["ch_old"],
                script_files=["game/legacy.rpy"],
                updated_at="legacy",
            ),
        )

        alice_final = project_dir / alice["path"]
        bg_final = project_dir / bg["path"]
        alice_final.parent.mkdir(parents=True, exist_ok=True)
        bg_final.parent.mkdir(parents=True, exist_ok=True)
        alice_final.write_text("legacy-alice", encoding="utf-8")
        bg_final.write_text("legacy-bg", encoding="utf-8")

        service.preview_script(project_name)

        old_manifest = (project_dir / "meta" / "prototype_manifest.json").read_text(encoding="utf-8")
        old_index = (project_dir / "meta" / "index.json").read_text(encoding="utf-8")
        old_script = (project_dir / "game" / "script.rpy").read_text(encoding="utf-8")

        monkeypatch.setattr(
            service._prototype_activation,
            "commit_prototype_replacement",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("simulated replacement failure"),
            ),
        )

        with pytest.raises(RuntimeError, match="simulated replacement failure"):
            service.commit(project_name)

        assert alice_final.read_text(encoding="utf-8") == "legacy-alice"
        assert bg_final.read_text(encoding="utf-8") == "legacy-bg"
        assert (project_dir / "game" / "script.rpy").read_text(encoding="utf-8") == old_script
        assert (project_dir / "meta" / "index.json").read_text(encoding="utf-8") == old_index
        assert (project_dir / "meta" / "prototype_manifest.json").read_text(encoding="utf-8") == old_manifest
        assert service.get_state(project_name)["state"] == "failed"
