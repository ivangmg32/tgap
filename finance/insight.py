'''
Looking inside a stock-market explanation: WHERE and WHEN, in pictures.

runPrepared (realdata/run_real_data.py) answers "which concept does each
model react to?" with a table and six overview figures. This module adds the
paper's other kind of picture, drawn on the stock network itself, with
tickers on the nodes:

    what_changed      the stocks and the ties each concept adds / removes
    when_it_mattered  in which 6-month window the concept mattered
    edge_impact       which pair of stocks the model leans on
    edge_over_time    which pair, in which window
    node_impact       which single stock the model leans on
    impact_heatmap    every concept x every nudge (valid experiments only)

for two models that between them react to all five concepts, written to
figures/insight/<model>/ and described in insight.md (read it first).
Nothing here changes a result: it re-asks the same models about the same
graphs. The pictures are illustrations of mechanism - the validity gating of
the main table (which experiments count) is not repeated, and the heatmap
shows only the experiments that passed it.
'''

import os

import pandas as pd

from core import (BridgeWidthMetric, ClusteringMetric, SlopeModel,
                  TrendTemporalModel)
from realdata.run_real_data import buildTransformations

# The two models, chosen because between them every concept can move the
# prediction (a present-only model cannot react to the trend concepts).
INSIGHT_MODELS = {
    "trend_clustering": (
        "how clustered the market is, extrapolated from its trend",
        lambda communities: TrendTemporalModel(ClusteringMetric())),
    "slope_bridge_width": (
        "how fast cross-sector co-movement is growing or shrinking",
        lambda communities: SlopeModel(BridgeWidthMetric(communities))),
}


def _validTable(results, model):
    ''' The main table for one model, in the shape the pictures want. The
    `valid` column marks the experiments that passed the validity checks;
    the impact pictures use only those, the validity map shows all. '''
    part = results[results["model"] == model]
    return pd.DataFrame({
        "concept": part["transformation"],
        "direction": part["direction"],
        "requested_change": part["requested_delta"],   # already signed
        "impact": part["impact"],
        "nothing_changed": part["noop"].astype(bool),
        "valid": part["valid_for_analysis"].astype(bool),
        "status": part["transformation_status"],
    })


def insightFigures(prepared, directory, budget=40, delta=0.25):
    ''' Draw the paper-style pictures for each insight model into
    `directory`/figures/insight/<model>/ and write insight.md. '''
    from examples import figures
    from examples.toolkit import Tutorial

    results = pd.read_csv(os.path.join(directory, "tgap_results.csv"))
    transformations = buildTransformations(prepared.communities)
    tutorial = Tutorial(directory, "{0}: looking inside - where and when "
                        "the models react".format(prepared.name),
                        intro="The report says WHAT each model reacts to. "
                              "These pictures show WHERE (which stocks, "
                              "which ties) and WHEN (which window). "
                              "**Red** raises the model's prediction, "
                              "**blue** lowers it, grey does nothing. "
                              "Tickers are on the nodes; node colour is the "
                              "sector group. They illustrate how the model "
                              "responds to controlled counterfactual "
                              "nudges - they are not claims about the "
                              "market. **Important:** the beeswarm, boxplot "
                              "and dependence pictures ask the question on "
                              "many sliding windows and do NOT apply the "
                              "validity gating of the main table (report.md), "
                              "so they also contain experiments that table "
                              "excludes, for example where a concept could "
                              "not keep the number of ties. Draw conclusions "
                              "from report.md; use these to see the spread.")
    for modelName, (meaning, build) in INSIGHT_MODELS.items():
        model = build(prepared.communities)
        folder = os.path.join(directory, "figures", "insight", modelName)
        table = _validTable(results, modelName)
        made = figures.paperFigures(
            folder, model, transformations, prepared.snapshots,
            prepared.communities, table=table if len(table) else None,
            delta=delta, budget=budget,
            say=lambda text: print("      " + text))
        tutorial.section("Model: {0}".format(modelName),
                         "It predicts: {0}. On this market it says **{1:.4g}**."
                         .format(meaning, model.predict(prepared.snapshots)))
        for figure in made:
            tutorial.image(os.path.join("figures", "insight", modelName,
                                        figure["file"]).replace(os.sep, "/"),
                           figure["caption"])
            if figure.get("notes"):
                tutorial.bullets(figure["notes"])
        print("  insight pictures: {0} for {1}".format(len(made), modelName))
    labels = prepared.labels
    tutorial.section("The windows", "Snapshot numbers in the pictures are "
                     "the correlation windows, oldest first: " +
                     ", ".join("{0} = {1}".format(i + 1, l)
                               for i, l in enumerate(labels)) + ".")
    return tutorial.save("insight.md")
