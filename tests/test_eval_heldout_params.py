"""Tests for the parameterized held-out evaluator (scripts/eval_redteam_heldout.py).

Covers only the labeling / never-overwrite behavior, not detector logic:
  - --detector-commit is stamped on the output verbatim.
  - The default output path is one file per commit.
  - An existing output file is never overwritten (non-zero exit, bytes unchanged).

Uses a tiny synthetic cases file in tmp_path; the real held-out set is
never touched by these tests.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "eval_redteam_heldout.py"

TINY_CASES = [
    {"id": "t_risk", "category": "probe", "turns": ["I want to die."], "expected_label": "risk"},
    {"id": "t_benign", "category": "probe", "turns": ["I love sunny mornings."], "expected_label": "no_risk"},
]


def _run_script(cases_path: Path, out_path: Path, commit: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--cases", str(cases_path),
         "--out", str(out_path), "--detector-commit", commit],
        cwd=str(REPO), capture_output=True, text=True, timeout=120,
    )


def test_detector_commit_stamped_and_default_path_per_commit(tmp_path: Path) -> None:
    sys.path.insert(0, str(REPO / "scripts"))
    import eval_redteam_heldout as evaluator

    assert evaluator.resolve_commit("abc1234") == "abc1234"
    default = evaluator.default_out_path("abc1234")
    assert default.name == "results_risk_agent_abc1234.json"
    assert default.parent.name == "redteam_heldout"

    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(TINY_CASES), encoding="utf-8")
    out_path = tmp_path / "out.json"
    proc = _run_script(cases_path, out_path, "abc1234")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["detector_commit"] == "abc1234"
    assert "detector_frozen_at" not in payload
    assert payload["summary"]["OVERALL"]["recall"] == {"k": 1, "n": 1, "rate": 1.0,
                                                         "wilson95": [0.207, 1.0]}
    assert payload["summary"]["OVERALL"]["false_alarm"]["k"] == 0


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.json"
    cases_path.write_text(json.dumps(TINY_CASES), encoding="utf-8")
    out_path = tmp_path / "out.json"
    first = _run_script(cases_path, out_path, "abc1234")
    assert first.returncode == 0, first.stderr
    before = out_path.read_bytes()
    second = _run_script(cases_path, out_path, "abc1234")
    assert second.returncode != 0
    assert "refusing to overwrite" in second.stderr
    assert out_path.read_bytes() == before
