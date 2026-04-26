"""Data models used by the Ren'Py MCP server."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


class BuildRequest(BaseModel):
    """Parameters controlling a build request."""

    project_name: str
    target: str = "web"
    force_rebuild: bool = False


class BuildResult(BaseModel):
    """Result payload returned from a build run."""

    project_name: str
    target: str
    success: bool
    output_path: Optional[Path] = None
    log_path: Optional[Path] = None
    error: Optional[str] = None


class ImageGenerationResult(BaseModel):
    """Metadata about generated image files."""

    success: bool
    prompt: str
    image_type: str
    files: List[Path] = Field(default_factory=list)
    primary_file: Optional[Path] = None
    error: Optional[str] = None
