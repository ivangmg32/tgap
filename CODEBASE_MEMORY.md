# TGAP codebase memory and navigation guide

Reviewed: 2026-10-08. Workspace: `C:\catalyst\tgap`.
Baseline branch: `real-data`; commit: `8eb32d9bb5d81ab6027123dee0c4567f183da8fb`.

This is a repository knowledge file for later questions and changes. Read this
first in a new session, then inspect the relevant implementation and current
Git diff. It records the reviewed version, not a promise that future code stays
the same. Conversation context can use these findings now; this file supplies
durable context when a future session does not retain the conversation.

## 1. Purpose and overall structure

TGAP means Temporal Graph Additive exPlanations. It is a Python research
prototype in the CATALYST project, inspired by TSAP for time series. It explains
any model that maps a graph or a graph history to one number. It changes a
human-readable concept, predicts again, and measures the model's sensitivity.
It does not establish causation in the real ecosystem, and its impacts are not
a guaranteed additive decomposition like a sum of Shapley values.

There are two substantial strands in this repository: the TGAP explanation and
evaluation framework, and separate stock-correlation data-mining experiments.
The finance code is not currently wired into the TGAP real-data adapters.

| Location | Responsibility |
|---|---|
| `core/` | Model/metric contracts, explainers, transformations, communities, feasibility, diagnostics, synthetic data, local attribution, sparsity, optional TGN |
| `core/Transformations/` | Five concepts, one implementation per file, and shared graph-rewiring helpers |
| `realdata/adapters/` | Convert timestamped events into fixed-node graph snapshots and a frozen partition |
| `realdata/` | Downloads, dataset runs, comparison, N-community experiments, TGN runs, publication exports |
| `examples.py` | Synthetic demos and interactive Plotly examples; use `--no-show` for console mode |
| `examples/` | Runnable custom-transformation example and package marker |
| `evaluation.py` | Smaller synthetic evaluation; writes top-level `output/*.csv` |
| `paper_evaluation.py` | Expanded synthetic evaluation, RQ1–RQ8 and matched comparisons; writes `output/paper/` |
| `tests/` | `unittest` tests for algorithms, contracts, dataset preprocessing, saved outputs, and figure semantics |
| `finance/` | Yahoo Finance cache, weighted correlation networks, four statistical experiments, saved results |
| `drafts/` | A tiny DAO graph scratch file, not an implemented subsystem |
| `docs/` | Eleven explanations, walkthroughs, audit/history documents, study protocol, and case studies |
| `output/` | Existing generated CSV/JSON/Markdown/PNG/PDF artifacts, including current and superseded figures |
| `requirements.txt` | Base scientific Python dependencies |
| `.gitignore` | Python/editor artifacts, finance price cache, and `realdata/data/` raw downloads |
| `LICENSE` | GPL version 3 license text |

There is no web application, database service, package build configuration,
container setup, or CI workflow among the reviewed tracked files. Commands
normally run from the repository root; many output paths are relative to it.

## 2. Data and public contracts

- A graph is a simple undirected `networkx.Graph`.
- A temporal graph is a Python **list** of snapshots, oldest to newest. Several
  functions specifically use `isinstance(x, list)`; an arbitrary sequence or
  pandas Series is not an interchangeable input everywhere.
- Keep the node set fixed across snapshots. Real-data adapters include inactive
  nodes as isolates. Transformations return copies and must not mutate inputs.
- Communities can be a legacy `(setA, setB)` tuple, a list of sets, or a
  `Partition` representing N groups. Prefer an explicit frozen partition.
- `delta=0.1` requests a positive 10% change, but each transformation defines
  what that request controls. Discrete graphs may achieve a different amount.
- Node labels are sorted and compared in several helpers; use mutually
  comparable labels (the adapters use strings, synthetic generators integers).

`core/__init__.py` re-exports the main public API. TGN is accessed separately
through `core.TgnModel` so importing the basic framework need not load Torch.

| Contract | Minimum method |
|---|---|
| `GraphModel` | `predict(graph)` returns one numerical output |
| `TemporalGraphModel` | `predict(temporalGraph)` returns one numerical output |
| `Metric` | `measure(graph)` returns a scalar |
| `TemporalGraphTransformation` | `name`, `propertyValue(x)`, and `transformGraph(graph, delta)` for structural concepts or `transform(history, delta)` for temporal concepts |

Transformation defaults are `deltaMode="relative"` and
`preservesEdgeCount=True`. `propertyValue` may return `None` when the concept
cannot be measured. The inherited temporal transform applies `transformGraph`
to every snapshot; temporal concepts override it.

## 3. How an explanation works

`GraphExplainer.py` contains `ExplainerBase`, shared by `GraphExplainer` and
`TgapExplainer` (`TemporalGraphExplainer.py`). The subclasses only decide
whether to call `transformGraph` or `transform`.

1. Resolve transformations. If none were supplied, detect two communities from
   the input graph or last snapshot and share them between Bridge Width and
   Centralization. These defaults are for exploration; real-data experiments
   pass their earlier-period partition explicitly.
2. Compute `baseline = model.predict(x)` once.
3. For each transformation, compute its property on the original input.
4. Apply the transformation independently at `+defaultDelta` and
   `-defaultDelta`, and predict each transformed input.
5. Measure achieved property change and normalize the prediction difference.
6. Return records; optionally measure a leakage metric panel as well.

For relative mode and nonzero original property:

```text
achievedDelta = (propertyAfter - propertyBefore) / abs(propertyBefore)
impact = (predictionAfter - baseline) / abs(achievedDelta)
```

Absolute mode uses `propertyAfter - propertyBefore`. A zero original property
also falls back to this difference in property units. If no nonzero achieved
change is available, the engine falls back to dividing by `abs(requestedDelta)`.
When both achieved change and prediction difference are zero it reports
`impact=0` and `noop=True`. In requested-normalization mode property measurement
is skipped, so achieved-delta provenance and no-op detection differ.

Example: six bridges become seven after a +10% request. The achieved change is
1/6, not 0.1. A model predicting bridge count has impact `1 / (1/6) = 6`.
Positive impact means this particular perturbation raised the prediction;
decrease-direction rows often have negative impact because the denominator is
an absolute magnitude, not a signed derivative denominator.

`explain()` returns `{label: impact}`. `explainDetailed()` returns a list with
`label`, `transformation`, `requestedDelta`, `achievedDelta`, `deltaMode`,
`baseline`, `transformed`, `impact`, `normalizer`, `noop`, and `leakage`.
Cost is **1 + 2K model calls** for K transformations (11 for five concepts).
This counts predictions, not all graph operations or feasibility probes.

Plotly methods: `summaryData`/`plotSummary` use a signed logarithmic display;
`plotTrans` plots raw prediction changes across requested deltas;
`boxplotTrans` plots distributions across inputs and caches one baseline per
input. Plot methods return figures and accept `show=False`.

The low-level explainer does **not** automatically apply the real-data validity
gates described below. Its transformation interface is generic.

## 4. Models and graph measurements

| Implementation | Behavior |
|---|---|
| `MetricGraphModel` | Evaluate a metric on one graph |
| `PersistenceTemporalModel` | Evaluate the metric on the last snapshot |
| `TrendTemporalModel` | Fit an OLS line to per-snapshot metric values and extrapolate to index T; one snapshot falls back to persistence |
| `WeightedMetricModel` | Sum weighted metrics, reading either the last snapshot or their mean (`mode="last"` / `"mean"`) |
| `SlopeModel` | Return the metric trajectory's OLS slope; fewer than two snapshots return zero |

Metrics in `GraphMetric.py`: NetworkX density; Freeman degree centralization
`sum(maxDegree-degree)/((n-1)(n-2))`; crossing-edge count for Bridge Width;
average clustering; and algebraic connectivity for Cohesion. Tiny graphs have
defined guards where appropriate. Disconnected graphs have Cohesion zero;
the spectral solver is seeded.

An important aggregation detail: structural `propertyValue` usually averages
over snapshots, while persistence reads only the last graph. An achieved
history-wide change can therefore coexist with a zero persistence response.
That does not necessarily mean the perturbation was a no-op.

## 5. The five transformation implementations

| File / concept | What changes | Constraints and measurement |
|---|---|---|
| `BridgeWidth.py` / Bridge Width | Target is `round(width*(1+delta))` per snapshot | Change crossing edges, pay using intra-community edges; node set and intended edge budget fixed. Property is mean crossing-edge count. Optional `communityPair=(i,j)` and `strict=True`. |
| `Centralization.py` / Centralization | Rewire roughly `round(abs(delta)*edgeCount)` edges toward or away from hubs | Keep nodes and edge count; with a partition, move endpoints within the same community so the pairwise crossing structure stays fixed. Property is mean Freeman centralization. Requested delta is a mechanism knob, not an exact centralization percentage. |
| `Density.py` / Density | Add or remove edges to target the requested edge-count change | Nodes fixed; edge count deliberately changes (`preservesEdgeCount=False`). With a partition, only intra-community edges change. Property is mean edge count. |
| `BridgeTrend.py` / Bridge Trend | Reshape the bridge-width history with TSAP backward recursion | Last snapshot copied unchanged; earlier graphs use `setBridgeWidth`; absolute delta mode measures OLS slope. Optional pair targeting and strict payment. Rejects exactly `delta == -1` with `ValueError`. |
| `Churn.py` / Churn | Make earlier edge sets agree more or less with the last graph | Last graph unchanged; paired removals/additions keep edge counts. With a partition, affect only intra-community edges. Property is mean Jaccard distance from each earlier eligible edge set to the present. |

`Base.py` shares `_edgeKey`, `_snapshots`, `_safeToRemove`, and
`setBridgeWidth`. The removal helper prefers non-cut edges but falls back to
all candidates if none are safe: connectivity is a preference, not an absolute
guarantee. `setBridgeWidth` floors target width at one. In permissive mode it
can fail to pay for all added/removed crossing edges and change the edge count;
strict mode raises `InfeasibleTransformation` with measured details.

Bridge Trend recursion, preserving the original differences:

```text
target[last] = originalWidth[last]
target[t] = (target[t+1] + originalWidth[t] - originalWidth[t+1]) / (1+delta)
```

Long histories can hit the width-one floor, distort the requested shape, and
even reverse the achieved direction. Preserve these semantics unless a task
explicitly calls for changing the method and its published evidence.

Random transformations recreate seeded RNGs for each call; temporal ones
typically use `seed + snapshotIndex`. Integer rounding uses Python's
half-to-even rule. Density addition canonicalizes undirected non-edges before
sorting to avoid process-dependent string hash orientation.

## 6. Communities and extensibility

`Partition` subclasses `tuple` for legacy two-group unpacking. It stores
disjoint sets, labels, and a node-to-group index. Methods include
`communityOf`, `sameCommunity`, `sizes`, `nodes`, `pairs`, and `labelOfPair`.
Groups are sets; do not mutate them after construction because the lookup
index was built once.

`detectCommunities` uses greedy modularity; `n=None` keeps natural groups,
while explicit n merges to that count and can include empty groups.
`detectTwoCommunities` keeps the largest detected group versus the remainder.
Bridge aggregate is the **sum of all pairwise crossing-edge counts**.
`bridgeMatrix` includes zero-count pairs. Pair-specific transformations pay
only from their two groups. N=2 compatibility is covered by regression tests.

To add a concept to the core API, simply pass an instance in the transformation
list. `examples/MyCustomTransformation.py` demonstrates Isolation: change the
number of degree-zero nodes and honestly declare no edge-count preservation.

`TransformationRegistry.py` is an additional **pipeline** registry with
factories and metadata: `preservesEdgeCount`, `needsTrendGating`, `temporal`,
`description`, and `builtin`. It provides `register`, `unregister`, `get`,
`names`, `entries`, `buildAll`, and `conceptNames`. Built-ins are registered at
import time. It is not needed by the explainer and does not discover files.
Factories are called with communities/kwargs and may retry after `TypeError`.

Integration is incomplete: the main runner builds transformations through the
registry, but `screenBridgeTrend` still identifies the built-in class and
`rowValidity` checks the literal `"Bridge Trend"`. Do not assume registering
`needsTrendGating=True` automatically extends all gate paths.

## 7. Feasibility and interpretation safeguards

`Feasibility.py` has pure pool inspection (`bridgeWidthFeasibility`), empirical
per-snapshot edge-count checking (`edgeCountFeasibility`), declaration lookup,
and direction/floor diagnostics (`bridgeTrendDirection`). Strict exceptions
carry the exact mechanism failure; pool-size checks alone are only necessary
conditions because edge-selection preferences can narrow usable pools.

The main real-data runner combines gates through `rowValidity`:

- Edge-count failure takes priority: `edge_count_infeasible`, invalid, with
  prediction/impact numeric fields blanked when writing results.
- Bridge Trend statuses `saturated`, `wrong_direction`, and
  `no_property_change` are invalid for analysis, but their numeric values may
  remain for diagnostic inspection.
- `ok` with feasible perturbation is valid. Use `valid_for_analysis`, not merely
  nonmissing `impact`, when aggregating outputs.

Do not mix missing/invalid cells with genuine zeros. Do not rank all concept
impacts across models or incompatible perturbation units. The current
publication figure keeps each model separate and isolates Centralization and
Bridge Trend from the relative-change concepts.

Implementation details to revisit if changing comparison code: `bestMatch`
returns the closest pair and takes a `tolerance` argument, but does not itself
reject a gap above that tolerance; synthetic callers enforce the threshold.
The TGN stability caller currently accepts a returned pair without separately
checking the gap. Also, `bridgeTrendDirection` measures aggregate bridge widths
for floor diagnostics, even if the transformation targets a specific pair.
These are observations from source inspection, not fixes made in this task.

## 8. Local explanations, attribution, and sparsity

`LocalExplanation.py` separates two kinds of information:

- `graphDifference` and `localExplanation`: record the added/removed/kept
  edges, touched nodes, per-snapshot changes, achieved concept change, and
  optional predictions. A touched edge is not thereby assigned importance.
- `edgeAttribution`: remove one edge from every snapshot, predict again, and
  report the **raw prediction difference**. It supports deterministic sample,
  structural `topK`, budget, and optional bridge-only selection, with coverage.
- `nodeAttribution`: isolate one node across history while retaining the node
  set; structural top-K and budget caps are reported with coverage.
- `temporalAttribution`: retain only one snapshot's part of a concept
  perturbation; cost 1+T. Per-snapshot impacts need not add up for nonlinear
  models.
- `edgeTimeAttribution`: remove one edge in one snapshot; distinct from a
  whole-concept snapshot perturbation. Returns response times and all-zero
  diagnostics. Top-K selects by endpoint degrees within each snapshot.
- `writeElementAttribution` and `writeTemporalAttribution` persist flat stable
  CSV schemas and provenance. Temporal output records `attribution_level`.

Occlusion costs one baseline plus one model call per evaluated element. It
does not share the concept explanation's 1+2K budget. Structural pre-ranking
does not mean elements were ranked by measured importance before evaluation.

`Sparsity.py` counts exact zero impacts by default; optional thresholds are
recorded. Concept sparsity excludes no-ops and invalid rows. Element sparsity
retains coverage. Never average the two levels: their denominators differ.
An empty usable set has undefined sparsity, rather than a perfect score.

`Diagnostics.py` supplies `CallCountingModel`, metric panels, leakage reports,
and console formatting. Leakage is measured off-target property movement.

## 9. Synthetic generation and evaluation

`SyntheticData.py` generates two-community graphs with internal path
backbones, random extra edges, exact initial bridges, internal churn, and
optional bridge drift. **Legacy `bridgeDrift > 0` removes bridges**; negative
values add them. Ten scenario presets cover stable/growing/decaying bridges,
churn extremes, hub concentration, unequal sizes, and sparse/dense regimes.

N-community generators accept per-pair bridge widths, an optional default,
and per-pair temporal drift. Their drift follows `width + drift*step`, so its
sign convention differs from the legacy two-group generator. N-community
internal graphs are regenerated with `seed+step` and need not be connected.

`evaluation.py` measures known-truth faithfulness, repeatability and seed
variation, call/time cost, delta effects, and leakage. The expanded
`paper_evaluation.py` adds explicit expectation kinds (`exact`, `zero`,
`measured`) and follows this experiment map:

| Experiment | Question |
|---|---|
| RQ1 | Recover analytically known dependencies, recording leakage-adjusted expectations where possible |
| RQ1b | Sweep requests, match achieved changes, compare only sufficiently close same-unit settings across five seeds |
| RQ2 | Distinguish present-only and trajectory-sensitive models |
| RQ3 | Separate exact repeatability, variation of graph seeds, and transformation seeds |
| RQ4 | Count predictions and measure runtime, including baseline caching |
| RQ5 | Sensitivity to requested delta |
| RQ6 | Intended change versus leakage, including temporal properties |
| RQ7 | Robustness across graph sizes |
| RQ8 | Achieved versus requested normalization |

Known-truth mean-mode linear models align model aggregation with the
transformation property measurement. Real-data runs demonstrate applicability;
they do not supply analytical explanation ground truth.

## 10. Real-data pipeline

`download.py` caches ten source files for eight datasets in ignored
`realdata/data/`, using urllib, a certifi SSL context, and source URL metadata.
`fileDigest` hashes only the first MiB by default: it is a fingerprint, not a
whole-file checksum. Existing cached paths are trusted unless force is set.

Adapters return `PreparedDataset(name, snapshots, communities, labels, meta,
preprocessing)`. `base.py` contains projection, temporal selection boundaries,
frozen partitions, retention/selection reports, modularity loss, aggregate
graphs, and per-snapshot summaries.

Default `temporal_evaluation` uses the first 20% of the **time span** for actor
selection and detected communities. It freezes those choices and builds
evaluated graphs from the remaining period. `descriptive` ranks and detects
on the full period and is labeled accordingly. Static department labels take
the ground-truth path. These preprocessing periods are separate from the
later TGN train/test split.

All current real-data graphs drop direction, weights, signs, self-loops, and
repeated-edge multiplicity as appropriate; discarded richer fields are
documented. Fixed nodes cause isolates and disconnected graphs, so Cohesion
is not a real-data prediction target. Report both raw and retained counts.
Only windows with retained events are materialized; absent windows are not
automatically filled with empty graphs. OLS models use snapshot index rather
than the actual elapsed-time gaps in human-readable labels.

| Key | Adapter and nodes/edges | Defaults |
|---|---|---|
| `decentraland` | Voter wallets; co-voting on the same proposal, frozen 2023 export | Top 100 voters; calendar months |
| `tgbl_wiki` | Wikipedia **pages**; two pages co-edited by one user | Top 100 pages; two-day windows |
| `email_eu_core` | People and observed emails; real department partition | Two largest departments by default; 40-day windows |
| `tgbl_enron` | Employees and observed emails | Top 120 active candidates; 60-day windows |
| `tgbl_uci` | Students and messages | Top 120; 10-day windows |
| `sx_mathoverflow` | Users and question/answer/comment interaction | Top 120; 120-day windows |
| `bitcoin_otc` | Traders and trust-rating events, rating discarded | Top 120; 90-day windows |
| `bitcoin_alpha` | Traders and trust-rating events, rating discarded | Top 120; 90-day windows |

`edgelist.py` shares parsing and preprocessing for the six unipartite datasets.
Bitcoin timestamps are column index 3, unlike the usual index 2. Enron/UCI
archive headers differ from Wiki. UCI and SNAP CollegeMsg are intentionally
not counted as independent datasets.

`run_real_data.py` prepares data, writes metadata/metrics, screens feasibility
and trend direction, runs six models at deltas 0.1/0.25/0.5 in both directions,
writes explanation/leakage/reach diagnostics, figures, a report, and summary.
Six models × five concepts × three sizes × two directions = 180 rows/dataset.
Models: persistence/trend/slope bridge width, persistence density,
persistence centralization, and trend clustering.

`compare_datasets.py` reads completed per-dataset outputs, computes tables and
observations, and exports three cross-dataset figures. It filters valid rows
for analysis. `run_ncommunity.py` runs N=2,3,4 for unipartite datasets, compares
pair-reading models against pair perturbations, and reports selectivity and
modularity. Its pairwise result schema does not include the main runner's
feasibility flags; do not treat it as an identical gated experiment.

## 11. Optional learned model: TGN

`TgnModel.py` catches optional Torch/PyG import failures, exposes
`TORCH_AVAILABLE`/`requireTorch`, and wraps TGN memory, a TransformerConv
embedding, and an endpoint link predictor in the standard `predict` contract.
Default model dimensions are 32; neighbor-loader size is 10; CPU is the
practical default used by the runners.

Each prediction sets evaluation mode and resets memory and neighbor state,
replays history, then returns the mean sigmoid score for edges in the last
nonempty event batch. Edge-event messages encode endpoint degree divided by
node count. Node labels map to contiguous IDs in the adapter. Each prediction
is a full replay, so eleven calls can be much more expensive than eleven
metric evaluations. Empty graphs are filtered from event batches: a final
empty snapshot therefore does not necessarily mean an empty readout.

Training uses self-supervised positive links and sampled negative targets,
BCE loss, Adam, and detached memory between batches. `splitTemporally` defaults
to earlier 70% training and later test snapshots; runners use 50 epochs.
Held-out evaluation reports AP, ROC AUC, and accuracy with balanced classes.
The model demonstrates explaining a learned function; it is not presented as
a tuned link-prediction benchmark winner.

`run_tgn.py` reuses main validity gates and stores `tgn_link_prediction` rows.
`run_tgn_stability.py` trains seeds 0–4 on the same split, persists each seed,
per-concept spread/sign consistency, performance summaries, and matched
comparisons. It rejects comparisons across different delta modes or involving
Centralization in `comparabilityOf`. Never quote a single seed's concept
impact as stable across trained models.

Source-inspection cautions for future TGN work: several tensors are created
on CPU despite a device argument, test event timestamps restart at zero,
and held-out negative selection checks a sampled pair `(u,v)` but retains only
v before scoring it against the positive source tensor. These deserve focused
validation before making stronger evaluation or device-support claims.

## 12. Publication and stored outputs

`realdata/plotting.py` centralizes plotting themes and PNG/PDF export and
draws the architecture figure. `make_publication.py` reads existing runs,
builds manuscript tables, generates concept/local/element/time figures, writes
comparability metadata, and persists attribution before its consuming plots.

Current main global figure:
`output/publication/fig1_final_model_separated_impacts.{png,pdf}`.
It preserves each dataset/model separately and plots individual valid rows;
it does not pool different model scales into a global importance ranking.
Older candidates are retained in `output/publication/superseded/` with reasons
in its README. Consult `figure_metadata.json` for permitted interpretations.

| Artifact family | Contents |
|---|---|
| `output/*.csv` | Smaller evaluation results |
| `output/paper/` | Expanded synthetic CSVs, plots, and summary |
| `output/real_data_v2/temporal_evaluation/<dataset>/` | Current real-data metadata, retention, graph summary, metrics, `tgap_results`, feasibility, trend status, reach diagnostics, leakage, report, figures |
| `output/real_data_v2/temporal_evaluation/` | Combined summary, comparison table, observations, cross-dataset figures |
| `output/real_data_v2/tgn/` | Learned-model run results |
| `output/real_data_v2/tgn_stability/email_eu_core/` | Per-seed explanations, performance spread, concept stability, matched comparisons |
| `output/real_data_v2/ncommunity/` | Pairwise experiments and per-N summaries |
| `output/publication/` | Tables 1–9, final figures, metadata, and attribution CSVs/provenance |
| `finance/resultsDatamining/` | Temporal stock features, RQ1–RQ4 tables, and report |

The code supports descriptive outputs, but a full `descriptive/` result tree
was not present in the visible tracked inventory at review time.

Stored temporal comparison reports eight datasets, 1,440 explanation rows,
1,140 valid rows, 300 excluded, and only 36/288 valid Bridge Trend rows.
These are **existing artifact measurements**, not a fresh full-pipeline rerun.
The five-seed stored TGN AUC mean is 0.74404, sample SD 0.028832, range
0.702–0.7727. Preserve provenance when citing results.

## 13. Finance subsystem

`Cache.py` fetches adjusted stock price histories from yfinance and caches CSVs
under `./finance/Cache/` and in memory. Filenames include ticker and duration,
but not interval; cached data has no automatic freshness expiry.

`CorrGraphs.py` aligns Close prices, drops incomplete rows, computes percentage
returns and Pearson correlations, and creates a weighted edge for every
nonmissing ticker pair. `temporalGraph` uses calendar sliding windows with
approximately evenly spaced actual ending dates and returns a **pandas
Series of graphs**, each carrying start/end/period metadata. Visualization
methods draw weighted stock graphs and temporal frames.

`experimentationDatamining.py` contains `ExperimentConfig`, feature extraction,
bootstrap/Welch/permutation helpers, a runner, CSV/text export, and CLI:

1. RQ1: split windows by median mean absolute correlation and compare network
   statistics between synchronization groups.
2. RQ2: Spearman density association and optional statsmodels OLS with HAC
   covariance.
3. RQ3: within-sector versus cross-sector absolute correlation; permute sector
   labels while preserving graph weights.
4. RQ4: permute weights among existing edges, preserve topology, compare a
   chosen statistic. This is not a time-series null model.

Current all-pairs correlation graphs are normally complete: unweighted density
and clustering are both one. Existing RQ2 outputs consequently have undefined
density correlations. Permuting edge weights leaves mean absolute correlation
unchanged, so the current default RQ4 statistic cannot detect allocation
effects. These follow from construction and match the saved finance report.
`block_length` is configured but not used by the bootstrap implementation.

`yfinance` is imported by finance but absent from base requirements;
`statsmodels` is optional. Finance uses sibling imports (`from Cache`,
`from CorrGraphs`) and is most naturally executed as a script. No finance
test module exists in the current TGAP test suite.

## 14. Documentation map and historical caveats

| Document | Use |
|---|---|
| `README.md` | Public overview, install/run commands, contracts and extension example |
| `realdata/README.md` | Real-data rationale, modes, preprocessing, output interpretation; some limitations are historical |
| `docs/01-TSAP-explained-simply.md` | TSAP background |
| `docs/02-TGAP-code-walkthrough.md` | Earlier core walkthrough |
| `docs/03-TGAP-technical-audit.md` | Earlier mathematical/implementation audit |
| `docs/04-TGAP-v02-walkthrough.md` | Achieved normalization and v0.2 changes |
| `docs/05-TGAP-worked-example-trace.md` | Concrete explanation trace |
| `docs/06-TGAP-complete-guide-A-to-Z.md` | Broad conceptual guide |
| `docs/07-real-data-explained-simply.md` | Accessible real-data explanation |
| `docs/08-real-data-outputs-and-pipeline.md` | Pipeline/output schema guide |
| `docs/09-user-study-design.md` | **Design only**, no collected participants/results |
| `docs/10-case-studies.md` | Decentraland and Email-Eu-core examples |
| `docs/11-status-report.md` | Explicitly superseded point-in-time status; read the correction banner |

Use code and source CSV/JSON as the current authority. Earlier docs refer to a
monolithic `Transformations.py`, claim no implemented TGN, report old test
counts, or say delta=-1 causes `ZeroDivisionError`; these no longer describe
the reviewed implementation. Some historical charts pool incompatible units.
Do not copy these claims into new work. The study protocol describes a planned
36-person, three-condition study and contains empty result tables; there is
no implemented recruitment/data-collection application here.

## 15. Practical commands and change navigation

Run these from the repository root. Commands that generate artifacts overwrite
their output files; raw downloads and finance fetching can require networking.

```powershell
pip install -r requirements.txt
python examples.py --no-show
python -m examples.MyCustomTransformation
python -m unittest discover -s tests
python evaluation.py
python paper_evaluation.py
python -m realdata.download
python -m realdata.run_real_data
python -m realdata.run_real_data email_eu_core
python -m realdata.run_real_data --mode descriptive
python -m realdata.compare_datasets
python -m realdata.run_ncommunity email_eu_core
python -m realdata.run_tgn email_eu_core
python -m realdata.run_tgn_stability email_eu_core
python -m realdata.make_publication
python finance/experimentationDatamining.py --period 5y --window 6mo --graphs 20
```

Optional learned-model install: Torch and torch_geometric; optional finance
install: yfinance and statsmodels. Base requirements: networkx, numpy, pandas,
matplotlib, scipy, plotly, certifi. There is no pinned lockfile.

| Future task | Start here and check these tests |
|---|---|
| Impact math, normalization, plotting API | `core/GraphExplainer.py`; `test_explainer`, `test_custom_transformation` |
| Graph edits / new concept | Transformation contract, relevant concept and `Base.py`; `test_transformations`, `test_feasibility`, `test_custom_transformation` |
| N-community behavior | `Communities.py`, pair-targeted edits, synthetic N generators; `test_communities`, `test_ncommunity_known_truth` |
| Dataset ingestion / leakage | `realdata/adapters/*`; `test_realdata` |
| Validity handling / result aggregation | `Feasibility.py`, main runner, comparison/publication readers; `test_validity_gating` |
| Learned model / seeds | `TgnModel.py`, TGN runners; `test_tgn`, `test_tgn_stability`, `test_registry` stability cases |
| Element/time attribution | `LocalExplanation.py`; `test_local_explanation`, `test_attribution_persistence` |
| Sparsity | `Sparsity.py`; `test_sparsity` |
| Synthetic paper claims | `paper_evaluation.py`; `test_paper_evaluation` |
| Publication appearance / interpretation | `make_publication.py`, `plotting.py`, metadata; `test_semantic_figures`, `test_publication_figures`, `test_registry` |
| Stocks / statistical experiments | `finance/Cache.py`, `CorrGraphs.py`, `experimentationDatamining.py`; inspect saved report and validate separately |

Preserve the existing camelCase public conventions in `core/`. Keep model
adapters behind `predict`, measurements honest about achieved changes,
invalid rows excluded from analysis, and attribution scopes/coverage explicit.
Re-read the relevant source before a change rather than treating this guide
as executable specification.

## 16. Review coverage and verification

Fresh verification on 2026-10-07: `python -m unittest discover -s tests`
ran **533 tests in 219.455 seconds; OK, 2 skipped** (531 passed, no failures
or errors), using Python 3.11.7. Torch/PyG imports succeeded in this environment.
Warnings included Matplotlib/Torch deprecations, unclosed-file resource warnings
in tests, duplicate optimizer parameters, and tensor-to-scalar conversion.
These were warnings, not failures. The test suite exercises generated figures
and existing result artifacts; this does not mean the complete scientific
pipelines were rerun. Git status after verification showed only this new guide;
no tracked source or result artifact changes.

The source inventory contains 64 Python files and 20,288 lines, including
tests and package markers. All source files were parsed for their structure;
the principal implementation paths were inspected directly, together with
documentation structure, historical caveats, and representative stored
result schemas/summaries. This review does not claim a line-by-line formal
audit of every test, every repeated documentation passage, every CSV row,
or a visual review of every generated image/PDF. No scientific pipeline was
regenerated for this knowledge task.

The following inventory is generated from the reviewed source. Line numbers
and hashes identify that snapshot and should be refreshed after changes.

### Source module index

#### `core/__init__.py`

112 lines; SHA-256 prefix `bccbb3b62b9736c8`.

Project dependencies: `from .GraphMetric import Metric, DensityMetric, DegreeCentralizationMetric, BridgeWidthMetric, CohesionMetric, ClusteringMetric`; `from .GraphModel import GraphModel, MetricGraphModel`; `from .TemporalGraphModel import TemporalGraphModel, PersistenceTemporalModel, TrendTemporalModel, WeightedMetricModel, SlopeModel`; `from .TemporalGraphTransformation import TemporalGraphTransformation`; `from .Transformations import BridgeWidthTransformation, CentralizationTransformation, DensityTransformation, BridgeTrendTransformation, ChurnTransformation`; `from .GraphExplainer import GraphExplainer`; `from .TemporalGraphExplainer import TgapExplainer`; `from .Communities import Partition, asPartition, detectCommunities, detectTwoCommunities, interCommunityEdges, intraCommunityEdges, bridgeMatrix, aggregateBridgeWidth`; `from .SyntheticData import makeNCommunityGraph, makeNCommunityTemporalGraph, makeTwoCommunityGraph, makeTemporalGraph, makeScenario, SCENARIOS`; `from .Feasibility import InfeasibleTransformation, bridgeWidthFeasibility, edgeCountFeasibility, bridgeTrendDirection, declaresEdgeCountPreservation`; `from .LocalExplanation import localExplanation, graphDifference, edgeAttribution, nodeAttribution, temporalAttribution, edgeTimeAttribution, writeElementAttribution, writeTemporalAttribution, ELEMENT_ATTRIBUTION_COLUMNS, TEMPORAL_ATTRIBUTION_COLUMNS`; `from .Sparsity import conceptSparsity, elementSparsity, sparsityReport`; `from .Diagnostics import CallCountingModel, leakageReport, formatLeakageReport, panelValue`.


#### `core/Communities.py`

291 lines; SHA-256 prefix `1050195b5ad1e880`.

- `Partition(tuple)` (line 39); methods: `__new__`, `labels`, `communityOf`, `sameCommunity`, `sizes`, `nodes`, `pairs`, `labelOfPair`, `__repr__`.
- `asPartition(communities)` (line 132).
- `detectCommunities(graph, n=None)` (line 145).
- `detectTwoCommunities(graph)` (line 187).
- `interCommunityEdges(graph, communities, pair=None)` (line 204).
- `intraCommunityEdges(graph, communities, community_=None)` (line 234).
- `bridgeMatrix(graph, communities)` (line 250).
- `aggregateBridgeWidth(graph, communities)` (line 276).

#### `core/Diagnostics.py`

86 lines; SHA-256 prefix `64e552a013b5967e`.

- `CallCountingModel` (line 21); methods: `__init__`, `predict`.
- `panelValue(metric, x)` (line 35).
- `leakageReport(x, transformation, delta, metrics)` (line 43).
- `formatLeakageReport(report, intendedName=None)` (line 75).

#### `core/Feasibility.py`

323 lines; SHA-256 prefix `e73da961d95eb67f`.

Project dependencies: `from .Communities import asPartition, interCommunityEdges, intraCommunityEdges`.

- `InfeasibleTransformation(Exception)` (line 48); methods: `__init__`.
- `bridgeWidthFeasibility(graph, communities, targetWidth, pair=None)` (line 60).
- `declaresEdgeCountPreservation(transformation)` (line 137).
- `edgeCountFeasibility(snapshots, transformation, delta, communities=None, strictTransformation=None)` (line 148).
- `bridgeTrendDirection(snapshots, transformation, delta)` (line 251).

#### `core/GraphExplainer.py`

387 lines; SHA-256 prefix `d18763fa19cfc2ba`.

- `_panelValue(metric, x)` (line 38).
- `ExplainerBase` (line 46); methods: `__init__`, `_applyTransformation`, `_resolveTransformations`, `explain`, `explainDetailed`, `summaryData`, `plotSummary`, `plotTrans`, `boxplotTrans`.
- `GraphExplainer(ExplainerBase)` (line 380); methods: `_applyTransformation`.

#### `core/GraphMetric.py`

145 lines; SHA-256 prefix `9be5240c69116d7d`.

Project dependencies: `from .Communities import detectTwoCommunities, interCommunityEdges`.

- `Metric` (line 22); methods: `measure`.
- `DensityMetric(Metric)` (line 32); methods: `measure`.
- `DegreeCentralizationMetric(Metric)` (line 40); methods: `measure`.
- `BridgeWidthMetric(Metric)` (line 64); methods: `__init__`, `measure`.
- `ClusteringMetric(Metric)` (line 101); methods: `measure`.
- `CohesionMetric(Metric)` (line 117); methods: `__init__`, `measure`.

#### `core/GraphModel.py`

40 lines; SHA-256 prefix `4fd67485457c624a`.

- `GraphModel` (line 11); methods: `predict`.
- `MetricGraphModel(GraphModel)` (line 24); methods: `__init__`, `predict`.

#### `core/LocalExplanation.py`

513 lines; SHA-256 prefix `13d52f6a2bc3dca4`.

Project dependencies: `from .Communities import asPartition, bridgeMatrix, interCommunityEdges`.

- `_edgeSet(graph)` (line 40).
- `graphDifference(before, after)` (line 44).
- `localExplanation(temporalGraph, transformation, delta, model=None, communities=None)` (line 64).
- `_candidateEdges(temporalGraph, communities=None, onlyBridges=False)` (line 163).
- `edgeAttribution(temporalGraph, model, communities=None, topK=None, sample=None, budget=None, seed=42, onlyBridges=False)` (line 178).
- `nodeAttribution(temporalGraph, model, topK=None, budget=None, seed=42)` (line 257).
- `temporalAttribution(temporalGraph, model, transformation, delta)` (line 303).
- `_writeRows(rows, columns, path)` (line 374).
- `writeElementAttribution(attribution, path, dataset=None, model=None, seed=None)` (line 389).
- `writeTemporalAttribution(attribution, path, dataset=None, model=None, seed=None, achievedDelta=None, level='snapshot_concept')` (line 417).
- `edgeTimeAttribution(temporalGraph, model, snapshotIndex=None, topK=None, seed=42)` (line 444).

#### `core/Sparsity.py`

179 lines; SHA-256 prefix `5f101f363b509017`.

- `_classify(values, threshold)` (line 47).
- `_summarise(carrying, inactive, threshold, level)` (line 65).
- `conceptSparsity(records, threshold=None, validOnly=True)` (line 83).
- `elementSparsity(attribution, threshold=None)` (line 127).
- `sparsityReport(records, attribution=None, threshold=None)` (line 163).

#### `core/SyntheticData.py`

319 lines; SHA-256 prefix `058f98bc2e88422e`.

- `makeTwoCommunityGraph(nPerCommunity=15, pIntra=0.3, bridgeWidth=6, seed=42, nPerCommunityB=None)` (line 30).
- `makeTemporalGraph(nSnapshots=8, nPerCommunity=15, pIntra=0.3, bridgeWidth=6, churn=0.05, bridgeDrift=0, seed=42, nPerCommunityB=None)` (line 78).
- `makeScenario(name, nSnapshots=6, nPerCommunity=15, seed=42)` (line 163).
- `makeNCommunityGraph(nCommunities=3, nPerCommunity=8, pIntra=0.3, bridgeWidths=None, seed=42)` (line 239).
- `makeNCommunityTemporalGraph(nSnapshots=6, nCommunities=3, nPerCommunity=8, pIntra=0.3, bridgeWidths=None, bridgeDrift=None, seed=42)` (line 290).

#### `core/TemporalGraphExplainer.py`

38 lines; SHA-256 prefix `a9b7da24eafea4e6`.

Project dependencies: `from .GraphExplainer import ExplainerBase`.

- `TgapExplainer(ExplainerBase)` (line 31); methods: `_applyTransformation`.

#### `core/TemporalGraphModel.py`

144 lines; SHA-256 prefix `2cba1d651cd2a0e7`.

- `TemporalGraphModel` (line 20); methods: `predict`.
- `PersistenceTemporalModel(TemporalGraphModel)` (line 34); methods: `__init__`, `predict`.
- `TrendTemporalModel(TemporalGraphModel)` (line 53); methods: `__init__`, `predict`.
- `WeightedMetricModel(TemporalGraphModel)` (line 89); methods: `__init__`, `predict`.
- `SlopeModel(TemporalGraphModel)` (line 125); methods: `__init__`, `predict`.

#### `core/TemporalGraphTransformation.py`

104 lines; SHA-256 prefix `d55303a31837a146`.

- `TemporalGraphTransformation` (line 32); methods: `propertyValue`, `transformGraph`, `transform`.

#### `core/TgnModel.py`

516 lines; SHA-256 prefix `dad5f13a63bf0841`.

Project dependencies: `from .TemporalGraphModel import TemporalGraphModel`.

- `requireTorch()` (line 66).
- `TgnTemporalGraphModel(TemporalGraphModel)` (line 117); methods: `__init__`, `predict`, `_identifier`, `_eventsFrom`, `_replay`, `_scoreSnapshot`.
- `buildTgn(nodeCount, memoryDimension=32, timeDimension=32, embeddingDimension=32, seed=42, device=None)` (line 262).
- `trainTgn(model, temporalGraph, epochs=3, learningRate=0.001, seed=42)` (line 289).
- `splitTemporally(temporalGraph, trainFraction=0.7)` (line 368).
- `_averagePrecision(scores, labels)` (line 379).
- `_areaUnderRoc(scores, labels)` (line 399).
- `evaluateTgn(model, trainSnapshots, testSnapshots, seed=42)` (line 414).

#### `core/TransformationRegistry.py`

153 lines; SHA-256 prefix `760dd8c1f7b5c246`.

Project dependencies: `from .Transformations import BridgeTrendTransformation, BridgeWidthTransformation, CentralizationTransformation, ChurnTransformation, DensityTransformation`.

- `TransformationEntry` (line 48); methods: `__init__`, `build`, `__repr__`.
- `register(name, factory, preservesEdgeCount=None, needsTrendGating=False, temporal=False, description='', builtin=False, replace=False)` (line 81).
- `unregister(name)` (line 101).
- `get(name)` (line 107).
- `names()` (line 113).
- `entries(builtinOnly=False)` (line 118).
- `buildAll(communities=None, builtinOnly=False, **kwargs)` (line 122).
- `conceptNames(builtinOnly=False)` (line 132).

#### `core/Transformations/__init__.py`

59 lines; SHA-256 prefix `70200b677252daf3`.

Project dependencies: `from .Base import setBridgeWidth, _edgeKey, _snapshots, _safeToRemove`; `from .BridgeWidth import BridgeWidthTransformation`; `from .Centralization import CentralizationTransformation`; `from .Density import DensityTransformation`; `from .BridgeTrend import BridgeTrendTransformation`; `from .Churn import ChurnTransformation`.


#### `core/Transformations/Base.py`

177 lines; SHA-256 prefix `2b4025dcab74cc4c`.

Project dependencies: `from ..TemporalGraphTransformation import TemporalGraphTransformation`; `from ..Communities import asPartition, detectTwoCommunities, interCommunityEdges, intraCommunityEdges`; `from ..GraphMetric import DegreeCentralizationMetric`; `from ..Feasibility import InfeasibleTransformation, bridgeWidthFeasibility`.

- `_edgeKey(u, v)` (line 29).
- `_snapshots(x)` (line 35).
- `_safeToRemove(graph, edges)` (line 42).
- `setBridgeWidth(graph, communities, targetWidth, rng, strict=False, pair=None)` (line 58).

#### `core/Transformations/BridgeTrend.py`

167 lines; SHA-256 prefix `4660663a0644572c`.

Project dependencies: `from ..TemporalGraphTransformation import TemporalGraphTransformation`; `from ..Communities import asPartition, detectTwoCommunities, interCommunityEdges, intraCommunityEdges`; `from ..GraphMetric import DegreeCentralizationMetric`; `from ..Feasibility import InfeasibleTransformation, bridgeWidthFeasibility`; `from .Base import _snapshots, setBridgeWidth`.

- `BridgeTrendTransformation(TemporalGraphTransformation)` (line 41); methods: `__init__`, `propertyValue`, `transformGraph`, `transform`.

#### `core/Transformations/BridgeWidth.py`

105 lines; SHA-256 prefix `55f0d756862ffc3f`.

Project dependencies: `from ..TemporalGraphTransformation import TemporalGraphTransformation`; `from ..Communities import asPartition, detectTwoCommunities, interCommunityEdges, intraCommunityEdges`; `from ..GraphMetric import DegreeCentralizationMetric`; `from ..Feasibility import InfeasibleTransformation, bridgeWidthFeasibility`; `from .Base import _snapshots, setBridgeWidth`.

- `BridgeWidthTransformation(TemporalGraphTransformation)` (line 41); methods: `__init__`, `transformGraph`, `propertyValue`.

#### `core/Transformations/Centralization.py`

181 lines; SHA-256 prefix `26682806bf5665b8`.

Project dependencies: `from ..TemporalGraphTransformation import TemporalGraphTransformation`; `from ..Communities import asPartition, detectTwoCommunities, interCommunityEdges, intraCommunityEdges`; `from ..GraphMetric import DegreeCentralizationMetric`; `from ..Feasibility import InfeasibleTransformation, bridgeWidthFeasibility`; `from .Base import _snapshots`.

- `CentralizationTransformation(TemporalGraphTransformation)` (line 41); methods: `__init__`, `_sameSide`, `transformGraph`, `propertyValue`.

#### `core/Transformations/Churn.py`

172 lines; SHA-256 prefix `d236dceb4241cfe5`.

Project dependencies: `from ..TemporalGraphTransformation import TemporalGraphTransformation`; `from ..Communities import asPartition, detectTwoCommunities, interCommunityEdges, intraCommunityEdges`; `from ..GraphMetric import DegreeCentralizationMetric`; `from ..Feasibility import InfeasibleTransformation, bridgeWidthFeasibility`; `from .Base import _edgeKey, _snapshots, _safeToRemove`.

- `ChurnTransformation(TemporalGraphTransformation)` (line 41); methods: `__init__`, `transformGraph`, `_isIntra`, `propertyValue`, `transform`.

#### `core/Transformations/Density.py`

116 lines; SHA-256 prefix `450bd3caedd8969f`.

Project dependencies: `from ..TemporalGraphTransformation import TemporalGraphTransformation`; `from ..Communities import asPartition, detectTwoCommunities, interCommunityEdges, intraCommunityEdges`; `from ..GraphMetric import DegreeCentralizationMetric`; `from ..Feasibility import InfeasibleTransformation, bridgeWidthFeasibility`; `from .Base import _edgeKey, _snapshots, _safeToRemove`.

- `DensityTransformation(TemporalGraphTransformation)` (line 41); methods: `__init__`, `_isIntra`, `transformGraph`, `propertyValue`.

#### `drafts/draftDAOsNetworkX.py`

3 lines; SHA-256 prefix `ba9cd2a9023dc25b`.


#### `evaluation.py`

297 lines; SHA-256 prefix `5e28d6b7b930c1fc`.

Project dependencies: `from core import TgapExplainer, PersistenceTemporalModel, WeightedMetricModel, SlopeModel, BridgeWidthMetric, DegreeCentralizationMetric, DensityMetric, ClusteringMetric, CohesionMetric, BridgeWidthTransformation, CentralizationTransformation, DensityTransformation, BridgeTrendTransformation, ChurnTransformation, CallCountingModel, leakageReport, makeTemporalGraph`.

- `makeWorld(seed=42)` (line 58).
- `makeTransformations(comm, seed=42)` (line 64).
- `evaluateFaithfulness()` (line 73).
- `evaluateStability()` (line 157).
- `evaluateEfficiency()` (line 196).
- `evaluateDeltaSensitivity()` (line 218).
- `evaluateLeakage()` (line 248).

#### `examples/__init__.py`

1 lines; SHA-256 prefix `4210045be7808d06`.


#### `examples/MyCustomTransformation.py`

176 lines; SHA-256 prefix `a4e84cefb30e48f5`.

Project dependencies: `from core import BridgeWidthMetric, PersistenceTemporalModel, TemporalGraphTransformation, TgapExplainer, TrendTemporalModel, makeTemporalGraph`; `from core.GraphMetric import DensityMetric`.

- `IsolationTransformation(TemporalGraphTransformation)` (line 53); methods: `__init__`, `propertyValue`, `transformGraph`.
- `main()` (line 131).

#### `examples.py`

313 lines; SHA-256 prefix `500eb8779c8cd088`.

Project dependencies: `from core import BridgeWidthMetric, CohesionMetric, DegreeCentralizationMetric, PersistenceTemporalModel, TrendTemporalModel, BridgeWidthTransformation, CentralizationTransformation, BridgeTrendTransformation, ChurnTransformation, TgapExplainer, makeTemporalGraph`.

- `sanityCheck()` (line 39).
- `localExplanation()` (line 110).
- `globalExplanation()` (line 190).
- `temporalProperties()` (line 226).

#### `finance/Cache.py`

57 lines; SHA-256 prefix `dc393c17718a8d6c`.

- `Cache` (line 13); methods: `__init__`, `filename`, `history`.

#### `finance/CorrGraphs.py`

431 lines; SHA-256 prefix `8ecc40b1a59bdb87`.

Project dependencies: `from Cache import Cache`.

- `CorrGraphs` (line 10); methods: `__init__`, `_buildGraph`, `graph`, `temporalGraph`, `_periodToOffset`, `_periodToDays`, `plotGraph`, `plotTemporalGraph`.
- `main()` (line 396).

#### `finance/experimentationDatamining.py`

878 lines; SHA-256 prefix `36cce1cb2294fa5e`.

Project dependencies: `from CorrGraphs import CorrGraphs`.

- `ExperimentConfig` (line 78); methods: .
- `_validate_temporal_networks(temporal_networks: pd.Series)` (line 92).
- `_graph_correlation_values(graph: nx.Graph)` (line 97).
- `_graph_statistics(graph: nx.Graph, strong_correlation_threshold: float=0.7)` (line 108).
- `_mean_graph_statistic(graph: nx.Graph, statistic: str='mean_abs_corr', threshold: float=0.7)` (line 168).
- `extract_temporal_features(temporal_networks: pd.Series, strong_correlation_threshold: float=0.7)` (line 198).
- `_bootstrap_mean_difference(group_a: np.ndarray, group_b: np.ndarray, iterations: int, rng: np.random.Generator)` (line 222).
- `_welch_test(group_a: np.ndarray, group_b: np.ndarray)` (line 247).
- `_permutation_test_difference(group_a: np.ndarray, group_b: np.ndarray, iterations: int, rng: np.random.Generator)` (line 285).
- `experiment_rq1_synchronization_groups(features: pd.DataFrame, alpha: float=0.05, bootstrap_iterations: int=2000, random_seed: int=42)` (line 316).
- `experiment_rq2_density_association(features: pd.DataFrame)` (line 387).
- `_sector_pair_statistics(graph: nx.Graph, sectors: Mapping[str, str])` (line 433).
- `experiment_rq3_sector_structure(temporal_networks: pd.Series, sectors: Mapping[str, str], iterations: int=2000, random_seed: int=42)` (line 466).
- `experiment_rq4_null_model(temporal_networks: pd.Series, statistic: str='mean_abs_corr', iterations: int=500, strong_correlation_threshold: float=0.7, random_seed: int=42)` (line 551).
- `run_all_experiments(tickers: Sequence[str]=DEFAULT_TICKERS, sectors: Mapping[str, str]=DEFAULT_SECTORS, config: Optional[ExperimentConfig]=None, cache_path: str='./finance/Cache/')` (line 651).
- `save_results(results: Mapping[str, object], output_directory: str='./finance/resultsDatamining')` (line 717).
- `_build_argument_parser()` (line 805).
- `main()` (line 821).

#### `paper_evaluation.py`

1507 lines; SHA-256 prefix `4c6295261aec8fa6`.

Project dependencies: `from core import TgapExplainer, PersistenceTemporalModel, TrendTemporalModel, WeightedMetricModel, SlopeModel, BridgeWidthMetric, DegreeCentralizationMetric, DensityMetric, ClusteringMetric, CohesionMetric, BridgeWidthTransformation, CentralizationTransformation, DensityTransformation, BridgeTrendTransformation, ChurnTransformation, CallCountingModel, leakageReport, makeTemporalGraph`.

- `makeWorld(seed=BASE_SEED, nPerCommunity=15, bridgeWidth=8, nSnapshots=6, bridgeDrift=0, churn=0.05)` (line 111).
- `makeTransformations(comm, seed=BASE_SEED)` (line 122).
- `meanMetric(metric, tg)` (line 132).
- `savePlot(fig, name)` (line 138).
- `saveCsv(rows, name)` (line 145).
- `errorFields(expectation, measured)` (line 151).
- `buildKnownTruthModels(tg, comm)` (line 169).
- `rq1Faithfulness(seed=BASE_SEED)` (line 272).
- `sweepConcept(model, tg, trans, deltas)` (line 445).
- `bestMatch(sweepA, sweepB, direction, tolerance=MATCH_TOLERANCE)` (line 470).
- `matchedComparisonForSeed(seed)` (line 500).
- `rq1bMatchedComparison(seeds=RQ1B_SEEDS)` (line 584).
- `rq2TemporalSensitivity(seed=BASE_SEED)` (line 731).
- `rq3Stability(nSeeds=10)` (line 814).
- `rq4Efficiency()` (line 898).
- `rq5DeltaSensitivity(seed=BASE_SEED)` (line 961).
- `rq6Leakage(seed=BASE_SEED, delta=0.1)` (line 1014).
- `rq7GraphSizeRobustness(nSeeds=5)` (line 1115).
- `rq8NormalizationAblation(seed=BASE_SEED)` (line 1218).
- `printSummary(results)` (line 1295).
- `toJson(results)` (line 1444).
- `runAll()` (line 1488).

#### `realdata/__init__.py`

44 lines; SHA-256 prefix `6a88c3ec9ebc4f7f`.


#### `realdata/adapters/__init__.py`

21 lines; SHA-256 prefix `8e0f17429a670c93`.

Project dependencies: `from .base import ANALYSIS_MODES, DESCRIPTIVE, TEMPORAL_EVALUATION, SELECTION_FRACTION, checkMode, temporalSplit, projectCoActivity, aggregateGraph, fixedPartitionFromAggregate, fixedPartitionWithReport, summariseSnapshots, retentionSummary, selectionWindowSummary, PreparedDataset`.


#### `realdata/adapters/base.py`

443 lines; SHA-256 prefix `026cda6792c48c40`.

Project dependencies: `from core.Communities import detectCommunities, detectTwoCommunities, interCommunityEdges`.

- `PreparedDataset` (line 130); methods: `__init__`.
- `checkMode(mode)` (line 153).
- `temporalSplit(times, fraction=SELECTION_FRACTION)` (line 162).
- `retentionSummary(rawNodes, retainedNodes, rawEvents, retainedEvents)` (line 176).
- `selectionWindowSummary(mode, activityBasis, fraction, eventsTotal, eventsSelection, eventsEvaluation, selectionStart, selectionEnd, evaluationEnd, timeUnit)` (line 202).
- `projectCoActivity(events, actorKey, itemKey, windowKey, keepActors)` (line 249).
- `aggregateGraph(snapshots, nodes=None)` (line 289).
- `_partitionFromGraph(graph, source, nCommunities=2)` (line 300).
- `_modularityReport(graph, communities)` (line 349).
- `fixedPartitionFromAggregate(snapshots)` (line 381).
- `fixedPartitionWithReport(snapshots, mode, trainingSnapshots=None, nodes=None, nCommunities=2)` (line 395).
- `summariseSnapshots(snapshots, communities, labels)` (line 419).

#### `realdata/adapters/decentraland.py`

245 lines; SHA-256 prefix `b4ece3961f104685`.

Project dependencies: `from .base import PreparedDataset, TEMPORAL_EVALUATION, SELECTION_FRACTION, aggregateGraph, checkMode, projectCoActivity, retentionSummary, selectionWindowSummary, _partitionFromGraph`; `from ..download import download, fileDigest`.

- `readVotes()` (line 77).
- `prepare(topVoters=100, windowFreq='MS', mode=TEMPORAL_EVALUATION, selectionFraction=SELECTION_FRACTION, nCommunities=2)` (line 91).

#### `realdata/adapters/edgelist.py`

547 lines; SHA-256 prefix `539ccbba637cf722`.

Project dependencies: `from .base import PreparedDataset, TEMPORAL_EVALUATION, SELECTION_FRACTION, aggregateGraph, checkMode, fixedPartitionWithReport, retentionSummary, selectionWindowSummary, temporalSplit, _modularityReport, _partitionFromGraph`; `from ..download import download, fileDigest`.

- `readEdgeList(config)` (line 223).
- `readLabels(config)` (line 256).
- `selectNodes(config, events)` (line 269).
- `buildSnapshots(events, keep, windowDays, start=None)` (line 317).
- `makeLabels(config, windowIds, start, dayOffset=0.0)` (line 356).
- `prepare(name, mode=TEMPORAL_EVALUATION, selectionFraction=SELECTION_FRACTION, nCommunities=2)` (line 375).

#### `realdata/adapters/tgbl_wiki.py`

249 lines; SHA-256 prefix `a15aafb6a653277a`.

Project dependencies: `from .base import PreparedDataset, TEMPORAL_EVALUATION, SELECTION_FRACTION, aggregateGraph, checkMode, projectCoActivity, retentionSummary, selectionWindowSummary, temporalSplit, _partitionFromGraph`; `from ..download import download, fileDigest`.

- `readEvents(path)` (line 72).
- `prepare(topItems=100, windowDays=2, mode=TEMPORAL_EVALUATION, selectionFraction=SELECTION_FRACTION, nCommunities=2)` (line 99).

#### `realdata/compare_datasets.py`

456 lines; SHA-256 prefix `4fe43aaea6b89c2f`.

Project dependencies: `from .adapters.base import ANALYSIS_MODES, TEMPORAL_EVALUATION`.

- `loadAll(root)` (line 82).
- `buildTable(datasets)` (line 122).
- `figureSaturationVersusStatus(datasets, path)` (line 186).
- `figureNoopVersusBridgeWidth(table, path)` (line 207).
- `figureImpactHeatmap(datasets, path)` (line 231).
- `observations(table, datasets)` (line 281).
- `runMode(mode)` (line 357).
- `main(argv=None)` (line 440).

#### `realdata/download.py`

153 lines; SHA-256 prefix `06b2cf676e819741`.

- `download(name, force=False)` (line 106).
- `fileDigest(path, limit=1 << 20)` (line 130).
- `downloadAll()` (line 140).

#### `realdata/make_publication.py`

1856 lines; SHA-256 prefix `679dc90a91be2a18`.

Project dependencies: `from core import BridgeWidthMetric, BridgeWidthTransformation, PersistenceTemporalModel, bridgeMatrix, edgeAttribution, edgeTimeAttribution, graphDifference, localExplanation, makeNCommunityTemporalGraph, nodeAttribution, temporalAttribution, writeElementAttribution`; `from realdata.plotting import POSITIVE, NEGATIVE, NEUTRAL, savePublicationFigure, usePublicationTheme`; `from realdata.run_tgn_stability import comparabilityOf`.

- `_load(dataset)` (line 77).
- `_valid(frame)` (line 88).
- `figure1ConceptImpacts(datasets, path)` (line 94).
- `figure2ModelConceptHeatmap(datasets, path)` (line 118).
- `figure3BridgeMatrix(path)` (line 155).
- `figure4LocalGraph(path)` (line 198).
- `figure5TemporalLocal(path)` (line 258).
- `figure6ImpactDistribution(path)` (line 298).
- `semanticGroups()` (line 362).
- `_meanAbsImpact(frame, concepts)` (line 404).
- `_dotPanel(ax, rows, colour)` (line 418).
- `figure1ACommensurable(datasets, path)` (line 448).
- `figure1BGrouped(datasets, path)` (line 480).
- `figure2CGroupedSemanticHeatmap(datasets, path)` (line 517).
- `semanticRows()` (line 622).
- `_stripPanel(ax, frame, concepts, xLabel)` (line 640).
- `figure1FinalModelSeparated(datasets, path)` (line 682).
- `_attributionWorld()` (line 809).
- `buildAttributionData(directory=ATTRIBUTION)` (line 821).
- `figure8Dependence(paths, path)` (line 897).
- `_beeswarmOffsets(values, pointWidth)` (line 961).
- `figure9TrueBeeswarm(datasets, path)` (line 997).
- `figure10PublicationBoxplot(datasets, path)` (line 1078).
- `figure11LocalBar(paths, path, topK=LOCAL_BAR_TOP_K, source='edge_trend')` (line 1170).
- `figure12TemporalEdgeTime(paths, path, topK=EDGE_TIME_TOP_K)` (line 1225).
- `_writeSupersededNotice(path)` (line 1322).
- `writeFigureMetadata(path)` (line 1329).
- `_asMarkdown(frame)` (line 1537).
- `writeTables(datasets)` (line 1562).
- `tgnTables()` (line 1662).
- `figureTgnSeedStability(path)` (line 1714).
- `main()` (line 1757).

#### `realdata/plotting.py`

214 lines; SHA-256 prefix `4af9e2a1aa9985de`.

- `usePublicationTheme()` (line 57).
- `useDiagnosticTheme()` (line 62).
- `savePublicationFigure(fig, path, formats=('png', VECTOR_FORMAT))` (line 66).
- `_box(ax, x, y, width, height, label, facecolor, fontsize=8.5, bold=False, textcolor='black')` (line 100).
- `_arrow(ax, x1, y1, x2, y2, style='-|>', colour='#333333', width=1.2)` (line 110).
- `architectureFigure(path)` (line 117).

#### `realdata/run_ncommunity.py`

219 lines; SHA-256 prefix `9788489d1c7420fc`.

Project dependencies: `from core import BridgeWidthMetric, BridgeWidthTransformation, CallCountingModel, PersistenceTemporalModel, TgapExplainer, TrendTemporalModel, bridgeMatrix`; `from .adapters import edgelist`; `from .run_real_data import DELTAS, SEED, writeJson`.

- `runOne(dataset, nCommunities)` (line 49).
- `selectivity(rows, partition_pairs)` (line 146).
- `runDataset(dataset, counts=COMMUNITY_COUNTS)` (line 169).
- `main(argv=None)` (line 206).

#### `realdata/run_real_data.py`

1151 lines; SHA-256 prefix `513a1b399f4acb65`.

Project dependencies: `from core import TgapExplainer, PersistenceTemporalModel, TrendTemporalModel, SlopeModel, BridgeWidthMetric, DegreeCentralizationMetric, DensityMetric, ClusteringMetric, BridgeWidthTransformation, CentralizationTransformation, DensityTransformation, BridgeTrendTransformation, ChurnTransformation, CallCountingModel, leakageReport, InfeasibleTransformation, edgeCountFeasibility, bridgeTrendDirection, declaresEdgeCountPreservation`; `from .adapters import summariseSnapshots`; `from .adapters import decentraland, edgelist, tgbl_wiki`; `from .adapters.base import ANALYSIS_MODES, DESCRIPTIVE, SELECTION_FRACTION, TEMPORAL_EVALUATION`.

- `writeJson(obj, path)` (line 150).
- `buildTransformations(communities, strict=False)` (line 155).
- `signedDeltas(deltas)` (line 184).
- `metricTrajectories(prepared)` (line 189).
- `screenFeasibility(prepared, transformations, strictTransformations, deltas)` (line 208).
- `screenBridgeTrend(prepared, transformations, deltas)` (line 265).
- `rowValidity(transformationName, delta, feasibilityFlags, trendStatuses)` (line 288).
- `explainOneModel(prepared, modelName, model, transformations, deltas, feasibilityFlags, trendStatuses)` (line 329).
- `isTemporal(transformation)` (line 384).
- `transformationDiagnostics(prepared, transformations, deltas)` (line 398).
- `_formatImpact(value)` (line 478).
- `explanationMatrix(resultFrame, delta, direction='increase')` (line 495).
- `figureExplanationHeatmap(name, mode, resultFrame, path, delta, direction='increase')` (line 509).
- `figureValidityMap(name, mode, resultFrame, path)` (line 563).
- `writeReport(prepared, summary, resultFrame, trendFrame, feasibilityFrame, path, delta)` (line 616).
- `makeFigures(prepared, summary, metricFrame, resultFrame, figureDir)` (line 744).
- `runDataset(key, mode, nCommunities=2)` (line 839).
- `main(argv=None)` (line 1092).

#### `realdata/run_tgn.py`

281 lines; SHA-256 prefix `2e749ed8ab9ae359`.

Project dependencies: `from core import BridgeTrendTransformation, BridgeWidthTransformation, CallCountingModel, CentralizationTransformation, ChurnTransformation, DensityTransformation`; `from core.TemporalGraphExplainer import TgapExplainer`; `from core.TgnModel import TORCH_AVAILABLE, buildTgn, evaluateTgn, requireTorch, splitTemporally, trainTgn`; `from .run_real_data import ADAPTERS, DELTAS, SEED, rowValidity, screenBridgeTrend, screenFeasibility, buildTransformations as buildGatedTransformations, writeJson`; `from .adapters.base import TEMPORAL_EVALUATION`.

- `buildTransformations(communities)` (line 57).
- `runDataset(key, mode=TEMPORAL_EVALUATION, epochs=EPOCHS)` (line 69).
- `main(argv=None)` (line 262).

#### `realdata/run_tgn_stability.py`

418 lines; SHA-256 prefix `e13cea65596b37e5`.

Project dependencies: `from core import CallCountingModel, TgapExplainer`; `from core.TgnModel import TORCH_AVAILABLE, buildTgn, evaluateTgn, requireTorch, splitTemporally, trainTgn`; `from paper_evaluation import MATCH_TOLERANCE, bestMatch, sweepConcept`; `from .adapters.base import TEMPORAL_EVALUATION`; `from .run_real_data import ADAPTERS, DELTAS, rowValidity, screenBridgeTrend, screenFeasibility, writeJson, buildTransformations as buildGated`; `from .run_tgn import EPOCHS, TRAIN_FRACTION, buildTransformations`.

- `runOneSeed(prepared, seed, epochs=EPOCHS)` (line 72).
- `summarise(values, name)` (line 126).
- `comparabilityOf(first, second)` (line 150).
- `matchedComparison(model, snapshots, transformations, seed)` (line 181).
- `perConceptStability(rows, minSeeds=2)` (line 240).
- `main(argv=None)` (line 303).

#### `tests/__init__.py`

13 lines; SHA-256 prefix `43c8897744d11c18`.


#### `tests/test_attribution_persistence.py`

223 lines; SHA-256 prefix `7849725d5842defa`.

Project dependencies: `from core import BridgeTrendTransformation, BridgeWidthMetric, BridgeWidthTransformation, ELEMENT_ATTRIBUTION_COLUMNS, PersistenceTemporalModel, TEMPORAL_ATTRIBUTION_COLUMNS, TrendTemporalModel, edgeAttribution, edgeTimeAttribution, makeTemporalGraph, temporalAttribution, writeElementAttribution, writeTemporalAttribution`.

- `readCsv(path)` (line 33).
- `AttributionFixture` (line 41): fixture/helper class.
- `TestElementAttributionPersistence` (line 54): `testSchemaIsFixedAndOrdered`, `testProvenanceSurvivesTheRoundTrip`, `testImpactIsPreservedExactly`, `testNoGraphObjectsArePersisted`.
- `TestTemporalAttributionPersistence` (line 107): `testSchemaAndRequiredFields`, `testAttributionLevelIsRecorded`.
- `TestEdgeTimeAttribution` (line 139): `testPerturbsOneEdgeInOneSnapshot`, `testPresentOnlyModelRespondsOnlyAtTheLastSnapshot`, `testTrajectoryModelRespondsAcrossTime`, `testAllZeroIsReportedNotHidden`, `testDistinctFromSnapshotConceptAttribution`.
- `TestBridgeTrendDeltaGuard` (line 189): `testDeltaMinusOneRaisesAClearError`, `testNotAZeroDivisionError`, `testNeighbouringDeltasStillWork`.

#### `tests/test_communities.py`

344 lines; SHA-256 prefix `5f1f192beffe00d9`.

Project dependencies: `from core import BridgeTrendTransformation, BridgeWidthTransformation, BridgeWidthMetric, CentralizationTransformation, ChurnTransformation, DensityTransformation, PersistenceTemporalModel, TgapExplainer, detectTwoCommunities`; `from core.Communities import Partition, aggregateBridgeWidth, asPartition, bridgeMatrix, detectCommunities, interCommunityEdges, intraCommunityEdges`; `from core.Transformations import setBridgeWidth`.

- `threeCommunityGraph()` (line 37).
- `TestPartition` (line 63): `testOneCommunityIsValid`, `testLookupsBothDirections`, `testSameCommunity`, `testPairsAreOrderedAndComplete`, `testOverlappingCommunitiesRejected`, `testEmptyPartitionRejected`, `testAsPartitionAcceptsEveryHistoricalForm`.
- `TestBridgeStructure` (line 116): `testBridgeMatrixMatchesHandCount`, `testEveryPairIsPresentEvenWhenZero`, `testAggregateIsTheSumOverPairs`, `testPairwiseEdgeSelection`, `testIntraEdgesPerCommunity`, `testMetricSupportsAggregateAndPair`, `testZeroBridge`.
- `TestTwoCommunityBackwardCompatibility` (line 172): `testTupleUnpackingStillWorks`, `testDetectTwoCommunitiesStillReturnsExactlyTwo`, `testAggregateEqualsLegacyBridgeWidth`, `testPairZeroOneIsIdenticalToAggregateAtTwoCommunities`, `testSetBridgeWidthIdenticalWithAndWithoutPair`, `testTransformationIdenticalWithAndWithoutPair`.
- `TestTransformationsWithThreeCommunities` (line 244): `testBridgeWidthTargetsOnlyTheNamedPair`, `testPairedTransformationIsNamedAfterItsPair`, `testEveryTransformationAcceptsThreeCommunities`, `testChurnAndDensityRespectThreeCommunityBoundaries`, `testExplainerRunsOnThreeCommunities`.
- `TestDetectCommunities` (line 310): `testNaturalNumberOfCommunities`, `testExplicitNMergesDown`, `testDetectionIsDeterministic`, `testRejectsNonPositiveN`.

#### `tests/test_custom_transformation.py`

255 lines; SHA-256 prefix `93fdf8da75426130`.

Project dependencies: `from core import BridgeWidthMetric, GraphExplainer, PersistenceTemporalModel, TemporalGraphTransformation, TgapExplainer, TrendTemporalModel`; `from core.GraphExplainer import ExplainerBase`; `from core.GraphMetric import DensityMetric`.

- `TriangleCountTransformation` (line 32): fixture/helper class.
- `sampleTemporalGraph()` (line 66).
- `TestCustomTransformationIsAccepted` (line 83): `testExplainerAcceptsATransformationDefinedInThisFile`, `testCustomAndBuiltInTransformationsMixFreely`, `testCustomTransformationGetsFullProvenance`, `testModelCallBudgetIsUnchangedByCustomTransformations`, `testStaticExplainerAlsoAcceptsCustomTransformations`, `testDeterministic`, `testTransformationNeverMutatesTheInput`.
- `TestExplainerHasNoTransformationSpecialCasing` (line 158): `testExplainerSourceNamesNoConcreteTransformation`, `testExplainerUsesOnlyTheDocumentedContract`.
- `TestShippedExample` (line 195): `testExampleRunsEndToEnd`, `testIsolationMeasuresWhatItClaims`, `testIsolationDeclaresItDoesNotPreserveEdgeCount`, `testIsolationMovesItsOwnPropertyInBothDirections`, `testIsolationCannotGrowFromZero`.

#### `tests/test_explainer.py`

198 lines; SHA-256 prefix `9c1b438b5e18b722`.

Project dependencies: `from core import TgapExplainer, PersistenceTemporalModel, TrendTemporalModel, WeightedMetricModel, SlopeModel, BridgeWidthMetric, DegreeCentralizationMetric, BridgeWidthTransformation, CentralizationTransformation, BridgeTrendTransformation, ChurnTransformation, CallCountingModel, makeTemporalGraph, makeScenario`.

- `ExplainerTestCase` (line 19): fixture/helper class.
- `TestNormalization` (line 29): `testAchievedIsTrueSensitivity`, `testRequestedModeMatchesTsapFormula`, `testNoopReportedHonestly`, `testProvenanceFields`.
- `TestEfficiency` (line 69): `testExplainCostsOnePlusTwoK`, `testBoxplotBaselineNotRecomputed`.
- `TestStability` (line 92): `testDeterministicStability`.
- `TestFaithfulnessKnownTruth` (line 106): `testLinearModelRecoverySingleConcept`, `testLinearModelTwoConcepts`, `testSlopeModelReadsOnlyTrajectory`, `testPersistenceBlindToHistory`.
- `TestScenariosAndDefaults` (line 163): `testAllScenariosBuild`, `testScenarioTrendGroundTruth`, `testLazyDefaultsAreLeakFree`.

#### `tests/test_feasibility.py`

358 lines; SHA-256 prefix `eafffee41f5281b8`.

Project dependencies: `from core import BridgeTrendTransformation, BridgeWidthTransformation, CentralizationTransformation, ChurnTransformation, DensityTransformation, InfeasibleTransformation, bridgeTrendDirection, bridgeWidthFeasibility, declaresEdgeCountPreservation, edgeCountFeasibility`; `from core.Communities import interCommunityEdges, intraCommunityEdges`; `from core.Transformations import setBridgeWidth`.

- `feasibleGraph()` (line 37).
- `infeasibleGraph()` (line 58).
- `TestContractAttribute` (line 76): `testEveryTransformationDeclaresItsPromise`.
- `TestBridgeWidthFeasibleCase` (line 96): `testHandCountedPoolsMatchTheInspection`, `testEdgeCountIsPreservedWhenFeasible`, `testNarrowingIsInfeasibleWhenBothSidesAreComplete`, `testStrictModeAgreesAndDoesNotRaise`, `testTransformationReportsFeasibleOnATemporalGraph`.
- `TestBridgeWidthInfeasibleCase` (line 158): `testHandCountedShortfall`, `testPermissiveModeSilentlyChangesTheEdgeCount`, `testStrictModeRaisesWithMeasuredDetail`, `testTransformationReportsInfeasibleOnATemporalGraph`, `testDensityIsNeverReportedAsViolating`.
- `trendSnapshots(widths, sideSize=6)` (line 218).
- `TestBridgeTrendSaturation` (line 239): `testShortHistoryIsNotSaturated`, `testLongHistorySaturatesAtTheFloor`, `testIncreaseAndDecreaseAreBothMeasured`, `testLastSnapshotIsAlwaysTheAnchor`, `testStatusIsOkWhenNothingClamps`.
- `_FixedTrend` (line 296): fixture/helper class.
- `TestBridgeTrendWrongDirection` (line 316): `testWrongDirectionIsDetected`, `testWrongDirectionTheOtherWayRound`, `testAnUnmovedTrendIsItsOwnStatus`, `testCorrectDirectionWithoutClampingIsValid`.

#### `tests/test_local_explanation.py`

226 lines; SHA-256 prefix `f06bb0b8f4074117`.

Project dependencies: `from core import BridgeWidthMetric, BridgeWidthTransformation, CallCountingModel, ChurnTransformation, DensityTransformation, PersistenceTemporalModel, SlopeModel, edgeAttribution, graphDifference, localExplanation, makeNCommunityTemporalGraph, nodeAttribution, temporalAttribution`.

- `TestGraphDifference` (line 24): `testAddedRemovedKept`, `testAffectedNodesAreEndpointsOfChangedEdges`, `testIdenticalGraphsHaveNoDifference`, `testEdgeOrientationIsCanonical`.
- `TestLocalExplanation` (line 52): `testCarriesTheFullSchema`, `testAffectedElementsAreReal`, `testAchievedDeltaAgreesWithTheExplainer`, `testBridgeMatrixBeforeAndAfterIsRecorded`, `testWorksWithoutAModel`, `testTemporalTransformationLeavesTheLastSnapshotAlone`.
- `TestElementAttribution` (line 129): `testEveryEdgeScoreIsAMeasuredPredictionDifference`, `testRemovingABridgeEdgeLowersABridgeReadingModel`, `testCoverageIsReportedWhenTruncated`, `testBudgetCapsModelCalls`, `testSamplingIsDeterministic`, `testNodeAttributionKeepsTheNodeSet`, `testTemporalAttributionIsolatesOneSnapshot`, `testTemporalAttributionRefusesToClaimAdditivity`.

#### `tests/test_metrics.py`

61 lines; SHA-256 prefix `6bca596ab5a9c0bb`.

Project dependencies: `from core import DensityMetric, DegreeCentralizationMetric, BridgeWidthMetric, CohesionMetric, ClusteringMetric, makeTwoCommunityGraph`.

- `TestMetrics` (line 12): `testCentralizationStarIsOne`, `testCentralizationRingIsZero`, `testCentralizationTinyGraphIsZero`, `testDensityCompleteGraphIsOne`, `testBridgeWidthExact`, `testCohesionDisconnectedIsZero`, `testCohesionDeterministic`, `testCohesionSeesThinBridge`, `testClusteringTriangleIsOne`.

#### `tests/test_ncommunity_known_truth.py`

214 lines; SHA-256 prefix `4d57377b5e3bb68e`.

Project dependencies: `from core import BridgeWidthMetric, BridgeWidthTransformation, PersistenceTemporalModel, SlopeModel, TgapExplainer, TrendTemporalModel`; `from core.Communities import aggregateBridgeWidth, bridgeMatrix`; `from core.SyntheticData import makeNCommunityGraph, makeNCommunityTemporalGraph, makeTemporalGraph`.

- `TestGeneratorTruth` (line 33): `testExactBridgeWidthsPerPair`, `testAggregateIsTheSumOfTheTruth`, `testDefaultAppliesToUnnamedPairs`, `testDriftProducesAnExactSlope`, `testGeneratorIsDeterministic`, `testImpossibleBridgeIsRejected`, `testSingleCommunityHasNoBridges`.
- `TestTgapRecoversNCommunityTruth` (line 93): `testPersistenceModelRecoversItsOwnPairAndIsBlindToOthers`, `testEachPairIsRecoveredByItsOwnModel`, `testAggregateModelRespondsToEveryPair`, `testSlopeModelRecoversAKnownPairwiseTrend`, `testPairTransformationDoesNotDisturbOtherPairs`.
- `TestTwoCommunityStillMatchesLegacy` (line 184): `testLegacyGeneratorUnchangedAndConsistent`, `testTwoCommunityKnownTruthViaTheNGenerator`.

#### `tests/test_paper_evaluation.py`

519 lines; SHA-256 prefix `dacae3ed2578dab7`.

Project dependencies: `from core import TgapExplainer, WeightedMetricModel, PersistenceTemporalModel, SlopeModel, BridgeWidthMetric, DegreeCentralizationMetric, DensityMetric, ClusteringMetric, CohesionMetric, BridgeWidthTransformation, CentralizationTransformation, DensityTransformation, BridgeTrendTransformation, ChurnTransformation, leakageReport, makeTemporalGraph`; `import paper_evaluation as pe`.

- `setUpModule()` (line 56).
- `tearDownModule()` (line 64).
- `TestLeakageReportStructure` (line 73): `testReportCoversEveryPanelMetric`, `testChangeEqualsAfterMinusBefore`, `testIntendedPropertyActuallyMoves`, `testBridgePreservingTransformationsShowZeroBridgeChange`, `testUnconstrainedDensityLeakIsVisibleNotHidden`, `testLeakageIsReportedForTemporalPropertiesToo`.
- `TestDiscretenessFloor` (line 136): `testBelowThresholdIsNoop`, `testAboveThresholdMoves`, `testExplainerReportsNoopFlagBelowThreshold`, `testSmallerPropertyNeedsLargerDelta`.
- `TestAcrossGraphSizes` (line 182): `testPureBridgeRecoveryAtThreeSizes`, `testAnchorHoldsAtEverySize`.
- `TestEvaluationHelpers` (line 214): `testErrorFieldsSkippedForMeasuredKind`, `testErrorFieldsForExactKind`, `testZeroKindRequiresExactZero`, `testKnownTruthExpectationsAreDerivedFromTheWorld`, `testNonIsolatedPairsAreNotClaimedZero`, `testMeanMetricMatchesTransformationProperty`, `testNoCrossConceptRankingIsPresentedAsAnRq1Result`, `testComparableFlagRequiresMatchedAchievedChange`.
- `TestMatchedComparison` (line 308): `testDifferentDeltaModesNeverMatch`, `testMatchPicksClosestAchievedPair`, `testNoMatchIsForcedWhenGapExceedsTolerance`, `testIncomparablePairsAreReportedNotCompared`, `testSlopeModelReferenceHasNoComparableCounterpart`, `testMatchedComparisonIsReproducible`.
- `TestMatchedComparisonAcrossSeeds` (line 388): `testEveryRequestedSeedIsEvaluated`, `testEverySeedContributesTheSameNumberOfPairs`, `testPerSeedCountsAreInternallyConsistent`, `testPooledTotalsEqualTheSumOverSeeds`, `testNoForcedMatchesInAnySeed`, `testConsistencyFlagMatchesThePerSeedCounts`, `testMultiSeedRunIsDeterministic`, `testDifferentSeedsProduceDifferentWorlds`.
- `TestEvaluationHelpersContinued` (line 493): `testFaithfulnessIsReproducible`, `testOvershootRatioIsRecorded`.

#### `tests/test_publication_figures.py`

569 lines; SHA-256 prefix `ea6ed2e8a170b64a`.

Project dependencies: `from realdata import make_publication as M`.

- `_capture(function, directory, name, *arguments)` (line 34).
- `_offsets(fig)` (line 51).
- `_texts(fig)` (line 61).
- `PublicationCase` (line 66): fixture/helper class.
- `TestAttributionPersistence` (line 83): `testEveryFigureSourceExists`, `testElementSchemaIsTheLibrarySchema`, `testEdgeTimeHoldsEveryEdgeAtEverySnapshot`, `testProvenanceRecordsMethodAndSelection`.
- `TestDependence` (line 122): `testAxesUseRealPersistedColumnsNotFabricatedFeatures`, `testEveryPlottedPairExistsInTheSourceCsv`, `testNoElementIsLostToTheMarkerTally`, `testTitleIsNotAFeatureImportanceClaim`, `testReportsNAndCoverage`.
- `TestBeeswarmLayout` (line 177): `testNoTwoPointsOverlap`, `testIsDeterministic`, `testLayoutDoesNotDependOnInputOrder`, `testUsesNoRandomness`, `testEveryPointKeepsItsValue`.
- `TestBeeswarmFigure` (line 226): `testAllValidPointsArePreserved`, `testOnlyValidRowsAreDrawn`, `testShowsNAndZeroLine`, `testNoRankingLanguage`.
- `TestBoxplot` (line 258): `testOnlyValidRowsReachTheBoxes`, `testNIsShownForEveryBox`, `testModelSeparationIsPreserved`, `testNonCommensurableConceptsAreNotBoxedWithTheOthers`, `testNoPooledStatisticAcrossModels`.
- `TestLocalBar` (line 310): `testEveryBarTracesToPersistedAttribution`, `testZeroReferenceLineExists`, `testNoExactZeroIsDrawnAsABar`, `testTopKAndTheDiscardedCountAreStated`, `testFullAttributionRemainsAvailable`, `testSortIsByAbsoluteImpactWithDeterministicTieBreak`, `testBothSignsAreRepresentable`.
- `TestTemporalEdgeTime` (line 367): `testEveryPointIsARealEdgeTimeObservation`, `testImpactMappingIsCorrect`, `testPointCountMatchesTheSelectedRows`, `testNoAggregationInTheSource`, `testSelectionRuleIsStatedAndDeterministic`, `testTheTshapDisclaimerIsPresentVerbatim`, `testNoAdditivityIsClaimed`, `testSnapshotsWithResponseAreReported`.
- `TestSharedRequirements` (line 448): `testNoScientificNumberIsHardCoded`, `testAllFiguresProducePngAndPdf`, `testRepeatedGenerationIsReproducible`, `testAttributionDataIsReproducible`, `testFiguresUseTheSharedPublicationTheme`, `testPipelineGeneratesAllFive`, `testMetadataDocumentsAllFive`, `testMetadataIsReproducible`.

#### `tests/test_realdata.py`

901 lines; SHA-256 prefix `c1b91c48ca631795`.

Project dependencies: `from core import TgapExplainer, PersistenceTemporalModel, SlopeModel, BridgeWidthMetric, BridgeWidthTransformation, CentralizationTransformation, ChurnTransformation, BridgeTrendTransformation, DensityTransformation, CallCountingModel, edgeCountFeasibility`; `from core.Communities import interCommunityEdges`; `from realdata import download`; `from realdata.adapters import base, decentraland, edgelist, tgbl_wiki`; `from realdata.adapters.base import DESCRIPTIVE, SELECTION_FRACTION, TEMPORAL_EVALUATION, temporalSplit`.

- `cached(name)` (line 44).
- `TestDownloadModule` (line 51): `testEverySourceHasUrlAndFilename`, `testRejectedDatasetsAreDocumentedWithReasons`, `testDigestIsStableForTheSameFile`.
- `TestModeConstants` (line 73): `testModesAreDeclaredAndValidated`, `testSelectionFractionIsAFixedDocumentedConstant`, `testTemporalSplitIsDeterministicAndOrdered`.
- `TestTemporalNodeSelection` (line 96): `testFullPeriodRankingWouldLeakTheFuture`, `testSelectionPeriodRankingPicksOnlyEarlyActors`, `testChangingTheFutureCannotChangeTheSelection`, `testRankingIsDeterministicUnderReordering`.
- `TestTrainingPeriodCommunityDetection` (line 157): `testTemporalModeDetectsOnTheTrainingGraph`, `testDescriptiveModeDetectsOnTheFullPeriod`, `testTemporalModeRefusesToGuessWithoutATrainingPeriod`, `testEveryNodeGetsExactlyOneSideIncludingIsolatedOnes`.
- `TestRetentionSummary` (line 225): `testPercentagesAndDropsAreConsistent`, `testEmptyDatasetDoesNotDivideByZero`.
- `TestProjection` (line 245): `testSnapshotCountEqualsWindowCount`, `testEdgesAreTheCoActivityPairs`, `testNodeSetIsFixedAndIncludesInactiveActors`, `testActorsOutsideKeepSetAreDropped`, `testRepeatedInteractionsDoNotDuplicateEdges`, `testProjectionIsDeterministic`, `testPartitionCoversEveryNodeExactlyOnce`, `testSummaryNamesTheNodeColumnRetained`.
- `RealDatasetTestCase` (line 330): fixture/helper class.
- `TestDecentraland` (line 512): `testTgapCompatible`, `testMetadata`, `testRawAndRetained`, `testLeakageControl`, `testFilteringDocumented`, `testEdgeAttributesDeclaredUnused`, `testSnapshotsAreMonthlyAndOrdered`, `testBridgeWidthIsMeasurableAndNonTrivial`, `testTgapRuns`, `testExpectedInvarianceHolds`, `testEdgeCountInvariant`, `testDeterministic`.
- `TestTgblWiki` (line 570): `testTgapCompatible`, `testMetadata`, `testRawAndRetained`, `testLeakageControl`, `testFilteringDocumented`, `testEdgeAttributesDeclaredUnused`, `testHeaderIsValidated`, `testTgapRuns`, `testExpectedInvarianceHolds`, `testTrajectoryModelDoesReactToTrend`, `testEdgeCountInvariant`, `testDeterministic`.
- `TestEdgeListAdapterConfig` (line 633): `testEveryDatasetIsFullyDocumented`, `testBitcoinTimestampColumnIsThree`, `testBitcoinRatingIsDeclaredAvailableAndUnused`, `testCollegeMsgDuplicationIsRecorded`.
- `EdgeListDatasetMixin` (line 672): `testTgapCompatible`, `testMetadata`, `testRawAndRetained`, `testLeakageControl`, `testFilteringDocumented`, `testEdgeAttributesDeclaredUnused`, `testSelectionUsedOnlyTheSelectionPeriodEvents`, `testNoProjectionWasUsed`, `testNoSelfLoops`, `testSpanIsPlausible`, `testEvaluatedSpanIsShorterThanRawSpan`, `testTgapRuns`, `testExpectedInvarianceHolds`, `testEdgeCountInvariant`, `testDeterministic`.
- `TestEmailEuCore` (line 755): `testPartitionIsGroundTruthNotDetected`, `testMeasuredRawFacts`.
- `TestTgblEnron` (line 775): `testMeasuredRawFacts`.
- `TestTgblUci` (line 782): `testMeasuredRawFacts`.
- `TestSxMathoverflow` (line 789): `testMeasuredRawFacts`.
- `TestBitcoinOtc` (line 796): `testTimestampColumnGivesAMultiYearSpan`, `testMeasuredRawFacts`, `testWeightAndSignMetadataOnThePreparedDataset`.
- `TestBitcoinAlpha` (line 819): `testMeasuredRawFacts`.
- `TestAnalysisModesDiffer` (line 826): `testBothModesAreLabelled`, `testOnlyDescriptiveModeUsesFutureInformation`, `testCommunityModeFollowsTheAnalysisMode`, `testDescriptiveModeCoversTheWholeSpan`, `testTheTwoModesProduceDifferentGraphs`, `testRawFactsAreIdenticalInBothModes`.
- `TestDensityTransformationOnRealGraphs` (line 884): `testConfinedDensityPreservesBridgeWidth`.

#### `tests/test_registry.py`

311 lines; SHA-256 prefix `e2da799934a47d55`.

Project dependencies: `from core import TemporalGraphTransformation, makeTemporalGraph`; `from core.TransformationRegistry import buildAll, conceptNames, entries, get, names, register, unregister`.

- `DummyTransformation` (line 28): fixture/helper class.
- `TestBuiltinRegistrations` (line 46): `testAllFiveShippedConceptsAreRegistered`, `testCapabilityMetadataReplacesStringComparison`, `testEdgeCountCapabilityComesFromTheClass`, `testTemporalFlag`, `testBuildAllProducesWorkingInstances`, `testNoNameBasedSpecialCasing`.
- `TestCustomRegistration` (line 114): `testRegistrationAndDiscovery`, `testCapabilityInferredFromTheClass`, `testCustomTransformationReachesThePipeline`, `testBuiltinOnlyFiltersItOut`, `testExplainerExecutesIt`, `testResultsCanBePersisted`, `testDuplicateRegistrationIsRefusedUnlessDeliberate`.
- `TestPipelineUsesTheRegistry` (line 183): `testCompareDatasetsHasNoLiteralConceptList`, `testRunRealDataBuildsFromTheRegistry`, `testBuiltinPipelineStillProducesTheSameFiveNames`.
- `TestArchitectureFigure` (line 208): `testGeneratesPngAndVector`, `testSaveHelperHonoursRequestedFormats`, `testThemeIsShared`.
- `TestPerConceptStability` (line 243): `testInsufficientSeedsReportedNotManufactured`, `testSufficientSeedsAreSummarised`, `testInvalidRowsAreExcluded`, `testComparabilityFlagTravelsWithTheRow`, `testNoRankingColumnExists`.

#### `tests/test_semantic_figures.py`

709 lines; SHA-256 prefix `e6ebc844af8dd32b`.

Project dependencies: `from realdata import make_publication as M`.

- `_capture(function, datasets, directory, name)` (line 31).
- `_yLabels(ax)` (line 52).
- `_xLabels(ax)` (line 56).
- `_conceptOf(label)` (line 60).
- `FigureCase` (line 65): fixture/helper class.
- `TestSemanticGroups` (line 80): `testGroupingIsNotTakenFromTheStoredDeltaMode`, `testGroupsPartitionTheRegisteredConcepts`, `testGroupMembershipMatchesTheRq1bRule`.
- `TestCandidateA` (line 120): `testOnlyCommensurableConceptsAppear`, `testExcludedConceptsAppearNowhere`, `testTitleMakesNoImportanceClaim`.
- `TestCandidateB` (line 151): `testNoAxesMixesTheTwoGroups`, `testBothGroupsArePresent`, `testGroupsDoNotShareAnAxisRange`, `testCaptionStatesNonComparability`.
- `TestCandidateC` (line 197): `testConceptsAreInRegistryOrderNotImpactOrder`, `testColumnsAreNotSortedByRawImpact`, `testNoAxesMixesTheTwoGroups`, `testPrintedValuesAreRealImpactsNotNormalised`, `testNoSingleColourScaleSpansBothGroups`.
- `TestProvenanceAndReproducibility` (line 291): `testCandidateAValuesComeFromTheCsv`, `testNoScientificNumbersAreHardCoded`, `testConceptListsAreNotHardCoded`, `testPublicationDpiSurvivesAPipelineImport`, `testFiguresAreReproducible`.
- `TestFinalFigure` (line 414): `testNoAggregationAcrossModels`, `testPanelPointCountsMatchThePerModelRowCounts`, `testEveryModelIsRepresented`, `testCommensurableConceptsShareAPanel`, `testNonCommensurableConceptsNeverJoinThatPanel`, `testCentralizationAndBridgeTrendAreNotInTheSameRow`, `testEachModelPanelHasItsOwnAxis`, `testInsufficientCellsAreLabelledNotPlottedAsZero`, `testEveryPlottedPointIsARealValidImpact`, `testNoGlobalRankingLanguage`.
- `TestFinalFigureOutputs` (line 555): `testPngAndPdfAreBothProducedAndReproducible`, `testNoScientificNumberIsHardCoded`, `testNoConceptOrModelNameIsHardCoded`, `testThePipelineUsesTheFinalFigureAsTheMainOne`, `testSupersededFiguresAreNotInThePublicationRoot`.
- `TestMetadata` (line 650): `testFileIsValidJsonOnDisk`, `testEveryCandidateIsDocumented`, `testComparabilityFlagsMatchTheFigures`, `testMetadataConceptsMatchSemanticGroups`, `testGenerationFunctionsResolve`, `testSourceCsvFilesExist`.

#### `tests/test_sparsity.py`

206 lines; SHA-256 prefix `249421a7c7ed6720`.

Project dependencies: `from core import BridgeWidthMetric, BridgeWidthTransformation, CentralizationTransformation, ChurnTransformation, DensityTransformation, PersistenceTemporalModel, TgapExplainer, TrendTemporalModel, edgeAttribution, makeTemporalGraph`; `from core.GraphMetric import DensityMetric`; `from core.Sparsity import conceptSparsity, elementSparsity, sparsityReport`.

- `TestConceptSparsityDefinition` (line 30): `testAllZeroMeansFullySparse`, `testNoZerosMeansFullyDense`, `testMixedCountsCorrectly`, `testDefaultIsThresholdFree`, `testThresholdIsHonouredAndRecorded`, `testNoopRowsLeaveTheDenominator`, `testInvalidRowsAreExcluded`, `testUndefinedRatherThanOneWhenNothingWasProbed`, `testEmptyInput`.
- `TestConceptSparsityOnRealExplanations` (line 107): `testTgapProducesExactZeros`, `testSelectiveModelGivesHighSparsity`, `testSparsityIsDeterministic`.
- `TestElementSparsity` (line 150): `testAcceptsAnAttributionDict`, `testPartialCoverageIsFlagged`, `testFullCoverageIsNotFlagged`.
- `TestSparsityReport` (line 181): `testBothLevelsReturnedSeparately`, `testElementLevelOmittedWhenNoAttributionGiven`.

#### `tests/test_tgn.py`

234 lines; SHA-256 prefix `22bdd7e9f70b10bd`.

Project dependencies: `from core import BridgeWidthTransformation, CallCountingModel, DensityTransformation, TgapExplainer, makeTemporalGraph`; `from core.TemporalGraphModel import TemporalGraphModel`; `from core.TgnModel import TORCH_AVAILABLE, buildTgn, requireTorch, trainTgn`.

- `TestTgnAdapter` (line 29): `testImplementsIvansContract`, `testPredictionIsAProbability`, `testPredictionIsDeterministic`, `testPredictionSurvivesInterleavedCalls`, `testTrainingReducesLoss`, `testTrainingIsReproducible`, `testEmptyInputDoesNotCrash`, `testTgapExplainsTheLearnedModel`, `testModelCallBudgetHoldsForTheLearnedModel`, `testTgapNeverTouchesModelInternals`.
- `TestTgnOptionalDependency` (line 121): `testRequireTorchMessageIsActionable`, `testCoreImportsWithoutTorch`.
- `TestHeldOutEvaluation` (line 143): `testSplitIsTemporalNotRandom`, `testSplitAlwaysLeavesSomethingToEvaluate`, `testMemoryDiffersAcrossNodes`, `testEvaluationReportsBalancedClassesAndChanceLevel`, `testEvaluationIsDeterministic`, `testAveragePrecisionAndAucOnKnownInput`.

#### `tests/test_tgn_stability.py`

206 lines; SHA-256 prefix `56d784f300844ea0`.

Project dependencies: `from core.TgnModel import TORCH_AVAILABLE`; `from realdata.run_tgn_stability import SEEDS, comparabilityOf`.

- `TestComparabilityRule` (line 27): `testRelativeConceptsAreComparableInPrinciple`, `testAbsoluteDeltaModeBlocksComparison`, `testCentralizationIsNeverComparable`, `testRuleIsSymmetric`, `testRuleReadsTransformationPropertiesNotNames`.
- `TestSeedStabilityOutputs` (line 93): `testFiveFixedSeedsWereUsed`, `testEverySeedIsRecordedInEveryRow`, `testSplitIsIdenticalAcrossSeeds`, `testPerSeedValuesAreReportedNotOnlySummarised`, `testSummaryStatisticsAreConsistent`, `testNoPoolingOrSignificanceClaimed`, `testNoRankingIsProduced`.
- `TestMatchedComparisonOutputs` (line 153): `testSchemaHasEveryRequiredField`, `testNotComparableIsALegitimateRecordedState`, `testIncomparablePairsCarryNoNumbers`, `testComparablePairsCarryBothSidesAndAMatchedDelta`, `testCentralizationAndBridgeTrendAreNeverCompared`, `testNoWinnerColumnExists`.

#### `tests/test_transformations.py`

303 lines; SHA-256 prefix `1a8810a3342ecd25`.

Project dependencies: `from core import BridgeWidthTransformation, CentralizationTransformation, DensityTransformation, BridgeTrendTransformation, ChurnTransformation, BridgeWidthMetric, DegreeCentralizationMetric, makeTwoCommunityGraph, makeTemporalGraph`; `from core.Communities import interCommunityEdges`.

- `edgeSet(g)` (line 20).
- `snapshotFingerprint(tg)` (line 25).
- `TransformationTestCase` (line 30): fixture/helper class.
- `TestBridgeWidthExact` (line 42): `testIncreaseTenPercent`, `testDecreaseTenPercent`, `testZeroDeltaIsIdentity`, `testTinyDeltaIsNoop`, `testLargeDeltaCappedByCandidates`, `testEdgeCountAndNodesPreserved`, `testNeverSeversLastBridge`, `testTinyGraph`, `testDisconnectedInputDoesNotCrash`.
- `TestCentralization` (line 108): `testConcentrateRaisesMetric`, `testRedistributeLowersMetric`, `testRedistributeLowersMetricUnderTiedMaxDegree`, `testBridgePreservedExactly`, `testAnchorNodeAndEdgeCount`.
- `TestDensity` (line 161): `testExactEdgeCountChange`, `testCommunitiesModePreservesBridge`, `testUnconstrainedModeLeaksIntoBridge`, `testCompleteGraphNoAddCandidates`.
- `TestBridgeTrend` (line 191): `testLastSnapshotByteIdentical`, `testTrajectoryDirection`, `testCompoundingMatchesTsapRecursion`, `testPerSnapshotAnchors`, `testStaticModeRaises`.
- `TestChurn` (line 227): `testLastSnapshotByteIdentical`, `testChurnPropertyMovesInDeltaDirection`, `testBridgePreservedInEverySnapshot`, `testEdgeCountPreservedInEverySnapshot`, `testSingleSnapshotPropertyUndefined`, `testStaticModeRaises`.
- `TestDeterminismAndMutation` (line 261): `testDeterminism`, `testInputNeverMutated`, `testDifferentSeedsDifferentChoices`.

#### `tests/test_validity_gating.py`

151 lines; SHA-256 prefix `6f5599a21a5f2639`.

- `available(path)` (line 35).
- `TestTgnValidityGating` (line 41): `testTgnRowsCarryEveryValidityField`, `testStatusVocabularyMatchesTheMainPipeline`, `testInfeasibleRowsCarryNoNumbers`, `testInvalidRowsArePreservedNotDeleted`, `testSummaryAgreesWithTheCsv`, `testNoRawCrossConceptRanking`, `testFeasibilityDiagnosticsArePersisted`.
- `TestInvalidRowsCannotEnterAggregates` (line 98): `testPublicationTableUsesValidRowsOnly`, `testEveryInvalidRowHasAReason`, `testValidRowsAreAllStatusOk`, `testInfeasibleCountIsReported`.

# Workbench and self-hosting addition (2026-10-07)

Latest continuation point: the opening handoff section of
`docs/13-sandbox-and-self-hosting-knowledge.md` records ALL subsequent user
requests and completed website changes, including larger fonts, actionable
onboarding, explicit/easy explanations, paper reference gallery, graph
relationships, and live publication-style charts generated per experiment.
Read that handoff before continuing; the user explicitly requested it as
the persistent history for the next conversation.

The current implementation adds the isolated-environment `tgap` CLI and a
private, independently hosted sibling web laboratory. Read
[deployment knowledge](docs/13-sandbox-and-self-hosting-knowledge.md) and
[installation guide](docs/12-installation-and-self-hosting.md) for the new
architecture, operations, user-study flow, security limits and packaging.
The original core and research workflow descriptions below still apply.

## Account and reliability update - 2026-10-08

Self-service registration/sign-in with local CAPTCHA and persistent throttling
now lives in the sibling website and refreshed portable bundle. New passwords
are hashed; protected manual researcher accounts remain supported. Numerical
and reliability audit details, fixes and evidence are in
[the audit report](docs/14-scientific-reliability-audit-2026-10-08.md) and the
latest handoff in [the workbench knowledge file](docs/13-sandbox-and-self-hosting-knowledge.md).
The web models are six transparent baselines; do not describe this audit as
validating all trained TGN models or real-world causal explanations.

## Research dashboard follow-up - 2026-10-08

The admin-only Researcher view now has consent-scoped charts, detailed records,
cohort filters and reproducible study ZIP exports. See
[the research dashboard guide](docs/15-research-dashboard.md) and the latest
workbench knowledge handoff. `sandbox/reporting.py` and `static/researcher.js`
live in the sibling web project and portable bundle. Study consent pilot-1.1
clarifies saved-result/code inspection and repeat-visit pseudonyms. Never insert
demonstration participant data into the live research database.
