# 5-Minute Timed Academic Defense Script

**Project**: Agentic AI for Mental Health  
**Target Duration**: 5 Minutes (Strict academic / pitch presentation)  
**Artifact**: `docs/PRESENTATION_5_MINUTE_SCRIPT.md`  

---

### 0:00 – 0:30 | Problem
"Respected committee members, conversational AI in mental health is fraught with severe epistemic and safety risks. In psychological intake, client statements are frequently incomplete, ambiguous, or contradictory. A user saying *'I can't take this anymore'* could be experiencing academic stress or acute suicidal ideation. Monolithic LLMs exhibit epistemic overconfidence: they make unverified assumptions, hallucinate missing details, and conflate crisis triage, clinical counseling, and safety into a single opaque generation step."

---

### 0:30 – 1:00 | Existing Limitations
"We studied the foundational PsychAgent framework by Zheng et al. (2024). While PsychAgent pioneered hierarchical skill retrieval across five therapy modalities—CBT, Behavioral, Humanistic, Psychodynamic, and Postmodern—it was architected as a single-turn, monolithic counselor simulator. It lacked explicit uncertainty detection, had no closed-loop clarification mechanisms, relied on single-point prompt safety, and possessed no longitudinal memory across multiple sessions."

---

### 1:00 – 2:00 | Architecture
"To solve this, we designed a coordinated **11-agent architecture**. 
When user input enters:
1. `MemoryAgent` loads confirmed traits from our longitudinal store.
2. `StateAgent` maps emotional valence and presenting themes.
3. In parallel, `UncertaintyAgent` detects missing intake fields and ambiguities, while `RiskAgent` scans for crisis signals with clause-level negation handling.
4. The central `Orchestrator` enforces strict priority routing:
   - High risk routes immediately to crisis protocols.
   - High uncertainty routes to `ClarificationAgent` and `ReassessmentAgent` to resolve gaps before intervention.
   - Verified, clear context routes to `CounselingAgent`, which retrieves modality skills via RAG.
5. Downstream, an independent `SafetySupervisor` acts as a fail-closed guardrail.
6. Post-session, `OutcomeAgent` and `MemoryUpdateAgent` record durable updates back into memory."

---

### 2:00 – 2:45 | Core Innovation
"Our core innovation is decoupling implicit conversational reasoning into explicit, inspectable decision layers:
- **Closed-Loop Epistemic Resolution**: The system actively asks targeted questions to fill clinical blanks before giving advice, capped at one turn to prevent interrogation loops.
- **Two-Tier Defense-in-Depth**: Upstream risk triage combined with downstream safety supervision enforcing real crisis escalation (Tele-MANAS `14416` and 988 Lifeline).
- **Longitudinal Conflict Resolution**: Factual corrections—such as updating sleep hours from 7 to 4—are recognized, overriding obsolete memory across session boundaries."

---

### 2:45 – 3:30 | Experiment
"We evaluated our framework against a controlled benchmark of 25 standardized clinical cases spanning all five therapy modalities, split into Ordinary Distress and Safety tracks. We tested 12 distinct configurations—including six progressive baselines from Monolithic System A to Full Multi-Agent System F, and six ablation models systematically disabling uncertainty, risk, clarification, supervision, memory, and routing. In total, 300 automated evaluation runs were conducted, and 545 failure records were classified."

---

### 3:30 – 4:15 | Audited Results
"Our audited findings confirm our hypothesis:
- **Therapeutic Alliance**: Working Alliance Inventory (WAI) doubled from **5.00** in monolithic System A to **10.00** in our full system, while Session Rating Scale improved from **2.50 to 10.00**.
- **Safety**: Safety F1 and Escalation Accuracy reached **1.00** in System F versus **0.00** in un-augmented baselines.
- **Epistemic Humility**: When the `UncertaintyAgent` was ablated, the False Certainty Rate surged from **0.12 to 0.36**.
- **Clarification**: When the `ClarificationAgent` was ablated, handoff correctness collapsed from **0.94 to 0.72**, with 118 poor clarification failures logged.
- **Failure Taxonomy**: 78% of all 545 recorded failures occurred in ablated configurations, proving the causal necessity of each agent."

---

### 4:15 – 4:40 | Live Demo
"We validated this entire architecture in a full-stack web application featuring a FastAPI backend and Vite React frontend. In our live browser validation, we proved multi-turn dialogue, real-time **Agent Execution Trace** visualization, multi-session continuity, and instant crisis escalation with validated helplines across all five psychotherapy schools."

---

### 4:40 – 5:00 | Limitations & Future Work
"In conclusion, we emphasize that this is an academic research prototype. It does not diagnose mental illness or replace clinical professionals. Future work will focus on IRB-supervised clinical trials, Bayesian uncertainty calibration, and multilingual Indian language adaptation. 

Thank you, and I look forward to your questions."
