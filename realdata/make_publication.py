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
import matplotlib.pyplot as plt
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
OUTPUT = os.path.join("output", "publication")
CASE_STUDIES = ("decentraland", "email_eu_core")

# One visual language for the whole paper.
POSITIVE = "#b2182b"
NEGATIVE = "#2166ac"
NEUTRAL = "#9e9e9e"

plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.25,
                     "savefig.dpi": 300, "savefig.bbox": "tight",
                     "figure.autolayout": False})


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
    fig.savefig(path)
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
    fig.savefig(path)
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

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(9.2, 3.6))
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
    fig.savefig(path)
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
    fig.savefig(path)
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
    fig.savefig(path)
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
    fig.savefig(path)
    plt.close(fig)


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
        table3 = tgn[(tgn["requested_delta"] == 0.1)
                     & (tgn["direction"] == "increase")][
            ["dataset", "transformation", "achieved_delta",
             "baseline_prediction", "after_prediction", "impact"]].round(6)

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

    counts = writeTables(datasets)
    print()
    for name, rows in counts.items():
        print(f"  {name}: {rows} rows (csv + md)")
    print(f"\n  wrote {OUTPUT}")
    return counts


if __name__ == "__main__":
    main()
