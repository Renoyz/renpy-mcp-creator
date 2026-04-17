"""Structured audit models for the chat engine and dashboard."""

from __future__ import annotations

from pydantic import BaseModel


class AuditIssue(BaseModel):
    """Single issue inside an audit report."""

    id: str
    type: str  # e.g. plot_hole, consistency, characterization, pacing, sensitive
    severity: str  # high, medium, low
    description: str
    scene_id: str | None = None
    suggestion: str = ""


class AuditReport(BaseModel):
    """Aggregate audit result for a project or chapter."""

    status: str  # passed or failed
    overall_score: int
    summary: str = ""
    issues: list[AuditIssue] = []
