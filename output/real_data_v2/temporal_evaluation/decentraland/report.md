# decentraland - TGAP real-data run

**Analysis mode:** `temporal_evaluation`  (leakage-safe - use these numbers)

> Decentraland DAO governance votes (frozen export, 2023-04-30). 53,533 votes by 4,133 voters on 1,816 proposals over 705 days. Bipartite, so it is projected onto voters: two voters are linked when they voted on the same proposal in the window.

## What was used

| | in the source file | actually used | kept |
|---|---|---|---|
| actors | 4,133 | 100 | 2.42% |
| events | 53,533 | 4,996 | 9.33% |

- A node is **voter wallet addresses (Member)**
- A link means **two voters who voted on the same proposal in the window**
- 19 snapshots of 1 calendar month
- Communities: **[50, 50]** via `temporal_train`
- Edge weights used: **False**, signs used: **False**

## No future information

- Actors chosen using: **2021-05-24 .. 2021-10-12** (`temporal_train`)
- TGAP explained: **2021-10-12 .. 2023-04-30**
- Future information used for selection: **False**

## How much of the run is usable

**144 of 180 experiments are valid.** Excluded, by reason:

| reason | rows |
|---|---|
| `saturated` | 18 |
| `edge_count_infeasible` | 18 |

- edge-count invariant held in 27/30 settings
- bridge-trend status: {'saturated': 3, 'ok': 3}

## What each model responds to (delta 0.1, increase)

Impact = change in the model's answer, divided by the change we actually achieved. `n/a` = the experiment failed a validity check.

| model | Bridge Width | Centralization | Churn | Density |
|---|---|---|---|---|
| `persistence_bridge_width` | +40.15 | 0 | 0 | 0 |
| `persistence_centralization` | 0 | 0 | 0 | -0.014 |
| `persistence_density` | 0 | 0 | 0 | +0.014 |
| `slope_bridge_width` | -14.40 | 0 | 0 | 0 |
| `trend_bridge_width` | +14.44 | 0 | 0 | 0 |
| `trend_clustering` | -0.196 | +1e-03 | -0.272 | -0.158 |

## Largest responses (valid rows only)

| model | concept | direction | delta | impact |
|---|---|---|---|---|
| `persistence_bridge_width` | Bridge Width | increase | 0.1 | +40.15 |
| `persistence_bridge_width` | Bridge Width | decrease | 0.1 | -40.15 |
| `persistence_bridge_width` | Bridge Width | increase | 0.5 | +36.04 |
| `persistence_bridge_width` | Bridge Width | decrease | 0.5 | -36.04 |
| `persistence_bridge_width` | Bridge Width | increase | 0.25 | +35.99 |

## Snapshots

| # | label | links | density | bridge width |
|---|---|---|---|---|
| 0 | 2021-10 | 521 | 0.1053 | 234 |
| 1 | 2021-11 | 840 | 0.1697 | 387 |
| 2 | 2021-12 | 1007 | 0.2034 | 493 |
| 3 | 2022-01 | 310 | 0.0626 | 112 |
| 4 | 2022-02 | 394 | 0.0796 | 197 |
| 5 | 2022-03 | 349 | 0.0705 | 180 |
| 6 | 2022-04 | 173 | 0.0349 | 80 |
| 7 | 2022-05 | 377 | 0.0762 | 180 |
| 8 | 2022-06 | 272 | 0.0549 | 124 |
| 9 | 2022-07 | 204 | 0.0412 | 99 |
| 10 | 2022-08 | 385 | 0.0778 | 173 |
| 11 | 2022-09 | 306 | 0.0618 | 155 |
| 12 | 2022-10 | 256 | 0.0517 | 131 |
| 13 | 2022-11 | 299 | 0.0604 | 148 |
| 14 | 2022-12 | 251 | 0.0507 | 123 |
| 15 | 2023-01 | 116 | 0.0234 | 48 |
| 16 | 2023-02 | 121 | 0.0244 | 64 |
| 17 | 2023-03 | 107 | 0.0216 | 47 |
| 18 | 2023-04 | 68 | 0.0137 | 36 |

---

*Real data has no ground truth, so nothing here validates TGAP's correctness - it shows the pipeline handles real temporal structure. Every number is a model sensitivity to a controlled counterfactual perturbation, not a causal claim.*
