# ivan_market - TGAP real-data run

**Analysis mode:** `temporal_evaluation`  (leakage-safe - use these numbers)

> Stock co-movement networks: two stocks are tied in a window when the correlation of their daily returns is at least 0.3 (positive). Communities are sectors.

## What was used

| | in the source file | actually used | kept |
|---|---|---|---|
| actors | 8 | 8 | 100.0% |
| events | 336 | 144 | 42.86% |

- A node is **stocks (tickers)**
- A link means **strong return correlation within one window**
- 12 snapshots of 6mo correlation windows, ends spread evenly over 5y
- Communities: **[4, 4]** via `sector_labels (Technology vs other)`
- Edge weights used: **False**, signs used: **False**

## No future information

- Actors chosen using: **none - tickers chosen by the user in advance** (`user_chosen_tickers`)
- TGAP explained: **2022-03-21 .. 2026-09-18**
- Future information used for selection: **False**

## How much of the run is usable

**120 of 180 experiments are valid.** Excluded, by reason:

| reason | rows |
|---|---|
| `edge_count_infeasible` | 60 |

- edge-count invariant held in 20/30 settings
- bridge-trend status: {'ok': 4, 'saturated': 2}

## What each model responds to (delta 0.1, increase)

Impact = change in the model's answer, divided by the change we actually achieved. `n/a` = the experiment failed a validity check.

| model | Bridge Width | Centralization | Churn | Density |
|---|---|---|---|---|
| `persistence_bridge_width` | 0 | 0 | 0 | 0 |
| `persistence_centralization` | 0 | 0 | 0 | 0 |
| `persistence_density` | 0 | 0 | 0 | 0 |
| `slope_bridge_width` | -0.839 | 0 | 0 | 0 |
| `trend_bridge_width` | +0.545 | 0 | 0 | 0 |
| `trend_clustering` | -0.102 | +0.074 | 0 | +0.015 |

## Largest responses (valid rows only)

| model | concept | direction | delta | impact |
|---|---|---|---|---|
| `persistence_centralization` | Centralization | decrease | 0.5 | -1.90 |
| `trend_clustering` | Centralization | decrease | 0.1 | -0.934 |
| `slope_bridge_width` | Bridge Width | decrease | 0.1 | +0.839 |
| `slope_bridge_width` | Bridge Width | increase | 0.1 | -0.839 |
| `trend_clustering` | Centralization | decrease | 0.5 | -0.619 |

## Snapshots

| # | label | links | density | bridge width |
|---|---|---|---|---|
| 0 | 2022-03-21 | 13 | 0.4643 | 6 |
| 1 | 2022-08-16 | 17 | 0.6071 | 9 |
| 2 | 2023-01-12 | 25 | 0.8929 | 15 |
| 3 | 2023-06-09 | 12 | 0.4286 | 5 |
| 4 | 2023-11-06 | 11 | 0.3929 | 4 |
| 5 | 2024-04-04 | 10 | 0.3571 | 4 |
| 6 | 2024-08-30 | 9 | 0.3214 | 4 |
| 7 | 2025-01-29 | 11 | 0.3929 | 4 |
| 8 | 2025-06-27 | 19 | 0.6786 | 10 |
| 9 | 2025-11-20 | 7 | 0.2500 | 5 |
| 10 | 2026-04-22 | 8 | 0.2857 | 4 |
| 11 | 2026-09-18 | 2 | 0.0714 | 2 |

---

*Real data has no ground truth, so nothing here validates TGAP's correctness - it shows the pipeline handles real temporal structure. Every number is a model sensitivity to a controlled counterfactual perturbation, not a causal claim.*

**More pictures:** which stocks and ties each model leans on, and in which window - see [insight.md](insight.md).
