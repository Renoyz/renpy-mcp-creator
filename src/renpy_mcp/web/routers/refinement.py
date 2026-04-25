"""Refinement routes — intake, brief, outline, freeze, status."""

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from ...blueprint.models import (
    BlueprintFreezeStatus,
    ChapterOutline,
    IntakePhase,
    ProjectBlueprint,
    ProjectBrief,
    RefinementState,
)
from ...config import get_settings, resolve_project_dir
from ...services.project_manager import ProjectManager
from ...utils.atomic_file import transactional_write
from ...services.refinement_logic import (
    assemble_frozen_blueprint,
    build_chapter_intake_entries_from_blueprint,
    compute_blueprint_freeze_status,
    compute_refinement_state,
    freeze_status_after_upstream_change,
    is_brief_fully_confirmed,
    is_character_identity_card_valid,
    is_outline_fully_confirmed,
    materialize_brief_from_intake,
    materialize_outline_from_intake,
    persist_refinement_metadata,
)
from ..chat_ws import _append_refinement_flow_log

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/projects/{project_name}/refinement-intake")
async def api_project_refinement_intake_get(project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    settings = get_settings()
    pm = ProjectManager(settings)
    try:
        intake = pm.read_refinement_intake(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if intake is None:
        raise HTTPException(status_code=404, detail="Refinement intake not found")
    return intake.model_dump(mode="json")


@router.post("/api/projects/{project_name}/brief/promote-draft")
async def api_project_brief_promote_draft(project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    settings = get_settings()
    pm = ProjectManager(settings)
    try:
        intake = pm.read_refinement_intake(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if intake is None:
        raise HTTPException(status_code=404, detail="Refinement intake not found")
    if not intake.brief_draft_ready:
        raise HTTPException(status_code=409, detail="Project Brief draft is not ready yet")

    try:
        outline = pm.read_chapter_outline(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        meta = pm.read_project_meta(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    brief = materialize_brief_from_intake(intake)
    target_state = compute_refinement_state(brief, outline)
    target_freeze_status = freeze_status_after_upstream_change(
        meta.blueprint_freeze_status if meta else None
    )

    brief_path = project_dir / "meta" / "project_brief.json"
    meta_path = project_dir / "meta" / "project.json"
    try:
        with transactional_write(brief_path, meta_path):
            pm.write_project_brief(project_name, brief)
            persist_refinement_metadata(pm, project_name, target_state, target_freeze_status)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transaction failed: {exc}")

    return {"success": True}


@router.post("/api/projects/{project_name}/chapter-outline/promote-draft")
async def api_project_chapter_outline_promote_draft(project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    logger.info("Chapter outline promote requested for project %s", project_name)
    _append_refinement_flow_log(project_name, "INFO", "Chapter outline promote requested for project %s", project_name)
    settings = get_settings()
    pm = ProjectManager(settings)
    try:
        intake = pm.read_refinement_intake(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if intake is None:
        logger.info("Chapter outline promote blocked for project %s: refinement intake missing", project_name)
        _append_refinement_flow_log(
            project_name, "INFO", "Chapter outline promote blocked for project %s: refinement intake missing", project_name
        )
        raise HTTPException(status_code=404, detail="Refinement intake not found")
    if not intake.outline_draft_ready:
        logger.info("Chapter outline promote blocked for project %s: outline draft not ready", project_name)
        _append_refinement_flow_log(
            project_name, "INFO", "Chapter outline promote blocked for project %s: outline draft not ready", project_name
        )
        raise HTTPException(status_code=409, detail="Chapter Outline draft is not ready yet")
    if intake.phase not in (IntakePhase.CHAPTER, IntakePhase.OUTLINE_READY):
        logger.info(
            "Chapter outline promote blocked for project %s: invalid intake phase %s",
            project_name,
            intake.phase.value,
        )
        _append_refinement_flow_log(
            project_name,
            "INFO",
            "Chapter outline promote blocked for project %s: invalid intake phase %s",
            project_name,
            intake.phase.value,
        )
        raise HTTPException(
            status_code=409,
            detail=f"Chapter Outline promotion requires intake phase 'chapter' or 'outline_ready', got '{intake.phase.value}'",
        )

    try:
        brief = pm.read_project_brief(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if brief is None or not is_brief_fully_confirmed(brief):
        logger.info("Chapter outline promote blocked for project %s: brief not fully confirmed", project_name)
        _append_refinement_flow_log(
            project_name, "INFO", "Chapter outline promote blocked for project %s: brief not fully confirmed", project_name
        )
        raise HTTPException(
            status_code=409,
            detail="Cannot promote Chapter Outline draft before Project Brief is fully confirmed",
        )

    try:
        existing_outline = pm.read_chapter_outline(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        meta = pm.read_project_meta(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    outline = materialize_outline_from_intake(intake)
    logger.info(
        "Chapter outline promote materialized %d chapters for project %s",
        len(outline.chapters),
        project_name,
    )
    _append_refinement_flow_log(
        project_name,
        "INFO",
        "Chapter outline promote materialized %d chapters for project %s",
        len(outline.chapters),
        project_name,
    )
    target_state = compute_refinement_state(brief, outline)
    target_freeze_status = freeze_status_after_upstream_change(
        meta.blueprint_freeze_status if meta else None
    )

    outline_path = project_dir / "meta" / "chapter_outline.json"
    meta_path = project_dir / "meta" / "project.json"
    try:
        with transactional_write(outline_path, meta_path):
            pm.write_chapter_outline(project_name, outline)
            persist_refinement_metadata(pm, project_name, target_state, target_freeze_status)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transaction failed: {exc}")

    return {"success": True}


@router.get("/api/projects/{project_name}/brief")
async def api_project_brief_get(project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    settings = get_settings()
    pm = ProjectManager(settings)
    try:
        brief = pm.read_project_brief(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if brief is None:
        raise HTTPException(status_code=404, detail="Project brief not found")
    return brief.model_dump(mode="json")


@router.put("/api/projects/{project_name}/brief")
async def api_project_brief_put(request: Request, project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid brief: malformed JSON ({exc})")
    try:
        brief = ProjectBrief.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid brief: {exc}")
    settings = get_settings()
    pm = ProjectManager(settings)
    for card in brief.cards.values():
        card.confirmed = False

    try:
        outline = pm.read_chapter_outline(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        meta = pm.read_project_meta(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    target_state = compute_refinement_state(brief, outline)
    target_freeze_status = freeze_status_after_upstream_change(
        meta.blueprint_freeze_status if meta else None
    )

    brief_path = project_dir / "meta" / "project_brief.json"
    meta_path = project_dir / "meta" / "project.json"
    try:
        with transactional_write(brief_path, meta_path):
            pm.write_project_brief(project_name, brief)
            persist_refinement_metadata(pm, project_name, target_state, target_freeze_status)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transaction failed: {exc}")

    return {"success": True}


@router.post("/api/projects/{project_name}/brief/confirm-card")
async def api_project_brief_confirm_card(request: Request, project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid request: malformed JSON ({exc})")
    card_key = body.get("card_key", "").strip()
    if not card_key:
        raise HTTPException(status_code=400, detail="card_key is required")

    settings = get_settings()
    pm = ProjectManager(settings)
    try:
        brief = pm.read_project_brief(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if brief is None:
        raise HTTPException(status_code=404, detail="Project brief not found")
    if card_key not in brief.cards:
        raise HTTPException(status_code=400, detail=f"Card '{card_key}' not found in brief")

    if card_key == "character_identity":
        if not is_character_identity_card_valid(brief.cards[card_key]):
            raise HTTPException(
                status_code=400,
                detail="Character identity card is incomplete. Each character needs at least story_role, core_motivation, personality_anchors, visual_identity_anchors, or forbidden_drift.",
            )

    brief.cards[card_key].confirmed = True

    try:
        outline = pm.read_chapter_outline(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        meta = pm.read_project_meta(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    target_state = compute_refinement_state(brief, outline)
    target_freeze_status = freeze_status_after_upstream_change(
        meta.blueprint_freeze_status if meta else None
    )

    brief_path = project_dir / "meta" / "project_brief.json"
    meta_path = project_dir / "meta" / "project.json"
    try:
        with transactional_write(brief_path, meta_path):
            pm.write_project_brief(project_name, brief)
            persist_refinement_metadata(pm, project_name, target_state, target_freeze_status)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transaction failed: {exc}")

    # Auto-promote chapter outline draft from blueprint session when brief is fully confirmed
    if is_brief_fully_confirmed(brief):
        try:
            intake = pm.read_refinement_intake(project_name)
        except ValueError:
            intake = None

        if intake is not None and not intake.outline_draft_ready:
            from ..chat_ws import _load_runtime_session

            session = _load_runtime_session(project_name)
            if session and session.get("draft"):
                try:
                    blueprint = ProjectBlueprint.model_validate(session["draft"])
                    chapter_draft = build_chapter_intake_entries_from_blueprint(blueprint)
                    updated_intake = intake.model_copy(
                        update={
                            "phase": IntakePhase.OUTLINE_READY,
                            "outline_draft_ready": True,
                            "brief_draft_ready": True,
                            "chapter_draft": chapter_draft,
                        }
                    )
                    pm.write_refinement_intake(project_name, updated_intake)
                except Exception:
                    logger.warning(
                        "Auto-promotion failed during confirm-card for %s",
                        project_name,
                        exc_info=True,
                    )

    return {"success": True, "card_key": card_key, "confirmed": True}


@router.get("/api/projects/{project_name}/chapter-outline")
async def api_project_chapter_outline_get(project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    settings = get_settings()
    pm = ProjectManager(settings)
    try:
        outline = pm.read_chapter_outline(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if outline is None:
        raise HTTPException(status_code=404, detail="Chapter outline not found")
    return outline.model_dump(mode="json")


@router.put("/api/projects/{project_name}/chapter-outline")
async def api_project_chapter_outline_put(request: Request, project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid outline: malformed JSON ({exc})")
    try:
        outline = ChapterOutline.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid outline: {exc}")
    settings = get_settings()
    pm = ProjectManager(settings)
    for ch in outline.chapters:
        ch.confirmed = False

    try:
        brief = pm.read_project_brief(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        meta = pm.read_project_meta(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    target_state = compute_refinement_state(brief, outline)
    target_freeze_status = freeze_status_after_upstream_change(
        meta.blueprint_freeze_status if meta else None
    )

    outline_path = project_dir / "meta" / "chapter_outline.json"
    meta_path = project_dir / "meta" / "project.json"
    try:
        with transactional_write(outline_path, meta_path):
            pm.write_chapter_outline(project_name, outline)
            persist_refinement_metadata(pm, project_name, target_state, target_freeze_status)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transaction failed: {exc}")

    return {"success": True}


@router.post("/api/projects/{project_name}/chapter-outline/confirm-chapter")
async def api_project_chapter_outline_confirm_chapter(request: Request, project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid request: malformed JSON ({exc})")
    chapter_id = body.get("chapter_id", "").strip()
    if not chapter_id:
        raise HTTPException(status_code=400, detail="chapter_id is required")

    settings = get_settings()
    pm = ProjectManager(settings)
    try:
        outline = pm.read_chapter_outline(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if outline is None:
        raise HTTPException(status_code=404, detail="Chapter outline not found")

    try:
        brief = pm.read_project_brief(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if brief is None or not is_brief_fully_confirmed(brief):
        raise HTTPException(
            status_code=409,
            detail="Cannot confirm chapter outline before all brief cards are confirmed.",
        )

    for ch in outline.chapters:
        if ch.chapter_id == chapter_id:
            ch.confirmed = True

            target_state = compute_refinement_state(brief, outline)
            try:
                meta = pm.read_project_meta(project_name)
            except ValueError as exc:
                raise HTTPException(status_code=500, detail=str(exc))
            target_freeze_status = freeze_status_after_upstream_change(
                meta.blueprint_freeze_status if meta else None
            )

            outline_path = project_dir / "meta" / "chapter_outline.json"
            meta_path = project_dir / "meta" / "project.json"

            try:
                with transactional_write(outline_path, meta_path):
                    pm.write_chapter_outline(project_name, outline)
                    persist_refinement_metadata(pm, project_name, target_state, target_freeze_status)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Transaction failed: {exc}")

            return {"success": True, "chapter_id": chapter_id, "confirmed": True}

    raise HTTPException(status_code=400, detail=f"Chapter '{chapter_id}' not found")


@router.post("/api/projects/{project_name}/blueprint/freeze")
async def api_project_blueprint_freeze(project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    settings = get_settings()
    pm = ProjectManager(settings)
    try:
        brief = pm.read_project_brief(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        outline = pm.read_chapter_outline(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        meta = pm.read_project_meta(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    target_state = compute_refinement_state(brief, outline)
    if brief is None or outline is None or target_state != RefinementState.BLUEPRINT_READY:
        raise HTTPException(
            status_code=409,
            detail="Cannot freeze blueprint before all Project Brief cards and Chapter Outline chapters are confirmed.",
        )

    blueprint = assemble_frozen_blueprint(project_name, brief, outline)
    blueprint_path = project_dir / "meta" / "blueprint.yaml"
    backup_path = project_dir / "meta" / "blueprint.previous.yaml"
    meta_path = project_dir / "meta" / "project.json"

    try:
        with transactional_write(blueprint_path, backup_path, meta_path):
            if blueprint_path.exists():
                backup_path.write_text(blueprint_path.read_text(encoding="utf-8"), encoding="utf-8")
            pm.write_blueprint(project_name, blueprint)
            persist_refinement_metadata(
                pm,
                project_name,
                RefinementState.BLUEPRINT_READY,
                BlueprintFreezeStatus.FROZEN,
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transaction failed: {exc}")

    return {"success": True, "blueprint_freeze_status": "frozen"}


@router.get("/api/projects/{project_name}/refinement-status")
async def api_project_refinement_status(project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    settings = get_settings()
    pm = ProjectManager(settings)

    try:
        brief = pm.read_project_brief(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        outline = pm.read_chapter_outline(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        meta = pm.read_project_meta(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        intake = pm.read_refinement_intake(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    target_state = compute_refinement_state(brief, outline)
    freeze_status = compute_blueprint_freeze_status(meta, brief, outline)

    brief_fully_confirmed = is_brief_fully_confirmed(brief) if brief else False
    outline_fully_confirmed = is_outline_fully_confirmed(outline) if outline else False
    blueprint_ready = target_state == RefinementState.BLUEPRINT_READY
    freeze_allowed = blueprint_ready

    has_blueprint = False
    if brief is None and outline is None:
        try:
            has_blueprint = pm.read_blueprint(project_name) is not None
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        generation_allowed = has_blueprint
    else:
        generation_allowed = (
            blueprint_ready and freeze_status == BlueprintFreezeStatus.FROZEN
        )

    intake_required = brief is None and not has_blueprint
    chapter_intake_required = (
        brief_fully_confirmed
        and (outline is None or not outline.chapters)
    )

    return {
        "refinement_state": target_state.value if target_state else None,
        "brief_fully_confirmed": brief_fully_confirmed,
        "outline_fully_confirmed": outline_fully_confirmed,
        "blueprint_ready": blueprint_ready,
        "freeze_allowed": freeze_allowed,
        "blueprint_freeze_status": freeze_status.value if freeze_status else None,
        "generation_allowed": generation_allowed,
        "intake_phase": intake.phase.value if intake else None,
        "brief_draft_ready": intake.brief_draft_ready if intake else False,
        "outline_draft_ready": intake.outline_draft_ready if intake else False,
        "intake_required": intake_required,
        "chapter_intake_required": chapter_intake_required,
    }
