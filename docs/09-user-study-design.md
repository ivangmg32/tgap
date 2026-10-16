# TGAP User Study — Design Protocol

> **Status: DESIGN ONLY. No participants have been recruited, no data
> collected, and no results exist.** This document specifies what would be
> run. Every results table below is deliberately empty. Reporting numbers
> here before collection would be fabrication.

---

## 1. Motivation and research questions

TGAP produces **concept-level** explanations ("widening the bridge between
these two communities by 10% moves the prediction by +9.35") rather than
**element-level** ones ("edge 42→17 has importance 0.31"). The scientific
claim is that concept-level explanations are more *usable* for reasoning
about temporal graphs. Usability is a claim about people, so it needs a
study with people.

| | Research question | Hypothesis |
|---|---|---|
| **RQ-U1** | Do concept-level explanations let analysts predict model behaviour more accurately than element-level ones? | H1: accuracy is higher with TGAP concepts than with an edge-importance list |
| **RQ-U2** | Are they faster to act on? | H2: time-to-answer is lower |
| **RQ-U3** | Do analysts trust them more, and is that trust *calibrated*? | H3: self-reported trust is higher **and** tracks actual accuracy |
| **RQ-U4** | Does the validity gating (`valid_for_analysis`) change what people conclude? | H4: shown validity flags, participants avoid unsupported conclusions more often |

RQ-U4 matters most and is the one nobody else can run: it tests whether
*honest reporting of failed perturbations* changes behaviour, which is the
distinctive methodological contribution of this implementation.

---

## 2. Participants

- **Target N = 36**, allowing 12 per condition in a 3-condition
  between-subjects design.
- **Population:** graduate students and researchers in network science,
  computational social science, or ML. Requirement: can read a node-link
  diagram and a time series; no requirement to know TGAP or XAI.
- **Recruitment:** university mailing lists and the CATALYST project
  network. No compensation beyond standard institutional practice.
- **Exclusion:** prior involvement in TGAP development.

> **Power.** N = 36 with 3 groups detects a large effect
> (Cohen's *f* ≈ 0.40) at α = 0.05 with power ≈ 0.72 — adequate for a first
> study, **underpowered for medium effects**. This is a limitation to state
> in the paper, not to hide. If recruitment allows N = 60, power for a
> medium effect (*f* = 0.25) reaches ≈ 0.80.

---

## 3. Design

**Between-subjects, three conditions**, each seeing the same model and the
same temporal graph:

| Condition | What the participant sees |
|---|---|
| **A — Baseline** | the temporal graph and the model's predictions only; no explanation |
| **B — Element-level** | plus a ranked edge-importance list (TGAP's occlusion attribution, `edgeAttribution`) |
| **C — Concept-level (TGAP)** | plus the concept impact table and the model × concept heatmap |

A within-subjects **sub-manipulation** applies to condition C only: half the
tasks show `valid_for_analysis` flags and exclusion reasons, half hide them
(order counterbalanced). This isolates RQ-U4 without needing a fourth group.

**Materials:** the two case studies already in the repository —
Decentraland (projected co-voting) and Email-Eu-core (real department
labels) — plus one synthetic world with **known ground truth**
(`makeNCommunityTemporalGraph`), which is the only task where objective
accuracy can be scored without ambiguity.

---

## 4. Tasks

Each participant completes **8 tasks**, presented in a counterbalanced
order (Latin square).

1. **Prediction (×3).** *"The analyst widens the bridge between departments
   4 and 14 by 25%. Will the model's output go up, down, or stay the same?
   By roughly how much?"*
   → scored against the actual measured result. **Primary accuracy measure.**
2. **Counterfactual ranking (×2).** *"Which of these three changes would
   move the prediction most?"* → scored against measured impacts.
3. **Diagnosis (×2).** *"The model's prediction dropped sharply between
   snapshot 6 and 7. Which structural change is most consistent with
   that?"* → scored against the known generative truth (synthetic task).
4. **Validity judgement (×1, condition C only).** *"Can you conclude from
   this output that bridge trend matters for this dataset?"*
   → correct answer is **no** when the Bridge Trend rows are `saturated`.
   Scores whether validity flags are read and acted upon.

---

## 5. Measures

| Measure | Type | Instrument |
|---|---|---|
| Accuracy | objective | proportion correct, tasks 1–3 |
| Magnitude error | objective | \|predicted − actual\| ÷ \|actual\| where a magnitude is given |
| Time to answer | objective | seconds per task, logged automatically |
| Confidence | subjective | 7-point Likert, per task |
| Trust | subjective | 4 items adapted from a standard automation-trust scale, 7-point |
| Understanding | subjective | 3 items, 7-point |
| Cognitive load | subjective | NASA-TLX raw, 6 items |
| Free response | qualitative | "what was confusing?" per condition |

**Trust calibration** (RQ-U3) is the correlation between per-task confidence
and per-task correctness within each participant. High trust with low
accuracy is *worse* than low trust — a point a raw trust score cannot make.

---

## 6. Procedure

```
  consent  →  demographics + background (2 min)
           →  tutorial for the assigned condition (8 min, fixed script)
           →  2 practice tasks with feedback
           →  8 scored tasks, no feedback, time logged
           →  post-questionnaire (trust, understanding, NASA-TLX)
           →  free-response debrief
```

Total ≈ 45 minutes. Delivered online; the tutorial is a recorded script so
it is identical for every participant in a condition.

---

## 7. Analysis plan (pre-registered before collection)

- **H1 (accuracy):** one-way ANOVA across conditions, then Holm-corrected
  pairwise comparisons. Report η² with 95% CI.
- **H2 (time):** same, on log-transformed time.
- **H3 (trust):** ANOVA on trust; **separately** report within-participant
  confidence–accuracy correlation, which is the calibration claim.
- **H4 (validity):** within-subjects comparison in condition C
  (flags shown vs hidden), paired test on the validity-judgement item and on
  unsupported-conclusion rate in free responses.
- **Qualitative:** two coders, inductive coding of free responses,
  Cohen's κ reported; disagreements resolved by discussion.

**Committed in advance:**
- All tests two-tailed, α = 0.05.
- No participant excluded after seeing their scores; exclusion criteria
  (incomplete session, failed attention check) are fixed beforehand.
- **Null and negative results will be reported.** If concept-level
  explanations do not beat element-level ones, that is the finding.
- No optional stopping: data collection ends at the planned N.

---

## 8. Ethics

- Institutional ethics approval required before recruitment.
- Informed consent; withdrawal at any time without penalty.
- No personal data beyond coarse demographics (field, years of experience).
- Responses pseudonymised at collection; only aggregates published.
- Task materials and analysis scripts released with the paper.

---

## 9. Threats to validity

| Threat | Mitigation |
|---|---|
| Experimenter allegiance (we built TGAP) | pre-registered analysis; a non-author runs the sessions; free responses coded blind to condition |
| Condition B is a straw man | the edge list is TGAP's own `edgeAttribution` — a real occlusion method, not a weakened one |
| Tutorial quality differs by condition | fixed recorded script, equal length, piloted |
| Real-data tasks have no ground truth | objective accuracy is scored **only** on the synthetic known-truth world and on measured model responses, never on "what is true about Decentraland" |
| Learning effects | between-subjects for the main manipulation; counterbalanced order within |
| Underpowered for medium effects | stated explicitly as a limitation; N = 60 preferred if recruitment allows |

---

## 10. Results

**Empty by design.** To be completed after collection.

| | Condition A | Condition B | Condition C |
|---|---|---|---|
| N | — | — | — |
| Accuracy (tasks 1–3) | — | — | — |
| Median time per task | — | — | — |
| Trust (mean, 7-point) | — | — | — |
| Confidence–accuracy correlation | — | — | — |

| RQ-U4 (condition C only) | Flags shown | Flags hidden |
|---|---|---|
| Correct validity judgement | — | — |
| Unsupported conclusions in free response | — | — |

---

## 11. What this study cannot show

- It cannot show TGAP's explanations are **correct** — correctness is
  established by the synthetic known-truth experiments, not by opinion.
- It cannot generalise beyond graph-literate researchers.
- It cannot separate "concepts help" from "*these five* concepts help";
  a different concept set might perform differently.
- With N = 36 it cannot detect small or medium effects reliably.
