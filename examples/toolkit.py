'''
Helpers for the easy examples - everything that is NOT the interesting part.

The examples in this folder only choose a dataset, a model and some
transformations; this module does the rest:

    syntheticGraph(...)        a made-up temporal graph with two groups
    loadEdgeList(csv, ...)     YOUR data: a CSV of "who, whom, when" rows
    loadGroups(csv, ...)       YOUR communities: a CSV of "who, group" rows
    findCommunities(...)       or let TGAP find the communities for you
    model(name, communities)   a built-in model, chosen by name
    transformations(names, communities)   built-in concepts, chosen by name
    explainAndSave(...)        run TGAP and write CSV + PNG outputs

Everything written goes to output/examples/<name>/ :

    explanation.csv        one row per concept x direction x delta
    explanation.png        bar chart of the impacts
    sensitivity.csv/.png   how the prediction moves as each concept is
                           pushed from -50% to +50%
    graph_over_time.csv/.png   your temporal graph, snapshot by snapshot
'''

import os

import matplotlib
matplotlib.use("Agg")           # write image files; never open a window
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx            # noqa: E402
import numpy as np               # noqa: E402
import pandas as pd              # noqa: E402

import paths                     # noqa: E402
from core import (               # noqa: E402
    BridgeTrendTransformation, BridgeWidthMetric, BridgeWidthTransformation,
    CentralizationTransformation, ChurnTransformation, ClusteringMetric,
    DegreeCentralizationMetric, DensityMetric, DensityTransformation,
    PersistenceTemporalModel, SlopeModel, TgapExplainer, TrendTemporalModel,
    declaresEdgeCountPreservation, detectCommunities, interCommunityEdges,
    makeTemporalGraph,
)

# Where results go. A module variable so tests can redirect it.
OUTPUT = paths.EXAMPLES

POSITIVE = "#c0392b"     # red: pushes the prediction UP
NEGATIVE = "#2e6fb5"     # blue: pushes it DOWN


# --------------------------------------------------------------------------
#  Data
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
#  Tutorial-style outputs
# --------------------------------------------------------------------------

class Tutorial:
    ''' Builds TUTORIAL.md next to an example's outputs: a step-by-step
    walk through what was done, every table and figure, and how to read
    them. Markdown, so it renders on GitHub and in any editor.

        t = Tutorial(folder, "My study")
        t.section("1. The data", "We used ...")
        t.table(frame, "caption")
        t.image("figure.png", "what it shows")
        t.save()
    '''

    def __init__(self, folder, title, intro=""):
        self.folder = folder
        self.lines = ["# " + title, ""]
        if intro:
            self.lines += [intro.strip(), ""]
        os.makedirs(folder, exist_ok=True)

    def section(self, heading, text=""):
        self.lines += ["## " + heading, ""]
        if text:
            self.lines += [text.strip(), ""]
        return self

    def text(self, text):
        self.lines += [text.strip(), ""]
        return self

    def bullets(self, items):
        self.lines += ["- " + str(item) for item in items] + [""]
        return self

    def table(self, frame, caption="", maxRows=25):
        if caption:
            self.lines += ["*" + caption + "*", ""]
        shown = frame.head(maxRows)
        columns = [str(c) for c in shown.columns]
        self.lines.append("| " + " | ".join(columns) + " |")
        self.lines.append("|" + "---|" * len(columns))
        for _, row in shown.iterrows():
            cells = []
            for value in row:
                if isinstance(value, float):
                    cells.append("{0:.4g}".format(value))
                else:
                    cells.append(str(value))
            self.lines.append("| " + " | ".join(cells) + " |")
        if len(frame) > maxRows:
            self.lines.append("")
            self.lines.append("*... {0} more rows in the CSV file.*".format(
                len(frame) - maxRows))
        self.lines.append("")
        return self

    def image(self, filename, caption):
        self.lines += ["![{0}]({1})".format(caption, filename), "",
                       "*" + caption + "*", ""]
        return self

    def save(self, filename="TUTORIAL.md"):
        path = os.path.join(self.folder, filename)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(self.lines).rstrip() + "\n")
        return path


# What each built-in concept means, for the tutorials.
CONCEPT_MEANING = {
    "Bridge Width": "the number of ties BETWEEN groups (redundant "
                    "connections across a boundary)",
    "Centralization": "how much the ties concentrate on one hub",
    "Density": "the overall number of ties (how active / connected the "
               "graph is)",
    "Bridge Trend": "whether ties between groups grow or decay over time",
    "Churn": "how much the past differs from the present",
}


def _meaning(transformation):
    if transformation.name in CONCEPT_MEANING:
        return CONCEPT_MEANING[transformation.name]
    described = getattr(transformation, "description", "")
    if described:
        return described
    doc = (type(transformation).__doc__ or "").strip().splitlines()
    return doc[0].strip() if doc else "a user-defined concept"


def _narrateExplanation(tutorial, model, transformations, snapshots,
                        communities, table, deltas, sweep, description,
                        step=None, extra=()):
    ''' The standard TGAP chapters of a tutorial. '''
    chapter = [0]

    def heading(title):
        if step is None:
            return title
        chapter[0] += 1
        return "{0}{1} - {2}".format(step, "abcdefgh"[chapter[0] - 1], title)
    first = table[table["requested_change"].abs() == float(deltas[0])]
    groups = ("" if communities is None else
              ", in {0} groups of sizes {1}".format(
                  len(communities),
                  "/".join(str(len(g)) for g in communities)))
    tutorial.section(
        heading("What TGAP did"),
        "TGAP took a temporal graph of **{0} snapshots** with **{1} "
        "nodes**{2}, and a model that turns that history into one number"
        "{3}. On this data the model predicts **{4:.4g}**.\n\n"
        "It then nudged one concept at a time by {5:g}% (up and down), "
        "re-ran the model, and measured how far the prediction moved. "
        "That movement, divided by how much the concept really changed, "
        "is the **impact**.".format(
            len(snapshots), snapshots[0].number_of_nodes(), groups,
            ": " + description if description else
            " (`{0}`)".format(type(model).__name__),
            table["prediction_before"].iloc[0], 100 * float(deltas[0])))
    tutorial.section(heading("The concepts that were tested"))
    tutorial.bullets(["**{0}** - {1}".format(t.name, _meaning(t))
                      for t in transformations])

    summary = first[["concept", "direction", "achieved_change", "impact",
                     "nothing_changed"]].copy()
    tutorial.section(heading("The result"), "Each row is one experiment. "
                     "`achieved_change` is how much the concept really "
                     "moved (graphs are discrete, so it is rarely exactly "
                     "the requested amount).")
    tutorial.table(summary, "explanation.csv (delta {0:g}; all deltas are in "
                   "the CSV)".format(float(deltas[0])))

    reading = []
    for concept, part in first.groupby("concept", sort=False):
        up = part[part["direction"] == "increase"]
        down = part[part["direction"] == "decrease"]
        if up.empty:
            continue
        row = up.iloc[0]
        flat = (not down.empty and not down.iloc[0]["nothing_changed"]
                and abs(down.iloc[0]["impact"]) < 1e-12)
        if (not row["nothing_changed"] and abs(row["impact"]) >= 1e-12
                and flat):
            reading.append(
                "**{0}**: more of it pushes the prediction **{1}** (impact "
                "{2:+.4g}), but LESS of it changes nothing - the model "
                "reacts in one direction only. Look at sensitivity.png to "
                "see where the response starts.".format(
                    concept, "up" if row["impact"] > 0 else "down",
                    row["impact"]))
        elif row["nothing_changed"]:
            reading.append("**{0}**: this graph could not be changed in that "
                           "direction, so there is no evidence either way."
                           .format(concept))
        elif abs(row["impact"]) < 1e-12:
            reading.append("**{0}**: the model does **not react** to it - "
                           "changing it leaves the prediction exactly where "
                           "it was.".format(concept))
        else:
            reading.append("**{0}**: more of it pushes the prediction **{1}** "
                           "(impact {2:+.4g}).".format(
                               concept, "up" if row["impact"] > 0 else
                               "down", row["impact"]))
    tutorial.section(heading("How to read it"))
    tutorial.bullets(reading)
    tutorial.text("> Impacts of different concepts are in different units "
                  "(a relative change, a slope, a rewiring fraction), so "
                  "compare their **directions**, not their sizes. They "
                  "describe how the **model** responds - not what would "
                  "happen in the real world.")
    tutorial.section(heading("The pictures"))
    tutorial.image("explanation.png", "The impact of each concept, both "
                   "directions. Red raises the prediction, blue lowers it.")
    if sweep:
        tutorial.image("sensitivity.png", "The prediction as each concept "
                       "is pushed from -50% to +50%. A straight line means "
                       "a steady response; steps come from whole ties "
                       "being added or removed.")
    tutorial.image("graph_over_time.png", "The data itself: ties (and ties "
                   "between groups) in every snapshot.")
    if extra:
        tutorial.section(
            heading("Looking inside: where and when it happens"),
            "The explanation says WHAT the model reacts to. These pictures "
            "(the same kinds as in the paper) show WHERE in the graph and "
            "WHEN in time. Colours always mean the same: **red** raises the "
            "prediction, **blue** lowers it, grey does nothing.")
        for figure in extra:
            tutorial.image(figure["file"], figure["caption"])
            if figure.get("notes"):
                tutorial.bullets(figure["notes"])
    tutorial.section(heading("Files in this folder"))
    tutorial.bullets([
        "`explanation.csv` - every experiment, every delta",
        "`sensitivity.csv` - the curves in sensitivity.png",
        "`graph_over_time.csv` - the data, snapshot by snapshot",
    ] + ["`{0}` - {1}".format(f["file"], f["caption"].split(".")[0].lower())
         for f in extra])


# --------------------------------------------------------------------------
#  A tiny simulator, so every example can make a dataset with a story
# --------------------------------------------------------------------------

def simulateInteractions(groups, periods, withinPerPeriod, crossPerPeriod,
                         start="2024-01-01", periodDays=7, seed=1,
                         hubs=None):
    ''' Interactions between people in named groups, period by period.

    groups          : {group name: [people]}
    withinPerPeriod : interactions inside each group per period (number, or
                      a function of the period index)
    crossPerPeriod  : interactions between groups per period (same)
    hubs            : {person: weight} - people who take part more often

    Returns a DataFrame with source, target, time (a date). '''
    import random
    rng = random.Random(seed)
    names = list(groups)
    everyone = [p for members in groups.values() for p in members]
    weights = hubs or {}

    def pick(pool):
        return rng.choices(pool, weights=[weights.get(p, 1.0)
                                          for p in pool])[0]

    def count(rule, period):
        return int(round(rule(period) if callable(rule) else rule))

    rows = []
    day0 = pd.Timestamp(start)
    for period in range(periods):
        for _ in range(count(withinPerPeriod, period) * len(names)):
            members = groups[rng.choice(names)]
            u = pick(members)
            v = pick([m for m in members if m != u])
            rows.append((u, v, period))
        for _ in range(count(crossPerPeriod, period)):
            a, b = rng.sample(names, 2)
            rows.append((pick(groups[a]), pick(groups[b]), period))
    frame = pd.DataFrame(rows, columns=["source", "target", "period"])
    frame["time"] = [(day0 + pd.Timedelta(days=int(p * periodDays +
                                                    rng.randrange(
                                                        periodDays))))
                     .strftime("%Y-%m-%d") for p in frame["period"]]
    _ = everyone
    return frame[["source", "target", "time"]]


def step(number, total, text):
    ''' Print one step of an example: "[1/4] Loading the data". '''
    print("  [{0}/{1}] {2}".format(number, total, text))


def syntheticGraph(snapshots=6, peoplePerGroup=10, bridgeWidth=8,
                   bridgeDecay=0, seed=42):
    ''' A made-up temporal graph: two groups of people, `bridgeWidth` ties
    between the groups, losing `bridgeDecay` of those ties per snapshot.

    Returns (snapshots, communities). '''
    return makeTemporalGraph(nSnapshots=snapshots,
                             nPerCommunity=peoplePerGroup,
                             bridgeWidth=bridgeWidth,
                             bridgeDrift=bridgeDecay, seed=seed)


def _readCsv(path):
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    # sep=None sniffs the separator, so a CSV saved by Excel with ';' (common
    # in Europe) works as well as one with ','. Excel on Windows also saves
    # "CSV" in the local code page rather than UTF-8, so a name like "José"
    # would not decode as UTF-8: fall back to cp1252 in that case.
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return pd.read_csv(path, sep=None, engine="python",
                               encoding=encoding, dtype=str)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, sep=None, engine="python", encoding="latin-1",
                       dtype=str)


def _requireColumns(frame, path, columns):
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(
            "{0} has no column named {1}. Its columns are: {2}. Fix the "
            "column names in the PARAMETERS block.".format(
                os.path.basename(path), ", ".join(map(repr, missing)),
                ", ".join(map(repr, frame.columns))))


def _parseDates(column, name):
    ''' Dates in any common layout. ISO (2024-03-20) is unambiguous; for
    03/20/2024 vs 20/03/2024 both day orders are tried and the one that
    reads EVERY row wins. '''
    attempts = [{}, {"dayfirst": True}]
    for options in attempts:
        for extra in ({}, {"format": "mixed"}):
            try:
                parsed = pd.to_datetime(column, errors="coerce",
                                        **options, **extra)
            except (TypeError, ValueError):
                continue
            if not parsed.isna().any():
                return parsed
    parsed = pd.to_datetime(column, errors="coerce", dayfirst=True)
    bad = column[parsed.isna()].iloc[0]
    raise ValueError("Column {0!r} must hold numbers or dates; {1!r} is "
                     "neither. Dates like 2024-03-20 are the safest."
                     .format(name, bad))


def loadEdgeList(path, sourceColumn="source", targetColumn="target",
                 timeColumn="time", snapshots=6):
    ''' Turn a CSV of interactions into a temporal graph.

    Each row is one interaction: who (source), with whom (target), when
    (time). Time may be a number (seconds, days, ...) or a date such as
    2024-03-01. The whole time span is cut into `snapshots` equal windows;
    snapshot k holds every pair that interacted in window k.

    Every person appears in every snapshot (isolated when inactive),
    because TGAP keeps the set of people fixed. Direction and repeats are
    ignored: an interaction is an undirected tie. '''
    frame = _readCsv(path)
    _requireColumns(frame, path, [sourceColumn, targetColumn, timeColumn])
    frame = frame.dropna(subset=[sourceColumn, targetColumn, timeColumn])
    if frame.empty:
        raise ValueError("{0} has no complete rows.".format(
            os.path.basename(path)))
    if int(snapshots) < 2:
        raise ValueError("snapshots must be at least 2 (TGAP needs a "
                         "history), got {0}.".format(snapshots))

    times = pd.to_numeric(frame[timeColumn], errors="coerce")
    if times.isna().any():
        times = _parseDates(frame[timeColumn], timeColumn)
        times = (times - times.min()).dt.total_seconds()
    times = times.astype(float).to_numpy()

    start, end = times.min(), times.max()
    if end == start:
        raise ValueError("All rows have the same time, so there is no "
                         "history to cut into snapshots.")
    window = (end - start) / int(snapshots)
    index = np.minimum(((times - start) // window).astype(int),
                       int(snapshots) - 1)

    sources = frame[sourceColumn].astype(str).str.strip().to_numpy()
    targets = frame[targetColumn].astype(str).str.strip().to_numpy()
    people = sorted(set(sources) | set(targets))
    graphs = [nx.Graph() for _ in range(int(snapshots))]
    for graph in graphs:
        graph.add_nodes_from(people)
    for k, u, v in zip(index, sources, targets):
        if u != v:                       # a self-interaction is not a tie
            graphs[k].add_edge(u, v)
    return graphs


def loadGroups(path, personColumn="person", groupColumn="group",
               snapshots=None):
    ''' Read known communities (teams, departments, ...) from a CSV with
    one row per person. People missing from the CSV but present in the
    graph are put in an extra group called "other", so every person
    belongs to exactly one group. Returns a list of sets of people. '''
    frame = _readCsv(path)
    _requireColumns(frame, path, [personColumn, groupColumn])
    groups = {}
    for person, group in zip(frame[personColumn].astype(str).str.strip(),
                             frame[groupColumn].astype(str).str.strip()):
        groups.setdefault(group, set()).add(person)
    if snapshots is not None:
        known = set().union(*groups.values())
        others = set(snapshots[0].nodes()) - known
        if others:
            groups["other"] = others
        everyone = set(snapshots[0].nodes())
        groups = {g: members & everyone for g, members in groups.items()
                  if members & everyone}
    if len(groups) < 2:
        raise ValueError("Need at least two groups; {0} defines {1}.".format(
            os.path.basename(path), len(groups)))
    return [groups[g] for g in sorted(groups)]


def findCommunities(snapshots, howMany=2):
    ''' Let TGAP find `howMany` communities, using all snapshots together
    (greedy modularity - deterministic). For real studies prefer known
    groups (loadGroups): detected groups are a convenience. '''
    union = nx.Graph()
    for graph in snapshots:
        union.add_nodes_from(graph.nodes())
        union.add_edges_from(graph.edges())
    if union.number_of_edges() == 0:
        raise ValueError("The graph has no ties at all, so communities "
                         "cannot be found.")
    communities = detectCommunities(union, n=howMany)
    sizes = [len(group) for group in communities]
    if min(sizes) < 2:
        raise ValueError(
            "Could only find groups of sizes {0} in this graph - asking for "
            "{1} groups splits it too finely. Lower HOW_MANY_GROUPS, or give "
            "the groups in a CSV (GROUPS_FILE).".format(sizes, howMany))
    return communities


# --------------------------------------------------------------------------
#  Built-in models and transformations, by name
# --------------------------------------------------------------------------

MODELS = {
    # name: (description, builder)
    "persistence_bridge_width": (
        "tomorrow's bridge width = today's",
        lambda c: PersistenceTemporalModel(BridgeWidthMetric(c))),
    "trend_bridge_width": (
        "bridge width, extrapolated from its trend over all snapshots",
        lambda c: TrendTemporalModel(BridgeWidthMetric(c))),
    "slope_bridge_width": (
        "how fast the bridge is growing or shrinking",
        lambda c: SlopeModel(BridgeWidthMetric(c))),
    "persistence_density": (
        "tomorrow's density = today's",
        lambda c: PersistenceTemporalModel(DensityMetric())),
    "trend_density": (
        "density, extrapolated from its trend",
        lambda c: TrendTemporalModel(DensityMetric())),
    "persistence_centralization": (
        "tomorrow's centralization = today's",
        lambda c: PersistenceTemporalModel(DegreeCentralizationMetric())),
    "trend_clustering": (
        "clustering, extrapolated from its trend",
        lambda c: TrendTemporalModel(ClusteringMetric())),
}

TRANSFORMATIONS = {
    "bridge_width": lambda c: BridgeWidthTransformation(c, seed=42),
    "centralization": lambda c: CentralizationTransformation(c, seed=42),
    "density": lambda c: DensityTransformation(c, seed=42),
    "bridge_trend": lambda c: BridgeTrendTransformation(c, seed=42),
    "churn": lambda c: ChurnTransformation(c, seed=42),
}


def model(name, communities):
    ''' A built-in model by name (see MODELS). '''
    if name not in MODELS:
        raise ValueError("Unknown model {0!r}. Choose one of: {1}".format(
            name, ", ".join(MODELS)))
    return MODELS[name][1](communities)


def transformations(names, communities):
    ''' Built-in transformations by name (see TRANSFORMATIONS). '''
    unknown = [n for n in names if n not in TRANSFORMATIONS]
    if unknown:
        raise ValueError("Unknown transformation {0}. Choose from: {1}"
                         .format(", ".join(map(repr, unknown)),
                                 ", ".join(TRANSFORMATIONS)))
    return [TRANSFORMATIONS[n](communities) for n in names]


# --------------------------------------------------------------------------
#  Run TGAP and save everything
# --------------------------------------------------------------------------

def _edgeCountKept(transformation, snapshots, delta):
    ''' Did a transformation that PROMISES to keep the number of ties
    actually keep it? (On small or dense graphs it sometimes cannot.) '''
    if not declaresEdgeCountPreservation(transformation):
        return "not promised"
    after = transformation.transform(snapshots, delta)
    same = all(a.number_of_edges() == b.number_of_edges()
               for a, b in zip(snapshots, after))
    return "yes" if same else "NO - read with care"


def _graphOverTime(snapshots, communities):
    rows = []
    for k, graph in enumerate(snapshots):
        row = {"snapshot": k, "people": graph.number_of_nodes(),
               "ties": graph.number_of_edges(),
               "density": round(nx.density(graph), 4)}
        if communities is not None:
            row["bridge_width"] = len(interCommunityEdges(graph, communities))
        rows.append(row)
    return pd.DataFrame(rows)


def saveGraphOverTime(overTime, folder, name):
    ''' graph_over_time.png: ties (and bridge width) per snapshot. '''
    columns = [c for c in ("ties", "bridge_width") if c in overTime]
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    for column in columns:
        ax.plot(overTime["snapshot"], overTime[column], marker="o",
                label=column.replace("_", " "))
    ax.set_xlabel("snapshot (oldest -> newest)")
    ax.set_title("{0}: your temporal graph".format(name), fontsize=10)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(folder, "graph_over_time.png"), dpi=150)
    plt.close(fig)


def addPictures(tutorial, folder, theModel, theTransformations, snapshots,
                communities, heading, intro="", delta=0.25, budget=40):
    ''' Draw the paper-style pictures (see examples/figures.py) for a study
    that does its own explaining, and add them to its tutorial as a chapter.
    Returns the list of pictures drawn. '''
    from examples import figures
    made = figures.paperFigures(
        folder, theModel, theTransformations, snapshots, communities,
        delta=delta, budget=budget,
        say=lambda text: print("      " + text))
    tutorial.section(heading, (intro + " " if intro else "") +
                     "**Red** raises the prediction, **blue** lowers it, "
                     "grey does nothing.")
    for figure in made:
        tutorial.image(figure["file"], figure["caption"])
        if figure.get("notes"):
            tutorial.bullets(figure["notes"])
    return made


def explainAndSave(name, theModel, theTransformations, snapshots,
                   communities=None, deltas=(0.1, 0.25), sweep=True,
                   folder=None, tutorial=None, modelDescription=None,
                   step=None, figures=True, figureBudget=40):
    ''' Explain `theModel` on `snapshots` with `theTransformations`, print
    the result, and save CSV + PNG files plus a TUTORIAL.md that walks
    through them.

    folder   : where to write (default output/examples/<name>/)
    tutorial : a Tutorial to continue (default: a new one in `folder`)
    modelDescription : one sentence saying what the model predicts
    step     : e.g. "Step 4" - number the explanation's chapters as part of
               that step of a longer tutorial
    figures  : also draw the paper-style pictures (what changed, when it
               mattered, which ties / nodes matter, heatmap - see
               examples/figures.py). They re-ask the model up to
               `figureBudget` times per picture; pass False to skip them.

    Returns the explanation as a pandas DataFrame. '''
    if len(snapshots) < 2:
        raise ValueError("Need at least 2 snapshots, got {0}.".format(
            len(snapshots)))
    if not theTransformations:
        raise ValueError("Choose at least one transformation.")
    folder = folder or os.path.join(OUTPUT, name)
    os.makedirs(folder, exist_ok=True)

    rows = []
    for delta in deltas:
        explainer = TgapExplainer(theModel, theTransformations,
                                  defaultDelta=float(delta))
        byName = {t.name: t for t in theTransformations}
        for record in explainer.explainDetailed(snapshots):
            transformation = byName[record["transformation"]]
            rows.append({
                "concept": record["transformation"],
                "direction": ("increase" if record["requestedDelta"] > 0
                              else "decrease"),
                "requested_change": record["requestedDelta"],
                "achieved_change": record["achievedDelta"],
                "prediction_before": record["baseline"],
                "prediction_after": record["transformed"],
                "impact": record["impact"],
                "nothing_changed": record["noop"],
                "tie_count_kept": _edgeCountKept(
                    transformation, snapshots, record["requestedDelta"]),
            })
    table = pd.DataFrame(rows)
    table.to_csv(os.path.join(folder, "explanation.csv"), index=False)

    # -- print it ------------------------------------------------------
    first = table[table["requested_change"].abs() == float(deltas[0])]
    print()
    print("      The model predicts {0:.4f} on your data.".format(
        table["prediction_before"].iloc[0]))
    print("      Nudging each concept by {0:g}%:".format(
        100 * float(deltas[0])))
    print()
    print("        {0:<24s} {1:<10s} {2:>12s}".format(
        "concept", "direction", "impact"))
    print("        " + "-" * 48)
    for _, row in first.iterrows():
        note = "   (could not change this graph)" \
            if row["nothing_changed"] else ""
        print("        {0:<24s} {1:<10s} {2:>+12.4f}{3}".format(
            row["concept"], row["direction"], row["impact"], note))
    print()
    print("      impact > 0: more of the concept raises the prediction;"
          " < 0: lowers it; 0: no effect.")

    # -- explanation.png ----------------------------------------------
    labels = ["{0} {1}".format(r["direction"], r["concept"])
              for _, r in first.iterrows()]
    values = first["impact"].to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(7.5, 0.45 * len(labels) + 1.6))
    ax.barh(range(len(values)), values,
            color=[POSITIVE if v > 0 else NEGATIVE for v in values])
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.axvline(0, color="black", linewidth=0.8)
    span = max(abs(values).max(), 1e-12)
    for position, value in enumerate(values):
        ax.text(value + (0.02 * span if value >= 0 else -0.02 * span),
                position, "{0:+.3g}".format(value), va="center",
                ha="left" if value >= 0 else "right", fontsize=8)
    ax.set_xlim(-1.25 * span, 1.25 * span)
    ax.set_xlabel("impact on the prediction (per unit of achieved change)")
    ax.set_title("{0}: what moves the model (delta {1:g})".format(
        name, float(deltas[0])), fontsize=10)
    fig.tight_layout()
    fig.savefig(os.path.join(folder, "explanation.png"), dpi=150)
    plt.close(fig)

    # -- sensitivity ---------------------------------------------------
    if sweep:
        baseline = theModel.predict(snapshots)
        sweepRows = []
        steps = [d for d in np.round(np.linspace(-0.5, 0.5, 11), 2) if d != 0]
        for transformation in theTransformations:
            for delta in steps:
                after = theModel.predict(
                    transformation.transform(snapshots, float(delta)))
                sweepRows.append({"concept": transformation.name,
                                  "requested_change": float(delta),
                                  "prediction_change": after - baseline})
        sweepFrame = pd.DataFrame(sweepRows)
        sweepFrame.to_csv(os.path.join(folder, "sensitivity.csv"),
                          index=False)
        fig, ax = plt.subplots(figsize=(7.5, 4.2))
        for concept, part in sweepFrame.groupby("concept", sort=False):
            ax.plot(100 * part["requested_change"],
                    part["prediction_change"], marker="o", label=concept)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xlabel("requested change of the concept (%)")
        ax.set_ylabel("change of the prediction")
        ax.set_title("{0}: sensitivity".format(name), fontsize=10)
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(os.path.join(folder, "sensitivity.png"), dpi=150)
        plt.close(fig)

    # -- the data itself ----------------------------------------------
    overTime = _graphOverTime(snapshots, communities)
    overTime.to_csv(os.path.join(folder, "graph_over_time.csv"), index=False)
    saveGraphOverTime(overTime, folder, name)

    extra = []
    if figures:
        from examples import figures as paperFigures
        print()
        print("      Drawing the paper-style pictures (where and when the "
              "model reacts) ...")
        extra = paperFigures.paperFigures(
            folder, theModel, theTransformations, snapshots, communities,
            table=table,
            delta=min(max(abs(float(d)) for d in deltas), 0.5),
            budget=figureBudget, say=lambda text: print("      " + text))

    tutorial = tutorial or Tutorial(
        folder, "{0}: a TGAP explanation, step by step".format(name))
    _narrateExplanation(tutorial, theModel, theTransformations, snapshots,
                        communities, table, deltas, sweep, modelDescription,
                        step, extra)
    path = tutorial.save()
    print("      Results ({0} pictures + CSV + tutorial): {1}".format(
        2 + (1 if sweep else 0) + len(extra), folder))
    print("      Read first: {0}".format(path))
    return table
