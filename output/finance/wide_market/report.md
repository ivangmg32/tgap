# wide_market - TGAP real-data run

**Analysis mode:** `temporal_evaluation`  (leakage-safe - use these numbers)

> Stock co-movement networks: two stocks are tied in a window when the correlation of their daily returns is at least 0.5 (positive). Communities are sectors.

## What was used

| | in the source file | actually used | kept |
|---|---|---|---|
| actors | 30 | 30 | 100.0% |
| events | 5,220 | 742 | 14.21% |

- A node is **stocks (tickers)**
- A link means **strong return correlation within one window**
- 12 snapshots of 6mo correlation windows, ends spread evenly over 5y
- Communities: **[5, 5, 5, 5, 5, 5]** via `sector_labels`
- Edge weights used: **False**, signs used: **False**

## No future information

- Actors chosen using: **none - tickers chosen by the user in advance** (`user_chosen_tickers`)
- TGAP explained: **2022-04-18 .. 2026-09-18**
- Future information used for selection: **False**

## How much of the run is usable

**126 of 180 experiments are valid.** Excluded, by reason:

| reason | rows |
|---|---|
| `edge_count_infeasible` | 54 |

- edge-count invariant held in 21/30 settings
- bridge-trend status: {'saturated': 3, 'ok': 3}

## What each model responds to (delta 0.1, increase)

Impact = change in the model's answer, divided by the change we actually achieved. `n/a` = the experiment failed a validity check.

| model | Bridge Width | Centralization | Churn | Density |
|---|---|---|---|---|
| `persistence_bridge_width` | 0 | 0 | 0 | 0 |
| `persistence_centralization` | 0 | +0.126 | 0 | -0.055 |
| `persistence_density` | 0 | 0 | 0 | +0.051 |
| `slope_bridge_width` | -3.87 | 0 | 0 | 0 |
| `trend_bridge_width` | +6.66 | 0 | 0 | 0 |
| `trend_clustering` | -0.244 | +0.001 | -0.087 | -0.171 |

## Largest responses (valid rows only)

| model | concept | direction | delta | impact |
|---|---|---|---|---|
| `trend_bridge_width` | Bridge Width | increase | 0.1 | +6.66 |
| `slope_bridge_width` | Bridge Width | decrease | 0.1 | +4.57 |
| `slope_bridge_width` | Bridge Width | increase | 0.25 | -4.44 |
| `slope_bridge_width` | Bridge Width | increase | 0.1 | -3.87 |
| `trend_bridge_width` | Bridge Width | increase | 0.25 | +2.95 |

## Snapshots

| # | label | links | density | bridge width |
|---|---|---|---|---|
| 0 | 2022-04-18 | 48 | 0.1103 | 15 |
| 1 | 2022-09-09 | 147 | 0.3379 | 99 |
| 2 | 2023-02-03 | 156 | 0.3586 | 107 |
| 3 | 2023-06-30 | 47 | 0.1080 | 14 |
| 4 | 2023-11-22 | 32 | 0.0736 | 6 |
| 5 | 2024-04-19 | 26 | 0.0598 | 6 |
| 6 | 2024-09-12 | 30 | 0.0690 | 7 |
| 7 | 2025-02-07 | 32 | 0.0736 | 9 |
| 8 | 2025-07-07 | 158 | 0.3632 | 116 |
| 9 | 2025-11-26 | 24 | 0.0552 | 0 |
| 10 | 2026-04-24 | 19 | 0.0437 | 1 |
| 11 | 2026-09-18 | 23 | 0.0529 | 2 |

---

*Real data has no ground truth, so nothing here validates TGAP's correctness - it shows the pipeline handles real temporal structure. Every number is a model sensitivity to a controlled counterfactual perturbation, not a causal claim.*
