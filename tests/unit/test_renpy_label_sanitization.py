"""Ren'Py label names must be valid identifiers (Python identifier rules).

Real-run evidence (2026-07-19): the stepwise flow built labels like
``prototype_ch1_1_ch1_1-s1`` from hyphenated scene ids, and the real Ren'Py
SDK build failed with ``expected ':' not found``. Sanitizing at the
``PrototypeScene`` model covers every construction site (stepwise, scene
generation, chapter wiring).
"""

from __future__ import annotations

from renpy_mcp.services.prototype_generation_service import (
    PrototypeScene,
    sanitize_renpy_label,
)


def _scene(entry_label: str) -> PrototypeScene:
    return PrototypeScene(
        scene_id="s1",
        title="t",
        summary="s",
        location="l",
        entry_label=entry_label,
    )


def test_sanitize_renpy_label_replaces_hyphens() -> None:
    assert sanitize_renpy_label("prototype_ch1_1_ch1_1-s1") == "prototype_ch1_1_ch1_1_s1"


def test_sanitize_renpy_label_handles_leading_digit_and_punctuation() -> None:
    assert sanitize_renpy_label("1st scene.x") == "_1st_scene_x"


def test_sanitize_renpy_label_replaces_non_ascii() -> None:
    assert sanitize_renpy_label("场景-1") == "___1"


def test_prototype_scene_entry_label_is_sanitized() -> None:
    scene = _scene("prototype_ch1_1_ch1_1-s2_start")
    assert scene.entry_label == "prototype_ch1_1_ch1_1_s2_start"
