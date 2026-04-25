"""Tests for with_async_retry utility."""

import asyncio
from typing import Any

import pytest

from renpy_mcp.utils.retry import with_async_retry


class TestWithAsyncRetry:
    async def test_success_no_retry(self) -> None:
        call_count = 0

        async def _op() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await with_async_retry(_op)
        assert result == "ok"
        assert call_count == 1

    async def test_retry_then_success(self) -> None:
        call_count = 0

        async def _op() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"fail {call_count}")
            return "ok"

        result = await with_async_retry(_op, max_retries=3)
        assert result == "ok"
        assert call_count == 3

    async def test_retry_exhausted_raises_last_error(self) -> None:
        call_count = 0

        async def _op() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError(f"attempt {call_count}")

        with pytest.raises(RuntimeError, match="attempt 3"):
            await with_async_retry(_op, max_retries=2)
        assert call_count == 3

    async def test_non_retryable_exception_raises_immediately(self) -> None:
        call_count = 0

        async def _op() -> str:
            nonlocal call_count
            call_count += 1
            raise KeyError("immediate")

        with pytest.raises(KeyError, match="immediate"):
            await with_async_retry(_op, retryable=(ValueError,))
        assert call_count == 1

    async def test_on_retry_callback_invoked(self) -> None:
        call_count = 0
        errors: list[tuple[Exception, int]] = []

        async def _op() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"fail {call_count}")
            return "ok"

        def _on_retry(exc: Exception, attempt: int) -> None:
            errors.append((exc, attempt))

        result = await with_async_retry(_op, max_retries=3, on_retry=_on_retry)
        assert result == "ok"
        assert call_count == 3
        assert len(errors) == 2
        assert str(errors[0][0]) == "fail 1"
        assert errors[0][1] == 0
        assert str(errors[1][0]) == "fail 2"
        assert errors[1][1] == 1

    async def test_zero_retries(self) -> None:
        call_count = 0

        async def _op() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(ValueError, match="fail"):
            await with_async_retry(_op, max_retries=0)
        assert call_count == 1
