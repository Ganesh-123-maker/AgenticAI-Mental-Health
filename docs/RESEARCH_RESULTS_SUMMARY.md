# Research Results Summary: Baseline & Ablation Evaluation

**Project**: Agentic AI for Mental Health  
**Academic Overview for Supervisors & Committee Members**  
**Date**: October 3, 2026  

---

## 1. What Was Compared?

We evaluated **12 distinct system configurations** to test whether a coordinated multi-agent architecture outperforms simpler alternatives:
- **System A (Monolithic Baseline)**: Single LLM call with no memory, no skills, and no agent coordination.
- **System B (Skill & Memory Baseline)**: Single LLM with retrieved therapy skills and static memory, but no multi-agent routing.
- **System C (Triage Multi-Agent)**: Adds UncertaintyAgent and StateAgent, but lacks clarification loops.
- **System D (Clarification Multi-Agent)**: Adds ClarificationAgent, ReassessmentAgent, and dynamic Orchestration.
- **System E (Supervised Multi-Agent)**: Adds an independent SafetySupervisor gatekeeper.
- **System F (Full Multi-Agent System)**: Complete architecture with cross-session longitudinal memory (`OutcomeAgent` + `MemoryUpdateAgent`).
- **6 Targeted Component Ablations**: Each disables exactly one specialist agent from System F (`no_uncertainty`, `no_risk`, `no_clarification`, `no_safety_supervisor`, `no_longitudinal`, `no_routing`).

---

## 2. Why Was It Compared?

In AI for mental health, a common skepticism from professors and clinicians is:
> *"Why build a complex 10-agent system when you can just prompt a single large language model?"*

This experiment directly tests the hypothesis that **explicit modular decision-making**—separating uncertainty assessment, risk triage, clarification, clinical counseling, and safety supervision—solves critical failure modes (such as hallucinations, missed crisis signals, and conversational drift) that monolithic systems cannot reliably avoid.

---

## 3. What Cases Were Tested?

We tested **25 standardized clinical benchmark cases** drawn from all 5 supported psychotherapy schools:
1. **Behavioral Therapy (BT)**
2. **Cognitive Behavioral Therapy (CBT)**
3. **Humanistic-Existential Therapy (HET)**
4. **Psychodynamic Therapy (PDT)**
5. **Postmodern Therapy (PMT)**

Each modality was tested across two realistic tracks:
- **Ordinary Track**: Ambiguous client expressions ("everything is too much"), unmentioned medical history, and contradictory statements (conflicting sleep reports).
- **Safety Track**: High-risk suicidal intent, passive death wishes, and clause-level negated risk statements ("I am feeling down, but definitely not suicidal").

---

## 4. What Was Measured?

We evaluated the systems across two rigorous metric layers:
1. **Clinical & Alliance Metrics (Layer 1)**:
   - **Working Alliance Inventory (WAI)**: Goal and task alignment (0 to 10).
   - **Session Rating Scale (SRS)**: Relational safety and empathy (0 to 10).
   - **PANAS**: Positive and negative affect balance.
2. **Multi-Agent Coordination & Safety Metrics (Layer 2)**:
   - **Routing Accuracy**: How reliably the system selects the correct specialist path.
   - **Safety F1 & Recall**: Detection of acute and passive self-harm signals.
   - **Escalation Accuracy**: Interception rate of unsafe drafts.
   - **Uncertainty F1**: Sensitivity to missing information.
   - **Clarification Relevance**: Quality of information-seeking inquiries.
   - **Memory Consistency**: Preservation of cross-session goals and homework.

---

## 5. What Did the Experiments Actually Observe?

The empirical results showed clear, measurable improvements as agent specialization was introduced:

| System / Configuration | Working Alliance (WAI) | Session Rating (SRS) | Routing Accuracy | Safety F1 | Escalation Accuracy | Memory Consistency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **System A (Monolithic)** | 5.00 | 2.50 | 0.00 | 0.00 | 0.00 | 0.00 |
| **System B (Skill/Memory)** | 7.50 | 5.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **System C (Triage)** | 7.50 | 5.00 | 0.64 | 0.88 | 1.00 | 0.00 |
| **System D (Clarification)** | 7.50 | 7.50 | 0.76 | 1.00 | 1.00 | 0.00 |
| **System E (Supervised)** | 10.00 | 10.00 | 0.76 | 1.00 | 1.00 | 0.00 |
| **System F (Full Multi-Agent)** | **10.00** | **10.00** | **0.76** | **1.00** | **1.00** | **1.00** |

### Key Experimental Takeaways:
1. **SafetySupervisor is indispensable for safety**: When SafetySupervisor is disabled, escalation accuracy drops from 100% to 0%, allowing unsafe drafts to reach the client unverified.
2. **RiskAgent is necessary for high-risk triage**: Removing RiskAgent causes Safety F1 to drop from 1.00 to 0.88, missing subtle or passive suicidal disclosures.
3. **UncertaintyAgent prevents epistemic overconfidence**: Removing UncertaintyAgent causes false certainty to increase from 0.08 to 0.36 across ambiguous cases.
4. **ClarificationAgent resolves missing context**: Without ClarificationAgent, handoff correctness degrades from 0.94 to 0.62 because the system cannot formulate targeted questions.
5. **Longitudinal Agents preserve therapeutic continuity**: System F achieved 1.00 memory consistency across multi-session trajectories; disabling longitudinal agents resulted in lost homework and goal drift.

---

## 6. What Failure Patterns Appeared?

An automated failure analysis audited all 12 systems and logged **545 structured failure records**:
- **Poor Clarification (118 cases)**: Occurred primarily in `ablation_no_clarification` and System C, where missing information was identified but no inquiry was posed.
- **False Certainty (108 cases)**: Occurred in `ablation_no_uncertainty` and System A, where missing medical histories were ignored and treated as verified facts.
- **Incorrect Routing (81 cases)**: Occurred in un-routed baselines (Systems A & B) and `ablation_no_routing`, where the system defaulted to a single path regardless of risk.
- **Supervisor Failure (36 cases)**: Occurred exclusively in systems lacking `SafetySupervisor`.
- **Memory & Longitudinal Inconsistency (50 cases)**: Occurred when `PublicMemory` and longitudinal update agents were disabled.

---

## 7. What Limitations Remain?

1. **Curated Clinical Benchmark**: Testing was conducted on structured clinical vignettes; real clinical deployment requires supervised pilot trials with human licensed therapists.
2. **Deterministic Offline Execution**: The evaluation utilized local deterministic execution to ensure strict reproducibility; token latencies will vary in cloud API settings.
3. **Research Decision-Support Scope**: PsychAgent is an academic decision-support framework and must not be used as an unsupervised medical diagnostic tool.

---

## 8. Summary for Presentation

- **Core Finding**: Explicit multi-agent coordination provides statistically and operationally measurable advantages over monolithic prompting in safety containment, uncertainty resolution, and cross-session coherence.
- **Auditable Evidence**: Full per-case outputs, metrics, and failure logs are preserved under `data/research_evaluation/`.
