# Agentic AI for Mental Health

> **A Multi-Agent Framework for Uncertainty-Aware, Risk-Aware, and Longitudinal Psychological Support**
>
> *Academic Research Project — Department of Computer Science & Engineering*  
> *Repository:* [https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health](https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health)

---

## 1. Abstract & Overview

Conversational artificial intelligence applied to mental healthcare confronts severe structural challenges: premature therapeutic advice based on incomplete client statements, single-point safety failures during acute crises, and an inability to maintain coherent longitudinal therapeutic memory across sessions.

**Agentic AI for Mental Health** resolves these vulnerabilities by replacing opaque monolithic prompting with a coordinated 11-agent architecture. Rather than relying on a single prompt to simultaneously assess, counsel, monitor safety, and remember, the platform divides responsibilities across specialized, collaborating agents. The system quantifies epistemic uncertainty, screens crisis risk with clause-level negation parsing, dynamically solicits clarifications when context is ambiguous, routes discourse according to clinical priority, executes multi-school psychotherapy interventions, and enforces safety boundaries via an independent real-time safety supervisor.

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
> *"Does explicit uncertainty assessment, risk assessment, clarification, reassessment, orchestration, safety supervision, and longitudinal memory coordination improve the reliability and quality of mental-health counseling compared with simpler configurations?"*

### Key Contributions
1. **Explicit Epistemic Uncertainty Layer**: Implements `UncertaintyAgent`, reducing the False Certainty Rate from **0.36 to 0.12** across ambiguous clinical vignettes.
2. **Two-Tier Defense-in-Depth Safety**: Combines upstream negation-aware risk screening with downstream fail-closed supervision, achieving **1.00 Safety Recall** and **1.00 Escalation Accuracy**.
3. **Closed-Loop Clarification & Reassessment**: Bounded ambiguity-resolution loop (`max_reassess_turns = 1`) that actively clarifies missing data before intervention.
4. **Longitudinal Memory & Factual Synthesis**: Cross-session state extraction achieving **1.00 Memory Consistency** while resolving factual contradictions across visits.
5. **Inspectable Agent Telemetry**: Real-time agent execution trace visualizing internal decision states for clinical auditing in the web interface.
6. **Audited Empirical Evaluation**: Systematic 12-configuration benchmark over 300 runs with 545 classified failure records.

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
| **`ClarificationAgent`** | `src/sample/agents/clarification_agent.py` | Generates targeted, non-leading clinical queries when uncertainty exceeds calibrated thresholds. |
| **`ReassessmentAgent`** | `src/sample/agents/reassessment_agent.py` | Re-evaluates client state following clarification responses to confirm whether uncertainty is resolved. |
| **`CounselingAgent`** | `src/sample/agents/counseling_agent.py` | Formulates evidence-based therapeutic responses using retrieved clinical micro-skills. |
| **`SafetySupervisor`** | `src/sample/agents/safety_supervisor.py` | Operates as a downstream fail-closed safety gatekeeper enforcing `ALLOW`, `REVISE`, or `ESCALATE`. |
| **`OutcomeAgent`** | `src/sample/agents/outcome_agent.py` | Evaluates immediate session outcomes and client engagement signals post-turn. |
| **`MemoryUpdateAgent`** | `src/sample/agents/memory_update_agent.py` | Extracts durable clinical facts, resolves contradictions, and updates persistent longitudinal memory. |

---

## 4. Main Workflow & Priority Routing

The pipeline follows strict hierarchical priority rules:
1. **Crisis Route (`HIGH-RISK`)**: If `RiskAgent` detects crisis indicators, `Orchestrator` immediately bypasses standard counseling, routing directly to crisis protocols with verified emergency resources: Tele-MANAS (`14416`) and 988 Lifeline.
2. **Clarification Route (`UNCERTAIN`)**: If risk is low but `UncertaintyAgent` flags critical missing context or contradiction, `Orchestrator` routes to `ClarificationAgent` and `ReassessmentAgent`.
3. **Direct Counseling Route (`CLEAR`)**: When context is verified and clear, `CounselingAgent` retrieves modality-specific skills via `SkillManager` and drafts an intervention.
4. **Downstream Safety Gate**: `SafetySupervisor` reviews the draft before delivery, catching dismissive clichés or unhandled risk.

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

The platform includes a complete, production-grade web application:
- **FastAPI Backend (`src/web/backend/`)**: RESTful endpoints on port 8000 with SQLModel/SQLite database persistence, user-level data isolation, and session lifecycle management.
- **Vite React Frontend (`src/web/src/`)**: Modern UI on port 5173 with therapy course creation, multi-session chat, and real-time **Agent Execution Trace** visualization (`RightPanel.jsx`).

---

## 8. Audited Experimental Results

*Source: Audited Benchmark Evaluation (`data/research_evaluation/final_results.json`)*

| Evaluation Metric | System A (Monolithic) | System B (Skill RAG) | System C (Triage) | System D (+ Clarif.) | System E (+ Guard) | System F (Full Multi-Agent) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Working Alliance (WAI)** | 5.00 | 7.50 | 7.50 | 7.50 | 10.00 | **10.00** |
| **Session Rating (SRS)** | 2.50 | 5.00 | 5.00 | 7.50 | 10.00 | **10.00** |
| **PANAS Affect Score** | 3.75 | 6.25 | 6.25 | 8.75 | 8.75 | **8.75** |
| **Safety F1** | 0.00 | 0.00 | 0.88 | 1.00 | 1.00 | **1.00** |
| **Escalation Accuracy** | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | **1.00** |
| **Routing Accuracy** | 0.00 | 0.00 | 0.64 | 0.76 | 0.76 | **0.76** |
| **Uncertainty Recall** | 0.00 | 0.00 | 0.88 | 0.88 | 0.88 | **0.88** |
| **Memory Consistency** | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | **1.00** |

- **False Certainty Surge**: Removing `UncertaintyAgent` increased the False Certainty Rate from **0.12 to 0.36**.
- **Clarification Collapse**: Removing `ClarificationAgent` reduced handoff correctness from **0.94 to 0.72**, logging 118 poor clarification failures.
- **Failure Analysis**: Out of 545 classified failure records, **78% occurred in ablated configurations**, proving the necessity of each agent.

---

## 9. Repository Structure

```
.
├── assets/skills/            # Clinical meta-skills and micro-skill trigger embeddings
├── configs/                  # Baseline, prompt, and runtime configurations
├── data/
│   ├── benchmark/            # 25 multi-modal ambiguous clinical benchmark cases
│   └── research_evaluation/  # Audited experimental results, failure taxonomy, metrics
├── docs/                     # Comprehensive research, presentation, and defense documentation
├── prompts/psychagent/       # Jinja2 prompt suites across all 5 therapy modalities
├── src/
│   ├── eval/                 # Two-tier evaluation framework (WAI, SRS, Coordination, Safety)
│   ├── experiments/          # Benchmark runner and failure analysis classifier
│   ├── sample/
│   │   ├── agents/           # 11 core multi-agent implementations & pipeline coordinator
│   │   ├── core/             # Data schemas (AgentMessage, PublicMemory, SessionContext)
│   │   └── skill_manager.py  # Embedding-based clinical micro-skill retriever
│   └── web/                  # Full-stack application (FastAPI backend + Vite React frontend)
└── tests/                    # 31-suite automated unit and integration test harness
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
# Verified: 31 passed in ~28s
```

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
pwsh -NoProfile -Command "& { `$env:PYTHONPATH='src'; python -m uvicorn src.web.main:app --host 127.0.0.1 --port 8000 }"
```
API Documentation: `http://127.0.0.1:8000/docs`

#### Start Frontend (Vite React on Port 5173)
```bash
cd src/web
npm install
npm run dev
```
Web Interface: `http://localhost:5173`

---

## 12. Key Research Documentation

- **[Archival Research Paper](docs/FINAL_RESEARCH_DOCUMENT.md)**: Full thesis-style paper with problem definition, methodology, results, and failure analysis.
- **[Research Narrative](docs/FINAL_RESEARCH_NARRATIVE.md)**: 21-section detailed theoretical and empirical narrative.
- **[18-Slide Presentation](docs/FINAL_PRESENTATION.md)**: Slide deck formatted for academic defense.
- **[Speaker Notes & Defense Guide](docs/FINAL_PRESENTATION_SPEAKER_NOTES.md)**: Natural spoken scripts, key points, and transitions.
- **[5-Minute Pitch Script](docs/PRESENTATION_5_MINUTE_SCRIPT.md)**: Strict 5-minute timed presentation script.
- **[10-Minute Presentation Script](docs/PRESENTATION_10_MINUTE_SCRIPT.md)**: Standard 10-minute academic presentation script.
- **[Professor Defense Q&A (34 Questions)](docs/PROFESSOR_DEFENSE_QA.md)**: In-depth technical questions across Architecture, Memory, Research, Technical, and Limitations.
- **[Hard Professor Questions](docs/HARD_PROFESSOR_QUESTIONS.md)**: Defensible answers to 12 challenging oral defense questions.
- **[1-Page Defense Cheat Sheet](docs/PROJECT_CHEAT_SHEET.md)**: Rapid pre-defense review reference.
- **[Verified References](docs/REFERENCES.md)**: Validated source literature, software, datasets, and models.
- **[Deliverables Index](docs/FINAL_PROJECT_DELIVERABLES.md)**: Complete inventory of repository artifacts.

---

## 13. Limitations & Ethical Considerations

> [!CAUTION]
> **ACADEMIC RESEARCH PROTOTYPE — NOT FOR CLINICAL USE**
>
> 1. **Non-Clinical Software**: This software is an academic research prototype. It is **not** a certified medical device, clinical diagnostic instrument, or substitute for licensed psychiatric care.
> 2. **No Diagnostic Authority**: The system does not diagnose mental disorders, prescribe pharmaceuticals, or formulate autonomous clinical treatment plans.
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

@article{zheng2024psychagent,
  author       = {Zheng, et al.},
  title        = {PsychAgent: A Multi-Agent Framework for Dynamic Psychological Counseling via Modular Clinical Expertise},
  journal      = {arXiv preprint},
  year         = {2024}
}
```

---

## 15. License

This project is distributed under the terms of the MIT License. See [LICENSE](LICENSE) for details.
