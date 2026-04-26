"""TDD: verify _write_build_status is unified — only one implementation exists."""
import inspect


def test_write_build_status_only_exists_in_fastapi_app():
    """_write_build_status should only be defined in fastapi_app, not chat_ws."""
    from renpy_mcp.web import chat_ws
    from renpy_mcp.web import fastapi_app

    assert hasattr(fastapi_app, "_write_build_status"), "fastapi_app must have _write_build_status"
    assert not hasattr(chat_ws, "_write_build_status_for_project"), (
        "chat_ws._write_build_status_for_project must be removed — use fastapi_app._write_build_status"
    )


def test_write_build_status_previewable_uses_previewable_output_path():
    """previewable field is computed via _previewable_output_path, not ad-hoc path check."""
    from renpy_mcp.web.fastapi_app import _write_build_status

    source = inspect.getsource(_write_build_status)
    assert "_previewable_output_path" in source, (
        "previewable must be computed via _previewable_output_path() for consistency"
    )
