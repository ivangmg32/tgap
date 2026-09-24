# tgbl_enron - TGAP real-data run

**Analysis mode:** `temporal_evaluation`  (leakage-safe - use these numbers)

> Enron corporate email network (TGB). 125,235 emails among ~184 employees over 1316.4 days. Note the header is u,i,ts,label,idx - NOT the tgbl-wiki schema, which is why each adapter validates its own.

## What was used

| | in the source file | actually used | kept |
|---|---|---|---|
| actors | 184 | 25 | 13.59% |
| events | 125,235 | 18,510 | 14.78% |

- A node is **Enron employees (anonymised ids)**
- A link means **an email between two employees in the window**
- 18 snapshots of 60 days
- Communities: **[8, 17]** via `temporal_train`
- Edge weights used: **False**, signs used: **False**

## No future information

- Actors chosen using: **0.0d .. 263.3d** (`temporal_train`)
- TGAP explained: **263.3d .. 1316.4d**
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
| `persistence_bridge_width` | +9.12 | 0 | 0 | 0 |
| `persistence_centralization` | 0 | 0 | 0 | 0 |
| `persistence_density` | 0 | 0 | 0 | 0 |
| `slope_bridge_width` | -0.179 | 0 | 0 | 0 |
| `trend_bridge_width` | +10.97 | 0 | 0 | 0 |
| `trend_clustering` | -0.564 | +0.068 | 0 | -0.163 |

## Largest responses (valid rows only)

| model | concept | direction | delta | impact |
|---|---|---|---|---|
| `trend_bridge_width` | Bridge Width | increase | 0.1 | +10.97 |
| `persistence_bridge_width` | Bridge Width | decrease | 0.1 | +10.86 |
| `persistence_bridge_width` | Bridge Width | increase | 0.1 | +9.12 |
| `trend_bridge_width` | Bridge Width | increase | 0.25 | +8.61 |
| `trend_bridge_width` | Bridge Width | increase | 0.5 | +7.44 |

## Snapshots

| # | label | links | density | bridge width |
|---|---|---|---|---|
| 0 | d263-323 | 38 | 0.1267 | 9 |
| 1 | d323-383 | 35 | 0.1167 | 9 |
| 2 | d383-443 | 52 | 0.1733 | 19 |
| 3 | d443-503 | 45 | 0.1500 | 15 |
| 4 | d503-563 | 38 | 0.1267 | 9 |
| 5 | d563-623 | 43 | 0.1433 | 12 |
| 6 | d623-683 | 63 | 0.2100 | 23 |
| 7 | d683-743 | 63 | 0.2100 | 18 |
| 8 | d743-803 | 56 | 0.1867 | 20 |
| 9 | d803-863 | 68 | 0.2267 | 28 |
| 10 | d863-923 | 70 | 0.2333 | 19 |
| 11 | d923-983 | 54 | 0.1800 | 20 |
| 12 | d983-1043 | 17 | 0.0567 | 3 |
| 13 | d1043-1103 | 25 | 0.0833 | 7 |
| 14 | d1103-1163 | 23 | 0.0767 | 9 |
| 15 | d1163-1223 | 15 | 0.0500 | 8 |
| 16 | d1223-1283 | 2 | 0.0067 | 0 |
| 17 | d1283-1343 | 3 | 0.0100 | 0 |

---

*Real data has no ground truth, so nothing here validates TGAP's correctness - it shows the pipeline handles real temporal structure. Every number is a model sensitivity to a controlled counterfactual perturbation, not a causal claim.*
