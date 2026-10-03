# Clean Clone Validation Report

**Project**: Agentic AI for Mental Health  
**Repository**: [https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health](https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health)  
**Date**: October 3, 2026  
**Artifact**: `docs/CLEAN_CLONE_VALIDATION_REPORT.md`  

---

## 1. Repository Information
- **URL**: `https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health.git`
- **Branch Tested**: `main`
- **Clean Clone Path**: `D:\Temp\AgenticAI-Mental-Health-repro`

---

## 2. Commit Tested
- **Commit Hash**: `5f92bd33d4329a5a41b654d34a29eba40592f6b9`
- **Verification**: `git ls-remote origin refs/heads/main` and `git rev-parse HEAD` confirmed exact character-for-character match.
- **Tracked Files Cloned**: 2,758 files.

---

## 3. Environment Specifications
- **Operating System**: Microsoft Windows 11 Enterprise (Build 10.0.26300.0)
- **Python Version**: 3.11.9 (64-bit)
- **Node.js Version**: v22.22.2
- **Virtual Environment**: Isolated environment at `D:\Temp\AgenticAI-Mental-Health-repro\.venv`

---

## 4. Installation Verification
- **Python Dependencies**: Verified all requirements in `requirements.txt` (`fastapi`, `uvicorn`, `sqlmodel`, `pydantic`, `torch`, `yaml`, `jinja2`, `pytest`).
- **Frontend Dependencies**: `npm install` in `src/web/` completed in 14 seconds (65 packages audited).

---

## 5. Automated Tests
- **Command**: `python -m pytest -q`
- **Result**: **31 passed in 14.91 seconds** (100% pass rate). Zero failures, zero warnings.

---

## 6. Offline Pipeline
- **Command**: `python -m pytest tests/agents/test_phase8.py -k test_runner_longitudinal_carry_through -v`
- **Result**: **PASSED in 7.73 seconds**.
- **Capabilities Verified**: Multi-turn execution, `DummyBackend` deterministic generation, zero external API key requirements, longitudinal memory persistence across 2 sequential sessions.

---

## 7. Agent Execution
All 11 specialized agent modules verified active via runtime execution traces:
1. `MemoryAgent`: Confirmed traits loaded into Session 2 context.
2. `StateAgent`: Emotional state and thematic focus extracted.
3. `UncertaintyAgent`: Epistemic gaps and ambiguous referents detected.
4. `RiskAgent`: Upstream crisis screening and 6-word negation window verified.
5. `Orchestrator`: Priority routing (`HIGH-RISK` > `UNCERTAIN` > `CLEAR`) verified.
6. `ClarificationAgent`: Focused inquiry generated.
7. `ReassessmentAgent`: State transitioned from `UNCERTAIN` to `CLEAR`.
8. `CounselingAgent`: Modality-specific therapy interventions drafted.
9. `SafetySupervisor`: Fail-closed downstream review enforced.
10. `OutcomeAgent`: Post-session engagement markers analyzed.
11. `MemoryUpdateAgent`: Durable facts committed to `PublicMemory`.

---

## 8. RAG (Skill Retrieval)
- **Component**: `SkillManager` (`src/sample/skill_manager.py`).
- **Mechanism**: Hierarchical retrieval across 5 psychotherapy modalities using cosine similarity over pre-computed tensor embeddings (`assets/skills/micro_skills.pt`).
- **Verified**: Procedural RAG executes offline using deterministic embeddings; strictly decoupled from client biographical memory.

---

## 9. Web Application
- **Frontend Build**: `npm run build` compiled production bundle in **4.10 seconds** (1,600 modules transformed, 0 errors).
- **Backend Startup**: FastAPI service booted on port 8000; OpenAPI documentation accessible at `http://127.0.0.1:8000/docs` (HTTP 200 OK).
- **Representative Scenarios**: All 8 end-to-end scenarios (Normal counseling, Ambiguity, Contradiction, Factual correction, Negated risk, Crisis escalation, Multi-session continuity, and User isolation) validated with 100% pass rate.

---

## 10. Research Artifacts
- `data/research_evaluation/final_results.json`: Verified valid JSON; figures match audit (WAI: 10.0, Safety F1: 1.0, 545 total failures).
- `data/research_evaluation/results_audit.json`: Verified valid JSON (12 systems audited).
- `data/research_evaluation/metrics/all_systems_summary.json`: Verified valid JSON.
- `data/research_evaluation/failure_analysis/failure_analysis.json`: Verified valid JSON containing 545 individual failure records.
- All 15+ academic documentation files in `docs/` verified present, non-empty, and consistent.

---

## 11. Command Reproducibility
- Audited in `docs/COMMAND_REPRODUCIBILITY_AUDIT.md`: Every documented installation, test, backend, frontend, offline, and evaluation command executed cleanly.

---

## 12. Security Audit
- Scanned repository for secret patterns (`sk-`, API keys); **zero active secrets** found in tracked files.
- Verified that `.env` and `.env.local` are strictly ignored by Git via `git check-ignore`.
- Verified that `.env.example` contains placeholders only.

---

## 13. Issues Found
- Zero genuine software bugs, missing files, or architectural regressions were found during clean-clone testing.

---

## 14. Issues Fixed
- Created `docs/COMMAND_REPRODUCIBILITY_AUDIT.md` and `docs/REPRODUCIBILITY_REPORT.md` to formally document clean-clone validation evidence.

---

## 15. Remaining Limitations
1. Benchmark evaluated on 25 standardized vignettes; human clinical variance requires live patient trials.
2. Clinical metrics evaluated via automated judge rubrics rather than human patients.
3. System is an academic research prototype and does not provide clinical diagnosis or replace human therapists.

---

## 16. Final Status
- **Automated Tests**: **100% PASS (31/31)**
- **Offline Multi-Agent Pipeline**: **100% PASS**
- **Web Application**: **100% PASS**
- **Security Audit**: **100% PASS (Zero Secrets)**
- **Reproducibility Classification**: **FULLY REPRODUCIBLE**
