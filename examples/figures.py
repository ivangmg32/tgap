'''
Paper-style figures for ANY study - the same kinds of pictures as the
publication pipeline (output/publication/figures), drawn from your own data.

    paperFigures(folder, model, transformations, snapshots, communities, ...)

writes these PNG files into `folder` and returns a description of each one
(so a tutorial can show and explain it):

    what_changed.png       the graph before, after, and the DIFFERENCE for
                           every concept (paper fig. 4)
    when_it_mattered.png   which snapshot the concept mattered in (fig. 5)
    edge_impact.png        which single ties the model leans on (fig. 11)
    edge_over_time.png     tie x snapshot impact (fig. 12)
    node_impact.png        which people / stocks the model leans on
    impact_heatmap.png     every concept x every size of change
    bridge_matrix.png      ties between every pair of groups (only with 3+
                           groups; fig. 3)

and the GLOBAL pictures, the graph version of TSAP's boxplotTransLong - the
same question asked on many sliding windows of the history, so each concept
gets a whole distribution of impacts instead of one number:

    beeswarm.png           every impact as a dot, packed without overlap
                           (paper fig. 9)
    boxplot.png            median and quartiles with every dot overlaid
                           (paper fig. 10)
    dependence.png         the concept's value in a window vs its impact
                           (paper fig. 8)
    global_impacts.csv     every observation behind those three
    global_summary.csv     n, median, quartiles, share raising the prediction
    how_tgap_works.png     the method as one diagram (paper fig. 0)

and the diagnostic pictures of the real-data pipeline:

    side_effects.png       does a concept change ONLY what it should? (leakage)
    concept_trajectories.png  the concepts' values over time (what models read)
    validity_map.png       which experiments are trustworthy, and why not
    impacts_by_direction.png  more vs less of each concept, side by side
                           (paper fig. 1)
    impact_distribution.png   the spread of impacts per concept (paper fig. 6)
    sparsity.png           how many concepts / ties / nodes carry the answer
    tsap_summary.png       the original TSAP summary: signed-log bars

Colour language, everywhere: RED = raises the prediction, BLUE = lowers it,
GREY = no effect / not applicable.

Cost: besides the explanation itself, these pictures re-ask the model about
single ties, people and snapshots. `budget` caps the extra model calls PER
PICTURE (default 40), so a slow model stays usable; the title of each picture
says how much of the graph was covered. A picture that cannot be drawn is
skipped with a one-line reason - it never stops the study.
'''

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt       # noqa: E402
import networkx as nx                 # noqa: E402
import numpy as np                    # noqa: E402

from core import (                    # noqa: E402
    BridgeWidthMetric, ClusteringMetric, DegreeCentralizationMetric,
    DensityMetric, bridgeMatrix, conceptSparsity, declaresEdgeCountPreservation,
    edgeAttribution, edgeCountFeasibility, edgeTimeAttribution,
    elementSparsity, graphDifference, localExplanation, nodeAttribution,
    temporalAttribution,
)
from core.Diagnostics import leakageReport   # noqa: E402
from realdata.plotting import (       # noqa: E402
    NEGATIVE, NEUTRAL, POSITIVE, PUBLICATION_THEME, architectureFigure,
    beeswarmOffsets,
)
import pandas as pd                   # noqa: E402
from core import TgapExplainer        # noqa: E402

GROUP_COLOURS = ["#e08214", "#4d9221", "#8073ac", "#35978f", "#c51b7d",
                 "#7f7f7f"]
MAX_DRAWN_NODES = 60            # a readable node-link picture needs few nodes
THEME = dict(PUBLICATION_THEME, **{"savefig.dpi": 150})


# --------------------------------------------------------------------------
#  small helpers
# --------------------------------------------------------------------------

def _groupOf(communities):
    ''' node -> (index, label) for colouring. '''
    if communities is None:
        return {}, []
    labels = list(getattr(communities, "labels", None) or
                  ["group {0}".format(i + 1) for i in range(len(communities))])
    return ({n: i for i, c in enumerate(communities) for n in c}, labels)


def _layout(snapshots):
    ''' One layout for the whole history, so pictures line up. Big graphs
    are cut to their best-connected people (and the title says so). '''
    union = nx.Graph()
    for graph in snapshots:
        union.add_nodes_from(graph.nodes())
        for u, v in graph.edges():
            weight = union[u][v]["weight"] + 1 if union.has_edge(u, v) else 1
            union.add_edge(u, v, weight=weight)
    nodes = sorted(union, key=lambda n: (-union.degree(n), str(n)))
    shown = set(nodes[:MAX_DRAWN_NODES])
    sub = union.subgraph(shown)
    return nx.spring_layout(sub, seed=1, weight="weight"), shown, \
        len(nodes) > MAX_DRAWN_NODES


def _drawNodes(ax, graph, pos, shown, group, small):
    nodes = [n for n in graph.nodes() if n in shown]
    colours = [GROUP_COLOURS[group.get(n, len(GROUP_COLOURS) - 1)
                             % len(GROUP_COLOURS)] for n in nodes]
    nx.draw_networkx_nodes(graph, pos, nodelist=nodes, ax=ax,
                           node_size=150 if small else 60,
                           node_color=colours, linewidths=0.5,
                           edgecolors="black")
    if len(nodes) <= 30:
        nx.draw_networkx_labels(graph, pos, labels={n: str(n) for n in nodes},
                                ax=ax, font_size=6.5)


def _edges(graph, shown):
    return [e for e in graph.edges() if e[0] in shown and e[1] in shown]


def _save(fig, folder, filename):
    path = os.path.join(folder, filename)
    fig.savefig(path)
    plt.close(fig)
    return filename


def _message(ax, text):
    ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=9,
            transform=ax.transAxes, wrap=True)
    ax.axis("off")


def _short(text, limit=26):
    text = str(text)
    return text if len(text) <= limit else text[:limit - 1] + "..."


# --------------------------------------------------------------------------
#  the figures
# --------------------------------------------------------------------------

def whatChanged(folder, model, transformations, snapshots, communities,
                delta):
    ''' Paper fig. 4: for each concept, the graph before, after and the
    difference (red = tie added, blue dashed = tie removed). The snapshot
    shown is the one the concept changed most. '''
    pos, shown, cut = _layout(snapshots)
    group, labels = _groupOf(communities)
    rows = len(transformations)
    fig, axes = plt.subplots(rows, 3, figsize=(11.5, 3.6 * rows),
                             squeeze=False)
    notes = []
    for row, transformation in zip(axes, transformations):
        record, changed = localExplanation(
            snapshots, transformation, delta, model=model,
            communities=communities)
        # the snapshot with the most change (latest on ties)
        size = [len(d["added"]) + len(d["removed"]) for d in
                (graphDifference(a, b) for a, b in zip(snapshots, changed))]
        index = max(range(len(size)), key=lambda i: (size[i], i))
        before, after = snapshots[index], changed[index]
        difference = graphDifference(before, after)
        small = len(shown) <= 30
        for ax, graph, title in ((row[0], before, "before"),
                                 (row[1], after, "after +{0:g}%".format(
                                     100 * delta))):
            _drawNodes(ax, graph, pos, shown, group, small)
            nx.draw_networkx_edges(graph, pos, edgelist=_edges(graph, shown),
                                   ax=ax, width=0.7, alpha=0.5)
            ax.set_title("{0}: {1}".format(_short(transformation.name),
                                           title), fontsize=9)
            ax.axis("off")
        ax = row[2]
        _drawNodes(ax, before, pos, shown, group, small)
        nx.draw_networkx_edges(before, pos, ax=ax, width=0.4, alpha=0.12,
                               edgelist=_edges(
                                   before, shown))
        nx.draw_networkx_edges(
            nx.Graph(difference["added"]), pos, ax=ax, width=2.2,
            edge_color=POSITIVE,
            edgelist=[e for e in difference["added"]
                      if e[0] in shown and e[1] in shown])
        nx.draw_networkx_edges(
            nx.Graph(difference["removed"]), pos, ax=ax, width=2.2,
            edge_color=NEGATIVE, style="dashed",
            edgelist=[e for e in difference["removed"]
                      if e[0] in shown and e[1] in shown])
        impact = record.get("impact")
        if not any(size):
            ax.set_title("difference: NONE - this concept could not change "
                         "this graph\n(impact {0})".format(
                             "n/a" if impact is None else
                             "{0:+.3g}".format(impact)), fontsize=8.5)
        else:
            ax.set_title("difference (snapshot {0}): {1} added (red), {2} "
                         "removed (blue)\nimpact {3}".format(
                             index + 1, len(difference["added"]),
                             len(difference["removed"]),
                             "n/a" if impact is None else
                             "{0:+.3g}".format(impact)), fontsize=8.5)
        ax.axis("off")
        notes.append("{0}: {1} tie(s) added, {2} removed in snapshot {3}".format(
            transformation.name, len(difference["added"]),
            len(difference["removed"]), index + 1))
    handles = [plt.Line2D([], [], marker="o", linestyle="", markersize=7,
                          markerfacecolor=GROUP_COLOURS[i % len(
                              GROUP_COLOURS)], markeredgecolor="black",
                          label=_short(label))
               for i, label in enumerate(labels)]
    if handles:
        fig.legend(handles=handles, loc="lower center", ncol=len(handles),
                   fontsize=8, frameon=False)
    fig.suptitle("What each concept does to the graph (nudge +{0:g}%)".format(
        100 * delta) + ("  -  drawing the {0} best-connected nodes".format(
            MAX_DRAWN_NODES) if cut else ""), fontsize=11)
    fig.tight_layout(rect=(0, 0.04 if handles else 0, 1, 0.97))
    return {"file": _save(fig, folder, "what_changed.png"), "notes": notes,
            "caption": "For each concept, the graph before and after the "
                       "nudge, and the difference: red lines are ties the "
                       "concept ADDED, blue dashed lines are ties it "
                       "REMOVED. Node colours are the groups. This shows "
                       "exactly what 'a concept moved by x%' means for "
                       "your graph."}


def whenItMattered(folder, model, transformations, snapshots, delta):
    ''' Paper fig. 5: for each concept, the concept's value in every
    snapshot, coloured by how much the prediction moves when ONLY that
    snapshot is nudged. '''
    count = len(transformations)
    columns = 2 if count > 1 else 1
    rows = (count + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, figsize=(5.6 * columns,
                                                     3.2 * rows),
                             squeeze=False, sharex=True)
    notes = []
    calls = 0
    for index, transformation in enumerate(transformations):
        ax = axes[index // columns][index % columns]
        attribution = temporalAttribution(snapshots, model, transformation,
                                          delta)
        calls += attribution["model_calls"]
        impacts = [r["impact"] for r in attribution["rows"]]
        values = []
        for graph in snapshots:
            try:
                value = transformation.propertyValue([graph])
            except Exception:                       # noqa: BLE001
                value = None
            values.append(float(value) if value is not None else
                          float(graph.number_of_edges()))
        limit = max(abs(v) for v in impacts) or 1.0
        points = ax.scatter(range(1, len(values) + 1), values, c=impacts,
                            cmap="RdBu_r", vmin=-limit, vmax=limit, s=110,
                            edgecolors="black", linewidths=0.4, zorder=3)
        ax.plot(range(1, len(values) + 1), values, color="grey", alpha=0.4)
        ax.set_title(_short(transformation.name, 40), fontsize=9.5)
        ax.set_ylabel("concept value", fontsize=8)
        fig.colorbar(points, ax=ax, fraction=0.05, pad=0.02,
                     label="impact of nudging this\nsnapshot alone")
        responsive = [i + 1 for i, v in enumerate(impacts) if v != 0]
        notes.append("{0}: {1}".format(
            transformation.name, "the prediction reacts when snapshot(s) "
            + ", ".join(map(str, responsive)) + " are nudged"
            if responsive else "nudging a single snapshot never moves the "
            "prediction"))
    for ax in axes[-1]:
        ax.set_xlabel("snapshot (time ->)", fontsize=8)
    for index in range(count, rows * columns):
        axes[index // columns][index % columns].axis("off")
    fig.suptitle("When did each concept matter? (nudge +{0:g}% in ONE "
                 "snapshot at a time)".format(100 * delta), fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return {"file": _save(fig, folder, "when_it_mattered.png"),
            "notes": notes, "calls": calls,
            "caption": "Each dot is one snapshot; its height is the "
                       "concept's value there and its colour is how far the "
                       "prediction moves when ONLY that snapshot is nudged "
                       "(red up, blue down). A model that only reads the "
                       "latest snapshot is coloured only at the right-hand "
                       "end."}


def edgeImpact(folder, model, snapshots, communities, budget=40, top=15):
    ''' Paper fig. 11: which single ties the model leans on - remove one tie
    (from every snapshot), re-ask the model. '''
    result = edgeAttribution(snapshots, model, communities=communities,
                             topK=budget, budget=budget + 1)
    rows = [r for r in result["rows"] if np.isfinite(r["impact"])]
    nonzero = [r for r in rows if r["impact"] != 0]
    shown = nonzero[:top][::-1]
    fig, ax = plt.subplots(figsize=(7.2, 0.3 * max(len(shown), 3) + 2.0))
    if shown:
        ax.barh(range(len(shown)), [r["impact"] for r in shown],
                color=[POSITIVE if r["impact"] > 0 else NEGATIVE
                       for r in shown], edgecolor="black", linewidth=0.4)
        ax.set_yticks(range(len(shown)))
        ax.set_yticklabels(["{0} - {1}".format(_short(r["u"], 14),
                                               _short(r["v"], 14))
                            for r in shown], fontsize=7)
        ax.axvline(0, color="black", linewidth=1.0)
        ax.set_xlabel("change of the prediction when this tie is removed",
                      fontsize=8)
    else:
        _message(ax, "Removing any single tie leaves the prediction "
                     "unchanged:\nthis model does not depend on individual "
                     "ties.")
    ax.set_title("Which single ties does the model lean on?\n{0} of {1} ties "
                 "tested (the most frequent ones); {2} moved the "
                 "prediction".format(result["edges_evaluated"],
                                     result["edges_total"], len(nonzero)),
                 fontsize=9)
    fig.tight_layout()
    return {"file": _save(fig, folder, "edge_impact.png"),
            "calls": result["model_calls"], "attribution": result,
            "level": "tie",
            "notes": ["{0} of {1} tested ties change the prediction when "
                      "removed{2}".format(
                          len(nonzero), result["edges_evaluated"],
                          "; the strongest is {0} - {1} ({2:+.3g})".format(
                              nonzero[0]["u"], nonzero[0]["v"],
                              nonzero[0]["impact"]) if nonzero else "")],
            "caption": "One bar per tie: how much the prediction changes if "
                       "that single tie is removed from every snapshot "
                       "(red: prediction rises, blue: it falls). Ordered by "
                       "size WITHIN this picture only. Ties that change "
                       "nothing are not drawn - they are counted in the "
                       "title."}


def nodeImpact(folder, model, snapshots, communities, budget=40, top=15):
    ''' Which people / stocks the model leans on - isolate one node (all its
    ties removed, the node itself kept) and re-ask the model. '''
    result = nodeAttribution(snapshots, model, topK=budget, budget=budget + 1)
    rows = [r for r in result["rows"] if np.isfinite(r["impact"])]
    nonzero = [r for r in rows if r["impact"] != 0]
    shown = nonzero[:top][::-1]
    group, _ = _groupOf(communities)
    fig, ax = plt.subplots(figsize=(7.2, 0.3 * max(len(shown), 3) + 2.0))
    if shown:
        ax.barh(range(len(shown)), [r["impact"] for r in shown],
                color=[POSITIVE if r["impact"] > 0 else NEGATIVE
                       for r in shown], edgecolor="black", linewidth=0.4)
        ax.set_yticks(range(len(shown)))
        ax.set_yticklabels([_short(r["node"], 18) for r in shown],
                           fontsize=8)
        ax.axvline(0, color="black", linewidth=1.0)
        ax.set_xlabel("change of the prediction when this node loses all "
                      "its ties", fontsize=8)
    else:
        _message(ax, "Silencing any single node leaves the prediction "
                     "unchanged.")
    ax.set_title("Which nodes (people, stocks, ...) does the model lean on?\n{0} of {1} "
                 "tested; {2} moved the prediction".format(
                     result["nodes_evaluated"], result["nodes_total"],
                     len(nonzero)), fontsize=9)
    fig.tight_layout()
    return {"file": _save(fig, folder, "node_impact.png"),
            "calls": result["model_calls"], "attribution": result,
            "level": "node",
            "notes": ["{0} of {1} tested nodes change the prediction when "
                      "silenced{2}".format(
                          len(nonzero), result["nodes_evaluated"],
                          "; the strongest is {0} ({1:+.3g})".format(
                              nonzero[0]["node"], nonzero[0]["impact"])
                          if nonzero else "")],
            "caption": "One bar per node: the change of the prediction if "
                       "that node loses ALL its ties (the node stays, so "
                       "the graph does not shrink). Red: prediction rises, "
                       "blue: it falls."}


def edgeOverTime(folder, model, snapshots, budget=40, top=12):
    ''' Paper fig. 12: impact of removing one tie from ONE snapshot. '''
    perSnapshot = max(1, min(top, budget // max(len(snapshots), 1)))
    result = edgeTimeAttribution(snapshots, model, topK=perSnapshot)
    rows = [r for r in result["rows"] if np.isfinite(r["impact"])]
    edges = []
    for r in sorted(rows, key=lambda r: (-abs(r["impact"]), r["edge"])):
        if r["edge"] not in edges:
            edges.append(r["edge"])
    edges = sorted(edges[:top])
    index = {e: i for i, e in enumerate(edges)}
    kept = [r for r in rows if r["edge"] in index]
    fig, ax = plt.subplots(figsize=(7.4, 0.3 * max(len(edges), 3) + 2.4))
    if kept:
        limit = max(abs(r["impact"]) for r in kept) or 1.0
        points = ax.scatter(
            [r["snapshot_index"] + 1 for r in kept],
            [index[r["edge"]] for r in kept],
            c=[r["impact"] for r in kept], cmap="RdBu_r", vmin=-limit,
            vmax=limit, s=64, edgecolors="black", linewidths=0.35, zorder=3)
        ax.set_yticks(range(len(edges)))
        ax.set_yticklabels(["{0} - {1}".format(_short(u, 12), _short(v, 12))
                            for u, v in edges], fontsize=6.5)
        ax.set_xticks(range(1, len(snapshots) + 1))
        ax.set_xlabel("snapshot (time ->)", fontsize=8)
        fig.colorbar(points, ax=ax, fraction=0.04, pad=0.02,
                     label="change of the prediction")
    responsive = [i + 1 for i in result["snapshots_with_any_response"]]
    ax.set_title("Which tie, in which snapshot?  (remove ONE tie from ONE "
                 "snapshot)\nsnapshots where the model reacts: {0}".format(
                     ", ".join(map(str, responsive)) if responsive else
                     "none - this model has no time dependence on single "
                     "ties"), fontsize=8.5)
    fig.tight_layout()
    return {"file": _save(fig, folder, "edge_over_time.png"),
            "calls": result["model_calls"],
            "notes": ["The model reacts to single-tie removals in "
                      "snapshot(s): {0}".format(
                          ", ".join(map(str, responsive)) if responsive
                          else "none")],
            "caption": "One dot per (tie, snapshot): the change of the "
                       "prediction when that tie is removed from that one "
                       "snapshot only. A model that reads only the latest "
                       "snapshot is blind to the earlier ones - a flat "
                       "picture is a result, not an error. Nothing is "
                       "added up across time."}


def impactHeatmap(folder, table):
    ''' Every concept x every nudge (both directions, all deltas). '''
    frame = table.copy()
    concepts = list(dict.fromkeys(frame["concept"]))
    steps = sorted(set(frame["requested_change"]))
    grid = np.full((len(concepts), len(steps)), np.nan)
    stuck = np.zeros_like(grid, dtype=bool)
    for _, r in frame.iterrows():
        i, j = concepts.index(r["concept"]), steps.index(
            r["requested_change"])
        grid[i, j] = r["impact"]
        stuck[i, j] = bool(r["nothing_changed"])
    limit = np.nanmax(np.abs(grid)) if np.isfinite(grid).any() else 1.0
    limit = limit or 1.0
    fig, ax = plt.subplots(figsize=(1.1 * len(steps) + 3.2,
                                    0.5 * len(concepts) + 2.2))
    image = ax.imshow(np.ma.masked_invalid(grid), cmap="RdBu_r",
                      vmin=-limit, vmax=limit, aspect="auto")
    ax.set_xticks(range(len(steps)))
    ax.set_xticklabels(["{0:+g}%".format(100 * s) for s in steps],
                       fontsize=8)
    ax.set_yticks(range(len(concepts)))
    ax.set_yticklabels([_short(c, 30) for c in concepts], fontsize=8)
    ax.grid(False)
    for i in range(len(concepts)):
        for j in range(len(steps)):
            if np.isnan(grid[i, j]):
                continue
            ax.text(j, i, "n/a" if stuck[i, j] else
                    "{0:+.2g}".format(grid[i, j]), ha="center", va="center",
                    fontsize=7.5, color="#444444" if stuck[i, j] else
                    ("white" if abs(grid[i, j]) > 0.6 * limit else "black"))
    ax.set_xlabel("how much the concept was nudged", fontsize=8)
    ax.set_title("Impact of every concept at every size of nudge\n"
                 "(n/a = the graph could not be changed that way; blank = left out "
                 "by the validity checks)",
                 fontsize=9)
    fig.colorbar(image, ax=ax, fraction=0.04, pad=0.02, label="impact")
    fig.tight_layout()
    return {"file": _save(fig, folder, "impact_heatmap.png"), "notes": [],
            "caption": "The whole explanation in one picture: rows are "
                       "concepts, columns are how hard each was nudged "
                       "(left: less of it, right: more of it). Red raises "
                       "the prediction, blue lowers it. n/a: the graph "
                       "could not be changed that way. Blank: left out "
                       "because that experiment failed a validity check "
                       "(it is not shown rather than shown wrongly)."}


def bridgeMatrixFigure(folder, snapshots, communities):
    ''' Paper fig. 3: ties between every pair of groups, latest snapshot. '''
    labels = list(getattr(communities, "labels", None) or
                  ["group {0}".format(i + 1) for i in range(len(communities))])
    count = len(communities)
    grid = np.zeros((count, count))
    for (i, j), value in bridgeMatrix(snapshots[-1], communities).items():
        grid[i, j] = grid[j, i] = value
    fig, ax = plt.subplots(figsize=(1.0 * count + 3.0, 1.0 * count + 2.2))
    image = ax.imshow(grid, cmap="Purples")
    ax.set_xticks(range(count))
    ax.set_xticklabels([_short(label, 12) for label in labels], fontsize=8,
                       rotation=30, ha="right")
    ax.set_yticks(range(count))
    ax.set_yticklabels([_short(label, 12) for label in labels], fontsize=8)
    ax.grid(False)
    for i in range(count):
        for j in range(count):
            if i != j:
                ax.text(j, i, "{0:g}".format(grid[i, j]), ha="center",
                        va="center", fontsize=9)
    ax.set_title("Ties between every pair of groups (latest snapshot)",
                 fontsize=9)
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    return {"file": _save(fig, folder, "bridge_matrix.png"), "notes": [],
            "caption": "How many ties join each pair of groups in the "
                       "latest snapshot - the structure Bridge Width "
                       "nudges."}


# --------------------------------------------------------------------------
#  global pictures: many windows, a distribution of impacts per concept
# --------------------------------------------------------------------------

def _windows(snapshots, perWindowCalls, budget):
    ''' Sliding sub-histories of about half the length (at least 3), evenly
    thinned so the model calls stay within `budget`. Returns
    [(first, last, snapshots)] with 0-based snapshot numbers. '''
    total = len(snapshots)
    length = min(total, max(3, total // 2))
    starts = list(range(0, total - length + 1))
    allowed = max(1, budget // max(perWindowCalls, 1))
    if len(starts) > allowed:
        picks = np.linspace(0, len(starts) - 1, allowed).round().astype(int)
        starts = [starts[i] for i in sorted(set(picks))]
    return [(a, a + length - 1, snapshots[a:a + length]) for a in starts]


def collectGlobal(model, transformations, snapshots, deltas=(0.1, 0.25, 0.5),
                  budget=600):
    ''' The observations behind the global pictures: for every sliding
    window, every concept and every delta (both directions), one impact.
    A window the model cannot read (too short for it) is skipped. '''
    steps = sorted({abs(float(d)) for d in deltas})
    perWindow = len(steps) * (1 + 2 * len(transformations))
    rows, skipped = [], 0
    for first, last, window in _windows(snapshots, perWindow, budget):
        try:
            baseline = float(model.predict(window))
        except Exception:                           # noqa: BLE001
            skipped += 1
            continue
        for step in steps:
            explainer = TgapExplainer(model, transformations,
                                      defaultDelta=step)
            for record in explainer.explainDetailed(window):
                transformation = next(t for t in transformations
                                      if t.name == record["transformation"])
                try:
                    value = transformation.propertyValue(window)
                except Exception:                   # noqa: BLE001
                    value = None
                rows.append({
                    "window_first_snapshot": first + 1,
                    "window_last_snapshot": last + 1,
                    "concept": record["transformation"],
                    "requested_change": record["requestedDelta"],
                    "achieved_change": record["achievedDelta"],
                    "concept_value_before": value,
                    "prediction_before": baseline,
                    "impact": record["impact"],
                    "nothing_changed": bool(record["noop"]),
                })
    return pd.DataFrame(rows), skipped


def _summaryTable(frame):
    rows = []
    for concept, part in frame.groupby("concept", sort=False):
        moved = part[~part["nothing_changed"] & np.isfinite(part["impact"])]
        values = moved["impact"].to_numpy(dtype=float)
        rows.append({
            "concept": concept,
            "observations": len(part),
            "graph_changed": len(moved),
            "median_impact": float(np.median(values)) if len(values) else
            float("nan"),
            "q1": float(np.percentile(values, 25)) if len(values) else
            float("nan"),
            "q3": float(np.percentile(values, 75)) if len(values) else
            float("nan"),
            "share_raising_prediction": float((values > 0).mean())
            if len(values) else float("nan"),
        })
    return pd.DataFrame(rows)


def _valid(frame):
    return frame[~frame["nothing_changed"] & np.isfinite(frame["impact"])]


def beeswarmFigure(folder, frame, windows, deltas):
    ''' Paper fig. 9: every impact as a dot, one row per concept. Rows are
    never compared with each other (different units). '''
    valid = _valid(frame)
    concepts = list(dict.fromkeys(frame["concept"]))
    fig, ax = plt.subplots(figsize=(8.2, 0.95 * len(concepts) + 2.4))
    span = valid["impact"].abs().max() if len(valid) else 1.0
    span = span or 1.0
    for position, concept in enumerate(concepts):
        values = [float(v) for v in
                  valid[valid["concept"] == concept]["impact"]]
        if not values:
            ax.text(0.5, position, "the graph never changed (n=0)",
                    transform=ax.get_yaxis_transform(), ha="center",
                    va="center", fontsize=7, color=NEUTRAL, style="italic")
            continue
        offsets = beeswarmOffsets(values, pointWidth=span * 0.022)
        scale = 0.34 / max(1.0, max(abs(o) for o in offsets))
        ax.scatter(values, [position + o * scale for o in offsets], s=22,
                   alpha=0.85, edgecolors="black", linewidths=0.25, zorder=3,
                   c=[POSITIVE if v > 0 else NEGATIVE if v < 0 else NEUTRAL
                      for v in values])
        ax.annotate("n={0}".format(len(values)), (0.0, position),
                    xycoords=ax.get_yaxis_transform(),
                    textcoords="offset points", xytext=(3, 12), ha="left",
                    fontsize=6.5, color="#555555")
    ax.axvline(0, color="black", linewidth=0.9, zorder=2)
    ax.set_yticks(range(len(concepts)))
    ax.set_yticklabels([_short(c, 28) for c in concepts], fontsize=8)
    ax.set_ylim(-0.7, len(concepts) - 0.3)
    ax.invert_yaxis()
    ax.set_xlabel("impact (change of the prediction per unit of achieved "
                  "change)", fontsize=8)
    ax.set_title("Beeswarm of impacts over {0} sliding windows x {1} nudge "
                 "sizes x 2 directions\ndots are packed to avoid overlap "
                 "(no random jitter); rows are NOT comparable with each "
                 "other".format(windows, deltas), fontsize=8.8)
    fig.tight_layout()
    return {"file": _save(fig, folder, "beeswarm.png"), "notes": [],
            "caption": "The global explanation: instead of one number per "
                       "concept, every impact measured over many sliding "
                       "windows of the history, both directions and several "
                       "sizes of nudge. Red dots raise the prediction, blue "
                       "dots lower it. A concept whose dots sit on both "
                       "sides of zero has no steady effect. Windows "
                       "overlap, so the dots are not independent samples. "
                       "Rows use different units: compare directions and "
                       "spread, never sizes between rows."}


def boxplotFigure(folder, frame, windows, deltas):
    ''' Paper fig. 10: median and quartiles with every observation drawn. '''
    valid = _valid(frame)
    concepts = list(dict.fromkeys(frame["concept"]))
    series = [[float(v) for v in valid[valid["concept"] == c]["impact"]]
              for c in concepts]
    fig, ax = plt.subplots(figsize=(8.2, 0.7 * len(concepts) + 2.2))
    if any(series):
        style = dict(widths=0.55, patch_artist=True, showfliers=False,
                     medianprops=dict(color="black", linewidth=1.2),
                     boxprops=dict(facecolor="#dfe7ef", edgecolor="#444444",
                                   linewidth=0.8),
                     whiskerprops=dict(color="#444444", linewidth=0.8),
                     capprops=dict(color="#444444", linewidth=0.8))
        try:       # matplotlib >= 3.10 says "orientation"; older says "vert"
            ax.boxplot([s or [np.nan] for s in series],
                       orientation="horizontal", **style)
        except TypeError:
            ax.boxplot([s or [np.nan] for s in series], vert=False, **style)
        for position, values in enumerate(series, start=1):
            if values:
                offsets = beeswarmOffsets(
                    values, pointWidth=(max(map(abs, values)) or 1.0) * 0.03)
                scale = 0.18 / max(1.0, max(abs(o) for o in offsets))
                ax.scatter(values, [position + o * scale for o in offsets],
                           s=10, alpha=0.8, zorder=4, edgecolors="none",
                           c=[POSITIVE if v > 0 else NEGATIVE if v < 0
                              else NEUTRAL for v in values])
            ax.annotate("n={0}".format(len(values)), (0.0, position),
                        xycoords=ax.get_yaxis_transform(),
                        textcoords="offset points", xytext=(3, 11),
                        ha="left", fontsize=6.5, color="#555555")
        ax.axvline(0, color="black", linewidth=0.9, zorder=2)
    ax.set_yticks(range(1, len(concepts) + 1))
    ax.set_yticklabels([_short(c, 28) for c in concepts], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("impact", fontsize=8)
    ax.set_title("Distribution of impacts per concept ({0} windows x {1} "
                 "nudge sizes)\nbox = quartiles, line = median, every "
                 "observation overlaid, n printed".format(windows, deltas),
                 fontsize=8.8)
    fig.tight_layout()
    return {"file": _save(fig, folder, "boxplot.png"), "notes": [],
            "caption": "The same observations as the beeswarm, summarised: "
                       "the box covers the middle half of the impacts and "
                       "the black line is the median; every single "
                       "observation is drawn on top, so a box built from "
                       "few points cannot pass for a distribution."}


def dependenceFigure(folder, frame):
    ''' Paper fig. 8: does the effect depend on how much of the concept the
    window already had? x = concept's value, y = impact (increases only). '''
    usable = _valid(frame)
    usable = usable[(usable["requested_change"] > 0)
                    & usable["concept_value_before"].notna()]
    concepts = [c for c in dict.fromkeys(frame["concept"])
                if (usable["concept"] == c).any()]
    if not concepts:
        raise ValueError("no concept has a measurable value")
    columns = 2 if len(concepts) > 1 else 1
    rows = (len(concepts) + columns - 1) // columns
    fig, axes = plt.subplots(rows, columns, figsize=(5.4 * columns,
                                                     3.1 * rows),
                             squeeze=False)
    notes = []
    for index, concept in enumerate(concepts):
        ax = axes[index // columns][index % columns]
        part = usable[usable["concept"] == concept]
        x = part["concept_value_before"].astype(float)
        y = part["impact"].astype(float)
        ax.scatter(x, y, s=22, edgecolors="black", linewidths=0.25,
                   alpha=0.85, zorder=3,
                   c=[POSITIVE if v > 0 else NEGATIVE if v < 0 else NEUTRAL
                      for v in y])
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_title(_short(concept, 36), fontsize=9)
        ax.set_xlabel("concept value in the window", fontsize=8)
        ax.set_ylabel("impact (increase)", fontsize=8)
        if len(part) >= 4 and x.nunique() > 1 and y.nunique() > 1:
            rho = float(pd.Series(x.values).corr(pd.Series(y.values),
                                                 method="spearman"))
            notes.append("{0}: Spearman correlation {1:+.2f} between the "
                         "concept's value and its impact over {2} "
                         "observations".format(concept, rho, len(part)))
    for index in range(len(concepts), rows * columns):
        axes[index // columns][index % columns].axis("off")
    fig.suptitle("Does the impact depend on how much of the concept the "
                 "window already has?", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return {"file": _save(fig, folder, "dependence.png"), "notes": notes,
            "caption": "Each dot is one window: how much of the concept it "
                       "had (left to right) against the impact of nudging "
                       "it up (height). A slope means the model reacts more "
                       "when there is more, or less, of the concept to "
                       "begin with; a flat cloud means a steady response."}


def globalFigures(folder, model, transformations, snapshots,
                  deltas=(0.1, 0.25, 0.5), budget=600):
    ''' Beeswarm, boxplot and dependence over many sliding windows, plus the
    two CSV files behind them. Returns a list of figure descriptions. '''
    frame, skipped = collectGlobal(model, transformations, snapshots, deltas,
                                   budget)
    if frame.empty:
        raise ValueError("the model could not read any sliding window of "
                         "{0} snapshots".format(len(snapshots)))
    frame.to_csv(os.path.join(folder, "global_impacts.csv"), index=False)
    summary = _summaryTable(frame)
    summary.to_csv(os.path.join(folder, "global_summary.csv"), index=False)
    windows = frame["window_first_snapshot"].nunique()
    steps = len({abs(d) for d in frame["requested_change"]})
    made = []
    for draw in (lambda: beeswarmFigure(folder, frame, windows, steps),
                 lambda: boxplotFigure(folder, frame, windows, steps),
                 lambda: dependenceFigure(folder, frame)):
        try:
            made.append(draw())
        except Exception as error:                  # noqa: BLE001
            plt.close("all")
            print("      (skipped a global picture: {0}: {1})".format(
                type(error).__name__, error))
    length = (frame["window_last_snapshot"].iloc[0]
              - frame["window_first_snapshot"].iloc[0] + 1)
    if made:
        made[0]["frame"] = frame
    for figure in made[:1]:
        figure["notes"] = [
            "{0} windows of {1} snapshots each; {2} experiments, of which "
            "{3} changed the graph.".format(
                windows, length, len(frame),
                int((~frame["nothing_changed"]).sum()))] + [
            "{0}: median impact {1:+.3g}; the prediction rises in {2:.0%} of "
            "the {3} experiments that changed the graph".format(
                r["concept"], r["median_impact"],
                r["share_raising_prediction"], r["graph_changed"])
            for _, r in summary.iterrows() if r["graph_changed"]]
    return made


def howItWorks(folder):
    ''' Paper fig. 0: the method as one diagram. '''
    stem = os.path.join(folder, "how_tgap_works")
    architectureFigure(stem + ".png")
    if os.path.exists(stem + ".pdf"):
        os.remove(stem + ".pdf")
    plt.close("all")
    return {"file": "how_tgap_works.png", "notes": [],
            "caption": "The method in one diagram: take a model and a "
                       "temporal graph, nudge one human-meaningful concept "
                       "at a time, re-ask the model, and divide the change "
                       "of the prediction by the change that was really "
                       "achieved."}



# --------------------------------------------------------------------------
#  diagnostic pictures (the real-data pipeline's, and TSAP's)
# --------------------------------------------------------------------------

def _panel(communities):
    panel = {"density": DensityMetric(),
             "centralization": DegreeCentralizationMetric(),
             "clustering": ClusteringMetric()}
    if communities is not None:
        panel = dict({"bridge width": BridgeWidthMetric(communities)},
                     **panel)
    return panel


def sideEffects(folder, transformations, snapshots, communities, delta):
    ''' Does a concept change ONLY what it should? Each row nudges one
    concept; each column is the relative change of one property. The
    property the concept is about should move; the others should not. '''
    panel = _panel(communities)
    grid = np.zeros((len(transformations), len(panel)))
    for i, transformation in enumerate(transformations):
        report = leakageReport(snapshots, transformation, delta, panel)
        for j, name in enumerate(panel):
            before = report[name]["before"]
            grid[i, j] = (report[name]["change"] / abs(before)
                          if before else report[name]["change"])
    limit = np.abs(grid).max() or 1.0
    fig, ax = plt.subplots(figsize=(1.3 * len(panel) + 3.8,
                                    0.55 * len(transformations) + 2.3))
    image = ax.imshow(grid, cmap="RdBu_r", vmin=-limit, vmax=limit,
                      aspect="auto")
    ax.set_xticks(range(len(panel)))
    ax.set_xticklabels(list(panel), fontsize=8)
    ax.set_yticks(range(len(transformations)))
    ax.set_yticklabels([_short(t.name, 28) for t in transformations],
                       fontsize=8)
    ax.grid(False)
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            ax.text(j, i, "{0:+.0%}".format(grid[i, j]), ha="center",
                    va="center", fontsize=8,
                    color="white" if abs(grid[i, j]) > 0.6 * limit
                    else "black")
    ax.set_title("Side effects: relative change of each property when ONE "
                 "concept is nudged +{0:g}%".format(100 * delta),
                 fontsize=9)
    ax.set_xlabel("property that was measured", fontsize=8)
    fig.colorbar(image, ax=ax, fraction=0.04, pad=0.02,
                 label="relative change")
    fig.tight_layout()
    return {"file": _save(fig, folder, "side_effects.png"), "notes": [],
            "caption": "A good concept moves ITS property and leaves the "
                       "others alone, so each concept's row should be strong "
                       "in one column and near 0% elsewhere. Large entries "
                       "elsewhere are side effects: the prediction may then "
                       "be reacting to the side effect, not the concept. "
                       "(Density is expected to move with every concept "
                       "that adds or removes ties.)"}


def conceptTrajectories(folder, snapshots, communities):
    ''' The value of each general property in every snapshot - what
    most models actually read. Normalised so they share an axis. '''
    panel = _panel(communities)
    fig, ax = plt.subplots(figsize=(7.6, 3.8))
    for name, metric in panel.items():
        values = np.array([float(metric.measure(g)) for g in snapshots])
        span = values.max() - values.min()
        ax.plot(range(1, len(values) + 1),
                (values - values.min()) / span if span > 0
                else np.zeros_like(values), marker="o", markersize=4,
                label=name)
    ax.set_xlabel("snapshot (time ->)", fontsize=8)
    ax.set_ylabel("value, scaled 0 to 1 per property", fontsize=8)
    ax.set_xticks(range(1, len(snapshots) + 1))
    ax.set_title("How the properties of the graph move over time",
                 fontsize=9)
    ax.legend(fontsize=8)
    fig.tight_layout()
    return {"file": _save(fig, folder, "concept_trajectories.png"),
            "notes": [], "caption": "Each property of the graph over time, "
            "rescaled so they can share one axis (only the shape is "
            "meaningful, not the height). A model that extrapolates a "
            "trend reads exactly these curves."}


def validityMap(folder, table, transformations, snapshots, communities):
    ''' Which experiments can be trusted, and why not the others. '''
    concepts = list(dict.fromkeys(table["concept"]))
    steps = sorted(set(table["requested_change"]))
    byName = {t.name: t for t in transformations}
    labels = ["ok", "tie count not kept", "graph could not change",
              "other problem", "n/a"]
    colours = ["#2e7d32", "#c62828", "#757575", "#ef6c00", "#d9d9d9"]
    grid = np.full((len(concepts), len(steps)), 4.0)
    for _, row in table.iterrows():
        i, j = concepts.index(row["concept"]), steps.index(
            row["requested_change"])
        status = str(row["status"]) if "status" in table.columns else None
        transformation = byName.get(row["concept"])
        if status is not None and status != "ok":
            grid[i, j] = (1 if "infeasible" in status else
                          2 if status == "no_property_change" else 3)
        elif row["nothing_changed"]:
            grid[i, j] = 2
        elif status is None and transformation is not None \
                and declaresEdgeCountPreservation(transformation):
            try:
                kept = edgeCountFeasibility(
                    snapshots, transformation, row["requested_change"],
                    communities)["feasible"]
            except Exception:                           # noqa: BLE001
                kept = True
            grid[i, j] = 0 if kept else 1
        else:
            grid[i, j] = 0
    from matplotlib.colors import ListedColormap
    fig, ax = plt.subplots(figsize=(1.1 * len(steps) + 4.2,
                                    0.55 * len(concepts) + 2.4))
    ax.imshow(grid, cmap=ListedColormap(colours), vmin=-0.5, vmax=4.5,
              aspect="auto")
    ax.set_xticks(range(len(steps)))
    ax.set_xticklabels(["{0:+g}%".format(100 * x) for x in steps],
                       fontsize=8)
    ax.set_yticks(range(len(concepts)))
    ax.set_yticklabels([_short(c, 28) for c in concepts], fontsize=8)
    ax.grid(False)
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            ax.text(j, i, "OK" if grid[i, j] == 0 else
                    labels[int(grid[i, j])].split()[0], ha="center",
                    va="center", fontsize=7.5, color="white")
    present = sorted({int(v) for v in grid.flat})
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=colours[k],
                                     label=labels[k]) for k in present],
              loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=8)
    ax.set_title("Which experiments can be trusted?", fontsize=9)
    ax.set_xlabel("how much the concept was nudged", fontsize=8)
    fig.tight_layout()
    bad = int((grid == 1).sum())
    total = int((grid != 4).sum())
    return {"file": _save(fig, folder, "validity_map.png"),
            "notes": ["{0} of {1} experiments could not keep the number of "
                      "ties the concept promised to keep - read those with "
                      "care.".format(bad, total)] if bad else [],
            "caption": "Green: the concept did what it promised. Red: it "
                       "promised to keep the number of ties fixed but "
                       "could not on this graph (usually too few free "
                       "places to move ties). Grey: the graph could not be "
                       "changed that way at all. Orange: another validity "
                       "check failed (for example a trend that hit its "
                       "floor). Experiments that are not green should not "
                       "be used as evidence."}


def impactsByDirection(folder, table):
    ''' Paper fig. 1: for every concept, MORE of it (up triangles) against
    LESS of it (down triangles), at every nudge size. '''
    concepts = list(dict.fromkeys(table["concept"]))
    fig, ax = plt.subplots(figsize=(8.0, 0.8 * len(concepts) + 2.2))
    for position, concept in enumerate(concepts):
        part = table[(table["concept"] == concept) & ~table["nothing_changed"]]
        for direction, marker, shift in (("increase", "^", -0.12),
                                         ("decrease", "v", 0.12)):
            values = part[part["direction"] == direction]["impact"]
            ax.scatter(values, [position + shift] * len(values), marker=marker,
                       s=48, edgecolors="black", linewidths=0.4, zorder=3,
                       c=[POSITIVE if v > 0 else NEGATIVE if v < 0
                          else NEUTRAL for v in values])
    ax.axvline(0, color="black", linewidth=0.9)
    ax.set_yticks(range(len(concepts)))
    ax.set_yticklabels([_short(c, 28) for c in concepts], fontsize=8)
    ax.set_ylim(-0.6, len(concepts) - 0.4)
    ax.invert_yaxis()
    ax.set_xlabel("impact", fontsize=8)
    ax.plot([], [], "^", color="grey", label="more of the concept")
    ax.plot([], [], "v", color="grey", label="less of the concept")
    ax.legend(fontsize=8, loc="best")
    ax.set_title("More versus less of each concept (every nudge size)\n"
                 "if both triangles point the same way, the response is "
                 "not simply 'more raises, less lowers'", fontsize=8.8)
    fig.tight_layout()
    return {"file": _save(fig, folder, "impacts_by_direction.png"),
            "notes": [], "caption": "Each concept has two triangles per "
            "nudge size: up-pointing for MORE of the concept, down-pointing "
            "for LESS. Red raises the prediction, blue lowers it. A "
            "sensible, symmetric response has the two on opposite sides of "
            "zero; the same side means the model reacts to any change, "
            "not to the direction."}


def impactDistribution(folder, frame):
    ''' Paper fig. 6: the spread of impacts per concept over the windows. '''
    valid = _valid(frame)
    concepts = [c for c in dict.fromkeys(frame["concept"])
                if (valid["concept"] == c).sum() >= 3]
    if not concepts:
        raise ValueError("fewer than 3 observations for every concept")
    fig, axes = plt.subplots(1, len(concepts), sharey=False,
                             figsize=(2.9 * len(concepts), 3.4),
                             squeeze=False)
    for ax, concept in zip(axes[0], concepts):
        values = valid[valid["concept"] == concept]["impact"].to_numpy(float)
        ax.hist(values, bins=min(14, max(5, len(values) // 3)),
                color="#9bb4cf", edgecolor="#444444", linewidth=0.5)
        ax.axvline(0, color="black", linewidth=0.9)
        ax.axvline(float(np.median(values)), color=POSITIVE, linewidth=1.2,
                   linestyle="--")
        ax.set_title("{0}\nn={1}, median {2:+.3g}".format(
            _short(concept, 22), len(values), np.median(values)),
            fontsize=8)
        ax.set_xlabel("impact", fontsize=7.5)
    axes[0][0].set_ylabel("number of experiments", fontsize=8)
    fig.suptitle("Spread of impacts per concept (dashed = median)",
                 fontsize=9.5)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return {"file": _save(fig, folder, "impact_distribution.png"),
            "notes": [], "caption": "How the impact of each concept is "
            "spread over all the windows and nudge sizes: a narrow bar "
            "away from zero is a steady effect, a wide or two-sided one is "
            "not. Each concept has its own horizontal scale."}


def sparsityFigure(folder, table, attributions):
    ''' How many concepts / ties / nodes carry the explanation? '''
    records = [{"impact": r["impact"], "noop": bool(r["nothing_changed"])}
               for _, r in table.iterrows()]
    bars = []
    concept = conceptSparsity(records)
    if concept.get("denominator_total"):
        bars.append(("concept experiments", concept["active"],
                     concept["denominator_total"]))
    for attribution in attributions:
        if attribution.get("rows"):
            level = "ties" if attribution["rows"][0]["element"] == "edge" \
                else "nodes"
            result = elementSparsity(attribution)
            bars.append(("single {0} removed".format(level),
                         result["active"],
                         result["denominator_total"]))
    if not bars:
        raise ValueError("nothing was measured")
    fig, ax = plt.subplots(figsize=(7.4, 0.8 * len(bars) + 1.9))
    for position, (label, active, total) in enumerate(bars):
        ax.barh(position, total, color="#e6e6e6", edgecolor="#444444")
        ax.barh(position, active, color=POSITIVE, edgecolor="#444444")
        ax.text(total, position, "  {0} of {1} change the prediction".format(
            active, total), va="center", fontsize=8)
    ax.set_yticks(range(len(bars)))
    ax.set_yticklabels([b[0] for b in bars], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, max(b[2] for b in bars) * 1.6)
    ax.set_xlabel("experiments (grey = all, red = the prediction moved)",
                  fontsize=8)
    ax.set_title("Sparsity: how much of what was tried actually matters?",
                 fontsize=9)
    fig.tight_layout()
    return {"file": _save(fig, folder, "sparsity.png"), "notes": [],
            "caption": "An explanation is easier to use when only a few "
                       "things carry it. Red is the share of experiments in "
                       "which the prediction moved at all; exact zeros count "
                       "as 'no response' because TGAP's concepts leave "
                       "everything else untouched. High sparsity is not "
                       "automatically good: a model that really depends on "
                       "many things should give a dense answer."}


def tsapSummary(folder, table, delta):
    ''' The original TSAP summary plot: signed log10 of each impact, so
    effects of very different size can share one axis. '''
    first = table[table["requested_change"].abs() == delta]
    if first.empty:
        first = table[table["requested_change"].abs()
                      == table["requested_change"].abs().min()]
    labels = ["{0} {1}".format("Increase" if r["direction"] == "increase"
                               else "Decrease", r["concept"])
              for _, r in first.iterrows()]
    values = first["impact"].to_numpy(float)
    logs = [np.log10(abs(v)) if v != 0 else 0.0 for v in values]
    shift = abs(min(math_floor(min(logs)), 0))
    signed = [np.sign(v) * (np.log10(abs(v)) + shift) if v != 0 else 0.0
              for v in values]
    fig, ax = plt.subplots(figsize=(7.4, 0.36 * len(labels) + 1.8))
    ax.barh(range(len(labels)), signed,
            color=[POSITIVE if v > 0 else NEGATIVE for v in values],
            edgecolor="black", linewidth=0.4)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels([_short(l, 34) for l in labels], fontsize=8)
    ax.invert_yaxis()
    ax.axvline(0, color="black", linestyle="--", linewidth=0.9)
    ax.set_xlabel("signed log10(impact)" + (
        " + {0}".format(shift) if shift else ""), fontsize=8)
    ax.set_title("TSAP-style summary (nudge {0:g}%): effects of very "
                 "different size on one axis".format(100 * delta),
                 fontsize=9)
    fig.tight_layout()
    return {"file": _save(fig, folder, "tsap_summary.png"), "notes": [],
            "caption": "The summary plot of TSAP, the time-series ancestor "
                       "of TGAP: each bar is the base-10 logarithm of an "
                       "impact, keeping its sign, so a tiny effect and a "
                       "huge one both stay visible. Red raises the "
                       "prediction, blue lowers it. Bar lengths are "
                       "orders of magnitude, not amounts."}


def math_floor(value):
    return int(np.floor(value))


# --------------------------------------------------------------------------
#  all of them
# --------------------------------------------------------------------------

def paperFigures(folder, model, transformations, snapshots, communities,
                 table=None, delta=0.25, budget=40, say=None,
                 globalDeltas=(0.1, 0.25, 0.5), globalBudget=600):
    ''' Draw every figure that applies and return a list of dicts
    {file, caption, notes, calls}. A figure that fails is skipped with a
    one-line message (through `say`), never an exception.

    budget        extra model calls per local picture (ties, nodes, ...)
    globalBudget  model calls for the global pictures (beeswarm, boxplot,
                  dependence), which ask the question on many windows '''
    os.makedirs(folder, exist_ok=True)
    say = say or (lambda text: None)
    jobs = [
        ("what_changed.png", lambda: whatChanged(
            folder, model, transformations, snapshots, communities, delta)),
        ("when_it_mattered.png", lambda: whenItMattered(
            folder, model, transformations, snapshots, delta)),
        ("edge_impact.png", lambda: edgeImpact(
            folder, model, snapshots, communities, budget)),
        ("edge_over_time.png", lambda: edgeOverTime(
            folder, model, snapshots, budget)),
        ("node_impact.png", lambda: nodeImpact(
            folder, model, snapshots, communities, budget)),
    ]
    if table is not None:
        jobs.append(("impact_heatmap.png", lambda: impactHeatmap(
            folder, table[table["valid"]] if "valid" in table.columns
            else table)))
    if communities is not None and len(communities) >= 3:
        jobs.append(("bridge_matrix.png", lambda: bridgeMatrixFigure(
            folder, snapshots, communities)))
    jobs.append(("side_effects.png", lambda: sideEffects(
        folder, transformations, snapshots, communities, delta)))
    jobs.append(("concept_trajectories.png", lambda: conceptTrajectories(
        folder, snapshots, communities)))
    usable = (table[table["valid"]] if table is not None
              and "valid" in table.columns else table)
    if table is not None and len(table):
        jobs.append(("validity_map.png", lambda: validityMap(
            folder, table, transformations, snapshots, communities)))
    if usable is not None and len(usable):
        jobs.append(("impacts_by_direction.png", lambda: impactsByDirection(
            folder, usable)))
        jobs.append(("tsap_summary.png", lambda: tsapSummary(
            folder, usable, float(usable["requested_change"].abs().min()))))
    jobs.append(("beeswarm.png", lambda: globalFigures(
        folder, model, transformations, snapshots,
        deltas=globalDeltas, budget=globalBudget)))
    jobs.append(("how_tgap_works.png", lambda: howItWorks(folder)))
    made = []
    with plt.rc_context(THEME):
        for filename, job in jobs:
            try:
                result = job()
                made.extend(result if isinstance(result, list) else [result])
            except Exception as error:                 # noqa: BLE001
                plt.close("all")
                say("(skipped {0}: {1}: {2})".format(
                    filename, type(error).__name__, error))
        # pictures that need the results of the ones above
        frames = [f["frame"] for f in made if "frame" in f]
        attributions = [f["attribution"] for f in made
                        if "attribution" in f]
        later = []
        if frames:
            later.append(("impact_distribution.png",
                          lambda: impactDistribution(folder, frames[0])))
        if usable is not None and len(usable):
            later.append(("sparsity.png", lambda: sparsityFigure(
                folder, usable, attributions)))
        for filename, job in later:
            try:
                made.append(job())
            except Exception as error:                 # noqa: BLE001
                plt.close("all")
                say("(skipped {0}: {1}: {2})".format(
                    filename, type(error).__name__, error))
    return made
