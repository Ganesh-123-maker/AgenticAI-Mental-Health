# Academic Presentation: Speaker Notes & Oral Defense Guide

**Project**: Agentic AI for Mental Health  
**Artifact**: `docs/FINAL_PRESENTATION_SPEAKER_NOTES.md`  
**Purpose**: Natural spoken script for the 18-slide academic presentation. Designed to sound like a confident student explaining their project to an examination committee.

---

### Slide 1 — Title
**WHAT TO SAY:**  
"Good morning, respected committee members and professors. Today, I am presenting our capstone research project titled *Agentic AI for Mental Health: A Multi-Agent Framework for Uncertainty-Aware, Risk-Aware, and Longitudinal Psychological Support*. 

Conversational AI has advanced rapidly, but applying it to mental healthcare presents high-stakes challenges that off-the-shelf chatbots cannot safely handle. In this project, we built, validated, and evaluated an 11-agent architecture designed to make conversational uncertainty, crisis risk, and longitudinal memory explicit, safe, and inspectable."

**KEY POINT:**  
This project introduces a coordinated 11-agent architecture to solve critical reliability, safety, and continuity challenges in conversational mental-health support.

**TRANSITION:**  
"To understand why a multi-agent approach is necessary, let us look at the inherent challenges in mental health dialogues."

---

### Slide 2 — Problem
**WHAT TO SAY:**  
"In mental health counseling, users rarely present their difficulties in neat, complete paragraphs. A client might say, *'I can't take this anymore,'* or *'Things just keep falling apart.'* That single sentence could mean academic exhaustion, or it could be an active sign of acute suicidal crisis. 

When a standard, monolithic LLM receives that utterance, it immediately tries to generate a helpful response. But because it has no explicit step to ask *'Do I have enough information?'*, it suffers from what researchers call *epistemic overconfidence*—it makes unverified assumptions about what the user means, hallucinating background facts. Worse, if crisis cues are subtle or negated, a single prompt can easily overlook immediate risk. A single response generator conflates risk triage, uncertainty detection, therapy, and memory into one opaque step."

**KEY POINT:**  
Monolithic LLMs suffer from epistemic overconfidence and safety vulnerabilities because they conflate uncertainty detection, risk triage, and counseling into a single prompt.

**TRANSITION:**  
"Before designing our architecture, we examined existing literature and foundational systems in this space."

---

### Slide 3 — Existing System / Starting Point
**WHAT TO SAY:**  
"We began our work by studying **PsychAgent**, a state-of-the-art framework published by Zheng et al. in 2024. PsychAgent established a solid foundation for simulating therapy: it uses Jinja2 templates for prompt compilation, and it features a two-stage retrieval mechanism that fetches high-level meta-skills and fine-grained micro-skills across five therapy modalities like CBT, Behavioral Therapy, and Psychodynamic Therapy.

We deliberately did not rebuild therapeutic domain knowledge from scratch. We reused PsychAgent's validated skill taxonomies, embedding indices, and clinical prompt templates. However, PsychAgent was fundamentally designed as a single-turn, monolithic counselor simulator. It lacked dynamic triage, conversational clarification, and downstream safety guardrails."

**KEY POINT:**  
We leveraged PsychAgent's validated therapeutic skills and modalities while recognizing that its single-turn, monolithic pipeline lacked dynamic decision layers.

**TRANSITION:**  
"This brings us directly to the core research gap our project investigates."

---

### Slide 4 — Research Gap
**WHAT TO SAY:**  
"The research gap is architectural. In existing mental health conversational systems, the decision-making process is a black box. If an LLM gives advice, we cannot inspect whether it recognized missing information, whether it assessed self-harm, or whether it simply guessed.

We asked: What happens if we take those implicit decisions and turn them into explicit, decoupled, inspectable agent roles? Specifically, an upstream uncertainty assessment, an independent risk triage, an active clarification-reassessment loop, and a fail-closed safety supervisor. Can making these decisions modular and inspectable measurably improve reliability and clinical alliance?"

**KEY POINT:**  
The critical gap is the lack of explicit, inspectable decision layers for uncertainty, risk triage, clarification, and longitudinal memory.

**TRANSITION:**  
"This led us to formulate our central research question."

---

### Slide 5 — Research Question
**WHAT TO SAY:**  
"Our primary research question is: *Does explicit uncertainty assessment, risk assessment, clarification, reassessment, orchestration, safety supervision, and longitudinal memory coordination improve the reliability and quality of mental-health counseling compared with simpler configurations?*

Our hypothesis was that by giving specialized agents narrow, well-defined responsibilities, we would reduce false certainty, guarantee crisis escalation sensitivity, and produce higher therapeutic alliance scores without increasing hallucination."

**KEY POINT:**  
We hypothesized that a specialized multi-agent pipeline significantly reduces false certainty and safety failures compared to monolithic baselines.

**TRANSITION:**  
"Now, let us examine the 11-agent architecture we built to test this hypothesis."

---

### Slide 6 — Proposed Architecture
**WHAT TO SAY:**  
"Here is the architecture we implemented in the codebase. When user input arrives, it first passes through the `MemoryAgent`, which loads confirmed client traits from our longitudinal `PublicMemory`. The `StateAgent` then evaluates emotional tone and thematic focus.

Next, the input is processed in parallel by two critical triage agents: the `UncertaintyAgent` and the `RiskAgent`. Their assessments feed directly into the central `Orchestrator`. The Orchestrator follows strict priority rules: if there is high risk, it bypasses counseling immediately and routes to the emergency crisis protocol. If risk is low but uncertainty is high, it branches to the `ClarificationAgent` and `ReassessmentAgent`. Only when context is verified and clear does it invoke the `CounselingAgent`. Finally, before any response reaches the user, the downstream `SafetySupervisor` inspects the draft. After the session closes, the `OutcomeAgent` and `MemoryUpdateAgent` record durable updates back into memory."

**KEY POINT:**  
The architecture is a directional pipeline with dynamic branching, strict safety priority routing, and downstream supervisory review.

**TRANSITION:**  
"Let us quickly summarize the exact responsibility of each of the 11 agents."

---

### Slide 7 — 11 Agents
**WHAT TO SAY:**  
"To ensure modularity, each agent has exactly one core responsibility:
1. `MemoryAgent` retrieves historical context and confirmed traits.
2. `StateAgent` maps the client's current emotional state and presenting focus.
3. `UncertaintyAgent` detects missing intake dimensions, linguistic vagueness, and contradictions.
4. `RiskAgent` detects suicidal cues, intent, and self-harm with clause-level negation handling.
5. `Orchestrator` enforces priority routing across `HIGH-RISK`, `UNCERTAIN`, and `CLEAR`.
6. `ClarificationAgent` formulates 1 to 2 targeted questions to fill identified gaps.
7. `ReassessmentAgent` analyzes client answers to verify whether the state has become clear.
8. `CounselingAgent` drafts therapy interventions using modality-specific skills.
9. `SafetySupervisor` performs downstream fail-closed review against invalidation and false reassurance.
10. `OutcomeAgent` evaluates post-session client engagement signals.
11. `MemoryUpdateAgent` extracts durable facts and commits them to long-term memory."

**KEY POINT:**  
Decomposing the system into 11 single-responsibility agents ensures every decision is modular, traceable, and independently auditable.

**TRANSITION:**  
"Let's look more closely at how the system handles uncertainty and clarification."

---

### Slide 8 — Uncertainty + Clarification
**WHAT TO SAY:**  
"Here is an actual trace from our validation. Suppose a client says: *'I can't focus on anything anymore. It just keeps happening.'*
A standard LLM would immediately jump into study tips or breathing exercises. 

In our system, the `UncertaintyAgent` flags that the referent *'it'* is ambiguous, and crucial clinical dimensions—duration and triggers—are missing. The Orchestrator routes this to `UNCERTAIN`. The `ClarificationAgent` asks: *'Could you share what you notice happening when you lose focus, and how long this has been going on?'* 
When the user answers: *'During my afternoon classes for the last two weeks,'* the `ReassessmentAgent` processes the reply, confirms the gap is resolved, and updates the status to `CLEAR`. Only then does the `CounselingAgent` step in. Crucially, we enforce a strict turn cap of one clarification cycle so the system never traps the user in an interrogation loop."

**KEY POINT:**  
The clarification-reassessment loop actively resolves informational gaps before therapeutic intervention, bounded by strict turn limits.

**TRANSITION:**  
"Next, let us look at our two-tier safety architecture."

---

### Slide 9 — Risk + Safety
**WHAT TO SAY:**  
"Safety in mental health cannot rely on a single prompt or post-hoc filter. We implemented a two-tier defense-in-depth model.

Tier 1 is upstream: the `RiskAgent` scans incoming text for acute self-harm and crisis markers. Importantly, it features a 6-word negation parser. If a user says *'I am definitely not suicidal,'* it recognizes the negation and avoids a false emergency lockdown. 

Tier 2 is downstream: the `SafetySupervisor` reviews the counselor's generated response before it is displayed. It checks for clinical invalidation or dismissive clichés like *'Don't worry, everything will be fine.'* If risk was flagged, the supervisor enforces an immediate `ESCALATE` verdict, injecting verified emergency resources: Tele-MANAS `14416` in India and the 988 Lifeline. And if any component throws an unexpected runtime exception, the supervisor fails closed—it defaults to crisis escalation rather than leaking unreviewed text."

**KEY POINT:**  
Our two-tier safety architecture combines upstream negation-aware risk triage with a downstream fail-closed supervisor providing real-world crisis helplines.

**TRANSITION:**  
"Now let's examine how the system handles memory across multiple sessions."

---

### Slide 10 — Memory + RAG
**WHAT TO SAY:**  
"A key distinction in our architecture is separating procedural RAG from longitudinal memory. 

`SkillManager` is our RAG component—it stores domain knowledge about *how to counsel*, retrieving micro-skills based on semantic vector similarity. 

`PublicMemory`, on the other hand, stores *who the client is*. It tracks confirmed client traits, session summaries, and pending homework. In our multi-session validation, we tested factual conflict resolution: in Session 1, a client noted sleeping 7 hours. In Session 2, the client stated: *'Actually, I've only been getting 4 hours of sleep.'* The `MemoryUpdateAgent` recognized the factual contradiction, updated the record, and when Session 3 loaded, the context correctly reflected the updated 4-hour baseline."

**KEY POINT:**  
We strictly separate procedural RAG skill retrieval from longitudinal client memory, enabling seamless cross-session fact updates and contradiction resolution.

**TRANSITION:**  
"To rigorously evaluate this architecture, we conducted a systematic comparative benchmark."

---

### Slide 11 — Experimental Design
**WHAT TO SAY:**  
"We designed a controlled comparative benchmark comprising 25 standardized clinical cases spanning all five supported therapy modalities: Behavior Therapy, CBT, Humanistic-Existential, Psychodynamic, and Postmodern Therapy.

The cases were divided into an Ordinary Distress track—with controlled injections of ambiguity, missing information, and contradictions—and a Safety track with acute crises, passive ideation, and negated risk. 

We ran 12 distinct system configurations through all 25 cases, resulting in 300 full evaluation runs. Every single run was automatically scored across standard psychometrics—Working Alliance Inventory, Session Rating Scale, and PANAS—as well as safety F1, routing accuracy, and uncertainty recall."

**KEY POINT:**  
Our evaluation evaluated 12 system configurations across 25 multi-modal clinical benchmark cases, totaling 300 controlled experimental runs.

**TRANSITION:**  
"Let us examine the exact baselines and ablations we evaluated."

---

### Slide 12 — Baselines + Ablations
**WHAT TO SAY:**  
"To isolate the exact causal impact of each agent, we evaluated six progressive systems and six targeted ablations.

System A is the un-augmented monolithic baseline. System B adds skill retrieval and memory. System C introduces multi-agent triage. System D adds clarification and reassessment. System E adds the downstream Safety Supervisor, and System F is the full multi-agent framework with longitudinal updates.

Then, we took System F and systematically disabled one component at a time: removing uncertainty, removing risk, removing clarification, removing the supervisor, removing longitudinal memory, and removing dynamic routing. This allowed us to measure the exact failure modes caused by omitting each specific agent."

**KEY POINT:**  
Our 12 configurations rigorously isolate the individual contributions of uncertainty detection, risk triage, clarification, supervision, memory, and orchestration.

**TRANSITION:**  
"Let us now look at the audited experimental results."

---

### Slide 13 — Results
**WHAT TO SAY:**  
"These numbers are taken directly from our audited experimental results in `final_results.json`. 

In counseling quality, the Working Alliance Inventory increased from 5.00 in the monolithic baseline to a maximum of 10.00 in our full multi-agent system, and Session Rating Scale increased from 2.50 to 10.00. 

In safety, Systems A and B produce no multi-agent trail, so Safety F1 and Escalation Accuracy are not applicable (N/A) to them — not 0%. System F achieved 1.00 Safety F1 and 1.00 Escalation Accuracy. 

The ablations prove the necessity of each component: when we disabled the `UncertaintyAgent`, the False Certainty Rate surged from 0.12 to 0.36. When we disabled the `ClarificationAgent`, clarification handoff correctness fell from 0.92 to 0.72. And longitudinal memory consistency reached 1.00 in System F (not measured for non-longitudinal baselines, so N/A there)."

**KEY POINT:**  
The full multi-agent system achieved 10.00 WAI, 1.00 Safety F1, and reduced false certainty threefold compared to the ablated configuration.

**TRANSITION:**  
"Behind these quantitative metrics lies a comprehensive failure analysis."

---

### Slide 14 — Failure Analysis
**WHAT TO SAY:**  
"Across all 300 runs, we cataloged and analyzed 545 structured failure records. 

The top failure categories were Poor Clarification with 118 occurrences, False Certainty with 108, and Incorrect Routing with 81. Crucially, 44.4% of these failures occurred in the ablated configurations, directly validating why each agent is required. 

For example, in case `cbt_412_safety` with `ablation_no_risk`, the system missed subtle suicidal cues and drafted a standard cognitive restructuring exercise. It was only the downstream Safety Supervisor that prevented an unsafe response from reaching the client. This proved our defense-in-depth hypothesis."

**KEY POINT:**  
44.4% of all 545 recorded failures occurred in ablated configurations, empirically proving that removing any single agent introduces predictable clinical failures.

**TRANSITION:**  
"We have validated this entire pipeline not just offline, but through a live, full-stack web application."

---

### Slide 15 — Live Demonstration
**WHAT TO SAY:**  
"To prove that this architecture operates in a real environment, we developed a production-grade web application featuring a FastAPI backend and a Vite React frontend.

In our live demonstration, we walk through a complete clinical flow: creating a course under Cognitive Behavioral Therapy, starting Session 1, and introducing ambiguous statements. As the dialogue unfolds, the right-hand panel reveals the real-time **Agent Execution Trace**—displaying the exact state, uncertainty rating, and routing decisions. We show clarification, factual correction of sleep duration from 7 to 4 hours, closing the session, and observing Session 2 retrieve that corrected memory. Finally, we input a crisis statement and observe immediate interception and crisis helpline injection."

**KEY POINT:**  
Our live web application demonstrates real-time agent execution tracing, longitudinal memory continuity, and automated crisis intervention in the browser.

**TRANSITION:**  
"As an academic research project, it is essential to clearly state our limitations."

---

### Slide 16 — Limitations
**WHAT TO SAY:**  
"We must be scientifically honest about the boundaries of this research:
First, our evaluation was conducted on a benchmark of 25 structured clinical vignettes. Real patient speech contains greater informal and acoustic variance.
Second, quality metrics were scored using automated clinical judge rubrics; human client trials are necessary to observe true subjective variance.
Third, and most importantly: this is an academic research prototype. It does not possess clinical diagnostic authority, it cannot prescribe treatments, and it must never replace licensed mental health professionals. In local offline testing, counselor drafts use deterministic templates to ensure reproducible benchmarking."

**KEY POINT:**  
This system is an academic research prototype evaluated on structured benchmarks; it is not a medical device and does not diagnose or replace clinicians.

**TRANSITION:**  
"Despite these limitations, this project makes several clear academic contributions."

---

### Slide 17 — Contribution
**WHAT TO SAY:**  
"To summarize our contributions:
First, we implemented an explicit epistemic uncertainty layer that detects incomplete intake information, reducing false certainty from 0.36 to 0.12.
Second, we built a two-tier safety architecture combining upstream negation-aware risk triage with downstream fail-closed supervision, achieving perfect crisis escalation on our benchmark.
Third, we established a closed-loop clarification and reassessment cycle bounded by strict turn limits.
Fourth, we demonstrated longitudinal cross-session memory synthesis and conflict resolution.
And fifth, we validated the entire framework through a 12-configuration ablation study and a live, inspectable full-stack application."

**KEY POINT:**  
We contributed an explicit, inspectable multi-agent decision framework that empirically outperforms monolithic baselines in safety, alliance, and epistemic clarity.

**TRANSITION:**  
"Finally, let us look at the roadmap for future research."

---

### Slide 18 — Future Work
**WHAT TO SAY:**  
"Looking ahead, there are several promising research directions:
First, conducting IRB-approved clinical pilot studies under the direct supervision of licensed clinical psychologists.
Second, augmenting rule-based uncertainty with deep semantic token entropy and calibrated Bayesian neural network confidence scores.
Third, incorporating multimodal sensing, such as acoustic pitch and speech pause analysis, into the intake state assessment.
Fourth, expanding longitudinal memory to hierarchical vector stores for long-term engagements.
And fifth, adapting our crisis and clarification signal dictionaries into regional Indian languages to support Tele-MANAS integrations.

Thank you very much for your time and attention. I am now ready to take your questions."

**KEY POINT:**  
Future work focuses on supervised clinical trials, Bayesian uncertainty calibration, multimodal sensing, and multilingual expansion.

**TRANSITION:**  
"I look forward to discussing the technical details with the committee."
