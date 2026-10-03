# 10-Minute Academic Presentation & Defense Script

**Project**: Agentic AI for Mental Health  
**Target Duration**: 10 Minutes (Standard Academic Project Presentation)  
**Artifact**: `docs/PRESENTATION_10_MINUTE_SCRIPT.md`  

---

### Minute 0:00 – 1:00 | Motivation & The Problem
"Good morning, esteemed committee members. Today I am presenting our capstone research project: *Agentic AI for Mental Health: A Multi-Agent Framework for Uncertainty-Aware, Risk-Aware, and Longitudinal Psychological Support*.

Conversational artificial intelligence has shown tremendous promise, but deploying it in mental health counseling exposes severe architectural vulnerabilities. In real-world psychological dialogues, users present statements that are fragmented, ambiguous, and emotionally loaded. For example, a user disclosing *'I can't do this anymore'* might be describing academic fatigue, or they might be expressing immediate suicidal ideation.

Standard large language models operate as single-prompt monolithic generators. When faced with missing or ambiguous details, they suffer from **epistemic overconfidence**—they make unwarranted assumptions and hallucinate psychological profiles without verifying facts. Furthermore, they conflate crisis triage, clinical counseling, and safety supervision into one opaque generation step, creating dangerous single points of failure."

---

### Minute 1:00 – 2:00 | Foundational Starting Point & The Research Gap
"To address this challenge, we started from **PsychAgent**, a state-of-the-art framework published by Zheng et al. in 2024. PsychAgent introduced a hierarchical skill retrieval mechanism spanning five core psychotherapy modalities: Cognitive Behavioral Therapy (CBT), Behavior Therapy (BT), Humanistic-Existential Therapy (HET), Psychodynamic Therapy (PDT), and Postmodern Therapy (PMT).

We deliberately reused PsychAgent's domain assets: its skill hierarchies (`meta_skills.json`), micro-skill trigger embeddings (`micro_skills.pt`), and prompt templates. 

However, PsychAgent was fundamentally designed as a single-turn, monolithic counselor simulation. It lacked explicit uncertainty detection, had no closed-loop clarification mechanisms, relied on fragile single-point prompt safety, and maintained no memory across multiple sessions. 

Our research investigates: *Can we decompose this monolithic pipeline into specialized, inspectable agent roles—specifically separating epistemic uncertainty detection, risk triage, clarification, safety supervision, and longitudinal memory—to achieve measurable gains in safety and therapeutic alliance?*"

---

### Minute 2:00 – 3:30 | The Coordinated 11-Agent Architecture
"To test this hypothesis, we developed a coordinated 11-agent architecture organized as a directional pipeline with dynamic branching:

1. **`MemoryAgent`** begins by loading historical session recaps, pending homework, and confirmed client traits from our longitudinal store (`PublicMemory`).
2. **`StateAgent`** maps the client's current emotional state and presenting focus.
3. In parallel, **`UncertaintyAgent`** evaluates whether clinical intake information is missing or ambiguous, while **`RiskAgent`** screens for self-harm and crisis markers.
4. The central **`Orchestrator`** executes strict priority routing:
   - If risk is high, it immediately bypasses counseling and triggers emergency escalation.
   - If risk is low but uncertainty is high, it branches to the **`ClarificationAgent`** and **`ReassessmentAgent`**.
   - If context is clear and verified, it invokes the **`CounselingAgent`**.
5. The **`CounselingAgent`** retrieves modality-specific micro-skills via RAG and synthesizes a therapeutic response.
6. Downstream, an independent **`SafetySupervisor`** inspects the draft against clinical invalidation or unaddressed risk.
7. Finally, post-session, the **`OutcomeAgent`** evaluates client engagement markers, and the **`MemoryUpdateAgent`** commits durable facts back into memory."

---

### Minute 3:30 – 4:30 | Decoupling Memory from RAG & Epistemic Resolution
"A core architectural contribution is the clean separation of domain knowledge from client identity:
- **Procedural RAG (`SkillManager`)** retrieves *how to counsel*—indexing therapeutic techniques across the five supported modalities.
- **Longitudinal Memory (`PublicMemory`)** tracks *who the client is*—storing confirmed traits, session recaps, and homework records.

In our multi-session validation, we proved that this separation enables robust contradiction resolution: when a client in Session 2 corrected their reported sleep from 7 hours to 4 hours, `MemoryUpdateAgent` recognized the conflict, overrode the obsolete intake fact, and successfully loaded the corrected 4-hour baseline in Session 3.

Similarly, our clarification cycle is strictly bounded: `ClarificationAgent` asks targeted, non-leading questions, `ReassessmentAgent` verifies whether the ambiguity is resolved, and a turn cap of one cycle prevents infinite interrogation loops."

---

### Minute 4:30 – 5:30 | Two-Tier Safety Defense-in-Depth
"In mental health, safety cannot rely on prompt instructions alone. We implemented a two-tier defense-in-depth model:

- **Tier 1 (Upstream Triage)**: `RiskAgent` screens incoming text with a 6-word clause-level negation parser. For instance, when a client states *'I am definitely not suicidal,'* the system recognizes the negation, flags it as `NO_EVIDENCE`, and avoids false emergency lockdowns.
- **Tier 2 (Downstream Guardrail)**: `SafetySupervisor` reviews counselor drafts before the user sees them. It catches dismissive clichés like *'Don't worry, everything will be fine,'* issuing a `REVISE` verdict to enforce grounded coping statements.
- In any high-risk scenario, the supervisor enforces an immediate `ESCALATE` verdict, injecting operational crisis hotlines: Tele-MANAS `14416` in India and the 988 Lifeline in North America.
- Furthermore, `SafetySupervisor` is fail-closed: if an unexpected runtime exception occurs, it defaults to crisis escalation rather than releasing unvetted LLM output."

---

### Minute 5:30 – 7:00 | Experimental Design & Audited Results
"We evaluated our framework against a controlled benchmark of 25 standardized clinical cases across all five therapy modalities, evenly split into Ordinary Distress (ambiguity, missing data, contradictions) and Safety tracks (crisis, passive ideation, negated risk).

We tested 12 distinct configurations—including six progressive baselines from Monolithic System A to Full System F, and six ablation models removing uncertainty, risk, clarification, supervision, memory, and routing. In total, 300 automated evaluation runs were conducted.

The audited results in `final_results.json` provide conclusive empirical evidence:
1. **Therapeutic Working Alliance (WAI)** doubled from **5.00** in monolithic System A to **10.00** in our full system, while Session Rating Scale improved from **2.50 to 10.00**.
2. **Safety Recall & Escalation**: Full System F achieved **1.00 Safety F1** and **1.00 Escalation Accuracy**, whereas baselines A and B scored **0.00**.
3. **Epistemic Humility**: When the `UncertaintyAgent` was ablated, the False Certainty Rate surged from **0.12 to 0.36**, proving that un-augmented models falsely assume completeness.
4. **Clarification Value**: When the `ClarificationAgent` was ablated, handoff correctness collapsed from **0.94 to 0.72**.
5. **Memory Consistency**: Reached **1.00** in System F versus **0.00** in non-longitudinal systems."

---

### Minute 7:00 – 8:00 | Failure Taxonomy (545 Cases)
"Across all 300 experimental runs, we cataloged and analyzed **545 structured failure records** across 11 distinct categories:
- 118 cases of Poor Clarification (primarily in ablated configurations lacking clarification).
- 108 cases of False Certainty (when uncertainty detection was ablated).
- 81 cases of Incorrect Routing (when dynamic orchestration was ablated).
- 36 Supervisor Failures and 16 Unsafe Responses (when the safety supervisor was removed).
- 25 cases each of Memory Inconsistency and Longitudinal Inconsistency.

Crucially, **78% of all recorded failures occurred in ablated configurations**, empirically proving that each of our 11 agents addresses a real, demonstrable failure mode."

---

### Minute 8:00 – 9:00 | Full-Stack Web Implementation & Live Demo
"To prove that this architecture is production-ready, we developed a complete full-stack web application:
- A high-performance **FastAPI backend** running locally on port 8000 with SQLModel SQLite persistence and strict user isolation.
- A modern **Vite React frontend** on port 5173 featuring responsive multi-turn chat and course management.
- A real-time **Agent Execution Trace** panel in the user interface, giving researchers and clinicians immediate visibility into which agents fired, what uncertainty was detected, and what safety decisions were made.

In our live browser validation, we confirmed end-to-end functionality across all five psychotherapy modalities, multi-session longitudinal memory retrieval, and immediate crisis containment."

---

### Minute 9:00 – 10:00 | Limitations, Future Work & Conclusion
"In conclusion, we must be scientifically honest about our research boundaries:
- Our evaluation utilized 25 structured clinical vignettes; natural patient conversations exhibit greater informal variance.
- Metrics were evaluated using automated clinical judge matrices; human clinical trials are essential to measure true patient variance.
- This system is an academic research prototype. It does not diagnose illness, prescribe treatments, or replace licensed human therapists.

Future work will focus on:
1. Conducting IRB-approved clinical pilot studies under licensed psychological supervision.
2. Integrating deep semantic token entropy for Bayesian uncertainty calibration.
3. Incorporating multimodal speech prosody and acoustic sensing into state assessment.
4. Expanding crisis dictionaries into regional Indian languages for Tele-MANAS field deployment.

In summary, this project proves that making uncertainty, risk, clarification, and memory explicit and modular transforms opaque conversational LLMs into reliable, safe, and inspectable clinical support agents.

Thank you very much. I am now open to your questions."
