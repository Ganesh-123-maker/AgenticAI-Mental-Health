"""HTTP retry-policy tests (Item 3c, 2026-10-24).

- Transient 503s: bounded retry, at most 2 retries with backoff, then a
  fatal error. A 503 followed by success must succeed.
- Quota 429s: hard stop. QuotaExhaustedError propagates immediately
  with exactly one ledger record, even with max_retries=3, and the
  runner layer must not retry it either.

Fake clients are used throughout: no network, no API key. Because the
openai package is not installed here, the module's APITimeoutError /
APIStatusError aliases collapse to one fallback class, so the tests
install distinct stand-in exception classes via monkeypatch.
"""

import asyncio
import logging
import pathlib
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.backends.base import BackendSettings
from sample.backends.call_ledger import DEFAULT_LEDGER, reset_ledger
from sample.backends.openai_api import OpenAIStyleBackend
from sample.core.retry import FatalBackendError, QuotaExhaustedError


@pytest.fixture(autouse=True)
def _clean_ledger():
    reset_ledger()
    yield
    reset_ledger()


class _FakeTimeout(Exception):
    pass


class _FakeConnection(Exception):
    pass


class _FakeStatus(Exception):
    def __init__(self, status_code):
        self.status_code = status_code
        self.response = None
        super().__init__(f"{status_code}")


@pytest.fixture()
def _distinct_errors(monkeypatch):
    import sample.backends.openai_api as mod

    monkeypatch.setattr(mod, "APITimeoutError", _FakeTimeout)
    monkeypatch.setattr(mod, "APIConnectionError", _FakeConnection)
    monkeypatch.setattr(mod, "APIStatusError", _FakeStatus)


class _Completions:
    def __init__(self, behavior):
        self.behavior = behavior
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        return self.behavior(self.calls)


class _FakeClient:
    def __init__(self, behavior):
        self.chat = SimpleNamespace(completions=_Completions(behavior))


def _backend(fake_client, max_retries=3):
    be = object.__new__(OpenAIStyleBackend)
    be._settings = BackendSettings(
        model="gemini-3.8-flash",
        temperature=0.7,
        max_tokens=1024,
        timeout_sec=60,
        max_retries=max_retries,
        retry_sleep_sec=0.0,
    )
    be._logger = logging.getLogger("test_http_retry")
    be.client = fake_client
    return be


def _ok_response():
    return {"choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}]}


def test_503_then_success_succeeds_within_retry_budget(_distinct_errors):
    def behavior(call):
        if call <= 2:
            raise _FakeStatus(503)
        return _ok_response()

    be = _backend(_FakeClient(behavior))
    text = asyncio.run(be.chat_text(messages=[{"role": "user", "content": "hi"}],
                                    ledger_purpose="counseling"))
    assert text == "hello"
    statuses = [r.status for r in DEFAULT_LEDGER.records()]
    assert statuses == ["503", "503", "ok"]


def test_persistent_503_fails_after_exactly_two_retries(_distinct_errors):
    def behavior(call):
        raise _FakeStatus(503)

    be = _backend(_FakeClient(behavior))
    with pytest.raises(FatalBackendError, match="503 persisted after 2 retries"):
        asyncio.run(be.chat_text(messages=[{"role": "user", "content": "hi"}],
                                 ledger_purpose="counseling"))
    records = DEFAULT_LEDGER.records()
    assert len(records) == 3
    assert all(r.status == "503" for r in records)


def test_429_is_a_hard_stop_with_one_ledger_record(_distinct_errors):
    def behavior(call):
        raise _FakeStatus(429)

    be = _backend(_FakeClient(behavior))
    with pytest.raises(QuotaExhaustedError, match="quota exhausted"):
        asyncio.run(be.chat_text(messages=[{"role": "user", "content": "hi"}],
                                 ledger_purpose="counseling"))
    records = DEFAULT_LEDGER.records()
    assert len(records) == 1
    assert records[0].status == "429"


def test_runner_does_not_retry_quota_exhaustion():
    """PsychAgentRunner._chat_with_retry re-raises QuotaExhaustedError at once."""
    from sample.runner import PsychAgentRunner as Runner

    calls = []

    class _QuotaBackend:
        async def chat_text(self, **kwargs):
            calls.append(1)
            raise QuotaExhaustedError("quota exhausted: http status 429")

    runner = object.__new__(Runner)
    runner.runtime_config = SimpleNamespace(
        psychagent_max_retries=16, psychagent_retry_sleep_sec=0.0,
        output_language="English",
    )
    runner.baseline_config = SimpleNamespace(
        model="gemini-3.8-flash", temperature=0.7, max_tokens=1024,
        timeout_sec=60, max_retries=0, retry_sleep_sec=0.0,
        end_token="<end>",
    )
    runner._logger = logging.getLogger("test_runner_quota")
    with pytest.raises(QuotaExhaustedError):
        asyncio.run(runner._chat_with_retry(
            _QuotaBackend(), [{"role": "user", "content": "hi"}], "[test] turn",
            purpose="counseling",
        ))
    assert len(calls) == 1
