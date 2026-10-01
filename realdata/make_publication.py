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
    bridgeMatrix, graphDifference, localExplanation,
    makeNCommunityTemporalGraph, temporalAttribution,
)

RESULTS = os.path.join("output", "real_data_v2", "temporal_evaluation")
TGN_RESULTS = os.path.join("output", "real_data_v2", "tgn")
TGN_STABILITY = os.path.join("output", "real_data_v2", "tgn_stability",
                             "email_eu_core")
OUTPUT = os.path.join("output", "publication")
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
                "figure": "fig1A_commensurable_concept_impacts",
                "candidate": "A",
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
                "figure": "fig1B_grouped_concept_impacts",
                "candidate": "B",
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
                "figure": "fig2_grouped_semantic_heatmap",
                "candidate": "C",
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
    figure1ConceptImpacts(datasets,
                          os.path.join(OUTPUT, "fig1_concept_impacts.png"))
    print("  fig1_concept_impacts.png        global concept importance")
    figure2ModelConceptHeatmap(
        datasets, os.path.join(OUTPUT, "fig2_model_concept_heatmap.png"))
    print("  fig2_model_concept_heatmap.png  model x concept matrix")

    # Candidates A/B/C: alternatives to fig1/fig2 that do not imply a single
    # cross-concept ranking. fig1/fig2 above are left untouched so the three
    # can be compared against what they would replace.
    groups = semanticGroups()
    a = figure1ACommensurable(
        datasets, os.path.join(OUTPUT,
                               "fig1A_commensurable_concept_impacts.png"))
    print(f"  fig1A_commensurable_...png      candidate A, "
          f"{len(a['concepts'])} commensurable concepts")
    figure1BGrouped(datasets,
                    os.path.join(OUTPUT, "fig1B_grouped_concept_impacts.png"))
    print(f"  fig1B_grouped_concept_...png    candidate B, "
          f"{len(groups)} semantic groups")
    figure2CGroupedSemanticHeatmap(
        datasets, os.path.join(OUTPUT, "fig2_grouped_semantic_heatmap.png"))
    print("  fig2_grouped_semantic_...png    candidate C, grouped heatmap")
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
