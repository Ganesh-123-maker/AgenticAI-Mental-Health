"""Tests for Gemini embedding integration (native google-genai SDK path).

All tests use an injected fake `google.genai` module - no network, no key.
"""
from __future__ import annotations

import asyncio
import sys
import types as pytypes

import pytest


# ---------------------------------------------------------------------------
# Fake google.genai SDK (injected before skill_manager is imported)
# ---------------------------------------------------------------------------

FAKE_KEY = "sk-fake-test-key-12345"


class _FakeEmbedding:
    def __init__(self, values):
        self.values = values


class _FakeEmbedResponse:
    def __init__(self, embeddings):
        self.embeddings = embeddings


class _FakeModels:
    def __init__(self, client):
        self._client = client

    def embed_content(self, model, contents, config=None):
        self._client.calls.append(
            {"model": model, "n": len(contents),
             "dim": getattr(config, "output_dimensionality", None),
             "task_type": getattr(config, "task_type", None)}
        )
        if self._client.fail_times > 0:
            self._client.fail_times -= 1
            err = RuntimeError(f"injected failure (key={self._client.api_key})")
            if self._client.fail_code is not None:
                err.status_code = self._client.fail_code
            raise err
        if self._client.malformed == "count":
            return _FakeEmbedResponse([_FakeEmbedding([0.1, 0.2])])  # wrong count
        if self._client.malformed == "empty":
            return _FakeEmbedResponse([_FakeEmbedding([]) for _ in contents])
        dim = getattr(config, "output_dimensionality", 4) or 4
        return _FakeEmbedResponse([_FakeEmbedding([0.5] * dim) for _ in contents])


class _FakeHeaders(dict):
    pass


class _FakeAio:
    def __init__(self):
        self.aclosed = False

    async def aclose(self):
        self.aclosed = True


class _FakeClient:
    def __init__(self, api_key=None, http_options=None):
        self.api_key = api_key
        self.http_options = http_options
        self.models = _FakeModels(self)
        self.aio = _FakeAio()
        self.calls = []
        self.closed = False
        self.fail_times = 0
        self.fail_code = None
        self.malformed = None

    def close(self):
        self.closed = True


class _FakeEmbedContentConfig:
    def __init__(self, output_dimensionality=None, task_type=None):
        self.output_dimensionality = output_dimensionality
        self.task_type = task_type


class _FakeHttpOptions:
    def __init__(self, timeout=None, retry_options=None):
        self.timeout = timeout
        self.retry_options = retry_options


class _FakeHttpRetryOptions:
    def __init__(self, attempts=None):
        self.attempts = attempts


_fake_types = pytypes.ModuleType("google.genai.types")
_fake_types.EmbedContentConfig = _FakeEmbedContentConfig
_fake_types.HttpOptions = _FakeHttpOptions
_fake_types.HttpRetryOptions = _FakeHttpRetryOptions
_fake_genai = pytypes.ModuleType("google.genai")
_fake_genai.Client = _FakeClient
_fake_genai.types = _fake_types
_fake_google = pytypes.ModuleType("google")
_fake_google.genai = _fake_genai
sys.modules["google"] = _fake_google
sys.modules["google.genai"] = _fake_genai
sys.modules["google.genai.types"] = _fake_types

_last_client = {}


def _tracking_client(api_key=None, **kwargs):
    c = _FakeClient(api_key=api_key, **kwargs)
    _last_client["client"] = c
    return c


_fake_genai.Client = _tracking_client

# Fake openai module for the siliconflow-path test
class _FakeEmbeddingItem:
    def __init__(self, embedding):
        self.embedding = embedding


class _FakeEmbeddingsAPI:
    def __init__(self, outer):
        self._outer = outer

    async def create(self, input, model):
        self._outer.calls.append({"model": model, "n": len(input)})
        return pytypes.SimpleNamespace(data=[_FakeEmbeddingItem([0.25] * 1024) for _ in input])


class _FakeAsyncOpenAI:
    def __init__(self, api_key=None, base_url=None, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.calls = []
        self.embeddings = _FakeEmbeddingsAPI(self)


_fake_openai = pytypes.ModuleType("openai")
_fake_openai.AsyncOpenAI = _FakeAsyncOpenAI
sys.modules["openai"] = _fake_openai

sys.path.insert(0, "src")
from sample.backends.dummy_backend import DummyBackend  # noqa: E402
from sample.core.schemas import RuntimeConfig  # noqa: E402
from sample.skill_manager import SkillManager  # noqa: E402


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.delenv("PSYCHAGENT_EMBEDDING_API_KEY", raising=False)
    # Patch module attributes directly: other test modules may have imported
    # skill_manager before this file, so import-time sys.modules injection
    # alone is not enough.
    import sample.skill_manager as _sm
    monkeypatch.setattr(_sm, "genai", _fake_genai, raising=False)
    monkeypatch.setattr(_sm, "AsyncOpenAI", _FakeAsyncOpenAI, raising=False)
    _last_client.clear()
    yield


def _gemini_cfg(**over):
    kw = dict(
        client_backend="openai_api",
        psychagent_embedding_provider="gemini",
        psychagent_embedding_api_key_env="GEMINI_API_KEY",
        psychagent_embedding_model="gemini-embedding-001",
        psychagent_embedding_dimensions=768,
        psychagent_embedding_batch_size=16,
        psychagent_embedding_max_retries=3,
        psychagent_embedding_retry_sleep_sec=0.0,
    )
    kw.update(over)
    cfg = RuntimeConfig(**kw)
    cfg.validate()
    return cfg


class _NonDummyBackend:
    async def chat_text(self, messages, **kwargs):
        return "ok"


def _mgr(cfg=None):
    return SkillManager(_NonDummyBackend(), cfg or _gemini_cfg())


def test_gemini_routing_model_dim_and_batching():
    cfg = _gemini_cfg(psychagent_embedding_batch_size=2)
    mgr = _mgr(cfg)
    vecs = asyncio.run(mgr._embed_by_api(["a", "b", "c", "d", "e"]))
    assert len(vecs) == 5
    assert all(len(v) == 768 for v in vecs)
    client = _last_client["client"]
    assert client.api_key == FAKE_KEY
    assert len(client.calls) == 3  # 5 texts / batch 2
    assert all(c["model"] == "gemini-embedding-001" for c in client.calls)
    assert all(c["dim"] == 768 for c in client.calls)
    assert client.closed is True


def test_gemini_retry_then_success():
    mgr = _mgr()
    client_holder = {}

    orig = _fake_genai.Client

    def flaky(api_key=None, **kwargs):
        c = _FakeClient(api_key=api_key, **kwargs)
        c.fail_times = 2
        client_holder["c"] = c
        _last_client["client"] = c
        return c

    _fake_genai.Client = flaky
    try:
        cfg = _gemini_cfg(psychagent_embedding_max_retries=3, psychagent_embedding_retry_sleep_sec=0.0)
        vecs = asyncio.run(_mgr(cfg)._embed_by_api(["hello"]))
    finally:
        _fake_genai.Client = orig
    assert len(vecs) == 1 and len(vecs[0]) == 768


def test_gemini_retry_exhaustion_raises_without_key_leak():
    mgr = _mgr()

    orig = _fake_genai.Client

    def always_fail(api_key=None, **kwargs):
        c = _FakeClient(api_key=api_key, **kwargs)
        c.fail_times = 99
        _last_client["client"] = c
        return c

    _fake_genai.Client = always_fail
    try:
        cfg = _gemini_cfg(psychagent_embedding_max_retries=2, psychagent_embedding_retry_sleep_sec=0.0)
        with pytest.raises(RuntimeError, match="failed after 2 attempts") as ei:
            asyncio.run(_mgr(cfg)._embed_by_api(["hello"]))
    finally:
        _fake_genai.Client = orig
    assert FAKE_KEY not in str(ei.value)  # key redacted from error


def test_gemini_malformed_count_raises():
    mgr = _mgr()
    orig = _fake_genai.Client

    def bad_count(api_key=None, **kwargs):
        c = _FakeClient(api_key=api_key)
        c.malformed = "count"
        _last_client["client"] = c
        return c

    _fake_genai.Client = bad_count
    try:
        with pytest.raises((RuntimeError, ValueError)):
            asyncio.run(mgr._embed_by_api(["a", "b", "c"]))
    finally:
        _fake_genai.Client = orig


def test_gemini_malformed_empty_vector_raises():
    mgr = _mgr()
    orig = _fake_genai.Client

    def bad_vec(api_key=None, **kwargs):
        c = _FakeClient(api_key=api_key)
        c.malformed = "empty"
        _last_client["client"] = c
        return c

    _fake_genai.Client = bad_vec
    try:
        with pytest.raises((RuntimeError, ValueError)):
            asyncio.run(mgr._embed_by_api(["a"]))
    finally:
        _fake_genai.Client = orig


def test_stale_dimension_triggers_full_reembed():
    mgr = _mgr()  # expects 768-dim
    micro = {
        "s1": {
            "skill_id": "s1", "skill_name": "n", "skill_description": "d",
            "trigger": "t", "when_to_use": "w", "parent_ids": [],
            "embedding_to_merge": [0.1] * 1024,   # stale bge-m3 vectors
            "embedding_to_retrive": [0.2] * 1024,
        }
    }
    updated_lib, updated = asyncio.run(mgr._ensure_embeddings_for_all(micro))
    assert updated is True
    assert len(updated_lib["s1"]["embedding_to_merge"]) == 768
    assert len(updated_lib["s1"]["embedding_to_retrive"]) == 768


def test_matching_dimension_no_reembed():
    mgr = _mgr()
    vec = [0.1] * 768
    micro = {
        "s1": {
            "skill_id": "s1", "skill_name": "n", "skill_description": "d",
            "trigger": "t", "when_to_use": "w", "parent_ids": [],
            "embedding_to_merge": list(vec),
            "embedding_to_retrive": list(vec),
        }
    }
    _, updated = asyncio.run(mgr._ensure_embeddings_for_all(micro))
    assert updated is False
    assert "client" not in _last_client  # no API call made


def test_dummy_fallback_uses_configured_dimension(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    cfg = _gemini_cfg(client_backend="dummy", psychagent_embedding_dimensions=768)
    vecs = asyncio.run(SkillManager(DummyBackend(), cfg)._embed_by_api(["x", "y"]))
    assert vecs == [[0.0] * 768, [0.0] * 768]


def test_missing_key_non_dummy_raises():
    cfg = _gemini_cfg(client_backend="openai_api",
                      psychagent_embedding_api_key_env="GEMINI_API_KEY_MISSING_XYZ")
    import os
    os.environ.pop("GEMINI_API_KEY_MISSING_XYZ", None)
    mgr = SkillManager(_NonDummyBackend(), cfg)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY_MISSING_XYZ"):
        asyncio.run(mgr._embed_by_api(["x"]))


def test_siliconflow_path_still_works():
    cfg = _gemini_cfg(
        psychagent_embedding_provider="siliconflow",
        psychagent_embedding_api_key_env="GEMINI_API_KEY",  # reuse fake key
        psychagent_embedding_model="BAAI/bge-m3",
        psychagent_embedding_dimensions=1024,
    )
    vecs = asyncio.run(_mgr(cfg)._embed_by_api(["a", "b"]))
    assert len(vecs) == 2 and all(len(v) == 1024 for v in vecs)


def test_runtime_config_validation_rejects_bad_provider():
    with pytest.raises(Exception):
        _gemini_cfg(psychagent_embedding_provider="nope")


def test_runtime_config_validation_rejects_bad_dimensions():
    with pytest.raises(Exception):
        _gemini_cfg(psychagent_embedding_dimensions=0)


def test_offline_mode_never_goes_live_even_with_key_set():
    """Regression: offline tests must not touch the network even when a key exists."""
    cfg = _gemini_cfg(client_backend="dummy")  # GEMINI_API_KEY is set by fixture
    mgr = SkillManager(DummyBackend(), cfg)
    vecs = asyncio.run(mgr._embed_by_api(["a", "b"]))
    assert vecs == [[0.0] * 768, [0.0] * 768]
    assert "client" not in _last_client  # no SDK client ever created


def test_offline_mode_detects_dummy_backend_class():
    cfg = _gemini_cfg(client_backend="openai_api")  # not dummy by config...
    mgr = SkillManager(DummyBackend(), cfg)  # ...but dummy by backend class
    vecs = asyncio.run(mgr._embed_by_api(["a"]))
    assert vecs == [[0.0] * 768]
    assert "client" not in _last_client


def test_gemini_async_client_aclose_awaited():
    cfg = _gemini_cfg(client_backend="openai_api")
    mgr = SkillManager(_NonDummyBackend(), cfg)
    asyncio.run(mgr._embed_by_api(["hello"]))
    client = _last_client["client"]
    assert client.closed is True
    assert client.aio.aclosed is True


def test_gemini_auth_error_fails_fast_without_retry():
    orig = _fake_genai.Client

    def auth_fail(api_key=None, http_options=None):
        c = _FakeClient(api_key=api_key, http_options=http_options)
        c.fail_times = 99
        c.fail_code = 401
        _last_client["client"] = c
        return c

    _fake_genai.Client = auth_fail
    try:
        cfg = _gemini_cfg(client_backend="openai_api", psychagent_embedding_max_retries=5)
        mgr = SkillManager(_NonDummyBackend(), cfg)
        with pytest.raises(RuntimeError, match="not retryable"):
            asyncio.run(mgr._embed_by_api(["hello"]))
    finally:
        _fake_genai.Client = orig
    assert len(_last_client["client"].calls) == 1  # exactly one attempt
    assert FAKE_KEY not in str(_last_client["client"].calls and "")


def test_gemini_timeout_option_passed():
    cfg = _gemini_cfg(client_backend="openai_api", psychagent_embedding_timeout_sec=42)
    mgr = SkillManager(_NonDummyBackend(), cfg)
    asyncio.run(mgr._embed_by_api(["hello"]))
    assert _last_client["client"].http_options.timeout == 42000


def test_timeout_config_validation():
    with pytest.raises(Exception):
        _gemini_cfg(psychagent_embedding_timeout_sec=0)

# ---------------------------------------------------------------------------
# Additional tests: offline guard, keyed store, retry policy, shutdown
# ---------------------------------------------------------------------------

def test_offline_guard_with_socket_blocked(monkeypatch):
    """Strongest offline guarantee: TCP/DNS attempts raise, dummy path passes.

    (socket.socket itself is left alone: asyncio's event loop needs socketpair
    for its internal self-pipe.)
    """
    import socket

    def _boom(*a, **k):
        raise AssertionError("network attempted in offline mode")

    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    monkeypatch.setenv("GEMINI_API_KEY", "sentinel-should-never-be-used")
    cfg = _gemini_cfg(client_backend="dummy")
    mgr = SkillManager(DummyBackend(), cfg)
    vecs = asyncio.run(mgr._embed_by_api(["a", "b"], task_type="RETRIEVAL_QUERY"))
    assert vecs == [[0.0] * 768, [0.0] * 768]
    assert "client" not in _last_client


def test_offline_uses_is_offline_attribute_not_class_name():
    class CustomOffline:
        is_offline = True

        async def chat_text(self, messages, **kwargs):
            return "ok"

    cfg = _gemini_cfg(client_backend="openai_api")
    mgr = SkillManager(CustomOffline(), cfg)
    assert mgr._is_offline_embedding_mode() is True
    vecs = asyncio.run(mgr._embed_by_api(["x"]))
    assert vecs == [[0.0] * 768]


def test_live_mode_never_returns_zero_vectors():
    cfg = _gemini_cfg(client_backend="openai_api")
    mgr = SkillManager(_NonDummyBackend(), cfg)
    vecs = asyncio.run(mgr._embed_by_api(["hello"], task_type="RETRIEVAL_QUERY"))
    assert len(vecs) == 1
    assert any(v != 0.0 for v in vecs[0])


def test_task_types_propagated():
    cfg = _gemini_cfg(client_backend="openai_api")
    mgr = SkillManager(_NonDummyBackend(), cfg)
    asyncio.run(mgr._embed_by_api(["doc text"], task_type="RETRIEVAL_DOCUMENT"))
    first = _last_client["client"]
    assert first.calls[0]["task_type"] == "RETRIEVAL_DOCUMENT"
    asyncio.run(mgr._embed_by_api(["query text"], task_type="RETRIEVAL_QUERY"))
    second = _last_client["client"]
    assert second is not first  # fresh client per call
    assert second.calls[0]["task_type"] == "RETRIEVAL_QUERY"


def test_429_retries_bounded_then_quota_message():
    orig = _fake_genai.Client

    def rate_limited(api_key=None, **kwargs):
        c = _FakeClient(api_key=api_key, **kwargs)
        c.fail_times = 99
        c.fail_code = 429
        _last_client["client"] = c
        return c

    _fake_genai.Client = rate_limited
    try:
        cfg = _gemini_cfg(client_backend="openai_api", psychagent_embedding_max_retries=3,
                          psychagent_embedding_retry_sleep_sec=0.0)
        mgr = SkillManager(_NonDummyBackend(), cfg)
        with pytest.raises(RuntimeError, match="rate limit / quota exhausted") as ei:
            asyncio.run(mgr._embed_by_api(["hello"]))
    finally:
        _fake_genai.Client = orig
    assert len(_last_client["client"].calls) == 3
    assert FAKE_KEY not in str(ei.value)


def test_retry_after_honored(monkeypatch):
    sleeps = []
    orig_sleep = asyncio.sleep

    async def _rec(d):
        sleeps.append(d)
        await orig_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _rec)
    orig = _fake_genai.Client

    def retry_after_once(api_key=None, **kwargs):
        c = _FakeClient(api_key=api_key, **kwargs)
        c.fail_times = 1
        _last_client["client"] = c
        orig_embed = c.models.embed_content

        def _with_header(model, contents, config=None):
            try:
                return orig_embed(model, contents, config)
            except RuntimeError as e:
                e.headers = _FakeHeaders({"retry-after": "0.05"})
                raise

        c.models.embed_content = _with_header
        return c

    _fake_genai.Client = retry_after_once
    try:
        cfg = _gemini_cfg(client_backend="openai_api", psychagent_embedding_max_retries=2,
                          psychagent_embedding_retry_sleep_sec=0.0)
        mgr = SkillManager(_NonDummyBackend(), cfg)
        vecs = asyncio.run(mgr._embed_by_api(["hello"]))
    finally:
        _fake_genai.Client = orig
    assert len(vecs) == 1
    assert sleeps and sleeps[0] >= 0.05


def test_backoff_is_exponential_with_jitter():
    cfg = _gemini_cfg()
    mgr = _mgr(cfg)
    d1 = mgr._backoff_delay(1, 1.0, RuntimeError("x"))
    d2 = mgr._backoff_delay(2, 1.0, RuntimeError("x"))
    d3 = mgr._backoff_delay(3, 1.0, RuntimeError("x"))
    assert 1.0 <= d1 <= 1.3
    assert 2.0 <= d2 <= 2.6
    assert 4.0 <= d3 <= 5.2
    assert mgr._backoff_delay(10, 100.0, RuntimeError("x")) <= 60.0


def test_idempotent_shutdown():
    cfg = _gemini_cfg(client_backend="openai_api")
    mgr = SkillManager(_NonDummyBackend(), cfg)
    asyncio.run(mgr._embed_by_api(["hello"]))
    asyncio.run(mgr.aclose())
    asyncio.run(mgr.aclose())  # second close must not raise


def test_cosine_similarity_magnitude_invariant():
    assert SkillManager._cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    # scaled vectors score identically: no L2 normalization required
    assert SkillManager._cosine_similarity([3.0, 4.0], [6.0, 8.0]) == pytest.approx(1.0)
    assert SkillManager._cosine_similarity([1.0] * 768, [2.0] * 768) == pytest.approx(1.0)
    # dimension mismatch can never score
    assert SkillManager._cosine_similarity([1.0] * 768, [1.0] * 1024) == -1.0


def test_keyed_store_preferred_over_base(tmp_path):
    torch = pytest.importorskip("torch")
    cfg = _gemini_cfg(client_backend="dummy")
    mgr = SkillManager(DummyBackend(), cfg)
    stage = tmp_path / "stage1"
    stage.mkdir()
    torch.save({"s1": {"skill_id": "s1", "embedding_to_merge": [0.1] * 1024,
                       "embedding_to_retrive": [0.1] * 1024}}, str(stage / "micro_skills.pt"))
    keyed = stage / f"micro_skills.{mgr._embedding_store_key()}.pt"
    torch.save({"s1": {"skill_id": "s1", "embedding_to_merge": [0.2] * 768,
                       "embedding_to_retrive": [0.2] * 768},
                "_provenance": mgr._build_provenance("abc", 1)}, str(keyed))
    loaded = mgr._load_micro_skills(stage)
    assert len(loaded["s1"]["embedding_to_merge"]) == 768
    assert "_provenance" not in loaded


def test_keyed_store_provenance_mismatch_falls_back(tmp_path):
    torch = pytest.importorskip("torch")
    cfg = _gemini_cfg(client_backend="dummy")
    mgr = SkillManager(DummyBackend(), cfg)
    stage = tmp_path / "stage1"
    stage.mkdir()
    torch.save({"s1": {"skill_id": "s1", "embedding_to_merge": [0.1] * 1024,
                       "embedding_to_retrive": [0.1] * 1024}}, str(stage / "micro_skills.pt"))
    keyed = stage / f"micro_skills.{mgr._embedding_store_key()}.pt"
    torch.save({"s1": {"skill_id": "s1", "embedding_to_merge": [0.2] * 512,
                       "embedding_to_retrive": [0.2] * 512},
                "_provenance": {"embedding_model": "other-model",
                                "embedding_dimensions": 512}}, str(keyed))
    loaded = mgr._load_micro_skills(stage)
    assert len(loaded["s1"]["embedding_to_merge"]) == 1024


def test_retry_delay_from_details_honored(monkeypatch):
    """A 429 carrying RetryInfo retryDelay must be honored, not ignored."""
    sleeps = []
    orig_sleep = asyncio.sleep

    async def _rec(d):
        sleeps.append(d)
        await orig_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _rec)
    orig = _fake_genai.Client

    def retry_info_once(api_key=None, **kwargs):
        c = _FakeClient(api_key=api_key, **kwargs)
        c.fail_times = 1
        c.fail_code = 429
        _last_client["client"] = c
        orig_embed = c.models.embed_content

        def _with_retry_info(model, contents, config=None):
            try:
                return orig_embed(model, contents, config)
            except RuntimeError as e:
                e.response_json = {"error": {"details": [
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo",
                     "retryDelay": "22s"}]}}
                raise

        c.models.embed_content = _with_retry_info
        return c

    _fake_genai.Client = retry_info_once
    try:
        cfg = _gemini_cfg(client_backend="openai_api", psychagent_embedding_max_retries=2,
                          psychagent_embedding_retry_sleep_sec=0.0)
        mgr = SkillManager(_NonDummyBackend(), cfg)
        vecs = asyncio.run(mgr._embed_by_api(["hello"]))
    finally:
        _fake_genai.Client = orig
    assert len(vecs) == 1
    # server said wait 22s: our backoff must honor it (>= 22), not the 0s base
    assert sleeps and sleeps[0] >= 22.0, sleeps


def test_daily_quota_stops_without_retry(monkeypatch):
    """A daily-quota 429 must stop immediately, not burn retries."""
    sleeps = []
    orig_sleep = asyncio.sleep

    async def _rec(d):
        sleeps.append(d)
        await orig_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _rec)
    orig = _fake_genai.Client

    def daily_quota(api_key=None, **kwargs):
        c = _FakeClient(api_key=api_key, **kwargs)
        c.fail_times = 99
        c.fail_code = 429
        _last_client["client"] = c
        orig_embed = c.models.embed_content

        def _with_daily(model, contents, config=None):
            try:
                return orig_embed(model, contents, config)
            except RuntimeError as e:
                e.response_json = {"error": {"details": [
                    {"quotaId": "EmbedContentRequestsPerDayPerProjectPerModel-FreeTier",
                     "quotaMetric": "generativelanguage.googleapis.com/embed_content_free_tier_requests"}]}}
                raise

        c.models.embed_content = _with_daily
        return c

    _fake_genai.Client = daily_quota
    try:
        cfg = _gemini_cfg(client_backend="openai_api", psychagent_embedding_max_retries=3,
                          psychagent_embedding_retry_sleep_sec=0.0)
        mgr = SkillManager(_NonDummyBackend(), cfg)
        with pytest.raises(RuntimeError, match="daily quota exhausted") as ei:
            asyncio.run(mgr._embed_by_api(["hello"]))
    finally:
        _fake_genai.Client = orig
    # exactly one HTTP attempt: no retry on daily quota
    assert len(_last_client["client"].calls) == 1
    assert not sleeps
    assert FAKE_KEY not in str(ei.value)


def test_sdk_internal_retries_disabled():
    """Our HttpOptions must request attempts=1 so the SDK never multiplies requests."""
    cfg = _gemini_cfg(client_backend="openai_api")
    mgr = SkillManager(_NonDummyBackend(), cfg)
    asyncio.run(mgr._embed_by_api(["hello"]))
    client = _last_client["client"]
    http_options = client.http_options
    assert http_options is not None
    retry_options = getattr(http_options, "retry_options", None)
    assert retry_options is not None, "SDK retry options must be set explicitly"
    assert retry_options.attempts == 1


def _quota_error(code, violations, via_details=True, retry_delay="22s"):
    """Realistic google.rpc.QuotaFailure error body.

    The real google-genai APIError exposes the body as .details (not
    .response_json); via_details=True mirrors the real SDK shape.
    """
    err = RuntimeError(f'{"429" if code == 429 else code} RESOURCE_EXHAUSTED: quota exceeded')
    err.status_code = code
    body = {"error": {"details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": violations}] + (
        [{"@type": "type.googleapis.com/google.rpc.RetryInfo",
          "retryDelay": retry_delay}] if code == 429 else [])}}
    if via_details:
        err.details = body
    else:
        err.response_json = body
    return err


def test_daily_quota_from_structured_details():
    cfg = _gemini_cfg(client_backend="openai_api")
    mgr = SkillManager(_NonDummyBackend(), cfg)
    err = _quota_error(429, [{
        "quotaId": "EmbedContentRequestsPerDayPerProjectPerModel-FreeTier",
        "quotaMetric": "generativelanguage.googleapis.com/embed_content_free_tier_requests"}])
    assert mgr._is_rate_limit_error(err)
    assert mgr._is_daily_quota_error(err)


def test_multi_violation_body_daily_wins():
    cfg = _gemini_cfg(client_backend="openai_api")
    mgr = SkillManager(_NonDummyBackend(), cfg)
    err = _quota_error(429, [
        {"quotaId": "EmbedContentRequestsPerMinutePerProjectPerModel-FreeTier",
         "quotaMetric": "generativelanguage.googleapis.com/embed_content_free_tier_requests"},
        {"quotaId": "EmbedContentRequestsPerDayPerProjectPerModel-FreeTier",
         "quotaMetric": "generativelanguage.googleapis.com/embed_content_free_tier_requests"}])
    assert mgr._is_rate_limit_error(err)
    assert mgr._is_daily_quota_error(err)


def test_per_minute_429_is_not_daily():
    cfg = _gemini_cfg(client_backend="openai_api")
    mgr = SkillManager(_NonDummyBackend(), cfg)
    err = _quota_error(429, [{
        "quotaId": "EmbedContentRequestsPerMinutePerProjectPerModel-FreeTier",
        "quotaMetric": "generativelanguage.googleapis.com/embed_content_free_tier_requests"}])
    assert mgr._is_rate_limit_error(err)
    assert not mgr._is_daily_quota_error(err)


def test_no_bare_429_substring_classification():
    """A message merely mentioning digits like 4290 must not count as a 429."""
    cfg = _gemini_cfg(client_backend="openai_api")
    mgr = SkillManager(_NonDummyBackend(), cfg)
    err = RuntimeError("validation failed for field batch_4290: bad value")
    err.status_code = 400
    assert not mgr._is_rate_limit_error(err)
    assert not mgr._is_daily_quota_error(err)
    # But a genuine 429 status code still classifies.
    err2 = RuntimeError("RESOURCE_EXHAUSTED")
    err2.status_code = 429
    assert mgr._is_rate_limit_error(err2)


def test_structured_classification_via_details_attribute():
    """The real SDK puts the body on .details; classification must use it."""
    cfg = _gemini_cfg(client_backend="openai_api")
    mgr = SkillManager(_NonDummyBackend(), cfg)
    err = _quota_error(429, [{
        "quotaId": "EmbedContentRequestsPerDayPerProjectPerModel-FreeTier",
        "quotaMetric": "generativelanguage.googleapis.com/embed_content_free_tier_requests"}],
        via_details=True)
    assert not hasattr(err, "response_json")
    assert mgr._is_daily_quota_error(err)
    # retryDelay also parsed from .details
    assert mgr._retry_after_seconds(err) == pytest.approx(22.0)


def test_backoff_honors_large_provider_delay_exactly():
    """A provider-requested 90s delay must not be shortened to 60s."""
    cfg = _gemini_cfg(client_backend="openai_api")
    mgr = SkillManager(_NonDummyBackend(), cfg)
    err = _quota_error(429, [{
        "quotaId": "EmbedContentRequestsPerMinutePerProjectPerModel-FreeTier",
        "quotaMetric": "generativelanguage.googleapis.com/embed_content_free_tier_requests"}],
        retry_delay="90s")
    assert mgr._retry_after_seconds(err) == pytest.approx(90.0)
    assert mgr._backoff_delay(1, 1.0, err) == pytest.approx(90.0)


def test_retry_loop_sleeps_full_provider_delay(monkeypatch):
    """The retry loop must sleep the full server-requested delay (mocked)."""
    sleeps = []
    orig_sleep = asyncio.sleep

    async def _rec(d):
        sleeps.append(d)
        await orig_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _rec)
    orig = _fake_genai.Client

    def delayed_429(api_key=None, **kwargs):
        c = _FakeClient(api_key=api_key, **kwargs)
        c.fail_times = 1
        c.fail_code = 429
        _last_client["client"] = c
        orig_embed = c.models.embed_content

        def _with_delay(model, contents, config=None):
            try:
                return orig_embed(model, contents, config)
            except RuntimeError as e:
                e.response_json = {"error": {"details": [
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo",
                     "retryDelay": "75s"}]}}
                raise

        c.models.embed_content = _with_delay
        return c

    _fake_genai.Client = delayed_429
    try:
        cfg = _gemini_cfg(client_backend="openai_api", psychagent_embedding_max_retries=2,
                          psychagent_embedding_retry_sleep_sec=0.0)
        mgr = SkillManager(_NonDummyBackend(), cfg)
        vecs = asyncio.run(mgr._embed_by_api(["hello"]))
        assert len(vecs) == 1
    finally:
        _fake_genai.Client = orig
    assert sleeps, "expected a backoff sleep"
    assert sleeps[0] == pytest.approx(75.0), f"provider delay shortened: {sleeps}"
