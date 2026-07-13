"""Contracts for reproducible desktop packaging scripts."""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_node_build_scripts_install_from_lockfiles() -> None:
    for relative_path in (
        "packaging/scripts/build-dashboard.ps1",
        "packaging/scripts/build-electron.ps1",
    ):
        script = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "npm ci" in script
        assert "npm install" not in script


def test_backend_build_uses_locked_pyinstaller_dependency() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    packaging_dependencies = pyproject["project"]["optional-dependencies"]["packaging"]
    script = (REPO_ROOT / "packaging/scripts/build-backend.ps1").read_text(encoding="utf-8")

    assert any(dependency.startswith("pyinstaller") for dependency in packaging_dependencies)
    assert "uv run --extra packaging python -m PyInstaller" in script
