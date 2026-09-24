# bitcoin_alpha - TGAP real-data run

**Analysis mode:** `temporal_evaluation`  (leakage-safe - use these numbers)

> Bitcoin Alpha web-of-trust (SNAP). 24,186 trust ratings among 3,783 traders over 1901.0 days. Same structure as bitcoin-otc on a different platform, so the pair tests whether results transfer between two similar ecosystems.

## What was used

| | in the source file | actually used | kept |
|---|---|---|---|
| actors | 3,783 | 120 | 3.17% |
| events | 24,186 | 415 | 1.72% |

- A node is **Bitcoin Alpha traders**
- A link means **a trust rating given between two traders**
- 13 snapshots of 90 days
- Communities: **[39, 81]** via `temporal_train`
- Edge weights used: **False**, signs used: **False**

## No future information

- Actors chosen using: **0.0d .. 380.2d** (`temporal_train`)
- TGAP explained: **380.2d .. 1901.0d**
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
| `persistence_bridge_width` | 0 | 0 | 0 | 0 | 0 |
| `persistence_centralization` | 0 | 0 | 0 | 0 | 0 |
| `persistence_density` | 0 | 0 | 0 | 0 | 0 |
| `slope_bridge_width` | +1.00 | -2.58 | 0 | 0 | 0 |
| `trend_bridge_width` | +3.53 | -8.21 | 0 | 0 | 0 |
| `trend_clustering` | +0.007 | -0.003 | -0.013 | 0 | +0.015 |

## Largest responses (valid rows only)

| model | concept | direction | delta | impact |
|---|---|---|---|---|
| `trend_bridge_width` | Bridge Width | decrease | 0.1 | +8.21 |
| `trend_bridge_width` | Bridge Width | increase | 0.1 | -8.21 |
| `trend_bridge_width` | Bridge Width | decrease | 0.25 | +6.83 |
| `trend_bridge_width` | Bridge Width | decrease | 0.5 | +6.67 |
| `trend_bridge_width` | Bridge Trend | increase | 0.1 | +3.53 |

## Snapshots

| # | label | links | density | bridge width |
|---|---|---|---|---|
| 0 | 2011-11-23 | 61 | 0.0085 | 24 |
| 1 | 2012-02-21 | 60 | 0.0084 | 25 |
| 2 | 2012-05-21 | 62 | 0.0087 | 22 |
| 3 | 2012-08-19 | 43 | 0.0060 | 19 |
| 4 | 2012-11-17 | 20 | 0.0028 | 10 |
| 5 | 2013-02-15 | 17 | 0.0024 | 9 |
| 6 | 2013-05-16 | 12 | 0.0017 | 7 |
| 7 | 2013-08-14 | 7 | 0.0010 | 3 |
| 8 | 2013-11-12 | 4 | 0.0006 | 1 |
| 9 | 2014-02-10 | 3 | 0.0004 | 2 |
| 10 | 2014-05-11 | 1 | 0.0001 | 1 |
| 11 | 2014-08-09 | 5 | 0.0007 | 3 |
| 12 | 2014-11-07 | 2 | 0.0003 | 2 |

---

*Real data has no ground truth, so nothing here validates TGAP's correctness - it shows the pipeline handles real temporal structure. Every number is a model sensitivity to a controlled counterfactual perturbation, not a causal claim.*
