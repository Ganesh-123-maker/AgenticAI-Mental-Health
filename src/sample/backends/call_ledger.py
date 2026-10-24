"""Central ledger for chat-completion calls (the generate_content quota).

Every chat call made through OpenAIStyleBackend.chat_text is recorded
here, once per API attempt, so a live run can reconcile counted calls
against the provider's daily quota instead of guessing who spent it.
This ledger exists because two 2026-10-23/24 live runs hit HTTP 429
with only a handful of counted calls: the quota had been consumed by
calls nobody had itemized (notably SkillManager coarse-filter calls
firing on every web turn, including template clarification turns).

Recorded fields are metadata ONLY: purpose, model, HTTP status, and
finish reason, plus response length. Prompts, responses, user text,
and secrets are never recorded. Embedding calls use a separate quota
metric and are deliberately not recorded here.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class CallRecord:
    """One chat-completion API attempt."""

    timestamp: float
    purpose: str
    model: str
    status: str  # "ok", an HTTP status like "429"/"503", or "timeout"/"connection"/"empty"
    finish_reason: Optional[str]
    response_chars: int


class CallLedger:
    """Thread-safe append-only ledger of chat-completion attempts."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: List[CallRecord] = []

    def record(
        self,
        *,
        purpose: str,
        model: str,
        status: str,
        finish_reason: Optional[str] = None,
        response_chars: int = 0,
    ) -> CallRecord:
        rec = CallRecord(
            timestamp=time.time(),
            purpose=purpose,
            model=model,
            status=status,
            finish_reason=finish_reason,
            response_chars=response_chars,
        )
        with self._lock:
            self._records.append(rec)
        return rec

    def records(self) -> List[CallRecord]:
        with self._lock:
            return list(self._records)

    def summary(self) -> Dict[str, object]:
        with self._lock:
            records = list(self._records)
        by_purpose: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        by_model: Dict[str, int] = {}
        for rec in records:
            by_purpose[rec.purpose] = by_purpose.get(rec.purpose, 0) + 1
            by_status[rec.status] = by_status.get(rec.status, 0) + 1
            by_model[rec.model] = by_model.get(rec.model, 0) + 1
        return {
            "total": len(records),
            "by_purpose": by_purpose,
            "by_status": by_status,
            "by_model": by_model,
        }

    def reset(self) -> None:
        with self._lock:
            self._records.clear()


DEFAULT_LEDGER = CallLedger()


def record_call(
    *,
    purpose: str,
    model: str,
    status: str,
    finish_reason: Optional[str] = None,
    response_chars: int = 0,
    ledger: Optional[CallLedger] = None,
) -> CallRecord:
    """Record one chat-completion attempt on the given (or default) ledger."""
    return (ledger or DEFAULT_LEDGER).record(
        purpose=purpose,
        model=model,
        status=status,
        finish_reason=finish_reason,
        response_chars=response_chars,
    )


def ledger_summary(ledger: Optional[CallLedger] = None) -> Dict[str, object]:
    """Summarize the given (or default) ledger: total + counts by purpose/status/model."""
    return (ledger or DEFAULT_LEDGER).summary()


def reset_ledger(ledger: Optional[CallLedger] = None) -> None:
    """Clear the given (or default) ledger."""
    (ledger or DEFAULT_LEDGER).reset()
