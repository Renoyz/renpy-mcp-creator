"""Tests for scripts/download_web_support.py (manual web-support downloader)."""

from __future__ import annotations

import importlib.util
import io
import types
import zipfile
from pathlib import Path


def _load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "download_web_support.py"
    spec = importlib.util.spec_from_file_location("download_web_support", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_creates_missing_sdk_directory(tmp_path: Path, monkeypatch) -> None:
    """DEST's parent dir may not exist on a fresh machine; main() must create it."""
    module = _load_module()
    dest = tmp_path / "sdk" / "renpy-web.zip"  # parent intentionally missing
    sdk_dir = tmp_path / "sdk" / "renpy-8.3.4-sdk"  # intentionally missing
    monkeypatch.setattr(module, "DEST", dest)
    monkeypatch.setattr(module, "SDK_DIR", sdk_dir)
    monkeypatch.setattr(module, "LOG", tmp_path / "download.log")

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as zf:
        zf.writestr("web/dummy.txt", "ok")
    data = payload.getvalue()

    class _FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def iter_bytes(self, chunk_size: int = 8192):
            yield data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    fake_httpx = types.SimpleNamespace(stream=lambda *a, **k: _FakeResponse())
    monkeypatch.setattr(module, "httpx", fake_httpx)

    module.main()

    assert (sdk_dir / "web" / "dummy.txt").read_text(encoding="utf-8") == "ok"
    assert not dest.exists()
