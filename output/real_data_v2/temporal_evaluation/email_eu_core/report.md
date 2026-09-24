# email_eu_core - TGAP real-data run

**Analysis mode:** `temporal_evaluation`  (leakage-safe - use these numbers)

> European research institution email network (SNAP). 332,334 emails between 1,005 members over 803.9 days. Ships ground-truth department labels.

## What was used

| | in the source file | actually used | kept |
|---|---|---|---|
| actors | 986 | 201 | 20.39% |
| events | 332,334 | 12,599 | 3.79% |

- A node is **institution members (anonymised ids)**
- A link means **an email sent between two members in the window**
- 12 snapshots of 40 days
- Communities: **[109, 92]** via `ground_truth_labels`
- Edge weights used: **False**, signs used: **False**

## No future information

- Actors chosen using: **0.0d .. 160.8d** (`ground_truth_labels`)
- TGAP explained: **160.8d .. 803.9d**
- Future information used for selection: **False**

## How much of the run is usable

**138 of 180 experiments are valid.** Excluded, by reason:

| reason | rows |
|---|---|
| `edge_count_infeasible` | 30 |
| `saturated` | 12 |

- edge-count invariant held in 25/30 settings
- bridge-trend status: {'ok': 4, 'saturated': 2}

## What each model responds to (delta 0.1, increase)

Impact = change in the model's answer, divided by the change we actually achieved. `n/a` = the experiment failed a validity check.

| model | Bridge Trend | Bridge Width | Centralization | Churn | Density |
|---|---|---|---|---|---|
| `persistence_bridge_width` | 0 | +9.94 | 0 | 0 | 0 |
| `persistence_centralization` | 0 | 0 | +0.007 | 0 | -1e-03 |
| `persistence_density` | 0 | 0 | 0 | 0 | +1e-03 |
| `slope_bridge_width` | +1.00 | -5.42 | 0 | 0 | 0 |
| `trend_bridge_width` | +1.13 | +45.93 | 0 | 0 | 0 |
| `trend_clustering` | +4e-04 | -0.147 | -0.007 | -0.147 | -0.040 |

## Largest responses (valid rows only)

| model | concept | direction | delta | impact |
|---|---|---|---|---|
| `trend_bridge_width` | Bridge Width | decrease | 0.1 | -45.93 |
| `trend_bridge_width` | Bridge Width | increase | 0.1 | +45.93 |
| `trend_bridge_width` | Bridge Width | decrease | 0.25 | -44.70 |
| `trend_bridge_width` | Bridge Width | decrease | 0.5 | -43.79 |
| `persistence_bridge_width` | Bridge Width | decrease | 0.25 | -11.98 |

## Snapshots

| # | label | links | density | bridge width |
|---|---|---|---|---|
| 0 | d160-200 | 165 | 0.0082 | 82 |
| 1 | d200-240 | 193 | 0.0096 | 103 |
| 2 | d240-280 | 203 | 0.0101 | 106 |
| 3 | d280-320 | 150 | 0.0075 | 75 |
| 4 | d320-360 | 186 | 0.0093 | 99 |
| 5 | d360-400 | 195 | 0.0097 | 97 |
| 6 | d400-440 | 156 | 0.0078 | 78 |
| 7 | d440-480 | 269 | 0.0134 | 139 |
| 8 | d480-520 | 245 | 0.0122 | 128 |
| 9 | d520-560 | 55 | 0.0027 | 31 |
| 10 | d760-800 | 41 | 0.0020 | 25 |
| 11 | d800-840 | 20 | 0.0010 | 11 |

---

*Real data has no ground truth, so nothing here validates TGAP's correctness - it shows the pipeline handles real temporal structure. Every number is a model sensitivity to a controlled counterfactual perturbation, not a causal claim.*
