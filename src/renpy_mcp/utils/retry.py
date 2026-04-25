"""Async retry utilities."""

from __future__ import annotations

from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


async def with_async_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 2,
    retryable: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
) -> T:
    """Execute an async operation with configurable retry logic.

    Args:
        operation: Async callable that performs the work.
        max_retries: Number of retry attempts after the first failure.
                     Total attempts = ``1 + max_retries``.
        retryable: Exception types that should trigger a retry.
                   Other exceptions are re-raised immediately.
        on_retry: Optional callback invoked before each retry with
                  ``(exception, attempt_index)`` where ``attempt_index``
                  is 0-based and counts only failed attempts.

    Returns:
        The result of the first successful ``operation()`` call.

    Raises:
        The last exception raised by ``operation`` if all retries are exhausted.
    """
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except retryable as exc:
            last_error = exc
            if attempt < max_retries:
                if on_retry is not None:
                    on_retry(exc, attempt)
                continue
            raise
    # Unreachable — the loop always either returns or raises.
    raise last_error  # pragma: no cover
