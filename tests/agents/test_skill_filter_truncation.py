"""Skill coarse-filter truncation tests (Item 3a, 2026-10-24).

Verified in code: when the filter LLM output cannot be parsed (e.g.
cut off mid-JSON), corse_filter falls back to the default top skills
and previously only logged a warning — callers had no observable
signal. The filter now passes an explicit 1024-token budget (the
prompt demands IDs-only JSON, so this is ample and stops a small
backend default from truncating the object) and reports
``truncated`` in its result dict.

A stub SkillManager is used: no skill library load, no network.
"""

import asyncio
import logging
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.skill_manager import SkillManager


class _StubBackend:
    def __init__(self, response_text):
        self.response_text = response_text
        self.seen_kwargs = None

    async def chat_text(self, messages, **kwargs):
        self.seen_kwargs = kwargs
        return self.response_text


def _manager(backend):
    mgr = object.__new__(SkillManager)
    mgr.skill_lib = {
        "cbt": {
            "stage1": SimpleNamespace(
                leaf={
                    "1": {"skill_id": "1", "skill_name": "A"},
                    "2": {"skill_id": "2", "skill_name": "B"},
                    "3": {"skill_id": "3", "skill_name": "C"},
                },
                meta={
                    "1": {"parent_ids": [], "skill_name": "A"},
                    "2": {"parent_ids": [], "skill_name": "B"},
                    "3": {"parent_ids": [], "skill_name": "C"},
                },
                micro={},
            )
        }
    }
    mgr._select_system_prompt = "select {{number}} skills"
    mgr._select_user_prompt = "goals {{session_goals}} library {{skills_library}}"
    mgr._backend = backend
    mgr._logger = logging.getLogger("test_filter_truncation")
    return mgr


def test_truncated_filter_output_falls_back_and_flags_truncated():
    # Cut off mid-JSON, naming skills 2 and 3: the fallback must return
    # the default top skills (1, 2), proving parsing did not succeed.
    backend = _StubBackend('{"skill_id": ["2", "3"')
    mgr = _manager(backend)
    meta, _wo, ids, res = asyncio.run(mgr.corse_filter(
        sect="cbt", session_goals={}, stage=1, n=2,
    ))
    # Fallback: default top skills (first leaf keys), not parsed ids.
    assert [sid for _sect, sid in ids] == ["1", "2"]
    assert res["truncated"] is True
    # Explicit filter budget, not an inherited small default.
    assert backend.seen_kwargs.get("max_tokens") == 1024
    assert backend.seen_kwargs.get("ledger_purpose") == "skill_coarse_filter"


def test_clean_filter_output_parses_and_flags_not_truncated():
    backend = _StubBackend('{"skill_id": ["2", "3"]}')
    mgr = _manager(backend)
    _meta, _wo, ids, res = asyncio.run(mgr.corse_filter(
        sect="cbt", session_goals={}, stage=1, n=2,
    ))
    assert [sid for _sect, sid in ids] == ["2", "3"]
    assert res["truncated"] is False
