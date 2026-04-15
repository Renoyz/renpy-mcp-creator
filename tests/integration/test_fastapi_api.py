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
def client(temp_project: Path) -> TestClient:
    """Provide a TestClient with project config injected."""
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
        # Ensure a clean config state for this test
        from renpy_mcp.web.fastapi_app import set_config
        from renpy_mcp.config import RenPyConfig
        set_config(RenPyConfig())

        project_name = "fastapi_select_test"
        # Create project via API so it lands in the default workspace
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
