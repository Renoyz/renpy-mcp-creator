from __future__ import annotations

import json
from pathlib import Path

import pytest

from renpy_mcp.blueprint.models import (
    ProjectBlueprint,
    ProjectMeta,
    ProjectStatus,
    ScenePackageChapter,
    ScenePackageScene,
    ScenePackagesSnapshot,
)
from renpy_mcp.config import Settings
from renpy_mcp.services.project_manager import ProjectManager


@pytest.fixture()
def pm(tmp_path: Path) -> ProjectManager:
    settings = Settings().model_copy(update={"workspace": tmp_path / "workspace"})
    return ProjectManager(settings)


def _make_project(pm: ProjectManager, project_name: str) -> Path:
    project_dir = pm.ensure_project_dir(project_name)
    pm._init_project_meta(project_dir)
    (project_dir / "game").mkdir(exist_ok=True)
    return project_dir


def test_derive_shell_config_uses_blueprint_assets_and_default_credits(pm: ProjectManager):
    from renpy_mcp.services.game_shell_render_service import GameShellRenderService

    project_name = "demo"
    project_dir = _make_project(pm, project_name)
    pm.write_project_meta(
        project_name,
        ProjectMeta(name=project_name, path=project_dir, status=ProjectStatus.DRAFT),
    )
    pm.write_blueprint(
        project_name,
        ProjectBlueprint(title="雨夜重启", genre="悬疑", worldview="雨城"),
    )
    pm.write_scene_packages(
        project_name,
        ScenePackagesSnapshot(
            chapters=[
                ScenePackageChapter(
                    chapter_id="ch1",
                    chapter_name="第一章",
                    chapter_order=1,
                    scenes=[
                        ScenePackageScene(
                            scene_id="s1",
                            title="屋顶终局",
                            summary="最后一场雨",
                            location="屋顶",
                            scene_order=1,
                        )
                    ],
                )
            ]
        ),
    )
    generation_state = {
        "character_assets": {
            "char_lin_normal": {
                "asset_id": "char_lin_normal",
                "target": "林侦",
                "kind": "character_sprite",
                "status": "accepted",
                "path": "game/images/sprites/lin.png",
            }
        },
        "background_assets": {
            "bg_rooftop_main": {
                "asset_id": "bg_rooftop_main",
                "target": "屋顶",
                "kind": "background",
                "status": "accepted",
                "path": "game/images/backgrounds/rooftop.png",
            }
        },
    }
    state_path = project_dir / "meta" / "generation_state.json"
    state_path.write_text(json.dumps(generation_state, ensure_ascii=False), encoding="utf-8")

    config = GameShellRenderService(pm).derive_config(project_name)

    assert config.title == "雨夜重启"
    assert [item.title for item in config.gallery_items] == ["林侦", "屋顶"]
    assert {item.image_path for item in config.gallery_items} == {
        "game/images/sprites/lin.png",
        "game/images/backgrounds/rooftop.png",
    }
    assert config.ending_items[0].title == "屋顶终局"
    assert "Created with RenPy MCP Creator" in config.credits


def test_render_preview_writes_additive_files_and_no_absolute_paths(pm: ProjectManager):
    from renpy_mcp.blueprint.models import GameShellConfig, GameShellGalleryItem
    from renpy_mcp.services.game_shell_render_service import GameShellRenderService

    project_name = "demo"
    _make_project(pm, project_name)
    config = GameShellConfig(
        title="Demo VN",
        subtitle="Prototype shell",
        gallery_items=[
            GameShellGalleryItem(
                id="bg_1",
                title="Rooftop",
                image_path="game/images/backgrounds/rooftop.png",
                source="background",
            )
        ],
        credits=["Writer: AI", "Editor: User"],
    )

    preview = GameShellRenderService(pm).render_preview(project_name, config)

    assert preview.gallery_count == 1
    assert set(preview.script_files) == {
        "game/__staging__/shell/zz_generated_shell.rpy",
        "game/__staging__/shell/zz_generated_gallery.rpy",
        "game/__staging__/shell/zz_generated_endings.rpy",
        "game/__staging__/shell/zz_generated_credits.rpy",
    }
    for rel_path in preview.script_files:
        assert not Path(rel_path).is_absolute()
        assert (pm._project_dir(project_name) / rel_path).exists()
    assert "screen mcp_extras" in preview.preview
    assert "Rooftop" in preview.preview


def test_gallery_image_add_uses_valid_renpy_syntax(pm: ProjectManager):
    """Ren'Py rejects `add "..." xmaximum N` — the gallery must fit via im.Fit.

    Evidence: a real SDK build of a generated project failed on
    zz_generated_gallery.rpy with "'xmaximum' is not a keyword argument or
    valid child of the add statement" (2026-07-19).
    """
    from renpy_mcp.blueprint.models import GameShellConfig, GameShellGalleryItem
    from renpy_mcp.services.game_shell_render_service import GameShellRenderService

    project_name = "demo"
    _make_project(pm, project_name)
    config = GameShellConfig(
        title="Demo VN",
        gallery_items=[
            GameShellGalleryItem(
                id="bg_1",
                title="Rooftop",
                image_path="game/images/backgrounds/rooftop.png",
                source="background",
            )
        ],
    )

    GameShellRenderService(pm).render_preview(project_name, config)

    gallery_text = (
        pm._project_dir(project_name) / "game/__staging__/shell/zz_generated_gallery.rpy"
    ).read_text(encoding="utf-8")
    assert "xmaximum" not in gallery_text
    assert 'im.Fit("game/images/backgrounds/rooftop.png", 640, 360, "contain")' in gallery_text


def test_validate_shell_rejects_absolute_and_traversal_paths(pm: ProjectManager, tmp_path: Path):
    from pydantic import ValidationError
    from renpy_mcp.blueprint.models import GameShellConfig, GameShellGalleryItem
    from renpy_mcp.services.game_shell_render_service import GameShellRenderService

    service = GameShellRenderService(pm)

    with pytest.raises(ValidationError):
        service.validate_config(
            GameShellConfig(
                title="bad",
                main_menu_background=str(tmp_path / "secret.png"),
            )
        )

    with pytest.raises(ValidationError):
        service.validate_config(
            GameShellConfig(
                title="bad",
                gallery_items=[
                    GameShellGalleryItem(
                        id="bad",
                        title="bad",
                        image_path="../outside.png",
                    )
                ],
            )
        )
