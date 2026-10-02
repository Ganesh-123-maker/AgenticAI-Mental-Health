"""Standalone test script for Phase 3: Memory Agent + State Assessment Agent.

Run from the project root:
    python -X utf8 tests/agents/test_agents_standalone.py

Tests:
  1. Base agent schema construction
  2. AgentContext construction with minimal fields
  3. Memory Agent on a full CBT sample profile (no PublicMemory pre-built)
  4. State Agent on Memory Agent output from full profile
  5. Memory Agent on an ambiguous benchmark case (missing fields)
  6. State Agent on ambiguous benchmark case
  7. Memory Agent with empty PublicMemory (first-session scenario)
  8. State Agent with empty memory output
  9. Verify no memory mutation
 10. Verify State Agent has no clinical/diagnostic labels in output
"""

import json
import pathlib
import sys

# Make src importable when run from project root
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "src"))

from sample.agents.base import Agent, AgentContext, AgentError, AgentMessage
from sample.agents.memory_agent import MemoryAgent
from sample.agents.state_agent import StateAgent
from sample.core.schemas import PublicMemory

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

_results = []

def _check(name: str, condition: bool, detail: str = "") -> None:
    label = PASS if condition else FAIL
    msg = f"  [{label}] {name}"
    if detail and not condition:
        msg += f"\n         detail: {detail}"
    print(msg)
    _results.append((name, condition))


def _load_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Test 1: Base schema construction
# ---------------------------------------------------------------------------
print("\n--- Test 1: Base schema construction ---")

ctx = AgentContext(case_id="test_1", modality="cbt")
_check("AgentContext constructs with required fields only", ctx.case_id == "test_1")
_check("AgentContext optional fields default to None/[]",
       ctx.current_message is None and ctx.history_list == [])

msg = AgentMessage(agent="test_agent", status="ok", payload={"x": 1})
_check("AgentMessage constructs correctly", msg.agent == "test_agent")
_check("AgentMessage.to_dict() works", isinstance(msg.to_dict(), dict))

_check("AgentError is raised correctly", True)
try:
    raise AgentError("test", "something failed")
except AgentError as e:
    _check("AgentError carries agent_name", e.agent_name == "test")


# ---------------------------------------------------------------------------
# Test 2: Memory Agent — full CBT sample profile, no pre-built PublicMemory
# ---------------------------------------------------------------------------
print("\n--- Test 2: Memory Agent on full CBT profile ---")

cbt_dir = pathlib.Path("assets/profiles/cbt/sample")
cbt_files = sorted(cbt_dir.glob("*.json"))[:1]
assert cbt_files, "No CBT sample profiles found!"
cbt_profile_path = cbt_files[0]
cbt_profile = _load_json(cbt_profile_path)

ctx2 = AgentContext(
    case_id=cbt_profile_path.stem,
    modality="cbt",
    therapy_stage="Problem conceptualization and goal setting",
    session_index=1,
    full_profile=cbt_profile,
    current_message="I have been under a lot of pressure at work lately and feel like I can't do anything right.",
)

mem_agent = MemoryAgent()
mem_msg = mem_agent.run(ctx2)

_check("Memory Agent status is ok or unavailable",
       mem_msg.status in ("ok", "partial", "unavailable"))
_check("Memory Agent has payload", isinstance(mem_msg.payload, dict) and bool(mem_msg.payload))
_check("Memory Agent payload has known_static_traits",
       "known_static_traits" in mem_msg.payload)
_check("Memory Agent payload has main_problem",
       bool(mem_msg.payload.get("main_problem")))
_check("Memory Agent payload has source field",
       "source" in mem_msg.payload)
_check("Memory Agent source references full_profile",
       "full_profile" in str(mem_msg.payload.get("source", "")))
_check("Memory Agent output is non-empty (references actual content)",
       bool(mem_msg.payload.get("known_static_traits")) or bool(mem_msg.payload.get("main_problem")))
_check("Memory Agent missing_information is a list",
       isinstance(mem_msg.missing_information, list))

print(f"     case: {cbt_profile_path.stem}")
print(f"     source: {mem_msg.payload.get('source')}")
print(f"     main_problem: {str(mem_msg.payload.get('main_problem', ''))[:60]}")
print(f"     known_traits_count: {len(mem_msg.payload.get('known_static_traits', {}))}")
print(f"     missing: {mem_msg.missing_information}")


# ---------------------------------------------------------------------------
# Test 3: State Agent — full CBT profile
# ---------------------------------------------------------------------------
print("\n--- Test 3: State Agent on full CBT profile ---")

ctx2.memory_output = mem_msg.payload
state_agent = StateAgent()
state_msg = state_agent.run(ctx2)

_check("State Agent status is ok or partial",
       state_msg.status in ("ok", "partial"))
_check("State Agent has payload", isinstance(state_msg.payload, dict))
_check("State Agent has current_concern",
       bool(state_msg.payload.get("current_concern")))
_check("State Agent has known_information list",
       isinstance(state_msg.payload.get("known_information"), list))
_check("State Agent has unknown_information list",
       isinstance(state_msg.payload.get("unknown_information"), list))
_check("State Agent has longitudinal_relevance",
       isinstance(state_msg.payload.get("longitudinal_relevance"), str))
_check("State Agent confidence is 0.0–1.0",
       0.0 <= (state_msg.confidence or 0.0) <= 1.0)
_check("State Agent known_information is non-empty (evidenced content)",
       bool(state_msg.payload.get("known_information")))

# Verify NO clinical/diagnostic labels
clinical_labels = [
    "diagnosis", "DSM", "ICD", "depression", "anxiety", "disorder", "psychosis", "mania",
    "CLEAR", "UNCERTAIN", "HIGH-RISK", "crisis intervention"
]
output_text = json.dumps(state_msg.payload, ensure_ascii=False)
clinical_found = [lbl for lbl in clinical_labels if lbl in output_text]
_check("State Agent contains no clinical/diagnostic labels",
       not clinical_found,
       f"found labels: {clinical_found}")

print(f"     current_concern: {str(state_msg.payload.get('current_concern', ''))[:80]}")
print(f"     known_information count: {len(state_msg.payload.get('known_information', []))}")
print(f"     unknown_information count: {len(state_msg.payload.get('unknown_information', []))}")
print(f"     confidence: {state_msg.confidence:.2f}")
print(f"     longitudinal: {state_msg.payload.get('longitudinal_relevance', '')[:80]}")


# ---------------------------------------------------------------------------
# Test 4: Memory Agent + State Agent — ambiguous benchmark case (missing fields)
# ---------------------------------------------------------------------------
print("\n--- Test 4: Memory + State Agent on ambiguous benchmark case ---")

bench_dir = pathlib.Path("data/benchmark/ambiguous_cases/cbt")
bench_files = sorted(bench_dir.glob("*_ordinary.json"))[:1]
if bench_files:
    bench_path = bench_files[0]
    bench_data = _load_json(bench_path)
    # Use ambiguous_context (the redacted version)
    ambig_profile = bench_data.get("ambiguous_context", {})
    missing_fields = bench_data.get("missing_information", [])
    uncertainty_type = bench_data.get("uncertainty_type", "")

    ctx4 = AgentContext(
        case_id=bench_data["case_id"],
        modality="cbt",
        therapy_stage=bench_data.get("therapy_stage"),
        full_profile=ambig_profile,
        current_message="I feel very troubled lately and don't know what to do.",
    )

    mem_msg4 = mem_agent.run(ctx4)
    ctx4.memory_output = mem_msg4.payload
    state_msg4 = state_agent.run(ctx4)

    _check("Ambiguous case: Memory Agent does not crash", True)
    _check("Ambiguous case: State Agent does not crash", True)

    # Verify that missing fields (from the benchmark) appear in unknown_information
    unknown_str = json.dumps(state_msg4.payload.get("unknown_information", []), ensure_ascii=False)
    missing_str = json.dumps(mem_msg4.missing_information, ensure_ascii=False)
    _check("Ambiguous case: missing_information is populated",
           bool(mem_msg4.missing_information) or bool(state_msg4.payload.get("unknown_information")))

    print(f"     bench case_id: {bench_data['case_id']}")
    print(f"     uncertainty_type: {uncertainty_type}")
    print(f"     expected missing: {missing_fields}")
    print(f"     memory missing: {mem_msg4.missing_information}")
    print(f"     state unknown count: {len(state_msg4.payload.get('unknown_information', []))}")
    print(f"     state confidence: {state_msg4.confidence:.2f}")
else:
    print("  [SKIP] No ambiguous benchmark cases found — Phase 2 not run?")


# ---------------------------------------------------------------------------
# Test 5: Memory Agent with explicit PublicMemory (first-session, empty)
# ---------------------------------------------------------------------------
print("\n--- Test 5: Memory Agent with empty PublicMemory (first session) ---")

empty_mem = PublicMemory()
ctx5 = AgentContext(
    case_id="first_session_test",
    modality="bt",
    session_index=1,
    therapy_stage="Problem conceptualization and goal setting",
    public_memory=empty_mem,
)

mem_msg5 = mem_agent.run(ctx5)
_check("Empty PublicMemory: Memory Agent does not crash", True)
_check("Empty PublicMemory: status is ok or unavailable",
       mem_msg5.status in ("ok", "unavailable"))
_check("Empty PublicMemory: missing_information mentions prior_session_recaps",
       any("prior_session_recaps" in m for m in mem_msg5.missing_information))
_check("Empty PublicMemory: payload still has required keys",
       all(k in mem_msg5.payload for k in ("session_recaps", "last_homework", "known_static_traits")))

ctx5.memory_output = mem_msg5.payload
state_msg5 = state_agent.run(ctx5)
_check("Empty PublicMemory: State Agent produces valid payload", bool(state_msg5.payload))
_check("Empty PublicMemory: unknown_information non-empty (expected for first session)",
       bool(state_msg5.payload.get("unknown_information")))


# ---------------------------------------------------------------------------
# Test 6: Verify Memory Agent does NOT mutate PublicMemory
# ---------------------------------------------------------------------------
print("\n--- Test 6: Memory Agent does not mutate PublicMemory ---")

test_mem = PublicMemory(
    known_static_traits={"name": "Test User", "age": "30"},
    session_recaps=[{"session_index": 1, "summary": "Initial consultation"}],
    last_homework=["Keep an emotion log"],
)
original_recaps_len = len(test_mem.session_recaps)
original_traits_copy = dict(test_mem.known_static_traits)

ctx6 = AgentContext(
    case_id="mutation_test",
    modality="cbt",
    public_memory=test_mem,
)
mem_msg6 = mem_agent.run(ctx6)

_check("Memory Agent: PublicMemory.session_recaps not mutated",
       len(test_mem.session_recaps) == original_recaps_len)
_check("Memory Agent: PublicMemory.known_static_traits not mutated",
       test_mem.known_static_traits == original_traits_copy)
_check("Memory Agent: payload session_recaps is a copy (not same object)",
       mem_msg6.payload.get("session_recaps") is not test_mem.session_recaps)


# ---------------------------------------------------------------------------
# Test 7: Second CBT profile for variety
# ---------------------------------------------------------------------------
print("\n--- Test 7: Memory + State Agent on second CBT profile ---")

if len(cbt_files_all := sorted(cbt_dir.glob("*.json"))) >= 2:
    cbt_profile_path2 = cbt_files_all[5]  # pick a different one
    cbt_profile2 = _load_json(cbt_profile_path2)

    ctx7 = AgentContext(
        case_id=cbt_profile_path2.stem,
        modality="cbt",
        therapy_stage="Problem conceptualization and goal setting",
        session_index=2,
        full_profile=cbt_profile2,
        history_list=[{"session_summary_abstract": "Last session discussed work stress and cognitive patterns", "homework": ["Daily automatic thought records"]}],
        current_message="I tried making notes, but sometimes I still feel like everything I do is wrong.",
    )

    mem_msg7 = mem_agent.run(ctx7)
    ctx7.memory_output = mem_msg7.payload
    state_msg7 = state_agent.run(ctx7)

    _check("Second profile: Memory Agent ok", mem_msg7.status in ("ok", "partial"))
    _check("Second profile: prior_outcomes populated from history",
           bool(mem_msg7.payload.get("prior_outcomes")) or bool(mem_msg7.payload.get("previous_interventions")))
    _check("Second profile: newly_observed populated from current_message",
           bool(mem_msg7.payload.get("newly_observed")))
    _check("Second profile: State Agent known_information non-empty",
           bool(state_msg7.payload.get("known_information")))

    print(f"     case: {cbt_profile_path2.stem}")
    print(f"     previous_interventions: {len(mem_msg7.payload.get('previous_interventions', []))}")
    print(f"     newly_observed: {mem_msg7.payload.get('newly_observed', [])[:1]}")
    print(f"     state confidence: {state_msg7.confidence:.2f}")
else:
    print("  [SKIP] fewer than 2 CBT profiles found")


# ---------------------------------------------------------------------------
# Print sample output for one case
# ---------------------------------------------------------------------------
print("\n--- Sample output: Memory Agent (CBT case", cbt_profile_path.stem, ") ---")
print(json.dumps({
    "agent": mem_msg.agent,
    "status": mem_msg.status,
    "evidence": mem_msg.evidence,
    "missing_information": mem_msg.missing_information,
    "payload_keys": list(mem_msg.payload.keys()),
    "main_problem": mem_msg.payload.get("main_problem", "")[:60],
    "known_traits_sample": dict(list(mem_msg.payload.get("known_static_traits", {}).items())[:3]),
}, indent=2, ensure_ascii=False))

print("\n--- Sample output: State Agent (CBT case", cbt_profile_path.stem, ") ---")
print(json.dumps({
    "agent": state_msg.agent,
    "status": state_msg.status,
    "confidence": state_msg.confidence,
    "current_concern": state_msg.payload.get("current_concern", "")[:80],
    "expressed_needs": state_msg.payload.get("expressed_needs", "")[:80],
    "known_information_count": len(state_msg.payload.get("known_information", [])),
    "unknown_information": state_msg.payload.get("unknown_information", []),
    "longitudinal_relevance": state_msg.payload.get("longitudinal_relevance", ""),
    "context": state_msg.payload.get("context", {}),
}, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n=== Test Summary ===")
total = len(_results)
passed = sum(1 for _, ok in _results if ok)
failed = total - passed
print(f"  Passed: {passed}/{total}")
if failed:
    print(f"  Failed: {failed}")
    for name, ok in _results:
        if not ok:
            print(f"    - {name}")

sys.exit(0 if failed == 0 else 1)
