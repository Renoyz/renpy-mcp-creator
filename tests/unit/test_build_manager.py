"""Tests for BuildManager."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from renpy_mcp.models import BuildRequest
from renpy_mcp.services.build_manager import BuildManager


class _FakeSubprocess:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode
        self.stdout = None

    async def wait(self):
        return self.returncode


@pytest.fixture
def settings(tmp_path: Path):
    from renpy_mcp.config import Settings

    return Settings().model_copy(
        update={"workspace": tmp_path / "workspace", "renpy_sdk_path": None}
    )


@pytest.fixture
def build_manager(settings):
    return BuildManager(settings)


class TestBuildManager:
    @pytest.mark.asyncio
    async def test_build_web_command_stays_the_same(self, settings, tmp_path):
        settings.workspace.mkdir(parents=True, exist_ok=True)
        project_dir = settings.workspace / "web_project"
        project_dir.mkdir()
        (project_dir / "game").mkdir()

        sdk_path = tmp_path / "sdk_web"
        sdk_path.mkdir()
        (sdk_path / "renpy.sh").touch()
        (sdk_path / "web").mkdir()

        settings.renpy_sdk_path = sdk_path

        from renpy_mcp.services import build_manager as bm

        recorded: dict[str, list[str]] = {}

        async def fake_create_subprocess_exec(*command, **kwargs):
            recorded["command"] = list(command)
            return _FakeSubprocess()

        with (
            patch.object(
                bm.LocalRenpyToolchain, "_stream_log", AsyncMock()
            ) as mock_stream,
            patch.object(
                bm.asyncio, "create_subprocess_exec", AsyncMock(side_effect=fake_create_subprocess_exec)
            ) as mock_subprocess,
        ):
            result = await BuildManager(settings).build(
                BuildRequest(project_name=project_dir.name, target="web")
            )
        mock_subprocess.assert_awaited_once()
        mock_stream.assert_awaited_once()

        assert result.success is True
        assert recorded["command"][:3] == [
            str((sdk_path / "renpy.sh").resolve()),
            str((sdk_path / "launcher").resolve()),
            "distribute",
        ]
        assert recorded["command"][3:] == [
            "--package",
            "web",
            "--destination",
            str((project_dir.parent / f"{project_dir.name}-dists").resolve()),
            str(project_dir.resolve()),
        ]

    @pytest.mark.asyncio
    async def test_build_windows_command_and_output_preference(self, settings, tmp_path):
        settings.workspace.mkdir(parents=True, exist_ok=True)
        project_dir = settings.workspace / "win_project"
        project_dir.mkdir()
        (project_dir / "game").mkdir()

        sdk_path = tmp_path / "sdk_windows"
        sdk_path.mkdir()
        (sdk_path / "renpy.exe").touch()

        settings.renpy_sdk_path = sdk_path
        destination = project_dir.parent / f"{project_dir.name}-dists"
        destination.mkdir()
        (destination / f"{project_dir.name}-pc.zip").write_bytes(b"pc")
        (destination / f"{project_dir.name}-win.zip").write_text("win")
        (destination / f"{project_dir.name}-windows.zip").write_text("windows")
        (destination / "dist").mkdir()

        from renpy_mcp.services import build_manager as bm

        async def fake_create_subprocess_exec(*command, **kwargs):
            return _FakeSubprocess()

        with patch.object(
            bm.asyncio, "create_subprocess_exec",
            AsyncMock(side_effect=fake_create_subprocess_exec),
        ) as mock_subprocess, patch.object(
            bm.LocalRenpyToolchain, "_stream_log", AsyncMock()
        ) as mock_stream:
            result = await BuildManager(settings).build(
                BuildRequest(project_name=project_dir.name, target="windows")
            )
        mock_subprocess.assert_awaited_once()
        mock_stream.assert_awaited_once()

        assert result.success is True
        assert result.target == "windows"
        assert result.output_path == destination / f"{project_dir.name}-pc.zip"

    @pytest.mark.asyncio
    async def test_build_windows_output_uses_dist_dir_or_build_dest_fallback(self, settings, tmp_path):
        settings.workspace.mkdir(parents=True, exist_ok=True)
        project_dir = settings.workspace / "win_project_fallback"
        project_dir.mkdir()
        (project_dir / "game").mkdir()

        sdk_path = tmp_path / "sdk_windows"
        sdk_path.mkdir()
        (sdk_path / "renpy.exe").touch()
        settings.renpy_sdk_path = sdk_path

        destination = project_dir.parent / f"{project_dir.name}-dists"
        destination.mkdir()
        (destination / "dist").mkdir()

        from renpy_mcp.services import build_manager as bm

        async def fake_create_subprocess_exec(*command, **kwargs):
            return _FakeSubprocess()

        with patch.object(
            bm.asyncio, "create_subprocess_exec",
            AsyncMock(side_effect=fake_create_subprocess_exec),
        ) as mock_subprocess, patch.object(
            bm.LocalRenpyToolchain, "_stream_log", AsyncMock()
        ) as mock_stream:
            result = await BuildManager(settings).build(
                BuildRequest(project_name=project_dir.name, target="windows")
            )
        mock_subprocess.assert_awaited_once()
        mock_stream.assert_awaited_once()

        assert result.success is True
        assert result.output_path == destination / "dist"

        destination.joinpath("dist").rmdir()
        with patch.object(
            bm.asyncio, "create_subprocess_exec",
            AsyncMock(side_effect=fake_create_subprocess_exec),
        ) as mock_subprocess, patch.object(
            bm.LocalRenpyToolchain, "_stream_log", AsyncMock()
        ) as mock_stream:
            result = await BuildManager(settings).build(
                BuildRequest(project_name=project_dir.name, target="windows")
            )
        mock_subprocess.assert_awaited_once()
        mock_stream.assert_awaited_once()

        assert result.success is True
        assert result.output_path == destination

    def test_build_command_windows_uses_pc_package(self, settings, tmp_path):
        sdk_path = tmp_path / "sdk_cmd_windows"
        sdk_path.mkdir()
        (sdk_path / "renpy.exe").write_text("")
        (sdk_path / "launcher").write_text("")
        from renpy_mcp.services.build_manager import LocalRenpyToolchain

        toolchain = LocalRenpyToolchain(sdk_path)
        command = toolchain._build_command(
            project_dir=tmp_path / "project",
            destination=str((tmp_path / "project-dists").resolve()),
            force_rebuild=True,
            target="windows",
        )
        assert command == [
            str((sdk_path / "renpy.exe").resolve()),
            str((sdk_path / "launcher").resolve()),
            "distribute",
            "--package",
            "pc",
            "--force-rebuild",
            "--destination",
            str((tmp_path / "project-dists").resolve()),
            str((tmp_path / "project").resolve()),
        ]

    @pytest.mark.asyncio
    async def test_build_missing_executable_reports_windows_error(self, settings, tmp_path):
        settings.workspace.mkdir(parents=True, exist_ok=True)
        project_dir = settings.workspace / "win_project_no_exe"
        project_dir.mkdir()
        (project_dir / "game").mkdir()
        from renpy_mcp.services.build_manager import LocalRenpyToolchain

        settings.renpy_sdk_path = tmp_path / "missing_exe"
        settings.renpy_sdk_path.mkdir()

        result = await LocalRenpyToolchain(settings.renpy_sdk_path).build(
            project_dir=project_dir,
            request=BuildRequest(project_name=project_dir.name, target="windows"),
        )

        assert result.success is False
        assert result.target == "windows"
        assert "Ren'Py executable not found under" in result.error

    def test_build_request_defaults(self):
        req = BuildRequest(project_name="test_vn")
        assert req.project_name == "test_vn"
        assert req.target == "web"
        assert req.force_rebuild is False

    @pytest.mark.asyncio
    async def test_build_missing_project(self, build_manager):
        req = BuildRequest(project_name="missing")
        result = await build_manager.build(req)
        assert result.success is False
        assert "not found" in result.error

    def test_build_command_windows_forces_targeted_build_args(self, tmp_path):
        sdk_path = tmp_path / "sdk_cmd_force"
        sdk_path.mkdir()
        (sdk_path / "renpy.sh").write_text("")
        (sdk_path / "launcher").write_text("")
        from renpy_mcp.services.build_manager import LocalRenpyToolchain

        command = LocalRenpyToolchain(sdk_path)._build_command(
            project_dir=tmp_path / "project",
            destination=str((tmp_path / "project-dists").resolve()),
            force_rebuild=False,
            target="windows",
        )
        assert "--package" in command
        package_index = command.index("--package") + 1
        assert command[package_index] in {"pc", "windows", "win"}

    @pytest.mark.asyncio
    async def test_build_no_toolchain(self, settings, tmp_path):
        settings = settings.model_copy(update={"renpy_sdk_path": None})
        bm = BuildManager(settings)

        project_dir = settings.workspace / "test_vn"
        project_dir.mkdir(parents=True)
        (project_dir / "game").mkdir()

        req = BuildRequest(project_name="test_vn")
        result = await bm.build(req)
        assert result.success is False
        assert "No usable Ren'Py SDK found" in result.error


def test_prototype_build_route_honors_windows_target_under_mock(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from renpy_mcp.blueprint.models import PrototypeManifest
    from renpy_mcp.config import RenPyConfig, get_settings
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.web.fastapi_app import create_app, set_config

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)
    monkeypatch.setenv("RENPY_MCP_MOCK_BUILD", "1")

    import renpy_mcp.web.fastapi_app as fa

    dashboard_dir = tmp_path / "dashboard_dist"
    dashboard_dir.mkdir()
    (dashboard_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(fa, "DASHBOARD_DIR", dashboard_dir)
    monkeypatch.setattr(fa, "_last_build_results", {})
    set_config(RenPyConfig(sdk_path=Path("."), project_path=tmp_path))

    client = TestClient(create_app())
    project_name = "proto_windows"
    assert client.post("/api/projects", json={"name": project_name}).status_code == 200

    pm = ProjectManager(settings)
    project_dir = tmp_path / project_name
    proto_path = project_dir / "game" / "prototype_ch1.rpy"
    proto_path.write_text("label proto_start:\n    return\n", encoding="utf-8")
    (project_dir / "game" / "script.rpy").write_text(
        "label start:\n"
        "    # PROTOTYPE START (managed)\n"
        "    call proto_start\n"
        "    return\n"
        "    # PROTOTYPE END (managed)\n",
        encoding="utf-8",
    )
    pm.write_project_index(
        project_name,
        {
            "scenes": {
                "s1": {
                    "source": "prototype",
                    "scene_id": "s1",
                    "file_path": "game/prototype_ch1.rpy",
                    "label": "proto_start",
                }
            }
        },
    )
    pm.write_prototype_manifest(
        project_name,
        PrototypeManifest(
            mode="single_chapter",
            entry_label="proto_start",
            entry_file="game/prototype_ch1.rpy",
            chapter_ids=["ch1"],
            script_files=["game/prototype_ch1.rpy"],
        ),
    )

    web_response = client.post(f"/api/projects/{project_name}/prototype/build", json={"target": "web"})
    assert web_response.status_code == 200, web_response.text
    web_status = client.get(f"/api/projects/{project_name}/build/status").json()
    assert web_status["target"] == "web"
    assert web_status["previewable"] is True

    response = client.post(f"/api/projects/{project_name}/prototype/build", json={"target": "windows"})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["target"] == "windows"
    assert payload["output_path"].endswith(f"{project_name}-windows")
    assert not Path(payload["output_path"]).is_absolute()
    assert payload["log_path"] is None
    status = client.get(f"/api/projects/{project_name}/build/status").json()
    assert status["target"] == "windows"
    assert status["previewable"] is True
    assert status["targets"]["web"]["previewable"] is True
    assert status["targets"]["windows"]["previewable"] is False
    assert not Path(status["output_path"]).is_absolute()
    assert not Path(status["targets"]["web"]["output_path"]).is_absolute()
    assert str(tmp_path) not in status["message"]
    assert str(tmp_path) not in status["targets"]["web"]["message"]
