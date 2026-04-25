"""Structural tests for the P2-2 router split of create_app().

Verifies that:
1. Each router module exists and exports an APIRouter
2. The assembled app contains all expected routes
3. Domain logic is importable from services.refinement_logic
4. fastapi_app.py is significantly slimmer
"""

import importlib
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Router modules exist and export APIRouter
# ---------------------------------------------------------------------------

ROUTER_MODULES = [
    "renpy_mcp.web.routers.pages",
    "renpy_mcp.web.routers.projects",
    "renpy_mcp.web.routers.refinement",
    "renpy_mcp.web.routers.generation",
    "renpy_mcp.web.routers.preview_build",
    "renpy_mcp.web.routers.scripts_assets",
]


@pytest.mark.parametrize("module_name", ROUTER_MODULES)
def test_router_module_importable(module_name: str):
    mod = importlib.import_module(module_name)
    assert hasattr(mod, "router"), f"{module_name} must export 'router'"


@pytest.mark.parametrize("module_name", ROUTER_MODULES)
def test_router_has_routes(module_name: str):
    from fastapi.routing import APIRouter

    mod = importlib.import_module(module_name)
    r = getattr(mod, "router")
    assert isinstance(r, APIRouter), f"{module_name}.router must be an APIRouter"
    assert len(r.routes) > 0, f"{module_name}.router must have at least one route"


# ---------------------------------------------------------------------------
# Domain logic importable from services
# ---------------------------------------------------------------------------

def test_refinement_logic_importable():
    from renpy_mcp.services import refinement_logic  # noqa: F401

    expected_names = [
        "compute_refinement_state",
        "compute_blueprint_freeze_status",
        "is_brief_fully_confirmed",
        "is_outline_fully_confirmed",
        "is_character_identity_card_valid",
        "freeze_status_after_upstream_change",
        "brief_card_text",
        "intake_slot_content",
        "materialize_brief_from_intake",
        "materialize_outline_from_intake",
        "assemble_frozen_blueprint",
        "build_chapter_intake_entries_from_blueprint",
    ]
    for name in expected_names:
        assert hasattr(refinement_logic, name), f"refinement_logic must export '{name}'"


# ---------------------------------------------------------------------------
# Assembled app has all expected route paths
# ---------------------------------------------------------------------------

EXPECTED_PATHS = [
    # Pages
    "/",
    "/dashboard",
    "/story-map",
    "/script-editor",
    "/heatmap",
    "/assets",
    # Projects
    "/api/projects",
    "/api/projects/current",
    "/api/projects/select",
    "/api/projects/{project_name}/meta",
    "/api/projects/{project_name}/blueprint",
    # Refinement
    "/api/projects/{project_name}/refinement-intake",
    "/api/projects/{project_name}/brief",
    "/api/projects/{project_name}/brief/promote-draft",
    "/api/projects/{project_name}/brief/confirm-card",
    "/api/projects/{project_name}/chapter-outline",
    "/api/projects/{project_name}/chapter-outline/promote-draft",
    "/api/projects/{project_name}/chapter-outline/confirm-chapter",
    "/api/projects/{project_name}/blueprint/freeze",
    "/api/projects/{project_name}/refinement-status",
    # Generation
    "/api/projects/{project_name}/scene-packages/generate",
    "/api/projects/{project_name}/prototype/multi-chapter/generate",
    "/api/projects/{project_name}/scenes",
    "/api/projects/{project_name}/storymap",
    "/api/projects/{project_name}/scenes/{scene_id}/script",
    "/api/projects/{project_name}/prototype/multi-chapter/activate",
    "/api/projects/{project_name}/prototype/status",
    "/api/projects/{project_name}/prototype/pipeline-status",
    # Preview / Build
    "/api/projects/{project_name}/prototype/build",
    "/api/projects/build",
    "/api/projects/{project_name}/build",
    "/api/projects/build/status",
    "/api/projects/preview",
    "/api/projects/preview/stop",
    "/api/projects/preview/status",
    "/api/projects/{project_name}/build/status",
    "/api/projects/{project_name}/preview",
    "/api/projects/{project_name}/preview/status",
    # Scripts / Assets
    "/api/graph",
    "/api/status",
    "/api/labels",
    "/api/script/files",
    "/api/script/parse",
    "/api/characters",
    "/api/script/save",
    "/api/assets",
    "/api/asset-usage",
    "/api/projects/{project_name}/asset-file/{file_path:path}",
    # Chat / Session
    "/api/projects/{project_name}/chat/history",
    "/api/projects/{project_name}/blueprint-session",
]


def test_all_routes_present():
    from renpy_mcp.web.fastapi_app import create_app

    app = create_app()
    registered = {route.path for route in app.routes if hasattr(route, "path")}
    for path in EXPECTED_PATHS:
        assert path in registered, f"Route '{path}' not found in assembled app"


# ---------------------------------------------------------------------------
# fastapi_app.py is slimmer than before
# ---------------------------------------------------------------------------

def test_fastapi_app_line_count_reduced():
    """create_app() should be drastically smaller after the split."""
    src = Path(__file__).resolve().parent.parent.parent / "src" / "renpy_mcp" / "web" / "fastapi_app.py"
    lines = src.read_text(encoding="utf-8").splitlines()
    # Before: ~2785 lines.  After: should be under 350 lines.
    assert len(lines) < 400, (
        f"fastapi_app.py still has {len(lines)} lines; "
        f"expected <400 after router extraction"
    )
