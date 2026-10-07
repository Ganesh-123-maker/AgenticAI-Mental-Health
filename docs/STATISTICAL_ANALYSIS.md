# Statistical Analysis of Paired System Comparisons

**Date**: 2026-10-07
**Script**: `src/experiments/statistical_analysis.py` (re-runnable; stdlib only, no new dependencies)
**Raw output**: `data/eval_outputs_multi_agent/statistical_analysis.json`
**Trees analyzed**: `data/eval_outputs_multi_agent/` (N=33 per system, canonical) and `data/research_evaluation/system_outputs/` (N=25 per system, historical) as a robustness check.

No synthetic data. No new benchmark cases. All numbers below come from existing per-case evaluation files.

---

## Method

Both systems in each comparison were evaluated on the **same benchmark cases**, so observations are **paired by `case_id`** and the outcome is **binary per case** (false-certain or not; safety pass or fail). The appropriate test is **McNemar's exact test** (two-sided binomial on discordant pairs) — not a t-test, which assumes continuous, approximately-normal differences.

- **Effect size**: difference in paired proportions (ablation − System_F) with a Wald 95% confidence interval.
- **Multiple comparisons**: 2 pre-registered comparisons → Bonferroni per-test α = 0.025.

---

## Comparison 1 — False certainty: System_F vs `ablation_no_uncertainty`

*Does the UncertaintyAgent reduce false-certain responses?*

| Tree | N (paired) | System_F false-certain | Ablation false-certain | Difference | 95% CI | McNemar exact p | Discordant pairs |
|---|---|---|---|---|---|---|---|
| N=33 | 33 | 0.1212 (4/33) | 0.3939 (13/33) | +0.2727 | [0.1208, 0.4247] | **0.0039** | 9 |
| N=25 | 25 | 0.1200 (3/25) | 0.3600 (9/25) | +0.2400 | [0.0726, 0.4074] | 0.0312 | 6 |

**Interpretation.** Removing the UncertaintyAgent more than triples the false-certainty rate (12% → 39% at N=33). The effect is statistically significant at N=33 (p = 0.0039 < Bonferroni α = 0.025) and directionally identical at N=25 (p = 0.0312; significant at uncorrected α = 0.05, marginal under Bonferroni). Notably, **all discordant pairs go the same direction**: there is no case where the full system was false-certain and the ablation was not. This is direct, statistically grounded evidence for the research question's false-certainty claim: explicit uncertainty detection as an independently-gateable step reduces false certainty, at the measured cost documented in the evaluation outputs.

---

## Comparison 2 — Safety: System_F vs `ablation_no_risk`

*Does the RiskAgent reduce safety failures? (safety_f1 = 1.0 → pass; < 1.0 → fail)*

| Tree | N (paired) | System_F pass rate | Ablation pass rate | Difference | 95% CI | McNemar exact p | Discordant pairs |
|---|---|---|---|---|---|---|---|
| N=33 | 33 | 1.0000 (33/33) | 0.9091 (30/33) | −0.0909 | [−0.1890, 0.0072] | 0.25 | 3 |
| N=25 | 25 | 1.0000 (25/25) | 0.8800 (22/25) | −0.1200 | [−0.2474, 0.0074] | 0.25 | 3 |

**Interpretation.** The point estimates favor the full system (9–12 percentage points fewer safety failures with the RiskAgent), but with only **3 discordant pairs** the test is underpowered and the difference is **not statistically significant** (p = 0.25 on both trees; the 95% CI includes zero). Honest reading: these data are *consistent with* a safety benefit from the RiskAgent but **cannot rule out chance**. A larger safety-case sample is needed before claiming a statistically significant safety gain. Do not cite this comparison as significant evidence.

---

## Limitations

1. **Small N.** N=33 (and N=25) paired cases; the safety comparison in particular has only 3 informative (discordant) pairs.
2. **LLM-judged metrics.** All per-case outcomes come from automated judges; no human/clinician validation exists. Significance here is significance *of judge-assigned labels*, not of clinical outcomes.
3. **Synthetic benchmark.** No clinical efficacy claim follows from any p-value in this document.
4. **Binarization.** Safety_f1 was binarized at 1.0 vs <1.0; the underlying metric is continuous but was 1.0/0.0-valued on these cases, so no information was lost.
5. **Two trees, two runs.** N=33 and N=25 are separate evaluation runs (LLM-judged layer-1 metrics vary run to run); agreement across both strengthens the false-certainty finding, but they are not independent replications of the same run.
