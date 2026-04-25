"""Diagnose why /brief/promote-draft fails with real LLM intake data."""

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).parent.parent.parent


def _find_free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> bool:
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            try:
                sock.connect((host, port))
                return True
            except OSError:
                time.sleep(0.2)
    return False


def start_server(workspace: Path, log_file: Path) -> tuple[str, subprocess.Popen]:
    port = _find_free_port()
    env = os.environ.copy()
    env["RENPY_MCP_WORKSPACE"] = str(workspace)
    env["RENPY_MCP_MOCK_BUILD"] = "1"

    cmd = [sys.executable, "-m", "renpy_mcp.main", "--transport", "http", "--port", str(port)]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=str(REPO_ROOT),
    )

    url = f"http://127.0.0.1:{port}"
    if not _wait_for_port("127.0.0.1", port, timeout=30.0):
        proc.terminate()
        proc.kill()
        raise RuntimeError(f"Backend did not start on {url}")

    deadline = time.time() + 10.0
    while time.time() < deadline:
        try:
            if httpx.get(f"{url}/api/status", timeout=2.0).status_code == 200:
                return url, proc
        except Exception:
            pass
        time.sleep(0.5)

    proc.terminate()
    proc.kill()
    raise RuntimeError(f"Backend did not become ready on {url}")


def test_diagnose() -> None:
    import tempfile
    workspace = Path(tempfile.mkdtemp(prefix="renpy-mcp-diag-"))
    log_file = workspace / "server.log"
    url, proc = start_server(workspace, log_file)

    try:
        project_name = f"diag_{int(time.time())}"

        # Create project
        r = httpx.post(f"{url}/api/projects", json={"name": project_name})
        assert r.status_code == 200, r.text

        # Seed a refinement intake with brief_draft_ready = True
        import json
        meta_dir = workspace / project_name / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        intake = {
            "phase": "brief_ready",
            "current_summary": "Western fantasy dragon slayer",
            "missing_slots": [],
            "slots": {
                "core_premise": {"value": "A warrior must slay an ancient dragon to save the kingdom.", "complete": True},
                "audience_genre": {"value": "Western fantasy, teens and young adults", "complete": True},
                "tone_themes": {"value": "Epic, sacrifice, honor", "complete": True},
                "visual_style": {"value": "Realistic medieval with magical elements", "complete": True},
                "world_rules": {"value": "Dragons exist, magic is rare", "complete": True},
                "core_cast": {"value": "Elena (warrior), Marcus (companion)", "complete": True},
                "character_identity": {"value": {"characters": [
                    {"character_id": "elena", "name": "Elena", "story_role": "Protagonist", "core_motivation": "Save her village", "personality_anchors": ["brave", "stubborn"], "visual_identity_anchors": ["red hair", "leather armor"], "forbidden_drift": ["do not make her cruel"]}
                ]}, "complete": True},
                "relationship_baselines": {"value": {"relationships": [
                    {"pair": ["elena", "marcus"], "baseline": "Trusted allies", "must_preserve": ["loyalty"]}
                ]}, "complete": True},
                "constraints": {"value": "No deus ex machina endings.", "complete": True},
            },
            "brief_draft_ready": True,
            "outline_draft_ready": False,
            "chapter_draft": [],
            "updated_at": "2026-04-24T00:00:00Z",
        }
        (meta_dir / "refinement_intake.json").write_text(json.dumps(intake), encoding="utf-8")

        # Try promote
        r = httpx.post(f"{url}/api/projects/{project_name}/brief/promote-draft")
        print(f"Promote status: {r.status_code}")
        print(f"Promote response: {r.text}")

        # Check brief was created
        brief_path = meta_dir / "project_brief.json"
        if brief_path.exists():
            print(f"Brief created: {brief_path.read_text(encoding='utf-8')[:500]}")
        else:
            print("Brief NOT created!")

        # Also check refinement status
        r = httpx.get(f"{url}/api/projects/{project_name}/refinement-status")
        print(f"Refinement status: {r.status_code}")
        print(f"Refinement response: {r.json()}")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    test_diagnose()
