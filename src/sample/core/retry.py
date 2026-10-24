"""Async retry helpers used by model backends and runners."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, Tuple, Type


class RetryableError(RuntimeError):
    """Base class for transient failures."""


class RetryableHTTPError(RetryableError):
    """A retryable HTTP failure carrying its status code.

    Lets callers bound retries per status (e.g. at most 2 retries for
    transient 503s) instead of retrying every retryable status alike.
    """

    def __init__(self, status: int, message: str = "") -> None:
        super().__init__(message or f"retryable http status {status}")
        self.status = status


class FatalBackendError(RuntimeError):
    """Raised when a backend fails after retries or in non-retryable ways."""


class QuotaExhaustedError(FatalBackendError):
    """Provider quota exhausted (HTTP 429).

    Non-retryable by construction: retrying a spent daily quota, switching
    keys, or switching models are all forbidden by the live-run stop rule,
    so this error must propagate immediately at every layer instead of
    being retried or wrapped into a generic failure.
    """


@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_sleep_sec: float = 1.0
    max_sleep_sec: float = 2.0
    jitter_sec: float = 0.2


async def retry_async(
    func: Callable[[], Awaitable[Any]],
    policy: RetryPolicy,
    *,
    logger: Optional[logging.Logger] = None,
    retry_on: Tuple[Type[BaseException], ...] = (RetryableError, asyncio.TimeoutError),
) -> Any:
    """Execute async function with exponential backoff.

    max_retries means additional attempts after the first attempt.
    """

    attempt = 0
    total_attempts = policy.max_retries + 1
    last_error: Optional[BaseException] = None

    while attempt < total_attempts:
        attempt += 1
        try:
            return await func()
        except retry_on as exc:
            last_error = exc
            if attempt >= total_attempts:
                break
            sleep_sec = min(policy.base_sleep_sec * (2 ** (attempt - 1)), policy.max_sleep_sec)
            sleep_sec += random.uniform(0.0, policy.jitter_sec)
            if logger:
                logger.warning(
                    "retryable failure: attempt=%s/%s, sleep=%.2fs, error=%s",
                    attempt,
                    total_attempts,
                    sleep_sec,
                    repr(exc),
                )
            await asyncio.sleep(sleep_sec)
        except FatalBackendError:
            # Already non-retryable (e.g. QuotaExhaustedError): propagate
            # unchanged so callers can recognize it instead of seeing a
            # generic wrapper.
            raise
        except BaseException as exc:
            raise FatalBackendError(f"non-retryable backend error: {exc!r}") from exc

    raise FatalBackendError(f"backend failed after {total_attempts} attempts: {last_error!r}") from last_error
