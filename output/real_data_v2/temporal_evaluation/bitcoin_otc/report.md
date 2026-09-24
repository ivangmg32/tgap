# bitcoin_otc - TGAP real-data run

**Analysis mode:** `temporal_evaluation`  (leakage-safe - use these numbers)

> Bitcoin OTC web-of-trust (SNAP). 35,592 trust ratings among 5,881 traders over 1903.3 days. NOTE the timestamp is the FOURTH column; reading column 3 as time (as in the other files) silently yields a span of 0 days.

## What was used

| | in the source file | actually used | kept |
|---|---|---|---|
| actors | 5,881 | 120 | 2.04% |
| events | 35,592 | 414 | 1.16% |

- A node is **Bitcoin OTC traders**
- A link means **a trust rating given between two traders**
- 14 snapshots of 90 days
- Communities: **[45, 75]** via `temporal_train`
- Edge weights used: **False**, signs used: **False**

## No future information

- Actors chosen using: **0.0d .. 380.7d** (`temporal_train`)
- TGAP explained: **380.7d .. 1903.3d**
- Future information used for selection: **False**

## How much of the run is usable

**132 of 180 experiments are valid.** Excluded, by reason:

| reason | rows |
|---|---|
| `edge_count_infeasible` | 30 |
| `saturated` | 18 |

- edge-count invariant held in 25/30 settings
- bridge-trend status: {'saturated': 3, 'ok': 3}

## What each model responds to (delta 0.1, increase)

Impact = change in the model's answer, divided by the change we actually achieved. `n/a` = the experiment failed a validity check.

| model | Bridge Width | Centralization | Churn | Density |
|---|---|---|---|---|
| `persistence_bridge_width` | 0 | 0 | 0 | 0 |
| `persistence_centralization` | 0 | 0 | 0 | 0 |
| `persistence_density` | 0 | 0 | 0 | 0 |
| `slope_bridge_width` | -2.22 | 0 | 0 | 0 |
| `trend_bridge_width` | -7.98 | 0 | 0 | 0 |
| `trend_clustering` | +0.008 | -0.012 | 0 | +0.014 |

## Largest responses (valid rows only)

| model | concept | direction | delta | impact |
|---|---|---|---|---|
| `trend_bridge_width` | Bridge Width | decrease | 0.1 | +7.98 |
| `trend_bridge_width` | Bridge Width | increase | 0.1 | -7.98 |
| `trend_bridge_width` | Bridge Width | decrease | 0.25 | +7.46 |
| `trend_bridge_width` | Bridge Width | decrease | 0.5 | +6.87 |
| `slope_bridge_width` | Bridge Width | increase | 0.1 | -2.22 |

## Snapshots

| # | label | links | density | bridge width |
|---|---|---|---|---|
| 0 | 2011-11-24 | 61 | 0.0085 | 24 |
| 1 | 2012-02-22 | 60 | 0.0084 | 25 |
| 2 | 2012-05-22 | 62 | 0.0087 | 20 |
| 3 | 2012-08-20 | 43 | 0.0060 | 16 |
| 4 | 2012-11-18 | 20 | 0.0028 | 9 |
| 5 | 2013-02-16 | 15 | 0.0021 | 8 |
| 6 | 2013-05-17 | 12 | 0.0017 | 7 |
| 7 | 2013-08-15 | 7 | 0.0010 | 2 |
| 8 | 2013-11-13 | 4 | 0.0006 | 1 |
| 9 | 2014-02-11 | 3 | 0.0004 | 2 |
| 10 | 2014-05-12 | 1 | 0.0001 | 1 |
| 11 | 2014-08-10 | 5 | 0.0007 | 3 |
| 12 | 2014-11-08 | 2 | 0.0003 | 2 |
| 13 | 2015-05-07 | 1 | 0.0001 | 1 |

---

*Real data has no ground truth, so nothing here validates TGAP's correctness - it shows the pipeline handles real temporal structure. Every number is a model sensitivity to a controlled counterfactual perturbation, not a causal claim.*
