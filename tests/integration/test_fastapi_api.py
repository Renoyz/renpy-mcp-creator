"""Integration tests for FastAPI routes."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from renpy_mcp.config import RenPyConfig
from renpy_mcp.web.fastapi_app import create_app, set_config


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a minimal Ren'Py project structure."""
    project_dir = tmp_path / "fastapi_test_vn"
    game_dir = project_dir / "game"
    game_dir.mkdir(parents=True)
    lines = ["label start:", "    scene bg room", '    "Hello."', "    return", ""]
    (game_dir / "script.rpy").write_text("\n".join(lines), encoding="utf-8")
    (game_dir / "options.rpy").write_text(
        "define config.name = _('Test VN')\n",
        encoding="utf-8",
    )
    return project_dir


@pytest.fixture
def client(temp_project: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    """Provide a TestClient with project config injected."""
    from renpy_mcp.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", temp_project.parent)

    # Set up temp dashboard dir for hermetic static file tests
    import renpy_mcp.web.fastapi_app as fa

    dashboard_dir = tmp_path / "dashboard_dist"
    dashboard_dir.mkdir()
    (dashboard_dir / "index.html").write_text("<html><body>dashboard</body></html>", encoding="utf-8")
    (dashboard_dir / "assets").mkdir()
    (dashboard_dir / "assets" / "test.js").write_text("console.log('test');", encoding="utf-8")
    monkeypatch.setattr(fa, "DASHBOARD_DIR", dashboard_dir)
    monkeypatch.setattr(fa, "_last_build_results", {})

    config = RenPyConfig(sdk_path=Path("."), project_path=temp_project)
    set_config(config)
    app = create_app()
    return TestClient(app)


class TestFastApiPages:
    """Smoke tests for page routes."""

    def test_root_redirect(self, client: TestClient):
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == "/dashboard"

    def test_dashboard_page(self, client: TestClient):
        r = client.get("/dashboard")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_dashboard_deep_route_returns_html(self, client: TestClient):
        r = client.get("/dashboard/projects/test-project")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "dashboard" in r.text

    def test_dashboard_story_map_returns_html(self, client: TestClient):
        r = client.get("/dashboard/story-map")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "dashboard" in r.text

    def test_dashboard_static_asset_not_fallback(self, client: TestClient):
        r = client.get("/dashboard/assets/test.js")
        assert r.status_code == 200
        assert "javascript" in r.headers["content-type"] or "js" in r.headers.get("content-type", "")
        assert r.text.strip() == "console.log('test');"

    def test_api_not_affected_by_dashboard_fallback(self, client: TestClient):
        r = client.get("/api/nonexistent")
        # Should return JSON 404 rather than HTML fallback
        assert r.status_code == 404
        assert "application/json" in r.headers["content-type"]

    def test_dashboard_missing_asset_returns_404(self, client: TestClient):
        r = client.get("/dashboard/assets/missing.js")
        assert r.status_code == 404

    def test_dashboard_missing_favicon_returns_404(self, client: TestClient):
        r = client.get("/dashboard/favicon.ico")
        assert r.status_code == 404

    def test_dashboard_traversal_path_returns_404(self, client: TestClient):
        r = client.get("/dashboard/..%5csecret.txt")
        assert r.status_code == 404

    @pytest.mark.parametrize("path", ["/story-map", "/script-editor", "/assets", "/heatmap"])
    def test_legacy_pages_do_not_link_back_to_dashboard(self, client: TestClient, path: str):
        r = client.get(path)
        assert r.status_code == 200
        assert 'href="/dashboard"' not in r.text


class TestFastApiGraph:
    """Tests for /api/graph."""

    def test_graph_returns_nodes_and_edges(self, client: TestClient):
        r = client.get("/api/graph")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data
        assert any(n["id"] == "start" for n in data["nodes"])


class TestFastApiLabels:
    """Tests for /api/labels."""

    def test_labels_list(self, client: TestClient):
        r = client.get("/api/labels")
        assert r.status_code == 200
        data = r.json()
        assert "labels" in data
        assert "start" in data["labels"]


class TestCurrentProject:
    """Tests for current project selection."""

    def test_current_project_selection(self, client: TestClient):
        project_name = "fastapi_select_test"
        # Create project via API in the hermetic workspace
        r = client.post("/api/projects", json={"name": project_name})
        assert r.status_code == 200

        # Before selection, current_project should be None
        r = client.get("/api/projects/current")
        assert r.status_code == 200
        assert r.json()["current_project"] is None

        # Select the project
        r = client.post("/api/projects/select", json={"name": project_name})
        assert r.status_code == 200
        payload = r.json()
        assert payload["success"] is True
        assert payload["current_project"]["name"] == project_name

        # Verify current project is persisted
        r = client.get("/api/projects/current")
        assert r.status_code == 200
        assert r.json()["current_project"]["name"] == project_name


class TestFastApiScript:
    """Tests for script editor API."""

    def test_script_files(self, client: TestClient):
        r = client.get("/api/script/files")
        assert r.status_code == 200
        data = r.json()
        assert "script.rpy" in data["files"]

    def test_script_parse(self, client: TestClient):
        r = client.get("/api/script/parse?file=script.rpy")
        assert r.status_code == 200
        data = r.json()
        assert data["file"] == "script.rpy"
        assert "blocks" in data
        assert any(b["type"] == "label" for b in data["blocks"])

    def test_script_parse_missing_file(self, client: TestClient):
        r = client.get("/api/script/parse?file=missing.rpy")
        assert r.status_code == 404

    def test_script_save(self, client: TestClient):
        payload = {
            "file": "script.rpy",
            "edits": [
                {
                    "line_start": 3,
                    "line_end": 3,
                    "new_lines": ['    "Updated line."'],
                }
            ],
        }
        r = client.post("/api/script/save", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True

        # Verify file was updated
        script_path = client.app  # type: ignore[attr-defined]
        # Re-read via parse
        r2 = client.get("/api/script/parse?file=script.rpy")
        texts = [
            b.get("text", "")
            for b in r2.json()["blocks"]
            if b["type"] in ("dialogue", "narration")
        ]
        assert any("Updated line" in t for t in texts)


class TestAssetFile:
    def test_asset_file_serves_project_image(self, client: TestClient, temp_project: Path):
        image_dir = temp_project / "game" / "images"
        image_dir.mkdir(parents=True)
        (image_dir / "test.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        r = client.get(f"/api/projects/{temp_project.name}/asset-file/images/test.png")
        assert r.status_code == 200
        assert r.headers.get("content-type") == "image/png"

    def test_asset_file_blocks_traversal(self, client: TestClient, temp_project: Path):
        # Create a file outside game_dir so traversal would succeed if not blocked
        (temp_project / "secret.txt").write_text("leak", encoding="utf-8")

        # Use URL-encoded traversal so httpx TestClient does not normalize it away
        r = client.get(f"/api/projects/{temp_project.name}/asset-file/..%2fsecret.txt")
        assert r.status_code == 403

    def test_asset_file_survives_project_switch(self, client: TestClient, tmp_path: Path):
        """An image URL for project A should still work after switching session to project B."""
        # Create project A with an image
        project_a = tmp_path / "project_a"
        game_a = project_a / "game"
        game_a.mkdir(parents=True)
        (game_a / "script.rpy").write_text('label start:\n    return\n', encoding="utf-8")
        (game_a / "options.rpy").write_text("define config.name = _('A')\n", encoding="utf-8")
        (game_a / "images").mkdir(parents=True, exist_ok=True)
        (game_a / "images" / "bg_a.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        # Create project B with no image
        project_b = tmp_path / "project_b"
        game_b = project_b / "game"
        game_b.mkdir(parents=True)
        (game_b / "script.rpy").write_text('label start:\n    return\n', encoding="utf-8")
        (game_b / "options.rpy").write_text("define config.name = _('B')\n", encoding="utf-8")

        # Select project B in session
        r = client.post("/api/projects/select", json={"name": "project_b"})
        assert r.status_code == 200

        # Access project A image via explicit project route (no session dependency)
        r = client.get("/api/projects/project_a/asset-file/images/bg_a.png")
        assert r.status_code == 200
        assert r.headers.get("content-type") == "image/png"

        # Access project B image that does not exist
        r = client.get("/api/projects/project_b/asset-file/images/bg_a.png")
        assert r.status_code == 404

    def test_asset_file_rejects_unknown_project(self, client: TestClient):
        r = client.get("/api/projects/nonexistent_proj/asset-file/images/test.png")
        assert r.status_code == 404
        assert "Project not found" in r.json()["detail"]


class TestBuildAndPreview:
    """Tests for build and preview endpoints."""

    def test_build_project_success(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        from renpy_mcp.models import BuildResult
        from renpy_mcp.services import build_manager as bm

        async def _mock_build(self, request):
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=True,
                output_path=Path("/fake/output"),
            )

        monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

        project_name = "build_success_test"
        client.post("/api/projects", json={"name": project_name})
        client.post("/api/projects/select", json={"name": project_name})

        r = client.post("/api/projects/build", json={"target": "web"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["project_name"] == project_name

    def test_build_project_no_sdk(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        from renpy_mcp.services import build_manager as bm

        monkeypatch.setattr(bm.BuildManager, "_resolve_toolchain", lambda self: None)

        project_name = "build_no_sdk_test"
        client.post("/api/projects", json={"name": project_name})
        client.post("/api/projects/select", json={"name": project_name})

        r = client.post("/api/projects/build", json={"target": "web"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is False
        assert "No usable Ren'Py SDK found" in data["error"]

    def test_preview_project_success(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        from renpy_mcp.config import get_settings
        from renpy_mcp.models import BuildResult
        from renpy_mcp.services import build_manager as bm
        from renpy_mcp.services import preview_manager as pm
        from renpy_mcp.services.preview_manager import PreviewServer

        workspace = get_settings().workspace

        async def _mock_build(self, request):
            output_path = workspace / f"{request.project_name}-dists" / f"{request.project_name}-web"
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / "index.html").write_text("<html></html>", encoding="utf-8")
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=True,
                output_path=output_path,
            )

        async def _mock_start(self, project_name, directory):
            return PreviewServer(
                project_name=project_name,
                directory=directory,
                port=55555,
                process=None,  # type: ignore[arg-type]
            )

        monkeypatch.setattr(bm.BuildManager, "build", _mock_build)
        monkeypatch.setattr(pm.PreviewManager, "start", _mock_start)

        project_name = "preview_success_test"
        client.post("/api/projects", json={"name": project_name})
        client.post("/api/projects/select", json={"name": project_name})

        # Build first to record the output_path for preview
        r = client.post("/api/projects/build", json={"target": "web"})
        assert r.status_code == 200
        assert r.json()["success"] is True

        r = client.post("/api/projects/preview", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "127.0.0.1:55555" in data["url"]
        assert data["port"] == 55555

    def test_preview_project_no_build(self, client: TestClient):
        project_name = "preview_no_build_test"
        client.post("/api/projects", json={"name": project_name})
        client.post("/api/projects/select", json={"name": project_name})

        r = client.post("/api/projects/preview", json={})
        assert r.status_code == 404
        assert "No successful build available" in r.json()["detail"]

    def test_build_uses_current_project_context(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        from renpy_mcp.models import BuildResult
        from renpy_mcp.services import build_manager as bm

        seen = {}

        async def _mock_build(self, request):
            seen["project_name"] = request.project_name
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=True,
                output_path=Path(f"/fake/{request.project_name}-web"),
            )

        monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

        client.post("/api/projects", json={"name": "project_a"})
        client.post("/api/projects", json={"name": "project_b"})
        client.post("/api/projects/select", json={"name": "project_a"})

        r = client.post("/api/projects/build", json={"target": "web"})
        assert r.status_code == 200
        assert seen["project_name"] == "project_a"

    def test_build_rejects_project_name_mismatch(self, client: TestClient):
        client.post("/api/projects", json={"name": "project_a"})
        client.post("/api/projects", json={"name": "project_b"})
        client.post("/api/projects/select", json={"name": "project_a"})

        r = client.post("/api/projects/build", json={"name": "project_b", "target": "web"})
        assert r.status_code == 400
        assert "current project" in r.json()["detail"].lower()

    def test_failed_build_clears_previous_preview_result(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.config import get_settings
        from renpy_mcp.models import BuildResult
        from renpy_mcp.services import build_manager as bm

        workspace = get_settings().workspace
        call_count = {"value": 0}

        async def _mock_build(self, request):
            call_count["value"] += 1
            if call_count["value"] == 1:
                output_path = workspace / f"{request.project_name}-dists" / f"{request.project_name}-web"
                output_path.mkdir(parents=True, exist_ok=True)
                (output_path / "index.html").write_text("<html></html>", encoding="utf-8")
                return BuildResult(
                    project_name=request.project_name,
                    target=request.target,
                    success=True,
                    output_path=output_path,
                )
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=False,
                error="mock build failed",
            )

        monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

        project_name = "stale_preview_test"
        client.post("/api/projects", json={"name": project_name})
        client.post("/api/projects/select", json={"name": project_name})

        first = client.post("/api/projects/build", json={"target": "web"})
        assert first.status_code == 200
        assert first.json()["success"] is True

        second = client.post("/api/projects/build", json={"target": "web"})
        assert second.status_code == 200
        assert second.json()["success"] is False

        preview = client.post("/api/projects/preview", json={})
        assert preview.status_code == 404
        assert "No successful build available" in preview.json()["detail"]

    def test_non_previewable_build_result_is_not_reused_for_preview(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.models import BuildResult
        from renpy_mcp.services import build_manager as bm

        async def _mock_build(self, request):
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=True,
                output_path=Path("/fake/output.zip"),
            )

        monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

        project_name = "non_previewable_build_test"
        client.post("/api/projects", json={"name": project_name})
        client.post("/api/projects/select", json={"name": project_name})

        build = client.post("/api/projects/build", json={"target": "web"})
        assert build.status_code == 200
        assert build.json()["success"] is True

        preview = client.post("/api/projects/preview", json={})
        assert preview.status_code == 404
        assert "No successful build available" in preview.json()["detail"]

    def test_build_status_written_on_success(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        from renpy_mcp.models import BuildResult
        from renpy_mcp.services import build_manager as bm

        async def _mock_build(self, request):
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=True,
                output_path=Path("/fake/output"),
            )

        monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

        project_name = "build_status_success_test"
        client.post("/api/projects", json={"name": project_name})
        client.post("/api/projects/select", json={"name": project_name})

        r = client.post("/api/projects/build", json={"target": "web"})
        assert r.status_code == 200

        status = client.get("/api/projects/build/status")
        assert status.status_code == 200
        data = status.json()
        assert data["status"] == "success"
        assert "Built to" in data["message"]
        assert data["previewable"] is False
        assert data["target"] == "web"
        assert data["updated_at"] is not None

    def test_build_status_written_on_failure(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        from renpy_mcp.services import build_manager as bm

        monkeypatch.setattr(bm.BuildManager, "_resolve_toolchain", lambda self: None)

        project_name = "build_status_fail_test"
        client.post("/api/projects", json={"name": project_name})
        client.post("/api/projects/select", json={"name": project_name})

        r = client.post("/api/projects/build", json={"target": "web"})
        assert r.status_code == 200
        assert r.json()["success"] is False

        status = client.get("/api/projects/build/status")
        assert status.status_code == 200
        data = status.json()
        assert data["status"] == "failed"
        assert "No usable Ren'Py SDK found" in data["message"]
        assert data["previewable"] is False
        assert data["target"] == "web"
        assert data["updated_at"] is not None

    def test_preview_restores_after_app_recreation(self, client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Simulate server restart by clearing in-memory cache and recreating app."""
        from renpy_mcp.config import get_settings
        from renpy_mcp.models import BuildResult
        from renpy_mcp.services import build_manager as bm
        from renpy_mcp.services import preview_manager as pm
        from renpy_mcp.services.preview_manager import PreviewServer

        workspace = get_settings().workspace

        async def _mock_build(self, request):
            output_path = workspace / f"{request.project_name}-dists" / f"{request.project_name}-web"
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / "index.html").write_text("<html></html>", encoding="utf-8")
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=True,
                output_path=output_path,
            )

        async def _mock_start(self, project_name, directory):
            return PreviewServer(
                project_name=project_name,
                directory=directory,
                port=55555,
                process=None,  # type: ignore[arg-type]
            )

        monkeypatch.setattr(bm.BuildManager, "build", _mock_build)
        monkeypatch.setattr(pm.PreviewManager, "start", _mock_start)

        project_name = "restart_preview_test"
        client.post("/api/projects", json={"name": project_name})
        client.post("/api/projects/select", json={"name": project_name})

        r = client.post("/api/projects/build", json={"target": "web"})
        assert r.status_code == 200

        # Simulate restart: clear in-memory cache
        import renpy_mcp.web.fastapi_app as fa
        fa._last_build_results.pop(project_name, None)

        # Recreate app (simulates new process)
        new_app = create_app()
        new_client = TestClient(new_app)
        # Must select project in new client session
        new_client.post("/api/projects/select", json={"name": project_name})

        r = new_client.post("/api/projects/preview", json={})
        assert r.status_code == 200
        assert "127.0.0.1:55555" in r.json()["url"]


class TestProjectListErrors:
    """Tests for corrupt-project error propagation in /api/projects."""

    def test_api_projects_includes_errors_for_corrupt_meta(self, client: TestClient, tmp_path: Path):
        """Valid, legacy, and corrupt projects must be distinguishable in the API response."""
        workspace = tmp_path

        # Valid project: create via API
        client.post("/api/projects", json={"name": "valid_proj"})

        # Legacy project: directory exists but has no meta/project.json
        legacy_dir = workspace / "legacy_proj"
        (legacy_dir / "game").mkdir(parents=True)
        (legacy_dir / "game" / "script.rpy").write_text('label start:\n    return\n', encoding="utf-8")

        # Corrupt project: meta/project.json exists but is invalid
        corrupt_dir = workspace / "corrupt_proj"
        (corrupt_dir / "meta").mkdir(parents=True)
        (corrupt_dir / "meta" / "project.json").write_text("not json", encoding="utf-8")

        r = client.get("/api/projects")
        assert r.status_code == 200
        data = r.json()

        project_names = {p["name"] for p in data["projects"]}
        assert "valid_proj" in project_names
        assert "legacy_proj" in project_names
        assert "corrupt_proj" not in project_names

        assert any("corrupt_proj" in err and "meta/project.json" in err for err in data["errors"])


class TestProjectMetaApi:
    """Tests for /api/projects/{project_name}/meta."""

    def test_get_meta_returns_project_meta(self, client: TestClient):
        project_name = "meta_get_test"
        client.post("/api/projects", json={"name": project_name})

        r = client.get(f"/api/projects/{project_name}/meta")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == project_name
        assert data["status"] == "draft"
        assert data["pipeline_stage"] == "idle"

    def test_put_meta_updates_and_refreshes_updated_at(self, client: TestClient):
        from datetime import datetime

        project_name = "meta_put_test"
        client.post("/api/projects", json={"name": project_name})

        r = client.get(f"/api/projects/{project_name}/meta")
        before = datetime.fromisoformat(r.json()["updated_at"])

        payload = {
            "name": project_name,
            "status": "draft",
            "pipeline_stage": "collecting",
            "chapter_count": 3,
            "scene_count": 12,
            "confirmed_scenes": 5,
        }
        r = client.put(f"/api/projects/{project_name}/meta", json=payload)
        assert r.status_code == 200

        r = client.get(f"/api/projects/{project_name}/meta")
        data = r.json()
        assert data["status"] == "draft"
        assert data["pipeline_stage"] == "collecting"
        assert data["chapter_count"] == 3
        assert data["scene_count"] == 12
        assert data["confirmed_scenes"] == 5
        after = datetime.fromisoformat(data["updated_at"])
        assert after > before

    def test_get_meta_404_for_missing_project(self, client: TestClient):
        r = client.get("/api/projects/nonexistent_project/meta")
        assert r.status_code == 404

    def test_put_meta_404_for_missing_project(self, client: TestClient):
        r = client.put("/api/projects/nonexistent_project/meta", json={"name": "x"})
        assert r.status_code == 404

    def test_put_meta_does_not_allow_name_override(self, client: TestClient):
        """The route-level project_name must always win over body.name."""
        project_name = "name_lock_test"
        client.post("/api/projects", json={"name": project_name})

        r = client.put(
            f"/api/projects/{project_name}/meta",
            json={"name": "hijacked_name", "status": "draft"},
        )
        assert r.status_code == 200

        r = client.get(f"/api/projects/{project_name}/meta")
        data = r.json()
        assert data["name"] == project_name
        assert data["status"] == "draft"

    def test_put_meta_returns_400_for_invalid_payload(self, client: TestClient):
        """Validation errors in the meta payload must be 400, not 500."""
        project_name = "meta_400_test"
        client.post("/api/projects", json={"name": project_name})

        r = client.put(
            f"/api/projects/{project_name}/meta",
            json={"status": "not_a_status"},
        )
        assert r.status_code == 400
        assert "invalid" in r.json()["detail"].lower() or "validation" in r.json()["detail"].lower()

    def test_put_meta_returns_400_for_non_object_payload(self, client: TestClient):
        """Non-object JSON bodies must be rejected as 400."""
        project_name = "meta_non_object_test"
        client.post("/api/projects", json={"name": project_name})

        r = client.put(
            f"/api/projects/{project_name}/meta",
            json=["not", "an", "object"],
        )
        assert r.status_code == 400
        assert "object" in r.json()["detail"].lower()

    def test_put_meta_returns_400_for_unknown_fields(self, client: TestClient):
        """Unknown or misspelled fields must be rejected as 400, not silently ignored."""
        project_name = "meta_unknown_field_test"
        client.post("/api/projects", json={"name": project_name})

        r = client.put(
            f"/api/projects/{project_name}/meta",
            json={"stauts": "editing", "bogus": 123},
        )
        assert r.status_code == 400
        detail = r.json()["detail"].lower()
        assert "invalid" in detail or "unknown" in detail or "unsupported" in detail

        # Verify the misspelled field did NOT take effect
        r2 = client.get(f"/api/projects/{project_name}/meta")
        assert r2.json()["status"] != "editing"

    def test_put_meta_returns_400_for_malformed_json(self, client: TestClient):
        """Malformed JSON must be rejected as 400, not 500."""
        project_name = "meta_malformed_json_test"
        client.post("/api/projects", json={"name": project_name})

        r = client.put(
            f"/api/projects/{project_name}/meta",
            data='{"status": ',
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400
        detail = r.json()["detail"].lower()
        assert "malformed" in detail or "invalid" in detail or "json" in detail

    def test_put_meta_returns_500_for_unexpected_validation_runtime_error(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Non-validation exceptions during model_validate must NOT be disguised as 400."""
        from renpy_mcp.blueprint.models import ProjectMeta
        from renpy_mcp.web.fastapi_app import create_app

        project_name = "meta_runtime_error_test"
        client.post("/api/projects", json={"name": project_name})

        monkeypatch.setattr(
            ProjectMeta, "model_validate", lambda obj: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        # Use a client that does not re-raise server exceptions so we can inspect the status code
        raw_client = TestClient(create_app(), raise_server_exceptions=False)
        r = raw_client.put(
            f"/api/projects/{project_name}/meta",
            json={"status": "editing"},
        )
        assert r.status_code == 500


class TestProjectBlueprintApi:
    """Tests for /api/projects/{project_name}/blueprint."""

    def test_get_blueprint_returns_content(self, client: TestClient):
        from renpy_mcp.blueprint.models import ProjectBlueprint
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        project_name = "bp_get_test"
        client.post("/api/projects", json={"name": project_name})

        pm = ProjectManager(get_settings())
        bp = ProjectBlueprint(title="Test VN", genre="sci-fi", worldview="space")
        pm.write_blueprint(project_name, bp)

        r = client.get(f"/api/projects/{project_name}/blueprint")
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "Test VN"
        assert data["genre"] == "sci-fi"
        assert data["worldview"] == "space"

    def test_put_blueprint_writes_yaml_and_roundtrips(self, client: TestClient):
        project_name = "bp_put_test"
        client.post("/api/projects", json={"name": project_name})

        payload = {
            "title": "New VN",
            "genre": "romance",
            "worldview": "high school",
            "themes": ["love", "friendship"],
        }
        r = client.put(f"/api/projects/{project_name}/blueprint", json=payload)
        assert r.status_code == 200

        r = client.get(f"/api/projects/{project_name}/blueprint")
        data = r.json()
        assert data["title"] == "New VN"
        assert data["genre"] == "romance"
        assert data["worldview"] == "high school"
        assert data["themes"] == ["love", "friendship"]

        # Verify the file is real YAML, not JSON
        from renpy_mcp.config import get_settings
        bp_path = get_settings().workspace / project_name / "meta" / "blueprint.yaml"
        raw = bp_path.read_text(encoding="utf-8")
        assert not raw.strip().startswith("{")
        assert "title: New VN" in raw

    def test_get_blueprint_404_when_missing(self, client: TestClient):
        project_name = "bp_missing_test"
        client.post("/api/projects", json={"name": project_name})

        r = client.get(f"/api/projects/{project_name}/blueprint")
        assert r.status_code == 404

    def test_get_blueprint_error_for_invalid_yaml(self, client: TestClient, tmp_path: Path):
        project_name = "bp_bad_yaml_test"
        client.post("/api/projects", json={"name": project_name})

        # Corrupt the blueprint.yaml directly
        from renpy_mcp.config import get_settings
        meta_dir = get_settings().workspace / project_name / "meta"
        (meta_dir / "blueprint.yaml").write_text("not: [ valid yaml", encoding="utf-8")

        r = client.get(f"/api/projects/{project_name}/blueprint")
        assert r.status_code == 500
        assert "blueprint" in r.json()["detail"].lower()

    def test_get_blueprint_404_for_missing_project(self, client: TestClient):
        r = client.get("/api/projects/nonexistent_project/blueprint")
        assert r.status_code == 404

    def test_put_blueprint_404_for_missing_project(self, client: TestClient):
        r = client.put("/api/projects/nonexistent_project/blueprint", json={"title": "x", "genre": "x", "worldview": "x"})
        assert r.status_code == 404

    def test_put_blueprint_returns_400_for_malformed_json(self, client: TestClient):
        """Malformed JSON must be rejected as 400, not 500."""
        project_name = "bp_malformed_json_test"
        client.post("/api/projects", json={"name": project_name})

        r = client.put(
            f"/api/projects/{project_name}/blueprint",
            data='{"title": ',
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400
        detail = r.json()["detail"].lower()
        assert "malformed" in detail or "invalid" in detail or "json" in detail

    def test_put_blueprint_returns_500_for_unexpected_validation_runtime_error(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Non-validation exceptions during model_validate must NOT be disguised as 400."""
        from renpy_mcp.blueprint.models import ProjectBlueprint
        from renpy_mcp.web.fastapi_app import create_app

        project_name = "bp_runtime_error_test"
        client.post("/api/projects", json={"name": project_name})

        monkeypatch.setattr(
            ProjectBlueprint,
            "model_validate",
            lambda obj: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        raw_client = TestClient(create_app(), raise_server_exceptions=False)
        r = raw_client.put(
            f"/api/projects/{project_name}/blueprint",
            json={"title": "x", "genre": "y", "worldview": "z"},
        )
        assert r.status_code == 500


class TestChatHistoryApi:
    """Tests for /api/projects/{project_name}/chat/history."""

    def test_chat_history_empty_when_no_history(self, client: TestClient):
        project_name = "no_history_proj"
        client.post("/api/projects", json={"name": project_name})
        client.post("/api/projects/select", json={"name": project_name})

        r = client.get(f"/api/projects/{project_name}/chat/history")
        assert r.status_code == 200
        assert r.json()["messages"] == []

    def test_chat_history_rejects_mismatched_project(self, client: TestClient):
        client.post("/api/projects", json={"name": "proj_a"})
        client.post("/api/projects", json={"name": "proj_b"})
        client.post("/api/projects/select", json={"name": "proj_a"})

        r = client.get("/api/projects/proj_b/chat/history")
        assert r.status_code == 400
        assert "current project" in r.json()["detail"].lower()

    def test_chat_history_returns_persisted_messages(self, client: TestClient, temp_project: Path):
        from renpy_mcp.web.chat_ws import _write_chat_history

        project_name = temp_project.name
        client.post("/api/projects/select", json={"name": project_name})

        fake_messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [{"type": "text", "text": "hi there"}]},
        ]
        _write_chat_history(project_name, fake_messages)

        r = client.get(f"/api/projects/{project_name}/chat/history")
        assert r.status_code == 200
        data = r.json()
        assert data["messages"] == fake_messages

    def test_chat_history_isolated_per_project(self, client: TestClient, tmp_path: Path):
        from renpy_mcp.web.chat_ws import _write_chat_history

        for name in ("hist_a", "hist_b"):
            game_dir = tmp_path / name / "game"
            game_dir.mkdir(parents=True)
            (game_dir / "script.rpy").write_text('label start:\n    return\n', encoding="utf-8")
            _write_chat_history(name, [{"role": "user", "content": f"msg_for_{name}"}])

        client.post("/api/projects/select", json={"name": "hist_a"})
        r = client.get("/api/projects/hist_a/chat/history")
        assert r.status_code == 200
        assert r.json()["messages"][0]["content"] == "msg_for_hist_a"

        client.post("/api/projects/select", json={"name": "hist_b"})
        r = client.get("/api/projects/hist_b/chat/history")
        assert r.status_code == 200
        assert r.json()["messages"][0]["content"] == "msg_for_hist_b"


class TestProjectScenesApi:
    """Tests for GET /api/projects/{name}/scenes."""

    def _setup_project_with_blueprint(self, client: TestClient, project_name: str):
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings
        from renpy_mcp.blueprint.models import ProjectBlueprint, ChapterSummary, SceneSummary

        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())
        bp = ProjectBlueprint(
            title="Test VN",
            genre="romance",
            worldview="high school",
            chapters=[
                ChapterSummary(
                    id="ch1",
                    name="Prologue",
                    order=1,
                    scenes=[
                        SceneSummary(id="s1-1", name="Morning", order=1),
                        SceneSummary(id="s1-2", name="Cafeteria", order=2),
                    ],
                ),
                ChapterSummary(
                    id="ch2",
                    name="Act 1",
                    order=2,
                    scenes=[
                        SceneSummary(id="s2-1", name="Classroom", order=1),
                    ],
                ),
            ],
        )
        pm.write_blueprint(project_name, bp)
        return bp

    def test_get_scenes_returns_chapters(self, client: TestClient):
        project_name = "scenes_test"
        self._setup_project_with_blueprint(client, project_name)

        r = client.get(f"/api/projects/{project_name}/scenes")
        assert r.status_code == 200
        data = r.json()
        assert "chapters" in data
        assert len(data["chapters"]) == 2
        assert data["chapters"][0]["id"] == "ch1"
        assert len(data["chapters"][0]["scenes"]) == 2
        assert data["chapters"][0]["scenes"][0]["id"] == "s1-1"
        assert data["chapters"][1]["id"] == "ch2"
        assert len(data["chapters"][1]["scenes"]) == 1

    def test_get_scenes_404_for_missing_project(self, client: TestClient):
        r = client.get("/api/projects/nonexistent_project/scenes")
        assert r.status_code == 404

    def test_get_scenes_404_when_blueprint_missing(self, client: TestClient):
        project_name = "scenes_no_bp"
        client.post("/api/projects", json={"name": project_name})
        r = client.get(f"/api/projects/{project_name}/scenes")
        assert r.status_code == 404

    def test_get_scenes_returns_prototype_scenes_when_index_has_prototype(self, client: TestClient):
        """When prototype scenes exist in index, /scenes should return them instead of blueprint summary."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings
        from renpy_mcp.blueprint.models import ProjectBlueprint, ChapterSummary, SceneSummary

        project_name = "scenes_proto"
        self._setup_project_with_blueprint(client, project_name)

        # Inject prototype scene index
        pm = ProjectManager(get_settings())
        index = {
            "scenes": {
                "proto-s1": {
                    "chapter_id": "ch1",
                    "scene_id": "proto-s1",
                    "title": "Prototype Opening",
                    "summary": "The real prototype opening scene.",
                    "location": "classroom",
                    "next_scene_id": "proto-s2",
                    "label": "prototype_ch1_start",
                    "file_path": "game/prototype_ch1.rpy",
                    "source": "prototype",
                    "order": 1,
                },
                "proto-s2": {
                    "chapter_id": "ch1",
                    "scene_id": "proto-s2",
                    "title": "Prototype Climax",
                    "summary": "The real prototype climax scene.",
                    "location": "roof",
                    "next_scene_id": None,
                    "label": "prototype_ch1_scene2",
                    "file_path": "game/prototype_ch1.rpy",
                    "source": "prototype",
                    "order": 2,
                },
            }
        }
        pm.write_project_index(project_name, index)

        r = client.get(f"/api/projects/{project_name}/scenes")
        assert r.status_code == 200
        data = r.json()
        assert "chapters" in data
        assert len(data["chapters"]) == 1
        assert data["chapters"][0]["id"] == "ch1"
        scenes = data["chapters"][0]["scenes"]
        assert len(scenes) == 2
        assert scenes[0]["id"] == "proto-s1"
        assert scenes[0]["name"] == "Prototype Opening"
        assert scenes[1]["id"] == "proto-s2"
        assert scenes[1]["name"] == "Prototype Climax"


class TestProjectStorymapApi:
    """Tests for GET /api/projects/{name}/storymap."""

    def _setup_project_with_blueprint(self, client: TestClient, project_name: str):
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings
        from renpy_mcp.blueprint.models import (
            ProjectBlueprint,
            ChapterSummary,
            SceneSummary,
        )

        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())
        bp = ProjectBlueprint(
            title="Test VN",
            genre="romance",
            worldview="high school",
            chapters=[
                ChapterSummary(
                    id="ch1",
                    name="Prologue",
                    order=1,
                    scenes=[
                        SceneSummary(id="s1-1", name="Morning", order=1),
                        SceneSummary(
                            id="s1-2",
                            name="Choice",
                            order=2,
                        ),
                    ],
                ),
                ChapterSummary(
                    id="ch2",
                    name="Act 1",
                    order=2,
                    scenes=[
                        SceneSummary(id="s2-1", name="Left path", order=1),
                        SceneSummary(id="s2-2", name="Right path", order=2),
                    ],
                ),
            ],
        )
        pm.write_blueprint(project_name, bp)
        return bp

    def test_get_storymap_returns_nodes_and_edges(self, client: TestClient):
        project_name = "storymap_test"
        self._setup_project_with_blueprint(client, project_name)

        r = client.get(f"/api/projects/{project_name}/storymap")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data

        # 4 scenes = 4 nodes
        assert len(data["nodes"]) == 4
        node_ids = {n["id"] for n in data["nodes"]}
        assert node_ids == {"s1-1", "s1-2", "s2-1", "s2-2"}

        # Sequential main edge: s1-1 -> s1-2 within ch1
        main_edges = [e for e in data["edges"] if e["type"] == "main"]
        assert len(main_edges) == 2  # s1-1->s1-2 and s2-1->s2-2
        assert any(
            e["from_scene_id"] == "s1-1" and e["to_scene_id"] == "s1-2"
            for e in main_edges
        )

        # No branch edges when choices are absent
        branch_edges = [e for e in data["edges"] if e["type"] == "branch"]
        assert len(branch_edges) == 0

    def test_get_storymap_404_for_missing_project(self, client: TestClient):
        r = client.get("/api/projects/nonexistent_project/storymap")
        assert r.status_code == 404

    def test_get_storymap_404_when_blueprint_missing(self, client: TestClient):
        project_name = "storymap_no_bp"
        client.post("/api/projects", json={"name": project_name})
        r = client.get(f"/api/projects/{project_name}/storymap")
        assert r.status_code == 404

    def test_get_storymap_returns_prototype_graph_when_index_has_prototype(self, client: TestClient):
        """When prototype scenes exist in index, /storymap should use next_scene_id for edges."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings
        from renpy_mcp.blueprint.models import ProjectBlueprint, ChapterSummary, SceneSummary

        project_name = "storymap_proto"
        self._setup_project_with_blueprint(client, project_name)

        pm = ProjectManager(get_settings())
        index = {
            "scenes": {
                "proto-s1": {
                    "chapter_id": "ch1",
                    "scene_id": "proto-s1",
                    "title": "Prototype Opening",
                    "summary": "Opening scene.",
                    "location": "classroom",
                    "next_scene_id": "proto-s2",
                    "label": "prototype_ch1_start",
                    "file_path": "game/prototype_ch1.rpy",
                    "source": "prototype",
                    "order": 1,
                },
                "proto-s2": {
                    "chapter_id": "ch1",
                    "scene_id": "proto-s2",
                    "title": "Prototype End",
                    "summary": "End scene.",
                    "location": "roof",
                    "next_scene_id": None,
                    "label": "prototype_ch1_end",
                    "file_path": "game/prototype_ch1.rpy",
                    "source": "prototype",
                    "order": 2,
                },
            }
        }
        pm.write_project_index(project_name, index)

        r = client.get(f"/api/projects/{project_name}/storymap")
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data
        assert "edges" in data

        node_ids = {n["id"] for n in data["nodes"]}
        assert node_ids == {"proto-s1", "proto-s2"}

        main_edges = [e for e in data["edges"] if e["type"] == "main"]
        assert len(main_edges) == 1
        assert main_edges[0]["from_scene_id"] == "proto-s1"
        assert main_edges[0]["to_scene_id"] == "proto-s2"

    def test_get_storymap_handles_missing_choice_target(self, client: TestClient):
        """Dangling branch edges to non-existent scenes must be skipped."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings
        from renpy_mcp.blueprint.models import (
            ProjectBlueprint,
            ChapterSummary,
            SceneSummary,
        )

        project_name = "storymap_missing_choice_target"
        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())
        bp = ProjectBlueprint(
            title="Test VN",
            genre="romance",
            worldview="high school",
            chapters=[
                ChapterSummary(
                    id="ch1",
                    name="Prologue",
                    order=1,
                    scenes=[
                        SceneSummary(
                            id="s1-1",
                            name="Choice",
                            order=1,
                        ),
                        SceneSummary(id="s1-2", name="Next", order=2),
                    ],
                ),
            ],
        )
        pm.write_blueprint(project_name, bp)

        r = client.get(f"/api/projects/{project_name}/storymap")
        assert r.status_code == 200
        data = r.json()
        branch_edges = [e for e in data["edges"] if e["type"] == "branch"]
        # No choices means no branch edges
        assert len(branch_edges) == 0


class TestProjectSceneScriptApi:
    """Tests for GET /api/projects/{name}/scenes/{scene_id}/script."""

    def _setup_project_with_index(self, client: TestClient, project_name: str):
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())

        # Create a script file
        game_dir = get_settings().workspace / project_name / "game"
        game_dir.mkdir(parents=True, exist_ok=True)
        script_path = game_dir / "scene1.rpy"
        script_path.write_text('label start:\n    "Hello world"\n    return\n', encoding="utf-8")

        # Create index
        pm.write_project_index(
            project_name,
            {
                "scenes": {
                    "s1-1": {
                        "chapter_id": "ch1",
                        "label": "start",
                        "file_path": "game/scene1.rpy",
                    }
                }
            },
        )
        return script_path

    def test_get_scene_script_returns_structured_data(self, client: TestClient):
        project_name = "script_test"
        self._setup_project_with_index(client, project_name)

        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 200
        data = r.json()
        assert data["scene_id"] == "s1-1"
        assert data["chapter_id"] == "ch1"
        assert data["label"] == "start"
        assert data["file_path"] == "game/scene1.rpy"
        assert 'label start:' in data["content"]

    def test_get_scene_script_404_for_missing_project(self, client: TestClient):
        r = client.get("/api/projects/nonexistent_project/scenes/s1-1/script")
        assert r.status_code == 404

    def test_get_scene_script_404_when_index_missing(self, client: TestClient):
        project_name = "script_no_index"
        client.post("/api/projects", json={"name": project_name})
        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 404

    def test_get_scene_script_404_when_scene_id_not_in_index(self, client: TestClient):
        project_name = "script_no_scene"
        self._setup_project_with_index(client, project_name)
        r = client.get(f"/api/projects/{project_name}/scenes/s99-99/script")
        assert r.status_code == 404

    def test_get_scene_script_404_when_file_missing(self, client: TestClient):
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        project_name = "script_missing_file"
        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())
        pm.write_project_index(
            project_name,
            {
                "scenes": {
                    "s1-1": {
                        "chapter_id": "ch1",
                        "label": "start",
                        "file_path": "game/nonexistent.rpy",
                    }
                }
            },
        )
        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 404

    def test_get_scene_script_500_when_index_corrupt(self, client: TestClient):
        from renpy_mcp.config import get_settings

        project_name = "script_corrupt_index"
        client.post("/api/projects", json={"name": project_name})
        meta_dir = get_settings().workspace / project_name / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "index.json").write_text("not valid json", encoding="utf-8")
        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 500

    def test_get_scene_script_rejects_path_traversal_from_index(self, client: TestClient):
        """file_path escaping the project directory must be rejected."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        project_name = "script_traversal"
        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())

        # Write a secret file outside the project directory
        secret_path = get_settings().workspace / "secret.txt"
        secret_path.write_text("top secret", encoding="utf-8")

        pm.write_project_index(
            project_name,
            {
                "scenes": {
                    "s1-1": {
                        "chapter_id": "ch1",
                        "label": "start",
                        "file_path": "../secret.txt",
                    }
                }
            },
        )

        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 500
        detail = r.json().get("detail", "")
        assert "invalid" in detail.lower() or "file_path" in detail.lower() or "traversal" in detail.lower()
        # Ensure the content was NOT returned
        assert "top secret" not in r.text

    def test_get_scene_script_500_when_index_structure_invalid(self, client: TestClient):
        """scenes must be a dict/object, not a list."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        project_name = "script_bad_index_struct"
        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())
        pm.write_project_index(project_name, {"scenes": ["not-a-map"]})

        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 500
        detail = r.json().get("detail", "")
        assert "structure" in detail.lower() or "invalid" in detail.lower()

    def test_get_scene_script_500_when_scene_mapping_structure_invalid(self, client: TestClient):
        """scene mapping must be a dict, not a string or list."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        project_name = "script_bad_scene_struct"
        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())
        pm.write_project_index(project_name, {"scenes": {"s1-1": "not-a-dict"}})

        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 500
        detail = r.json().get("detail", "")
        assert "structure" in detail.lower() or "invalid" in detail.lower()

    def test_get_scene_script_rejects_missing_required_mapping_fields(self, client: TestClient):
        """Missing chapter_id or label must not silently succeed with empty strings."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        project_name = "script_missing_fields"
        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())

        # Create the script file so only the mapping is bad
        game_dir = get_settings().workspace / project_name / "game"
        game_dir.mkdir(parents=True, exist_ok=True)
        (game_dir / "scene1.rpy").write_text('label start:\n    return\n', encoding="utf-8")

        pm.write_project_index(
            project_name,
            {
                "scenes": {
                    "s1-1": {
                        # missing chapter_id and label on purpose
                        "file_path": "game/scene1.rpy",
                    }
                }
            },
        )

        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 500
        detail = r.json().get("detail", "")
        assert "incomplete" in detail.lower() or "missing" in detail.lower() or "invalid" in detail.lower()
        # Ensure it did not return 200 with empty strings
        assert r.status_code != 200


    def test_get_scene_script_500_when_index_top_level_not_object(self, client: TestClient):
        """Top-level index.json must be an object, not list/null/string."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        project_name = "script_top_level_not_obj"
        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())
        pm.write_project_index(project_name, [])

        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 500
        detail = r.json().get("detail", "")
        assert "structure" in detail.lower() or "object" in detail.lower()

    def test_get_scene_script_500_when_scene_mapping_is_null(self, client: TestClient):
        """scene_id present but mapping is null must be 500, not 404."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        project_name = "script_scene_mapping_null"
        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())
        pm.write_project_index(
            project_name,
            {
                "scenes": {
                    "s1-1": None,
                }
            },
        )

        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 500
        detail = r.json().get("detail", "")
        assert "structure" in detail.lower() or "mapping" in detail.lower()


    def test_get_scene_script_500_when_file_path_is_not_rpy_script(self, client: TestClient):
        """file_path pointing to non-rpy / non-game files must be rejected."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        project_name = "script_not_rpy"
        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())

        # Write a meta/project.json so we can try to read it through the script endpoint
        meta_dir = get_settings().workspace / project_name / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "project.json").write_text('{"secret": true}', encoding="utf-8")

        pm.write_project_index(
            project_name,
            {
                "scenes": {
                    "s1-1": {
                        "chapter_id": "ch1",
                        "label": "start",
                        "file_path": "meta/project.json",
                    }
                }
            },
        )

        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 500
        detail = r.json().get("detail", "")
        assert "invalid" in detail.lower() or "file_path" in detail.lower() or "script" in detail.lower()
        # Must NOT return the contents of project.json
        assert '"secret": true' not in r.text

    def test_get_scene_script_500_when_file_path_is_not_string(self, client: TestClient):
        """Non-string file_path must not cause a raw 500."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        project_name = "script_path_not_string"
        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())

        pm.write_project_index(
            project_name,
            {
                "scenes": {
                    "s1-1": {
                        "chapter_id": "ch1",
                        "label": "start",
                        "file_path": 123,
                    }
                }
            },
        )

        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 500
        detail = r.json().get("detail", "")
        assert "invalid" in detail.lower() or "file_path" in detail.lower() or "structure" in detail.lower()


    def test_get_scene_script_rejects_path_that_escapes_game_subtree(self, client: TestClient):
        """file_path using traversal to escape game/ must be rejected even if still inside project_dir."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        project_name = "script_escapes_game"
        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())

        # Create a .rpy file outside game/ but still inside the project
        meta_dir = get_settings().workspace / project_name / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "secret.rpy").write_text('label leak:\n    "leaked"\n', encoding="utf-8")

        pm.write_project_index(
            project_name,
            {
                "scenes": {
                    "s1-1": {
                        "chapter_id": "ch1",
                        "label": "start",
                        "file_path": "game/../meta/secret.rpy",
                    }
                }
            },
        )

        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 500
        detail = r.json().get("detail", "")
        assert "game" in detail.lower() or "file_path" in detail.lower() or "invalid" in detail.lower()
        # Must NOT return the contents of the file
        assert '"leaked"' not in r.text


    def test_get_scene_script_accepts_valid_windows_style_game_path(self, client: TestClient):
        """Windows-style backslash separators in file_path must be accepted."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        project_name = "script_windows_path"
        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())

        game_dir = get_settings().workspace / project_name / "game"
        game_dir.mkdir(parents=True, exist_ok=True)
        (game_dir / "scene1.rpy").write_text('label start:\n    "Hello windows"\n    return\n', encoding="utf-8")

        pm.write_project_index(
            project_name,
            {
                "scenes": {
                    "s1-1": {
                        "chapter_id": "ch1",
                        "label": "start",
                        "file_path": "game\\scene1.rpy",
                    }
                }
            },
        )

        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 200
        data = r.json()
        assert data["file_path"] == "game\\scene1.rpy"
        assert 'label start:' in data["content"]
        assert '"Hello windows"' in data["content"]


    def test_get_scene_script_accepts_redundant_separator_game_path(self, client: TestClient):
        """Redundant separators like game//scene1.rpy must work and use normalized path semantics."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        project_name = "script_redundant_sep"
        client.post("/api/projects", json={"name": project_name})
        pm = ProjectManager(get_settings())

        game_dir = get_settings().workspace / project_name / "game"
        game_dir.mkdir(parents=True, exist_ok=True)
        (game_dir / "scene1.rpy").write_text('label start:\n    "Hello sep"\n    return\n', encoding="utf-8")

        pm.write_project_index(
            project_name,
            {
                "scenes": {
                    "s1-1": {
                        "chapter_id": "ch1",
                        "label": "start",
                        "file_path": "game//scene1.rpy",
                    }
                }
            },
        )

        r = client.get(f"/api/projects/{project_name}/scenes/s1-1/script")
        assert r.status_code == 200
        data = r.json()
        assert data["file_path"] == "game//scene1.rpy"
        assert 'label start:' in data["content"]
        assert '"Hello sep"' in data["content"]


class TestProjectScopedBuildPreviewApi:
    """Tests for project-scoped build status and preview endpoints."""

    def test_project_scoped_build_status_returns_project_status(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """GET /api/projects/{name}/build/status must return that project's build status."""
        from renpy_mcp.models import BuildResult
        from renpy_mcp.services import build_manager as bm

        project_name = "scoped_status_test"
        client.post("/api/projects", json={"name": project_name})

        # Create a real previewable directory so previewable=True is written
        from renpy_mcp.config import get_settings
        build_dir = get_settings().workspace / f"{project_name}-dists" / f"{project_name}-web"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "index.html").write_text("<html>mock</html>", encoding="utf-8")

        async def _mock_build(self, request):
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=True,
                output_path=build_dir,
            )

        monkeypatch.setattr(bm.BuildManager, "build", _mock_build)
        client.post("/api/projects/select", json={"name": project_name})
        client.post("/api/projects/build", json={"target": "web"})

        r = client.get(f"/api/projects/{project_name}/build/status")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "success"
        assert data["previewable"] is True

    def test_project_scoped_build_status_for_unbuilt_project(
        self, client: TestClient
    ):
        """GET /api/projects/{name}/build/status for an unbuilt project returns idle."""
        project_name = "scoped_idle_test"
        client.post("/api/projects", json={"name": project_name})

        r = client.get(f"/api/projects/{project_name}/build/status")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "idle"
        assert data["previewable"] is False

    def test_project_scoped_preview_starts_for_project(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """POST /api/projects/{name}/preview must start preview for that specific project."""
        from renpy_mcp.models import BuildResult
        from renpy_mcp.services import build_manager as bm

        project_name = "scoped_preview_test"
        client.post("/api/projects", json={"name": project_name})

        from renpy_mcp.config import get_settings
        build_dir = get_settings().workspace / f"{project_name}-dists" / f"{project_name}-web"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "index.html").write_text("<html>mock</html>", encoding="utf-8")

        async def _mock_build(self, request):
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=True,
                output_path=build_dir,
            )

        monkeypatch.setattr(bm.BuildManager, "build", _mock_build)
        client.post("/api/projects/select", json={"name": project_name})
        client.post("/api/projects/build", json={"target": "web"})

        r = client.post(f"/api/projects/{project_name}/preview", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "url" in data
        assert "127.0.0.1" in data["url"]

    def test_project_scoped_preview_rejects_no_build(
        self, client: TestClient
    ):
        """POST /api/projects/{name}/preview must 404 if project has no build."""
        project_name = "scoped_preview_no_build"
        client.post("/api/projects", json={"name": project_name})

        r = client.post(f"/api/projects/{project_name}/preview", json={})
        assert r.status_code == 404
        assert "build" in r.json()["detail"].lower()

    def test_project_scoped_generic_build_invokes_build_for_specific_project(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """POST /api/projects/{name}/build must invoke BuildManager for that specific project."""
        from renpy_mcp.models import BuildResult
        from renpy_mcp.services import build_manager as bm

        project_a = "scoped_gen_a"
        project_b = "scoped_gen_b"
        client.post("/api/projects", json={"name": project_a})
        client.post("/api/projects", json={"name": project_b})

        seen_names: list[str] = []

        async def _mock_build(self, request):
            seen_names.append(request.project_name)
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=True,
                output_path=Path("/fake/output"),
            )

        monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

        # Build project A explicitly via project-scoped endpoint
        r = client.post(f"/api/projects/{project_a}/build", json={"target": "web"})
        assert r.status_code == 200
        assert seen_names == [project_a]

    def test_project_scoped_generic_build_status_written_for_specific_project(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Project-scoped generic build must write status only to that project."""
        from renpy_mcp.models import BuildResult
        from renpy_mcp.services import build_manager as bm

        project_a = "scoped_gen_status_a"
        project_b = "scoped_gen_status_b"
        client.post("/api/projects", json={"name": project_a})
        client.post("/api/projects", json={"name": project_b})

        async def _mock_build(self, request):
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=True,
                output_path=Path("/fake/output"),
            )

        monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

        client.post(f"/api/projects/{project_a}/build", json={"target": "web"})

        # A should have success status
        r_a = client.get(f"/api/projects/{project_a}/build/status")
        assert r_a.json()["status"] == "success"

        # B should still be idle
        r_b = client.get(f"/api/projects/{project_b}/build/status")
        assert r_b.json()["status"] == "idle"


class TestPrototypePipelineStatus:
    """Tests for GET /api/projects/{name}/prototype/pipeline-status."""

    def _seed_prototype(self, workspace: Path, project_name: str) -> None:
        """Write prototype artifacts so the project has a playable prototype."""
        meta_dir = workspace / project_name / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        game_dir = workspace / project_name / "game"
        game_dir.mkdir(parents=True, exist_ok=True)

        proto_script = (
            'label prototype_ch1_start:\n'
            '    scene black\n'
            '    "Hello prototype."\n'
            '    return\n'
        )
        (game_dir / "prototype_ch1_第一章.rpy").write_text(proto_script, encoding="utf-8")

        (game_dir / "script.rpy").write_text(
            "label start:\n"
            "    # PROTOTYPE START (managed)\n"
            "    call prototype_ch1_start\n"
            "    return\n"
            "    # PROTOTYPE END (managed)\n",
            encoding="utf-8",
        )

        index = {
            "scenes": {
                "proto-ch1-s1": {
                    "chapter_id": "ch1",
                    "scene_id": "proto-ch1-s1",
                    "title": "初次相遇",
                    "summary": "主角在图书馆遇到配角。",
                    "location": "library",
                    "location_visual_brief": "安静的大学图书馆，暖黄色灯光，午后阳光",
                    "mood": "短暂温暖",
                    "characters_present": ["主角", "配角"],
                    "dialogue_beats": [
                        {"speaker": "主角", "intent": "寻找一本书", "content_brief": "询问配角是否见过某本书"},
                    ],
                    "next_scene_id": None,
                    "label": "prototype_ch1_start",
                    "file_path": "game/prototype_ch1_第一章.rpy",
                    "source": "prototype",
                    "order": 1,
                    "background_asset_path": None,
                    "background_placeholder": True,
                },
            }
        }
        (meta_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")

    def test_pipeline_status_idle_when_no_prototype(self, client: TestClient, tmp_path: Path):
        """A project with no prototype artifacts should report idle."""
        project_name = "pipeline_idle"
        client.post("/api/projects", json={"name": project_name})

        r = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
        assert r.status_code == 200
        data = r.json()
        assert data["stage"] == "idle"
        assert data["has_prototype"] is False
        assert data["previewable"] is False

    def test_pipeline_status_returns_prototype_ready_when_prototype_exists_without_successful_build(
        self, client: TestClient, tmp_path: Path
    ):
        """A project with prototype but no successful build should report prototype_ready."""
        project_name = "pipeline_ready"
        client.post("/api/projects", json={"name": project_name})
        self._seed_prototype(tmp_path, project_name)

        r = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
        assert r.status_code == 200
        data = r.json()
        assert data["stage"] == "prototype_ready"
        assert data["has_prototype"] is True
        assert data["previewable"] is False
        assert data["build_status"] == "idle"

    def test_pipeline_status_returns_building_when_build_in_progress(
        self, client: TestClient, tmp_path: Path
    ):
        """When build-status.json says building, pipeline should report prototype_building."""
        project_name = "pipeline_building"
        client.post("/api/projects", json={"name": project_name})
        self._seed_prototype(tmp_path, project_name)

        # Write a building status directly
        logs_dir = tmp_path / project_name / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "build-status.json").write_text(
            json.dumps({"status": "building", "message": "Building...", "previewable": False, "target": "web"}),
            encoding="utf-8",
        )

        r = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
        assert r.status_code == 200
        data = r.json()
        assert data["stage"] == "prototype_building"
        assert data["has_prototype"] is True
        assert data["build_status"] == "building"

    def test_pipeline_status_returns_build_failed_when_build_failed(
        self, client: TestClient, tmp_path: Path
    ):
        """When build-status.json says failed, pipeline should report prototype_build_failed."""
        project_name = "pipeline_failed"
        client.post("/api/projects", json={"name": project_name})
        self._seed_prototype(tmp_path, project_name)

        logs_dir = tmp_path / project_name / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "build-status.json").write_text(
            json.dumps({"status": "failed", "message": "Build failed", "previewable": False, "target": "web"}),
            encoding="utf-8",
        )

        r = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
        assert r.status_code == 200
        data = r.json()
        assert data["stage"] == "prototype_build_failed"
        assert data["has_prototype"] is True
        assert data["build_status"] == "failed"
        assert data["previewable"] is False

    def test_pipeline_status_returns_preview_ready_when_build_success_is_previewable(
        self, client: TestClient, tmp_path: Path
    ):
        """When build succeeded and output is previewable, pipeline should report prototype_preview_ready."""
        project_name = "pipeline_preview_ready"
        client.post("/api/projects", json={"name": project_name})
        self._seed_prototype(tmp_path, project_name)

        build_dir = tmp_path / f"{project_name}-dists" / f"{project_name}-web"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "index.html").write_text("<html>mock</html>", encoding="utf-8")

        logs_dir = tmp_path / project_name / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "build-status.json").write_text(
            json.dumps({
                "status": "success",
                "message": "Built successfully",
                "output_path": str(build_dir),
                "previewable": True,
                "target": "web",
            }),
            encoding="utf-8",
        )

        r = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
        assert r.status_code == 200
        data = r.json()
        assert data["stage"] == "prototype_preview_ready"
        assert data["has_prototype"] is True
        assert data["build_status"] == "success"
        assert data["previewable"] is True

    def test_pipeline_status_returns_generating_when_runtime_session_indicates_generating(
        self, client: TestClient, tmp_path: Path
    ):
        """When blueprint_session.json indicates generating, pipeline should report prototype_generating."""
        project_name = "pipeline_generating"
        client.post("/api/projects", json={"name": project_name})

        meta_dir = tmp_path / project_name / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "blueprint_session.json").write_text(
            json.dumps({"pipeline_stage": "generating", "awaiting_confirmation": False}),
            encoding="utf-8",
        )

        r = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
        assert r.status_code == 200
        data = r.json()
        assert data["stage"] == "prototype_generating"
        assert data["has_prototype"] is False
        assert data["build_status"] == "idle"

    def test_pipeline_status_returns_generating_from_runtime_session_before_prototype_artifacts_exist(
        self, client: TestClient, tmp_path: Path
    ):
        """Real confirmation window: no prototype on disk yet, but runtime session says generating."""
        project_name = "pipeline_generating_real"
        client.post("/api/projects", json={"name": project_name})

        meta_dir = tmp_path / project_name / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "blueprint_session.json").write_text(
            json.dumps({"pipeline_stage": "generating", "awaiting_confirmation": False}),
            encoding="utf-8",
        )

        r = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
        assert r.status_code == 200
        data = r.json()
        assert data["stage"] == "prototype_generating"
        assert data["has_prototype"] is False
        assert data["build_status"] == "idle"

    def test_pipeline_status_stays_idle_after_generic_build_without_prototype(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Generic build on a non-prototype project must not promote pipeline to prototype stages."""
        from renpy_mcp.models import BuildResult
        from renpy_mcp.services import build_manager as bm

        async def _mock_build(self, request):
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=True,
                output_path=Path("/fake/output"),
            )

        monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

        project_name = "pipeline_generic_build"
        client.post("/api/projects", json={"name": project_name})
        client.post("/api/projects/select", json={"name": project_name})

        r = client.post("/api/projects/build", json={"target": "web"})
        assert r.status_code == 200
        assert r.json()["success"] is True

        # Pipeline status should remain idle because there are no prototype artifacts
        r = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
        assert r.status_code == 200
        data = r.json()
        assert data["stage"] == "idle"
        assert data["has_prototype"] is False

    def test_pipeline_status_preserves_real_build_failure_message(
        self, client: TestClient, tmp_path: Path
    ):
        """Failed builds must preserve the real failure message, not a static fallback."""
        project_name = "pipeline_failed_msg"
        client.post("/api/projects", json={"name": project_name})
        self._seed_prototype(tmp_path, project_name)

        logs_dir = tmp_path / project_name / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "build-status.json").write_text(
            json.dumps({
                "status": "failed",
                "message": "Missing SDK executable: raptools not found",
                "previewable": False,
                "target": "web",
            }),
            encoding="utf-8",
        )

        r = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
        assert r.status_code == 200
        data = r.json()
        assert data["stage"] == "prototype_build_failed"
        assert data["message"] == "Missing SDK executable: raptools not found"
        assert data["message"] != "Prototype build failed"

    def test_pipeline_status_preserves_real_success_message_for_preview_ready(
        self, client: TestClient, tmp_path: Path
    ):
        """Successful previewable builds must preserve the real success message."""
        project_name = "pipeline_success_msg"
        client.post("/api/projects", json={"name": project_name})
        self._seed_prototype(tmp_path, project_name)

        build_dir = tmp_path / f"{project_name}-dists" / f"{project_name}-web"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "index.html").write_text("<html>mock</html>", encoding="utf-8")

        logs_dir = tmp_path / project_name / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "build-status.json").write_text(
            json.dumps({
                "status": "success",
                "message": f"Prototype built to {build_dir}",
                "output_path": str(build_dir),
                "previewable": True,
                "target": "web",
            }),
            encoding="utf-8",
        )

        r = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
        assert r.status_code == 200
        data = r.json()
        assert data["stage"] == "prototype_preview_ready"
        assert data["message"] == f"Prototype built to {build_dir}"
        assert data["message"] != "Prototype built and previewable"


class TestPreviewStatus:
    """Tests for GET /api/projects/{name}/preview/status and preview runtime boundary."""

    def _seed_prototype_and_build(self, client, monkeypatch, workspace, project_name):
        from renpy_mcp.models import BuildResult
        from renpy_mcp.services import build_manager as bm
        from renpy_mcp.services import preview_manager as pm
        from renpy_mcp.services.preview_manager import PreviewServer

        async def _mock_build(self, request):
            output_path = workspace / f"{request.project_name}-dists" / f"{request.project_name}-web"
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / "index.html").write_text("<html></html>", encoding="utf-8")
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=True,
                output_path=output_path,
            )

        async def _mock_start(self, project_name, directory):
            server = PreviewServer(
                project_name=project_name,
                directory=directory,
                port=55555,
                process=None,
            )
            self._servers[project_name] = server
            return server

        monkeypatch.setattr(bm.BuildManager, "build", _mock_build)
        monkeypatch.setattr(pm.PreviewManager, "start", _mock_start)

        client.post("/api/projects", json={"name": project_name})

        meta_dir = workspace / project_name / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        game_dir = workspace / project_name / "game"
        game_dir.mkdir(parents=True, exist_ok=True)
        (game_dir / "prototype_ch1.rpy").write_text(
            "label prototype_ch1_start:\n    \"Hello\"\n    return\n",
            encoding="utf-8",
        )
        (game_dir / "script.rpy").write_text(
            "label start:\n    # PROTOTYPE START (managed)\n    call prototype_ch1_start\n    return\n    # PROTOTYPE END (managed)\n",
            encoding="utf-8",
        )
        index = {
            "scenes": {
                "proto-s1": {
                    "chapter_id": "ch1",
                    "scene_id": "proto-s1",
                    "title": "Opening",
                    "summary": "Open scene.",
                    "location": "library",
                    "next_scene_id": None,
                    "label": "prototype_ch1_start",
                    "file_path": "game/prototype_ch1.rpy",
                    "source": "prototype",
                    "order": 1,
                },
            }
        }
        (meta_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")

        r = client.post(f"/api/projects/{project_name}/prototype/build", json={"target": "web"})
        assert r.status_code == 200
        assert r.json()["success"] is True

        build_dir = workspace / f"{project_name}-dists" / f"{project_name}-web"
        return build_dir

    def test_preview_status_returns_running_after_project_scoped_preview_start(self, client, monkeypatch, tmp_path):
        from renpy_mcp.config import get_settings

        workspace = get_settings().workspace
        project_name = "preview_status_running"
        build_dir = self._seed_prototype_and_build(client, monkeypatch, workspace, project_name)
        assert build_dir.exists()

        r = client.post(f"/api/projects/{project_name}/preview")
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "127.0.0.1:55555" in data["url"]

        r = client.get(f"/api/projects/{project_name}/preview/status")
        assert r.status_code == 200
        status = r.json()
        assert status["status"] == "running"
        assert "127.0.0.1:55555" in status["url"]

    def test_preview_failure_does_not_erase_preview_ready_or_build_success(self, client, monkeypatch, tmp_path):
        from renpy_mcp.config import get_settings
        from renpy_mcp.services import preview_manager as pm

        workspace = get_settings().workspace
        project_name = "preview_fail_safe"
        build_dir = self._seed_prototype_and_build(client, monkeypatch, workspace, project_name)
        assert build_dir.exists()

        async def _mock_start_failing(self, project_name, directory):
            raise RuntimeError("Port allocation failed")

        monkeypatch.setattr(pm.PreviewManager, "start", _mock_start_failing)

        r = client.post(f"/api/projects/{project_name}/preview")
        assert r.status_code == 500

        r = client.get(f"/api/projects/{project_name}/build/status")
        assert r.status_code == 200
        bs = r.json()
        assert bs["status"] == "success"
        assert bs["previewable"] is True

        r = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
        assert r.status_code == 200
        pipe = r.json()
        assert pipe["stage"] == "prototype_preview_ready"
        assert pipe["build_status"] == "success"
        assert pipe["previewable"] is True

        assert (workspace / project_name / "game" / "prototype_ch1.rpy").exists()
        assert (workspace / project_name / "game" / "script.rpy").exists()

    def test_build_retry_after_failure_succeeds_without_restarting_blueprint_pipeline(self, client, monkeypatch, tmp_path):
        from renpy_mcp.config import get_settings
        from renpy_mcp.models import BuildResult
        from renpy_mcp.services import build_manager as bm

        workspace = get_settings().workspace
        project_name = "build_retry_test"

        client.post("/api/projects", json={"name": project_name})

        meta_dir = workspace / project_name / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        game_dir = workspace / project_name / "game"
        game_dir.mkdir(parents=True, exist_ok=True)
        (game_dir / "prototype_ch1.rpy").write_text(
            "label prototype_ch1_start:\n    \"Hello\"\n    return\n",
            encoding="utf-8",
        )
        (game_dir / "script.rpy").write_text(
            "label start:\n    # PROTOTYPE START (managed)\n    call prototype_ch1_start\n    return\n    # PROTOTYPE END (managed)\n",
            encoding="utf-8",
        )
        index = {
            "scenes": {
                "proto-s1": {
                    "chapter_id": "ch1",
                    "scene_id": "proto-s1",
                    "title": "Opening",
                    "summary": "Open scene.",
                    "location": "library",
                    "next_scene_id": None,
                    "label": "prototype_ch1_start",
                    "file_path": "game/prototype_ch1.rpy",
                    "source": "prototype",
                    "order": 1,
                },
            }
        }
        (meta_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")

        (meta_dir / "blueprint_session.json").write_text(
            json.dumps({"pipeline_stage": "confirmed", "awaiting_confirmation": False}),
            encoding="utf-8",
        )

        call_count = {"value": 0}

        async def _mock_build_fail_then_succeed(self, request):
            call_count["value"] += 1
            if call_count["value"] == 1:
                return BuildResult(
                    project_name=request.project_name,
                    target=request.target,
                    success=False,
                    error="SDK not found",
                )
            output_path = workspace / f"{request.project_name}-dists" / f"{request.project_name}-web"
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / "index.html").write_text("<html></html>", encoding="utf-8")
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=True,
                output_path=output_path,
            )

        monkeypatch.setattr(bm.BuildManager, "build", _mock_build_fail_then_succeed)

        r = client.post(f"/api/projects/{project_name}/prototype/build", json={"target": "web"})
        assert r.status_code == 200
        assert r.json()["success"] is False

        r = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
        assert r.json()["stage"] == "prototype_build_failed"

        r = client.post(f"/api/projects/{project_name}/prototype/build", json={"target": "web"})
        assert r.status_code == 200
        assert r.json()["success"] is True

        r = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
        pipe = r.json()
        assert pipe["stage"] == "prototype_preview_ready"
        assert pipe["build_status"] == "success"
        assert pipe["previewable"] is True

        session = json.loads((meta_dir / "blueprint_session.json").read_text(encoding="utf-8"))
        assert session["pipeline_stage"] == "confirmed"
        assert session["awaiting_confirmation"] is False


    def test_scenes_api_returns_controlled_sprite_paths_not_absolute_filesystem_paths(
        self, client: TestClient, tmp_path: Path
    ):
        """GET /scenes must return sprite paths as project-relative, not absolute filesystem paths."""
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        project_name = "scenes_sprite_path"
        client.post("/api/projects", json={"name": project_name})

        pm = ProjectManager(get_settings())
        index = {
            "scenes": {
                "proto-s1": {
                    "chapter_id": "ch1",
                    "scene_id": "proto-s1",
                    "title": "Test",
                    "summary": "Test scene",
                    "location": "library",
                    "next_scene_id": None,
                    "label": "prototype_start",
                    "file_path": "game/prototype.rpy",
                    "source": "prototype",
                    "order": 1,
                    "sprite_plan": [
                        {
                            "character_name": "Alice",
                            "character_id": "char_0",
                            "sprite_path": "game/images/character/char_0_neutral.png",
                            "sprite_placeholder": False,
                            "sprite_renderable": True,
                            "sprite_quality_reason": "ok",
                            "position": "center",
                            "expression": "neutral",
                            "layout_mode": "solo",
                            "transform_name": "proto_center_solo",
                        }
                    ],
                }
            }
        }
        pm.write_project_index(project_name, index)

        r = client.get(f"/api/projects/{project_name}/scenes")
        assert r.status_code == 200
        data = r.json()
        scenes = data["chapters"][0]["scenes"]
        sprite_plan = scenes[0]["sprite_plan"]
        assert len(sprite_plan) == 1
        sprite_path = sprite_plan[0]["sprite_path"]
        assert not Path(sprite_path).is_absolute(), (
            f"API must not return absolute sprite path: {sprite_path}"
        )
        assert sprite_path == "game/images/character/char_0_neutral.png"
