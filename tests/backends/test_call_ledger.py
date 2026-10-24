"""Call-ledger tests (Item 2a, 2026-10-24).

The ledger records one entry per chat-completion attempt through
OpenAIStyleBackend.chat_text, with metadata only (purpose, model,
status, finish reason, response length). These tests use a fake
client, so no network or API key is involved.

A fake client is required because the backend is constructed without
__init__ (which would build a real AsyncOpenAI client): only
_settings, _logger, and .client are needed by chat_text.
"""

import asyncio
import logging
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.backends.base import BackendSettings
from sample.backends.call_ledger import (
    DEFAULT_LEDGER,
    ledger_summary,
    reset_ledger,
)
from sample.backends.openai_api import OpenAIStyleBackend


@pytest.fixture(autouse=True)
def _clean_ledger():
    reset_ledger()
    yield
    reset_ledger()


def _backend(fake_client, **settings_kw):
    be = object.__new__(OpenAIStyleBackend)
    settings = BackendSettings(
        model="gemini-3.8-flash",
        temperature=0.7,
        max_tokens=1024,
        timeout_sec=60,
        max_retries=0,
        retry_sleep_sec=0.0,
        **settings_kw,
    )
    be._settings = settings
    be._logger = logging.getLogger("test_ledger")
    be.client = fake_client
    return be


class _Completions:
    def __init__(self, behavior):
        self.behavior = behavior
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        return self.behavior()


class _Chat:
    def __init__(self, behavior):
        self.completions = _Completions(behavior)


class _FakeClient:
    def __init__(self, behavior):
        self.chat = _Chat(behavior)


def _ok_response():
    return {"choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}]}


class _FakeTimeout(Exception):
    pass


class _FakeConnection(Exception):
    pass


class _FakeStatus(Exception):
    """Distinct from _FakeTimeout: without the openai package installed,
    the module's APITimeoutError/APIStatusError aliases collapse to one
    class, so the test installs distinct stand-ins (see below)."""

    def __init__(self, status_code):
        self.status_code = status_code
        self.response = None
        super().__init__(f"{status_code} quota exhausted")


def test_success_recorded_with_purpose_model_and_finish_reason():
    be = _backend(_FakeClient(_ok_response))
    text = asyncio.run(be.chat_text(messages=[{"role": "user", "content": "hi"}],
                                    ledger_purpose="counseling"))
    assert text == "hello"
    records = DEFAULT_LEDGER.records()
    assert len(records) == 1
    rec = records[0]
    assert rec.purpose == "counseling"
    assert rec.model == "gemini-3.8-flash"
    assert rec.status == "ok"
    assert rec.finish_reason == "stop"
    assert rec.response_chars == 5
    # Metadata only: no record field can carry prompt or response text.
    assert "hello" not in (rec.purpose, rec.model, rec.status, rec.finish_reason)


def test_default_purpose_is_chat():
    be = _backend(_FakeClient(_ok_response))
    asyncio.run(be.chat_text(messages=[{"role": "user", "content": "hi"}]))
    assert DEFAULT_LEDGER.records()[0].purpose == "chat"


def test_429_recorded_once_with_status_and_no_retry_when_max_retries_zero(monkeypatch):
    import sample.backends.openai_api as mod

    # Install distinct exception classes: with no openai package, the
    # module's APITimeoutError/APIStatusError are the same fallback class
    # and the timeout branch would swallow the status error.
    monkeypatch.setattr(mod, "APITimeoutError", _FakeTimeout)
    monkeypatch.setattr(mod, "APIConnectionError", _FakeConnection)
    monkeypatch.setattr(mod, "APIStatusError", _FakeStatus)

    def _raise():
        raise _FakeStatus(429)

    be = _backend(_FakeClient(_raise))
    with pytest.raises(Exception, match="retryable http status 429"):
        asyncio.run(be.chat_text(messages=[{"role": "user", "content": "hi"}],
                                 ledger_purpose="counseling"))
    records = DEFAULT_LEDGER.records()
    assert len(records) == 1
    assert records[0].status == "429"
    assert records[0].purpose == "counseling"
    assert records[0].finish_reason is None


def test_summary_counts_by_purpose_status_and_model():
    be = _backend(_FakeClient(_ok_response))
    asyncio.run(be.chat_text(messages=[{"role": "user", "content": "a"}], ledger_purpose="counseling"))
    asyncio.run(be.chat_text(messages=[{"role": "user", "content": "b"}], ledger_purpose="skill_coarse_filter"))
    summary = ledger_summary()
    assert summary["total"] == 2
    assert summary["by_purpose"] == {"counseling": 1, "skill_coarse_filter": 1}
    assert summary["by_status"] == {"ok": 2}
    assert summary["by_model"] == {"gemini-3.8-flash": 2}
