"""Application settings with v1.1.2 backward compatibility."""

import contextvars
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv()

# Context-local override for the active project path (request / WebSocket scoped)
_current_project_path: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "current_project_path", default=None
)


@contextmanager
def set_current_project_path(path: Path | None):
    token = _current_project_path.set(path)
    try:
        yield
    finally:
        _current_project_path.reset(token)


class Settings(BaseSettings):
    """Application configuration for unified-design."""

    workspace: Path = Field(
        default_factory=lambda: Path.home() / ".renpy-mcp" / "workspace",
        description="Directory for storing projects",
    )
    port: int = Field(default=8080, description="HTTP server port")
    renpy_sdk_path: Path | None = Field(
        default=None,
        description="Path to Ren'Py SDK directory",
        validation_alias="RENPY_SDK_PATH",
    )
    renpy_sdk_mirror: str | None = Field(
        default=None,
        description="Custom mirror URL for Ren'Py SDK downloads",
    )

    # AI model API keys
    anthropic_api_key: str | None = Field(default=None)
    deepseek_api_key: str | None = Field(default=None)
    qwen_api_key: str | None = Field(default=None)
    jimeng_api_key: str | None = Field(default=None)
    tongyi_api_key: str | None = Field(default=None)

    # Gemini configuration (from banjtheman/renpy_mcp_server)
    gemini_api_key: str | None = Field(default=None)
    gemini_image_model: str = Field(default="gemini-2.5-flash-image")
    gemini_text_model: str = Field(default="gemini-2.0-flash-exp")
    default_template: str = Field(default="basic")

    # DashScope image generation model override
    dashscope_image_model: str = Field(
        default="qwen-image-2.1",
        description="DashScope image generation model. Default changed from qwen-image-2.0-pro to conserve quota.",
    )
    session_secret: str | None = Field(
        default=None,
        description="Secret key for HTTP session signing. Falls back to SESSION_SECRET env var, then a random token generated at startup.",
    )

    model_config = {"env_prefix": "RENPY_MCP_", "case_sensitive": False}


# Global settings instance (lazy loading pattern)
_settings: Settings | None = None


def get_settings() -> Settings:
    """Return cached settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# -----------------------------------------------------------------------------
# v1.1.2 backward-compatible config
# -----------------------------------------------------------------------------


@dataclass
class RenPyConfig:
    """Configuration for RenPy SDK and project paths (legacy from v1.1.2)."""

    sdk_path: Path = field(default_factory=lambda: _legacy_default_sdk_path())
    _project_path: Path | None = field(default=None, repr=False)

    def __init__(self, sdk_path: Path | None = None, project_path: Path | None = None):
        object.__setattr__(
            self, "sdk_path", sdk_path if sdk_path is not None else _legacy_default_sdk_path()
        )
        object.__setattr__(self, "_project_path", project_path)

    @property
    def project_path(self) -> Path | None:
        ctx_path = _current_project_path.get()
        if ctx_path is not None:
            return ctx_path
        return self._project_path

    @project_path.setter
    def project_path(self, value: Path | None) -> None:
        object.__setattr__(self, "_project_path", value)

    @property
    def renpy_exe(self) -> Path:
        """Path to the RenPy executable."""
        if os.name == "nt":
            return self.sdk_path / "renpy.exe"
        return self.sdk_path / "renpy.sh"

    def validate(self) -> list[str]:
        """Return list of validation errors, empty if valid."""
        errors = []
        if not self.sdk_path.exists():
            errors.append(f"SDK path does not exist: {self.sdk_path}")
        elif not self.renpy_exe.exists():
            errors.append(f"RenPy executable not found: {self.renpy_exe}")
        if self.project_path and not self.project_path.exists():
            errors.append(f"Project path does not exist: {self.project_path}")
        return errors


def _legacy_default_sdk_path() -> Path:
    """Resolve default SDK path from Settings or environment."""
    settings = get_settings()
    if settings.renpy_sdk_path:
        return settings.renpy_sdk_path
    env = os.environ.get("RENPY_SDK_PATH")
    if env:
        return Path(env)
    return Path(".")


def resolve_project_dir(name: str) -> Path | None:
    """Resolve a project directory under the workspace, guarding against path traversal."""
    settings = get_settings()
    try:
        project_dir = (settings.workspace / name).resolve()
        workspace = settings.workspace.resolve()
        project_dir.relative_to(workspace)
    except (ValueError, RuntimeError):
        return None
    if not (project_dir / "game").exists():
        return None
    return project_dir
