"""Tests for Gemini provider."""

from unittest.mock import MagicMock, patch

import pytest


class TestGetGeminiClient:
    """Tests for get_gemini_client."""

    def test_raises_when_api_key_missing(self) -> None:
        """Should raise GeminiProviderError when API key is None."""
        from renpy_mcp.ai.gemini_provider import GeminiProviderError, get_gemini_client

        with pytest.raises(GeminiProviderError, match="GEMINI_API_KEY"):
            get_gemini_client(None)

    def test_raises_when_api_key_empty(self) -> None:
        """Should raise GeminiProviderError when API key is empty string."""
        from renpy_mcp.ai.gemini_provider import GeminiProviderError, get_gemini_client

        with pytest.raises(GeminiProviderError, match="GEMINI_API_KEY"):
            get_gemini_client("")

    @patch("renpy_mcp.ai.gemini_provider.genai")
    def test_returns_client(self, mock_genai: MagicMock) -> None:
        """Should return a genai.Client instance."""
        from renpy_mcp.ai.gemini_provider import get_gemini_client

        mock_instance = MagicMock()
        mock_genai.Client.return_value = mock_instance

        client = get_gemini_client("test-key")
        assert client is mock_instance
        mock_genai.Client.assert_called_once_with(api_key="test-key")

    @patch("renpy_mcp.ai.gemini_provider.genai")
    def test_caches_client(self, mock_genai: MagicMock) -> None:
        """Should cache the client for the same API key."""
        from renpy_mcp.ai.gemini_provider import get_gemini_client

        mock_genai.Client.return_value = MagicMock()

        # Clear cache first (lru_cache on function)
        get_gemini_client.cache_clear()

        client1 = get_gemini_client("same-key")
        client2 = get_gemini_client("same-key")

        assert client1 is client2
        mock_genai.Client.assert_called_once()
