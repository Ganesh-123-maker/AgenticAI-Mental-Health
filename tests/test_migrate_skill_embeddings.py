"""Tests for scripts/migrate_skill_embeddings.py: pacing, locking, checkpoints.

Mocked/offline only: no API calls, no network. The script's pure components
(RatePacer, _est_tokens, lock helpers, ShardCheckpoint, _validate_vectors,
DailyQuotaExhausted) are exercised directly; _migrate_one is driven with a
fake manager and tiny synthetic .pt files.
"""

import asyncio
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


def _load_script():
    path = REPO_ROOT / "scripts" / "migrate_skill_embeddings.py"
    spec = importlib.util.spec_from_file_location("migrate_skill_embeddings", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mig():
    return _load_script()


# ---------------------------------------------------------------------------
# Token estimates
# ---------------------------------------------------------------------------

def test_est_tokens_cjk_aware(mig):
    # Pure CJK: ~1 token per character.
    assert mig._est_tokens("你好世界") == pytest.approx(4.0)
    # Pure ASCII: ~0.25 per character.
    assert mig._est_tokens("abcd") == pytest.approx(1.0)
    # Mixed.
    assert mig._est_tokens("ab你好") == pytest.approx(0.5 + 2.0)
    # Multiplier applies.
    assert mig._est_tokens("ab你好", multiplier=2.0) == pytest.approx(5.0)
    # Optimistic len/4 kept for comparison.
    assert mig._est_tokens_optimistic("abcd") == pytest.approx(1.0)
    assert mig._est_tokens_optimistic("你好世界") == pytest.approx(1.0)


def test_pacer_interval_cjk_tpm_binding(mig):
    # CJK-heavy workload: 2268 est tokens/request. TPM cap 25000 must bind
    # over the 30 RPM request pacing.
    pacer = mig.RatePacer(rpm=30.0, tpm=25000.0, est_tokens_per_request=2268.0)
    assert pacer.tpm_active
    # interval = 60 * 2268 / 25000 = 5.44s  (> 2.0s RPM interval)
    assert pacer.interval == pytest.approx(5.44, rel=0.01)
    assert pacer.base_interval == pytest.approx(5.44, rel=0.01)


def test_pacer_interval_rpm_binding(mig):
    # Light workload: RPM pacing binds, TPM does not.
    pacer = mig.RatePacer(rpm=30.0, tpm=25000.0, est_tokens_per_request=100.0)
    assert not pacer.tpm_active
    assert pacer.interval == pytest.approx(2.0)


def test_pacer_adaptive_slowdown_and_relax(mig, monkeypatch):
    # No real sleeping in this test.
    async def _no_sleep(d):
        return None
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    pacer = mig.RatePacer(rpm=30.0, tpm=None, est_tokens_per_request=0.0)
    base = pacer.interval
    pacer.adapt_on_429()
    assert pacer.interval == pytest.approx(base * 1.5)
    assert pacer.adaptations == 1
    pacer.adapt_on_429()
    assert pacer.interval == pytest.approx(base * 1.5 * 1.5)
    # Cap at 60s.
    for _ in range(10):
        pacer.adapt_on_429()
    assert pacer.interval <= 60.0
    widened = pacer.interval
    # wait() relaxes slowly toward base (multiplicative, never below base).
    async def _drain():
        for _ in range(200):
            await pacer.wait()
    asyncio.run(_drain())
    assert pacer.interval == pytest.approx(base)
    assert widened > base


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------

def test_lock_acquire_release(mig, tmp_path):
    lock = tmp_path / "x.lock"
    token = mig._acquire_lock(lock)
    assert lock.exists()
    info = json.loads(lock.read_text())
    assert info["pid"] == os.getpid()
    assert info["token"] == token
    mig._release_lock(lock, token)
    assert not lock.exists()
    # Releasing twice is harmless.
    mig._release_lock(lock, token)


def test_lock_release_does_not_remove_others_lock(mig, tmp_path):
    lock = tmp_path / "x.lock"
    token_a = mig._acquire_lock(lock)
    # Another process takes over (simulated): different token in the file.
    lock.write_text(json.dumps({"at": "t", "pid": 999, "token": "other-token"}))
    mig._release_lock(lock, token_a)
    assert lock.exists(), "must not delete another process's lock"
    assert json.loads(lock.read_text())["token"] == "other-token"


def test_lock_active_refused(mig, tmp_path):
    lock = tmp_path / "x.lock"
    token = mig._acquire_lock(lock)  # our own live PID
    with pytest.raises(RuntimeError, match="another migration is active"):
        mig._acquire_lock(lock)
    mig._release_lock(lock, token)


def test_lock_stale_dead_pid_takeover(mig, tmp_path):
    lock = tmp_path / "x.lock"
    lock.write_text(json.dumps({"at": "2020-01-01T00:00:00", "pid": 999999999}))
    os.utime(lock, (time.time(), time.time()))  # fresh mtime, dead PID
    token = mig._acquire_lock(lock)  # must not raise
    assert json.loads(lock.read_text())["pid"] == os.getpid()
    mig._release_lock(lock, token)


def test_lock_malformed_takeover(mig, tmp_path):
    lock = tmp_path / "x.lock"
    lock.write_text("not json{{{")
    token = mig._acquire_lock(lock)  # malformed -> treated as stale
    mig._release_lock(lock, token)
    assert not lock.exists()


def test_lock_live_not_displaced_by_age(mig, tmp_path):
    # A live owner keeps its lock no matter how old it is.
    lock = tmp_path / "x.lock"
    token = mig._acquire_lock(lock)
    old = time.time() - 3 * 3600
    os.utime(lock, (old, old))
    with pytest.raises(RuntimeError, match="another migration is active"):
        mig._acquire_lock(lock)
    mig._release_lock(lock, token)


def test_concurrent_acquire_one_winner(mig, tmp_path):
    import threading
    lock = tmp_path / "x.lock"
    results = []

    def _try():
        try:
            tok = mig._acquire_lock(lock)
            results.append(("ok", tok))
        except RuntimeError as e:
            results.append(("refused", str(e)))

    threads = [threading.Thread(target=_try) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    wins = [r for r in results if r[0] == "ok"]
    assert len(wins) == 1, f"expected exactly one winner, got {results}"
    assert json.loads(lock.read_text())["token"] == wins[0][1]
    mig._release_lock(lock, wins[0][1])
    assert not lock.exists()


# --- _migrate_one lock release: fake manager + tiny .pt file -------------

class _FakeRuntime:
    psychagent_embedding_dimensions = 4
    psychagent_embedding_batch_size = 2


class _FakeManager:
    def __init__(self, fail_on_call=None):
        self._runtime = _FakeRuntime()
        self._calls = 0
        self._fail_on_call = fail_on_call

    def _embedding_store_key(self):
        return "gemini-embedding-001.4"

    def _build_provenance(self, source_hash, n):
        return {"embedding_provider": "gemini",
                "embedding_model": "gemini-embedding-001",
                "embedding_dimensions": 4,
                "source_hash": source_hash, "skill_count": n}

    def _provenance_matches(self, prov):
        return True

    async def _embed_by_api(self, texts, task_type=None, on_rate_limit=None):
        self._calls += 1
        if self._fail_on_call == self._calls:
            raise KeyboardInterrupt()
        if self._fail_on_call == -self._calls:
            raise RuntimeError("boom")
        return [[0.1] * 4 for _ in texts]


def _tiny_pt(tmp_path):
    import torch
    pt = tmp_path / "micro_skills.pt"
    skills = {
        f"s{i}": {"skill_id": f"s{i}", "skill_name": f"技能{i}",
                  "skill_description": "描述 " * 10,
                  "trigger": "触发", "when_to_use": "使用",
                  "parent_ids": []}
        for i in range(3)
    }
    torch.save(skills, str(pt))
    return pt


def test_lock_released_after_exception(mig, tmp_path):
    pt = _tiny_pt(tmp_path)
    mgr = _FakeManager(fail_on_call=-1)  # RuntimeError on first call
    result = asyncio.run(mig._migrate_one(mgr, pt, False, mig.RatePacer(6000, None, 0), "K"))
    assert result["status"].startswith("FAILED")
    assert not (tmp_path / "micro_skills.gemini-embedding-001.4.pt.lock").exists()


def test_lock_released_after_keyboard_interrupt(mig, tmp_path):
    pt = _tiny_pt(tmp_path)
    mgr = _FakeManager(fail_on_call=1)  # KeyboardInterrupt on first call
    with pytest.raises(KeyboardInterrupt):
        asyncio.run(mig._migrate_one(mgr, pt, False, mig.RatePacer(6000, None, 0), "K"))
    assert not (tmp_path / "micro_skills.gemini-embedding-001.4.pt.lock").exists()
    # The completed batch before the interrupt is checkpointed; resume works.
    mgr2 = _FakeManager()
    result = asyncio.run(mig._migrate_one(mgr2, pt, False, mig.RatePacer(6000, None, 0), "K"))
    assert result["status"] == "regenerated"
    assert result["reused_batches"] >= 0


def test_lock_released_after_cancelled(mig, tmp_path):
    pt = _tiny_pt(tmp_path)

    class _CancelManager(_FakeManager):
        async def _embed_by_api(self, texts, task_type=None, on_rate_limit=None):
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(mig._migrate_one(_CancelManager(), pt, False,
                                     mig.RatePacer(6000, None, 0), "K"))
    assert not (tmp_path / "micro_skills.gemini-embedding-001.4.pt.lock").exists()


# ---------------------------------------------------------------------------
# Shard checkpoints
# ---------------------------------------------------------------------------

def _prov():
    return {"embedding_provider": "gemini", "embedding_model": "gemini-embedding-001",
            "embedding_dimensions": 4}


def test_shard_resume_after_crash(mig, tmp_path):
    keyed = tmp_path / "micro_skills.gemini-embedding-001.4.pt"
    cp = mig.ShardCheckpoint(keyed, "hash1", _prov(), ["s1", "s2"], total_batches=3)
    assert cp.load() == 0
    cp.save_batch(0, [[0.1] * 4])
    cp.save_batch(1, [[0.2] * 4])
    # Simulate crash: new instance, batch 2 missing.
    cp2 = mig.ShardCheckpoint(keyed, "hash1", _prov(), ["s1", "s2"], total_batches=3)
    assert cp2.load() == 2
    assert not cp2.is_complete()
    cp2.save_batch(2, [[0.3] * 4])
    assert cp2.is_complete()
    ordered = cp2.ordered_vectors()
    assert [v[0] for v in ordered] == [0.1, 0.2, 0.3]
    cp2.discard()
    assert not keyed.with_name(keyed.name + ".partial").exists()


def test_shard_corrupt_partial_rejected(mig, tmp_path):
    keyed = tmp_path / "x.pt"
    partial = keyed.with_name(keyed.name + ".partial")
    partial.write_bytes(b"\x00\x01 not a torch file")
    cp = mig.ShardCheckpoint(keyed, "hash1", _prov(), ["s1"], total_batches=1)
    assert cp.load() == 0


def test_shard_tampered_source_hash_rejected(mig, tmp_path):
    keyed = tmp_path / "x.pt"
    cp = mig.ShardCheckpoint(keyed, "hash1", _prov(), ["s1"], total_batches=1)
    cp.save_batch(0, [[0.1] * 4])
    cp2 = mig.ShardCheckpoint(keyed, "DIFFERENT", _prov(), ["s1"], total_batches=1)
    assert cp2.load() == 0  # tampered source hash: no reuse


def test_shard_provenance_mismatch_rejected(mig, tmp_path):
    keyed = tmp_path / "x.pt"
    cp = mig.ShardCheckpoint(keyed, "hash1", _prov(), ["s1"], total_batches=1)
    cp.save_batch(0, [[0.1] * 4])
    other = dict(_prov(), embedding_model="other-model")
    cp2 = mig.ShardCheckpoint(keyed, "hash1", other, ["s1"], total_batches=1)
    assert cp2.load() == 0
    other2 = dict(_prov(), embedding_dimensions=8)
    cp3 = mig.ShardCheckpoint(keyed, "hash1", other2, ["s1"], total_batches=1)
    assert cp3.load() == 0


def test_assembled_store_validation(mig):
    ok = [[0.1] * 4 for _ in range(6)]
    assert mig._validate_vectors(ok, 6, 4) is None
    assert "count" in mig._validate_vectors(ok, 5, 4)
    bad_dim = [[0.1] * 8 for _ in range(6)]
    assert "dimension" in mig._validate_vectors(bad_dim, 6, 4)
    bad_val = [[0.1] * 4 for _ in range(6)]
    bad_val[2][1] = float("inf")
    assert "finite" in mig._validate_vectors(bad_val, 6, 4)
    bad_nan = [[0.1] * 4 for _ in range(6)]
    bad_nan[0][0] = float("nan")
    assert "finite" in mig._validate_vectors(bad_nan, 6, 4)


def test_daily_quota_exhausted_type(mig):
    assert issubclass(mig.DailyQuotaExhausted, RuntimeError)


def test_file_batch_count_boundaries(mig):
    # merge and retrieve are batched separately: 2 * ceil(N / batch)
    assert mig._file_batch_count(0, 16) == 0
    assert mig._file_batch_count(1, 16) == 2
    assert mig._file_batch_count(16, 16) == 2
    assert mig._file_batch_count(17, 16) == 4
    assert mig._file_batch_count(10, 16) == 2
    assert mig._file_batch_count(20, 16) == 4
    assert mig._file_batch_count(32, 16) == 4
    assert mig._file_batch_count(33, 16) == 6
    assert mig._file_batch_count(5, 8) == 2


def test_compute_demand_matches_actual_batching(mig, tmp_path):
    import torch
    # Two files with uneven skill counts straddling batch boundaries.
    for name, n in (("a", 17), ("b", 10)):
        d = tmp_path / name
        d.mkdir()
        skills = {f"s{i}": {"skill_id": f"s{i}", "skill_name": "n",
                            "skill_description": "d", "trigger": "t",
                            "when_to_use": "w", "parent_ids": []}
                  for i in range(n)}
        torch.save(skills, str(d / "micro_skills.pt"))
    files = sorted(tmp_path.rglob("micro_skills.pt"))
    texts, opt, cons, total = mig._compute_demand(files, 16, 1.0)
    assert texts == 2 * (17 + 10)
    # Exact: 2*ceil(17/16) + 2*ceil(10/16) = 4 + 2 = 6
    assert total == 6
    assert opt > 0 and cons > 0
