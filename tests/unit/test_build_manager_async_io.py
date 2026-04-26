"""TDD: build_manager.py uses asyncio.to_thread for sync I/O."""
import inspect


def test_build_errors_txt_uses_to_thread():
    """async build() must use asyncio.to_thread for errors.txt read_text."""
    from renpy_mcp.services.build_manager import LocalRenpyToolchain
    source = inspect.getsource(LocalRenpyToolchain.build)
    assert "to_thread" in source, (
        "async build() must use asyncio.to_thread for I/O calls"
    )
