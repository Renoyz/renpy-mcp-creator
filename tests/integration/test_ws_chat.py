"""Integration tests for /ws/chat WebSocket endpoint."""

import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from renpy_mcp.web.fastapi_app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from renpy_mcp.config import RenPyConfig, get_settings
    from renpy_mcp.web.fastapi_app import set_config

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)
    set_config(RenPyConfig(sdk_path=Path(".")))
    app = create_app()
    return TestClient(app)


def _make_fake_engine():
    class FakeEngine:
        def __init__(self, mcp=None, provider=None):
            pass

        async def run_turn(self, messages):
            from renpy_mcp.config import _current_project_path

            path = _current_project_path.get()
            return {
                "messages": [
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": str(path) if path else "NO_PROJECT"}],
                    }
                ],
            }

    return FakeEngine


def test_ws_chat_uses_payload_project_name(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """WebSocket should use project_name from payload even without session."""
    project_name = "payload_proj"
    game_dir = tmp_path / project_name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: type("P", (), {"complete": lambda **kw: []})(),
    )
    monkeypatch.setattr("renpy_mcp.web.chat_ws.ChatEngine", _make_fake_engine())

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "hi", "project_name": project_name})
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert project_name in data["delta"]


def test_ws_chat_no_project_guardrail(monkeypatch, client: TestClient) -> None:
    """When no project is set and message is not in whitelist, return error."""
    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: type("P", (), {"complete": lambda **kw: []})(),
    )
    monkeypatch.setattr("renpy_mcp.web.chat_ws.ChatEngine", _make_fake_engine())

    blocked_queries = [
        "build the web version",
        "create a background",
        "show assets",
        "status of current build",
    ]
    with client.websocket_connect("/ws/chat") as websocket:
        for query in blocked_queries:
            websocket.send_json({"type": "user_message", "content": query})
            data = websocket.receive_json()
            assert data["type"] == "error", f"Expected error for: {query}"
            assert "No active project" in data["message"], f"Wrong message for: {query}"


def test_ws_chat_allowed_without_project(monkeypatch, client: TestClient) -> None:
    """General chat queries in the whitelist are allowed without a project."""
    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: type("P", (), {"complete": lambda **kw: []})(),
    )
    monkeypatch.setattr("renpy_mcp.web.chat_ws.ChatEngine", _make_fake_engine())

    allowed_queries = ["hello", "help"]
    with client.websocket_connect("/ws/chat") as websocket:
        for query in allowed_queries:
            websocket.send_json({"type": "user_message", "content": query})
            data = websocket.receive_json()
            assert data["type"] == "assistant_delta", f"Expected delta for: {query}"
            assert data["delta"] == "NO_PROJECT", f"Wrong delta for: {query}"


def test_ws_chat_uses_session_project(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """WebSocket should pick up the current project from session at connect time."""
    project_name = "session_proj"
    game_dir = tmp_path / project_name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: type("P", (), {"complete": lambda **kw: []})(),
    )
    monkeypatch.setattr("renpy_mcp.web.chat_ws.ChatEngine", _make_fake_engine())

    # Select project via HTTP so the session cookie is set
    r = client.post("/api/projects/select", json={"name": project_name})
    assert r.status_code == 200

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "hi", "project_name": project_name})
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert project_name in data["delta"]


def test_ws_chat_switches_project_after_reconnect(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """After switching the session project, a new WebSocket connection must use the new project."""
    for name in ("proj_a", "proj_b"):
        game_dir = tmp_path / name / "game"
        game_dir.mkdir(parents=True)
        (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: type("P", (), {"complete": lambda **kw: []})(),
    )
    monkeypatch.setattr("renpy_mcp.web.chat_ws.ChatEngine", _make_fake_engine())

    # Select project A and chat
    r = client.post("/api/projects/select", json={"name": "proj_a"})
    assert r.status_code == 200

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "hi", "project_name": "proj_a"})
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert "proj_a" in data["delta"]

    # Switch to project B and open a new WebSocket
    r = client.post("/api/projects/select", json={"name": "proj_b"})
    assert r.status_code == 200

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "hi", "project_name": "proj_b"})
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert "proj_b" in data["delta"]


def test_ws_chat_mock_provider(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Test WebSocket chat with a mock provider to avoid real LLM calls."""
    from renpy_mcp.chat_engine.providers import AnthropicProvider

    # Create a dummy project so payload project_name resolves
    game_dir = tmp_path / "mock_proj" / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    class FakeMessages:
        def create(self, **kwargs):
            msg = type("M", (), {"content": [], "stop_reason": "end_turn", "usage": type("U", (), {"input_tokens": 5, "output_tokens": 5})()})()
            msg.content = [type("B", (), {"type": "text", "text": "Hello from mock"})()]
            return msg

    class FakeClient:
        messages = FakeMessages()

    provider = AnthropicProvider(api_key="fake")
    provider.client = FakeClient()

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: provider,
    )

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "hi", "project_name": "mock_proj"})
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert "Hello from mock" in data["delta"]


def test_ws_chat_injects_current_project_into_system_prompt(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """Project-bound chat should tell the model which current project is active."""
    from renpy_mcp.config import _current_project_path
    from renpy_mcp.web.chat_ws import _system_prompt_for_current_project

    project_name = "system_prompt_proj"
    project_dir = tmp_path / project_name
    game_dir = project_dir / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    class FakeEngine:
        system_prompt = "base prompt"

    token = _current_project_path.set(project_dir)
    try:
        prompt = _system_prompt_for_current_project(FakeEngine())
    finally:
        _current_project_path.reset(token)

    assert "already know the current project" in prompt.lower()
    assert project_name in prompt
    assert str(project_dir) in prompt
    assert "read the relevant project file" in prompt.lower()
    assert "do not claim a project file was modified" in prompt.lower()


def test_ws_chat_does_not_block_http_routes(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """A slow provider call should not block unrelated HTTP routes."""
    from renpy_mcp.chat_engine.providers import AnthropicProvider

    game_dir = tmp_path / "slow_proj" / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    started = threading.Event()

    class FakeMessages:
        def create(self, **kwargs):
            started.set()
            time.sleep(1.0)
            msg = type(
                "M",
                (),
                {
                    "content": [type("B", (), {"type": "text", "text": "slow reply"})()],
                    "stop_reason": "end_turn",
                    "usage": type("U", (), {"input_tokens": 5, "output_tokens": 5})(),
                },
            )()
            return msg

    class FakeClient:
        messages = FakeMessages()

    provider = AnthropicProvider(api_key="fake")
    provider.client = FakeClient()

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: provider)

    results: dict[str, object] = {}

    def _drive_socket() -> None:
        with client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json({"type": "user_message", "content": "hi", "project_name": "slow_proj"})
            results["ws"] = websocket.receive_json()

    worker = threading.Thread(target=_drive_socket)
    worker.start()
    assert started.wait(timeout=2.0), "provider did not start"

    start = time.perf_counter()
    response = client.get("/api/projects")
    elapsed = time.perf_counter() - start

    worker.join(timeout=3.0)

    assert response.status_code == 200
    assert elapsed < 0.5
    assert results["ws"]["type"] == "assistant_delta"


def test_ws_chat_no_provider(client: TestClient) -> None:
    """Test that WS closes immediately when no provider is configured."""
    import renpy_mcp.web.chat_ws as chat_ws

    original = chat_ws._get_provider
    chat_ws._get_provider = lambda: None
    try:
        with client.websocket_connect("/ws/chat") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "error"
    finally:
        chat_ws._get_provider = original


def test_ws_chat_tool_call(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Test a full tool-call turn via WebSocket."""
    from renpy_mcp.chat_engine.providers import AnthropicProvider

    game_dir = tmp_path / "tool_proj" / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    class FakeMessages:
        call_count = 0

        def create(self, **kwargs):
            self.call_count += 1
            msg = type(
                "M",
                (),
                {
                    "content": [],
                    "stop_reason": "tool_use" if self.call_count == 1 else "end_turn",
                    "usage": type("U", (), {"input_tokens": 5, "output_tokens": 5})(),
                },
            )()
            if self.call_count == 1:
                msg.content = [
                    type(
                        "B",
                        (),
                        {"type": "tool_use", "id": "call_1", "name": "list_projects", "input": {}},
                    )()
                ]
            else:
                msg.content = [type("B", (), {"type": "text", "text": "Done"})()]
            return msg

    class FakeClient:
        messages = FakeMessages()

    provider = AnthropicProvider(api_key="fake")
    provider.client = FakeClient()

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: provider,
    )

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "list projects", "project_name": "tool_proj"})

        # First response: tool_start
        data = websocket.receive_json()
        assert data["type"] == "tool_start"
        assert data["tool_name"] == "list_projects"

        # Second response: tool_result
        data = websocket.receive_json()
        assert data["type"] == "tool_result"
        assert data["result"]["success"] is True

        # Third response: assistant text
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert data["delta"] == "Done"


def test_ws_chat_only_streams_new_assistant_messages(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """Second turns should not replay assistant text that was already sent."""
    game_dir = tmp_path / "incremental_proj" / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: type("P", (), {"complete": lambda **kw: []})(),
    )

    class FakeEngine:
        def __init__(self, mcp=None, provider=None):
            self.turn = 0

        async def run_turn(self, messages):
            self.turn += 1
            if self.turn == 1:
                return {
                    "messages": [
                        {"role": "user", "content": "first"},
                        {
                            "role": "assistant",
                            "content": [{"type": "text", "text": "First reply"}],
                        },
                    ]
                }
            return {
                "messages": [
                    {"role": "user", "content": "first"},
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "First reply"}],
                    },
                    {"role": "user", "content": "second"},
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Second reply"}],
                    },
                ]
            }

    monkeypatch.setattr("renpy_mcp.web.chat_ws.ChatEngine", FakeEngine)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "hello", "project_name": "incremental_proj"})
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert data["delta"] == "First reply"

        websocket.send_json({"type": "user_message", "content": "hello again", "project_name": "incremental_proj"})
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert data["delta"] == "Second reply"


def test_ws_chat_persists_history_to_file(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """After a chat turn, the conversation should be persisted to disk and retrievable via API."""
    project_name = "persist_chat_proj"
    game_dir = tmp_path / project_name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: type("P", (), {"complete": lambda **kw: []})(),
    )

    class FakeEngine:
        def __init__(self, mcp=None, provider=None):
            pass

        async def run_turn(self, messages):
            return {
                "messages": [
                    {"role": "user", "content": "hello"},
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Persisted reply"}],
                    },
                ]
            }

    monkeypatch.setattr("renpy_mcp.web.chat_ws.ChatEngine", FakeEngine)

    # Select project so the history API accepts the request
    r = client.post("/api/projects/select", json={"name": project_name})
    assert r.status_code == 200

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "hello", "project_name": project_name})
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert data["delta"] == "Persisted reply"

    # Verify file was written
    history_file = tmp_path / project_name / "logs" / "chat-history.json"
    assert history_file.exists()
    raw = json.loads(history_file.read_text(encoding="utf-8"))
    assert any(m.get("role") == "user" and m.get("content") == "hello" for m in raw["messages"])
    assert any(
        m.get("role") == "assistant"
        and any(b.get("text") == "Persisted reply" for b in m.get("content", []))
        for m in raw["messages"]
    )

    # Verify API returns the persisted messages
    api_resp = client.get(f"/api/projects/{project_name}/chat/history")
    assert api_resp.status_code == 200
    api_data = api_resp.json()
    assert any(m.get("role") == "user" and m.get("content") == "hello" for m in api_data["messages"])
    assert any(
        m.get("role") == "assistant"
        and any(b.get("text") == "Persisted reply" for b in m.get("content", []))
        for m in api_data["messages"]
    )


def test_ws_chat_project_isolation(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Chat history for one project must not leak into another project's history file."""
    for name in ("proj_a", "proj_b"):
        game_dir = tmp_path / name / "game"
        game_dir.mkdir(parents=True)
        (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: type("P", (), {"complete": lambda **kw: []})(),
    )

    class FakeEngine:
        def __init__(self, mcp=None, provider=None):
            pass

        async def run_turn(self, messages):
            from renpy_mcp.config import _current_project_path
            path = _current_project_path.get()
            return {
                "messages": [
                    {"role": "user", "content": "hi"},
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": str(path.name) if path else "none"}],
                    },
                ]
            }

    monkeypatch.setattr("renpy_mcp.web.chat_ws.ChatEngine", FakeEngine)

    for name in ("proj_a", "proj_b"):
        r = client.post("/api/projects/select", json={"name": name})
        assert r.status_code == 200
        with client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json({"type": "user_message", "content": "hi", "project_name": name})
            websocket.receive_json()

    for name in ("proj_a", "proj_b"):
        history_file = tmp_path / name / "logs" / "chat-history.json"
        assert history_file.exists()
        data = json.loads(history_file.read_text(encoding="utf-8"))
        assert all(name in str(m.get("content", "")) for m in data["messages"] if m.get("role") == "assistant")

        other = "proj_b" if name == "proj_a" else "proj_a"
        assert not any(other in str(m.get("content", "")) for m in data["messages"] if m.get("role") == "assistant")


def test_ws_chat_persists_history_via_session_project(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """Even when frontend does not send project_name, history should be persisted using the session project."""
    project_name = "session_history_proj"
    game_dir = tmp_path / project_name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: type("P", (), {"complete": lambda **kw: []})(),
    )

    class FakeEngine:
        def __init__(self, mcp=None, provider=None):
            pass

        async def run_turn(self, messages):
            return {
                "messages": [
                    {"role": "user", "content": "hello session"},
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Session reply"}],
                    },
                ]
            }

    monkeypatch.setattr("renpy_mcp.web.chat_ws.ChatEngine", FakeEngine)

    r = client.post("/api/projects/select", json={"name": project_name})
    assert r.status_code == 200

    with client.websocket_connect("/ws/chat") as websocket:
        # intentionally omit project_name
        websocket.send_json({"type": "user_message", "content": "hello session"})
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert data["delta"] == "Session reply"

    history_file = tmp_path / project_name / "logs" / "chat-history.json"
    assert history_file.exists()
    raw = json.loads(history_file.read_text(encoding="utf-8"))
    assert any(m.get("role") == "user" and m.get("content") == "hello session" for m in raw["messages"])
    assert any(
        m.get("role") == "assistant"
        and any(b.get("text") == "Session reply" for b in m.get("content", []))
        for m in raw["messages"]
    )


def test_ws_chat_history_survives_app_recreate(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """History written via WS should be readable after recreating the app (simulating server restart)."""
    project_name = "restart_history_proj"
    game_dir = tmp_path / project_name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: type("P", (), {"complete": lambda **kw: []})(),
    )

    class FakeEngine:
        def __init__(self, mcp=None, provider=None):
            pass

        async def run_turn(self, messages):
            return {
                "messages": [
                    {"role": "user", "content": "write me"},
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Persisted across restart"}],
                    },
                ]
            }

    monkeypatch.setattr("renpy_mcp.web.chat_ws.ChatEngine", FakeEngine)

    r = client.post("/api/projects/select", json={"name": project_name})
    assert r.status_code == 200

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "write me", "project_name": project_name})
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"

    # Simulate server restart: recreate app and client
    new_app = create_app()
    new_client = TestClient(new_app)
    new_client.post("/api/projects/select", json={"name": project_name})

    r = new_client.get(f"/api/projects/{project_name}/chat/history")
    assert r.status_code == 200
    api_data = r.json()
    assert any(m.get("role") == "user" and m.get("content") == "write me" for m in api_data["messages"])
    assert any(
        m.get("role") == "assistant"
        and any(b.get("text") == "Persisted across restart" for b in m.get("content", []))
        for m in api_data["messages"]
    )
