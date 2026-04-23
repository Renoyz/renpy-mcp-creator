"""Utilities for managing Ren'Py project workspaces."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from renpy_mcp.blueprint.models import (
    ChapterOutline,
    ChapterStyleProfiles,
    PipelineStage,
    ProjectBlueprint,
    ProjectBrief,
    ProjectMeta,
    ProjectStatus,
    ProjectStyleBible,
    RefinementIntake,
    ScenePackagesSnapshot,
)
from renpy_mcp.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class ProjectListResult:
    """Result of listing projects, including both valid projects and errors."""

    projects: list[ProjectMeta]
    errors: list[str]


class ProjectManager:
    """Manage project directories and metadata."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.workspace.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, name: str) -> Path:
        """Return the absolute project directory path (no I/O)."""
        return self.settings.workspace / name

    def _meta_dir(self, project_dir: Path) -> Path:
        """Return the meta directory path for a project."""
        return project_dir / "meta"

    def _init_project_meta(self, project_dir: Path) -> None:
        """Create meta/ and a default project.json for a newly-initialized project."""
        meta_dir = self._meta_dir(project_dir)
        meta_dir.mkdir(parents=True, exist_ok=True)
        project_json = meta_dir / "project.json"
        if not project_json.exists():
            default_meta = ProjectMeta(
                name=project_dir.name,
                path=project_dir,
                status=ProjectStatus.DRAFT,
                pipeline_stage=PipelineStage.IDLE,
                chapter_count=0,
                scene_count=0,
                confirmed_scenes=0,
            )
            project_json.write_text(
                default_meta.model_dump_json(indent=2, by_alias=False),
                encoding="utf-8",
            )

    def list_projects(self) -> ProjectListResult:
        """Return metadata for all known projects.

        Prefers meta/project.json when available and falls back to a
        compatibility stub for legacy projects without metadata.
        Corrupt metadata files are collected in ``errors`` rather than
        silently skipped, so callers can distinguish valid, legacy, and
        corrupt projects.
        """
        projects: list[ProjectMeta] = []
        errors: list[str] = []
        for path in sorted(self.settings.workspace.glob("*")):
            if path.is_dir():
                try:
                    meta = self.read_project_meta(path.name)
                except ValueError as exc:
                    errors.append(str(exc))
                    continue
                if meta is not None:
                    projects.append(meta)
                else:
                    # Legacy fallback: synthesise a compatible stub.
                    projects.append(
                        ProjectMeta(
                            name=path.name,
                            path=path,
                            status=ProjectStatus.DRAFT,
                            pipeline_stage=PipelineStage.IDLE,
                            chapter_count=0,
                            scene_count=0,
                            confirmed_scenes=0,
                        )
                    )
        return ProjectListResult(projects=projects, errors=errors)

    def ensure_project_dir(self, name: str) -> Path:
        """Return absolute project directory, creating it if necessary."""
        project_dir = self._project_dir(name)
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir

    def delete_project(self, name: str) -> None:
        """Remove a project directory."""
        project_dir = self._project_dir(name)
        if project_dir.exists():
            shutil.rmtree(project_dir)

    def copy_template(self, destination: Path, template_dir: Path | None) -> None:
        """Copy a template project into place."""
        if template_dir is None:
            if destination.exists():
                shutil.rmtree(destination)
            (destination / "game").mkdir(parents=True, exist_ok=True)
            (destination / "game" / "script.rpy").write_text(
                "label start:\n    \"Hello from the Ren'Py MCP server!\"\n",
                encoding="utf-8",
            )
            self._init_project_meta(destination)
            return

        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(template_dir, destination)
        self._init_project_meta(destination)

    def find_template(self, template_name: str) -> Path | None:
        """Return an absolute path to the requested template, if present."""
        built_in = (
            Path(__file__).resolve().parent.parent / "templates" / template_name
        )
        if built_in.exists():
            return built_in
        return None

    # -----------------------------------------------------------------------
    # Meta persistence
    # -----------------------------------------------------------------------

    def read_project_meta(self, name: str) -> ProjectMeta | None:
        """Read meta/project.json for a project, if it exists.

        Returns ``None`` only when the metadata file is missing.  Existing
        files that are unreadable or fail validation raise ``ValueError``
        so that callers can distinguish "no meta" from "broken meta".
        """
        project_json = self._project_dir(name) / "meta" / "project.json"
        if not project_json.exists():
            return None
        try:
            data = json.loads(project_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Project {name!r} has corrupt meta/project.json: invalid JSON"
            ) from exc
        except OSError as exc:
            raise ValueError(
                f"Project {name!r} has unreadable meta/project.json"
            ) from exc

        # Ensure the path field is a Path object.
        data["path"] = self._project_dir(name)
        try:
            return ProjectMeta.model_validate(data)
        except ValueError as exc:
            raise ValueError(
                f"Project {name!r} has invalid meta/project.json: validation failed"
            ) from exc

    def write_project_meta(self, name: str, meta: ProjectMeta) -> None:
        """Persist meta/project.json for a project.

        The ``updated_at`` field is automatically refreshed to the current
        UTC time so callers do not need to manage it manually.
        """
        from datetime import datetime

        meta_dir = self._project_dir(name) / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        project_json = meta_dir / "project.json"
        # Update the path to the canonical project directory and refresh timestamp.
        updated = meta.model_copy(
            update={
                "path": self._project_dir(name),
                "updated_at": datetime.utcnow(),
            }
        )
        project_json.write_text(
            updated.model_dump_json(indent=2, by_alias=False),
            encoding="utf-8",
        )

    # -----------------------------------------------------------------------
    # Blueprint persistence (real YAML via PyYAML)
    # -----------------------------------------------------------------------

    def read_blueprint(self, name: str) -> ProjectBlueprint | None:
        """Read meta/blueprint.yaml for a project, if it exists.

        Returns ``None`` when the file is missing.  Existing files that are
        unreadable, syntactically invalid, empty, or fail model validation
        raise ``ValueError`` with a clear message so callers have a stable
        exception contract.
        """
        blueprint_path = self._project_dir(name) / "meta" / "blueprint.yaml"
        if not blueprint_path.exists():
            return None
        try:
            text = blueprint_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(
                f"Cannot read blueprint.yaml for project {name!r}"
            ) from exc

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(
                f"blueprint.yaml for project {name!r} contains invalid YAML"
            ) from exc

        if data is None:
            raise ValueError(
                f"blueprint.yaml for project {name!r} is empty or invalid"
            )

        try:
            return ProjectBlueprint.model_validate(data)
        except ValidationError as exc:
            raise ValueError(
                f"blueprint.yaml for project {name!r} has an invalid structure"
            ) from exc

    def write_blueprint(self, name: str, blueprint: ProjectBlueprint) -> None:
        """Persist meta/blueprint.yaml for a project as real YAML."""
        meta_dir = self._project_dir(name) / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        blueprint_path = meta_dir / "blueprint.yaml"
        blueprint_path.write_text(
            yaml.safe_dump(
                blueprint.model_dump(mode="json", by_alias=False),
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

    # -----------------------------------------------------------------------
    # Index persistence
    # -----------------------------------------------------------------------

    def read_project_index(self, name: str) -> dict[str, Any] | None:
        """Read meta/index.json for a project, if it exists."""
        index_path = self._project_dir(name) / "meta" / "index.json"
        if not index_path.exists():
            return None
        try:
            return json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def write_project_index(self, name: str, index: dict[str, Any]) -> None:
        """Persist meta/index.json for a project."""
        meta_dir = self._project_dir(name) / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        index_path = meta_dir / "index.json"
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # -----------------------------------------------------------------------
    # Style bible persistence
    # -----------------------------------------------------------------------

    def read_style_bible(self, name: str) -> ProjectStyleBible | None:
        """Read meta/style_bible.json for a project.

        Returns ``None`` only when the file is missing.  Existing files that are
        unreadable, syntactically invalid, or fail model validation raise
        ``ValueError`` so callers can distinguish "no config" from "broken config".
        """
        path = self._project_dir(name) / "meta" / "style_bible.json"
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Cannot read style_bible.json for project {name!r}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"style_bible.json for project {name!r} contains invalid JSON") from exc
        try:
            return ProjectStyleBible.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"style_bible.json for project {name!r} has an invalid structure") from exc

    def write_style_bible(self, name: str, bible: ProjectStyleBible) -> None:
        """Persist meta/style_bible.json for a project."""
        meta_dir = self._project_dir(name) / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        path = meta_dir / "style_bible.json"
        path.write_text(
            json.dumps(bible.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # -----------------------------------------------------------------------
    # Chapter style profiles persistence
    # -----------------------------------------------------------------------

    def read_chapter_style_profiles(self, name: str) -> ChapterStyleProfiles | None:
        """Read meta/chapter_style_profiles.json for a project.

        Returns ``None`` only when the file is missing.  Existing files that are
        unreadable, syntactically invalid, or fail model validation raise
        ``ValueError`` so callers can distinguish "no config" from "broken config".
        """
        path = self._project_dir(name) / "meta" / "chapter_style_profiles.json"
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Cannot read chapter_style_profiles.json for project {name!r}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"chapter_style_profiles.json for project {name!r} contains invalid JSON") from exc
        try:
            return ChapterStyleProfiles.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"chapter_style_profiles.json for project {name!r} has an invalid structure") from exc

    def write_chapter_style_profiles(self, name: str, profiles: ChapterStyleProfiles) -> None:
        """Persist meta/chapter_style_profiles.json for a project."""
        meta_dir = self._project_dir(name) / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        path = meta_dir / "chapter_style_profiles.json"
        path.write_text(
            json.dumps(profiles.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # -----------------------------------------------------------------------
    # Scene packages persistence
    # -----------------------------------------------------------------------

    def read_scene_packages(self, name: str) -> ScenePackagesSnapshot | None:
        """Read meta/scene_packages.json for a project, if it exists.

        Returns ``None`` when the file is missing.  Existing unreadable or
        invalid files raise ``ValueError``.
        """
        path = self._project_dir(name) / "meta" / "scene_packages.json"
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Cannot read scene_packages.json for project {name!r}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"scene_packages.json for project {name!r} contains invalid JSON") from exc
        try:
            return ScenePackagesSnapshot.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"Project {name!r} has invalid meta/scene_packages.json") from exc

    def write_scene_packages(self, name: str, snapshot: ScenePackagesSnapshot) -> None:
        """Persist meta/scene_packages.json for a project."""
        meta_dir = self._project_dir(name) / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        path = meta_dir / "scene_packages.json"
        path.write_text(
            snapshot.model_dump_json(indent=2, by_alias=False),
            encoding="utf-8",
        )

    # -----------------------------------------------------------------------
    # Prototype manifest persistence
    # -----------------------------------------------------------------------

    def read_prototype_manifest(self, name: str) -> PrototypeManifest | None:
        """Read meta/prototype_manifest.json for a project, if it exists.

        Returns ``None`` when the file is missing.  Existing unreadable or
        invalid files raise ``ValueError`` so callers can distinguish "no
        manifest" from "broken manifest".
        """
        from renpy_mcp.blueprint.models import PrototypeManifest

        path = self._project_dir(name) / "meta" / "prototype_manifest.json"
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Cannot read prototype_manifest.json for project {name!r}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"prototype_manifest.json for project {name!r} contains invalid JSON") from exc
        try:
            return PrototypeManifest.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"Project {name!r} has invalid meta/prototype_manifest.json") from exc

    def write_prototype_manifest(self, name: str, manifest: PrototypeManifest) -> None:
        """Persist meta/prototype_manifest.json for a project."""
        meta_dir = self._project_dir(name) / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        path = meta_dir / "prototype_manifest.json"
        path.write_text(
            manifest.model_dump_json(indent=2, by_alias=False),
            encoding="utf-8",
        )

    # -----------------------------------------------------------------------
    # Project brief persistence
    # -----------------------------------------------------------------------

    def read_project_brief(self, name: str) -> ProjectBrief | None:
        """Read meta/project_brief.json for a project, if it exists.

        Returns ``None`` when the file is missing.  Existing unreadable or
        invalid files raise ``ValueError`` so callers can distinguish "no
        brief" from "broken brief".
        """
        path = self._project_dir(name) / "meta" / "project_brief.json"
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Cannot read project_brief.json for project {name!r}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"project_brief.json for project {name!r} contains invalid JSON") from exc
        try:
            return ProjectBrief.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"project_brief.json for project {name!r} has an invalid structure") from exc

    def write_project_brief(self, name: str, brief: ProjectBrief) -> None:
        """Persist meta/project_brief.json for a project."""
        meta_dir = self._project_dir(name) / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        path = meta_dir / "project_brief.json"
        path.write_text(
            brief.model_dump_json(indent=2, by_alias=False),
            encoding="utf-8",
        )

    # -----------------------------------------------------------------------
    # Chapter outline persistence
    # -----------------------------------------------------------------------

    def read_chapter_outline(self, name: str) -> ChapterOutline | None:
        """Read meta/chapter_outline.json for a project, if it exists.

        Returns ``None`` when the file is missing.  Existing unreadable or
        invalid files raise ``ValueError`` so callers can distinguish "no
        outline" from "broken outline".
        """
        path = self._project_dir(name) / "meta" / "chapter_outline.json"
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Cannot read chapter_outline.json for project {name!r}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"chapter_outline.json for project {name!r} contains invalid JSON") from exc
        try:
            return ChapterOutline.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"chapter_outline.json for project {name!r} has an invalid structure") from exc

    def write_chapter_outline(self, name: str, outline: ChapterOutline) -> None:
        """Persist meta/chapter_outline.json for a project."""
        meta_dir = self._project_dir(name) / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        path = meta_dir / "chapter_outline.json"
        path.write_text(
            outline.model_dump_json(indent=2, by_alias=False),
            encoding="utf-8",
        )

    # -----------------------------------------------------------------------
    # Refinement intake persistence
    # -----------------------------------------------------------------------

    def read_refinement_intake(self, name: str) -> RefinementIntake | None:
        """Read meta/refinement_intake.json for a project, if it exists.

        Returns ``None`` when the file is missing. Existing unreadable or
        invalid files raise ``ValueError`` so callers can distinguish "no
        intake" from "broken intake".
        """
        path = self._project_dir(name) / "meta" / "refinement_intake.json"
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Cannot read refinement_intake.json for project {name!r}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"refinement_intake.json for project {name!r} contains invalid JSON") from exc
        try:
            return RefinementIntake.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"refinement_intake.json for project {name!r} has an invalid structure") from exc

    def write_refinement_intake(self, name: str, intake: RefinementIntake) -> None:
        """Persist meta/refinement_intake.json for a project."""
        meta_dir = self._project_dir(name) / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        path = meta_dir / "refinement_intake.json"
        path.write_text(
            intake.model_dump_json(indent=2, by_alias=False),
            encoding="utf-8",
        )
