import json
import shutil
from pathlib import Path
from typing import Any


class ArtifactWriter:
    def __init__(self, root: Path, run_id: str) -> None:
        self.root = root
        self.run_id = run_id
        self.run_dir = root / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, filename: str) -> Path:
        return self.run_dir / filename

    def capture_page(self, page: Any, step_id: str, note: str | None = None) -> Path:
        screenshot_path = self.run_dir / f"{step_id}.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        self.write_text(step_id, "page", page.content(), suffix=".html")
        if note is not None:
            self.write_text(step_id, "notes", note)
        return screenshot_path

    def write_json(self, step_id: str, name: str, payload: dict[str, Any]) -> Path:
        path = self.run_dir / f"{step_id}.{name}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def write_text(self, step_id: str, name: str, text: str, *, suffix: str = ".txt") -> Path:
        path = self.run_dir / f"{step_id}.{name}{suffix}"
        path.write_text(text, encoding="utf-8")
        return path

    def write_root_text(self, filename: str, text: str) -> Path:
        path = self.path_for(filename)
        path.write_text(text, encoding="utf-8")
        return path

    def write_markdown(self, filename: str, text: str) -> Path:
        return self.write_root_text(filename, text)

    def copy_file(self, source: Path, filename: str | None = None) -> Path:
        target = self.path_for(filename or source.name)
        shutil.copyfile(source, target)
        return target
