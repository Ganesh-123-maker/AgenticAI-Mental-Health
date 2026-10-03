# Presentation Deck: Agentic AI Mental Health

**Project Title**: Agentic AI Mental Health: A Coordinated Multi-Agent Architecture for Safe, Interpretable, and Longitudinal Psychological Support  
**Slide Count**: 20 Slides  
**Target Duration**: 20–25 Minutes + 10 Minutes Q&A  

---

## Slide 1: Title Slide
- **Title**: Agentic AI Mental Health
- **Subtitle**: Coordinated Multi-Agent Architecture for Safe, Longitudinal Psychological Support
- **Presenter**: Ganesh Barmavath
- **Academic Context**: Academic Research Project Defense
- **Key Visual**: Multi-Agent Hub and Spoke Architecture Diagram
- **Presenter Notes**: Welcome everyone. Today I am presenting our work on Agentic AI Mental Health, addressing critical safety, uncertainty, and longitudinal memory challenges in automated psychological support.

---

## Slide 2: The Challenge of AI in Mental Health
- **Core Problem**: Generative LLMs are increasingly accessed for mental health advice, yet suffer from catastrophic failure modes:
  - Epistemic Overconfidence (hallucinating psychological profiles when facts are missing)
  - Single-Point Safety Vulnerabilities (crisis signals bypassed by subtle language)
  - Memory Dissolution across repeated counseling sessions
- **Clinical Stakes**: In clinical support, an unflagged crisis or false reassurance can have severe, real-world consequences.
- **Presenter Notes**: Emphasize that standard chatbots are trained to be conversational, not clinically safe or epistemically humble.

---

## Slide 3: Research Questions & Objectives
- **Central Hypothesis**: Decoupling counseling dialogue into specialized micro-agents improves safety, diagnostic clarity, and alliance.
- **Key Research Questions**:
  1. Can epistemic uncertainty detection prevent premature therapeutic intervention?
  2. Does a two-tier safety supervisor eliminate crisis leakage?
  3. How effectively can longitudinal memory maintain goal coherence across multi-week sessions?
- **Presenter Notes**: Frame this as moving from monolithic prompting to auditable agentic decomposition.

---

## Slide 4: System Architecture Overview
- **11-Agent Coordinated Ecosystem**:
  - Memory & Context: `MemoryAgent`, `OutcomeAgent`, `MemoryUpdateAgent`
  - Assessment & Triage: `StateAgent`, `UncertaintyAgent`, `RiskAgent`
  - Control & Branching: `Orchestrator`, `ClarificationAgent`, `ReassessmentAgent`
  - Intervention & Supervision: `CounselingAgent`, `SafetySupervisor`
- **Visual Diagram**: Full-pipeline workflow flowchart (Memory → State → Triage → Orchestrator → Supervision).
- **Presenter Notes**: Walk through the separation of concerns. Emphasize that 10 of the 11 agents are pure rule/signal engines.

---

## Slide 5: The 5 Psychotherapy Modalities
- **Modality Support**:
  1. Cognitive Behavioral Therapy (**CBT**) — Cognitive restructuring & behavioral experiments
  2. Behavior Therapy (**BT**) — Functional analysis & reinforcement schedules
  3. Humanistic-Existential Therapy (**HET**) — Person-centered presence & meaning exploration
  4. Psychodynamic Therapy (**PDT**) — Defense mechanisms & core conflicts
  5. Postmodern Therapy (**PMT**) — Exception finding & solution-focused goals
- **Hierarchical Skill Library**: Modality-specific meta-skills and micro-skills.
- **Presenter Notes**: The system is not a generic advice-giver; it is grounded in established psychotherapeutic theory.

---

## Slide 6: Uncertainty Detection Engine
- **Why It Matters**: Clinicians do not guess; they clarify missing background.
- **Three Core Pillars of Uncertainty**:
  - *Clinical Gap Detection*: Identifying missing medical history or trauma timeline.
  - *Linguistic Ambiguity*: Flagging vague referents ("that thing", "I don't know what to do").
  - *Cross-Turn Contradictions*: Catching conflicting statements ("doing fine ... actually barely sleeping").
- **Presenter Notes**: Highlight that detecting uncertainty prevents false certainty.

---

## Slide 7: Clarification & Reassessment Loop
- **Targeted Inquiry**: `ClarificationAgent` generates 1–2 non-leading questions targeting prioritized gaps.
- **Reassessment**: When the client replies, `ReassessmentAgent` inspects the response:
  - Genuine context → Uncertainty resolved → Route transitions to `CLEAR`.
  - Evasive filler ("I don't know", "whatever") → Stays `UNCERTAIN`.
  - Crisis revealed → Upgraded to `HIGH-RISK`.
- **Termination Guarantee**: Bounded by turn caps to eliminate infinite loops.
- **Presenter Notes**: Contrast this with standard LLMs that hallucinate answers rather than asking for clarification.

---

## Slide 8: Two-Tier Safety Guardrails & Crisis Escalation
- **Tier 1 (Upstream Triage)**: `RiskAgent` scans client text for suicidal ideation, intent, and self-harm keywords.
- **Tier 2 (Downstream Review)**: `SafetySupervisor` reviews generated counselor drafts for false reassurance, dismissal, or crisis neglect.
- **Fail-Closed Principle**: If any review step fails, the system defaults to emergency escalation.
- **Verified Emergency Resources**: Directs clients immediately to Tele-MANAS (`14416`) and 988 Crisis Lifeline (`988`).
- **Presenter Notes**: Two independent barriers mean a hallucinating LLM draft is stopped before reaching the user.

---

## Slide 9: Negation Handling & False-Positive Prevention
- **The Problem**: Over-sensitive safety filters panic when a user says "I am NOT suicidal".
- **Our Solution**: A 6-word preceding negation window (`_NEGATION_WORDS`).
- **Empirical Behavior**: Statements like "I have never had thoughts of suicide or self-harm" maintain `severity="LOW"` and allow therapy to proceed.
- **Presenter Notes**: Show that safety is not just blocking everything; it is distinguishing actual crisis from negation.

---

## Slide 10: Longitudinal Memory & Cross-Session Evolution
- **Session Finalization Workflow**:
  - `OutcomeAgent` evaluates observable engagement markers and goal continuation.
  - `MemoryUpdateAgent` separates durable facts ("strives to manage presentation anxiety") from transient details ("traffic was bad today").
  - `PublicMemory` stores confirmed static traits, session recaps, and homework.
- **Session N+1 Startup**: History is seamlessly re-injected into prompt context.
- **Presenter Notes**: Show how the system remembers progress from session 1 to session 6 without infinite prompt bloat.

---

## Slide 11: Multi-User Isolation & Security Architecture
- **Tenant Protection**:
  - Token-based JWT authentication on all endpoints.
  - Relational SQLModel scoping: `where(course.user_id == current_user.id)`.
  - HTTP 403 Forbidden on unauthorized cross-tenant requests.
  - Completely separate global base profiles and visit contexts.
- **Presenter Notes**: Essential for production multi-user healthcare platforms.

---

## Slide 12: Full-Stack Web Platform & Trace Panel
- **Tech Stack**: FastAPI backend, SQLite database, React 18 frontend, Vite, Tailwind CSS.
- **Live Agent Trace Panel**:
  - Displays real-time pipeline route decision (`CLEAR` / `UNCERTAIN` / `HIGH-RISK`).
  - Renders execution status for all active agents.
  - Fully transparent and interpretable clinical reasoning audit trail.
- **Presenter Notes**: The trace panel demystifies AI decision-making for clinicians and researchers.

---

## Slide 13: Experimental Setup: Systems A through F
- **System A**: Baseline LLM (zero agent scaffolding).
- **System B**: Vanilla PsychAgent (hierarchical skills, no uncertainty/risk agents).
- **System C**: Static Multi-Agent (linear pipeline, no dynamic branching).
- **System D**: Dynamic Multi-Agent (Uncertainty + Risk + Clarification).
- **System E**: Dynamic Multi-Agent + Safety Supervisor.
- **System F**: Full System (Dynamic Multi-Agent + Safety Supervisor + Longitudinal Memory).
- **Presenter Notes**: Explain the progressive evolutionary design of our experimental systems.

---

## Slide 14: Quantitative Evaluation Results
- **Key Metrics Summary (Benchmark Evaluation)**:
  - Routing Accuracy: **0.00 (Sys A) → 0.76 (Sys F)**
  - Safety F1 & Recall: **0.00 (Sys A) → 1.00 (Sys F)**
  - Clarification Relevance: **0.00 (Sys A) → 0.68 (Sys F)**
  - Working Alliance Inventory (WAI): **5.00 → 10.00**
  - Session Rating Scale (SRS): **2.50 → 10.00**
- **Presenter Notes**: Highlight that our multi-agent architecture achieved 100% safety recall on crisis cases.

---

## Slide 15: Ablation Studies: Proving Architectural Necessity
- **What Happens When Components Are Removed?**
  - Without `UncertaintyAgent`: False certainty rate surges **4.5x (0.08 → 0.36)**.
  - Without `RiskAgent`: Safety recall drops **1.00 → 0.88** (crises missed).
  - Without `ClarificationAgent`: Handoff correctness collapses **0.94 → 0.62**.
  - Without `SafetySupervisor`: 100% of high-risk cases lack emergency escalation.
- **Presenter Notes**: Each agent proves its necessity through measurable performance degradation when removed.

---

## Slide 16: Failure Analysis & Error Taxonomy (609 Cases)
- **Top Failure Categories Analyzed**:
  1. Incorrect Routing (126 cases) — When dynamic routing was bypassed.
  2. Poor Clarification (104 cases) — Ablated clarification inquiries.
  3. Missed Uncertainty (99 cases) — Monolithic assumption of completeness.
  4. False Certainty (90 cases) — Masked by placeholder traits (fixed via `_is_placeholder`).
- **Presenter Notes**: Open, honest scientific discussion of system failure modes.

---

## Slide 17: Engineering Validation & Test Rigor
- **Verification Metrics**:
  - **Pytest Suite**: 31 of 31 test suites passing (100% pass rate in 25.34s).
  - **Live Runtime Scenario**: 11-phase end-to-end integration test (`test_demo_flow.py`) passing completely.
  - **Frontend Build**: Built with Vite in 4.54s with zero compilation warnings.
- **Presenter Notes**: Demonstrates high code quality, test coverage, and regression prevention.

---

## Slide 18: Live Demo Walkthrough
- **Demonstrated Scenarios**:
  1. Intake Assessment & Initial Clarification
  2. Multi-Session Transition & Memory Recall
  3. Linguistic Ambiguity Detection & Reassessment
  4. Contradiction Detection
  5. Crisis Detection & Fail-Closed Escalation with Helplines
  6. Negation False-Positive Prevention
- **Presenter Notes**: Reference our live execution traces recorded in the automated test logs.

---

## Slide 19: Clinical, Ethical & Safety Boundaries
- **Ethical Safeguards**:
  - Academic research prototype notice prominently displayed on UI.
  - Non-diagnostic disclaimer on every session.
  - Direct integration of verified crisis resources (Tele-MANAS `14416`, 988 Lifeline).
  - Zero autonomous clinical decision-making.
- **Presenter Notes**: Reinforce ethical AI principles in vulnerable domains like mental health.

---

## Slide 20: Conclusion & Future Outlook
- **Key Takeaways**:
  - Decomposing psychological support into 11 specialist agents solves epistemic overconfidence and crisis single-point failure.
  - Two-tier safety guardrails achieve 100% safety recall on critical benchmarks.
  - Longitudinal memory enables structured multi-session therapeutic continuity.
- **Future Directions**: Fine-tuned clinical foundation models, acoustic/visual multimodal inputs, and human-in-the-loop clinical IRB trials.
- **Thank You & Q&A**.
