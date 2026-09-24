# tgbl_wiki - TGAP real-data run

**Analysis mode:** `temporal_evaluation`  (leakage-safe - use these numbers)

> Wikipedia edit stream (TGB). 157,474 edits by 8,227 users on 1,000 pages over 31 days. Bipartite, so it is projected onto pages: two pages are linked when the same user edited both inside the window.

## What was used

| | in the source file | actually used | kept |
|---|---|---|---|
| actors | 1,000 | 100 | 10.0% |
| events | 157,474 | 13,267 | 8.42% |

- A node is **Wikipedia pages (item_id)**
- A link means **two pages co-edited by the same user in the window**
- 13 snapshots of 2 days
- Communities: **[25, 75]** via `temporal_train`
- Edge weights used: **False**, signs used: **False**

## No future information

- Actors chosen using: **0.0d .. 6.2d** (`temporal_train`)
- TGAP explained: **6.2d .. 31.0d**
- Future information used for selection: **False**

## How much of the run is usable

**144 of 180 experiments are valid.** Excluded, by reason:

| reason | rows |
|---|---|
| `edge_count_infeasible` | 24 |
| `saturated` | 12 |

- edge-count invariant held in 26/30 settings
- bridge-trend status: {'ok': 4, 'saturated': 2}

## What each model responds to (delta 0.1, increase)

Impact = change in the model's answer, divided by the change we actually achieved. `n/a` = the experiment failed a validity check.

| model | Bridge Trend | Bridge Width | Centralization | Churn | Density |
|---|---|---|---|---|---|
| `persistence_bridge_width` | 0 | +8.67 | 0 | 0 | 0 |
| `persistence_centralization` | 0 | 0 | 0 | 0 | 0 |
| `persistence_density` | 0 | 0 | 0 | 0 | 0 |
| `slope_bridge_width` | +1.00 | -1.19 | 0 | 0 | 0 |
| `trend_bridge_width` | +2.44 | +1.67 | 0 | 0 | 0 |
| `trend_clustering` | -0.002 | -0.050 | +0.010 | 0 | +0.002 |

## Largest responses (valid rows only)

| model | concept | direction | delta | impact |
|---|---|---|---|---|
| `persistence_bridge_width` | Bridge Width | decrease | 0.1 | +10.00 |
| `persistence_bridge_width` | Bridge Width | increase | 0.1 | +8.67 |
| `persistence_bridge_width` | Bridge Width | decrease | 0.25 | +4.33 |
| `trend_bridge_width` | Bridge Width | decrease | 0.1 | +4.23 |
| `persistence_bridge_width` | Bridge Width | increase | 0.25 | +4.06 |

## Snapshots

| # | label | links | density | bridge width |
|---|---|---|---|---|
| 0 | d6-d8 | 81 | 0.0164 | 16 |
| 1 | d8-d10 | 67 | 0.0135 | 29 |
| 2 | d10-d12 | 29 | 0.0059 | 13 |
| 3 | d12-d14 | 20 | 0.0040 | 8 |
| 4 | d14-d16 | 42 | 0.0085 | 21 |
| 5 | d16-d18 | 16 | 0.0032 | 8 |
| 6 | d18-d20 | 33 | 0.0067 | 9 |
| 7 | d20-d22 | 19 | 0.0038 | 9 |
| 8 | d22-d24 | 11 | 0.0022 | 3 |
| 9 | d24-d26 | 11 | 0.0022 | 5 |
| 10 | d26-d28 | 12 | 0.0024 | 5 |
| 11 | d28-d30 | 7 | 0.0014 | 4 |
| 12 | d30-d32 | 1 | 0.0002 | 0 |

---

*Real data has no ground truth, so nothing here validates TGAP's correctness - it shows the pipeline handles real temporal structure. Every number is a model sensitivity to a controlled counterfactual perturbation, not a causal claim.*
