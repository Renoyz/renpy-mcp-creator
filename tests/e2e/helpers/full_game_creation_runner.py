from pathlib import Path
from typing import Any, Callable


StageCallback = Callable[["FullGameCreationRunner"], Any]
UIAttemptCallback = Callable[["FullGameCreationRunner"], bool]


class FullGameCreationRunner:
    def __init__(
        self,
        *,
        page: Any,
        server_url: str,
        workspace: Path,
        mode: Any,
        artifacts: Any,
        create_project: StageCallback | None = None,
        intake: StageCallback | None = None,
        brief_review: StageCallback | None = None,
        outline_review: StageCallback | None = None,
        freeze_and_build: StageCallback | None = None,
    ) -> None:
        self.page = page
        self.server_url = server_url
        self.workspace = workspace
        self.mode = mode
        self.artifacts = artifacts
        self.create_project = create_project
        self.intake = intake
        self.brief_review = brief_review
        self.outline_review = outline_review
        self.freeze_and_build = freeze_and_build
        self.diagnostics: list[dict[str, Any]] = []
        self.fallbacks: list[dict[str, Any]] = []

    def can_use_api_promote_fallback(self, ui_failure: bool = False) -> bool:
        return bool(ui_failure and self.mode.allow_api_promote_fallback)

    def can_use_api_confirm_fallback(self, ui_failure: bool = False) -> bool:
        return bool(ui_failure and self.mode.allow_api_confirm_fallback)

    def record_diagnostic(self, code: str, *, stage: str, detail: str | None = None) -> dict[str, Any]:
        entry = {"code": code, "stage": stage}
        if detail:
            entry["detail"] = detail
        self.diagnostics.append(entry)
        return entry

    def record_fallback(
        self,
        fallback_used: str,
        *,
        stage: str,
        reason: str,
        step_id: str,
    ) -> dict[str, Any]:
        entry = {
            "fallback_used": fallback_used,
            "stage": stage,
            "reason": reason,
            "step_id": step_id,
        }
        self.fallbacks.append(entry)
        if self.artifacts is not None and hasattr(self.artifacts, "write_text"):
            self.artifacts.write_text(
                step_id,
                "fallback",
                f"fallback_used={fallback_used}\nreason={reason}",
            )
        return entry

    def attempt_brief_review(
        self,
        ui_attempt: UIAttemptCallback,
        fallback: StageCallback,
    ) -> Any:
        if ui_attempt(self):
            return "ui"
        self.record_diagnostic("brief_tab_route_failure", stage="brief_review")
        self.record_fallback(
            "api_promote_brief",
            stage="brief_review",
            reason="brief_tab_not_visible_after_ui_click",
            step_id="08_brief_tab_route_failure",
        )
        if not self.can_use_api_promote_fallback(ui_failure=True):
            raise AssertionError("Current execution mode forbids API brief promotion fallback after UI failure.")
        if not self.can_use_api_confirm_fallback(ui_failure=True):
            raise AssertionError("Current execution mode forbids API brief confirmation fallback after UI failure.")
        return fallback(self)

    def attempt_outline_review(
        self,
        ui_attempt: UIAttemptCallback,
        fallback: StageCallback,
    ) -> Any:
        if ui_attempt(self):
            return "ui"
        self.record_diagnostic("outline_tab_route_failure", stage="outline_review")
        self.record_fallback(
            "api_promote_outline",
            stage="outline_review",
            reason="outline_tab_not_visible_after_ui_click",
            step_id="10_outline_tab_route_failure",
        )
        if not self.can_use_api_promote_fallback(ui_failure=True):
            raise AssertionError("Current execution mode forbids API outline promotion fallback after UI failure.")
        if not self.can_use_api_confirm_fallback(ui_failure=True):
            raise AssertionError("Current execution mode forbids API outline confirmation fallback after UI failure.")
        return fallback(self)

    def _stage_callbacks(self) -> list[tuple[str, StageCallback | None]]:
        return [
            ("create_project", self.create_project),
            ("intake", self.intake),
            ("brief_review", self.brief_review),
            ("outline_review", self.outline_review),
            ("freeze_and_build", self.freeze_and_build),
        ]

    def run(self) -> list[Any]:
        results: list[Any] = []
        for stage_name, stage_callback in self._stage_callbacks():
            if stage_callback is None:
                raise RuntimeError(f"FullGameCreationRunner requires a {stage_name} stage callback.")
            results.append(stage_callback(self))
        return results
