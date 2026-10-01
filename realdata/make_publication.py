'''
Generate the publication figure and table set.

    python -m realdata.make_publication

Writes to output/publication/ - kept SEPARATE from the raw per-dataset
results (design section 44), so the paper's inputs are never mixed with
diagnostics. Nothing here computes new science: it selects and presents
results that already exist, except for the local/temporal explanations,
which are computed here because they are per-example rather than
per-dataset.

FIGURES
    fig1_concept_impacts.png        global concept importance
    fig2_model_concept_heatmap.png  model x concept explanation matrix
    fig3_bridge_matrix.png          N-community pairwise bridge structure
    fig4_local_graph.png            original / perturbed / difference graph
    fig5_temporal_local.png         when did the concept matter
    fig6_impact_distribution.png    beeswarm-style spread across datasets

TABLES (csv + markdown)
    table1_datasets.csv             dataset summary
    table2_main_results.csv         concept impacts, both case studies
    table3_tgn.csv                  learned-model results
    table4_validity.csv             how much of each run was usable

FIGURE SEMANTICS, used consistently everywhere:
    red / positive  = the perturbation RAISES the prediction
    blue / negative = the perturbation LOWERS it
    grey            = excluded (failed a validity gate) or not applicable
'''

import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
import networkx as nx
import numpy as np
import pandas as pd

from core import (
    BridgeWidthMetric, BridgeWidthTransformation, PersistenceTemporalModel,
    bridgeMatrix, edgeAttribution, edgeTimeAttribution, graphDifference,
    localExplanation, makeNCommunityTemporalGraph, nodeAttribution,
    temporalAttribution, writeElementAttribution,
)

RESULTS = os.path.join("output", "real_data_v2", "temporal_evaluation")
TGN_RESULTS = os.path.join("output", "real_data_v2", "tgn")
TGN_STABILITY = os.path.join("output", "real_data_v2", "tgn_stability",
                             "email_eu_core")
OUTPUT = os.path.join("output", "publication")
SUPERSEDED = os.path.join(OUTPUT, "superseded")
CASE_STUDIES = ("decentraland", "email_eu_core")

# One visual language for the whole paper, defined once in realdata.plotting
# and imported here. It used to be a second rcParams block with the same
# values copied in - the duplication is exactly the drift that module was
# added to prevent, so the copy is gone rather than kept in sync by hand.
from realdata.plotting import (POSITIVE, NEGATIVE, NEUTRAL,     # noqa: E402
                               savePublicationFigure,
                               usePublicationTheme)

# Imported BEFORE the theme is applied on purpose: this module pulls in
# paper_evaluation and run_real_data, both of which set savefig.dpi = 200 at
# import time. Importing it lazily inside semanticGroups() meant that clobber
# landed halfway through a run and silently downgraded every figure after it.
from realdata.run_tgn_stability import comparabilityOf   # noqa: E402

usePublicationTheme()


def _load(dataset):
    directory = os.path.join(RESULTS, dataset)
    with open(os.path.join(directory, "summary.json"), encoding="utf-8") as h:
        summary = json.load(h)
    return {
        "summary": summary,
        "results": pd.read_csv(os.path.join(directory, "tgap_results.csv")),
        "graph": pd.read_csv(os.path.join(directory, "graph_summary.csv")),
    }


def _valid(frame):
    ''' Publication figures show VALID rows only (design section 32);
    diagnostics keep the rest. '''
    return frame[frame["valid_for_analysis"]]


def figure1ConceptImpacts(datasets, path):
    ''' Global concept importance: mean |impact| per concept, per case
    study. Magnitudes differ by orders of magnitude between models, so each
    dataset is normalised by its own largest value - the comparison is of
    SHAPE, which is what "which concept matters here" means. '''
    fig, axes = plt.subplots(1, len(datasets), figsize=(4.2 * len(datasets), 3.2))
    axes = np.atleast_1d(axes)
    for ax, (name, data) in zip(axes, datasets.items()):
        valid = _valid(data["results"])
        grouped = valid.groupby("transformation")["impact"].apply(
            lambda s: s.abs().mean()).sort_values(ascending=True)
        largest = grouped.max() or 1.0
        ax.barh(range(len(grouped)), grouped / largest, color=POSITIVE,
                alpha=0.85)
        ax.set_yticks(range(len(grouped)))
        ax.set_yticklabels(grouped.index, fontsize=8)
        ax.set_xlabel("mean |impact|, scaled to this dataset's maximum")
        ax.set_title(name, fontsize=10)
        ax.set_xlim(0, 1.05)
    fig.suptitle("Concept importance (valid perturbations only)", fontsize=11)
    savePublicationFigure(fig, path)
    plt.close(fig)


def figure2ModelConceptHeatmap(datasets, path):
    ''' The explanation matrix: which model responds to which concept.
    Colour is normalised per model row so every model is legible whatever
    units it predicts in; the printed number is the real impact. '''
    fig, axes = plt.subplots(1, len(datasets),
                             figsize=(5.6 * len(datasets), 3.4))
    axes = np.atleast_1d(axes)
    for ax, (name, data) in zip(axes, datasets.items()):
        valid = _valid(data["results"])
        subset = valid[(valid["requested_delta"] == 0.1)
                       & (valid["direction"] == "increase")]
        matrix = subset.pivot_table(index="model", columns="transformation",
                                    values="impact", dropna=False)
        values = matrix.to_numpy(dtype=float)
        scale = np.nanmax(np.abs(values), axis=1, keepdims=True)
        scale[~np.isfinite(scale) | (scale == 0)] = 1.0
        image = ax.imshow(np.ma.masked_invalid(values / scale), cmap="RdBu_r",
                          vmin=-1, vmax=1, aspect="auto")
        ax.set_xticks(range(len(matrix.columns)))
        ax.set_xticklabels(matrix.columns, rotation=25, ha="right", fontsize=7)
        ax.set_yticks(range(len(matrix.index)))
        ax.set_yticklabels(matrix.index, fontsize=7)
        for i in range(values.shape[0]):
            for j in range(values.shape[1]):
                value = values[i, j]
                ax.text(j, i, "n/a" if value != value else f"{value:+.3g}",
                        ha="center", va="center", fontsize=6)
        ax.set_title(name, fontsize=10)
        ax.grid(False)
    fig.colorbar(image, ax=axes.tolist(), label="impact / row maximum",
                 fraction=0.02)
    fig.suptitle("Model x concept explanation matrix (delta 0.1, increase)",
                 fontsize=11)
    savePublicationFigure(fig, path)
    plt.close(fig)


def figure3BridgeMatrix(path):
    ''' N-community pairwise bridge structure (design section 29), on a
    synthetic world whose truth is known exactly - so the figure can be read
    as a demonstration of the representation rather than a finding. '''
    snapshots, partition = makeNCommunityTemporalGraph(
        nSnapshots=6, nCommunities=4, nPerCommunity=10,
        bridgeWidths={(0, 1): 18, (0, 2): 4, (1, 2): 11, "default": 6},
        bridgeDrift={(0, 1): -2}, seed=11)

    size = len(partition)
    matrix = np.full((size, size), np.nan)
    for (i, j), value in bridgeMatrix(snapshots[0], partition).items():
        matrix[i, j] = matrix[j, i] = value

    # Extra width and explicit spacing: at the default the right panel's
    # y-label collides with the left panel's colorbar label.
    fig, (axA, axB) = plt.subplots(1, 2, figsize=(10.6, 3.6))
    fig.subplots_adjust(wspace=0.45)
    image = axA.imshow(np.ma.masked_invalid(matrix), cmap="viridis")
    axA.set_xticks(range(size)); axA.set_xticklabels(partition.labels)
    axA.set_yticks(range(size)); axA.set_yticklabels(partition.labels)
    for i in range(size):
        for j in range(size):
            if i != j:
                axA.text(j, i, int(matrix[i, j]), ha="center", va="center",
                         color="white", fontsize=9)
    axA.set_title("Pairwise bridge width, first snapshot")
    axA.grid(False)
    fig.colorbar(image, ax=axA, fraction=0.046, label="edges between pair")

    for pair in partition.pairs():
        trajectory = [bridgeMatrix(g, partition)[pair] for g in snapshots]
        axB.plot(range(len(snapshots)), trajectory, marker="o", markersize=3,
                 label=partition.labelOfPair(pair))
    axB.set_xlabel("snapshot"); axB.set_ylabel("bridge width")
    axB.set_title("Pairwise bridge trajectories")
    axB.legend(fontsize=7, ncol=2)
    fig.suptitle("Bridge structure with four communities "
                 "(A-B declining by construction)", fontsize=11)
    savePublicationFigure(fig, path)
    plt.close(fig)


def figure4LocalGraph(path):
    ''' Design sections 23 and 28: original, perturbed and DIFFERENCE graph
    for one local explanation, with communities and affected edges marked.

    A small synthetic world is used deliberately: a readable node-link
    drawing needs few enough nodes to see, and the point of the figure is to
    show what a local explanation contains, not to make a claim about data.
    '''
    snapshots, partition = makeNCommunityTemporalGraph(
        nSnapshots=4, nCommunities=3, nPerCommunity=7,
        bridgeWidths={(0, 1): 6, "default": 3}, seed=4)
    model = PersistenceTemporalModel(
        BridgeWidthMetric(partition, communityPair=(0, 1)))
    transformation = BridgeWidthTransformation(partition, seed=42,
                                               communityPair=(0, 1))
    record, transformed = localExplanation(snapshots, transformation, 1.0,
                                           model=model, communities=partition)

    before, after = snapshots[-1], transformed[-1]
    difference = graphDifference(before, after)
    layout = nx.spring_layout(before, seed=1)
    colours = [[POSITIVE, NEGATIVE, "#4d9221"][partition.communityOf(n)]
               for n in before.nodes()]

    fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.9))
    for ax, graph, title in (
            (axes[0], before, "Original"),
            (axes[1], after, f"Perturbed (+100% bridge {partition.labelOfPair((0,1))})")):
        nx.draw_networkx_nodes(graph, layout, ax=ax, node_size=90,
                               node_color=colours, linewidths=0.4,
                               edgecolors="black")
        nx.draw_networkx_edges(graph, layout, ax=ax, width=0.6, alpha=0.45)
        ax.set_title(title, fontsize=10); ax.axis("off")

    ax = axes[2]
    nx.draw_networkx_nodes(before, layout, ax=ax, node_size=90,
                           node_color=colours, linewidths=0.4,
                           edgecolors="black")
    nx.draw_networkx_edges(before, layout, ax=ax, edgelist=difference["kept"],
                           width=0.4, alpha=0.15)
    nx.draw_networkx_edges(before, layout, ax=ax, edgelist=difference["added"],
                           width=2.0, edge_color=POSITIVE)
    nx.draw_networkx_edges(before, layout, ax=ax,
                           edgelist=difference["removed"], width=2.0,
                           edge_color=NEGATIVE, style="dashed")
    ax.set_title(f"Difference: {len(difference['added'])} added (red), "
                 f"{len(difference['removed'])} removed (blue dashed)",
                 fontsize=10)
    ax.axis("off")

    fig.suptitle(
        f"Local explanation - {record['concept']}: achieved "
        f"{record['achieved_delta']:+.3f}, impact {record['impact']:+.3f}, "
        f"{record['affected_edge_count']} edges and "
        f"{record['affected_node_count']} nodes touched", fontsize=11)
    savePublicationFigure(fig, path)
    plt.close(fig)
    return record


def figure5TemporalLocal(path):
    ''' Design section 24: WHEN did the concept matter?

    x = time, y = the concept's value in that snapshot, colour = the impact
    of perturbing that snapshot alone. Two models are shown because the
    contrast is the result: a present-only model can react to the last
    snapshot and nothing else, while a trajectory model spreads its
    sensitivity across time.
    '''
    from core import TrendTemporalModel
    snapshots, partition = makeNCommunityTemporalGraph(
        nSnapshots=8, nCommunities=2, nPerCommunity=10,
        bridgeWidths={(0, 1): 10}, bridgeDrift={(0, 1): 2}, seed=6)
    metric = BridgeWidthMetric(partition)
    transformation = BridgeWidthTransformation(partition, seed=42)
    widths = [metric.measure(g) for g in snapshots]

    fig, axes = plt.subplots(1, 2, figsize=(10.0, 3.6), sharey=True)
    for ax, model, title in (
            (axes[0], PersistenceTemporalModel(metric),
             "Present-only model"),
            (axes[1], TrendTemporalModel(metric), "Trajectory model")):
        attribution = temporalAttribution(snapshots, model, transformation, 0.5)
        impacts = [row["impact"] for row in attribution["rows"]]
        limit = max(abs(min(impacts)), abs(max(impacts))) or 1.0
        points = ax.scatter(range(len(snapshots)), widths, c=impacts,
                            cmap="RdBu_r", vmin=-limit, vmax=limit, s=110,
                            edgecolors="black", linewidths=0.4, zorder=3)
        ax.plot(range(len(snapshots)), widths, color="grey", alpha=0.4,
                zorder=1)
        ax.set_xlabel("snapshot"); ax.set_title(title, fontsize=10)
        fig.colorbar(points, ax=ax, fraction=0.046,
                     label="impact of perturbing this snapshot alone")
    axes[0].set_ylabel("bridge width")
    fig.suptitle("Temporal local explanation: when the concept matters",
                 fontsize=11)
    savePublicationFigure(fig, path)
    plt.close(fig)


def figure6ImpactDistribution(path):
    ''' Beeswarm-style spread of impacts per concept across all 8 datasets.
    Shows that a concept's importance is not a single number but a
    distribution, and where the outliers sit. '''
    frames = []
    for name in sorted(os.listdir(RESULTS)):
        directory = os.path.join(RESULTS, name)
        if not os.path.isdir(directory):
            continue
        path_ = os.path.join(directory, "tgap_results.csv")
        if os.path.exists(path_):
            frames.append(pd.read_csv(path_))
    if not frames:
        return
    everything = _valid(pd.concat(frames))
    concepts = sorted(everything["transformation"].unique())

    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    rng = np.random.default_rng(42)          # jitter only; seeded
    for position, concept in enumerate(concepts):
        values = everything[everything["transformation"] == concept]["impact"]
        values = values[np.isfinite(values)]
        # Symmetric log keeps +29 and +0.008 on one readable axis.
        shown = np.sign(values) * np.log10(1 + np.abs(values))
        jitter = rng.uniform(-0.16, 0.16, len(shown))
        ax.scatter(shown, position + jitter, s=9, alpha=0.5,
                   c=[POSITIVE if v > 0 else NEGATIVE for v in values])
    ax.set_yticks(range(len(concepts)))
    ax.set_yticklabels(concepts, fontsize=8)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("signed log10(1 + |impact|)   "
                  "(red = raises prediction, blue = lowers)")
    ax.set_title("Impact distribution per concept, 8 datasets, valid rows only",
                 fontsize=11)
    savePublicationFigure(fig, path)
    plt.close(fig)


##  Perturbation-semantics grouping (candidates A, B, C)  ##
#
# WHY THESE FIGURES EXIST
#     fig1 and fig2 place all five concepts on one comparison axis. RQ1b
#     records that this is not valid for all of them: Centralization's delta
#     is a rewiring FRACTION (a mechanism knob) and Bridge Trend's is in
#     absolute slope units, so neither achieved change is the same kind of
#     quantity as a relative change in bridge width, density or churn.
#     fig1/fig2 are left exactly as they are; these are alternatives.
#
# WHERE THE GROUPING COMES FROM
#     NOT a hand-written list of names, and NOT the stored `delta_mode`
#     column - that column says "relative" for Centralization, because
#     Centralization's REQUESTED delta is relative even though its ACHIEVED
#     delta is a rewiring fraction. Using it would silently put
#     Centralization in the commensurable group and reintroduce the exact
#     error these figures exist to prevent.
#
#     The grouping is derived by calling comparabilityOf - the same function
#     RQ1b's matched comparison uses - against a relative-delta reference
#     concept. One rule, one implementation, two consumers.

COMMENSURABLE = "relative delta"
NOT_COMMENSURABLE = "mechanism / absolute delta"


def semanticGroups():
    ''' Split the registered concepts by perturbation semantics.

    Returns an ordered dict {group label: [concept names]}, concepts in
    REGISTRY order inside each group - never impact order, so no figure
    built from this can imply a cross-concept ranking.

    The reference concept is the first registered concept that is
    comparable with itself under a relative delta; every other concept is
    then asked whether comparabilityOf admits it.
    '''
    from core.Communities import Partition
    from core.TransformationRegistry import entries

    # comparabilityOf inspects deltaMode and the transformation CLASS, so the
    # objects must be built. The partition is a throwaway - it affects no
    # attribute the rule reads.
    partition = Partition([{0, 1}, {2, 3}])
    built = []
    for entry in entries():
        try:
            built.append((entry.name, entry.build(communities=partition)))
        except Exception:                       # a concept that cannot build
            continue                            # cannot appear in a figure

    reference = None
    for name, transformation in built:
        if getattr(transformation, "deltaMode", "relative") == "relative":
            comparable, _ = comparabilityOf(transformation, transformation)
            if comparable:
                reference = transformation
                break
    if reference is None:                       # no relative concept at all
        return {NOT_COMMENSURABLE: [n for n, _ in built]}

    groups = {COMMENSURABLE: [], NOT_COMMENSURABLE: []}
    for name, transformation in built:
        comparable, _ = comparabilityOf(reference, transformation)
        groups[COMMENSURABLE if comparable else NOT_COMMENSURABLE].append(name)
    return groups


def _meanAbsImpact(frame, concepts):
    ''' Mean |impact| per concept over VALID rows, in the given order.
    Concepts with no valid row are dropped, not plotted as zero - absent
    evidence is not evidence of no effect. '''
    valid = _valid(frame)
    out = []
    for concept in concepts:
        values = valid[valid["transformation"] == concept]["impact"]
        values = values[np.isfinite(values)]
        if len(values):
            out.append((concept, float(values.abs().mean()), len(values)))
    return out


def _dotPanel(ax, rows, colour):
    ''' One concept-impact panel.

    A DOT, not a bar. On a log axis a bar's length depends on where the axis
    happens to start, so bar length is not proportional to the value; a
    dot's position is exactly the value. Every candidate figure uses this,
    so the two groups in candidate B cannot acquire different visual
    grammar by accident.
    '''
    if not rows:
        ax.text(0.5, 0.5, "no valid rows", ha="center", va="center",
                fontsize=8, color=NEUTRAL, transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
        return
    values = [v for _, v, _ in rows]
    floor = min(values) / 4
    ax.hlines(range(len(rows)), floor, values, color=NEUTRAL, linewidth=1.0,
              zorder=2)
    ax.scatter(values, range(len(rows)), s=58, color=colour,
               edgecolors="black", linewidths=0.5, zorder=3)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([f"{c}  (n={n})" for c, _, n in rows], fontsize=8)
    ax.set_xscale("log")
    for index, value in enumerate(values):
        ax.annotate(f"{value:.4g}", (value, index), textcoords="offset points",
                    xytext=(7, 0), va="center", fontsize=7.5)
    ax.set_xlim(floor, max(values) * 30)
    ax.set_ylim(-0.6, len(rows) - 0.4)


def figure1ACommensurable(datasets, path):
    ''' CANDIDATE A - only the concepts RQ1b admits as commensurable.

    Shows mean |impact| for the relative-delta concepts (Bridge Width,
    Density, Churn as currently registered) and omits the other two
    entirely. Values are the REAL means on a log axis, not rescaled to a
    per-dataset maximum: inside this group the quantities are commensurable,
    so there is no reason to hide their size.

    COMPARABILITY: cross-concept numerical comparison IS allowed within this
    figure. That is the whole point of restricting it.

    Deliberately NOT called "concept importance" - it reports measured
    prediction impact, which is not the same claim.
    '''
    groups = semanticGroups()
    concepts = groups.get(COMMENSURABLE, [])
    fig, axes = plt.subplots(1, len(datasets),
                             figsize=(5.2 * len(datasets), 3.1), squeeze=False)
    for ax, (name, data) in zip(axes[0], datasets.items()):
        _dotPanel(ax, _meanAbsImpact(data["results"], concepts), POSITIVE)
        ax.set_xlabel("mean |impact| (log scale)")
        ax.set_title(name, fontsize=10)
    fig.suptitle("Global prediction impact for commensurable transformations\n"
                 "(relative-delta concepts only; valid perturbations only)",
                 fontsize=10.5)
    fig.subplots_adjust(top=0.80, wspace=0.42)
    savePublicationFigure(fig, path)
    plt.close(fig)
    return {"concepts": concepts}


def figure1BGrouped(datasets, path):
    ''' CANDIDATE B - all five concepts, split into two separated panels.

    Each semantic group gets its OWN axes and its own x-axis. Nothing spans
    the two, so there is no shared bar length to read as a ranking, and the
    gap between the column pairs is wide enough that the eye does not carry
    one scale across it.

    COMPARABILITY: allowed WITHIN a group, not across groups. The caption
    says so, and the two groups never share an axis.
    '''
    groups = semanticGroups()
    order = [g for g in (COMMENSURABLE, NOT_COMMENSURABLE) if groups.get(g)]
    fig = plt.figure(figsize=(5.4 * len(datasets), 2.6 + 1.7 * len(order)))
    # Wide hspace/wspace: the separation IS the scientific content here.
    grid = fig.add_gridspec(len(order), len(datasets), wspace=0.42,
                            hspace=1.05, top=0.76, bottom=0.12)
    for rowIndex, group in enumerate(order):
        for columnIndex, (name, data) in enumerate(datasets.items()):
            ax = fig.add_subplot(grid[rowIndex, columnIndex])
            _dotPanel(ax, _meanAbsImpact(data["results"], groups[group]),
                      POSITIVE if group == COMMENSURABLE else NEUTRAL)
            ax.set_xlabel("mean |impact| (log scale)", fontsize=8)
            ax.set_title(f"{name}\ngroup: {group}", fontsize=9)
    # A hard rule between the groups, so the split cannot be missed.
    fig.add_artist(plt.Line2D([0.04, 0.96], [0.435, 0.435], color="#444444",
                              linewidth=1.1, linestyle=(0, (6, 4))))
    fig.suptitle("Global prediction impact, grouped by perturbation semantics\n"
                 "Values are NOT comparable across the two groups: a relative "
                 "property change, a rewiring\nfraction and an absolute slope "
                 "are different quantities. Each group has its own axis.",
                 fontsize=10, y=0.97)
    savePublicationFigure(fig, path)
    plt.close(fig)
    return {"groups": {g: groups.get(g, []) for g in order}}


def figure2CGroupedSemanticHeatmap(datasets, path):
    ''' CANDIDATE C - the model x concept matrix, grouped by semantics.

    All five concepts stay visible. What changes is that the matrix is cut
    into one block per semantic group, each with its own colour treatment,
    so no single colour scale spans all five columns.

      * commensurable block - colour is impact / row maximum WITHIN THE
        BLOCK. The three concepts are comparable, so a shared scale across
        them is meaningful.
      * non-commensurable block - colour encodes SIGN ONLY. Giving these
        columns a shared magnitude scale would be exactly the invented
        transformation-independent score this figure must not contain.

    In both blocks the printed number is the REAL TGAP impact, so no value
    is lost to normalisation. Concepts are in registry order inside each
    block and are never sorted by impact.

    COMPARABILITY: colour may be compared within the left block only.
    '''
    groups = semanticGroups()
    order = [g for g in (COMMENSURABLE, NOT_COMMENSURABLE) if groups.get(g)]
    widths = [max(len(groups[g]), 1) for g in order]
    fig = plt.figure(figsize=(3.0 + 1.5 * sum(widths), 1.9 * len(datasets) + 1.9))
    grid = fig.add_gridspec(len(datasets), len(order), width_ratios=widths,
                            wspace=0.30, hspace=0.80, top=0.84, bottom=0.17)

    image = None
    for rowIndex, (name, data) in enumerate(datasets.items()):
        valid = _valid(data["results"])
        subset = valid[(valid["requested_delta"] == 0.1)
                       & (valid["direction"] == "increase")]
        for columnIndex, group in enumerate(order):
            ax = fig.add_subplot(grid[rowIndex, columnIndex])
            concepts = [c for c in groups[group]
                        if c in set(subset["transformation"])]
            if not concepts:
                ax.text(0.5, 0.5, "no valid rows", ha="center", va="center",
                        fontsize=8, color=NEUTRAL, transform=ax.transAxes)
                ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
                ax.set_title(group, fontsize=9)
                continue
            matrix = subset.pivot_table(index="model", columns="transformation",
                                        values="impact", dropna=False)
            matrix = matrix.reindex(columns=concepts)    # registry order
            values = matrix.to_numpy(dtype=float)

            if group == COMMENSURABLE:
                scale = np.nanmax(np.abs(values), axis=1, keepdims=True)
                scale[~np.isfinite(scale) | (scale == 0)] = 1.0
                shown = values / scale
                image = ax.imshow(np.ma.masked_invalid(shown), cmap="RdBu_r",
                                  vmin=-1, vmax=1, aspect="auto")
            else:
                # Sign only, in a DELIBERATELY DIFFERENT palette. Reusing
                # RdBu_r here would render a +0.000994 cell fully saturated,
                # and a reader checking it against the continuous colorbar
                # would read it as a maximal impact. Three flat, muted,
                # obviously-categorical colours cannot be read off that bar.
                signColours = ListedColormap(["#9ecae1", "#f0f0f0", "#fcae91"])
                ax.imshow(np.ma.masked_invalid(np.sign(values)),
                          cmap=signColours,
                          norm=BoundaryNorm([-1.5, -0.5, 0.5, 1.5], 3),
                          aspect="auto")

            ax.set_xticks(range(len(concepts)))
            ax.set_xticklabels(concepts, rotation=25, ha="right", fontsize=7)
            ax.set_yticks(range(values.shape[0]))
            ax.set_yticklabels(matrix.index if columnIndex == 0 else
                               [""] * values.shape[0], fontsize=7)
            for i in range(values.shape[0]):
                for j in range(values.shape[1]):
                    value = values[i, j]
                    ax.text(j, i, "n/a" if value != value else f"{value:+.3g}",
                            ha="center", va="center", fontsize=6)
            note = ("colour: impact / row max" if group == COMMENSURABLE
                    else "colour: SIGN ONLY")
            ax.set_title(f"{name}\n{group}  -  {note}", fontsize=8.5)
            ax.grid(False)

    if image is not None:
        bar = fig.colorbar(image, ax=fig.axes, fraction=0.016, pad=0.02)
        bar.set_label("impact / row maximum\n(commensurable block ONLY)",
                      fontsize=8)
    # The sign block gets its own key, never the continuous bar.
    fig.legend(handles=[mpatches.Patch(facecolor="#fcae91",
                                       edgecolor="#444444",
                                       label="raises prediction"),
                        mpatches.Patch(facecolor="#9ecae1",
                                       edgecolor="#444444",
                                       label="lowers prediction")],
               title="mechanism / absolute block: sign only",
               loc="lower center", ncol=2, fontsize=8, title_fontsize=8,
               frameon=True, bbox_to_anchor=(0.5, 0.005))
    fig.suptitle("Model x concept impacts, grouped by perturbation semantics "
                 "(delta 0.1, increase)\nPrinted values are the real impacts. "
                 "No colour scale spans both groups.", fontsize=10, y=0.985)
    savePublicationFigure(fig, path)
    plt.close(fig)
    return {"groups": {g: groups.get(g, []) for g in order}}


##  The final publication figure  ##


def semanticRows():
    ''' The three row groups, in the order they are drawn.

    Row 1 holds every concept comparabilityOf admits as mutually
    commensurable. Rows 2 and 3 hold the rest, ONE CONCEPT PER ROW, because
    Centralization and Bridge Trend are not comparable with the relative
    group and are not comparable with each other either - a rewiring
    fraction and an absolute slope are different quantities. Giving them a
    shared row would imply a comparison that does not exist.
    '''
    groups = semanticGroups()
    rows = [(COMMENSURABLE, list(groups.get(COMMENSURABLE, [])),
             "comparable under the matched-delta protocol")]
    for concept in groups.get(NOT_COMMENSURABLE, []):
        rows.append((concept, [concept], "own perturbation units"))
    return rows


def _stripPanel(ax, frame, concepts, xLabel):
    ''' Every valid impact for one (dataset, model) cell, as individual
    points. NOTHING is averaged: each point is one (delta, direction) row
    straight from the CSV, so no pooled statistic can be read off the panel.

    Returns the number of points drawn, so the caller can tell an empty
    panel from a panel of zeros - a concept with no valid observation is
    never drawn at x = 0.
    '''
    drawn = 0
    for position, concept in enumerate(concepts):
        values = frame[frame["transformation"] == concept]["impact"]
        values = values[np.isfinite(values)]
        if not len(values):
            ax.text(0.5, position, "no valid obs.\n(n=0)",
                    transform=ax.get_yaxis_transform(), ha="center",
                    va="center", fontsize=6, color=NEUTRAL, style="italic")
            continue
        drawn += len(values)
        ax.scatter(values, [position] * len(values), s=26, alpha=0.85,
                   c=[POSITIVE if v > 0 else NEGATIVE for v in values],
                   edgecolors="black", linewidths=0.3, zorder=3)
        ax.annotate(f"n={len(values)}", (1.0, position),
                    xycoords=ax.get_yaxis_transform(),
                    textcoords="offset points", xytext=(-3, 7),
                    ha="right", va="center", fontsize=6, color="#555555")
    ax.set_yticks(range(len(concepts)))
    ax.set_yticklabels(concepts, fontsize=7)
    ax.set_ylim(-0.7, len(concepts) - 0.3)
    ax.tick_params(axis="x", labelsize=6.5)
    if drawn:
        # The zero line is the no-effect reference, so it is drawn only
        # where there is something to reference. An empty panel gets no
        # axis at all rather than a tick range implying a measured scale.
        ax.axvline(0, color="black", linewidth=0.9, zorder=2)
        if xLabel:
            ax.set_xlabel("impact", fontsize=7)
    else:
        ax.set_xticks([])
    return drawn


def figure1FinalModelSeparated(datasets, path):
    ''' THE final global-impact figure: descriptive, model-separated.

    WHAT IT ANSWERS
        "How does each individual model respond to each transformation?"

    WHAT IT DOES NOT ANSWER
        "Which transformation is globally most important?" Nothing here is
        pooled, averaged or ranked. Formal cross-concept comparison is
        RQ1b / table7, not this figure.

    TWO INDEPENDENT REASONS FOR THE LAYOUT
        1. The five transformations do not share perturbation semantics, so
           rows separate them: row 1 is the mutually commensurable group,
           rows 2 and 3 are one non-commensurable concept each.
        2. The six models do not share a prediction scale, so EVERY PANEL
           CARRIES ITS OWN X-AXIS. An impact of 2 under one model is not
           claimed to mean what an impact of 2 means under another, and no
           axis spans two models.

        Datasets are blocked into separate column groups for the same
        reason: the same model on a different graph is not guaranteed the
        same prediction scale either.

    AXIS CHOICE
        Linear. Impacts are signed and roughly symmetric about zero
        (-45.9 to +45.9 in the current data), so a log axis is
        mathematically unavailable, and the zero line carries real meaning:
        it is the no-effect reference, not a plotting convenience.

    EVERY POINT IS ONE VALID CSV ROW. Concepts with no valid observation
    are labelled, never plotted as zero.
    '''
    groups = semanticRows()
    models = sorted({m for data in datasets.values()
                     for m in _valid(data["results"])["model"].unique()})
    # One row per (dataset, semantic group): columns stay the models, which
    # keeps each row readable, and the two datasets are blocked vertically
    # rather than doubling the width to 12 columns.
    rows = [(dataset, label, concepts, note)
            for dataset in datasets
            for label, concepts, note in groups]
    if not models or not rows:
        return {}

    fig = plt.figure(figsize=(2.05 * len(models) + 1.9,
                              1.15 * sum(max(len(c), 1) for _, _, c, _ in rows)
                              + 2.6))
    grid = fig.add_gridspec(
        len(rows), len(models),
        height_ratios=[max(len(c), 1) for _, _, c, _ in rows],
        wspace=0.40, hspace=0.75, top=0.90, bottom=0.055, left=0.135,
        right=0.99)

    counts = {}
    for rowIndex, (dataset, label, concepts, note) in enumerate(rows):
        valid = _valid(datasets[dataset]["results"])
        lastOfBlock = (rowIndex + 1) % len(groups) == 0
        for columnIndex, model in enumerate(models):
            ax = fig.add_subplot(grid[rowIndex, columnIndex])
            drawn = _stripPanel(ax, valid[valid["model"] == model], concepts,
                                xLabel=lastOfBlock)
            counts[(dataset, model, label)] = drawn
            # Hide the repeated labels without DISCARDING them: tick_params
            # keeps the text on the artist, so the panel still reports which
            # concepts it holds. A single-concept row is already named by the
            # row label on the left, and repeating it there only collides.
            if columnIndex or len(concepts) == 1:
                ax.tick_params(labelleft=False)
            if not rowIndex:
                ax.set_title(model, fontsize=7.2, pad=5)
            if not columnIndex:
                ax.annotate(f"{dataset}\n{label}\n({note})", (-0.78, 0.5),
                            xycoords="axes fraction", ha="center",
                            va="center", fontsize=6.9, fontweight="bold",
                            linespacing=1.4)

    # A rule between the two dataset blocks, mirroring the row separation.
    if len(datasets) > 1:
        above = fig.axes[(len(groups) - 1) * len(models)].get_position().y0
        below = fig.axes[len(groups) * len(models)].get_position().y1
        fig.add_artist(plt.Line2D([0.02, 0.995], [(above + below) / 2] * 2,
                                  color="#444444", linewidth=1.0,
                                  linestyle=(0, (5, 4))))

    fig.suptitle(
        "TGAP prediction impacts, reported separately for each model\n"
        "Bridge Width, Density and Churn share a panel within a model "
        "because their perturbations are comparable under the matched-delta\n"
        "protocol. Centralization and Bridge Trend occupy their own rows: "
        "their perturbation units are not comparable with the relative-delta\n"
        "concepts, nor with each other. Every panel has its own x-axis "
        "because prediction scales differ across models and datasets.\n"
        "The figure is descriptive and gives no global ranking of "
        "transformations; formal matched comparisons are reported in RQ1b.",
        fontsize=8.2, y=0.988)
    savePublicationFigure(fig, path)
    plt.close(fig)
    return {"models": models, "datasets": list(datasets),
            "rows": [(d, l) for d, l, _, _ in rows], "points": counts}


##  Element-level attribution: compute once, persist, then plot  ##
#
# WHY THESE ARE COMPUTED HERE
#     Same reason fig4/fig5 already are: element-level attribution is
#     per-EXAMPLE, not per-dataset, and the real-data runs persist results
#     rather than model objects, so there is no stored model to re-occlude
#     against. A seeded synthetic world is used, exactly as fig4/fig5 do.
#
# WHAT IS NEW HERE IS THE PERSISTENCE
#     The attribution is written to CSV through the EXISTING
#     writeElementAttribution / ELEMENT_ATTRIBUTION_COLUMNS writers before
#     anything is drawn, and the figures then read that file. Two
#     consequences that matter: the complete attribution survives even where
#     a figure shows only a top-K view, and no figure can contain a number
#     that is not in a machine-readable file.
#
# NO NEW EXPLANATION ALGORITHM. edgeAttribution, nodeAttribution and
# edgeTimeAttribution already existed and are unchanged; this calls them.

ATTRIBUTION = os.path.join(OUTPUT, "attribution")
ATTRIBUTION_SEED = 42
LOCAL_BAR_TOP_K = 18
EDGE_TIME_TOP_K = 22


def _attributionWorld():
    ''' One small, seeded, deterministic world shared by the element-level
    figures, so they all describe the SAME explanation rather than three
    unrelated ones. '''
    snapshots, partition = makeNCommunityTemporalGraph(
        nSnapshots=5, nCommunities=3, nPerCommunity=8,
        bridgeWidths={(0, 1): 8, "default": 4}, seed=7)
    model = PersistenceTemporalModel(
        BridgeWidthMetric(partition, communityPair=(0, 1)))
    return snapshots, partition, model


def buildAttributionData(directory=ATTRIBUTION):
    ''' Compute and PERSIST element-level and edge-time attribution.

    Returns the paths written. Everything downstream reads these files, not
    the in-memory objects, so a figure and its data file cannot disagree.
    '''
    os.makedirs(directory, exist_ok=True)
    snapshots, partition, model = _attributionWorld()
    name = "synthetic_3community"

    edges = edgeAttribution(snapshots, model, communities=partition,
                            seed=ATTRIBUTION_SEED)
    nodes = nodeAttribution(snapshots, model, seed=ATTRIBUTION_SEED)
    edgePath = os.path.join(directory, "edge_attribution.csv")
    nodePath = os.path.join(directory, "node_attribution.csv")
    writeElementAttribution(edges, edgePath, dataset=name,
                            model=type(model).__name__, seed=ATTRIBUTION_SEED)
    writeElementAttribution(nodes, nodePath, dataset=name,
                            model=type(model).__name__, seed=ATTRIBUTION_SEED)

    # A SECOND model on the SAME world. The persistence model reads only the
    # last snapshot, so removing any edge can only lower bridge width: its
    # local explanation is entirely non-positive and never exercises the
    # diverging layout. A trajectory model responds to the whole history, so
    # removing an edge can raise or lower the fitted trend. Both are real
    # measured explanations; fig11 uses the trajectory one because it has
    # both signs, fig12 keeps the persistence model because its all-zero
    # response before the last snapshot IS the temporal result worth seeing.
    from core import TrendTemporalModel
    trendModel = TrendTemporalModel(
        BridgeWidthMetric(partition, communityPair=(0, 1)))
    trendEdges = edgeAttribution(snapshots, trendModel,
                                 communities=partition, seed=ATTRIBUTION_SEED)
    trendPath = os.path.join(directory, "edge_attribution_trend.csv")
    writeElementAttribution(trendEdges, trendPath, dataset=name,
                            model=type(trendModel).__name__,
                            seed=ATTRIBUTION_SEED)

    # Edge-time: one (edge, snapshot) pair per row. topK is NOT used here -
    # the COMPLETE attribution is persisted, every edge at every snapshot,
    # so the top-K in fig12 is purely a display choice applied to a file
    # that already holds everything. Note that the library's topK is applied
    # PER SNAPSHOT, so passing topK=14 would have persisted a different set
    # of edges for each snapshot and made the figure's grid sparse and its
    # "top K edges" caption wrong.
    edgeTime = edgeTimeAttribution(snapshots, model, seed=ATTRIBUTION_SEED)
    edgeTimePath = os.path.join(directory, "edge_time_attribution.csv")
    rows = [dict(row, dataset=name, model=type(model).__name__,
                 seed=ATTRIBUTION_SEED) for row in edgeTime["rows"]]
    pd.DataFrame(rows).drop(columns=["edge"]).to_csv(edgeTimePath,
                                                     index=False)
    with open(os.path.join(directory, "provenance.json"), "w",
              encoding="utf-8") as handle:
        json.dump({
            "dataset": name,
            "model": type(model).__name__,
            "seed": ATTRIBUTION_SEED,
            "snapshots": len(snapshots),
            "edge_method": edges["method_note"],
            "edge_coverage": edges["coverage"],
            "edge_selection": edges["selection"],
            "node_coverage": nodes["coverage"],
            "edge_time_method": edgeTime["method_note"],
            "edge_time_rows_persisted": len(edgeTime["rows"]),
            "edge_time_selection_rule":
                "none at persistence time - every edge at every snapshot is "
                "stored; fig12 applies a display-only top-K",
            "edge_time_snapshots_with_any_response":
                edgeTime["snapshots_with_any_response"],
            "edge_time_all_zero": edgeTime["all_zero"],
        }, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return {"edge": edgePath, "node": nodePath, "edge_time": edgeTimePath,
            "edge_trend": trendPath}


def figure8Dependence(paths, path):
    ''' FIG 8 - dependence: a structural property against the measured
    impact of perturbing that element.

    NOT a feature-importance plot. Nothing here is a learned feature
    attribution; x is a property the graph actually has and y is one
    measured prediction difference from occluding that element.

    The two properties are the ones the persisted schema genuinely carries:
    `total_degree` for nodes and `snapshots_present` for edges. No property
    is synthesised to fill an axis.

    Panels are separate per element type because a node degree and an edge
    presence count are different quantities, and the impacts come from
    different occlusions - pooling them would be the same unit error the
    concept figures avoid.
    '''
    panels = [("node", paths["node"], "total_degree", "node total degree"),
              ("edge", paths["edge"], "snapshots_present",
               "edge: snapshots present")]
    fig, axes = plt.subplots(1, len(panels), figsize=(5.4 * len(panels), 3.6),
                             squeeze=False)
    summary = []
    for ax, (element, source, xColumn, xLabel) in zip(axes[0], panels):
        frame = pd.read_csv(source)
        frame = frame[np.isfinite(frame["impact"])
                      & np.isfinite(frame[xColumn])]
        # Both properties are discrete, so many elements land on exactly the
        # same (x, y). Plain markers would hide that: 139 edges would look
        # like seven. Marker AREA encodes how many coincide - it adds no
        # value that is not in the data and moves no point off its true
        # coordinates, which jitter would.
        tally = frame.groupby([xColumn, "impact"]).size().reset_index(
            name="count")
        ax.scatter(tally[xColumn], tally["impact"],
                   s=22 + 16 * tally["count"], alpha=0.8,
                   c=[POSITIVE if v > 0 else NEGATIVE if v < 0 else NEUTRAL
                      for v in tally["impact"]],
                   edgecolors="black", linewidths=0.3, zorder=3)
        for row in tally.itertuples():
            if row.count > 1:
                ax.annotate(str(row.count),
                            (getattr(row, xColumn), row.impact),
                            ha="center", va="center", fontsize=5.5,
                            zorder=4, color="white", fontweight="bold")
        ax.axhline(0, color="black", linewidth=0.9, zorder=2)
        ax.set_xlabel(xLabel, fontsize=8)
        ax.set_ylabel("impact (prediction difference)", fontsize=8)
        coverage = frame["coverage"].iloc[0] if len(frame) else float("nan")
        ax.set_title(f"{frame['dataset'].iloc[0]} - {element} occlusion\n"
                     f"n={len(frame)}, coverage={coverage:.0%}, "
                     f"model={frame['model'].iloc[0]}", fontsize=8)
        summary.append({"element": element, "x": xColumn, "n": len(frame),
                        "source": source})
    fig.suptitle("Dependence: structural property against measured "
                 "occlusion impact\nEach point is one element; impact is a "
                 "measured prediction difference, not a learned attribution.",
                 fontsize=9.5)
    fig.subplots_adjust(top=0.78, wspace=0.28)
    savePublicationFigure(fig, path)
    plt.close(fig)
    return summary


def _beeswarmOffsets(values, pointWidth):
    ''' A real beeswarm: deterministic, collision-free vertical packing.

    For each value in ascending order, try candidate offsets 0, +s, -s,
    +2s, -2s ... and take the FIRST that collides with no already-placed
    point, where two points collide when they are within pointWidth on x
    and within one step on y. Ascending order makes the result independent
    of input order, so the layout is reproducible.

    This is NOT jitter. Nothing random is involved, and no seed is needed:
    the same values always produce the same offsets.
    '''
    order = sorted(range(len(values)), key=lambda i: (values[i], i))
    step = 1.0
    placed = []                       # (value, offset) already positioned
    offsets = [0.0] * len(values)
    for index in order:
        value = values[index]
        level = 0
        while True:
            for candidate in ({0.0} if not level else {level * step,
                                                       -level * step}):
                clash = any(abs(value - other) < pointWidth
                            and abs(candidate - taken) < step * 0.999
                            for other, taken in placed)
                if not clash:
                    offsets[index] = candidate
                    placed.append((value, candidate))
                    break
            else:
                level += 1
                continue
            break
    return offsets


def figure9TrueBeeswarm(datasets, path):
    ''' FIG 9 - a true beeswarm, not a jittered strip plot.

    Points are packed by _beeswarmOffsets so that none overlaps, which
    makes the DENSITY of the distribution readable - the thing a jittered
    scatter only approximates. The packing is deterministic.

    Every valid row is drawn; nothing is thinned. Semantic groups get
    separate panels, because the x-axis is an impact and the groups'
    perturbation units are not comparable.
    '''
    groups = semanticRows()
    fig = plt.figure(figsize=(6.6 * len(datasets),
                              1.1 * sum(max(len(c), 1) for _, c, _ in groups)
                              + 2.4))
    grid = fig.add_gridspec(len(groups), len(datasets),
                            height_ratios=[max(len(c), 1)
                                           for _, c, _ in groups],
                            wspace=0.22, hspace=0.62, top=0.82, bottom=0.09,
                            left=0.20, right=0.985)
    drawn = 0
    for rowIndex, (label, concepts, note) in enumerate(groups):
        for columnIndex, (name, data) in enumerate(datasets.items()):
            ax = fig.add_subplot(grid[rowIndex, columnIndex])
            valid = _valid(data["results"])
            span = valid["impact"].abs().max() or 1.0
            empty = 0
            for position, concept in enumerate(concepts):
                values = [float(v) for v in
                          valid[valid["transformation"] == concept]["impact"]
                          if np.isfinite(v)]
                if not values:
                    ax.text(0.5, position, "no valid obs. (n=0)",
                            transform=ax.get_yaxis_transform(), ha="center",
                            va="center", fontsize=6.5, color=NEUTRAL,
                            style="italic")
                    empty += 1
                    continue
                offsets = _beeswarmOffsets(values, pointWidth=span * 0.022)
                scale = 0.34 / max(1.0, max(abs(o) for o in offsets))
                ax.scatter(values, [position + o * scale for o in offsets],
                           s=16, alpha=0.85,
                           c=[POSITIVE if v > 0 else NEGATIVE if v < 0
                              else NEUTRAL for v in values],
                           edgecolors="black", linewidths=0.2, zorder=3)
                ax.annotate(f"n={len(values)}", (0.0, position),
                            xycoords=ax.get_yaxis_transform(),
                            textcoords="offset points", xytext=(3, 11),
                            ha="left", fontsize=6, color="#555555")
                drawn += len(values)
            if empty < len(concepts):
                ax.axvline(0, color="black", linewidth=0.9, zorder=2)
            else:
                # Nothing measured: no tick range, so an empty panel cannot
                # read as a measured scale.
                ax.set_xticks([])
            ax.set_yticks(range(len(concepts)))
            ax.set_yticklabels(concepts, fontsize=7)
            ax.set_ylim(-0.7, len(concepts) - 0.3)
            ax.tick_params(axis="x", labelsize=6.5)
            if columnIndex or len(concepts) == 1:
                ax.tick_params(labelleft=False)
            if not rowIndex:
                ax.set_title(name, fontsize=8.5)
            if rowIndex == len(groups) - 1:
                ax.set_xlabel("impact", fontsize=8)
            if not columnIndex:
                ax.annotate(f"{label}\n({note})", (-0.30, 0.5),
                            xycoords="axes fraction", ha="center",
                            va="center", fontsize=7, fontweight="bold")
    fig.suptitle("Beeswarm of TGAP impacts, valid rows only\n"
                 "Points are packed to avoid overlap by a deterministic "
                 "layout - no random jitter. Semantic groups are shown in\n"
                 "separate rows because their perturbation units are not "
                 "comparable; no ordering across rows is implied.",
                 fontsize=9.3)
    savePublicationFigure(fig, path)
    plt.close(fig)
    return {"points": drawn}


def figure10PublicationBoxplot(datasets, path):
    ''' FIG 10 - distribution of impacts per model, valid rows only.

    Models get their OWN panel, because their prediction scales differ and
    a box drawn across them would describe nothing. Within a panel only the
    mutually commensurable concepts are boxed together; the other concepts
    keep their own rows for the same reason as everywhere else.

    n is printed on every box. Individual observations are overlaid, so a
    box summarising three points cannot pass for a distribution.
    '''
    groups = semanticGroups()
    concepts = list(groups.get(COMMENSURABLE, []))
    models = sorted({m for data in datasets.values()
                     for m in _valid(data["results"])["model"].unique()})
    fig, axes = plt.subplots(len(datasets), len(models),
                             figsize=(2.0 * len(models) + 1.6,
                                      2.5 * len(datasets) + 1.6),
                             squeeze=False)
    summary = []
    for rowIndex, (name, data) in enumerate(datasets.items()):
        valid = _valid(data["results"])
        for columnIndex, model in enumerate(models):
            ax = axes[rowIndex][columnIndex]
            cell = valid[valid["model"] == model]
            series, labels = [], []
            for concept in concepts:
                values = [float(v) for v in
                          cell[cell["transformation"] == concept]["impact"]
                          if np.isfinite(v)]
                series.append(values)
                labels.append(concept)
                summary.append({"dataset": name, "model": model,
                                "concept": concept, "n": len(values)})
            populated = [s for s in series if s]
            if populated:
                ax.boxplot(series, vert=False, widths=0.55,
                           patch_artist=True, showfliers=False,
                           medianprops=dict(color="black", linewidth=1.2),
                           boxprops=dict(facecolor="#dfe7ef",
                                         edgecolor="#444444", linewidth=0.8),
                           whiskerprops=dict(color="#444444", linewidth=0.8),
                           capprops=dict(color="#444444", linewidth=0.8))
                for position, values in enumerate(series, start=1):
                    if values:
                        offsets = _beeswarmOffsets(
                            values, pointWidth=(max(map(abs, values)) or 1.0)
                            * 0.03)
                        scale = 0.18 / max(1.0,
                                           max(abs(o) for o in offsets))
                        ax.scatter(values,
                                   [position + o * scale for o in offsets],
                                   s=9, alpha=0.8, zorder=4,
                                   c=[POSITIVE if v > 0 else NEGATIVE
                                      if v < 0 else NEUTRAL for v in values],
                                   edgecolors="none")
                    ax.annotate(f"n={len(values)}", (0.0, position),
                                xycoords=ax.get_yaxis_transform(),
                                textcoords="offset points", xytext=(3, 10),
                                ha="left", fontsize=5.6, color="#555555")
                ax.axvline(0, color="black", linewidth=0.9, zorder=2)
            else:
                ax.text(0.5, 0.5, "no valid obs. (n=0)", ha="center",
                        va="center", transform=ax.transAxes, fontsize=7,
                        color=NEUTRAL, style="italic")
                ax.set_xticks([])
            ax.set_yticks(range(1, len(labels) + 1))
            ax.set_yticklabels(labels, fontsize=6.5)
            if columnIndex:
                ax.tick_params(labelleft=False)
            ax.tick_params(axis="x", labelsize=6)
            if not rowIndex:
                ax.set_title(model, fontsize=6.8)
            if rowIndex == len(datasets) - 1:
                ax.set_xlabel("impact", fontsize=7)
            if not columnIndex:
                ax.annotate(name, (-0.52, 0.5), xycoords="axes fraction",
                            ha="center", va="center", fontsize=7.4,
                            fontweight="bold", rotation=90)
    fig.suptitle("Distribution of TGAP impacts per model, valid rows only\n"
                 "One panel per model because prediction scales differ; only "
                 "the commensurable relative-delta concepts share a panel.\n"
                 "Boxes show median and quartiles; every observation is "
                 "overlaid and n is printed. No ranking is implied.",
                 fontsize=9.3)
    fig.subplots_adjust(top=0.84, bottom=0.08, left=0.16, right=0.99,
                        wspace=0.18, hspace=0.42)
    savePublicationFigure(fig, path)
    plt.close(fig)
    return summary


def figure11LocalBar(paths, path, topK=LOCAL_BAR_TOP_K, source="edge_trend"):
    ''' FIG 11 - diverging bar chart for ONE local explanation.

    Sorted by |impact| WITHIN THIS SINGLE EXPLANATION. That is a local
    ordering of elements in one graph under one model - it is not a concept
    ranking and says nothing about any other explanation.

    TOP-K IS EXPLICIT: the title states K and how many elements exist, and
    the complete attribution stays in edge_attribution.csv. Nothing is
    silently dropped.
    '''
    frame = pd.read_csv(paths[source])
    frame = frame[np.isfinite(frame["impact"])]
    total = len(frame)
    # Deterministic: |impact| descending, ties broken by endpoint ids.
    frame = frame.assign(magnitude=frame["impact"].abs()).sort_values(
        ["magnitude", "u", "v"], ascending=[False, True, True])
    nonZero = int((frame["impact"] != 0).sum())
    # Never pad the chart with exact zeros. Drawing K bars when only
    # `nonZero` elements moved the prediction fills most of the axis with
    # invisible bars and makes a complete result look like a broken figure.
    # The count of exact zeros is stated in the title instead, so nothing is
    # hidden - a zero here is a measured no-effect, not a missing value.
    shown = frame.head(min(topK, nonZero) or 1).iloc[::-1]
    labels = [f"({int(r.u)}, {int(r.v)})" for r in shown.itertuples()]

    fig, ax = plt.subplots(figsize=(7.4, 0.27 * len(shown) + 2.2))
    ax.barh(range(len(shown)), shown["impact"],
            color=[POSITIVE if v > 0 else NEGATIVE if v < 0 else NEUTRAL
                   for v in shown["impact"]],
            edgecolor="black", linewidth=0.4, alpha=0.9)
    ax.axvline(0, color="black", linewidth=1.0, zorder=3)
    ax.set_yticks(range(len(shown)))
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_xlabel("impact of removing this edge "
                  "(prediction difference)", fontsize=8)
    ax.set_ylabel("edge (u, v)", fontsize=8)
    ax.set_title(
        f"Local explanation: per-edge occlusion impact\n"
        f"{frame['dataset'].iloc[0]}, model={frame['model'].iloc[0]}, "
        f"seed={int(frame['seed'].iloc[0])}\n"
        f"Showing top {len(shown)} of {nonZero} edges with a non-zero "
        f"impact (top-K cap {topK}); the other {total - nonZero} of {total} "
        f"evaluated edges have an impact of exactly 0.\n"
        f"Sorted by |impact| WITHIN this explanation only - a local "
        f"ordering of elements, not a concept ranking.\n"
        f"Complete attribution: attribution/{os.path.basename(paths[source])}",
        fontsize=8.2)
    fig.subplots_adjust(top=0.84, left=0.17, right=0.97, bottom=0.12)
    savePublicationFigure(fig, path)
    plt.close(fig)
    return {"shown": len(shown), "total": total, "non_zero": nonZero,
            "top_k": topK}


def figure12TemporalEdgeTime(paths, path, topK=EDGE_TIME_TOP_K):
    ''' FIG 12 - edge-time attribution: one point per (edge, snapshot).

    x = snapshot index, y = edge, colour = impact on a diverging scale
    centred at zero. Nothing is summed over time: each point is its own
    measured prediction difference, and the figure makes no additivity
    claim, because edgeTimeAttribution does not support one.

    A flat result is a RESULT. This model reads only the last snapshot, so
    every earlier (edge, snapshot) impact is exactly zero - the figure says
    so in the caption rather than showing blank cells that look like
    missing data.
    '''
    frame = pd.read_csv(paths["edge_time"])
    frame = frame[np.isfinite(frame["impact"])]
    allEdges = {(int(r.u), int(r.v)) for r in frame.itertuples()}

    # DISPLAY-ONLY top-K. The persisted file holds every (edge, snapshot);
    # this picks which rows to draw. The rule is deterministic and stated in
    # the caption: edges ranked by their largest |impact| at any snapshot,
    # then by how many snapshots they appear in, then by edge id. No
    # sampling, so no seed governs the selection.
    ranking = frame.assign(magnitude=frame["impact"].abs()).groupby(
        ["u", "v"]).agg(peak=("magnitude", "max"),
                        seen=("snapshot_index", "count")).reset_index()
    ranking = ranking.sort_values(["peak", "seen", "u", "v"],
                                  ascending=[False, False, True, True])
    edges = sorted((int(r.u), int(r.v))
                   for r in ranking.head(topK).itertuples())
    frame = frame[[(int(r.u), int(r.v)) in set(edges)
                   for r in frame.itertuples()]]
    index = {edge: position for position, edge in enumerate(edges)}
    span = frame["impact"].abs().max()
    limit = span if span > 0 else 1.0

    fig, ax = plt.subplots(figsize=(7.8, 0.26 * len(edges) + 2.6))
    scatter = ax.scatter(
        frame["snapshot_index"],
        [index[(int(r.u), int(r.v))] for r in frame.itertuples()],
        c=frame["impact"], cmap="RdBu_r", vmin=-limit, vmax=limit,
        s=66, edgecolors="black", linewidths=0.35, zorder=3)
    ax.set_yticks(range(len(edges)))
    ax.set_yticklabels([f"({u}, {v})" for u, v in edges], fontsize=6.5)
    ax.set_xticks(sorted(frame["snapshot_index"].unique()))
    ax.set_xlabel("snapshot index (time)", fontsize=8)
    ax.set_ylabel("edge (u, v)", fontsize=8)
    ax.grid(True, axis="x", alpha=0.25)
    bar = fig.colorbar(scatter, ax=ax, fraction=0.03, pad=0.02)
    bar.set_label("impact of removing this edge from this snapshot",
                  fontsize=7.5)

    responsive = sorted(frame[frame["impact"] != 0]["snapshot_index"].unique())
    total = len(pd.read_csv(paths["edge_time"]))
    where = (", ".join(str(int(s)) for s in responsive) if responsive
             else "none - this model has no temporal dependence on these edges")
    ax.set_title(
        "TGAP edge-time attribution: impact of removing one edge from one "
        "snapshot\n"
        f"{frame['dataset'].iloc[0]}, model={frame['model'].iloc[0]} - "
        f"showing {len(edges)} of {len(allEdges)} edges "
        f"({len(frame)} of {total} edge-time observations)\n"
        f"DISPLAY-ONLY selection: largest |impact| at any snapshot, then "
        f"snapshots present, then edge id. Deterministic, never sampled.\n"
        f"Complete attribution: attribution/edge_time_attribution.csv. "
        f"Snapshots with any non-zero response: {where}\n"
        "TGAP edge-time attribution is shown here; this visualization is "
        "inspired by temporal XAI visualization\nstyles but is not a TSHAP "
        "implementation. No additivity across time is claimed.",
        fontsize=7.8)
    fig.subplots_adjust(top=0.78, left=0.14, right=0.99, bottom=0.11)
    savePublicationFigure(fig, path)
    plt.close(fig)
    return {"points": len(frame), "edges": len(edges),
            "edges_total": len(allEdges), "observations_total": total,
            "top_k": topK,
            "snapshots_with_response": [int(s) for s in responsive]}


SUPERSEDED_NOTICE = """# Superseded figures

Retained for the record. **None of these is the paper's global-impact
figure.** That is `../fig1_final_model_separated_impacts.png`.

| figure | why it was replaced |
|---|---|
| `fig1_concept_impacts` | Pooled mean abs(impact) across six models with different prediction scales, AND placed all five concepts on one axis. Both are invalid. |
| `fig2_model_concept_heatmap` | Kept models separate, but normalised each model row across all five concepts, so non-commensurable concepts shared one colour scale. |
| `fig1A_commensurable_concept_impacts` | Fixed the concept axis by dropping the non-commensurable concepts, but still pooled a mean across models. |
| `fig1B_grouped_concept_impacts` | Separated the semantic groups, but still pooled a mean across models. |
| `fig2_grouped_semantic_heatmap` | Separated the semantic groups, but still normalised within a model row. |

The common defect in all five is aggregation across models. The final figure
removes it: every point is one valid CSV row, and every panel carries its own
axis.
"""


def _writeSupersededNotice(path):
    ''' Say plainly why these figures are kept and must not be used. '''
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(SUPERSEDED_NOTICE)
    return path


def writeFigureMetadata(path):
    ''' Machine-readable comparability metadata for the candidate figures.

    Exists so a caption, a reviewer or a later script can establish which
    figure permits cross-concept numerical comparison WITHOUT re-reading the
    plotting code. Concept membership is taken from semanticGroups(), so
    this file cannot drift from the figures it describes.
    '''
    groups = semanticGroups()
    commensurable = groups.get(COMMENSURABLE, [])
    other = groups.get(NOT_COMMENSURABLE, [])
    sources = [os.path.join(RESULTS, d, "tgap_results.csv")
               for d in CASE_STUDIES]
    payload = {
        "comparability_rule": {
            "derived_by": "realdata.run_tgn_stability.comparabilityOf",
            "note": "The stored delta_mode column is NOT the grouping key: "
                    "it reads 'relative' for Centralization, whose achieved "
                    "delta is a rewiring fraction.",
            "groups": {COMMENSURABLE: commensurable,
                       NOT_COMMENSURABLE: other},
        },
        "figures": [
            {
                "figure": "fig1_final_model_separated_impacts",
                "candidate": "final",
                "status": "MAIN publication global-impact figure",
                "included_concepts": commensurable + other,
                "excluded_concepts": [],
                "delta_semantics": {**{c: COMMENSURABLE for c in commensurable},
                                    **{c: NOT_COMMENSURABLE for c in other}},
                "cross_concept_numerical_comparison_allowed": False,
                "cross_model_aggregation": "none - every point is one valid "
                                           "CSV row; nothing is averaged, "
                                           "normalised or ranked",
                "axis_policy": "one independent linear x-axis per "
                               "(dataset, model, semantic group) panel",
                "comparability_scope":
                    "within row 1 of a single panel only, where the model "
                    "and dataset are fixed and the three concepts share "
                    "relative-delta semantics; nowhere else",
                "source_csv": sources,
                "generation_function":
                    "realdata.make_publication.figure1FinalModelSeparated",
                "formats": ["png", "pdf"],
            },
            {
                "figure": "fig8_dependence",
                "candidate": "dependence",
                "status": "element-level dependence",
                "included_concepts": [],
                "excluded_concepts": [],
                "delta_semantics": {},
                "x_variable": ["total_degree (node)",
                               "snapshots_present (edge)"],
                "y_variable": "impact (measured occlusion prediction "
                              "difference)",
                "cross_concept_numerical_comparison_allowed": False,
                "comparability_scope": "within one panel only; node and edge "
                                       "occlusions are different quantities "
                                       "and are never pooled",
                "source_csv": [os.path.join(ATTRIBUTION,
                                            "node_attribution.csv"),
                               os.path.join(ATTRIBUTION,
                                            "edge_attribution.csv")],
                "generation_function":
                    "realdata.make_publication.figure8Dependence",
                "formats": ["png", "pdf"],
            },
            {
                "figure": "fig9_true_beeswarm",
                "candidate": "beeswarm",
                "status": "deterministic non-overlapping packing, no jitter",
                "included_concepts": commensurable + other,
                "excluded_concepts": [],
                "delta_semantics": {**{c: COMMENSURABLE for c in commensurable},
                                    **{c: NOT_COMMENSURABLE for c in other}},
                "cross_concept_numerical_comparison_allowed": False,
                "comparability_scope": "within a semantic row only",
                "layout_algorithm":
                    "realdata.make_publication._beeswarmOffsets - ascending "
                    "value order, first non-colliding offset; deterministic "
                    "and seedless",
                "source_csv": sources,
                "generation_function":
                    "realdata.make_publication.figure9TrueBeeswarm",
                "formats": ["png", "pdf"],
            },
            {
                "figure": "fig10_publication_boxplot",
                "candidate": "boxplot",
                "status": "per-model distributions, valid rows only",
                "included_concepts": commensurable,
                "excluded_concepts": other,
                "delta_semantics": {c: COMMENSURABLE for c in commensurable},
                "cross_concept_numerical_comparison_allowed": False,
                "comparability_scope": "within one model panel only; no box "
                                       "spans two models",
                "source_csv": sources,
                "generation_function":
                    "realdata.make_publication.figure10PublicationBoxplot",
                "formats": ["png", "pdf"],
            },
            {
                "figure": "fig11_local_bar",
                "candidate": "local",
                "status": "ONE local explanation; local ordering only",
                "included_concepts": [],
                "excluded_concepts": [],
                "delta_semantics": {},
                "x_variable": "impact (edge occlusion)",
                "y_variable": "edge (u, v)",
                "selection_rule": f"top {LOCAL_BAR_TOP_K} by |impact|, ties "
                                  f"broken by endpoint id; complete "
                                  f"attribution retained in the source CSV",
                "cross_concept_numerical_comparison_allowed": False,
                "comparability_scope": "elements within this single "
                                       "explanation; not a concept ranking",
                "source_csv": [os.path.join(ATTRIBUTION,
                                            "edge_attribution_trend.csv")],
                "generation_function":
                    "realdata.make_publication.figure11LocalBar",
                "formats": ["png", "pdf"],
            },
            {
                "figure": "fig12_temporal_edge_time",
                "candidate": "edge_time",
                "status": "TGAP edge-time attribution; NOT a TSHAP "
                          "implementation",
                "included_concepts": [],
                "excluded_concepts": [],
                "delta_semantics": {},
                "x_variable": "snapshot_index",
                "y_variable": "edge (u, v)",
                "colour_variable": "impact, diverging around zero",
                "selection_rule":
                    f"display-only top {EDGE_TIME_TOP_K} edges by largest "
                    f"|impact| at any snapshot, then snapshots present, then "
                    f"edge id; deterministic, never sampled. The persisted "
                    f"CSV holds every (edge, snapshot).",
                "additivity_claimed": False,
                "cross_concept_numerical_comparison_allowed": False,
                "comparability_scope": "one measured prediction difference "
                                       "per (edge, snapshot); nothing is "
                                       "summed over time",
                "source_csv": [os.path.join(ATTRIBUTION,
                                            "edge_time_attribution.csv")],
                "generation_function":
                    "realdata.make_publication.figure12TemporalEdgeTime",
                "formats": ["png", "pdf"],
            },
            {
                "figure": "superseded/fig1A_commensurable_concept_impacts",
                "candidate": "A",
                "status": "SUPERSEDED - pooled a mean across models",
                "included_concepts": commensurable,
                "excluded_concepts": other,
                "delta_semantics": {c: COMMENSURABLE for c in commensurable},
                "cross_concept_numerical_comparison_allowed": True,
                "comparability_scope": "all concepts shown are commensurable",
                "source_csv": sources,
                "generation_function":
                    "realdata.make_publication.figure1ACommensurable",
                "formats": ["png", "pdf"],
            },
            {
                "figure": "superseded/fig1B_grouped_concept_impacts",
                "candidate": "B",
                "status": "SUPERSEDED - pooled a mean across models",
                "included_concepts": commensurable + other,
                "excluded_concepts": [],
                "delta_semantics": {**{c: COMMENSURABLE for c in commensurable},
                                    **{c: NOT_COMMENSURABLE for c in other}},
                "cross_concept_numerical_comparison_allowed": False,
                "comparability_scope": "within a group only; the two groups "
                                       "never share an axis",
                "source_csv": sources,
                "generation_function":
                    "realdata.make_publication.figure1BGrouped",
                "formats": ["png", "pdf"],
            },
            {
                "figure": "superseded/fig2_grouped_semantic_heatmap",
                "candidate": "C",
                "status": "SUPERSEDED - normalised within a model row",
                "included_concepts": commensurable + other,
                "excluded_concepts": [],
                "delta_semantics": {**{c: COMMENSURABLE for c in commensurable},
                                    **{c: NOT_COMMENSURABLE for c in other}},
                "cross_concept_numerical_comparison_allowed": False,
                "comparability_scope": "colour comparable within the "
                                       "commensurable block only; the other "
                                       "block encodes sign only; printed "
                                       "values are the real impacts",
                "source_csv": sources,
                "generation_function":
                    "realdata.make_publication"
                    ".figure2CGroupedSemanticHeatmap",
                "formats": ["png", "pdf"],
            },
        ],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return payload


def _asMarkdown(frame):
    ''' Render a DataFrame as a markdown table.

    Written by hand rather than via DataFrame.to_markdown, which needs the
    optional `tabulate` package. A publication-output convenience is not
    worth adding a dependency to a research package's install - one that
    every user would then have to satisfy for a feature most never use.
    '''
    columns = list(frame.columns)
    lines = ["| " + " | ".join(str(c) for c in columns) + " |",
             "|" + "|".join("---" for _ in columns) + "|"]
    for _, row in frame.iterrows():
        cells = []
        for column in columns:
            value = row[column]
            if value is None or (isinstance(value, float) and value != value):
                cells.append("")
            elif isinstance(value, float):
                cells.append(f"{value:g}")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def writeTables(datasets):
    ''' Publication tables as csv AND markdown, so they can be pasted
    directly into a manuscript. '''
    rows = []
    for name in sorted(os.listdir(RESULTS)):
        directory = os.path.join(RESULTS, name)
        if not os.path.isdir(directory):
            continue
        summaryPath = os.path.join(directory, "summary.json")
        if not os.path.exists(summaryPath):
            continue
        with open(summaryPath, encoding="utf-8") as handle:
            summary = json.load(handle)
        rows.append({
            "dataset": summary["dataset"],
            "raw_nodes": summary["raw_nodes"],
            "retained_nodes": summary["retained_nodes"],
            "nodes_retained_pct": summary["nodes_retained_pct"],
            "raw_events": summary["raw_events"],
            "retained_events": summary["retained_events"],
            "snapshots": summary["snapshot_count"],
            "partition": "/".join(map(str, summary["partition_sizes"])),
            "community_source": summary["community_mode"],
            "bridge_width_min": summary["bridge_width_min"],
            "bridge_width_max": summary["bridge_width_max"],
        })
    table1 = pd.DataFrame(rows)

    main = []
    for name, data in datasets.items():
        valid = _valid(data["results"])
        subset = valid[(valid["requested_delta"] == 0.1)
                       & (valid["direction"] == "increase")]
        for _, row in subset.iterrows():
            main.append({"dataset": name, "model": row["model"],
                         "concept": row["transformation"],
                         "achieved_delta": round(row["achieved_delta"], 6),
                         "impact": round(row["impact"], 6)})
    table2 = pd.DataFrame(main)

    table3 = pd.DataFrame()
    tgnPath = os.path.join(TGN_RESULTS, "email_eu_core", "tgap_results.csv")
    if os.path.exists(tgnPath):
        tgn = pd.read_csv(tgnPath)
        # DATA INTEGRITY: valid rows ONLY. The TGN runner is validity-gated,
        # but this table was previously built from the raw file, so a
        # saturated or edge-count-infeasible row could reach the paper. The
        # raw CSV deliberately keeps every row for transparency; the
        # publication table must not. _valid() is the same helper every other
        # publication table uses, so the rule cannot diverge between tables.
        tgn = _valid(tgn)
        table3 = tgn[(tgn["requested_delta"] == 0.1)
                     & (tgn["direction"] == "increase")][
            ["dataset", "transformation", "achieved_delta",
             "baseline_prediction", "after_prediction", "impact"]].round(6)
        # SUPERSESSION: every impact here is ONE seed. The five-seed run
        # (table9) shows Churn's impact has sd 2.79 on a mean of 0.013 and
        # changes sign between seeds, so this row's -1.62 is one draw, not a
        # property of the model. Rows stay in registry order, never sorted by
        # impact, because the achieved deltas are in incompatible units
        # (Churn 0.0067 against Bridge Trend 5.83) - ordering by |impact|
        # would read as a ranking the units do not support.
        table3 = table3.assign(
            seeds=1,
            single_seed_see_table9=True)

    validity = []
    for name in sorted(os.listdir(RESULTS)):
        directory = os.path.join(RESULTS, name)
        summaryPath = os.path.join(directory, "summary.json")
        if not os.path.isdir(directory) or not os.path.exists(summaryPath):
            continue
        with open(summaryPath, encoding="utf-8") as handle:
            summary = json.load(handle)
        validity.append({
            "dataset": summary["dataset"],
            "explanation_rows": summary["explanation_rows"],
            "valid_rows": summary["valid_rows"],
            "invalid_rows": summary["invalid_rows"],
            "valid_pct": round(100 * summary["valid_rows"]
                               / summary["explanation_rows"], 1),
            **{f"excluded_{k}": v for k, v
               in summary["invalid_rows_by_status"].items()},
        })
    table4 = pd.DataFrame(validity)

    for name, frame in (("table1_datasets", table1),
                        ("table2_main_results", table2),
                        ("table3_tgn", table3),
                        ("table4_validity", table4)):
        if frame.empty:
            continue
        frame.to_csv(os.path.join(OUTPUT, f"{name}.csv"), index=False)
        with open(os.path.join(OUTPUT, f"{name}.md"), "w",
                  encoding="utf-8") as handle:
            handle.write(_asMarkdown(frame))
    return {"table1": len(table1), "table2": len(table2),
            "table3": len(table3), "table4": len(table4)}


def tgnTables():
    ''' Seed stability and matched comparison, as publication tables.

    Both are built from the machine-readable outputs of
    realdata/run_tgn_stability.py - never from numbers typed by hand.
    '''
    tables = {}
    stabilityPath = os.path.join(TGN_STABILITY, "seed_stability.csv")
    if os.path.exists(stabilityPath):
        stability = pd.read_csv(stabilityPath)
        tables["table6_tgn_seed_stability"] = stability[
            ["quantity", "n", "mean", "std", "min", "max", "per_seed"]]

    conceptPath = os.path.join(TGN_STABILITY, "per_concept_stability.csv")
    if os.path.exists(conceptPath):
        # Generated from per-seed machine-readable rows, never typed in.
        # Column order puts `sufficient` and the comparability flag beside
        # the statistics, so a reader cannot take a mean without seeing how
        # many seeds produced it or whether the concept may be compared.
        tables["table9_tgn_concept_stability"] = pd.read_csv(conceptPath)[
            ["concept", "direction", "requested_delta", "delta_mode",
             "valid_seeds", "sufficient", "mean_impact", "std_impact",
             "min_impact", "max_impact", "mean_achieved_delta",
             "std_achieved_delta", "comparable_with_relative_concepts"]]

    matchedPath = os.path.join(TGN_STABILITY, "matched_comparison.csv")
    if os.path.exists(matchedPath):
        matched = pd.read_csv(matchedPath)
        # Comparable pairs only in the publication table, with BOTH sides
        # shown side by side. There is deliberately no ordering column: a
        # matched comparison reports two numbers at a matched perturbation,
        # it does not declare a winner.
        comparable = matched[matched["comparable"]].copy()
        if not comparable.empty:
            summary = comparable.groupby(
                ["concept_a", "concept_b", "direction"]).agg(
                seeds=("seed", "nunique"),
                mean_achieved_a=("achieved_delta_a", "mean"),
                mean_achieved_b=("achieved_delta_b", "mean"),
                mean_impact_a=("impact_a", "mean"),
                mean_impact_b=("impact_b", "mean"),
                mean_relative_gap=("relative_gap", "mean"),
            ).round(6).reset_index()
            tables["table7_tgn_matched_comparison"] = summary
        # The incomparable pairs are themselves a result and are published.
        reasons = matched[~matched["comparable"]].groupby(
            ["concept_a", "concept_b"])["reason"].first().reset_index()
        reasons["comparable"] = False
        tables["table8_tgn_not_comparable"] = reasons
    return tables


def figureTgnSeedStability(path):
    ''' The one TGN figure. Held-out performance across five seeds.

    Chosen deliberately: AUC, AP and accuracy share one scale (0-1, chance
    0.5), so plotting them together compares commensurable quantities. The
    concept impacts do NOT share units, so they are not plotted against one
    another anywhere - that is the figure this project must not produce.
    '''
    path_csv = os.path.join(TGN_STABILITY, "seed_stability.csv")
    if not os.path.exists(path_csv):
        return False
    stability = pd.read_csv(path_csv)
    wanted = ["auc", "average_precision", "accuracy"]
    rows = stability[stability["quantity"].isin(wanted)]
    if rows.empty:
        return False

    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    for offset, (_, row) in enumerate(rows.iterrows()):
        values = [v for v in eval(row["per_seed"]) if v is not None]
        xs = [offset + (i - (len(values) - 1) / 2) * 0.08
              for i in range(len(values))]
        ax.scatter(xs, values, s=42, color=POSITIVE, zorder=3,
                   edgecolors="black", linewidths=0.4)
        ax.hlines(row["mean"], offset - 0.25, offset + 0.25,
                  color="black", linewidth=1.6, zorder=4)
        ax.text(offset, row["max"] + 0.025,
                f"mean {row['mean']:.3f}\nsd {row['std']:.3f}",
                ha="center", fontsize=7)
    ax.axhline(0.5, color=NEUTRAL, linestyle="--", linewidth=1)
    ax.text(len(rows) - 0.5, 0.508, "chance", fontsize=7, color=NEUTRAL,
            ha="right")
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels(["AUC", "average precision", "accuracy"])
    ax.set_ylim(0.45, 0.85)
    ax.set_ylabel("held-out score")
    ax.set_title("TGN held-out performance across 5 fixed seeds\n"
                 "(each point is one seed; bar is the mean)", fontsize=11)
    savePublicationFigure(fig, path)
    plt.close(fig)
    return True


def main():
    os.makedirs(OUTPUT, exist_ok=True)
    available = [d for d in CASE_STUDIES
                 if os.path.exists(os.path.join(RESULTS, d, "summary.json"))]
    if not available:
        print(f"no results under {RESULTS}; run "
              f"`python -m realdata.run_real_data` first")
        return None
    datasets = {name: _load(name) for name in available}

    print("=" * 66)
    print("PUBLICATION FIGURES AND TABLES")
    print("=" * 66)
    # THE global-impact figure. Descriptive and model-separated: nothing is
    # pooled across models, and no axis spans two models or two datasets.
    final = figure1FinalModelSeparated(
        datasets,
        os.path.join(OUTPUT, "fig1_final_model_separated_impacts.png"))
    print(f"  fig1_final_model_separated_impacts.png   MAIN global-impact "
          f"figure, {len(final['models'])} models x {len(final['rows'])} rows")

    # SUPERSEDED. fig1/fig2 pooled impacts across six models with different
    # prediction scales and put all five concepts on one axis; candidates
    # A/B/C were the intermediate designs that fixed only the second half of
    # that. They are kept - they are part of the record - but they are
    # written to a subdirectory so nothing downstream can pick one up as the
    # paper's global-impact figure by accident.
    os.makedirs(SUPERSEDED, exist_ok=True)
    figure1ConceptImpacts(datasets,
                          os.path.join(SUPERSEDED, "fig1_concept_impacts.png"))
    figure2ModelConceptHeatmap(
        datasets, os.path.join(SUPERSEDED, "fig2_model_concept_heatmap.png"))
    figure1ACommensurable(
        datasets, os.path.join(SUPERSEDED,
                               "fig1A_commensurable_concept_impacts.png"))
    figure1BGrouped(datasets, os.path.join(
        SUPERSEDED, "fig1B_grouped_concept_impacts.png"))
    figure2CGroupedSemanticHeatmap(
        datasets, os.path.join(SUPERSEDED, "fig2_grouped_semantic_heatmap.png"))
    _writeSupersededNotice(os.path.join(SUPERSEDED, "README.md"))
    print(f"  superseded/                     5 earlier designs, retained "
          f"for the record, not for the paper")
    # Element-level attribution: persisted FIRST, then plotted from the
    # files, so every number in figs 8/11/12 exists in a readable CSV.
    attributionPaths = buildAttributionData()
    print(f"  attribution/                    persisted element and "
          f"edge-time attribution ({len(attributionPaths)} csv)")
    dependence = figure8Dependence(attributionPaths,
                                   os.path.join(OUTPUT, "fig8_dependence.png"))
    print(f"  fig8_dependence.png             structural property vs impact, "
          f"{sum(d['n'] for d in dependence)} elements")
    swarm = figure9TrueBeeswarm(
        datasets, os.path.join(OUTPUT, "fig9_true_beeswarm.png"))
    print(f"  fig9_true_beeswarm.png          deterministic packing, "
          f"{swarm['points']} points")
    figure10PublicationBoxplot(
        datasets, os.path.join(OUTPUT, "fig10_publication_boxplot.png"))
    print("  fig10_publication_boxplot.png   per-model impact distributions")
    local = figure11LocalBar(attributionPaths,
                             os.path.join(OUTPUT, "fig11_local_bar.png"))
    print(f"  fig11_local_bar.png             top {local['shown']} of "
          f"{local['total']} edges, full data retained")
    temporal = figure12TemporalEdgeTime(
        attributionPaths, os.path.join(OUTPUT, "fig12_temporal_edge_time.png"))
    print(f"  fig12_temporal_edge_time.png    {temporal['points']} "
          f"(edge, snapshot) observations")

    writeFigureMetadata(os.path.join(OUTPUT, "figure_metadata.json"))
    print("  figure_metadata.json            comparability metadata")
    figure3BridgeMatrix(os.path.join(OUTPUT, "fig3_bridge_matrix.png"))
    print("  fig3_bridge_matrix.png          N-community bridge structure")
    record = figure4LocalGraph(os.path.join(OUTPUT, "fig4_local_graph.png"))
    print(f"  fig4_local_graph.png            local explanation "
          f"({record['affected_edge_count']} edges touched)")
    figure5TemporalLocal(os.path.join(OUTPUT, "fig5_temporal_local.png"))
    print("  fig5_temporal_local.png         temporal local explanation")
    figure6ImpactDistribution(
        os.path.join(OUTPUT, "fig6_impact_distribution.png"))
    print("  fig6_impact_distribution.png    impact spread, 8 datasets")

    if figureTgnSeedStability(os.path.join(OUTPUT,
                                           "fig7_tgn_seed_stability.png")):
        print("  fig7_tgn_seed_stability.png    TGN held-out, 5 seeds")

    counts = writeTables(datasets)
    for name, frame in tgnTables().items():
        frame.to_csv(os.path.join(OUTPUT, f"{name}.csv"), index=False)
        with open(os.path.join(OUTPUT, f"{name}.md"), "w",
                  encoding="utf-8") as handle:
            handle.write(_asMarkdown(frame))
        counts[name] = len(frame)
    print()
    for name, rows in counts.items():
        print(f"  {name}: {rows} rows (csv + md)")
    print(f"\n  wrote {OUTPUT}")
    return counts


if __name__ == "__main__":
    main()
