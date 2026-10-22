# TGAP Guided User Study (Phase 1)

Implemented 2026-10-22. A step-by-step section of the TGAP Laboratory
(`#guided`, sidebar **Guided user study**) that runs one complete TGAP
experiment on the real research pipeline and regenerates every empirical chart
of the paper (`Temporal_GNN_Explainer`, Figs 1–12, Tables 5–7, RQ1–RQ8) from
the user's own configuration. The TGAP-versus-CoDy comparison is **not** part
of this phase.

## Workflow

1. **Introduction** – what TGAP does, key terms, a live example (Stable
   ecosystem), the "model response, not causation" caveat, workflow, measured
   run times on this server, and optional predefined scenarios.
2. **Dataset** – cards with metadata computed from the fixture/generator
   (nodes, edges per snapshot, snapshots and time labels, communities,
   preprocessing, constraints).
3. **Model & target** – the six Table-4 models with the meaning and unit of
   their output, live original prediction for each, and a target snapshot
   (the prediction made at time *t* using snapshots 1..*t*).
4. **Transformation** – the five concepts (structural/temporal, delta units,
   edge-count promise, constraints, current value), direction, requested size,
   a server-side feasibility pre-check, optional custom transformer
   (interpreted subset, separate resource-limited worker), and the extra runs
   that paper charts need (comparison models/concepts, request sizes, seed
   repeats, graph sizes, matched sweep).
5. **Review & run** – every setting, original output, metrics, planned extra
   runs and which charts will be produced; stage-by-stage progress.
6. **Results** – A summary cards · B original vs transformed graph (snapshot
   selector) and concept history · C requested vs achieved and validity ·
   D every paper chart, grouped · static/published references (clearly marked
   "not your result") · **Overall Experiment Conclusion** · G provenance and
   exports (JSON, long-format CSV, standalone HTML report, print/PDF).

Every chart has a six-part explanation directly beneath it (what it measures,
conditions, key results, pattern, what can / cannot be concluded), generated
deterministically from the run's values by `sandbox/interpret.py`. Results
carry a configuration hash; if settings change after a run, the results page
shows a banner that they belong to the earlier configuration.

## Architecture

| File | Role |
|---|---|
| `workbench/sandbox/guided.py` | Runs the guided experiment in the worker: the existing `engine.execute` for the selected explanation and local measurements, then the model × concept × size matrix (each counterfactual built once and scored by every model), `core.temporalAttribution`, seed repeats, graph sizes, matched comparison (`sweepConcept`/`bestMatch`/`comparabilityOf`), bridge matrices and the snapshot view. Also dataset profiles, previews and feasibility pre-checks. |
| `workbench/sandbox/chart_registry.py` | `INVENTORY`: the traceable mapping paper chart → computation → data → page component; `build_charts()` asserts every entry produces a chart payload (never silently dropped). |
| `workbench/sandbox/interpret.py` | Deterministic chart explanations, experiment status, overall conclusion. |
| `workbench/sandbox/app.py` | `/api/guided/{catalogue,preview,feasibility,experiments,events}` and downloads; `jobs.kind`/`jobs.progress`; `guided_events` table; guided jobs use the same queue with a 240 s / 16 MiB budget. |
| `workbench/sandbox/worker.py` | Dispatches guided jobs; writes progress atomically. |
| `workbench/sandbox/guided_scenarios.json` | Predefined scenarios for a study administrator (paper case studies, RQ2 known-truth). |
| `workbench/static/guided.js`, `style.css` | Wizard, results dashboard and SVG chart renderers (reusing the Laboratory's edge-time, bar and scatter renderers). |
| `realdata/comparability.py` | `comparabilityOf` moved out of `run_tgn_stability.py` (re-exported there) so the web worker does not import PyTorch. |
| `workbench/sandbox/engine.py` | Added optional `target_snapshot`/`n_per_community` and a shared `validity_gate()`; lab behaviour unchanged. |

## User-study data

Interaction events (`step_enter`, `step_complete`, `validation_error`,
`run_submitted`, `run_complete`, `run_failed`, `results_viewed`, `export`,
`scenario_selected`, each with step, job id and scenario only) are stored
**only** while the account has an active consented study session, keyed by the
existing pseudonymous session. No free text, no new questionnaires or scales.
Withdrawal deletes them. Researchers can export `/api/admin/export/guided_events`.
Guided jobs keep the lab's spec fields, so existing history, researcher report
and exports include them unchanged.

## Fidelity checks

* Stable world, present-only bridge model: impact ±8 at every size; Bridge
  Trend leaves present-only models at exactly 0 and gives the slope model ±1
  (paper RQ1/RQ2/RQ5).
* Validity on the paper's case studies reproduces Table 5 exactly:
  Decentraland 180 / 144 valid / 18 edge-count / 18 saturated;
  Email-Eu-core 180 / 138 / 30 / 12. Bridge Trend has no valid Decentraland
  rows, as the paper states.
* Every matrix run uses exactly 1 + 2K model calls.

## Chart inventory

`kind`: dynamic = regenerated from the run; conditional = regenerated when the
needed option/dataset type is chosen; static = illustration plus a live
version; blocked = cannot be reproduced in the web workbench (reason given;
the published figure is shown, labelled as a reference).

| # | Paper reference | Chart (id) | Kind | Research question | Axes / series | Needs | Multiple runs? | Shown as | Implementation |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Fig. 1 — `fig0_tgap_architecture` | `workflow` | static | Method overview (no research question). | Diagram; no axes. | Nothing; the live diagram fills in this run's dataset, model, concept and call counts. | No. | Original diagram in the reference area plus a live workflow diagram with this run's values. | `chart_registry._workflow` |
| 2 | Fig. 2 — `fig1_final_model_separated_impacts` | `model_separated_impacts` | dynamic | How does each model respond to each transformation on a dataset? | x: normalized impact (own axis per model panel); rows: semantic groups (relative-delta concepts share a row; Centralization and Bridge Trend own rows); columns: models; points: one valid (delta, direction) row; colour: sign. | All selected models x selected concepts x request sizes x both directions on the selected dataset, with validity gating. | Yes: models x concepts x deltas x 2 (paper: 6 x 5 x 3 x 2 = 180 per dataset). | Strip-plot small multiples, one panel per model and semantic row. | `guided.execute_guided.run_matrix + chart_registry._strips` |
| 3 | Fig. 3 — `fig9_true_beeswarm` | `beeswarm` | dynamic | How are valid impacts distributed for each concept? | x: impact; rows: concepts inside semantic-group panels; colour: sign; deterministic packing, no jitter. | The model x concept x delta matrix (valid rows only). | Yes (same matrix as Fig. 2). | Packed dot plot per semantic group. | `chart_registry._beeswarm` |
| 4 | Fig. 4 — `fig10_publication_boxplot` | `boxplot` | dynamic | What is the spread of comparable concept responses within each model? | x: impact; one panel per model; boxes: relative-delta concepts only (Centralization and Bridge Trend excluded); n printed; points overlaid. | The model x concept x delta matrix (valid rows only). | Yes (same matrix as Fig. 2). | One box panel per model. | `chart_registry._boxplot` |
| 5 | Fig. 5 (and Tables 6-7) — `fig7_tgn_seed_stability` | `tgn_seed_stability` | blocked | Learned-model applicability and seed stability. | x: metric (AUC, AP, accuracy, baseline score); y: value across 5 training seeds. | Training a Temporal Graph Network (PyTorch, torch_geometric) five times on Email-Eu-core with held-out evaluation. | Yes: 5 training seeds. | Published reference image, clearly labelled; the RQ3 seed-stability chart below measures a different quantity on your model. | `none (blocked)`<br>**Blocked:** The web workbench runs only the six transparent analytical models in a bounded worker (one process, minutes at most). Training and replaying a TGN for five seeds needs PyTorch/torch_geometric and far more time than the worker budget, so this chart is not regenerated. Run `tgap run tgn` locally to reproduce it. |
| 6 | Fig. 6 — `fig4_local_graph` | `local_graph` | dynamic | Which concrete edges realize the concept change? | Node-link diagram with fixed positions; added edges and removed edges highlighted; snapshot selectable. | The original and transformed snapshots for the selected concept and direction. | No. | Original vs transformed network, side by side, with a snapshot selector. | `guided.run_structure (view)` |
| 7 | Fig. 7 — `fig11_local_bar` | `local_bar` | dynamic | Which individual edges move this prediction when removed? | y: edge; x: prediction difference after removing the edge from every snapshot (model output units). | Edge occlusion on the user's graph and model (bounded subset). | No (bounded extra calls). | Diverging bar chart. | `sandbox.analyses.detailed_analyses (edges)` |
| 8 | Fig. 8 — `fig5_temporal_local` | `temporal_local` | dynamic | When does the concept matter to each model? | x: snapshot; y: prediction difference when only that snapshot is transformed; one panel per model. | The selected concept/direction applied to one snapshot at a time, scored by each selected model. | Yes: models x snapshots predictions (transformation computed once). | Bar panels per model. | `guided.run_temporal (core.temporalAttribution)` |
| 9 | Fig. 9 — `fig12_temporal_edge_time` | `edge_time` | dynamic | Which edges matter at which time? | rows: selected edges; columns: snapshots; colour: prediction difference after removing that edge at that time only. | Edge occlusion per snapshot for the most responsive measured edges. | No (bounded extra calls). | Heatmap. | `sandbox.analyses.detailed_analyses (edge_time)` |
| 10 | Fig. 10 — `fig8_dependence` | `dependence` | dynamic | Do structurally prominent elements have larger measured responses? | x: node total degree / edge snapshots present; y: prediction difference after removal. | Node and edge occlusion measurements. | No. | Two scatter plots. | `sandbox.analyses.detailed_analyses (nodes, edges)` |
| 11 | Fig. 11 — `fig6_impact_distribution` | `impact_distribution` | dynamic | Exploratory spread of all valid impacts per concept. | x: sign(impact) * log10(1+/impact/); rows: concepts; colour: sign. | The model x concept x delta matrix (valid rows). | Yes (same matrix as Fig. 2). | Packed dot plot on a signed-log axis. | `chart_registry._signedlog` |
| 12 | Fig. 12 — `fig3_bridge_matrix` | `bridge_matrix` | dynamic | How do ties between each pair of communities change? | Community x community matrix; cells: edges in the target snapshot, original -> transformed; diagonal: internal edges. | Original and transformed target snapshot. | No. | Two matrices (increase, decrease). | `guided.run_structure (core.bridgeMatrix)` |
| 13 | §4.6 (Eqs. 8-10) | `requested_vs_achieved` | dynamic | Did the transformation achieve what was requested? | x: requested change (signed); y: achieved change in the concept's own units; status per point. | Requested/achieved deltas for the selected concept at every request size, and for all concepts at the selected size. | Uses the matrix runs. | Paired comparison chart and table. | `chart_registry._req_ach` |
| 14 | Table 5; real-data validity_map.png | `validity_map` | dynamic | Which settings are valid for analysis, and why are others excluded? | rows: concepts; columns: request size x direction; colour: status. Counts by cause as in Table 5. | Validity gate for every concept x delta x direction (model-independent). | Uses the matrix runs. | Status grid and Table-5-style counts. | `chart_registry._validity` |
| 15 | RQ5 (§6.7); output/synthetic/delta_sensitivity.png | `delta_sensitivity` | dynamic | What happens as the requested perturbation size changes? | x: requested change; y: normalized impact; markers: no-op / invalid. | The selected model and concept at each requested size. | Yes: one explanation per request size. | Line-and-point chart per direction. | `chart_registry._delta` |
| 16 | RQ8 (§6.10); output/synthetic/normalization_ablation.png | `normalization` | dynamic | What is the effect of normalizing by achieved rather than requested change? | x: requested change; y: impact under each normalization. | Prediction change, requested and achieved deltas from the same runs. | Uses the matrix runs. | Grouped bars per request size. | `chart_registry._normalization` |
| 17 | RQ2 (§6.4); output/synthetic/temporal_sensitivity.png | `temporal_sensitivity` | conditional | Can TGAP distinguish a present-only model from a history-dependent model? | x: model; y: Bridge Trend impact for increase and decrease. | Bridge Trend in the concept set and at least one model. | Uses the matrix runs. | Grouped bars per model. | `chart_registry._temporal_sensitivity` |
| 18 | Real-data metric_trajectories.png | `trajectory` | dynamic | How did the transformation reshape the history? | x: snapshot; y: Bridge Width, Density, Centralization; original vs transformed. | Original and transformed snapshots. | No. | Line chart with metric selector. | `sandbox.engine.execute (comparisons.trajectory)` |
| 19 | RQ6 (§6.8); output/synthetic/leakage.png | `leakage` | dynamic | How much do non-target properties change? | rows: measured property; x: change (mean over snapshots), increase and decrease. | Leakage panel measured on the same counterfactual. | Uses the matrix runs. | Diverging bars per property. | `guided.run_matrix (leakage)` |
| 20 | RQ3 (§6.5); output/synthetic/stability.png | `seed_stability` | conditional | Are repeated explanations reproducible, and how much do they vary across seeds? | x: direction; y: impact per seed; mean, SD and range. | Repeated runs with different transformation (or, for synthetic data, graph) seeds. | Yes: one explanation per seed (user-chosen count). | Dot plot with mean and range. | `guided.run_stability` |
| 21 | RQ4 (§6.6, Eq. 6); output/synthetic/efficiency.csv | `efficiency` | dynamic | Does the implementation use the expected model-call budget? | x: run; y: model calls, measured vs expected 1 + 2K; stage durations. | Call counters on every explanation run. | Uses all runs. | Paired bars and timing table. | `chart_registry._efficiency` |
| 22 | RQ7 (§6.9); output/synthetic/graph_size_robustness.csv, global_bridge_sensitivity.png | `graph_size` | conditional | Does behaviour persist across graph sizes? | x: nodes per community; y: impact (and achieved change, no-op, edge-count preservation). | Regenerating a synthetic dataset at several sizes; impossible for real fixtures whose node set is fixed. | Yes: one explanation per size. | Point chart per direction. | `guided.run_sizes` |
| 23 | RQ1b (§6.3); output/synthetic/matched_comparison.png | `matched_comparison` | conditional | When can two concepts' responses be compared? | Concept pairs x direction: comparable or not, reason, matched impacts. | A fine sweep of request sizes per concept (MATCH_DELTAS) on the selected model. | Yes: concepts x 12 request sizes x 2. | Pair table with matched impacts. | `guided.run_matched` |
| 24 | RQ1 (§6.2); output/synthetic/faithfulness.csv | `faithfulness` | blocked | Can TGAP recover relationships known from the model definition? | Table of measured vs analytical impact and relative error. | The synthetic known-truth model suite (pure Bridge Width, pure Centralization, weighted 2*BW + 3*C) with analytical expectations. | Yes. | Documented limitation. | `none (blocked)`<br>**Blocked:** The workbench models are the six real-data analytical variants (Table 4), not the known-truth suite, and no analytical expectation is defined for an arbitrary dataset. Run `tgap run paper` locally for RQ1. Your persistence-model runs on synthetic data can still be checked by hand: a present-only Bridge Width model's impact equals its baseline bridge count when bridges are constant over time. |

Pipeline-only figures in `output/real_data/*/figures` map as follows:
`explanation_heatmap`/`impact_by_transformation` → Fig. 2 strips and the
summary; `delta_sensitivity` → RQ5; `validity_map` → validity chart;
`metric_trajectories`/`activity_over_time` → concept history chart.
`output/finance/**` figures belong to the separate finance study and are not
paper figures.

## Known limitations

* Fig. 5 / Tables 6–7 (TGN seeds) and RQ1 (known-truth model suite) are not
  regenerated in the browser; run `tgap run tgn` / `tgap run paper` locally.
* Paper figures pool two datasets (Fig. 11: eight); the guided run covers the
  selected dataset only, stated on each chart.
* RQ7/RQ8 report measured values without analytical error, because the
  selected model has no analytical truth on arbitrary data.
* Element-level analyses (Figs 7, 9, 10) stay within the Laboratory's bounded
  budget (128 calls / 10 s) and are marked partial when not exhaustive.
* Leakage Cohesion is computed by exact dense eigen-decomposition: the core
  `CohesionMetric` (networkx iterative solver) does not terminate on some
  graphs with repeated Laplacian eigenvalues (e.g. a snapshot that became
  complete). This affects the research library itself and should be fixed
  there separately.
* Custom code runs in the existing interpreted subset in a separate worker
  process with CPU/memory/time limits; this is not container isolation.

## Tests

`workbench/tests/test_guided.py` (19 tests): known truth, matrix vs explainer
formulas and call budget, inventory completeness against the publication
manifest, Table 5 reproduction, target window, custom concept, stability,
sizes, interpretation for invalid / no-op / no-response / failed stages, API
validation of incompatible configurations, run–poll–download, ownership,
consent-gated events and withdrawal.
