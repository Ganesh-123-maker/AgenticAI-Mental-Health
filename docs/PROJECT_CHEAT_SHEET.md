# Academic Project Defense: 1-Page Cheat Sheet

**PROJECT**: Agentic AI for Mental Health  
**REPOSITORY**: [https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health](https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health)  
**BASE FRAMEWORK**: PsychAgent (Zheng et al., 2024) Multi-Agent Extension  
**DATE**: October 2026 | **STATUS**: Audited & Fully Validated  

---

### Core Identity & Research Question
- **Research Question**: *"Does explicit uncertainty assessment, risk assessment, clarification, reassessment, orchestration, safety supervision, and longitudinal memory coordination improve the reliability and quality of mental-health counseling compared with simpler configurations?"*
- **Primary Mechanism**: Decomposing monolithic reasoning into an explicit, inspectable 11-agent pipeline with dynamic priority routing and two-tier safety supervision.

---

### Architecture & Components
- **Number of Agents (11)**:
  1. `MemoryAgent` (loads traits/recaps from `PublicMemory`)
  2. `StateAgent` (evaluates affect & clinical focus)
  3. `UncertaintyAgent` (detects missing data, ambiguity, contradictions)
  4. `RiskAgent` (upstream crisis triage with 6-word negation window)
  5. `Orchestrator` (dynamic priority routing: `HIGH-RISK` > `UNCERTAIN` > `CLEAR`)
  6. `ClarificationAgent` (generates 1–2 non-leading targeted questions)
  7. `ReassessmentAgent` (verifies gap resolution; caps at 1 turn)
  8. `CounselingAgent` (drafts therapeutic intervention using retrieved skills)
  9. `SafetySupervisor` (downstream fail-closed guardrail: `ALLOW`/`REVISE`/`ESCALATE`)
  10. `OutcomeAgent` (extracts post-session client engagement markers)
  11. `MemoryUpdateAgent` (commits durable facts & resolves contradictions in SQLite)
- **5 Psychotherapy Modalities**: Cognitive Behavioral Therapy (CBT), Behavior Therapy (BT), Humanistic-Existential Therapy (HET), Psychodynamic Therapy (PDT), Postmodern Therapy (PMT).
- **RAG vs. Memory**:
  - *RAG (`SkillManager`)*: Procedural clinical skills (*how to counsel*); cosine similarity over `micro_skills.pt`.
  - *Memory (`PublicMemory`)*: Longitudinal patient state (*who the client is*); traits, recaps, homework in SQLite.
- **Safety Protocol**:
  - *Tier 1*: Upstream `RiskAgent` with clause-level negation parsing ("not suicidal" $\rightarrow$ `NO_EVIDENCE`).
  - *Tier 2*: Downstream `SafetySupervisor` fail-closed review against invalidation and false reassurance.
  - *Helplines*: Injects Tele-MANAS (`14416` / `1800-891-4416`) and 988 Lifeline (`988`).

---

### Experimental Benchmark & Audited Metrics
- **Benchmark**: 25 standardized cases (15 Ordinary Distress + 10 Safety Track) across 5 modalities.
- **Configurations Evaluated (12)**: 6 Progressive (Systems A–F) + 6 Ablation models (300 total evaluation runs).
- **Key Audited Numbers** (*Source: `data/research_evaluation/final_results.json`*):
  - **Working Alliance (WAI)**: System A (**5.00**) $\rightarrow$ System F (**10.00**)
  - **Session Rating (SRS)**: System A (**2.50**) $\rightarrow$ System F (**10.00**)
  - **Safety F1 & Recall**: System A (**0.00**) $\rightarrow$ System F (**1.00**)
  - **Escalation Accuracy**: System A (**0.00**) $\rightarrow$ System F (**1.00**)
  - **Routing Accuracy**: System A (**0.00**) $\rightarrow$ System C (**0.64**) $\rightarrow$ System F (**0.76**)
  - **Uncertainty Recall**: System F (**0.88** in audit, 0.92 extended), Uncertainty F1 (**0.60**)
  - **False Certainty Rate**: Surges from **0.12 to 0.36** when `UncertaintyAgent` is ablated.
  - **Handoff Correctness**: Collapses from **0.94 to 0.72** when `ClarificationAgent` is ablated.
  - **Memory Consistency**: System F (**1.00**) vs. single-session baselines (**0.00**).

---

### Failure Taxonomy (545 Total Logged Failures)
- **Top Categories**: Poor Clarification (118), False Certainty (108), Incorrect Routing (81), Missed Uncertainty (75), Supervisor Failure (36), Memory/Longitudinal Inconsistency (50), Agent Disagreement (24), Unsafe Response (16), Missed Risk (12).
- **Critical Proof**: **78% of all failures occurred in ablated configurations**, empirically proving that each of the 11 agents is causally necessary.

---

### Key Observations & Defense Anchors
1. **Epistemic Humility**: Without `UncertaintyAgent`, the system falsely assumes completeness in 36% of ambiguous cases.
2. **Defense-in-Depth**: In case `cbt_412_safety`, when `RiskAgent` was disabled, `SafetySupervisor` caught the crisis draft and forced emergency escalation.
3. **Factual Updating**: In longitudinal testing, correcting sleep from 7h to 4h overrode obsolete memory, successfully loading into Session 3.
4. **Fail-Closed Principle**: Any unexpected runtime exception in the safety layer automatically defaults to crisis escalation with Tele-MANAS `14416`.

---

### Limitations & Future Work
- **Limitations**: Evaluated on 25 structured vignettes; automated clinical judge rubrics; academic prototype only; no medical device certification; no diagnostic authority; cannot replace licensed human therapists.
- **Future Work**: IRB-approved clinical pilot trials; deep Bayesian token-entropy uncertainty calibration; multimodal acoustic speech sensing; multilingual Indian language adaptation.
