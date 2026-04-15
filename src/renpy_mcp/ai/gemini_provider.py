"""Shared helpers for interacting with the Google Gemini API."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

try:
    from google import genai
except Exception:  # pragma: no cover - optional dependency
    genai = None  # type: ignore[assignment]


class GeminiProviderError(RuntimeError):
    """Raised when the Gemini client cannot be initialized."""


@lru_cache(maxsize=1)
def get_gemini_client(api_key: Optional[str]) -> "genai.Client":
    """Return a cached Gemini client for the given API key."""
    if not api_key:
        raise GeminiProviderError(
            "GEMINI_API_KEY is not configured. Set the environment variable or update settings."
        )
    if genai is None:
        raise GeminiProviderError(
            "google-genai package is not installed. Install it to use Gemini features."
        )
    return genai.Client(api_key=api_key)
