# tgbl_uci - TGAP real-data run

**Analysis mode:** `temporal_evaluation`  (leakage-safe - use these numbers)

> UCI online-community private messages (TGB). 59,835 messages among 1,899 students over 193.7 days. VERIFIED IDENTICAL to SNAP's CollegeMsg dataset (same event count, node count and timestamp offsets), so CollegeMsg is deliberately NOT included as a separate dataset.

## What was used

| | in the source file | actually used | kept |
|---|---|---|---|
| actors | 1,899 | 120 | 6.32% |
| events | 59,835 | 1,663 | 2.78% |

- A node is **students in an online community**
- A link means **a private message between two students in the window**
- 16 snapshots of 10 days
- Communities: **[55, 65]** via `temporal_train`
- Edge weights used: **False**, signs used: **False**

## No future information

- Actors chosen using: **0.0d .. 38.7d** (`temporal_train`)
- TGAP explained: **38.7d .. 193.7d**
- Future information used for selection: **False**

## How much of the run is usable

**138 of 180 experiments are valid.** Excluded, by reason:

| reason | rows |
|---|---|
| `edge_count_infeasible` | 24 |
| `saturated` | 18 |

- edge-count invariant held in 26/30 settings
- bridge-trend status: {'saturated': 3, 'ok': 3}

## What each model responds to (delta 0.1, increase)

Impact = change in the model's answer, divided by the change we actually achieved. `n/a` = the experiment failed a validity check.

| model | Bridge Width | Centralization | Churn | Density |
|---|---|---|---|---|
| `persistence_bridge_width` | 0 | 0 | 0 | 0 |
| `persistence_centralization` | 0 | 0 | 0 | 0 |
| `persistence_density` | 0 | 0 | 0 | 0 |
| `slope_bridge_width` | -2.46 | 0 | 0 | 0 |
| `trend_bridge_width` | -10.93 | 0 | 0 | 0 |
| `trend_clustering` | -0.002 | -0.009 | 0 | -0.014 |

## Largest responses (valid rows only)

| model | concept | direction | delta | impact |
|---|---|---|---|---|
| `trend_bridge_width` | Bridge Width | decrease | 0.1 | +10.93 |
| `trend_bridge_width` | Bridge Width | increase | 0.1 | -10.93 |
| `trend_bridge_width` | Bridge Width | decrease | 0.5 | +10.57 |
| `trend_bridge_width` | Bridge Width | decrease | 0.25 | +10.53 |
| `trend_bridge_width` | Bridge Width | increase | 0.25 | -10.53 |

## Snapshots

| # | label | links | density | bridge width |
|---|---|---|---|---|
| 0 | d38-48 | 222 | 0.0311 | 74 |
| 1 | d48-58 | 81 | 0.0113 | 27 |
| 2 | d58-68 | 14 | 0.0020 | 7 |
| 3 | d68-78 | 18 | 0.0025 | 4 |
| 4 | d78-88 | 17 | 0.0024 | 6 |
| 5 | d88-98 | 14 | 0.0020 | 6 |
| 6 | d98-108 | 24 | 0.0034 | 6 |
| 7 | d108-118 | 13 | 0.0018 | 8 |
| 8 | d118-128 | 8 | 0.0011 | 4 |
| 9 | d128-138 | 13 | 0.0018 | 7 |
| 10 | d138-148 | 6 | 0.0008 | 3 |
| 11 | d148-158 | 4 | 0.0006 | 1 |
| 12 | d158-168 | 2 | 0.0003 | 2 |
| 13 | d168-178 | 4 | 0.0006 | 1 |
| 14 | d178-188 | 2 | 0.0003 | 1 |
| 15 | d188-198 | 2 | 0.0003 | 2 |

---

*Real data has no ground truth, so nothing here validates TGAP's correctness - it shows the pipeline handles real temporal structure. Every number is a model sensitivity to a controlled counterfactual perturbation, not a causal claim.*
