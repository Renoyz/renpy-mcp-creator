"""Tests for SdkProvisioner."""

from pathlib import Path

import pytest

from renpy_mcp.config import Settings
from renpy_mcp.services.sdk_provisioner import SdkProvisioner


@pytest.fixture
def temp_settings(tmp_path: Path) -> Settings:
    s = Settings(workspace=tmp_path / "workspace")
    s.renpy_sdk_path = None
    return s


def test_is_sdk_ready_when_exe_exists(temp_settings: Settings, tmp_path: Path) -> None:
    sdk_dir = tmp_path / "sdk"
    exe_name = "renpy.exe" if __import__("os").name == "nt" else "renpy.sh"
    (sdk_dir / exe_name).parent.mkdir(parents=True, exist_ok=True)
    (sdk_dir / exe_name).write_text("fake", encoding="utf-8")

    provisioner = SdkProvisioner(temp_settings)
    assert provisioner.is_sdk_ready(sdk_dir) is True


def test_is_sdk_ready_when_exe_missing(temp_settings: Settings, tmp_path: Path) -> None:
    sdk_dir = tmp_path / "sdk"
    sdk_dir.mkdir()
    provisioner = SdkProvisioner(temp_settings)
    assert provisioner.is_sdk_ready(sdk_dir) is False


def test_find_sdk_root_single_top_level_dir(temp_settings: Settings, tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    sdk = extracted / "renpy-8.3.4-sdk"
    exe_name = "renpy.exe" if __import__("os").name == "nt" else "renpy.sh"
    (sdk / exe_name).parent.mkdir(parents=True, exist_ok=True)
    (sdk / exe_name).write_text("fake", encoding="utf-8")

    provisioner = SdkProvisioner(temp_settings)
    assert provisioner._find_sdk_root(extracted) == sdk


def test_find_sdk_root_current_dir(temp_settings: Settings, tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    exe_name = "renpy.exe" if __import__("os").name == "nt" else "renpy.sh"
    (extracted / exe_name).parent.mkdir(parents=True, exist_ok=True)
    (extracted / exe_name).write_text("fake", encoding="utf-8")

    provisioner = SdkProvisioner(temp_settings)
    assert provisioner._find_sdk_root(extracted) == extracted


def test_find_sdk_root_nested_one_level(temp_settings: Settings, tmp_path: Path) -> None:
    extracted = tmp_path / "extracted"
    nested = extracted / "subdir" / "renpy-sdk"
    exe_name = "renpy.exe" if __import__("os").name == "nt" else "renpy.sh"
    (nested / exe_name).parent.mkdir(parents=True, exist_ok=True)
    (nested / exe_name).write_text("fake", encoding="utf-8")

    provisioner = SdkProvisioner(temp_settings)
    assert provisioner._find_sdk_root(extracted) == nested


@pytest.mark.asyncio
async def test_ensure_sdk_skips_when_ready(temp_settings: Settings, tmp_path: Path) -> None:
    sdk_dir = tmp_path / "sdk"
    exe_name = "renpy.exe" if __import__("os").name == "nt" else "renpy.sh"
    (sdk_dir / exe_name).parent.mkdir(parents=True, exist_ok=True)
    (sdk_dir / exe_name).write_text("fake", encoding="utf-8")

    temp_settings.renpy_sdk_path = sdk_dir
    provisioner = SdkProvisioner(temp_settings)
    result = await provisioner.ensure_sdk()
    assert result == sdk_dir.resolve()
