'''
Run TGAP on the real datasets.

    python -m realdata.run_real_data                      # default mode, all 8
    python -m realdata.run_real_data --mode descriptive   # full-period mode
    python -m realdata.run_real_data --mode both          # both modes
    python -m realdata.run_real_data bitcoin_otc          # one dataset

Writes to output/real_data_v2/<analysis_mode>/<dataset>/:
    metadata.json                  dataset facts (measured, not assumed)
    preprocessing_summary.json     every preprocessing decision + what it dropped
    graph_summary.csv              per-snapshot statistics
    metrics.csv                    metric trajectories per snapshot
    tgap_results.csv               the TGAP explanations, with validity flags
    transformation_feasibility.csv the edge-count invariant, per setting
    bridge_trend_status.csv        saturation / direction status per setting
    transformation_diagnostics.csv how far each transformation reached
    leakage.csv                    unintended side effects on other concepts
    summary.json                   headline results
    figures/*.png

TWO ANALYSIS MODES (see adapters/base.py DECISION 4). Every output file and
every summary carries `analysis_mode`, so no number can be traced to the
wrong methodology:

    temporal_evaluation  DEFAULT for scientific evaluation. Actors and the
                         community partition are chosen using only the first
                         20% of the time span; TGAP explains snapshots built
                         from the remaining 80%. Selection and evaluation are
                         disjoint in time, so no future information reaches
                         the selection step.
    descriptive          Full-period selection and snapshots. Useful for
                         describing a dataset as a whole; NOT leakage-safe,
                         and labelled as such wherever it appears.

MODELS. We reuse the existing core models rather than writing new ones -
that is the point of the interface. Six are used per dataset so that every
transformation has at least one model able to respond to it, and so we can
ask whether TGAP separates a model that reads history from one that does not:

    PersistenceTemporalModel(metric)  reads ONLY the last snapshot
    TrendTemporalModel(metric)        fits a line over all snapshots
    SlopeModel(metric)                predicts the slope itself

TRANSFORMATIONS. All five core transformations are applied, each with the
fixed partition so the bridge-preserving guarantees are active. Cohesion is
NOT used as a prediction target: real snapshots include isolated inactive
actors, so they are disconnected and algebraic connectivity is 0 by
construction (documented in the adapters).

VALIDITY GATING. A row is only usable as an explanation result when the
transformation kept the invariant it promised. Two gates are applied, both
measured, never assumed:

 1. EDGE-COUNT FEASIBILITY. BridgeWidth and BridgeTrend pay for each new
    bridge edge by deleting an intra-community edge. On real snapshots the
    intra pool is sometimes too small to pay, so the total edge count would
    move - the perturbation would then mix "rerouted activity" with "more
    activity". Such settings are marked feasible=False with a reason, their
    numeric fields are left EMPTY, and they are excluded from every
    aggregate (core.Feasibility.edgeCountFeasibility).

 2. BRIDGE-TREND DIRECTION. The trend recursion divides backwards by
    (1 + delta), so old snapshots can be pushed below the width-1 floor;
    once enough of them clamp, the achieved trend can move AGAINST the
    request. Those settings get status "saturated" or "wrong_direction" and
    are excluded from aggregate conclusions
    (core.Feasibility.bridgeTrendDirection).

SCIENTIFIC CAUTION. These runs demonstrate that the pipeline handles real
temporal structure and produces interpretable sensitivities. They do NOT
validate TGAP's correctness: real data has no ground truth. Correctness
evidence lives in the synthetic known-truth experiments
(paper_evaluation.py). Nothing here is a causal claim.
'''

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import networkx as nx
import numpy as np
import pandas as pd

from core import (
    TgapExplainer,
    PersistenceTemporalModel, TrendTemporalModel, SlopeModel,
    BridgeWidthMetric, DegreeCentralizationMetric, DensityMetric,
    ClusteringMetric,
    BridgeWidthTransformation, CentralizationTransformation,
    DensityTransformation, BridgeTrendTransformation, ChurnTransformation,
    CallCountingModel, leakageReport,
    InfeasibleTransformation, edgeCountFeasibility, bridgeTrendDirection,
    declaresEdgeCountPreservation,
)
from .adapters import summariseSnapshots
from .adapters import decentraland, edgelist, tgbl_wiki
from .adapters.base import (ANALYSIS_MODES, DESCRIPTIVE, SELECTION_FRACTION,
                            TEMPORAL_EVALUATION)

# Versioned root. The pre-cleanup v1 results (full-period selection, no
# validity gating) used to sit beside these under output/real_data/; they
# were deleted rather than kept, because git history already holds them and
# two similar-looking result trees invite quoting the wrong one. Recover
# them with `git show 28df00c:output/real_data/<file>` if ever needed.
#
# Only the DEFAULT mode's results are committed. Descriptive-mode results
# are reproducible on demand with `--mode descriptive` and are deliberately
# not stored, so nobody can quote a leakage-unsafe number by accident.
OUTPUT_ROOT = os.path.join("output", "real_data_v2")
SEED = 42
DELTAS = (0.1, 0.25, 0.5)

# Two graph families, deliberately kept distinct so their results can be
# compared. BIPARTITE sources need a one-mode projection (edges are derived
# and much data is dropped); UNIPARTITE sources are observed actor-to-actor
# edges that need no projection at all.
BIPARTITE = {
    "tgbl_wiki": tgbl_wiki.prepare,
    "decentraland": decentraland.prepare,
}
UNIPARTITE = {name: (lambda mode, n=name: edgelist.prepare(n, mode=mode))
              for name in edgelist.DATASETS}
ADAPTERS = {**{k: (lambda mode, f=f: f(mode=mode))
               for k, f in BIPARTITE.items()},
            **UNIPARTITE}

# The invariance statement of item 6: what follows from the definitions, and
# what the run therefore VERIFIES rather than discovers.
INVARIANCE_STATEMENT = (
    "Expected by construction, then verified on this dataset: Bridge Trend "
    "and Churn return the last snapshot untouched (the TSAP anchor rule in "
    "the time dimension), and the persistence models read only the last "
    "snapshot, so their prediction change must be exactly 0. A zero here is "
    "therefore a VERIFICATION OF AN EXPECTED INVARIANT - a correctness check "
    "on the implementation and the pipeline - not an unexpected empirical "
    "discovery about the data.")

plt.rcParams.update({"figure.figsize": (7.0, 4.2), "font.size": 10,
                     "axes.grid": True, "grid.alpha": 0.3,
                     "savefig.dpi": 200, "savefig.bbox": "tight"})


def writeJson(obj, path):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(obj, handle, indent=2, default=str)


def buildTransformations(communities, strict=False):
    ''' All five concepts, each given the partition. Every one is
    structurally meaningful on these graphs:
      Bridge Width   ties between the two communities
      Centralization concentration of activity on one hub actor
      Density        overall volume of interaction
      Bridge Trend   whether cross-community ties grow or decay over time
      Churn          how much earlier snapshots differ from the present

    strict=True asks the two setBridgeWidth-based transformations to RAISE
    InfeasibleTransformation instead of silently under-paying when the
    edge-count invariant cannot be kept. The strict list is used only for
    the feasibility cross-check; the explanations themselves run on the
    permissive list, so gating never changes a number it keeps.
    '''
    return [
        BridgeWidthTransformation(communities, seed=SEED, strict=strict),
        CentralizationTransformation(communities, seed=SEED),
        DensityTransformation(communities, seed=SEED),
        BridgeTrendTransformation(communities, seed=SEED, strict=strict),
        ChurnTransformation(communities, seed=SEED),
    ]


def signedDeltas(deltas):
    ''' Every (delta, direction) setting the explainer will exercise. '''
    return [signed for delta in deltas for signed in (delta, -delta)]


def metricTrajectories(prepared):
    ''' The value of each usable metric in every snapshot. This is what the
    models read, so it is saved next to the explanations. '''
    metrics = {
        "bridge_width": BridgeWidthMetric(prepared.communities),
        "density": DensityMetric(),
        "centralization": DegreeCentralizationMetric(),
        "clustering": ClusteringMetric(),
    }
    rows = []
    for index, (graph, label) in enumerate(zip(prepared.snapshots,
                                               prepared.labels)):
        row = {"snapshot_index": index, "label": label}
        for name, metric in metrics.items():
            row[name] = float(metric.measure(graph))
        rows.append(row)
    return pd.DataFrame(rows), metrics


def screenFeasibility(prepared, transformations, strictTransformations,
                      deltas):
    ''' Decide, for every (transformation, signed delta) setting, whether
    the transformation can keep the invariant it declares.

    Two independent checks are run and compared, because agreement between
    them is what makes the gate trustworthy:

      measurement  the permissive transformation is run and edge counts are
                   compared snapshot by snapshot.
      strict       the same transformation built with strict=True either
                   completes or raises InfeasibleTransformation at the exact
                   point where the payment could not be made.

    Both live in core.Feasibility.edgeCountFeasibility. Neither makes a
    model call, so TGAP's 1 + 2K model-call budget is untouched. Returns
    (flags, frame) where flags is keyed by (transformationName, signedDelta).
    '''
    flags, rows = {}, []
    for transformation, strictVersion in zip(transformations,
                                             strictTransformations):
        declares = declaresEdgeCountPreservation(transformation)
        for delta in signedDeltas(deltas):
            report = edgeCountFeasibility(
                prepared.snapshots, transformation, delta,
                prepared.communities, strictTransformation=strictVersion)
            strictRaised = bool(report["strict_raised"])
            strictReason = report["strict_reason"]
            status = "ok" if report["feasible"] else "edge_count_infeasible"
            record = {
                "dataset": prepared.name,
                "analysis_mode": prepared.meta["analysis_mode"],
                "transformation": transformation.name,
                "requested_delta": delta,
                "declares_edge_count_preservation": declares,
                "feasible": report["feasible"],
                "infeasible_reason": report["reason"],
                "edge_count_before": report["edge_count_before"],
                "edge_count_after": report["edge_count_after"],
                "edge_count_preserved": (report["edge_count_before"]
                                         == report["edge_count_after"]),
                "snapshots_checked": report["snapshots_checked"],
                "snapshots_violating": report["snapshots_violating"],
                # Cross-check: does core's explicit-failure path agree with
                # the measurement? A mismatch would mean the gate is
                # unreliable, so it is recorded rather than assumed.
                "strict_mode_raises": strictRaised,
                "strict_mode_reason": strictReason,
                "strict_agrees_with_measurement": bool(
                    strictRaised == (report["snapshots_violating"] > 0)),
                "transformation_status": status,
            }
            flags[(transformation.name, delta)] = record
            rows.append(record)
    return flags, pd.DataFrame(rows)


def screenBridgeTrend(prepared, transformations, deltas):
    ''' Saturation and direction status for BridgeTrendTransformation, the
    one transformation with a known long-history failure mode.

    Returns (statusByDelta, frame). See
    core.Feasibility.bridgeTrendDirection for the mechanism and the four
    possible statuses.
    '''
    trend = next((t for t in transformations
                  if isinstance(t, BridgeTrendTransformation)), None)
    if trend is None:
        return {}, pd.DataFrame()
    statuses, rows = {}, []
    for delta in signedDeltas(deltas):
        record = bridgeTrendDirection(prepared.snapshots, trend, delta)
        record = {"dataset": prepared.name,
                  "analysis_mode": prepared.meta["analysis_mode"],
                  "transformation": trend.name, **record}
        statuses[delta] = record
        rows.append(record)
    return statuses, pd.DataFrame(rows)


def rowValidity(transformationName, delta, feasibilityFlags, trendStatuses):
    ''' Combine both gates into the flags that every explanation row
    carries. Order matters: a broken edge-count invariant is the more
    fundamental failure, so it wins over a trend-shape failure.

    Returns (fields, blankNumbers). blankNumbers is True when the row's
    numeric results must not be written at all, because the perturbation
    was not a counterfactual of the declared concept. A saturated or
    wrong-direction trend DID keep its edge budget, so its numbers are kept
    for inspection but flagged invalid for analysis.
    '''
    flag = feasibilityFlags.get((transformationName, delta), {})
    feasible = flag.get("feasible", True)
    reason = flag.get("infeasible_reason")
    status = "ok" if feasible else "edge_count_infeasible"

    trend = trendStatuses.get(delta) if transformationName == "Bridge Trend" \
        else None
    if feasible and trend is not None and trend["status"] != "ok":
        status = trend["status"]
        reason = {
            "saturated": "bridge widths clamped to the width-1 floor, so the "
                         "intended trend shape was not realised",
            "wrong_direction": "achieved trend moved against the requested "
                               "direction (clamp saturation)",
            "no_property_change": "the trend did not move at all",
        }.get(trend["status"])

    fields = {
        "feasible": feasible,
        "infeasible_reason": reason,
        "edge_count_before": flag.get("edge_count_before"),
        "edge_count_after": flag.get("edge_count_after"),
        "edge_count_preserved": flag.get("edge_count_preserved"),
        "snapshots_violating_edge_count": flag.get("snapshots_violating"),
        "transformation_status": status,
        "valid_for_analysis": bool(feasible and status == "ok"),
    }
    return fields, not feasible


def explainOneModel(prepared, modelName, model, transformations, deltas,
                    feasibilityFlags, trendStatuses):
    ''' Run TGAP for one model across several deltas and both directions,
    returning one row per (transformation, direction, delta) with the full
    provenance TGAP reports plus the validity flags.

    The explainer is still called once per delta with all transformations,
    so the documented model-call budget of 1 + 2K per call is unchanged.
    Rows whose edge-count invariant failed have their numeric fields left
    EMPTY: the number exists in memory but writing it would invite its use.
    '''
    rows = []
    for delta in deltas:
        explainer = TgapExplainer(model, transformations, defaultDelta=delta)
        for record in explainer.explainDetailed(prepared.snapshots):
            signed = record["requestedDelta"]
            flags, blank = rowValidity(record["transformation"], signed,
                                       feasibilityFlags, trendStatuses)
            row = {
                "dataset": prepared.name,
                "analysis_mode": prepared.meta["analysis_mode"],
                "snapshot_count": len(prepared.snapshots),
                "model": modelName,
                "transformation": record["transformation"],
                "direction": "increase" if signed > 0 else "decrease",
                "requested_delta": signed,
                "delta_mode": record["deltaMode"],
                "seed": SEED,
                **flags,
            }
            if blank:
                row.update({
                    "achieved_delta": None,
                    "baseline_prediction": None,
                    "after_prediction": None,
                    "prediction_change": None,
                    "impact": None,
                    "normalizer": None,
                    "noop": None,
                })
            else:
                row.update({
                    "achieved_delta": record["achievedDelta"],
                    "baseline_prediction": record["baseline"],
                    "after_prediction": record["transformed"],
                    "prediction_change": (record["transformed"]
                                          - record["baseline"]),
                    "impact": record["impact"],
                    "normalizer": record["normalizer"],
                    "noop": record["noop"],
                })
            rows.append(row)
    return rows


def isTemporal(transformation):
    ''' True for transformations that reshape the trajectory rather than a
    single snapshot. They are identified by their own contract: a temporal
    transformation refuses transformGraph, because changing "the trend of
    one snapshot" is meaningless. No name matching, no new flag in core. '''
    probe = nx.Graph()
    probe.add_edges_from([(0, 1), (1, 2)])
    try:
        transformation.transformGraph(probe, 0.0)
        return False
    except NotImplementedError:
        return True


def transformationDiagnostics(prepared, transformations, deltas):
    ''' Per-transformation reach on real graphs: in how many snapshots did
    the transformation actually move its own property?

    Two real-data effects make this necessary, and both were observed:

    1. A transformation can be BLOCKED by the graph's own structure. The
       centralization rewiring needs the hub not to be connected to the
       node it steals a tie from; on a dense snapshot almost every candidate
       is blocked, so the property does not move there.

    2. propertyValue averages over snapshots, while a persistence model
       reads only the LAST snapshot. So the achieved delta can be non-zero
       (the mean moved) while the prediction change is zero (the last
       snapshot did not move). Such a row is legitimately not a no-op, but
       for that particular model nothing was tested. Recording per-snapshot
       reach makes the situation visible instead of leaving a bare 0.0.

    The edge-count column reads each transformation's own
    preservesEdgeCount contract, so DensityTransformation - whose property
    IS the edge count - is never counted as violating anything.
    '''
    rows = []
    for transformation in transformations:
        claimsPreservation = declaresEdgeCountPreservation(transformation)
        temporal = isTemporal(transformation)
        for signedDelta in signedDeltas(deltas):
            transformed = transformation.transform(prepared.snapshots,
                                                   signedDelta)
            changed = sum(
                1 for before, after in zip(prepared.snapshots, transformed)
                if set(map(frozenset, before.edges()))
                != set(map(frozenset, after.edges())))
            lastChanged = (
                set(map(frozenset, prepared.snapshots[-1].edges()))
                != set(map(frozenset, transformed[-1].edges())))
            anchorBreaks = sum(
                1 for before, after in zip(prepared.snapshots, transformed)
                if before.number_of_edges() != after.number_of_edges()
            ) if claimsPreservation else 0
            rows.append({
                "dataset": prepared.name,
                "analysis_mode": prepared.meta["analysis_mode"],
                "transformation": transformation.name,
                "family": "temporal" if temporal else "structural",
                "claims_edge_count_preservation": claimsPreservation,
                "snapshots_edge_count_changed": anchorBreaks,
                "requested_delta": signedDelta,
                "snapshots": len(prepared.snapshots),
                "snapshots_modified": changed,
                "modified_fraction": changed / len(prepared.snapshots),
                "last_snapshot_modified": bool(lastChanged),
                # Temporal transformations anchor the last snapshot ON
                # PURPOSE, so leaving it unchanged is correct for them.
                # For a structural transformation the same observation
                # means the graph BLOCKED it.
                "structurally_blocked": bool(not lastChanged and not temporal),
            })
    return pd.DataFrame(rows)




##  Readable views of tgap_results.csv  ##
#
# tgap_results.csv is the important output, but 180 rows of numbers is not
# something anyone reads. The three views below answer the three questions
# people actually ask of it.
#
# THE SCALE PROBLEM, and why a bar chart cannot solve it. Impacts legitimately
# span orders of magnitude in the same dataset - a model reading bridge width
# reacts to a bridge change with impact 29.4, while a model reading density
# reacts to the same change with 0.008. On one shared axis the small bars
# vanish, and a vanished bar is indistinguishable from a zero or from an
# excluded row. So the heatmap colours by RELATIVE response within each model
# (which concept does THIS model care about?) and prints the ABSOLUTE number
# in the cell. Colour carries the pattern, text carries the magnitude, and
# neither has to compromise for the other.


def _formatImpact(value):
    ''' Compact but honest: keep enough digits to be meaningful at every
    order of magnitude, and never round a non-zero number to "0". '''
    if value is None or value != value:
        return "n/a"
    magnitude = abs(value)
    if magnitude == 0:
        return "0"
    if magnitude >= 100:
        return f"{value:+.0f}"
    if magnitude >= 1:
        return f"{value:+.2f}"
    if magnitude >= 0.001:
        return f"{value:+.3f}"
    return f"{value:+.0e}"


def explanationMatrix(resultFrame, delta, direction="increase"):
    ''' The 6 models x 5 concepts table at one perturbation size, using
    VALID rows only. Missing cells stay missing (NaN) rather than becoming
    zero: "this was excluded" and "this model did not react" are different
    facts and must not be drawn the same way. '''
    subset = resultFrame[resultFrame["valid_for_analysis"]
                         & (resultFrame["requested_delta"].abs() == delta)
                         & (resultFrame["direction"] == direction)]
    if subset.empty:
        return None
    return subset.pivot_table(index="model", columns="transformation",
                              values="impact", dropna=False)


def figureExplanationHeatmap(name, mode, resultFrame, path, delta,
                             direction="increase"):
    ''' "Which concept does each model respond to?" - the central TGAP
    question, as one picture.

    Each ROW is normalised by its own largest absolute impact, so every model
    is readable regardless of the units it predicts in. The printed number is
    the real impact. Grey cells with "n/a" are settings that failed a validity
    gate, so the reader can see coverage and result at the same time.
    '''
    matrix = explanationMatrix(resultFrame, delta, direction)
    if matrix is None:
        return
    values = matrix.to_numpy(dtype=float)
    scale = np.nanmax(np.abs(values), axis=1, keepdims=True)
    scale[~np.isfinite(scale) | (scale == 0)] = 1.0
    relative = values / scale

    fig, ax = plt.subplots(figsize=(1.55 * len(matrix.columns) + 3.2,
                                    0.62 * len(matrix.index) + 2.4))
    image = ax.imshow(np.ma.masked_invalid(relative), cmap="RdBu_r",
                      vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(matrix.columns)))
    ax.set_xticklabels(matrix.columns, rotation=18, ha="right")
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels(matrix.index)
    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            cell = values[row, column]
            shown = _formatImpact(cell)
            # White text on saturated colour, dark text on pale colour.
            strong = np.isfinite(relative[row, column]) and \
                abs(relative[row, column]) > 0.55
            ax.text(column, row, shown, ha="center", va="center", fontsize=8,
                    color="white" if strong else "black")
    ax.set_title(f"{name} [{mode}]: what each model responds to\n"
                 f"{direction}, requested delta {delta}; number = impact, "
                 f"colour = share of that model's largest response")
    ax.grid(False)
    fig.colorbar(image, ax=ax, label="impact / largest |impact| in the row")
    fig.savefig(path)
    plt.close(fig)


# Status colours, shared by the figure and the report so the two agree.
STATUS_COLOURS = {
    "ok": "#2e7d32",                      # green  - usable
    "saturated": "#ef6c00",               # orange - trend hit the floor
    "wrong_direction": "#6a1b9a",          # purple - moved the wrong way
    "edge_count_infeasible": "#c62828",   # red    - broke the link budget
    "no_property_change": "#757575",      # grey   - nothing moved
}


def figureValidityMap(name, mode, resultFrame, path):
    ''' "Which experiments could I actually use, and why not the others?"

    One cell per (concept, signed delta). 300 of the 1,440 rows across the
    project are excluded; without this picture that fact lives only in a
    column of a CSV nobody scrolls to.
    '''
    frame = resultFrame.drop_duplicates(["transformation", "requested_delta"])
    concepts = sorted(frame["transformation"].unique())
    deltas = sorted(frame["requested_delta"].unique())
    statuses = sorted(set(frame["transformation_status"]))

    order = {status: index for index, status
             in enumerate(STATUS_COLOURS)}
    grid = np.full((len(concepts), len(deltas)), np.nan)
    for rowIndex, concept in enumerate(concepts):
        for columnIndex, delta in enumerate(deltas):
            match = frame[(frame["transformation"] == concept)
                          & (frame["requested_delta"] == delta)]
            if not match.empty:
                grid[rowIndex, columnIndex] = order.get(
                    match["transformation_status"].iloc[0], np.nan)

    colours = [STATUS_COLOURS[status] for status in STATUS_COLOURS]
    cmap = mcolors.ListedColormap(colours)
    fig, ax = plt.subplots(figsize=(1.1 * len(deltas) + 3.6,
                                    0.58 * len(concepts) + 2.6))
    ax.imshow(np.ma.masked_invalid(grid), cmap=cmap, aspect="auto",
              vmin=-0.5, vmax=len(colours) - 0.5)
    ax.set_xticks(range(len(deltas)))
    ax.set_xticklabels([f"{d:+g}" for d in deltas])
    ax.set_yticks(range(len(concepts)))
    ax.set_yticklabels(concepts)
    ax.set_xlabel("requested delta (sign = direction)")
    for rowIndex in range(len(concepts)):
        for columnIndex in range(len(deltas)):
            index = grid[rowIndex, columnIndex]
            if index == index:
                label = list(STATUS_COLOURS)[int(index)]
                ax.text(columnIndex, rowIndex,
                        "OK" if label == "ok" else label.split("_")[0],
                        ha="center", va="center", fontsize=7, color="white")
    present = [s for s in STATUS_COLOURS if s in statuses]
    ax.legend(handles=[mpatches.Patch(color=STATUS_COLOURS[s], label=s)
                       for s in present],
              loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=8)
    ax.set_title(f"{name} [{mode}]: which perturbations were usable\n"
                 f"(same for every model, so computed once)")
    ax.grid(False)
    fig.savefig(path)
    plt.close(fig)


def writeReport(prepared, summary, resultFrame, trendFrame, feasibilityFrame,
                path, delta):
    ''' A human-readable summary of this dataset\'s run, in markdown.

    The CSV files stay the source of truth; this is the thing a person reads
    first and shows to someone else. Deliberately contains NO timestamp, so
    two runs of the same code produce identical bytes.
    '''
    meta, pre = prepared.meta, prepared.preprocessing
    valid = resultFrame[resultFrame["valid_for_analysis"]]
    invalid = resultFrame[~resultFrame["valid_for_analysis"]]
    lines = []
    add = lines.append

    add(f"# {prepared.name} - TGAP real-data run")
    add("")
    add(f"**Analysis mode:** `{meta['analysis_mode']}`"
        + ("  (leakage-safe - use these numbers)"
           if meta["analysis_mode"] == "temporal_evaluation"
           else "  (FULL-PERIOD, NOT leakage-safe - description only)"))
    add("")
    # .get, not [...]: a report is a convenience, and a missing optional
    # field must never abort a whole run's worth of real computation.
    add(f"> {meta.get('description', prepared.name)}")
    add("")

    add("## What was used")
    add("")
    add("| | in the source file | actually used | kept |")
    add("|---|---|---|---|")
    add(f"| actors | {meta['raw_nodes']:,} | {meta['retained_nodes']:,} | "
        f"{meta['nodes_retained_pct']}% |")
    add(f"| events | {meta['raw_events']:,} | {meta['retained_events']:,} | "
        f"{meta['events_retained_pct']}% |")
    add("")
    add(f"- A node is **{meta['graph_nodes_are']}**")
    add(f"- A link means **{meta['graph_edges_are']}**")
    add(f"- {meta['snapshot_count']} snapshots of {meta['snapshot_interval']}")
    add(f"- Communities: **{pre['partition_sizes']}** "
        f"via `{pre['community_mode']}`")
    add(f"- Edge weights used: **{meta['edge_weight_used']}**, "
        f"signs used: **{meta['edge_sign_used']}**")
    add("")

    add("## No future information")
    add("")
    add(f"- Actors chosen using: **{pre['selection_period']}** "
        f"(`{pre['node_selection_mode']}`)")
    add(f"- TGAP explained: **{pre['evaluation_period']}**")
    add(f"- Future information used for selection: "
        f"**{pre['future_information_used_for_node_selection']}**")
    add("")

    add("## How much of the run is usable")
    add("")
    add(f"**{len(valid)} of {len(resultFrame)} experiments are valid.** "
        f"Excluded, by reason:")
    add("")
    if invalid.empty:
        add("- nothing excluded")
    else:
        add("| reason | rows |")
        add("|---|---|")
        for status, count in (invalid["transformation_status"]
                              .value_counts().items()):
            add(f"| `{status}` | {count} |")
    add("")
    add(f"- edge-count invariant held in "
        f"{int(feasibilityFrame['feasible'].sum())}/"
        f"{len(feasibilityFrame)} settings")
    if not trendFrame.empty:
        counts = trendFrame["status"].value_counts().to_dict()
        add(f"- bridge-trend status: {counts}")
    add("")

    add(f"## What each model responds to (delta {delta}, increase)")
    add("")
    matrix = explanationMatrix(resultFrame, delta, "increase")
    if matrix is None:
        add("_No valid rows at this delta._")
    else:
        add("Impact = change in the model's answer, divided by the change we "
            "actually achieved. `n/a` = the experiment failed a validity "
            "check.")
        add("")
        add("| model | " + " | ".join(matrix.columns) + " |")
        add("|---" * (len(matrix.columns) + 1) + "|")
        for modelName, row in matrix.iterrows():
            add(f"| `{modelName}` | "
                + " | ".join(_formatImpact(v) for v in row) + " |")
    add("")

    add("## Largest responses (valid rows only)")
    add("")
    strongest = valid.assign(size=valid["impact"].abs()) \
        .sort_values("size", ascending=False).head(5)
    if strongest.empty:
        add("_No valid rows._")
    else:
        add("| model | concept | direction | delta | impact |")
        add("|---|---|---|---|---|")
        for _, row in strongest.iterrows():
            add(f"| `{row['model']}` | {row['transformation']} | "
                f"{row['direction']} | {abs(row['requested_delta']):g} | "
                f"{_formatImpact(row['impact'])} |")
    add("")

    add("## Snapshots")
    add("")
    add("| # | label | links | density | bridge width |")
    add("|---|---|---|---|---|")
    for _, row in summary.iterrows():
        add(f"| {row['snapshot_index']} | {row['label']} | {row['edges']} | "
            f"{row['density']:.4f} | {row['bridge_width']} |")
    add("")

    add("---")
    add("")
    add("*Real data has no ground truth, so nothing here validates TGAP's "
        "correctness - it shows the pipeline handles real temporal "
        "structure. Every number is a model sensitivity to a controlled "
        "counterfactual perturbation, not a causal claim.*")
    add("")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def makeFigures(prepared, summary, metricFrame, resultFrame, figureDir):
    ''' Six figures per dataset - no more than the results justify.

    Every impact figure uses ONLY rows flagged valid_for_analysis, so a
    perturbation that broke its own invariant cannot appear as a result.
    The heatmap and the validity map are added last; see the "Readable
    views" section above for why a bar chart alone is not enough.
    '''
    os.makedirs(figureDir, exist_ok=True)
    name = prepared.name
    mode = prepared.meta["analysis_mode"]
    valid = resultFrame[resultFrame["valid_for_analysis"]]

    # 1. Activity and structure over time.
    fig, axA = plt.subplots()
    axA.plot(summary["snapshot_index"], summary["edges"], marker="o",
             label="edges", color="tab:blue")
    axA.set_xlabel("snapshot")
    axA.set_ylabel("edges", color="tab:blue")
    axB = axA.twinx()
    axB.plot(summary["snapshot_index"], summary["bridge_width"], marker="s",
             label="bridge width", color="tab:red")
    axB.set_ylabel("bridge width", color="tab:red")
    axB.grid(False)
    axA.set_title(f"{name} [{mode}]: activity and cross-community ties "
                  f"over time")
    fig.savefig(os.path.join(figureDir, "activity_over_time.png"))
    plt.close(fig)

    # 2. Metric trajectories (normalised so different scales share an axis).
    fig, ax = plt.subplots()
    for column in ("bridge_width", "density", "centralization", "clustering"):
        values = metricFrame[column].to_numpy(dtype=float)
        span = values.max() - values.min()
        ax.plot(metricFrame["snapshot_index"],
                (values - values.min()) / span if span > 0
                else np.zeros_like(values),
                marker="o", markersize=3, label=column)
    ax.set_xlabel("snapshot")
    ax.set_ylabel("min-max normalised value")
    ax.set_title(f"{name} [{mode}]: concept trajectories "
                 f"(normalised for comparison)")
    ax.legend(fontsize=8)
    fig.savefig(os.path.join(figureDir, "metric_trajectories.png"))
    plt.close(fig)

    # 3. Impact by transformation, per model, at the reference delta.
    reference = valid[(valid["requested_delta"] == DELTAS[0])
                      & (valid["direction"] == "increase")]
    if not reference.empty:
        pivot = reference.pivot_table(index="transformation", columns="model",
                                      values="impact")
        fig, ax = plt.subplots(figsize=(8.0, 4.2))
        xs = np.arange(len(pivot.index))
        width = 0.8 / max(len(pivot.columns), 1)
        for i, column in enumerate(pivot.columns):
            ax.bar(xs + i * width, pivot[column], width, label=column)
        ax.set_xticks(xs + width * (len(pivot.columns) - 1) / 2)
        ax.set_xticklabels(pivot.index, rotation=20, ha="right", fontsize=8)
        ax.set_ylabel("impact (achieved-normalized)")
        ax.set_title(f"{name} [{mode}]: TGAP impact by concept\n"
                     f"increase, requested delta {DELTAS[0]}; "
                     f"valid rows only")
        ax.legend(fontsize=8)
        fig.savefig(os.path.join(figureDir, "impact_by_transformation.png"))
        plt.close(fig)

    # 4. Delta sensitivity on real data.
    fig, ax = plt.subplots()
    subset = valid[(valid["direction"] == "increase") & (~valid["noop"])]
    for (modelName, transformation), group in subset.groupby(
            ["model", "transformation"]):
        if len(group) < 2:
            continue
        group = group.sort_values("requested_delta")
        ax.plot(group["requested_delta"], group["impact"], marker="o",
                markersize=3, label=f"{transformation} / {modelName}")
    ax.set_xlabel("requested delta")
    ax.set_ylabel("impact")
    ax.set_title(f"{name} [{mode}]: sensitivity to perturbation size "
                 f"(valid rows only)")
    ax.legend(fontsize=6, ncol=2)
    fig.savefig(os.path.join(figureDir, "delta_sensitivity.png"))
    plt.close(fig)

    # 5. The explanation itself, readable at every order of magnitude.
    figureExplanationHeatmap(
        name, mode, resultFrame,
        os.path.join(figureDir, "explanation_heatmap.png"), DELTAS[0])

    # 6. Which perturbations survived the validity gates, and which did not.
    figureValidityMap(name, mode, resultFrame,
                      os.path.join(figureDir, "validity_map.png"))


def runDataset(key, mode):
    print("=" * 72)
    print(f"REAL DATA: {key}   [analysis_mode = {mode}]")
    print("=" * 72)
    prepared = ADAPTERS[key](mode)
    directory = os.path.join(OUTPUT_ROOT, mode, key)
    os.makedirs(directory, exist_ok=True)

    pre = prepared.preprocessing
    print(f"  snapshots      : {len(prepared.snapshots)}")
    print(f"  nodes          : {pre['retained_nodes']} retained of "
          f"{pre['raw_nodes']} raw ({pre['nodes_retained_pct']}%)")
    print(f"  events         : {pre['retained_events']:,} retained of "
          f"{pre['raw_events']:,} raw ({pre['events_retained_pct']}%)")
    print(f"  selection      : {pre['selection_period']} "
          f"[{pre['node_selection_mode']}]")
    print(f"  evaluation     : {pre['evaluation_period']}")
    print(f"  future info used for selection: "
          f"{pre['future_information_used_for_node_selection']}")
    print(f"  partition      : {pre['partition_sizes']} "
          f"[{pre['community_mode']}]")

    writeJson(prepared.meta, os.path.join(directory, "metadata.json"))
    writeJson(prepared.preprocessing,
              os.path.join(directory, "preprocessing_summary.json"))

    summary = summariseSnapshots(prepared.snapshots, prepared.communities,
                                 prepared.labels)
    summary.insert(0, "analysis_mode", mode)
    summary.to_csv(os.path.join(directory, "graph_summary.csv"), index=False)
    print(f"  edges/snapshot : median "
          f"{int(summary['edges'].median())}, range "
          f"{int(summary['edges'].min())}-{int(summary['edges'].max())}")
    print(f"  bridge width   : range {int(summary['bridge_width'].min())}"
          f"-{int(summary['bridge_width'].max())}")
    print(f"  connected      : {int(summary['is_connected'].sum())}/"
          f"{len(summary)} snapshots")

    metricFrame, _ = metricTrajectories(prepared)
    metricFrame.insert(0, "analysis_mode", mode)
    metricFrame.to_csv(os.path.join(directory, "metrics.csv"), index=False)

    transformations = buildTransformations(prepared.communities)
    strictTransformations = buildTransformations(prepared.communities,
                                                strict=True)

    # GATE 1: can each transformation keep its declared edge-count invariant?
    feasibilityFlags, feasibilityFrame = screenFeasibility(
        prepared, transformations, strictTransformations, DELTAS)
    feasibilityFrame.to_csv(
        os.path.join(directory, "transformation_feasibility.csv"), index=False)
    infeasible = feasibilityFrame[~feasibilityFrame["feasible"]]
    if infeasible.empty:
        print("  edge-count invariant held in every setting")
    else:
        print(f"  EDGE-COUNT INFEASIBLE in {len(infeasible)}/"
              f"{len(feasibilityFrame)} settings (rows excluded):")
        for name, group in infeasible.groupby("transformation"):
            print(f"      {name:16s} {len(group)} settings, up to "
                  f"{int(group['snapshots_violating'].max())} snapshot(s); "
                  f"{group['infeasible_reason'].iloc[0]}")
    disagreements = int((~feasibilityFrame[
        "strict_agrees_with_measurement"]).sum())
    print(f"  strict-mode / measurement agreement: "
          f"{len(feasibilityFrame) - disagreements}/{len(feasibilityFrame)}")

    # GATE 2: did the trend transformation shape the trajectory as asked?
    trendStatuses, trendFrame = screenBridgeTrend(prepared, transformations,
                                                  DELTAS)
    trendFrame.to_csv(os.path.join(directory, "bridge_trend_status.csv"),
                      index=False)
    if not trendFrame.empty:
        counts = trendFrame["status"].value_counts().to_dict()
        print(f"  bridge-trend status: {counts}; worst saturation "
              f"{100 * trendFrame['fraction_saturated'].max():.1f}% of "
              f"snapshots clamped to width 1")

    # Models. Three read bridge width in different ways (present only /
    # trend line / slope), which is what lets us ask whether TGAP separates
    # a history-using model from a present-only one. The other three read a
    # different property each, so that EVERY transformation has at least one
    # model that can respond to it - otherwise Centralization and Churn
    # would report 0 everywhere simply because nothing was listening.
    bridgeMetric = BridgeWidthMetric(prepared.communities)
    models = {
        "persistence_bridge_width": PersistenceTemporalModel(bridgeMetric),
        "trend_bridge_width": TrendTemporalModel(bridgeMetric),
        "slope_bridge_width": SlopeModel(bridgeMetric),
        "persistence_density": PersistenceTemporalModel(DensityMetric()),
        "persistence_centralization": PersistenceTemporalModel(
            DegreeCentralizationMetric()),
        "trend_clustering": TrendTemporalModel(ClusteringMetric()),
    }

    rows = []
    for modelName, model in models.items():
        counter = CallCountingModel(model)
        rows.extend(explainOneModel(prepared, modelName, counter,
                                    transformations, DELTAS,
                                    feasibilityFlags, trendStatuses))
        print(f"  model {modelName:26s} baseline "
              f"{model.predict(prepared.snapshots):12.6f}   "
              f"model calls {counter.calls}")
    resultFrame = pd.DataFrame(rows)
    resultFrame.to_csv(os.path.join(directory, "tgap_results.csv"),
                       index=False)

    valid = resultFrame[resultFrame["valid_for_analysis"]]
    print(f"  explanation rows: {len(resultFrame)} total, {len(valid)} valid "
          f"for analysis, {len(resultFrame) - len(valid)} excluded "
          f"{resultFrame.loc[~resultFrame['valid_for_analysis'], 'transformation_status'].value_counts().to_dict()}")

    # Leakage on real data, at the reference delta.
    panel = {
        "bridge width": bridgeMetric,
        "centralization": DegreeCentralizationMetric(),
        "density": DensityMetric(),
        "clustering": ClusteringMetric(),
    }
    leakRows = []
    for transformation in transformations:
        report = leakageReport(prepared.snapshots, transformation,
                               DELTAS[0], panel)
        flags, _ = rowValidity(transformation.name, DELTAS[0],
                               feasibilityFlags, trendStatuses)
        for prop, values in report.items():
            leakRows.append({
                "dataset": prepared.name,
                "analysis_mode": mode,
                "transformation": transformation.name,
                "property": prop,
                "before": values["before"],
                "after": values["after"],
                "change": values["change"],
                "delta": DELTAS[0],
                "transformation_status": flags["transformation_status"],
                "valid_for_analysis": flags["valid_for_analysis"],
            })
    pd.DataFrame(leakRows).to_csv(os.path.join(directory, "leakage.csv"),
                                  index=False)

    # How far each transformation actually reaches on these real graphs.
    diagnostics = transformationDiagnostics(prepared, transformations, DELTAS)
    diagnostics.to_csv(os.path.join(directory,
                                    "transformation_diagnostics.csv"),
                       index=False)
    blocked = diagnostics[diagnostics["structurally_blocked"]]
    if blocked.empty:
        print("  every structural transformation reached the last snapshot")
    else:
        print("  STRUCTURAL transformations blocked by the graph "
              "(present-only models cannot react to them):")
        for name, group in blocked.groupby("transformation"):
            total = len(diagnostics[diagnostics["transformation"] == name])
            print(f"      {name:16s} blocked in {len(group)}/{total} "
                  f"delta settings")

    makeFigures(prepared, summary, metricFrame, resultFrame,
                os.path.join(directory, "figures"))

    # The one file a person reads first. The CSVs stay the source of truth;
    # this turns them into something showable without opening a spreadsheet.
    writeReport(prepared, summary, resultFrame, trendFrame, feasibilityFrame,
                os.path.join(directory, "report.md"), DELTAS[0])

    # The expected-invariance check of item 6: a verification, not a
    # discovery. Computed over ALL Bridge Trend / Churn rows of the
    # present-only models, because the anchor holds whether or not the
    # trend shape saturated.
    invarianceRows = resultFrame[
        resultFrame["model"].str.startswith("persistence")
        & resultFrame["transformation"].isin(["Bridge Trend", "Churn"])
        & resultFrame["impact"].notna()]
    activeValid = valid[valid["impact"].notna()]
    invalidCounts = resultFrame.loc[
        ~resultFrame["valid_for_analysis"],
        "transformation_status"].value_counts().to_dict()

    headline = {
        "dataset": prepared.name,
        "analysis_mode": mode,
        "selection_fraction_of_span": pre["selection_fraction_of_span"],
        "node_selection_mode": pre["node_selection_mode"],
        "community_mode": pre["community_mode"],
        "selection_period": pre["selection_period"],
        "evaluation_period": pre["evaluation_period"],
        "future_information_used_for_node_selection":
            pre["future_information_used_for_node_selection"],
        "snapshot_count": len(prepared.snapshots),
        # RAW vs RETAINED, side by side, never one alone.
        "raw_nodes": pre["raw_nodes"],
        "retained_nodes": pre["retained_nodes"],
        "nodes_retained_pct": pre["nodes_retained_pct"],
        "raw_events": pre["raw_events"],
        "retained_events": pre["retained_events"],
        "events_retained_pct": pre["events_retained_pct"],
        "partition_sizes": pre["partition_sizes"],
        "edges_median": float(summary["edges"].median()),
        "bridge_width_first": int(summary["bridge_width"].iloc[0]),
        "bridge_width_last": int(summary["bridge_width"].iloc[-1]),
        "bridge_width_min": int(summary["bridge_width"].min()),
        "bridge_width_max": int(summary["bridge_width"].max()),
        "snapshots_with_zero_bridge_width": int(
            (summary["bridge_width"] == 0).sum()),
        "connected_snapshots": int(summary["is_connected"].sum()),
        "explanation_rows": int(len(resultFrame)),
        "valid_rows": int(len(valid)),
        "invalid_rows": int(len(resultFrame) - len(valid)),
        "invalid_rows_by_status": invalidCounts,
        # No-op rates on the VALID rows (the ones a conclusion may use),
        # with the all-rows figure kept beside them for comparability.
        "noop_rows_valid": int(valid["noop"].fillna(False).sum()),
        "noop_fraction_valid": float(valid["noop"].fillna(False).mean())
                               if len(valid) else None,
        "noop_fraction_all_rows_with_numbers": float(
            resultFrame["noop"].dropna().mean())
            if resultFrame["noop"].notna().any() else None,
        "models": list(models),
        "transformations": [t.name for t in transformations],
        "deltas": list(DELTAS),
        "seed": SEED,
        "largest_absolute_impact_valid_rows": (
            activeValid.loc[activeValid["impact"].abs().idxmax(),
                            ["model", "transformation", "direction",
                             "requested_delta", "impact"]].to_dict()
            if not activeValid.empty else None),
        "expected_invariance_history_only_transformations": {
            "statement": INVARIANCE_STATEMENT,
            "rows_checked": int(len(invarianceRows)),
            "verified": bool((invarianceRows["impact"] == 0).all())
                        if len(invarianceRows) else None,
            "max_absolute_impact_observed": float(
                invarianceRows["impact"].abs().max())
                if len(invarianceRows) else None,
        },
        "edge_count_infeasible_settings": int((~feasibilityFrame[
            "feasible"]).sum()),
        "edge_count_settings_checked": int(len(feasibilityFrame)),
        "strict_mode_disagreements": disagreements,
        "bridge_trend_status_counts": (
            trendFrame["status"].value_counts().to_dict()
            if not trendFrame.empty else {}),
        "bridge_trend_max_saturated_fraction": float(
            trendFrame["fraction_saturated"].max())
            if not trendFrame.empty else None,
        "edge_weight_used": False,
        "edge_sign_used": False,
    }
    writeJson(headline, os.path.join(directory, "summary.json"))
    print(f"  wrote {directory}")
    return headline


def main(argv=None):
    ''' CLI. --mode selects the analysis mode(s); remaining arguments are
    dataset keys. The default is the leakage-safe temporal evaluation. '''
    argv = list(argv if argv is not None else sys.argv[1:])
    modes = [TEMPORAL_EVALUATION]
    if "--mode" in argv:
        index = argv.index("--mode")
        requested = argv[index + 1]
        del argv[index:index + 2]
        modes = list(ANALYSIS_MODES) if requested == "both" else [requested]
        for mode in modes:
            if mode not in ANALYSIS_MODES:
                raise SystemExit(f"unknown --mode {mode!r}; expected one of "
                                 f"{ANALYSIS_MODES} or 'both'")
    keys = argv or list(ADAPTERS)

    allHeadlines = {}
    for mode in modes:
        root = os.path.join(OUTPUT_ROOT, mode)
        os.makedirs(root, exist_ok=True)
        headlines = {}
        for key in keys:
            headlines[key] = runDataset(key, mode)
            print()
        writeJson({"analysis_mode": mode,
                   "selection_fraction_of_span": SELECTION_FRACTION,
                   "leakage_safe": mode == TEMPORAL_EVALUATION,
                   "datasets": headlines},
                  os.path.join(root, "summary.json"))
        allHeadlines[mode] = headlines

        print("=" * 72)
        print(f"REAL-DATA RUN COMPLETE  [analysis_mode = {mode}]")
        print("=" * 72)
        for key, headline in headlines.items():
            print(f"{key}: {headline['snapshot_count']} snapshots, "
                  f"{headline['retained_nodes']}/{headline['raw_nodes']} nodes, "
                  f"{headline['valid_rows']}/{headline['explanation_rows']} "
                  f"valid explanation rows")
        print()

    print("These runs show the pipeline works on real temporal structure. "
          "They do not\nvalidate TGAP's correctness - real data has no "
          "ground truth. Nothing here is\na causal claim. The "
          "'descriptive' mode is NOT leakage-safe and must not be used\n"
          "for the scientific evaluation.")
    return allHeadlines


if __name__ == "__main__":
    main()
