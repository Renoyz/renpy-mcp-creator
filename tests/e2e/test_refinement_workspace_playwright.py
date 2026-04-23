"""Playwright E2E coverage for the Phase 7 Round 2 refinement workspace."""

import json
import re
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page, expect


def wait_for_server(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{url}/api/status", timeout=2.0).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def create_project_via_api(server_url: str, project_name: str) -> None:
    response = httpx.post(
        f"{server_url}/api/projects",
        json={"name": project_name},
        timeout=10.0,
    )
    assert response.status_code == 200, response.text


def open_workspace_from_project_list(page: Page, server_url: str, project_name: str) -> None:
    page.goto(f"{server_url}/dashboard")
    project_card = page.locator("[data-testid='project-card']", has_text=project_name)
    expect(project_card).to_be_visible(timeout=10000)
    project_card.click()
    expect(page.locator("h1")).to_have_text(project_name, timeout=10000)


def _seed_project_brief(workspace: Path, project_name: str) -> None:
    meta_dir = workspace / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    brief = {
        "cards": {
            "core_premise": {"content": "A story about discovery.", "confirmed": False},
            "audience_genre": {"content": "Sci-fi, teens.", "confirmed": False},
            "tone_themes": {"content": "Hopeful, exploration.", "confirmed": False},
            "visual_style": {"content": "Cel-shaded, neon.", "confirmed": False},
            "world_rules": {"content": "Faster-than-light travel exists.", "confirmed": False},
            "core_cast": {"content": "Elena, Marcus, AI companion.", "confirmed": False},
            "character_identity": {
                "content": {
                    "characters": [
                        {
                            "character_id": "elena",
                            "name": "Elena",
                            "story_role": "Protagonist",
                            "core_motivation": "Find her lost brother",
                            "personality_anchors": ["curious", "stubborn"],
                            "visual_identity_anchors": ["blue hair", "lab coat"],
                            "forbidden_drift": ["do not make her cruel"],
                        }
                    ],
                },
                "confirmed": False,
            },
            "relationship_baselines": {
                "content": {
                    "relationships": [
                        {"pair": ["elena", "marcus"], "baseline": "Friends", "must_preserve": ["trust"]}
                    ],
                },
                "confirmed": False,
            },
            "constraints": {"content": "No time travel paradoxes.", "confirmed": False},
        },
        "updated_at": "",
    }
    (meta_dir / "project_brief.json").write_text(json.dumps(brief), encoding="utf-8")


def _seed_project_chapter_outline(workspace: Path, project_name: str) -> None:
    meta_dir = workspace / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    outline = {
        "chapters": [
            {
                "chapter_id": "ch1",
                "order": 1,
                "chapter_name": "The Beginning",
                "chapter_goal": "Introduce the world",
                "key_conflict": "Elena loses her brother",
                "emotional_arc": "Hope to despair",
                "reveals": "The brother is missing",
                "end_state": "Elena decides to search",
                "mood_or_pacing_bias": "Slow, contemplative",
                "character_focus": ["elena"],
                "relationship_shift": "None yet",
                "character_presentation_notes": "Elena is curious and determined",
                "confirmed": False,
            },
            {
                "chapter_id": "ch2",
                "order": 2,
                "chapter_name": "The Search",
                "chapter_goal": "Follow clues",
                "key_conflict": "Marcus disagrees with the plan",
                "emotional_arc": "Despair to determination",
                "reveals": "A hidden facility exists",
                "end_state": "They find coordinates",
                "mood_or_pacing_bias": "Fast, tense",
                "character_focus": ["elena", "marcus"],
                "relationship_shift": "Marcus commits to helping",
                "character_presentation_notes": "Marcus shows loyalty",
                "confirmed": False,
            },
        ],
        "updated_at": "",
    }
    (meta_dir / "chapter_outline.json").write_text(json.dumps(outline), encoding="utf-8")


def _seed_refinement_intake(
    workspace: Path,
    project_name: str,
    *,
    brief_draft_ready: bool = False,
    phase: str = "project",
) -> None:
    meta_dir = workspace / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    intake = {
        "phase": phase,
        "current_summary": "A YA sci-fi mystery about Elena searching for her missing brother.",
        "missing_slots": ["relationship_baselines", "constraints"],
        "slots": {
            "core_premise": {
                "value": "A YA sci-fi mystery about Elena searching for her missing brother.",
                "complete": True,
            },
            "audience_genre": {"value": "YA sci-fi mystery", "complete": True},
            "tone_themes": {"value": "Hope, grief, discovery", "complete": True},
            "visual_style": {"value": "Cel-shaded anime with cool neon lighting", "complete": True},
            "world_rules": {"value": "FTL travel is regulated by the state", "complete": True},
            "core_cast": {"value": "Elena, Marcus, station AI", "complete": True},
            "character_identity": {
                "value": {
                    "characters": [
                        {
                            "character_id": "elena",
                            "name": "Elena",
                            "story_role": "Protagonist",
                            "core_motivation": "Find her brother",
                            "personality_anchors": ["curious", "stubborn"],
                            "visual_identity_anchors": ["blue hair", "lab coat"],
                            "forbidden_drift": ["do not make her cruel"],
                        }
                    ]
                },
                "complete": True,
            },
            "relationship_baselines": {"value": {"relationships": []}, "complete": False},
            "constraints": {"value": "", "complete": False},
        },
        "brief_draft_ready": brief_draft_ready,
        "updated_at": "",
    }
    (meta_dir / "refinement_intake.json").write_text(json.dumps(intake), encoding="utf-8")


def _confirm_refinement_via_api(server_url: str, project_name: str) -> None:
    brief_keys = [
        "core_premise",
        "audience_genre",
        "tone_themes",
        "visual_style",
        "world_rules",
        "core_cast",
        "character_identity",
        "relationship_baselines",
        "constraints",
    ]
    for key in brief_keys:
        resp = httpx.post(
            f"{server_url}/api/projects/{project_name}/brief/confirm-card",
            json={"card_key": key},
            timeout=5.0,
        )
        assert resp.status_code == 200, resp.text

    for chapter_id in ["ch1", "ch2"]:
        resp = httpx.post(
            f"{server_url}/api/projects/{project_name}/chapter-outline/confirm-chapter",
            json={"chapter_id": chapter_id},
            timeout=5.0,
        )
        assert resp.status_code == 200, resp.text


def _seed_project_blueprint(workspace: Path, project_name: str) -> None:
    import yaml

    meta_dir = workspace / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    blueprint = {
        "title": "Campus Romance",
        "genre": "校园恋爱",
        "worldview": "现代日本高中",
        "themes": ["初恋", "成长"],
        "chapters": [
            {
                "id": "ch1",
                "name": "图书馆相遇",
                "order": 1,
                "scenes": [
                    {"id": "s1-1", "name": "初见", "order": 1},
                    {"id": "s1-2", "name": "借书", "order": 2},
                ],
            },
        ],
    }
    (meta_dir / "blueprint.yaml").write_text(
        yaml.safe_dump(blueprint, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def test_workspace_brief_view_loads_project_brief_from_api(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_brief_load_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    # Click Brief tab
    brief_tab = page.locator("button", has_text="Brief")
    expect(brief_tab).to_be_visible(timeout=10000)
    brief_tab.click()

    # Verify cards rendered
    expect(page.locator("text=Core Premise")).to_be_visible(timeout=10000)
    expect(page.locator("text=A story about discovery.")).to_be_visible(timeout=10000)
    expect(page.locator("text=Character Identity")).to_be_visible(timeout=10000)
    # Use exact match to avoid matching "Elena, Marcus, AI companion." in core_cast
    expect(page.get_by_text("Elena", exact=True)).to_be_visible(timeout=10000)


def test_workspace_brief_view_saves_edits_via_put_brief(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_brief_save_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    brief_tab = page.locator("button", has_text="Brief")
    brief_tab.click()
    expect(page.locator("text=Core Premise")).to_be_visible(timeout=10000)

    # Click Edit
    edit_btn = page.locator("button", has_text="Edit")
    expect(edit_btn).to_be_visible(timeout=10000)
    edit_btn.click()

    # Edit core premise textarea
    textarea = page.locator("textarea").first
    textarea.fill("A story about redemption.")

    # Save
    save_btn = page.locator("button", has_text="Save")
    save_btn.click()

    # Verify saved text appears
    expect(page.locator("text=A story about redemption.")).to_be_visible(timeout=10000)


def test_workspace_brief_view_renders_character_identity_entries(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_char_id_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    brief_tab = page.locator("button", has_text="Brief")
    brief_tab.click()

    expect(page.locator("text=Character Identity")).to_be_visible(timeout=10000)
    expect(page.locator("text=Story Role")).to_be_visible(timeout=10000)
    expect(page.locator("text=Protagonist")).to_be_visible(timeout=10000)
    expect(page.locator("text=Core Motivation")).to_be_visible(timeout=10000)
    expect(page.locator("text=Find her lost brother")).to_be_visible(timeout=10000)
    expect(page.locator("text=Personality Anchors")).to_be_visible(timeout=10000)
    expect(page.locator("text=curious")).to_be_visible(timeout=10000)


def test_workspace_chapter_outline_view_loads_outline_from_api(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_outline_load_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    _seed_project_chapter_outline(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    outline_tab = page.locator("button", has_text="Outline")
    expect(outline_tab).to_be_visible(timeout=10000)
    outline_tab.click()

    expect(page.locator("text=The Beginning")).to_be_visible(timeout=10000)
    expect(page.locator("text=The Search")).to_be_visible(timeout=10000)


def test_workspace_new_project_defaults_to_intake_tab(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_intake_default_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    intake_tab = page.get_by_role("button", name="Intake", exact=True)
    expect(intake_tab).to_be_visible(timeout=10000)
    expect(intake_tab).to_have_class(re.compile("border-blue-500"))
    expect(page.locator("text=Start Project Intake")).to_be_visible(timeout=10000)
    expect(page.locator("text=Create Brief")).to_have_count(0)


def test_workspace_intake_view_shows_agent_summary_and_missing_slots(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_intake_summary_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_refinement_intake(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    intake_tab = page.get_by_role("button", name="Intake", exact=True)
    intake_tab.click()

    expect(page.locator("text=Agent Intake")).to_be_visible(timeout=10000)
    expect(page.get_by_text("A YA sci-fi mystery about Elena searching for her missing brother.", exact=True).first).to_be_visible(timeout=10000)
    expect(page.get_by_text("Relationship Baselines", exact=True).first).to_be_visible(timeout=10000)
    expect(page.get_by_text("Constraints", exact=True).first).to_be_visible(timeout=10000)


def test_workspace_brief_review_is_not_primary_before_draft_ready(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_intake_gate_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_refinement_intake(e2e_workspace, project_name, brief_draft_ready=False, phase="project")
    open_workspace_from_project_list(page, server_url, project_name)

    brief_tab = page.get_by_role("button", name="Brief")
    brief_tab.click()

    expect(page.locator("text=Start in Intake first")).to_be_visible(timeout=10000)
    expect(page.locator("text=Go to Intake")).to_be_visible(timeout=10000)
    expect(page.locator("text=No Project Brief yet")).to_have_count(0)


def test_workspace_promote_brief_draft_enters_brief_review(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_intake_promote_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_refinement_intake(e2e_workspace, project_name, brief_draft_ready=True, phase="brief_ready")
    open_workspace_from_project_list(page, server_url, project_name)

    intake_tab = page.get_by_role("button", name="Intake", exact=True)
    intake_tab.click()
    promote_button = page.get_by_test_id("promote-brief-draft")
    expect(promote_button).to_be_visible(timeout=10000)
    promote_button.click()

    expect(page.get_by_role("button", name="Brief", exact=True)).to_have_class(re.compile("border-blue-500"), timeout=10000)
    expect(page.locator("text=Core Premise")).to_be_visible(timeout=10000)
    assert (e2e_workspace / project_name / "meta" / "project_brief.json").exists()
    expect(page.get_by_text("A YA sci-fi mystery about Elena searching for her missing brother.", exact=True)).to_be_visible(timeout=10000)


def test_workspace_chapter_outline_view_can_add_delete_and_reorder_chapters(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_outline_crud_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    _seed_project_chapter_outline(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    outline_tab = page.locator("button", has_text="Outline")
    outline_tab.click()
    expect(page.locator("text=The Beginning")).to_be_visible(timeout=10000)

    # Edit mode
    edit_btn = page.locator("button", has_text="Edit")
    edit_btn.click()

    # Add chapter
    add_btn = page.locator("button", has_text="Add Chapter")
    add_btn.click()

    # Rename new chapter
    name_input = page.locator("input[value='New Chapter']")
    expect(name_input).to_be_visible(timeout=10000)
    name_input.fill("The Climax")

    # Move first chapter down
    move_down_buttons = page.locator("button[title='Move down']")
    expect(move_down_buttons.first).to_be_visible(timeout=10000)
    move_down_buttons.first.click()

    # Remove last chapter
    remove_buttons = page.locator("button[title='Remove']")
    remove_buttons.last.click()

    # Save
    save_btn = page.locator("button", has_text="Save")
    save_btn.click()

    # After reorder and removal, verify at least one of the original chapters remains
    expect(page.locator("text=The Beginning")).to_be_visible(timeout=10000)


def test_workspace_chapter_outline_view_confirms_chapter_via_api(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_outline_confirm_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    # Confirm all brief cards first so chapter confirm gate opens
    for key in [
        "core_premise",
        "audience_genre",
        "tone_themes",
        "visual_style",
        "world_rules",
        "core_cast",
        "character_identity",
        "relationship_baselines",
        "constraints",
    ]:
        resp = httpx.post(
            f"{server_url}/api/projects/{project_name}/brief/confirm-card",
            json={"card_key": key},
            timeout=5.0,
        )
        assert resp.status_code == 200, resp.text

    _seed_project_chapter_outline(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    outline_tab = page.locator("button", has_text="Outline")
    outline_tab.click()
    expect(page.locator("text=The Beginning")).to_be_visible(timeout=10000)

    # Confirm first chapter
    confirm_buttons = page.locator("button", has_text="Confirm")
    expect(confirm_buttons.first).to_be_visible(timeout=10000)
    confirm_buttons.first.click()

    # Verify button changed to Confirmed
    expect(page.locator("button", has_text="Confirmed").first).to_be_visible(timeout=10000)


def test_workspace_refinement_status_shows_blocked_reason_before_blueprint_ready(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_status_block_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    # Wait for workspace to load
    expect(page.locator("h1")).to_have_text(project_name, timeout=10000)

    # Refinement status panel should show blocked reason
    expect(page.locator("text=Complete all Project Brief cards first")).to_be_visible(timeout=10000)
    expect(page.get_by_text("Planning", exact=True)).to_be_visible(timeout=10000)


def test_workspace_brief_view_renders_relationship_baselines_card(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_rb_render_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    brief_tab = page.locator("button", has_text="Brief")
    brief_tab.click()

    expect(page.locator("text=Relationship Baselines")).to_be_visible(timeout=10000)
    expect(page.locator("text=Friends")).to_be_visible(timeout=10000)
    expect(page.locator("text=trust")).to_be_visible(timeout=10000)


def test_workspace_brief_view_saves_relationship_baselines_via_put_brief(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_rb_save_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    brief_tab = page.locator("button", has_text="Brief")
    brief_tab.click()
    expect(page.locator("text=Relationship Baselines")).to_be_visible(timeout=10000)

    # Edit mode
    edit_btn = page.locator("button", has_text="Edit")
    edit_btn.click()

    # Edit the baseline input for the first relationship
    baseline_input = page.locator("[data-testid='baseline-input']")
    expect(baseline_input).to_be_visible(timeout=10000)
    baseline_input.fill("Close friends")

    # Save
    save_btn = page.locator("button", has_text="Save")
    save_btn.click()

    # Verify saved text appears
    expect(page.locator("text=Close friends")).to_be_visible(timeout=10000)


def test_workspace_brief_view_confirms_relationship_baselines_card_via_api(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_rb_confirm_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    brief_tab = page.locator("button", has_text="Brief")
    brief_tab.click()
    expect(page.locator("text=Relationship Baselines")).to_be_visible(timeout=10000)

    # Click Confirm on relationship_baselines card
    confirm_btn = page.locator("[data-testid='confirm-relationship-baselines']")
    expect(confirm_btn).to_be_visible(timeout=10000)
    confirm_btn.click()

    # Verify button changed to Confirmed
    expect(page.locator("[data-testid='confirm-relationship-baselines']", has_text="Confirmed")).to_be_visible(timeout=10000)


def test_workspace_legacy_project_status_panel_shows_ready_without_blocked_reason(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_legacy_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    # Workspace should load without crashing
    expect(page.locator("h1")).to_have_text(project_name, timeout=10000)

    # Brief tab should show empty state
    brief_tab = page.locator("button", has_text="Brief").first
    brief_tab.click()
    expect(page.locator("text=No Project Brief yet")).to_be_visible(timeout=10000)

    # Refinement status should show legacy state with ready wording
    expect(page.get_by_text("Legacy blueprint", exact=True)).to_be_visible(timeout=10000)
    expect(page.locator("text=Complete all Project Brief cards first")).not_to_be_visible()
    expect(page.get_by_text("Planning", exact=True)).not_to_be_visible()


def test_workspace_brief_empty_state_create_opens_edit_form(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_brief_create_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    # Seed blueprint so workspace tabs are visible (isOnboarding=false)
    _seed_project_blueprint(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    brief_tab = page.locator("button", has_text="Brief").first
    expect(brief_tab).to_be_visible(timeout=10000)
    brief_tab.click()
    expect(page.locator("text=No Project Brief yet")).to_be_visible(timeout=10000)

    # Click Create Brief
    create_btn = page.locator("button", has_text="Create Brief").first
    expect(create_btn).to_be_visible(timeout=10000)
    create_btn.click()

    # Should enter edit mode with Save / Cancel visible
    expect(page.locator("button", has_text="Save")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="Cancel")).to_be_visible(timeout=10000)
    expect(page.locator("text=No Project Brief yet")).not_to_be_visible()


def test_workspace_outline_empty_state_create_opens_edit_form(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_outline_create_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    # Seed blueprint + brief so workspace tabs are visible, but no outline
    _seed_project_blueprint(e2e_workspace, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    outline_tab = page.locator("button", has_text="Outline")
    expect(outline_tab).to_be_visible(timeout=10000)
    outline_tab.click()
    expect(page.locator("text=No Chapter Outline yet")).to_be_visible(timeout=10000)

    # Click Create Outline
    create_btn = page.locator("button", has_text="Create Outline")
    expect(create_btn).to_be_visible(timeout=10000)
    create_btn.click()

    # Should enter edit mode with Save / Cancel visible
    expect(page.locator("button", has_text="Save")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="Cancel")).to_be_visible(timeout=10000)
    expect(page.locator("text=No Chapter Outline yet")).not_to_be_visible()


def test_workspace_brief_api_failure_shows_error_not_empty_state(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_brief_err_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    # Seed blueprint so tabs are visible
    _seed_project_blueprint(e2e_workspace, project_name)
    # Seed a corrupted brief file to trigger 500 on /brief
    meta_dir = e2e_workspace / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "project_brief.json").write_text("{\"bad\":", encoding="utf-8")
    open_workspace_from_project_list(page, server_url, project_name)

    brief_tab = page.locator("button", has_text="Brief")
    expect(brief_tab).to_be_visible(timeout=10000)
    brief_tab.click()

    # Should show error, not empty state
    expect(page.locator("text=Failed to load Project Brief")).to_be_visible(timeout=10000)
    expect(page.locator("text=No Project Brief yet")).not_to_be_visible()


def test_workspace_outline_api_failure_shows_error_not_empty_state(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_outline_err_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    # Seed blueprint + brief so tabs are visible
    _seed_project_blueprint(e2e_workspace, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    # Seed a corrupted outline file to trigger 500 on /chapter-outline
    meta_dir = e2e_workspace / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "chapter_outline.json").write_text("{\"bad\":", encoding="utf-8")
    open_workspace_from_project_list(page, server_url, project_name)

    outline_tab = page.locator("button", has_text="Outline")
    expect(outline_tab).to_be_visible(timeout=10000)
    outline_tab.click()

    # Should show error, not empty state
    expect(page.locator("text=Failed to load Chapter Outline")).to_be_visible(timeout=10000)
    expect(page.locator("text=No Chapter Outline yet")).not_to_be_visible()


def test_workspace_refinement_status_api_failure_is_visible(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_status_err_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    # Seed blueprint + brief + outline so workspace is visible
    _seed_project_blueprint(e2e_workspace, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    _seed_project_chapter_outline(e2e_workspace, project_name)
    # Corrupt brief so /refinement-status returns 500 (it reads brief)
    meta_dir = e2e_workspace / project_name / "meta"
    (meta_dir / "project_brief.json").write_text("{\"bad\":", encoding="utf-8")
    open_workspace_from_project_list(page, server_url, project_name)

    # Refinement status panel should show error state
    expect(page.locator("text=Failed to load refinement status")).to_be_visible(timeout=10000)


def test_workspace_new_project_shows_brief_tab_and_create_entry(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """A brand-new project without any seeded data must enter the refinement workspace
    directly, showing tabs and the Intake entry path."""
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_new_proj_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    # Tabs must be visible immediately (no full-page onboarding blocking them)
    brief_tab = page.locator("button", has_text="Brief").first
    expect(brief_tab).to_be_visible(timeout=10000)
    outline_tab = page.locator("button", has_text="Outline").first
    expect(outline_tab).to_be_visible(timeout=10000)
    blueprint_tab = page.locator("button", has_text="蓝图").first
    expect(blueprint_tab).to_be_visible(timeout=10000)

    intake_tab = page.get_by_role("button", name="Intake", exact=True)
    expect(intake_tab).to_be_visible(timeout=10000)

    # Intake tab is active by default -> start entry visible
    expect(page.locator("text=Start Project Intake")).to_be_visible(timeout=10000)
    start_btn = page.get_by_role("button", name="Start Intake with AI", exact=True)
    expect(start_btn).to_be_visible(timeout=10000)


def test_workspace_new_project_defaults_to_brief_tab(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """A fresh project should land on the Intake tab by default."""
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_default_brief_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    # Intake tab should be active (blue underline / text colour)
    intake_tab = page.get_by_role("button", name="Intake", exact=True)
    expect(intake_tab).to_have_class(re.compile(r"border-blue-500"), timeout=10000)

    # Start Intake entry visible without any click
    expect(page.locator("text=Start Project Intake")).to_be_visible(timeout=10000)


def test_workspace_refinement_status_error_is_visible_without_seeded_blueprint(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Refinement-status errors must be visible even when no blueprint exists."""
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_status_err_no_bp_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    # Corrupt brief so /refinement-status returns 500
    meta_dir = e2e_workspace / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "project_brief.json").write_text('{"bad":', encoding="utf-8")
    open_workspace_from_project_list(page, server_url, project_name)

    # Refinement status panel should show error state (not be hidden by onboarding)
    expect(page.locator("text=Failed to load refinement status").first).to_be_visible(timeout=10000)


def test_workspace_blueprint_tab_can_still_show_onboarding_for_new_project(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """The old onboarding must still appear inside the Blueprint tab for a new project."""
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_bp_onboard_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    # Switch to Blueprint tab (label is "蓝图" in Chinese)
    blueprint_tab = page.locator("button", has_text="蓝图").first
    expect(blueprint_tab).to_be_visible(timeout=10000)
    blueprint_tab.click()

    # Onboarding content should be visible inside the tab
    expect(page.locator("text=项目已创建，开始构建蓝图吧").first).to_be_visible(timeout=10000)
def test_workspace_planning_only_project_hides_build_and_preview_actions(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Refinement-only projects without a blueprint should not expose Build/Preview actions."""
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_planning_only_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    expect(page.locator("h1")).to_have_text(project_name, timeout=10000)
    expect(page.get_by_role("button", name="Build")).not_to_be_visible()
    expect(page.get_by_role("button", name="Preview")).not_to_be_visible()


def test_workspace_blueprint_project_shows_build_and_preview_actions(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Projects with a real blueprint should still expose Build/Preview actions."""
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_bp_actions_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    expect(page.locator("h1")).to_have_text(project_name, timeout=10000)
    expect(page.get_by_role("button", name="Build")).to_be_visible(timeout=10000)
    expect(page.get_by_role("button", name="Preview")).to_be_visible(timeout=10000)


def test_workspace_shows_freeze_action_when_refinement_ready(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_freeze_ready_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    _seed_project_chapter_outline(e2e_workspace, project_name)
    _confirm_refinement_via_api(server_url, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    expect(page.get_by_role("button", name="Freeze Blueprint")).to_be_visible(timeout=10000)
    expect(page.locator("text=Freeze the blueprint to unlock generation")).to_be_visible(timeout=10000)


def test_workspace_freeze_action_creates_frozen_blueprint(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_freeze_ok_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    _seed_project_chapter_outline(e2e_workspace, project_name)
    _confirm_refinement_via_api(server_url, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    freeze_btn = page.get_by_role("button", name="Freeze Blueprint")
    expect(freeze_btn).to_be_visible(timeout=10000)
    freeze_btn.click()

    expect(page.locator("text=Ready for generation")).to_be_visible(timeout=10000)
    expect(page.locator("text=Freeze the blueprint to unlock generation")).not_to_be_visible()

    bp = httpx.get(f"{server_url}/api/projects/{project_name}/blueprint", timeout=5.0)
    assert bp.status_code == 200, bp.text
    assert bp.json()["chapters"][0]["id"] == "ch1"


def test_workspace_upstream_edit_marks_blueprint_stale(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_freeze_stale_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    _seed_project_chapter_outline(e2e_workspace, project_name)
    _confirm_refinement_via_api(server_url, project_name)
    httpx.post(f"{server_url}/api/projects/{project_name}/blueprint/freeze", timeout=5.0)
    open_workspace_from_project_list(page, server_url, project_name)

    brief_tab = page.locator("button", has_text="Brief").first
    brief_tab.click()
    page.locator("button", has_text="Edit").click()
    page.locator("textarea").first.fill("A story about discovery after freeze.")
    page.locator("button", has_text="Save").click()

    expect(page.locator("text=Blueprint stale")).to_be_visible(timeout=10000)
    expect(page.locator("text=Project Brief or Chapter Outline changed. Freeze Blueprint again.")).to_be_visible(timeout=10000)


def test_workspace_generation_stays_blocked_until_freeze(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_freeze_block_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief(e2e_workspace, project_name)
    _seed_project_chapter_outline(e2e_workspace, project_name)
    _confirm_refinement_via_api(server_url, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    status = httpx.get(f"{server_url}/api/projects/{project_name}/refinement-status", timeout=5.0)
    assert status.status_code == 200, status.text
    data = status.json()
    assert data["blueprint_ready"] is True
    assert data["blueprint_freeze_status"] == "not_frozen"
    assert data["generation_allowed"] is False
    expect(page.locator("text=Freeze the blueprint to unlock generation")).to_be_visible(timeout=10000)


def _seed_project_brief_confirmed(workspace: Path, project_name: str) -> None:
    """Seed a fully confirmed project brief."""
    meta_dir = workspace / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    brief = {
        "cards": {
            "core_premise": {"content": "A story about discovery.", "confirmed": True},
            "audience_genre": {"content": "Sci-fi, teens.", "confirmed": True},
            "tone_themes": {"content": "Hopeful, exploration.", "confirmed": True},
            "visual_style": {"content": "Cel-shaded, neon.", "confirmed": True},
            "world_rules": {"content": "Faster-than-light travel exists.", "confirmed": True},
            "core_cast": {"content": "Elena, Marcus, AI companion.", "confirmed": True},
            "character_identity": {
                "content": {
                    "characters": [
                        {
                            "character_id": "elena",
                            "name": "Elena",
                            "story_role": "Protagonist",
                            "core_motivation": "Find her lost brother",
                            "personality_anchors": ["curious", "stubborn"],
                            "visual_identity_anchors": ["blue hair", "lab coat"],
                            "forbidden_drift": ["do not make her cruel"],
                        }
                    ]
                },
                "confirmed": True,
            },
            "relationship_baselines": {
                "content": {"relationships": [{"pair": ["elena", "marcus"], "baseline": "Friends", "must_preserve": []}]},
                "confirmed": True,
            },
            "constraints": {"content": "No time travel.", "confirmed": True},
        },
        "updated_at": "2026-04-22T00:00:00Z",
    }
    (meta_dir / "project_brief.json").write_text(json.dumps(brief), encoding="utf-8")


def _seed_project_chapter_intake(workspace: Path, project_name: str, outline_ready: bool = True) -> None:
    """Seed a chapter-level refinement intake."""
    meta_dir = workspace / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    intake = {
        "phase": "outline_ready" if outline_ready else "chapter",
        "current_summary": "Brief confirmed. Collecting chapter details.",
        "missing_slots": [],
        "slots": {},
        "brief_draft_ready": True,
        "chapter_draft": [
            {
                "chapter_id": "ch1",
                "order": 1,
                "chapter_name": "Departure",
                "chapter_goal": "Establish motivation",
                "key_conflict": "Elena vs authority",
                "emotional_arc": "hope -> tension",
                "reveals": "Brother is missing",
                "end_state": "Elena leaves home",
                "mood_or_pacing_bias": "slow",
                "character_focus": ["elena"],
                "relationship_shift": "Elena distances from parents",
                "character_presentation_notes": "Civilian clothes",
            },
            {
                "chapter_id": "ch2",
                "order": 2,
                "chapter_name": "The Jump",
                "chapter_goal": "First FTL journey",
                "key_conflict": "Engine malfunction",
                "emotional_arc": "fear -> exhilaration",
                "reveals": "Marcus may still be alive",
                "end_state": "Arrival at Outpost 7",
                "mood_or_pacing_bias": "fast",
                "character_focus": ["elena", "marcus"],
                "relationship_shift": "Marcus reappears as ally",
                "character_presentation_notes": "Flight suit",
            },
        ],
        "outline_draft_ready": outline_ready,
        "updated_at": "2026-04-23T00:00:00Z",
    }
    (meta_dir / "refinement_intake.json").write_text(json.dumps(intake), encoding="utf-8")


def test_workspace_brief_confirmed_without_outline_defaults_to_intake_tab(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Brief fully confirmed but no outline yet -> default tab should be Intake."""
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_ch_intake_default_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief_confirmed(e2e_workspace, project_name)
    _seed_project_chapter_intake(e2e_workspace, project_name, outline_ready=False)
    open_workspace_from_project_list(page, server_url, project_name)

    # Intake tab should be active
    intake_tab = page.locator("button", has_text="Intake").first
    expect(intake_tab).to_have_class(re.compile(r"border-blue-500"), timeout=10000)


def test_workspace_brief_confirmed_without_intake_still_defaults_to_intake_tab(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Missing intake file must not drop a brief-confirmed project back to Brief as the primary path."""
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_ch_missing_intake_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief_confirmed(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    intake_tab = page.locator("button", has_text="Intake").first
    expect(intake_tab).to_have_class(re.compile(r"border-blue-500"), timeout=10000)
    expect(page.locator("text=Start Project Intake")).to_be_visible(timeout=10000)


def test_workspace_intake_view_shows_chapter_draft_summary(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Chapter intake should render chapter draft cards."""
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_ch_draft_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief_confirmed(e2e_workspace, project_name)
    _seed_project_chapter_intake(e2e_workspace, project_name, outline_ready=True)
    open_workspace_from_project_list(page, server_url, project_name)

    expect(page.locator("text=Chapter Draft")).to_be_visible(timeout=10000)
    expect(page.locator("text=Departure")).to_be_visible(timeout=10000)
    expect(page.locator("text=The Jump")).to_be_visible(timeout=10000)
    expect(page.locator("text=Establish motivation")).to_be_visible(timeout=10000)


def test_workspace_outline_review_is_not_primary_before_outline_draft_ready(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Outline tab should show intake prompt when chapter intake is required."""
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_ch_outline_gate_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief_confirmed(e2e_workspace, project_name)
    _seed_project_chapter_intake(e2e_workspace, project_name, outline_ready=False)
    open_workspace_from_project_list(page, server_url, project_name)

    # Switch to Outline tab
    outline_tab = page.locator("button", has_text="Outline").first
    outline_tab.click()

    expect(page.locator("text=Chapter Intake First")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="Go to Intake")).to_be_visible(timeout=10000)


def test_workspace_promote_outline_draft_enters_outline_review(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Clicking Enter Outline Review should materialize chapter outline and show review UI."""
    assert wait_for_server(server_url), "Server not ready"
    project_name = f"playwright_ch_promote_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_brief_confirmed(e2e_workspace, project_name)
    _seed_project_chapter_intake(e2e_workspace, project_name, outline_ready=True)
    open_workspace_from_project_list(page, server_url, project_name)

    expect(page.locator("text=Chapter Draft")).to_be_visible(timeout=10000)
    promote_btn = page.locator("[data-testid='promote-outline-draft']")
    expect(promote_btn).to_be_visible(timeout=10000)
    promote_btn.click()

    # Should switch to Outline tab with chapters visible
    expect(page.locator("text=Departure")).to_be_visible(timeout=10000)
    expect(page.locator("text=The Jump")).to_be_visible(timeout=10000)

    # Verify outline was persisted
    outline = httpx.get(f"{server_url}/api/projects/{project_name}/chapter-outline", timeout=5.0)
    assert outline.status_code == 200, outline.text
    data = outline.json()
    assert len(data["chapters"]) == 2
    assert data["chapters"][0]["chapter_id"] == "ch1"
    assert data["chapters"][0]["confirmed"] is False
