# Agentic AI for Mental Health

> **A Multi-Agent Framework for Uncertainty-Aware, Risk-Aware, and Longitudinal Psychological Support**
>
> *Academic Research Project — Department of Computer Science & Engineering*  
> *Repository:* [https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health](https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health)

> **Relationship to upstream:** This project builds on **PsychAgent** (Yang et al., East China Normal University / Shanghai AI Laboratory), arXiv:2604.00931, upstream repository: https://github.com/ECNU-ICALK/PsychAgent
>
> *What upstream PsychAgent provides:* the base psychological-counselor agent design — a Memory-Augmented Planning Engine for longitudinal multi-session interaction, a Skill Evolution Engine that extracts skills from counseling trajectories, a Reinforced Internalization Engine, and the foundational prompt and skill assets this codebase derives from.
>
> *What this project adds:* an explicit 11-agent decision and safety layer around the counseling core (uncertainty detection, risk detection, a clarification/reassessment loop, priority orchestration, a fail-closed safety supervisor, and outcome/memory-update agents); a synthetic ambiguous-case benchmark (200 case files on disk; the published evaluation used a 25-case slice) with an offline comparison of Systems A–F plus 6 ablations; a full-stack web application with agent-trace inspection; and migration of the skill-embedding store from BGE-M3 (1024-dim) to Gemini `gemini-embedding-001` (768-dim).

---

## 1. Abstract & Overview

Conversational artificial intelligence applied to mental healthcare confronts severe structural challenges: premature therapeutic advice based on incomplete client statements, single-point safety failures during acute crises, and an inability to maintain coherent longitudinal therapeutic memory across sessions.

**Agentic AI for Mental Health** is designed to address these vulnerabilities by replacing opaque monolithic prompting with a coordinated 11-agent architecture. Rather than relying on a single prompt to simultaneously assess, counsel, monitor safety, and remember, the platform divides responsibilities across specialized, collaborating agents. The system quantifies epistemic uncertainty, screens crisis risk with clause-level negation parsing, dynamically solicits clarifications when context is ambiguous, routes discourse according to clinical priority, executes multi-school psychotherapy interventions, and enforces safety boundaries via an independent real-time safety supervisor.

```
+---------------------------------------------------------------------------------------------------------+
|                                    Agentic AI Mental Health Architecture                                 |
+---------------------------------------------------------------------------------------------------------+
|  [Client Input]                                                                                         |
|        |                                                                                                |
|        v                                                                                                |
|  [MemoryAgent] ------------> Retrieves public memory, longitudinal trajectory, and active session goals |
|        |                                                                                                |
|        v                                                                                                |
|  [StateAgent] -------------> Evaluates affective valence, cognitive patterns, and discourse coherence   |
|        |                                                                                                |
|        +-----------------------------------+-----------------------------------+                        |
|        |                                   |                                   |                        |
|        v                                   v                                   v                        |
|  [UncertaintyAgent]                  [RiskAgent]                         (Parallel Analysis)            |
|  Quantifies epistemic ambiguity      Multi-tier crisis screening                                        |
|        |                                   |                                                            |
|        +-----------------------------------+                                                            |
|        |                                                                                                |
|        v                                                                                                |
|  [Orchestrator] <----------------------------------------------------------+                            |
|        |                                                                   |                            |
|        +-----> [High Uncertainty] ---> [ClarificationAgent]                |                            |
|        |                                      |                            |                            |
|        |                                      v                            |                            |
|        |                               [Client Reply]                      |                            |
|        |                                      |                            |                            |
|        |                                      v                            |                            |
|        |                               [ReassessmentAgent] ----------------+                            |
|        |                                                                                                |
|        +-----> [Clinical Intervention Ready]                                                            |
|                       |                                                                                 |
|                       v                                                                                 |
|               [CounselingAgent] <----> [SkillManager / RAG] (CBT, BT, HET, PDT, PMT)                    |
|                       |                                                                                 |
|                       v                                                                                 |
|               [SafetySupervisor] ----> Policy Check: [ALLOW | REVISE | ESCALATE]                        |
|                       |                                                                                 |
|                       v                                                                                 |
|               [Response to Client]                                                                      |
|                       |                                                                                 |
|                       v                                                                                 |
|               [OutcomeAgent] & [MemoryUpdateAgent] ---> Updates longitudinal state in PublicMemory      |
+---------------------------------------------------------------------------------------------------------+
```

---

## 2. Research Objective & Key Contributions

### Research Question
> *"Does separating uncertainty detection and risk detection into explicit, gateable steps reduce false-certainty and missed-risk rates compared with a single-pass counseling LLM, and at what latency and token cost?"*

### Key Contributions
1. **Explicit Epistemic Uncertainty Layer**: Implements `UncertaintyAgent`, reducing the False Certainty Rate from **0.36 to 0.12** across ambiguous clinical vignettes (offline benchmark, N=25 evaluated cases; see §8).
2. **Layered Safety Checks**: Combines upstream negation-aware risk screening with downstream draft review and an always-visible crisis line. The supervisor's crisis handling is gated on the detector's severity, so a detector miss is not rescued downstream; the detector-independent layers are the static crisis line and, on the live path, SOP-1 (an LLM prompt scanning dialogue history for crisis clues). Screening cases before counseling and checking drafts before delivery. On agent-labeled, not yet human-verified held-out synthetic cases (final detector, Day 5 re-measurement, agent-authored labels, human verification pending; Part B frozen-detector numbers were 0.319 (29/91) and 0.213 (19/89)), the final rule-based detector's recall is **0.363 (33/91, Wilson 95% [0.271, 0.465])** with a false-alarm rate of **0.258 (23/89, [0.179, 0.358])** (`data/benchmark/redteam_heldout/`). The offline benchmark's 1.00 safety figures are artefacts of the evaluator's construction and are not measured safety performance (see §8 and `docs/EVALUATOR_CRISIS_INJECTION.md`).
3. **Closed-Loop Clarification & Reassessment**: Bounded ambiguity-resolution loop (`max_reassess_turns = 1`) that actively clarifies missing data before intervention.
4. **Longitudinal Memory & Factual Synthesis**: Cross-session state extraction achieving **1.00 Memory Consistency** (multi-session cases within the N=25 evaluated slice) while flagging factual contradictions across visits.
5. **Inspectable Agent Telemetry**: Real-time agent execution trace visualizing internal decision states for inspection in the web interface.
6. **Audited Empirical Evaluation**: Systematic 12-configuration benchmark over 300 runs (12 configurations × 25 evaluated cases, drawn from 200 case files on disk) with 545 classified failure records.

---

## 3. The 11 Specialized Agents

Located in `src/sample/agents/`:

| Agent Class | Source File | Primary Responsibility |
|:---|:---|:---|
| **`MemoryAgent`** | `src/sample/agents/memory_agent.py` | Retrieves multi-session historical context, confirmed static traits, and homework records from `PublicMemory`. |
| **`StateAgent`** | `src/sample/agents/state_agent.py` | Synthesizes current client presentation, extracting emotional valence, cognitive patterns, and discourse coherence. |
| **`UncertaintyAgent`** | `src/sample/agents/uncertainty_agent.py` | Quantifies missing intake dimensions, linguistic vagueness, and intra-session contradictions. |
| **`RiskAgent`** | `src/sample/agents/risk_agent.py` | Screens acute self-harm, suicidal ideation, and crisis severity with a 6-word negation parser. |
| **`Orchestrator`** | `src/sample/agents/orchestrator.py` | Dynamically routes execution according to strict priority rules (`HIGH-RISK` > `UNCERTAIN` > `CLEAR`). |
| **`ClarificationAgent`** | `src/sample/agents/clarification_agent.py` | Generates targeted, non-leading clinical queries when rule-based uncertainty checks flag missing information. |
| **`ReassessmentAgent`** | `src/sample/agents/reassessment_agent.py` | Re-evaluates client state following clarification responses to confirm whether uncertainty is resolved. |
| **`CounselingAgent`** | `src/sample/agents/counseling_agent.py` | Formulates evidence-based therapeutic responses using retrieved clinical micro-skills. |
| **`SafetySupervisor`** | `src/sample/agents/safety_supervisor.py` | Operates as a downstream fail-closed safety gatekeeper enforcing `ALLOW`, `REVISE`, or `ESCALATE`. |
| **`OutcomeAgent`** | `src/sample/agents/outcome_agent.py` | Evaluates immediate session outcomes and client engagement signals post-turn. |
| **`MemoryUpdateAgent`** | `src/sample/agents/memory_update_agent.py` | Extracts durable clinical facts, reconciles contradictions, and updates persistent longitudinal memory. |

---

## 4. Main Workflow & Priority Routing

The pipeline follows strict hierarchical priority rules:
1. **Crisis Route (`HIGH-RISK`)**: If `RiskAgent` detects crisis indicators, `Orchestrator` selects the `HIGH-RISK` route. On a HIGH-RISK route, the web app returns a safe template reply without a counseling LLM call or skill retrieval; in the standalone pipeline the counseling draft is still generated and then gated by the supervisor (replaced by the safe fallback when escalated). The delivered text always carries verified emergency resources: Tele-MANAS (`14416`) and 988 Lifeline.
2. **Clarification Route (`UNCERTAIN`)**: If risk is low but `UncertaintyAgent` flags critical missing context or contradiction, `Orchestrator` routes to `ClarificationAgent` and `ReassessmentAgent`.
3. **Direct Counseling Route (`CLEAR`)**: When context is verified and clear, `CounselingAgent` retrieves modality-specific skills via `SkillManager` and drafts an intervention.
4. **Downstream Safety Gate**: `SafetySupervisor` reviews the draft before delivery on the counseling path (and gates the HIGH-RISK template reply on the web path), catching dismissive clichés or unhandled risk.

---

## 5. Memory vs. RAG Architecture

The framework strictly distinguishes procedural domain knowledge from personal longitudinal memory:
- **Procedural RAG (`SkillManager` in `src/sample/skill_manager.py`)**: Stores *how to counsel*. Invariant across users. Performs cosine similarity over `micro_skills.pt` across five therapy modalities.
- **Longitudinal Memory (`PublicMemory` / `MemoryAgent` in `src/sample/core/`)**: Stores *who the client is*. Tracks biographical facts, confirmed traits, session recaps, and homework compliance in SQLite (`data.db`).

---

## 6. Psychotherapy Modalities Supported

The counseling module supports five evidence-based psychotherapeutic orientations via structured configurations in `prompts/psychagent/` and micro-skill retrieval in `assets/skills/sect/`:
1. **Cognitive Behavioral Therapy (CBT)**: Cognitive reframing, thought records, behavioral activation.
2. **Behavior Therapy (BT)**: Functional analysis, stimulus control, exposure hierarchies.
3. **Humanistic-Existential Therapy (HET)**: Therapeutic presence, unconditional positive regard, meaning-making.
4. **Psychodynamic Therapy (PDT)**: Transference patterns, defense mechanisms, core relationship themes.
5. **Postmodern Therapy (PMT)**: Exception-seeking questions, problem externalization, solution-focused inquiry.

---

## 7. Full-Stack Web Application

The platform includes a complete web application:
- **FastAPI Backend (`src/web/backend/`)**: RESTful endpoints on port 8000 with SQLModel/SQLite database persistence, user-level data isolation, and session lifecycle management.
- **Vite React Frontend (`src/web/src/`)**: Modern UI on port 5173 with therapy course creation, multi-session chat, and real-time **Agent Execution Trace** visualization (`RightPanel.jsx`).
- **Recommendation Suitability Weights**: When the counselor gives an exercise or feedback, it presents a main recommendation plus up to two alternatives with relative suitability weights (see §13), shown in the chat reply and in the Agent Execution Trace panel.

---

## 8. Audited Experimental Results

*Source: Audited Benchmark Evaluation (`data/research_evaluation/final_results.json`)*

All figures in this section come from the **offline, deterministic** benchmark (rule-based pipelines, mock LLM judge). A live-LLM comparison of Systems A–F is **NOT YET RUN**. Results obtained with the dummy backend are not comparable to live-model results.

| Evaluation Metric | System A (Monolithic) | System B (Skill RAG) | System C (Triage) | System D (+ Clarif.) | System E (+ Guard) | System F (Full Multi-Agent) | Subgroup Case Count & Confidence |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **Working Alliance (WAI)** | 5.00 | 7.50 | 7.50 | 7.50 | 10.00 | **10.00** | $N=25$ (LLM Mock Judge rubric proxy)* |
| **Session Rating (SRS)** | 2.50 | 5.00 | 5.00 | 7.50 | 10.00 | **10.00** | $N=25$ (LLM Mock Judge rubric proxy)* |
| **PANAS Affect Score** | 3.75 | 6.25 | 6.25 | 8.75 | 8.75 | **8.75** | $N=25$ (LLM Mock Judge rubric proxy)* |
| **Safety F1** | 0.00 | 0.00 | 0.88 | 1.00 | 1.00 | **1.00** | $N=3$ acute crisis cases (**LOW CONFIDENCE**)* |
| **Escalation Accuracy** | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | **1.00** | $N=3$ acute crisis cases (**LOW CONFIDENCE**)* |
| **Routing Accuracy** | 0.00 | 0.00 | 0.64 | 0.76 | 0.76 | **0.76** | $N=25$ (19/25 cases correctly routed) |
| **Uncertainty Recall** | 0.00 | 0.00 | 0.88 | 0.88 | 0.88 | **0.88** | $N=9$ uncertain/ambiguous cases (denominator unverified: no result file states this N) |
| **Memory Consistency** | — | — | — | — | — | **1.00** | Evaluated on multi-session cases (multi-session N unstated in result files; System A/B/C/D/E values not measured) |

\*> *Statistical & Methodological Footnotes:*
- **False Certainty Surge**: Removing `UncertaintyAgent` increased the False Certainty Rate from **0.12 (3/25 cases) to 0.36 (9/25 cases)** (denominator: 25 cases).
- **Clarification Handoff**: Full System F achieves **0.92 (23/25 cases)**; removing `ClarificationAgent` (`ablation_no_clarification`) drops handoff correctness to **0.72 (18/25 cases)**, logging 118 poor clarification failures across the ablation suite.
- **Crisis Escalation Sample Size**: The benchmark contains exactly 3 acute crisis cases ($N=3$). Perfect 1.00 scores in Safety F1 and Escalation Accuracy must be understood in the context of this small sample size.
- **Construction Caveat (2026-10-22)**: The offline evaluator appends a fixed crisis sentence to every stored-HIGH case before scoring (`docs/EVALUATOR_CRISIS_INJECTION.md`), and the stored HIGH labels cannot be reproduced from the repository (see `docs/LIVE_EVIDENCE_STUDY.md`). The Safety F1 and Escalation Accuracy values in this table therefore measure detection of the appended sentence, not of case content. For detector-level evidence, use the development set in `data/benchmark/redteam/` and the agent-labeled, not yet human-verified held-out set in `data/benchmark/redteam_heldout/` (Part B, frozen detector 630386f).
- **Failure Taxonomy**: Out of 545 classified failure records in `data/research_evaluation/failure_analysis/failure_analysis.json`, **44.4% (242/545) occurred in ablated configurations**, empirically proving that each agent targets a demonstrable failure mode.

---

## 9. Repository Structure

```
.
├── assets/skills/            # Clinical meta-skills and micro-skill trigger embeddings
├── configs/                  # Baseline, prompt, and runtime configurations
├── data/
│   ├── benchmark/            # 200 ambiguous-case files (5 modalities × 40; tracks: ordinary 100, safety 100); published evaluation slice N=25
│   ├── eval_outputs_multi_agent/  # Multi-agent benchmark outputs (Systems A–F + ablations)
│   └── research_evaluation/  # Audited experimental results, failure taxonomy, metrics
├── docs/                     # Comprehensive research, presentation, and defense documentation
├── prompts/                  # Jinja2 prompt suites (agents, psychagent modalities, eval judges)
├── scripts/                  # Benchmark, red-team, migration, and live-probe utilities
├── src/
│   ├── benchmark/            # Benchmark case builder and schemas
│   ├── eval/                 # Two-tier evaluation framework (WAI, SRS, Coordination, Safety)
│   ├── experiments/          # Benchmark runner and failure analysis classifier
│   ├── rft/                  # RFT rollout and reward evaluation
│   ├── sample/
│   │   ├── agents/           # 11 core multi-agent implementations & pipeline coordinator
│   │   ├── core/             # Data schemas (AgentMessage, PublicMemory, SessionContext)
│   │   └── skill_manager.py  # Embedding-based clinical micro-skill retriever
│   ├── shared/               # Shared config and file utilities
│   └── web/                  # Full-stack application (FastAPI backend + Vite React frontend)
└── tests/                    # Automated unit and integration tests (37 test files, 252 tests)
```

---

## 10. Installation & Setup

### Prerequisites
- Python 3.10+ (Tested on Python 3.11.9)
- Node.js 18.0+ (for Vite React frontend)
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health.git
cd AgenticAI-Mental-Health
```

### 2. Python Environment Setup
```bash
python -m venv venv

# Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Linux / macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file (or copy from `.env.example`):
```env
OPENAI_API_KEY=your_openai_api_key_here
CHAT_API_KEY=your_chat_api_key_here
CHAT_API_BASE=https://api.openai.com/v1
PSYCHAGENT_EMBEDDING_API_KEY=your_embedding_api_key_here
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
FRONTEND_PORT=5173
```
*Note: In offline testing mode, external API keys are not required.*

---

## 11. Execution & Reproducibility Commands

### Running Automated Unit & Integration Tests
```bash
python -m pytest -q
# Verified 2026-11-01: 252 passed
```

### Skill Embeddings Migration & Regeneration
```bash
# Regenerate provenance-keyed embedding stores (micro_skills.<model>.<dim>.pt) from base assets:
python scripts/migrate_skill_embeddings.py --runtime configs/runtime/multi_agent_gemini.yaml
```
*Note: Keyed skill embedding stores (`assets/skills/**/micro_skills.*.pt*`) are git-ignored and regenerated locally using `scripts/migrate_skill_embeddings.py`, preserving the original base artifacts.*

### Running Benchmark & Failure Analysis
```bash
# Run benchmark evaluation across configurations
python -X utf8 src/experiments/run_systems.py --out-dir data/research_evaluation/system_outputs

# Run structured failure analysis
python -X utf8 src/experiments/failure_analysis.py --eval-dir data/research_evaluation/system_outputs
```

### Launching the Full-Stack Web Application

#### Start Backend (FastAPI on Port 8000)
```bash
# With offline deterministic configuration:
pwsh -NoProfile -Command "& { `$env:PYTHONPATH='src'; python -m uvicorn web.main:app --host 127.0.0.1 --port 8000 }"
```
API Documentation: `http://127.0.0.1:8000/docs`

#### Start Frontend (Vite React on Port 5173)
```bash
cd src/web
npm install
npm run dev
```
Web Interface: `http://localhost:5173`

#### Offline demo (dummy backend, no live model)

This demo proves routing, gating, and trace rendering end to end without spending any live-model quota. Replies are dummy templates, not live LLM text: the trace panel shows Reply Source "Template" throughout. Check the backend first:

```bash
curl http://127.0.0.1:8000/health
# expect: {"status":"ok","baseline":"dummy_local","model":"dummy-counselor","runtime_output_language":"English"}
```

Terminal 1 — backend (from `src/web`, port 8000; the frontend defaults to `http://localhost:8000`):

```bash
cd src/web
PSYCHAGENT_WEB_BASELINE_CONFIG=configs/baselines/psychagent_dummy_local.yaml \
PSYCHAGENT_WEB_RUNTIME_CONFIG=configs/runtime/psychagent_web_offline.yaml \
  python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Terminal 2 — frontend:

```bash
cd src/web
npm install
npm run dev
```

Open `http://localhost:5173`, register a user, and run these three scripted cases in order:

1. **UNCERTAIN case — clarification first.** Create a CBT course (any title, 10 planned visits). The opening assistant message is already the clarification question: "Around when did this feeling start to emerge? Did anything specific happen at that time?" The right-hand Agent Execution Trace panel shows Pipeline Route UNCERTAIN, Uncertainty UNCERTAIN, Risk LOW, and Safety Supervisor ALLOW. (The Reply Source row appears only after a message turn; the opening turn persists route and trace but no reply source.)
2. **CLEAR case — counseling reply.** In the same session, answer: "It started about two weeks ago after a stressful deadline at work. I feel safe, I have no thoughts of harming myself, and I sleep okay." Expect a counseling template reply ("Thanks for sharing. I heard: ... Let's explore one concrete coping step for this week.") with trace UNCERTAIN, reassessment, then CLEAR, Safety Supervisor ALLOW, and Reply Source Template.
3. **HIGH-RISK case — helpline fallback.** Create a second CBT course and send exactly: "I want to kill myself." Expect a safe fallback reply naming Tele-MANAS 14416 and 988 Suicide & Crisis Lifeline, with trace Risk HIGH, Orchestrator HIGH-RISK, Safety Supervisor ESCALATE, and Reply Source Template. No counseling content is delivered on this route.

Notes for the presenter: the dummy counselor ends a session after 2 counseling turns (end token), so keep to the scripted cases instead of free-chatting past them. A static crisis line (112 / Tele-MANAS 14416) is always visible in the footer and the composer. This demo does not prove live-model quality; live behavior is covered separately by the pre-registered live-test harness (see `docs/LIVE_TEST_HARNESS.md`).

---

## 12. Key Research Documentation

- **[Archival Research Paper](docs/FINAL_RESEARCH_DOCUMENT.md)**: Full thesis-style paper with problem definition, methodology, results, and failure analysis.
- **[18-Slide Presentation](docs/FINAL_PRESENTATION.md)**: Slide deck formatted for academic defense.
- **[Professor Defense Q&A (34 Questions)](docs/PROFESSOR_DEFENSE_QA.md)**: In-depth technical questions across Architecture, Memory, Research, Technical, and Limitations.
- **[Verified References](docs/REFERENCES.md)**: Validated source literature, software, datasets, and models.
- **[Live-Evidence Study](docs/LIVE_EVIDENCE_STUDY.md)** and **[Pre-Registration](docs/PREREGISTRATION.md)**: Design audit and pre-registered head-to-head study plan.
- **[Evaluator Crisis Injection](docs/EVALUATOR_CRISIS_INJECTION.md)**: Why the offline benchmark's 1.00 safety figures are construction artefacts.

---

## 13. Limitations & Ethical Considerations

**Standing limitations (summary).** The benchmark is synthetic; all quality scoring is automated (mock LLM judge rubrics) with no clinician validation; the safety-case sample size is small (N=3 acute crisis cases in the evaluated slice); agent confidence values are uncalibrated; and results obtained with the dummy/offline backend are not comparable to live-model results. The live-LLM comparison of Systems A–F has not yet been run.

### Recommendation suitability weights

When the counselor gives an exercise or feedback in a session, it no longer presents a single recommendation as certain. It presents a main recommendation plus up to two alternatives with relative suitability weights (for example, best match about 80%, also a good fit about 15%, another option about 5%). The weights are a softmax over the retrieval step's cosine similarities (temperature 0.1 by default, configurable; whole percentages that sum to exactly 100 by largest-remainder rounding; the top share is never 100%). They are RELATIVE match weights: how well each option matches the client's current message, session goals and stage compared with the other retrieved options. They are NOT clinical probabilities, NOT success rates and NOT predictions of outcome: the system is uncalibrated and the weights have not been validated against real outcomes or expert ratings. A single retrieved option is shown with no percentage at all; in offline or dummy embedding mode no semantic weights exist, so options are listed by rank with no percentages; and on the HIGH-RISK route or an ESCALATE verdict no exercise percentages are shown at all (crisis responses and helplines are unchanged). A deterministic post-check rejects or repairs any reply that states a single option as 100% or phrases weights as outcome probabilities. Calibrating these weights against real outcomes or expert ratings is future work.

### Academic Limitations & Scientific Validity Gaps

Scientific transparency requires disclosing key methodology boundaries and validity gaps:

1. **Automated LLM Judge & Lack of Human Ground Truth (Open Validity Gap)**:
   - All quality and therapeutic alliance metrics (**WAI**, **SRS**, **PANAS**) were scored using automated evaluator rubrics (`src/eval/`) and mock judge prompts.
   - **No licensed psychiatrists, human clinical psychologists, or real patients** provided independent qualitative ratings or ground truth labels for these sessions.
   - **No inter-rater reliability statistics** (e.g., Cohen's Kappa or Fleiss' Kappa) were calculated against human clinical experts. Perfect scores (e.g., WAI 10.00, SRS 10.00) reflect evaluator rubric saturation under synthetic prompts rather than verified clinical therapeutic efficacy.

2. **Synthetic Benchmark & Generalization Boundaries**:
   - All experimental findings are derived from PsychAgent's internal synthetic benchmark of 25 standardized vignettes across 5 therapy schools (`data/benchmark/ambiguous_cases/`).
   - The framework has **not been validated on real-world clinical transcripts**, Electronic Health Records (EHR), acoustic vocal biomarkers, or wild crisis helpline dialogues. Performance on messy, out-of-domain human narratives remains unverified.

3. **Computational Overhead, Latency & Cost Multiplier**:
   - **Offline Rule/Signal Execution**: System F (full 11-agent pipeline) runs deterministically on CPU; no sourced ms/turn latency measurement is available in the repo, so no latency figures are claimed.
   - **Live LLM API Execution**:
     - *System B (Baseline)*: Executes **1 to 2 LLM calls** per turn (1 skill retrieval + 1 response generation).
     - *System F (Full System)*: Executes **2 to 3 chat calls + 1 embedding call** per turn on the live path (skill-retrieval filtering/rewrite + counselor generation), plus **1 additional counselor call** when the Safety Supervisor returns REVISE. All gate agents — uncertainty, risk, routing, clarification, reassessment, supervision checks, longitudinal extraction — are **rule-based and make no LLM calls** (design audit: `docs/LIVE_EVIDENCE_STUDY.md`, Step 0).
     - *Overhead*: Against a true single-prompt baseline (1 chat call), the pipeline's extra model spend is the retrieval filter/rewrite calls and the occasional supervisor-revision call — roughly 2-3x the calls, not the larger multipliers stated in earlier drafts; the pre-registered head-to-head that would price this precisely has not yet been run.

4. **Statistical Sample Size & Low-Confidence Subgroups**:
   - The benchmark consists of $N=25$ cases. Within this dataset, **exactly 3 cases represent acute high-risk crisis presentations ($N=3$)**.
   - Consequently, high-risk detection metrics (**1.00 Safety Recall, 1.00 Escalation Accuracy**) and risk-related ablation deltas are derived from a very small sample size ($N < 10$) and must be treated as **LOW STATISTICAL CONFIDENCE**. Subgroup findings should be interpreted as directional architectural proofs rather than statistically powered clinical trials. In addition, per `docs/EVALUATOR_CRISIS_INJECTION.md`, the 1.00 recall/escalation values are artefacts of the evaluator's construction (a fixed crisis sentence is appended to HIGH cases before scoring) and are not measured safety performance at any sample size.

### Ethical Safeguards & Clinical Boundaries

> [!CAUTION]
> **ACADEMIC RESEARCH PROTOTYPE — NOT FOR CLINICAL USE**
>
> 1. **Non-Clinical Software**: This software is an academic research prototype developed for computer science evaluation. It is **not** a certified medical device, clinical diagnostic instrument, or substitute for licensed psychiatric care.
> 2. **No Diagnostic Authority**: The system does not diagnose mental disorders (DSM-5 / ICD-11), prescribe pharmaceuticals, or formulate autonomous clinical treatment plans.
> 3. **Emergency Crisis Resources**: If you or someone you know is in acute distress or experiencing thoughts of self-harm, please contact emergency support services immediately:
>    - **India**: Tele-MANAS (`14416` or `1800-891-4416`) | National Emergency (`112`)
>    - **United States & Canada**: Suicide & Crisis Lifeline (`988`) | Emergency (`911`)
>    - **United Kingdom**: NHS Mental Health Services (`111`) | Emergency (`999`)
>    - **International**: [findahelpline.com](https://findahelpline.com/)

---

## 14. Citation & Attribution

```bibtex
@misc{agentic_ai_mental_health_2026,
  author       = {Academic Research Team},
  title        = {Agentic AI for Mental Health: A Multi-Agent Framework for Uncertainty-Aware, Risk-Aware, and Longitudinal Psychological Support},
  year         = {2026},
  howpublished = {\url{https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health}}
}

@article{yang2026psychagent,
  author       = {Yang, Yutao and Li, Junsong and Pan, Qianjun and Zhou, Jie and Chen, Kai and Chen, Qin and Zhao, Jingyuan and Zhou, Ningning and Li, Xin and He, Liang},
  title        = {PsychAgent: An Experience-Driven Lifelong Learning Agent for Self-Evolving Psychological Counselor},
  journal      = {arXiv preprint arXiv:2604.00931 [cs.AI]},
  year         = {2026},
  url          = {https://arxiv.org/abs/2604.00931}
}
```

---


