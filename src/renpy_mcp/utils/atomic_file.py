"""Atomic file operations with transactional rollback."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator


@contextmanager
def transactional_write(*paths: Path) -> Generator[None, None, None]:
    """Capture file contents before a block and restore them if an exception occurs.

    For each *path*:
    - If the file exists, its text content is snapshotted before entering the block.
    - If the file does not exist, it is recorded as ``None``.

    If the wrapped block raises an exception, every snapshotted path is restored:
    - Files that existed are rewritten with their original content.
    - Files that did not exist are deleted (``missing_ok=True``).

    The original exception is re-raised after rollback so that callers can wrap or
    log it as needed.

    Example::

        try:
            with transactional_write(path_a, path_b):
                path_a.write_text("new a")
                path_b.write_text("new b")
        except Exception as exc:
            # Both files have been rolled back to their original state.
            raise HTTPException(status_code=500, detail=str(exc))
    """
    snapshots: dict[Path, str | None] = {}
    for path in paths:
        snapshots[path] = path.read_text(encoding="utf-8") if path.exists() else None

    try:
        yield
    except Exception:
        for path, old_text in snapshots.items():
            if old_text is not None:
                path.write_text(old_text, encoding="utf-8")
            else:
                path.unlink(missing_ok=True)
        raise
