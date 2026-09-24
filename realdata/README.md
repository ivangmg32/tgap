# TGAP on real temporal data

This folder is a **separate integration layer**. It imports from `core/`;
nothing in `core/` imports from here. The synthetic experiments
(`examples.py`, `evaluation.py`, `paper_evaluation.py`) and their results are
unchanged.

```bash
python -m realdata.download                            # fetch raw files into realdata/data/
python -m realdata.run_real_data                       # leakage-safe evaluation, all 8 datasets
python -m realdata.run_real_data --mode descriptive    # full-period description
python -m realdata.run_real_data --mode both           # both
python -m realdata.run_real_data bitcoin_otc           # one dataset
python -m realdata.compare_datasets --mode both        # comparison tables + figures
python -m unittest discover -s tests                   # 269 tests, 101.8 s
```

> **Only the default mode's results are committed**, under
> `output/real_data_v2/temporal_evaluation/`. Descriptive-mode results are
> reproducible with `--mode descriptive` but are not stored, so a
> leakage-unsafe number cannot be quoted by accident. The pre-cleanup v1
> results were deleted; git history still holds them.

---

## 0. The two analysis modes

The same pipeline runs in two modes, and **every output file records which
one produced it** (`analysis_mode` in `metadata.json`,
`preprocessing_summary.json`, `summary.json`, and as a column in every CSV).

| | `temporal_evaluation` (default) | `descriptive` |
|---|---|---|
| Actor selection | ranked over the **first 20%** of the span | ranked over **everything** |
| Community detection | on the **selection-period** graph, then frozen | on the **full-period** aggregate |
| Snapshots TGAP sees | the **remaining 80%** | all of them |
| Leakage-safe | **yes** | **no** — labelled everywhere |
| Use for | the scientific evaluation | describing a dataset as a whole |

### Why this exists

The original pipeline ranked actors by activity over the whole observation
period. That leaks the future into the past:

```
2018 -------- 2019 -------- 2020 -------- 2021
                     ^
    selection using all four years lets 2021 decide
    which actors appear in the 2018 snapshot
```

Node selection (`adapters/edgelist.py: selectNodes`) and community detection
(`adapters/base.py: fixedPartitionWithReport`) were both inspected and both
really did use the full period. They are now period-scoped, with the old
behaviour retained under `--mode descriptive`.

**`email_eu_core` is exempt from the leakage question.** Its actors come from
SNAP's ground-truth department labels, which are a *static attribute of the
people*, not a statistic of the event stream. Its
`node_selection_mode`/`community_mode` are both `ground_truth_labels`, and
`future_information_used_for_node_selection` is `false` in **both** modes.

### Why 20%

Chosen, then checked. Larger selection windows were measured on the four
weakest datasets, and they do not help — the sparsity is genuine actor
turnover, not a window-size artefact:

| dataset | f=0.2 | f=0.3 | f=0.4 | f=0.5 |
|---|---|---|---|---|
| `tgbl_enron` retained nodes | 25 | 43 | 100 | 120 |
| `bitcoin_otc` median edges/snapshot | 9 | 7 | 15 | 17 |
| `bitcoin_alpha` median edges/snapshot | 12 | 9 | 17 | 21 |
| `tgbl_uci` max bridge width | 74 | 13 | 17 | 10 |

Raising *f* buys almost nothing for bitcoin and *hurts* `tgbl_uci`, while
spending evaluation span. 20% is kept as a fixed, documented constant
(`adapters/base.py: SELECTION_FRACTION`), not a tuned parameter.

### What the leakage-safe mode costs

This is the largest change in the results, so it is stated plainly.
Selecting actors from the early period and evaluating later means tracking a
**cohort that partly goes quiet**:

| dataset | snapshots T / D | retained events T / D | median edges T / D | bridge width T / D |
|---|---|---|---|---|
| `decentraland` | 19 / 24 | 4,996 / 23,543 | 299 / 1,230 | 36–493 / 26–1428 |
| `tgbl_wiki` | 13 / 16 | 13,267 / 43,764 | 19 / 141 | 0–29 / 9–87 |
| `email_eu_core` | 12 / 16 | 12,599 / 16,643 | 175 / 180 | 11–139 / 9–138 |
| `tgbl_enron` | 18 / 22 | 18,510 / 99,745 | 40 / 158 | 0–28 / 6–118 |
| `tgbl_uci` | 16 / 20 | 1,663 / 13,602 | 13 / 40 | 1–74 / 2–188 |
| `sx_mathoverflow` | 16 / 20 | 10,685 / 35,392 | 236 / 622 | 29–386 / 69–465 |
| `bitcoin_otc` | 14 / 21 | 414 / 2,950 | 9 / 97 | 1–25 / 1–79 |
| `bitcoin_alpha` | 13 / 20 | 415 / 2,883 | 12 / 102 | 1–25 / 1–92 |

`email_eu_core` barely changes — its actor set is fixed by labels, so only
the shorter window matters. `tgbl_enron` changes most in node count
(**25** retained vs 120): only 25 employees are active in the first 20% of
its 1,316-day span, so the topN=120 filter is not even reached.

---

## 1. Datasets (unchanged — no datasets were added or removed)

**8 datasets, 2 graph families, 1,440 explanation rows per mode.**

Leakage-safe (`temporal_evaluation`) numbers:

| Dataset | Domain | Family | Snaps | Raw nodes | Retained | % | Raw events | Retained | % | Partition | Community source |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `tgbl_wiki` | wiki editing | bipartite (projected) | 13 | 1,000 | 100 | 10.00 | 157,474 | 13,267 | 8.42 | 25/75 | `temporal_train` |
| `decentraland` | DAO governance | bipartite (projected) | 19 | 4,133 | 100 | 2.42 | 53,533 | 4,996 | 9.33 | 50/50 | `temporal_train` |
| `email_eu_core` | email (institution) | unipartite (observed) | 12 | 986 | 201 | 20.39 | 332,334 | 12,599 | 3.79 | 109/92 | **`ground_truth_labels`** |
| `tgbl_enron` | email (corporate) | unipartite (observed) | 18 | 184 | 25 | 13.59 | 125,235 | 18,510 | 14.78 | 8/17 | `temporal_train` |
| `tgbl_uci` | student messaging | unipartite (observed) | 16 | 1,899 | 120 | 6.32 | 59,835 | 1,663 | 2.78 | 55/65 | `temporal_train` |
| `sx_mathoverflow` | Q&A interaction | unipartite (observed) | 16 | 24,818 | 120 | 0.48 | 506,550 | 10,685 | 2.11 | 57/63 | `temporal_train` |
| `bitcoin_otc` | crypto trust | unipartite (observed) | 14 | 5,881 | 120 | 2.04 | 35,592 | 414 | 1.16 | 45/75 | `temporal_train` |
| `bitcoin_alpha` | crypto trust | unipartite (observed) | 13 | 3,783 | 120 | 3.17 | 24,186 | 415 | 1.72 | 39/81 | `temporal_train` |

**Raw vs retained is never collapsed into one number.** `raw_nodes` is what
the source file contains; `retained_nodes` is what appears in the graphs
TGAP explains. Median retention in the default mode: **4.75% of nodes,
3.29% of events**. Reported in `metadata.json`,
`preprocessing_summary.json`, `summary.json`, `comparison.csv`, and as
`retained_nodes` / `active_retained_nodes` columns in `graph_summary.csv` —
there is no bare `nodes` column anywhere (enforced by a test).

The two families matter. **Bipartite** sources (user→page, voter→proposal)
need a one-mode projection: edges are *derived*. **Unipartite** sources are
observed actor-to-actor edges needing **no projection at all**.

`email_eu_core` is the control case: SNAP ships department labels for all
1,005 people, so its two communities are **real organisational units**. (Its
`raw_nodes` is **986**, not 1,005: that is the number of people who actually
appear in the temporal edge list, measured from the file. 201 of them belong
to the two largest departments and are retained.)

`realdata/data/` is gitignored (large, reproducible from the download
script).

> **Scope of the claim.** These runs show the pipeline handles real temporal
> structure and produces interpretable sensitivities. They do **not**
> validate TGAP's correctness — real data has no ground truth. Correctness
> evidence comes from the synthetic known-truth experiments in
> `paper_evaluation.py`. Nothing here is a causal claim; every number is a
> **model sensitivity to a controlled counterfactual perturbation**.

## 2. Datasets rejected, with measured reasons

Sizes from HTTP HEAD requests against the real URLs.

| Dataset | Measured size | Why rejected |
|---|---|---|
| `tgbl-review` | 539.6 MB | ~4.8M events. Feasible in principle, far larger than needed. |
| `tgbl-coin` | 1284.5 MB | ~22M events. Too large for a reproducible prototype run. |
| `tgbl-flight` | 1281.9 MB | ~67M events. Too large for a reproducible prototype run. |
| SNAP CollegeMsg | 345 KB | **Verified identical to `tgbl-uci`** — same event count, node count and timestamp offsets. Including both would double-count one dataset. |

Recorded in `download.py` (`REJECTED`) and enforced by tests.

## 3. Preprocessing decisions

Six, all recorded in each run's `preprocessing_summary.json`. Full rationale
in `adapters/base.py`'s module docstring.

1. **One-mode projection** for the two bipartite sources. Feeding TGAP the
   bipartite graph with `communities = (actors, items)` would make *every*
   edge a cross edge, so bridge width would equal the edge count and become
   a duplicate of density. Projecting onto one side makes bridge width mean
   "ties between two communities of actors".
2. **Fixed node set in every snapshot**, isolated when inactive, because
   TGAP's anchor rule assumes a constant node set. **Consequence:**
   snapshots are almost never connected, algebraic-connectivity cohesion is
   0 everywhere, and cohesion is **not** used as a prediction target.
3. **Keep only the most active actors, and report both counts** (§1).
4. **Which actors, and from which period** — the analysis mode (§0).
5. **Partition detected once and frozen, from the same period as node
   selection** (§0). Coverage is guaranteed by construction:
   `detectTwoCommunities` defines side B as "every node not in side A", so a
   node with no edge in the selection period still gets a side. How many
   such nodes there were is reported as
   `nodes_isolated_in_partition_graph`.
6. **Edge attributes are not used.** `edge_weight_used: false`,
   `edge_sign_used: false`, plus `edge_attributes_available` naming what the
   source offers, in every dataset's metadata. The bitcoin datasets carry a
   signed trust rating (integer −10…+10, both a sign and a magnitude); no
   current TGAP metric or transformation reads edge weights, so it is
   recorded as available-but-unused rather than silently averaged away.
   Verified by a test that every snapshot's edges carry an empty attribute
   dict.

## 4. Validity gating

A row in `tgap_results.csv` is only usable as an explanation result when the
transformation kept the invariant it promised. Two gates, both measured.

### Gate 1 — edge-count feasibility

`BridgeWidth` and `BridgeTrend` pay for each new bridge edge by deleting an
intra-community edge, so the total edge count stays fixed and the model sees
"the same activity, rerouted". On real snapshots the payment is sometimes
impossible. Three distinct causes now occur and are named separately:

| reason | temporal | descriptive |
|---|---|---|
| insufficient cross-community non-edges to widen the bridge | 11 | 15 |
| insufficient **removable** intra-community edges to preserve total edge count | 10 | 4 |
| insufficient intra-community edges to preserve total edge count | 10 | 10 |
| insufficient intra-community **non**-edges to preserve total edge count | 0 | 1 |
| **total infeasible settings** | **31 / 240** | **30 / 240** |

Two of those reasons look similar but are not: the pool-size check
(`core.Feasibility.bridgeWidthFeasibility`) counts raw intra edges, while
the exact check inside `setBridgeWidth` counts the *usable* pool after the
non-cut-edge preference has narrowed it. The first is a necessary condition;
the second is where the real failure happens.

Such settings get `feasible=False`, an `infeasible_reason`,
`edge_count_before`/`edge_count_after`/`edge_count_preserved`, and
`transformation_status = "edge_count_infeasible"`. **Their numeric fields
are written empty** — the number exists in memory but writing it would
invite its use.

Core can now also fail *explicitly*: `setBridgeWidth(..., strict=True)`
raises `InfeasibleTransformation` at the exact point where the payment falls
short, carrying the measured pool sizes. The flag defaults to `False`, so no
existing behaviour or result changed. Every run cross-checks the two paths:
**0 disagreements in 240 settings per mode (480 total)**.

### Gate 2 — bridge-trend direction

The trend recursion divides backwards by `(1 + delta)`, so the factor
reaching the oldest snapshot is `(1 + delta)^(T−1)`. Targets below 1 are
clamped by `setBridgeWidth`'s width-1 floor, and once enough snapshots sit
there the achieved trend can move *against* the request.

`core.Feasibility.bridgeTrendDirection` records
`requested_direction`, `achieved_direction`, `fraction_saturated`,
`min_bridge_width`, `max_bridge_width` and a status:

| status | temporal | descriptive | valid for analysis |
|---|---|---|---|
| `ok` | 29 | 25 | **yes** |
| `saturated` | 19 | 17 | no |
| `wrong_direction` | 0 | 6 | no |
| `no_property_change` | 0 | 0 | no |

**This is Option B of the cleanup brief, deliberately.** Option A — changing
the recursion so the requested direction is always achieved — would change
the concept the transformation measures *and* change the synthetic results
this project reports, both of which the brief forbids. The recursion is
therefore kept verbatim from TSAP and the failure is detected instead.

### What the gates cost

| | temporal | descriptive |
|---|---|---|
| explanation rows | 1,440 | 1,440 |
| valid for analysis | **1,140** (79.2%) | **1,128** (78.3%) |
| excluded: `edge_count_infeasible` | 186 | — |
| excluded: `saturated` / `wrong_direction` | 114 | — |
| **valid `Bridge Trend` rows** | **36 / 288** | **6 / 288** |
| valid rows, other four concepts | 240–288 each | — |

The headline consequence: **`Bridge Trend` survives gating in only 12.5% of
its rows in the default mode, and 2.1% in descriptive mode.** Any
conclusion that rests on Bridge Trend magnitudes rests on very few rows.

## 5. Transformations and models

All five transformations, each given the fixed partition so the
bridge-preserving guarantees are active:

| Transformation | Meaning here | Declares edge-count preservation |
|---|---|---|
| Bridge Width | ties between the two communities | yes |
| Centralization | concentration of activity on one hub actor | yes |
| Density | overall volume of interaction | **no** — the edge count *is* its property |
| Bridge Trend | whether cross-community ties grow or decay | yes |
| Churn | how much earlier snapshots differ from the present | yes |

That column is now read from each transformation's own
`preservesEdgeCount` attribute, so nothing classifies transformations by
name or `isinstance` chains.

Six models per dataset, reused from `core/` — no new model classes:

| Model | Reads |
|---|---|
| `persistence_bridge_width` | only the **last** snapshot's bridge width |
| `trend_bridge_width` | a line fitted over all snapshots |
| `slope_bridge_width` | the **slope** itself |
| `persistence_density` | only the last snapshot's density |
| `persistence_centralization` | only the last snapshot's centralization |
| `trend_clustering` | a line fitted over clustering |

The first three read the same property three different ways, which is what
lets us ask whether TGAP separates a history-using model from a present-only
one. The last three exist so **every transformation has at least one model
that can respond to it**.

## 6. Output location

```
output/real_data_v2/
├── temporal_evaluation/               <- the scientific evaluation
│   ├── summary.json                   headline results, all 8 datasets
│   ├── comparison.csv                 cross-dataset table
│   ├── comparison_observations.json   computed cross-dataset facts
│   ├── figures/*.png                  3 cross-dataset figures
│   └── <dataset>/
│       ├── metadata.json                    measured dataset facts
│       ├── preprocessing_summary.json       decisions + what they discarded
│       ├── graph_summary.csv                per-snapshot statistics
│       ├── metrics.csv                      metric trajectories
│       ├── tgap_results.csv                 180 rows + validity flags
│       ├── transformation_feasibility.csv   30 settings, gate 1
│       ├── bridge_trend_status.csv          6 settings, gate 2
│       ├── transformation_diagnostics.csv   per-snapshot reach
│       ├── leakage.csv                      property panel per transformation
│       ├── summary.json                     headline results
│       └── figures/*.png                    4 figures
└── descriptive/                       <- same layout, NOT leakage-safe
```

## 7. Findings from the new run

All from `output/real_data_v2/*/comparison.csv` and
`comparison_observations.json`.

### 1. An expected invariant, verified on 8/8 datasets in both modes

The history-only transformations (`Bridge Trend`, `Churn`) return the last
snapshot untouched, and the persistence models read only the last snapshot.
Their prediction change **must** therefore be exactly 0. It is, across
**219** checked rows in the default mode and **213** in descriptive mode.

This is a **verification of an expected invariant** — a correctness check on
the implementation and the pipeline — **not an unexpected empirical
discovery**. The previous wording ("the blindness property survives real
data") overstated it. The check is still worth running: an implementation
slip would break it.

### 2. The discreteness floor reproduces on real data

The synthetic suite derived that an integer property of size *p* can only
move when |δ| ≥ 0.5/p. Measured on valid rows only:

| | temporal | descriptive |
|---|---|---|
| thin-bridge datasets (min width ≤ 5) | **20.06%** no-op | **14.47%** |
| thicker-bridge datasets | **0.00%** no-op | **0.00%** |

A rule derived from theory on synthetic worlds, holding on eight
independently sourced real datasets it was never tuned on. The leakage-safe
mode makes the effect *stronger* (20.06% vs 14.47%) because its graphs are
sparser.

### 3. How much clamping the trend transformation survives

Among the settings where the width-1 floor was hit at all — so both groups
clamped, and the comparison is not circular:

| | settings | mean % of trajectory clamped |
|---|---|---|
| direction still **held** (`saturated`) | 17 | **21.0%** |
| direction **flipped** (`wrong_direction`) | 6 | **57.8%** |

(descriptive mode; in the default mode all 19 clamped settings held, mean
22.0% clamped, and **no setting flipped**.)

So the transformation survives roughly a fifth of its trajectory hitting the
floor and inverts around three-fifths. The flips occur in exactly two
datasets — `decentraland` and `tgbl_enron` — and **only in descriptive
mode**, because its histories are longer (24 and 22 snapshots vs 19 and 18),
which makes the compounding factor larger. This replaces the v1 claim of a
"clear threshold" between datasets with a per-setting measurement.

### 4. The edge-count invariant fails on all 8 datasets — now explicitly

Every dataset has at least one setting where the payment is impossible:
**31/240 settings in the default mode, 30/240 in descriptive**. The clearest
single case remains a two-real-department graph where most email is
*cross*-department, leaving too little internal structure to trade away.

The difference from v1 is not the phenomenon but the handling: these
settings are now reported, their numbers withheld, and they are excluded
from every aggregate and figure. `core` can also be asked to fail loudly
(`strict=True`), and the two detection paths agreed in 480/480 settings.

### 5. Leakage-safe evaluation is substantially harder than the full-period view

Because actor cohorts turn over, the default mode produces sparser graphs
(§0). Structural transformations are consequently blocked more often —
`Centralization` in 27 settings, `Density` in 21, `Bridge Width` in 13
(of 48 per transformation, default mode) — against 12, 5 and 9 in
descriptive mode. `tgbl_enron` and `tgbl_wiki` even reach snapshots with
**bridge width 0**, where the concept is undefined for a relative change;
those counts are reported as `snapshots_with_zero_bridge_width`.

Any claim about real-data behaviour must therefore say which mode it refers
to. The default mode is the methodologically sound one and the harder one.

## 8. Remaining limitations

1. **`Bridge Trend` has too few valid rows to support magnitude claims**
   (36/288 default, 6/288 descriptive). Option A — redesigning the
   recursion so the requested direction is always achieved — is the real
   fix, and it is a core semantic decision left open deliberately: it would
   change the concept and the synthetic results.
2. **The edge-count invariant still fails**, it is now only *reported*
   rather than repaired. The repair options are all semantic choices:
   (a) cap the requested change at what the intra pool can pay for,
   (b) allow payment from the bridge itself, (c) accept a partial achieved
   change. None was chosen unilaterally.
3. **`BridgeTrendTransformation` still raises `ZeroDivisionError` at
   δ = −1.0** (division by `1 + delta`). Unchanged from the synthetic
   audit; the runner stays clear of it.
4. **Retention is low in the default mode** — median 4.75% of nodes and
   3.29% of events. Results describe an early-selected cohort of the most
   active actors, not the whole ecosystem. `bitcoin_otc`/`bitcoin_alpha`
   retain only ~415 events each; treat their numbers as indicative at best.
5. **`tgbl_enron` retains only 25 nodes** in the default mode, with an
   8/17 partition. That is a small graph for a two-community analysis.
6. **Window size and topN were chosen by measured trade-off, not
   optimised**, and the 20% selection fraction is fixed rather than swept
   (the sensitivity check in §0 covers four values on four datasets only).
7. **No ground truth.** Nothing in this folder validates TGAP. It shows
   applicability, not correctness.
8. **Cohesion is unusable** under the fixed-node-set decision.
9. **The partition is one deterministic split** (greedy modularity, or real
   departments for `email_eu_core`). Results are conditional on it.
10. **Single seed (42).** The transformations' internal randomness was not
    swept on real data, unlike the synthetic RQ3.
11. **No trained model.** All six are metric-based baselines, as intended.
    A TGN would plug into the same contract but is not implemented.
12. **A mean-vs-last aggregation mismatch remains.** `propertyValue`
    averages over snapshots while a persistence model reads only the last
    one, so a row can have a non-zero achieved delta and a zero prediction
    change — impact 0 but not flagged `noop`, because a perturbation did
    occur. Visible in `transformation_diagnostics.csv`
    (`last_snapshot_modified`).
