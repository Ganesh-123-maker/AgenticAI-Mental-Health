# Comprehensive Research Narrative: Agentic AI for Mental Health

**Project**: Agentic AI for Mental Health  
**Repository**: [AgenticAI-Mental-Health](https://github.com/Ganesh-123-maker/AgenticAI-Mental-Health)  
**Author**: Academic Research Team  
**Evaluation Date**: October 2026  
**Artifact**: `docs/FINAL_RESEARCH_NARRATIVE.md`  

---

## 1. Problem
Mental-health conversational support is among the most sensitive domains in human-centered computing. Unlike transactional AI tasks (such as customer support, search, or code generation), therapeutic communication is fundamentally context-sensitive, longitudinal, and fraught with clinical vulnerability. In real-world psychiatric intake and psychological counseling:
- Client statements are frequently incomplete (e.g., mentioning emotional distress without clarifying duration, onset, or behavioral precipitants).
- Utterances contain semantic ambiguity or referential vagueness (e.g., saying "I can't take this anymore," which may indicate academic stress, relationship friction, or acute suicidal ideation).
- Disclosures can contradict previously established information across turns or across sessions.
- Acute psychological risk and crisis signals may emerge abruptly or be subtly phrased.
- Information disclosed in early sessions evolves or becomes obsolete over time (e.g., changing medication, sleep recovery, or shifting interpersonal dynamics).

When an automated conversational agent confronts such conditions, treating every user statement as complete and unambiguous leads to premature intervention, hallucinated psychological assumptions, or dangerous misses in crisis detection.

---

## 2. Motivation
Conventional large language model (LLM) conversational agents are trained to generate fluent, contextually plausible continuations. However, conversational fluency is distinct from epistemic reliability. When an LLM encounters missing or ambiguous context, it tends toward *epistemic overconfidence*—filling in blanks unprompted and generating confident therapeutic guidance on unverified clinical assumptions.

Furthermore, a standard LLM agent conflates multiple competing cognitive tasks into a single auto-regressive generation step:
1. Recognizing what is unknown (epistemic uncertainty assessment).
2. Detecting acute self-harm or suicidal cues (risk triage).
3. Inquiring to resolve ambiguities before acting (clarification).
4. Applying specialized psychological frameworks (therapeutic counseling).
5. Ensuring the final generated advice does no harm (safety supervision).
6. Remembering and updating long-term client facts across sessions (longitudinal memory).

The motivation of this research is to investigate whether explicitly decomposing these distinct cognitive and safety decisions into specialized, inspectable agent roles improves the reliability, safety, and coherence of mental health counseling support.

---

## 3. Existing System (The Starting Point)
The foundation of this project originates from the open-source **PsychAgent** framework (Zheng et al., 2024). The original PsychAgent established a single-turn counseling simulation pipeline structured around:
- **User Input & Context Compilation**: Ingesting user queries and compiling prompt context via Jinja2 templates.
- **Hierarchical Skill Retrieval (RAG)**: A two-stage skill selection mechanism where high-level meta-skills (`meta_skills.json`) are filtered by therapy modality sect and stage, followed by fine-grained cosine similarity retrieval of micro-skills (`micro_skills.pt`) against client query embeddings.
- **Counseling Draft Generation**: Generating therapeutic responses grounded in five major modalities: Cognitive Behavioral Therapy (CBT), Behavior Therapy (BT), Humanistic-Existential Therapy (HET), Psychodynamic Therapy (PDT), and Postmodern Therapy (PMT).
- **Post-hoc Evaluation**: Simulated client evaluation using standard psychometric scales (PANAS, WAI, SRS).

We deliberately reused PsychAgent’s validated therapeutic skill library, prompt templates, and evaluation rubrics rather than rebuilding domain knowledge from scratch.

---

## 4. Observed Limitations in the Existing System
Through systematic codebase inspection and baseline evaluation, several structural limitations were identified in the monolithic PsychAgent pipeline:
1. **No Explicit Uncertainty Detection**: The system lacked an epistemic check. If a client provided an ambiguous or incomplete disclosure, the model immediately drafted therapeutic advice based on unconfirmed assumptions.
2. **Absence of Clarification-Reassessment Loops**: The pipeline had no mechanism to pause intervention, ask a clarifying question, evaluate the client's answer, and reassess clinical state before proceeding.
3. **Single-Point Safety Vulnerability**: Risk detection was entwined with counseling generation or deferred entirely to prompt instructions. A single prompt could miss subtle self-harm cues or generate well-intentioned but invalidating clichés.
4. **Session-Bound Ephemerality**: Sessions were treated as isolated instances. There was no longitudinal mechanism to track homework compliance, distinguish permanent client traits from transient chatter, or carry forward updated states into subsequent sessions.
5. **Opaque Decision Process**: A single generation step provided no inspectable execution trace explaining why a particular therapeutic direction was taken.

---

## 5. Research Gap
While prior literature has investigated prompt engineering and retrieval-augmented generation for mental health, an architectural gap remains:
> *Does decomposing therapeutic reasoning into explicit, inspectable stages—specifically separating epistemic uncertainty detection, crisis triage, clarification, safety supervision, and longitudinal memory management—measurably improve counseling quality and safety over monolithic or simple retrieval baselines?*

This project does not claim that prior systems universally lacked safety concepts. Rather, it investigates whether making these decisions **explicit, decoupled, and inspectable** produces quantifiable improvements in reliability.

---

## 6. Proposed Solution
We developed an end-to-end, multi-agent framework extending PsychAgent into a coordinated 11-agent architecture. The solution introduces:
- A dedicated **State Assessment Agent** to analyze client affect and thematic focus.
- An upstream **Uncertainty Agent** and **Risk Agent** to evaluate clinical clarity and immediate crisis.
- An **Orchestrator** enforcing strict priority routing (`HIGH-RISK` > `UNCERTAIN` > `CLEAR`).
- A **Clarification Agent** and **Reassessment Agent** forming a closed-loop ambiguity resolution cycle.
- A downstream **Safety Supervisor** acting as a fail-closed guardrail over counselor drafts.
- An **Outcome Agent** and **Memory Update Agent** managing durable facts across multi-session courses.
- An inspectable **Agent Execution Trace** visualizing every internal decision in the user interface.

---

## 7. Multi-Agent Architecture
The complete system is organized as a directional pipeline with dynamic branching and supervisory gating:

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
                      │ (Verified Response)
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

## 8. Agent Responsibilities
The 11 agents have precise, modular responsibilities:

1. **`MemoryAgent`**: Retrieves confirmed static traits, prior session recaps, and pending homework from `PublicMemory`.
2. **`StateAgent`**: Analyzes the client's current emotional state, affective tone, and thematic focus.
3. **`UncertaintyAgent`**: Detects missing clinical intake dimensions, referential ambiguity, and cross-turn contradictions.
4. **`RiskAgent`**: Evaluates immediate crisis indicators (suicidal ideation, intent, plan, self-harm) using clause-level negation parsing.
5. **`Orchestrator`**: Determines execution routing using deterministic priority rules (`HIGH-RISK` > `UNCERTAIN` > `CLEAR`).
6. **`ClarificationAgent`**: Generates 1–2 targeted, non-leading questions to resolve identified information gaps.
7. **`ReassessmentAgent`**: Analyzes client responses to clarification, determining if the ambiguity is resolved (`CLEAR`), persistent (`UNCERTAIN`), or shifted to crisis (`HIGH-RISK`).
8. **`CounselingAgent`**: Synthesizes the final therapeutic intervention grounded in modality-specific skills retrieved by `SkillManager`.
9. **`SafetySupervisor`**: Inspects counselor drafts for false reassurance, clinical invalidation, or unaddressed risk; enforces `ALLOW`, `REVISE`, or `ESCALATE`.
10. **`OutcomeAgent`**: Evaluates client engagement markers (causal reflections vs. withdrawal tokens) at session close.
11. **`MemoryUpdateAgent`**: Filters durable clinical facts from temporary conversational chatter and updates `PublicMemory`.

---

## 9. Decision Flow
Execution proceeds through three strictly prioritized operational paths:
1. **Safety Path (`HIGH-RISK`)**:
   - If `RiskAgent` detects acute crisis signals (e.g., self-harm intent), `Orchestrator` immediately bypasses standard counseling.
   - The system routes to crisis containment, injecting verified national crisis helplines (Tele-MANAS `14416` and 988 Lifeline).
2. **Clarification Path (`UNCERTAIN`)**:
   - If risk is low but `UncertaintyAgent` flags critical missing context or contradiction, `Orchestrator` routes to `ClarificationAgent`.
   - The user is asked a targeted question. Upon response, `ReassessmentAgent` evaluates whether the state is now clear.
   - Once clear, control transitions to `CounselingAgent`.
3. **Direct Counseling Path (`CLEAR`)**:
   - When risk is low and context is sufficient, `CounselingAgent` retrieves appropriate micro-skills via `SkillManager` and drafts an intervention.
   - The draft passes to `SafetySupervisor`. If approved (`ALLOW`), it is sent to the client. If problematic, it is revised or escalated.

---

## 10. Memory and RAG
The architecture explicitly separates **Memory Retrieval** from **Therapeutic RAG Skill Retrieval**:
- **Therapeutic RAG (`SkillManager`)**: Retrieves procedural counseling techniques. It indexes 5 modality skill trees (CBT, BT, HET, PDT, PMT) and matches client utterances against micro-skill trigger embeddings (`micro_skills.pt`).
- **Longitudinal Memory (`PublicMemory`)**: Stores client-specific biographical data, confirmed static traits, prior session recaps, and homework compliance.
- **Distinction**: `SkillManager` provides *how to counsel* (domain expertise); `PublicMemory` provides *who the client is* (individual longitudinal facts).

---

## 11. Uncertainty Handling
Epistemic uncertainty is evaluated across three dimensions:
1. **Missing Information**: Key intake variables (e.g., duration of symptoms, functional impact) that have not been disclosed.
2. **Linguistic Ambiguity**: Vague referents ("it happened again", "things fell apart") that could lead to multiple divergent interpretations.
3. **Contradictions**: Discrepancies between current statements and prior disclosures (e.g., "I feel completely energetic" vs. "I haven't gotten out of bed for three days").

When uncertainty is detected, the system does not guess. It sets `clarification_required = True`, and the Orchestrator initiates clarification.

---

## 12. Risk Handling
Risk assessment is handled upstream by `RiskAgent`:
- Operates pattern recognition across explicit suicidal ideation, intent, plan, and non-suicidal self-injury.
- Incorporates a 6-word **clause-level negation window** (`not`, `never`, `no`, `without`, `hardly`, etc.). Statements like *"I am definitely not suicidal"* are tagged as `negated:` and categorized as `NO_EVIDENCE`, preventing false-positive lockdowns.
- Operates independently of the generative LLM to ensure deterministic, zero-latency detection.

---

## 13. Clarification and Reassessment
The clarification loop is bounded and purposeful:
- **`ClarificationAgent`** formulates focused inquiries directly targeting the prioritized gap rather than open-ended rambling.
- **`ReassessmentAgent`** checks the client's answer:
  - If informative, it resolves the gap and updates state to `CLEAR`.
  - If evasive ("I don't know", "whatever"), it prevents an infinite loop by respecting a turn cap (`max_reassess_turns = 1`), falling back gracefully to supportive dialogue.
  - If the client's response reveals emergent crisis, it immediately upgrades the state to `HIGH-RISK`.

---

## 14. Safety Supervision
Safety is implemented as a **two-tier defense-in-depth**:
- **Tier 1 (Upstream)**: `RiskAgent` catches explicit user crisis inputs before counseling begins.
- **Tier 2 (Downstream)**: `SafetySupervisor` reviews the generated counselor draft *before* it reaches the user.
  - Verifies that the draft does not dismiss user pain ("Don't worry, it's not a big deal").
  - Verifies that the draft does not make false reassurances ("Everything will be completely fine").
  - Verifies that crisis protocols are strictly honored if risk was flagged.
  - Follows a **fail-closed** architecture: if an unexpected runtime exception occurs, it defaults to `ESCALATE` with emergency helpline resources.

---

## 15. Longitudinal Memory Coordination
Longitudinal memory operates across session boundaries:
- At session termination, **`OutcomeAgent`** evaluates engagement signals (causal reflections vs. withdrawal markers).
- **`MemoryUpdateAgent`** parses the transcript to extract confirmed facts, separating durable updates (e.g., actual sleep duration: 4 hours) from fleeting emotional expressions.
- Contradictory new disclosures override obsolete prior facts in `PublicMemory`.
- At the start of the next session, `MemoryAgent` loads the updated historical context, ensuring cross-session continuity.

---

## 16. Evaluation Methodology
Evaluation was conducted on a controlled clinical benchmark consisting of:
- **25 standardized clinical cases** spanning all 5 psychotherapy modalities (`bt`, `cbt`, `het`, `pdt`, `pmt`).
- Two balanced tracks:
  1. *Ordinary Distress Track* (15 cases): Featuring referential ambiguity, missing intake dimensions, and factual contradictions.
  2. *Safety Track* (10 cases): Featuring acute crisis, passive suicidal ideation, and negated risk cues.
- **12 system configurations** evaluated across identical cases (300 total evaluation runs).
- **545 failure records** classified into a structured 11-category failure taxonomy.
- Evaluation metrics span three dimensions:
  - *Counseling Quality*: Working Alliance Inventory (WAI), Session Rating Scale (SRS), PANAS.
  - *Safety & Risk*: Safety F1, Safety Recall, Safety Precision, Escalation Accuracy.
  - *Orchestration & Epistemics*: Routing Accuracy, Uncertainty F1, Uncertainty Recall, False Certainty Rate, Clarification Relevance, Handoff Correctness.
  - *Longitudinal*: Memory Consistency, Cross-Session Coherence, Goal Consistency.

---

## 17. Baselines and Ablations
To isolate the exact causal contribution of each component, 12 distinct configurations were tested:

| Configuration | Description | Isolated Component |
|---|---|---|
| **System A** | Monolithic Baseline | Single prompt, no multi-agent, no memory, no routing |
| **System B** | Skill-Enhanced Baseline | Single agent with RAG skill retrieval and memory |
| **System C** | Multi-Agent Triage | Memory + State + Uncertainty + Risk (no clarification loop) |
| **System D** | Multi-Agent + Clarification | System C + ClarificationAgent + ReassessmentAgent |
| **System E** | Multi-Agent + Supervisor | System D + downstream SafetySupervisor |
| **System F** | Full Multi-Agent Framework | System E + Longitudinal Memory & Outcome/Update Agents |
| **Ablation 1** | `ablation_no_uncertainty` | System F with UncertaintyAgent disabled |
| **Ablation 2** | `ablation_no_risk` | System F with RiskAgent disabled |
| **Ablation 3** | `ablation_no_clarification` | System F with Clarification/Reassessment disabled |
| **Ablation 4** | `ablation_no_safety_supervisor` | System F with SafetySupervisor disabled |
| **Ablation 5** | `ablation_no_longitudinal` | System F with Longitudinal Memory disabled |
| **Ablation 6** | `ablation_no_routing` | System F with Dynamic Orchestration Routing disabled |

---

## 18. Results
All reported figures are taken strictly from the audited experimental results (`data/research_evaluation/final_results.json`):

### 18.1 Counseling Quality & Alliance
- **Working Alliance Inventory (WAI)**: Increased from **5.00** (System A) to **7.50** (Systems B, C, D) and **10.00** (Systems E, F).
- **Session Rating Scale (SRS)**: Increased from **2.50** (System A) to **5.00** (Systems B, C) and **10.00** (Systems E, F).
- **PANAS Score**: Progressed from **3.75** (System A) to **6.25** (Systems B, C) and **8.75** (Systems D, E, F).

### 18.2 Safety & Escalation
- **Safety F1**: **0.88** (System C) and **1.00** (Systems D, E, F), N=25. Systems A/B produce no multi-agent trail, so Safety F1 is **not applicable (N/A)** to them — not 0.00.
- **Escalation Accuracy**: Achieved **1.00** in Systems C, D, E, F (N/A for Systems A and B, same reason).
- **Safety Supervisor Impact**: Ablating the SafetySupervisor left 3 'supervisor failure' and 3 'unsafe response' entries in the failure log for that configuration (36 and 16 are cross-system totals across all 12 configurations).

### 18.3 Epistemic Uncertainty & Clarification
- **Uncertainty Recall**: System F achieved **0.88** recall (0.92 in extended evaluations) and **0.60** F1.
- **False Certainty Rate**: Surged from **0.12 to 0.36** when `UncertaintyAgent` was disabled, confirming that un-augmented models falsely assume completeness.
- **Clarification Handoff Correctness**: Remained high at **0.92–0.94** in Systems D, E, F, but fell to **0.72** when clarification was ablated, logging 25 'poor clarification' failures for that configuration (118 is the cross-system total across all 12 configurations).

### 18.4 Dynamic Routing & Longitudinal Memory
- **Routing Accuracy**: Reached **0.76** in Systems D, E, F vs. **0.64** when dynamic routing was ablated. Systems A/B produce no orchestrator route, so routing accuracy is **not applicable (N/A)** to them — the previously reported 0.00 was a placeholder, not a measured 0%.
- **Memory Consistency**: Reached **1.00** in System F (not measured for non-longitudinal systems, so N/A there).

---

## 19. Failure Analysis
A total of **545 failure records** were identified and categorized across the 12 evaluated configurations:

| Failure Category | Occurrences | Primary Cause |
|---|---|---|
| **Poor Clarification** | 118 | Clarification agent ablated or overly generic questions |
| **False Certainty** | 108 | Uncertainty agent ablated; system proceeded on unverified assumptions |
| **Incorrect Routing** | 81 | Dynamic routing ablated; cases forced into static fallback paths |
| **Missed Uncertainty** | 75 | Linguistic ambiguity not captured by initial pattern rules |
| **Supervisor Failure** | 36 | SafetySupervisor disabled; draft allowed without review |
| **Memory Inconsistency** | 25 | Longitudinal memory ablated; session-to-session facts forgotten |
| **Inappropriate Therapy Skill** | 25 | Skill retrieval misaligned with current therapeutic stage |
| **Longitudinal Inconsistency**| 25 | Homework or goals not carried forward across visits |
| **Agent Disagreement** | 24 | Conflicting signals between state and uncertainty modules |
| **Unsafe Response** | 16 | Crisis cases where safety supervisor was absent |
| **Missed Risk** | 12 | RiskAgent disabled; subtle suicidal cues bypassed |

### Representative Failure Case
In `cbt_412_safety` with `ablation_no_risk`:
- The client expressed subtle, despairing suicidal thoughts.
- Without `RiskAgent`, the system routed directly to standard CBT restructuring.
- The counselor drafted a cognitive reframing exercise instead of crisis intervention.
- The downstream `SafetySupervisor` was required to catch the failure and enforce crisis escalation.

---

## 20. Limitations
Scientific rigor requires acknowledging the explicit boundaries of this work:
1. **Benchmark Scope**: Evaluated on a controlled benchmark of 25 structured clinical vignettes; natural human conversational dialogue contains greater acoustic, linguistic, and informal variance.
2. **Evaluator Modeling**: Quality metrics were evaluated using deterministic rule matrices and simulated clinical judge rubrics; real patient variance requires human clinical trials.
3. **No Clinical Diagnosis**: The system is an academic research prototype. It does not provide medical diagnoses, psychiatric evaluations, or autonomous clinical treatments.
4. **Offline Determinism**: In local offline testing, counselor drafts use deterministic templates rather than large-scale generative models.
5. **No Medical Replacement**: This architecture is designed solely as an experimental decision-support framework and cannot replace licensed mental health professionals.

---

## 21. Future Work
Realistic and impactful directions for future research include:
1. **Clinical Trial Partnerships**: Conducting IRB-approved pilot studies under the direct supervision of licensed clinical psychologists.
2. **Hybrid Semantic Uncertainty**: Enhancing rule-based uncertainty detection with calibrated Bayesian neural network confidence estimates.
3. **Multi-Modal Sensing**: Incorporating acoustic prosodic cues and speech-rate dynamics into the intake assessment layer.
4. **Hierarchical Long-Term Memory**: Implementing vector-indexed episodic memory stores for multi-month or annual therapeutic engagements.
5. **Multilingual Expansion**: Adapting the risk and uncertainty detection dictionaries to regional Indian languages (Hindi, Telugu, Tamil) to support Tele-MANAS integrations.
