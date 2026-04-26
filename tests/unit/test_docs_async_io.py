"""TDD: docs.py _extract_doc_text offloads I/O via asyncio.to_thread."""
import asyncio
import inspect

import pytest


@pytest.mark.asyncio
async def test_extract_doc_text_is_async():
    """_extract_doc_text must be a coroutine function."""
    from renpy_mcp.resources.docs import _extract_doc_text
    assert asyncio.iscoroutinefunction(_extract_doc_text)


def test_extract_doc_text_uses_to_thread():
    """_extract_doc_text must use asyncio.to_thread to avoid blocking event loop."""
    from renpy_mcp.resources import docs
    source = inspect.getsource(docs._extract_doc_text)
    assert "to_thread" in source, (
        "_extract_doc_text must use asyncio.to_thread to avoid blocking event loop"
    )
