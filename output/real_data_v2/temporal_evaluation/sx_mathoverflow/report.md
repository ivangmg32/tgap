# sx_mathoverflow - TGAP real-data run

**Analysis mode:** `temporal_evaluation`  (leakage-safe - use these numbers)

> MathOverflow question-answer-comment interactions (SNAP). 506,550 interactions among 24,818 users over 2350.3 days - the longest span in the project.

## What was used

| | in the source file | actually used | kept |
|---|---|---|---|
| actors | 24,818 | 120 | 0.48% |
| events | 506,550 | 10,685 | 2.11% |

- A node is **MathOverflow users**
- A link means **an answer/comment interaction between two users**
- 16 snapshots of 120 days
- Communities: **[57, 63]** via `temporal_train`
- Edge weights used: **False**, signs used: **False**

## No future information

- Actors chosen using: **0.0d .. 470.1d** (`temporal_train`)
- TGAP explained: **470.1d .. 2350.3d**
- Future information used for selection: **False**

## How much of the run is usable

**162 of 180 experiments are valid.** Excluded, by reason:

| reason | rows |
|---|---|
| `edge_count_infeasible` | 12 |
| `saturated` | 6 |

- edge-count invariant held in 28/30 settings
- bridge-trend status: {'ok': 5, 'saturated': 1}

## What each model responds to (delta 0.1, increase)

Impact = change in the model's answer, divided by the change we actually achieved. `n/a` = the experiment failed a validity check.

| model | Bridge Trend | Bridge Width | Centralization | Churn | Density |
|---|---|---|---|---|---|
| `persistence_bridge_width` | 0 | +29.52 | 0 | 0 | 0 |
| `persistence_centralization` | 0 | 0 | +0.058 | 0 | -0.011 |
| `persistence_density` | 0 | 0 | 0 | 0 | +0.011 |
| `slope_bridge_width` | +1.00 | -15.42 | 0 | 0 | 0 |
| `trend_bridge_width` | +1.97 | -9.35 | 0 | 0 | 0 |
| `trend_clustering` | +4e-04 | -0.081 | +0.008 | -0.225 | +3e-04 |

## Largest responses (valid rows only)

| model | concept | direction | delta | impact |
|---|---|---|---|---|
| `persistence_bridge_width` | Bridge Width | increase | 0.5 | +30.00 |
| `persistence_bridge_width` | Bridge Width | decrease | 0.5 | -30.00 |
| `persistence_bridge_width` | Bridge Width | decrease | 0.1 | -29.52 |
| `persistence_bridge_width` | Bridge Width | increase | 0.1 | +29.52 |
| `persistence_bridge_width` | Bridge Width | decrease | 0.25 | -28.06 |

## Snapshots

| # | label | links | density | bridge width |
|---|---|---|---|---|
| 0 | 2011-01-12 | 990 | 0.1387 | 386 |
| 1 | 2011-05-12 | 628 | 0.0880 | 256 |
| 2 | 2011-09-09 | 545 | 0.0763 | 207 |
| 3 | 2012-01-07 | 355 | 0.0497 | 130 |
| 4 | 2012-05-06 | 308 | 0.0431 | 132 |
| 5 | 2012-09-03 | 330 | 0.0462 | 119 |
| 6 | 2013-01-01 | 260 | 0.0364 | 97 |
| 7 | 2013-05-01 | 255 | 0.0357 | 99 |
| 8 | 2013-08-29 | 218 | 0.0305 | 78 |
| 9 | 2013-12-27 | 146 | 0.0204 | 56 |
| 10 | 2014-04-26 | 196 | 0.0275 | 76 |
| 11 | 2014-08-24 | 218 | 0.0305 | 77 |
| 12 | 2014-12-22 | 163 | 0.0228 | 76 |
| 13 | 2015-04-21 | 152 | 0.0213 | 64 |
| 14 | 2015-08-19 | 178 | 0.0249 | 66 |
| 15 | 2015-12-17 | 78 | 0.0109 | 29 |

---

*Real data has no ground truth, so nothing here validates TGAP's correctness - it shows the pipeline handles real temporal structure. Every number is a model sensitivity to a controlled counterfactual perturbation, not a causal claim.*
