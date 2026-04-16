"""Integration tests for FastAPI routes."""

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
