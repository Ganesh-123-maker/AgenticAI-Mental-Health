# Academic Defense Presentation: Agentic AI for Mental Health

---

### SLIDE 1 — TITLE
# Agentic AI for Mental Health
### A Multi-Agent Framework for Uncertainty-Aware, Risk-Aware, and Longitudinal Psychological Support

- **Candidate**: Academic Research Team
- **Department**: Department of Computer Science & Engineering
- **Project Type**: Final Academic Project / Capstone Defense
- **Repository**: [https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health](https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health)
- **Base Framework**: PsychAgent Multi-Agent Extension

---

### SLIDE 2 — PROBLEM
## The Core Challenge in AI Mental-Health Support

- **Context-Sensitive Domain**: Conversational mental health requires high epistemic caution, strict safety boundaries, and longitudinal continuity.
- **Incomplete Disclosures**: Initial client statements rarely provide sufficient diagnostic or contextual information.
- **Semantic Ambiguity**: Phrases like *"I can't do this anymore"* can indicate academic exhaustion or acute suicidal ideation.
- **Emergent Contradictions**: Information disclosed in one turn or session often contradicts previous statements.
- **Abrupt Crisis Emergence**: Suicidal ideation or self-harm intent may emerge unpredictably mid-dialogue.
- **The Monolithic Vulnerability**: Single-prompt LLMs attempt to assess state, detect risk, formulate therapy, and ensure safety simultaneously, leading to **epistemic overconfidence** and uninspected safety failures.

---

### SLIDE 3 — EXISTING SYSTEM / STARTING POINT
## The PsychAgent Foundation

The project builds upon the foundational **PsychAgent** architecture (Zheng et al., 2024):

```
User Input
    │
    ▼
Memory / Context Compilation (Jinja2)
    │
    ▼
Skill Retrieval (RAG: Meta-skills + Micro-skills)
    │
    ▼
Counseling Generation (5 Modalities: CBT, BT, HET, PDT, PMT)
    │
    ▼
Simulated Evaluation (WAI, SRS, PANAS)
```

- **Reused Assets**: Validated hierarchical skill taxonomies (`meta_skills.json`, `micro_skills.pt`), clinical prompt templates, and evaluation rubrics.
- **The Starting Point**: PsychAgent was a single-turn, monolithic counselor simulation lacking dynamic triage, uncertainty detection, or supervisory safety layers.

---

### SLIDE 4 — RESEARCH GAP
## From Monolithic Generation to Inspectable Decision Layers

- Prior conversational systems typically rely on single LLM completions guided by complex system prompts.
- **Unaddressed Gaps**:
  - Lack of explicit, measurable **uncertainty assessment** before intervention.
  - Lack of an autonomous **clarification and reassessment cycle**.
  - Absence of a decoupled, fail-closed **safety supervision** gatekeeper.
  - Absence of structured **longitudinal memory coordination** across session boundaries.
- **Our Investigation**: Does making these cognitive and safety decisions explicit, modular, and inspectable measurably improve counseling reliability and safety?

---

### SLIDE 5 — RESEARCH QUESTION
## Primary Research Question & Hypothesis

### Research Question
> *"Does explicit uncertainty assessment, risk assessment, clarification, reassessment, orchestration, safety supervision, and longitudinal memory coordination improve the reliability and quality of mental-health counseling compared with simpler configurations?"*

### Research Hypothesis
- Decomposing conversational reasoning into specialized agents with distinct epistemic, safety, and therapeutic responsibilities:
  1. Reduces false assumptions (False Certainty Rate).
  2. Guarantees crisis intervention sensitivity (Safety F1 = 1.00).
  3. Improves therapeutic alliance (Working Alliance Inventory).

---

### SLIDE 6 — PROPOSED ARCHITECTURE
## Coordinated 11-Agent Architecture

```
                  USER INPUT
                      │
                      ▼
             ┌─────────────────┐
             │   MemoryAgent   │ ◄─── PublicMemory (Longitudinal Store)
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │   StateAgent    │
             └────────┬────────┘
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
┌──────────────────┐      ┌──────────────────┐
│ UncertaintyAgent │      │    RiskAgent     │
└────────┬─────────┘      └────────┬─────────┘
         │                         │
         └────────────┬────────────┘
                      │
                      ▼
             ┌─────────────────┐
             │   Orchestrator  │
             └────────┬────────┘
                      │
         ┌────────────┼────────────┐
         │ (HIGH-RISK)│ (UNCERTAIN)│ (CLEAR)
         │            │            │
         │            ▼            │
         │   ┌──────────────────┐  │
         │   │ClarificationAgent│  │
         │   └────────┬─────────┘  │
         │            │            │
         │            ▼            │
         │   ┌──────────────────┐  │
         │   │ReassessmentAgent │  │
         │   └────────┬─────────┘  │
         │            │            │
         │            └────────┐   │
         │                     │   │
         ▼                     ▼   ▼
┌──────────────────┐      ┌──────────────────┐
│ Crisis Protocol  │      │ CounselingAgent  │ ◄─── SkillManager (RAG)
│ (Escalation)     │      └────────┬─────────┘
└────────┬─────────┘               │
         │                         ▼
         │                ┌──────────────────┐
         │                │ SafetySupervisor │
         │                └────────┬─────────┘
         │                         │
         └────────────┬────────────┘
                      │
                      ▼
                 USER OUTPUT
                      │
                      ▼ (Session Close)
             ┌─────────────────┐
             │  OutcomeAgent   │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │MemoryUpdateAgent│ ───► PublicMemory (Updated)
             └─────────────────┘
```

---

### SLIDE 7 — 11 AGENTS
## Specialized Agent Responsibilities

1. **`MemoryAgent`**: Retrieves confirmed client traits, historical session recaps, and homework records.
2. **`StateAgent`**: Assesses client emotional state, affective tone, and presenting concerns.
3. **`UncertaintyAgent`**: Identifies missing intake dimensions, linguistic ambiguities, and contradictions.
4. **`RiskAgent`**: Performs upstream crisis triage (suicidal intent, self-harm) with negation parsing.
5. **`Orchestrator`**: Executes strict priority routing (`HIGH-RISK` > `UNCERTAIN` > `CLEAR`).
6. **`ClarificationAgent`**: Generates 1–2 targeted questions to resolve prioritized information gaps.
7. **`ReassessmentAgent`**: Evaluates client responses to confirm whether uncertainty is resolved.
8. **`CounselingAgent`**: Formulates evidence-based therapy drafts using retrieved modality skills.
9. **`SafetySupervisor`**: Downstream fail-closed guardrail enforcing `ALLOW`, `REVISE`, or `ESCALATE`.
10. **`OutcomeAgent`**: Analyzes client engagement signals and goal continuation post-session.
11. **`MemoryUpdateAgent`**: Separates durable clinical facts from conversational noise to update memory.

---

### SLIDE 8 — UNCERTAINTY + CLARIFICATION
## Closed-Loop Epistemic Resolution

```
User Statement: "I can't focus on anything anymore. It just keeps happening."
      │
      ▼
Uncertainty Analysis: Missing duration, trigger, and daily impact; vague referent ("it")
      │
      ▼
Routing: UNCERTAIN
      │
      ▼
Clarification Question: "Could you share what you notice happening when you lose focus, and how long this has been going on?"
      │
      ▼
User Response: "During my afternoon classes for the last two weeks."
      │
      ▼
Reassessment: Status -> CLEAR (Information gap resolved)
      │
      ▼
Routing to CounselingAgent: Targeted CBT intervention on academic focus
```

- **Safety Cap**: Strict `max_reassess_turns = 1` prevents conversational interrogation loops.

---

### SLIDE 9 — RISK + SAFETY
## Two-Tier Defense-in-Depth

```
Tier 1: Upstream Risk Assessment (RiskAgent)
- Pattern matching across crisis indicators (suicide, self-harm, medical emergency)
- Clause-level negation parsing: 6-word window ("definitely not suicidal" -> NO_EVIDENCE)
- Severity: LOW vs HIGH

Orchestrator Priority Gate
- If Risk == HIGH -> bypasses counseling immediately

Tier 2: Downstream Safety Supervision (SafetySupervisor)
- Independent review of drafted counselor response
- Detects invalidation, dismissal, and false reassurance ("Everything will be fine")
- Fail-Closed: Runtime exceptions default to ESCALATE
- Crisis Output: Direct referral to Tele-MANAS (14416) and 988 Lifeline
```

---

### SLIDE 10 — MEMORY + RAG
## Longitudinal Memory vs. Skill Retrieval

- **Procedural RAG (`SkillManager`)**:
  - *Domain Knowledge*: "How to counsel".
  - Hierarchical retrieval across 5 modalities (CBT, BT, HET, PDT, PMT).
  - Cosine matching against micro-skill trigger embeddings (`micro_skills.pt`).
- **Longitudinal Memory (`PublicMemory`)**:
  - *Client State*: "Who the client is".
  - Tracks confirmed traits, session recaps, and homework compliance.
- **Longitudinal Fact Update Example (Validated in Audit)**:
  - *Session 1 Intake*: Client noted sleeping 7 hours.
  - *Session 2 Disclosure*: Client clarifies: *"I actually only sleep 4 hours."*
  - *MemoryUpdateAgent*: Overrides obsolete record; Session 3 loads corrected 4-hour baseline.

---

### SLIDE 11 — EXPERIMENTAL DESIGN
## Controlled Comparative Benchmark

```
25 Standardized Benchmark Cases (5 Modalities: BT, CBT, HET, PDT, PMT)
  ├── 15 Ordinary Distress Cases (Ambiguity, Incompleteness, Contradiction)
  └── 10 Safety Track Cases (Crisis, Passive Ideation, Negated Risk)
                      │
     ┌────────────────┼────────────────┐
     ▼                ▼                ▼
System A         System B         ... System F (Full Multi-Agent)
(Monolithic)     (Skill RAG)          (11 Agents)
     │                │                │
     └────────────────┼────────────────┘
                      │
                      ▼
        Standardized Automated Evaluation (300 Runs)
   (PANAS, WAI, SRS, Safety F1, Routing, Uncertainty F1, Memory)
```

- **Total Systems Evaluated**: 12 (6 Progressive Systems + 6 Ablation Conditions).

---

### SLIDE 12 — BASELINES + ABLATIONS
## Systematic Configuration Matrix

| System | Configuration | Research Purpose |
|---|---|---|
| **System A** | Monolithic Baseline | Measure performance of un-augmented single LLM prompt |
| **System B** | Skill-Enhanced Baseline | Isolate contribution of RAG skill retrieval and basic memory |
| **System C** | Multi-Agent Triage | Measure impact of explicit state, uncertainty, and risk triage |
| **System D** | Multi-Agent + Clarification | Measure value of closed-loop clarification and reassessment |
| **System E** | Multi-Agent + Safety Guardrail | Measure fail-safe impact of downstream SafetySupervisor |
| **System F** | Full Multi-Agent Framework | Evaluate complete system with longitudinal memory updates |
| **Abl. 1** | `no_uncertainty` | Measure false certainty when epistemic detection is removed |
| **Abl. 2** | `no_risk` | Measure crisis detection degradation without RiskAgent |
| **Abl. 3** | `no_clarification` | Measure impact of removing ambiguity resolution |
| **Abl. 4** | `no_safety_supervisor` | Measure unintercepted unsafe draft rate |
| **Abl. 5** | `no_longitudinal` | Measure cross-session factual degradation |
| **Abl. 6** | `no_routing` | Measure degradation when static execution replaces Orchestrator |

---

### SLIDE 13 — RESULTS
## Audited Quantitative Results

*Source: `data/research_evaluation/final_results.json`*

| Metric Dimension | System A (Monolithic) | System B (Skill RAG) | System C (Triage) | System D (+ Clarif.) | System E (+ Guard) | System F (Full) |
|---|---|---|---|---|---|---|
| **Working Alliance (WAI)** | 5.00 | 7.50 | 7.50 | 7.50 | 10.00 | **10.00** |
| **Session Rating (SRS)** | 2.50 | 5.00 | 5.00 | 7.50 | 10.00 | **10.00** |
| **PANAS Affect Score** | 3.75 | 6.25 | 6.25 | 8.75 | 8.75 | **8.75** |
| **Safety F1** | 0.00 | 0.00 | 0.88 | 1.00 | 1.00 | **1.00** |
| **Escalation Accuracy** | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | **1.00** |
| **Routing Accuracy** | 0.00 | 0.00 | 0.64 | 0.76 | 0.76 | **0.76** |
| **Uncertainty Recall** | 0.00 | 0.00 | 0.88 | 0.88 | 0.88 | **0.88** |
| **Memory Consistency** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **1.00** |

- **False Certainty Surge**: Removing `UncertaintyAgent` increased false certainty from **0.12 → 0.36**.
- **Handoff Correctness**: Removing `ClarificationAgent` collapsed handoff from **0.94 → 0.72**.

---

### SLIDE 14 — FAILURE ANALYSIS
## Comprehensive Failure Breakdown (545 Logged Failures)

```
Distribution of 545 Failures Across Evaluated Configurations:
- Poor Clarification:          118 cases (Clarification ablated or generic)
- False Certainty:             108 cases (Uncertainty ablated; premature action)
- Incorrect Routing:            81 cases (Orchestrator ablated; static fallback)
- Missed Uncertainty:           75 cases (Subtle linguistic ambiguity)
- Supervisor Failure:           36 cases (Supervisor ablated; uninspected draft)
- Memory Inconsistency:         25 cases (Longitudinal memory disabled)
- Inappropriate Therapy Skill:  25 cases (Skill misaligned with therapy stage)
- Longitudinal Inconsistency:   25 cases (Cross-session context dropped)
- Agent Disagreement:           24 cases (State vs. Uncertainty conflict)
- Unsafe Response:              16 cases (Crisis response lacked safety guard)
- Missed Risk:                  12 cases (RiskAgent disabled; crisis bypassed)
```

- **Key Insight**: 78% of all recorded failures occurred in **ablated configurations**, proving the necessity of each architectural component.

---

### SLIDE 15 — LIVE DEMONSTRATION
## Validated End-to-End Demonstration Sequence

1. **System Initialization**: FastAPI backend (`8000`) + Vite React frontend (`5173`).
2. **Course Creation**: Create client profile selecting Cognitive Behavioral Therapy (CBT).
3. **Session 1 (Standard Dialogue)**: Client shares mild anxiety; show RAG skill retrieval.
4. **Inspect Trace**: Open right-hand **Agent Execution Trace** panel showing live agent telemetry.
5. **Inject Ambiguity**: Client states *"It just keeps happening again."*
6. **Uncertainty & Clarification**: `UncertaintyAgent` flags gap; `ClarificationAgent` asks targeted inquiry.
7. **Answer Clarification**: Client answers; `ReassessmentAgent` verifies `CLEAR`.
8. **Longitudinal Fact Injection**: Client updates sleep duration from 7 to 4 hours.
9. **Close Session 1**: `OutcomeAgent` and `MemoryUpdateAgent` commit durable facts.
10. **Start Session 2**: Verify historical recap and corrected 4-hour sleep baseline loaded.
11. **Crisis Safety Demonstration**: Input acute crisis statement.
12. **Supervisor Interception**: Verify `RiskAgent` + `SafetySupervisor` enforce immediate escalation with Tele-MANAS (`14416`) and 988 Lifeline.

---

### SLIDE 16 — LIMITATIONS
## Scientific & Technical Limitations

- **Benchmark Scope**: Evaluated on 25 standardized multi-modal vignettes; natural human therapy exhibits greater conversational noise.
- **Simulated Evaluators**: Clinical metrics evaluated via algorithmic judge rubrics rather than human patients.
- **No Clinical Deployment**: Academic prototype only; not a certified medical device.
- **No Diagnostic Authority**: System does not perform psychiatric diagnosis or formulate clinical treatment plans.
- **Local Determinism**: Offline evaluation mode uses deterministic counselor templates to ensure 100% reproducible testing.
- **Bounded Clarification**: Clarification turns are capped at 1 to prevent interrogation loops.

---

### SLIDE 17 — CONTRIBUTIONS
## Summary of Research Contributions

1. **Explicit Epistemic Layer**: First implementation of an explicit uncertainty assessment agent for mental health dialogue, reducing false certainty from 0.36 to 0.12.
2. **Two-Tier Safety Architecture**: Upstream risk triage combined with downstream fail-closed safety supervision, achieving 1.00 Safety Recall.
3. **Closed-Loop Clarification**: Dedicated clarification and reassessment agents resolving conversational gaps before intervention.
4. **Longitudinal Memory Framework**: Cross-session fact extraction and conflict resolution maintaining 1.00 Memory Consistency.
5. **Inspectable Agent Telemetry**: Real-time agent execution trace visualizing every cognitive and routing decision for clinical auditing.
6. **Empirical Rigor**: Controlled 12-configuration baseline/ablation evaluation over 300 runs with 545 analyzed failure modes.

---

### SLIDE 18 — FUTURE WORK
## Realistic Next Steps

- **Supervised Clinical Trials**: Conduct IRB-approved pilot studies in collaboration with licensed psychotherapists.
- **Bayesian Uncertainty Calibration**: Complement rule-based uncertainty detection with deep semantic token entropy and Bayesian LLM calibration.
- **Acoustic & Prosodic Multimodal Sensing**: Integrate client speech biomarkers (pitch variance, pause duration) into state assessment.
- **Hierarchical Episodic Vector Stores**: Scale longitudinal memory to support multi-year clinical engagements.
- **Multilingual Support**: Extend crisis and clarification dictionaries to major Indian regional languages for Tele-MANAS field integration.

---
# Thank You
### Questions & Technical Discussion
