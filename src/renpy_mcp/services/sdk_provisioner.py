"""SdkProvisioner: auto-download and extract Ren'Py SDK."""

from __future__ import annotations

import asyncio
import os
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Callable

import httpx

from renpy_mcp.config import Settings, get_settings


class SdkProvisioner:
    """Manage Ren'Py SDK download, extraction, and path configuration."""

    DEFAULT_OFFICIAL_URL = "https://www.renpy.org/dl/8.3.4/renpy-8.3.4-sdk.zip"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._install_dir = self.settings.workspace.parent / "sdk"

    def is_sdk_ready(self, sdk_path: Path | None = None) -> bool:
        """Check if Ren'Py SDK is already installed and valid."""
        path = sdk_path or self.settings.renpy_sdk_path
        if not path:
            return False
        exe = path / ("renpy.exe" if os.name == "nt" else "renpy.sh")
        return exe.exists()

    def resolve_sdk_path(self) -> Path | None:
        """Return the effective SDK path, or None if not configured."""
        if self.settings.renpy_sdk_path:
            return self.settings.renpy_sdk_path
        env = os.environ.get("RENPY_SDK_PATH")
        if env:
            return Path(env)
        return None

    async def ensure_sdk(
        self,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> Path:
        """Ensure SDK is available, downloading if necessary.

        Returns the absolute path to the SDK directory.
        Raises RuntimeError if download or extraction fails.
        """
        existing = self.resolve_sdk_path()
        if existing and self.is_sdk_ready(existing):
            return existing.resolve()

        # Check if already installed in default location
        default_path = self._install_dir / "renpy-8.3.4-sdk"
        if self.is_sdk_ready(default_path):
            self._update_sdk_path(default_path)
            return default_path.resolve()

        # Need to download
        url = self.settings.renpy_sdk_mirror or self.DEFAULT_OFFICIAL_URL
        archive_path = self._install_dir / "sdk_download.zip"
        self._install_dir.mkdir(parents=True, exist_ok=True)

        await self._download(url, archive_path, progress_callback)
        extracted = self._extract(archive_path, self._install_dir, progress_callback)

        # Clean up archive
        archive_path.unlink(missing_ok=True)

        # Find the actual SDK folder inside extracted contents
        sdk_path = self._find_sdk_root(extracted)
        if sdk_path is None:
            raise RuntimeError("Extracted archive does not contain a valid Ren'Py SDK")

        self._update_sdk_path(sdk_path)
        return sdk_path.resolve()

    async def _download(
        self,
        url: str,
        dest: Path,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> None:
        def _report(stage: str, percent: float) -> None:
            if progress_callback:
                progress_callback(stage, percent)

        _report("downloading", 0.0)

        async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length", 0))
                downloaded = 0

                with open(dest, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            _report("downloading", downloaded / total)

        _report("downloading", 1.0)

    def _extract(
        self,
        archive: Path,
        dest: Path,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> Path:
        def _report(stage: str, percent: float) -> None:
            if progress_callback:
                progress_callback(stage, percent)

        _report("extracting", 0.0)

        if archive.suffix == ".zip" or str(archive).endswith(".zip"):
            with zipfile.ZipFile(archive, "r") as zf:
                zf.extractall(dest)
        elif archive.suffixes == [".tar", ".gz"] or str(archive).endswith(".tar.gz"):
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(dest)
        else:
            # Fallback: try zip
            with zipfile.ZipFile(archive, "r") as zf:
                zf.extractall(dest)

        _report("extracting", 1.0)
        return dest

    def _find_sdk_root(self, extracted_dir: Path) -> Path | None:
        """Locate the actual SDK directory inside extracted contents."""
        exe_name = "renpy.exe" if os.name == "nt" else "renpy.sh"

        # If extraction created a single top-level directory, use it
        entries = [e for e in extracted_dir.iterdir() if e.is_dir()]
        if len(entries) == 1:
            candidate = entries[0]
            exe = candidate / exe_name
            if exe.exists():
                return candidate

        # Otherwise check the extracted dir itself
        exe = extracted_dir / exe_name
        if exe.exists():
            return extracted_dir

        # Search up to two levels deep
        for subdir in extracted_dir.rglob("*/"):
            # Limit depth to 2 levels below extracted_dir
            depth = len(subdir.relative_to(extracted_dir).parts)
            if depth > 2:
                continue
            exe = subdir / exe_name
            if exe.exists():
                return subdir
        return None

    def _update_sdk_path(self, sdk_path: Path) -> None:
        """Update settings and .env file with the new SDK path."""
        self.settings.renpy_sdk_path = sdk_path
        os.environ["RENPY_SDK_PATH"] = str(sdk_path)

        # Update .env file if it exists in project root
        env_file = Path(__file__).resolve().parent.parent.parent.parent / ".env"
        if env_file.exists():
            lines = env_file.read_text(encoding="utf-8").splitlines()
            found = False
            for i, line in enumerate(lines):
                if line.startswith("RENPY_SDK_PATH="):
                    lines[i] = f"RENPY_SDK_PATH={sdk_path}"
                    found = True
                    break
            if not found:
                lines.append(f"RENPY_SDK_PATH={sdk_path}")
            env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
