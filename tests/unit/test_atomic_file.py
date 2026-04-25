"""Tests for transactional_write context manager."""

from pathlib import Path

import pytest

from renpy_mcp.utils.atomic_file import transactional_write


class TestTransactionalWrite:
    def test_successful_write_no_rollback(self, tmp_path: Path) -> None:
        target = tmp_path / "file.txt"
        target.write_text("original", encoding="utf-8")

        with transactional_write(target):
            target.write_text("modified", encoding="utf-8")

        assert target.read_text(encoding="utf-8") == "modified"

    def test_rollback_restores_original_content(self, tmp_path: Path) -> None:
        target = tmp_path / "file.txt"
        target.write_text("original", encoding="utf-8")

        with pytest.raises(RuntimeError, match="boom"):
            with transactional_write(target):
                target.write_text("modified", encoding="utf-8")
                raise RuntimeError("boom")

        assert target.read_text(encoding="utf-8") == "original"

    def test_rollback_deletes_newly_created_file(self, tmp_path: Path) -> None:
        target = tmp_path / "new_file.txt"
        assert not target.exists()

        with pytest.raises(RuntimeError, match="boom"):
            with transactional_write(target):
                target.write_text("new content", encoding="utf-8")
                raise RuntimeError("boom")

        assert not target.exists()

    def test_rollback_restores_multiple_files(self, tmp_path: Path) -> None:
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("a-original", encoding="utf-8")
        b.write_text("b-original", encoding="utf-8")

        with pytest.raises(RuntimeError, match="boom"):
            with transactional_write(a, b):
                a.write_text("a-modified", encoding="utf-8")
                b.write_text("b-modified", encoding="utf-8")
                raise RuntimeError("boom")

        assert a.read_text(encoding="utf-8") == "a-original"
        assert b.read_text(encoding="utf-8") == "b-original"

    def test_rollback_mixed_existing_and_new_files(self, tmp_path: Path) -> None:
        existing = tmp_path / "existing.txt"
        new_file = tmp_path / "new.txt"
        existing.write_text("existing-original", encoding="utf-8")

        with pytest.raises(RuntimeError, match="boom"):
            with transactional_write(existing, new_file):
                existing.write_text("existing-modified", encoding="utf-8")
                new_file.write_text("new-content", encoding="utf-8")
                raise RuntimeError("boom")

        assert existing.read_text(encoding="utf-8") == "existing-original"
        assert not new_file.exists()

    def test_exception_propagates_after_rollback(self, tmp_path: Path) -> None:
        target = tmp_path / "file.txt"
        target.write_text("original", encoding="utf-8")

        class CustomError(Exception):
            pass

        with pytest.raises(CustomError, match="specific error"):
            with transactional_write(target):
                target.write_text("modified", encoding="utf-8")
                raise CustomError("specific error")

        assert target.read_text(encoding="utf-8") == "original"
