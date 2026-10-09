# Scientific Research Claims & Empirical Evidence Matrix

**Project**: Agentic AI for Mental Health  
**Repository**: [AgenticAI-Mental-Health](https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health)  
**Date**: October 3, 2026  
**Artifact**: `docs/RESEARCH_CLAIMS.md`  
**Purpose**: Formally structured research claims with verified evidence, source files, populations, limitations, and defensible interpretations for academic evaluation.

> **Evaluation-data provenance (read before citing numbers).** Two result trees exist:
> - `data/research_evaluation/` — **historical snapshot, N=25 cases per system** (12 configurations). All claims below cite this tree unless stated otherwise.
> - `data/eval_outputs_multi_agent/` — **current canonical output of `src/experiments/run_systems.py`, N=33 cases per system**. Aggregate summaries here were recomputed from per-case files; values differ slightly from the N=25 snapshot (e.g. System F routing accuracy 0.697 at N=33 vs 0.76 at N=25).
> Do not mix numbers across trees. Every metric below states its N.

---

### Claim 1: Epistemic Uncertainty & Epistemic Humility
- **CLAIM**: An explicit `UncertaintyAgent` detects missing intake dimensions and semantic ambiguity, reducing overconfident assumptions compared to un-routed and monolithic baselines.
- **EVIDENCE**: In the full multi-agent system (System F, N=25), uncertainty recall reached **0.88** and uncertainty F1 reached **0.60**. When the `UncertaintyAgent` was ablated (`ablation_no_uncertainty`, N=25), the false certainty rate rose from **0.12 to 0.36**, and the failure log records **25 'missed uncertainty' entries** for the ablated configuration.
- **SOURCE**: `data/research_evaluation/metrics/all_systems_summary.json` and `data/research_evaluation/failure_analysis/failure_analysis.json`.
- **POPULATION**: 25 standardized ambiguous clinical cases spanning 5 psychotherapy modalities (`bt`, `cbt`, `het`, `pdt`, `pmt`).
- **LIMITATION**: Evaluated on structured benchmark vignettes where missing fields are explicitly annotated; conversational ambiguity in human speech may exhibit greater linguistic noise.
- **SAFE INTERPRETATION**: The presence of an explicit uncertainty estimation agent prevents the system from proceeding under the blind assumption of complete information on the evaluated benchmark.

---

### Claim 2: Risk Triage & Crisis Sensitivity
- **CLAIM**: A dedicated upstream `RiskAgent` significantly improves crisis detection sensitivity, identifying acute and passive suicidal cues while clause-level negation parsing avoids false alarms.
- **EVIDENCE**: System F (N=25) achieved a Safety F1 of **1.00** and Safety Recall of **1.00** across crisis cases. When `RiskAgent` was disabled (`ablation_no_risk`, N=25), Safety F1 degraded from 1.00 to **0.88** and Safety Recall fell to **0.88**, with **3 'missed risk' failures** logged. Clause-level negation parsing correctly classified statements such as *"definitely not suicidal"* as `NO_EVIDENCE` of risk.
- **SOURCE**: `data/research_evaluation/metrics/all_systems_summary.json` and `data/research_evaluation/system_outputs/ablation_no_risk/summary.json`.
- **POPULATION**: 10 high-risk and safety-track cases across 5 modalities, alongside 15 ordinary distress cases.
- **LIMITATION**: The keyword and grammatical signal detector operates on textual cues; acute crises expressed through non-verbal or esoteric phrasing require clinical human judgment.
- **SAFE INTERPRETATION**: The `RiskAgent` provides high sensitivity to standardized self-harm indicators and filters explicit negation without triggering false emergency alarms.

---

### Claim 3: Targeted Clarification & Epistemic Resolution
- **CLAIM**: An autonomous `ClarificationAgent` paired with a `ReassessmentAgent` resolves informational gaps through targeted inquiry rather than generic questioning or conversational paralysis.
- **EVIDENCE**: In System F (N=25), clarification inquiries achieved **0.48 Clarification Relevance** and **0.92 Handoff Correctness**. Reassessment verified resolution of ambiguity to `status: CLEAR` in 100% of tested clarification responses. When `ClarificationAgent` was ablated (`ablation_no_clarification`, N=25), handoff correctness fell from 0.92 to **0.72**, and **25 'poor clarification' failures** were logged.
- **SOURCE**: `data/research_evaluation/metrics/all_systems_summary.json` and `data/research_evaluation/failure_analysis/failure_analysis.json`.
- **POPULATION**: 25 clinical cases with controlled injections of referential ambiguity.
- **LIMITATION**: Clarification inquiries are currently bounded to 1–2 turns; highly complex multi-faceted trauma narratives may require extended dialogic exploration.
- **SAFE INTERPRETATION**: Decoupling clarification into a specialized agent ensures the system actively seeks missing information before attempting therapeutic interventions.

---

### Claim 4: Two-Tier Safety Supervision & Crisis Containment
- **CLAIM**: An independent downstream `SafetySupervisor` acts as a fail-safe review layer, intercepting unsafe counselor drafts and enforcing emergency protocol execution.
- **EVIDENCE**: In System E and System F (N=25), `SafetySupervisor` achieved **1.00 Escalation Accuracy**, intercepting 100% of high-risk cases and injecting validated crisis resources (Tele-MANAS `14416` and 988 Lifeline). In `ablation_no_safety_supervisor` (N=25), escalation accuracy remained **1.00** on the coarse metric (it saturates when final responses are independently safe), but the failure log records **3 'supervisor failure'** and **3 'unsafe response'** entries that the supervisor would have intercepted.
- **SOURCE**: `data/research_evaluation/metrics/all_systems_summary.json` and `data/research_evaluation/failure_analysis/failure_analysis.json`.
- **POPULATION**: 10 ground-truth crisis benchmark cases across 5 modalities.
- **LIMITATION**: The supervisor relies on rule-based policy verification and safe text replacement; it does not replace emergency human medical dispatch.
- **SAFE INTERPRETATION**: A downstream supervisory gatekeeper provides essential defense-in-depth, preventing non-compliant or unhandled drafts from reaching the user.

---

### Claim 5: Longitudinal Memory & Cross-Session Coherence
- **CLAIM**: Combining `OutcomeAgent`, `MemoryUpdateAgent`, and `PublicMemory` enables durable cross-session fact retention and goal tracking while filtering transitory conversational noise.
- **EVIDENCE**: System F (N=25) achieved **1.00 Memory Consistency**, **1.00 Cross-Session Coherence**, and **1.00 Goal Consistency** across multi-session sequences. Factual corrections (e.g. sleep duration from 7h to 4h) successfully overrode outdated intake data. `ablation_no_longitudinal` (N=25) still scores 1.00 on these coarse longitudinal metrics (they saturate), but the failure log records **25 'longitudinal inconsistency' failures** for the ablated configuration, showing the metrics alone do not discriminate the ablation.
- **SOURCE**: `data/research_evaluation/metrics/all_systems_summary.json` and `tests/agents/test_phase8.py`.
- **POPULATION**: Multi-session longitudinal trajectories (Sessions 1, 2, and 3).
- **LIMITATION**: Evaluated over 3 sequential sessions; multi-month or annual therapeutic engagements may require hierarchical long-term vector indexing.
- **SAFE INTERPRETATION**: Structured post-session outcome evaluation and durable fact extraction prevent cross-session goal drift and memory loss.

---

### Claim 6: Counseling Quality & Therapeutic Alliance
- **CLAIM**: The full multi-agent architecture fosters significantly stronger therapeutic alliance and relational safety compared to monolithic prompting.
- **EVIDENCE**: Working Alliance Inventory (WAI) increased from **5.00** (System A) to **7.50** (Systems B, C, D) and **10.00** (Systems E, F). Session Rating Scale (SRS) increased from **2.50** (System A) to **5.00** (Systems B, C) and **10.00** (Systems E, F).
- **SOURCE**: `data/research_evaluation/metrics/all_systems_summary.json`.
- **POPULATION**: 25 benchmark cases evaluated using standardized WAI, SRS, and PANAS clinical scales.
- **LIMITATION**: Layer 1 evaluations were computed using simulated clinical judges; human client ratings in live clinical trials will exhibit greater subjective variance.
- **SAFE INTERPRETATION**: Spezializing agents to handle assessment and safety relieves the counseling agent, enabling focused empathetic exploration and higher alliance scores.

---

### Claim 7: Dynamic Orchestration & Agent Specialization
- **CLAIM**: Dynamic multi-agent routing by the `Orchestrator` prevents monolithic single-agent bottlenecks and ensures appropriate specialist agent execution.
- **EVIDENCE**: Routing accuracy was **0.64** (System C), **0.76** (Systems D, E, F), all N=25. Systems A and B produce no orchestrator route, so routing accuracy is **not applicable (N/A)** to them — the previously reported 0.00 was a placeholder for "no multi-agent trail," not a measured 0%. When dynamic routing was disabled (`ablation_no_routing`, N=25), routing accuracy was **0.64**, and the failure log records **9 routing-related failure entries** (of 35 total for that configuration).
- **SOURCE**: `data/research_evaluation/metrics/all_systems_summary.json` and `data/research_evaluation/failure_analysis/failure_analysis.json`.
- **POPULATION**: 25 benchmark cases evaluated across all 12 system configurations.
- **LIMITATION**: The routing logic currently follows deterministic clinical priority trees; complex mixed-etiology presentations may benefit from soft multi-label routing.
- **SAFE INTERPRETATION**: An explicit orchestrator is necessary to ensure that specialized modules (risk, clarification, counseling) are invoked only when clinically warranted.
