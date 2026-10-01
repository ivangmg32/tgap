'''
Run TGAP with N communities on real data.

    python -m realdata.run_ncommunity                 # email_eu_core, N=2,3,4
    python -m realdata.run_ncommunity tgbl_uci

Everything else in realdata/ uses two communities, because that is the
setting complex-contagion theory is stated in and the setting every earlier
result was produced in. This runner asks what the two-community restriction
was costing.

WHY EMAIL-EU-CORE IS THE RIGHT DATASET FOR THIS
    It ships GROUND-TRUTH department labels for all 1,005 people - 42 real
    departments in a real research institute. So "N communities" here does
    not mean "whatever a detector decided": at N = 4 the communities are
    four actual departments, and a bridge between two of them is a count of
    real emails between two real organisational units. No other dataset in
    the project can make that claim.

WHAT IS MEASURED
    * the pairwise bridge matrix, per N;
    * the modularity the partition captures, and how much merging to N
      discarded relative to the structure the data actually supports;
    * a TGAP explanation per community PAIR, so "which bridge does this
      model care about" becomes answerable - a question two communities
      cannot even express.

Output: output/real_data_v2/ncommunity/<dataset>/
'''

import json
import os
import sys

import pandas as pd

from core import (
    BridgeWidthMetric, BridgeWidthTransformation, CallCountingModel,
    PersistenceTemporalModel, TgapExplainer, TrendTemporalModel,
    bridgeMatrix,
)
from .adapters import edgelist
from .run_real_data import DELTAS, SEED, writeJson

OUTPUT_ROOT = os.path.join("output", "real_data_v2", "ncommunity")
COMMUNITY_COUNTS = (2, 3, 4)


def runOne(dataset, nCommunities):
    prepared = edgelist.prepare(dataset, nCommunities=nCommunities)
    partition = prepared.communities
    snapshots = prepared.snapshots
    pre = prepared.preprocessing

    print(f"\n  N = {nCommunities}")
    print(f"    communities   : {pre['partition_sizes']} "
          f"{list(partition.labels)}")
    print(f"    pairs         : {pre['community_pairs']}")
    print(f"    modularity    : {pre.get('modularity')} captured of "
          f"{pre.get('modularity_natural')} available "
          f"(lost {pre.get('modularity_lost_by_merging')}, natural k = "
          f"{pre.get('natural_n_communities')})")

    # The pairwise bridge structure, on the most recent snapshot.
    matrix = bridgeMatrix(snapshots[-1], partition)
    print(f"    bridge matrix (last snapshot):")
    for pair, width in sorted(matrix.items()):
        print(f"        {partition.labelOfPair(pair):>16s} : {width}")

    # One model per pair, each reading only its own bridge. A model that
    # reads pair (i, j) should respond to a perturbation of (i, j) and be
    # blind to the others - the N-community version of concept selectivity.
    rows = []
    for pair in partition.pairs():
        model = PersistenceTemporalModel(
            BridgeWidthMetric(partition, communityPair=pair))
        counter = CallCountingModel(model)
        transformations = [
            BridgeWidthTransformation(partition, seed=SEED,
                                      communityPair=other)
            for other in partition.pairs()]
        explainer = TgapExplainer(counter, transformations,
                                  defaultDelta=DELTAS[0])
        for record in explainer.explainDetailed(snapshots):
            rows.append({
                "dataset": dataset,
                "n_communities": nCommunities,
                "model_pair": partition.labelOfPair(pair),
                "model_pair_index": f"{pair[0]}-{pair[1]}",
                "perturbed_pair": record["transformation"],
                "perturbed_pair_index":
                    record["transformation"].split()[-1],
                "direction": "increase" if record["requestedDelta"] > 0
                             else "decrease",
                "requested_delta": record["requestedDelta"],
                "achieved_delta": record["achievedDelta"],
                "impact": record["impact"],
                "noop": record["noop"],
            })

    # An aggregate-bridge model as the control: it must react to EVERY pair,
    # because every pair contributes to the sum.
    aggregateModel = TrendTemporalModel(BridgeWidthMetric(partition))
    aggregateRows = []
    for pair in partition.pairs():
        explainer = TgapExplainer(
            aggregateModel,
            [BridgeWidthTransformation(partition, seed=SEED,
                                       communityPair=pair)],
            defaultDelta=DELTAS[0])
        for record in explainer.explainDetailed(snapshots):
            aggregateRows.append({
                "dataset": dataset, "n_communities": nCommunities,
                "model_pair": "AGGREGATE",
                "model_pair_index": "AGGREGATE",
                "perturbed_pair": record["transformation"],
                "perturbed_pair_index":
                    record["transformation"].split()[-1],
                "direction": "increase" if record["requestedDelta"] > 0
                             else "decrease",
                "requested_delta": record["requestedDelta"],
                "achieved_delta": record["achievedDelta"],
                "impact": record["impact"], "noop": record["noop"],
            })

    summary = {
        "dataset": dataset,
        "n_communities": nCommunities,
        "community_labels": list(partition.labels),
        "partition_sizes": pre["partition_sizes"],
        "community_mode": pre["community_mode"],
        "community_pairs": pre["community_pairs"],
        "modularity": pre.get("modularity"),
        "modularity_natural": pre.get("modularity_natural"),
        "modularity_lost_by_merging": pre.get("modularity_lost_by_merging"),
        "natural_n_communities": pre.get("natural_n_communities"),
        "retained_nodes": pre["retained_nodes"],
        "snapshots": len(snapshots),
        "bridge_matrix_last_snapshot": {
            partition.labelOfPair(k): v for k, v in matrix.items()},
        "seed": SEED,
    }
    return summary, rows + aggregateRows


def selectivity(rows, partition_pairs):
    ''' Did each pair-reading model respond to its own pair and to nothing
    else? Computed, not assumed. '''
    frame = pd.DataFrame([r for r in rows if r["model_pair"] != "AGGREGATE"])
    if frame.empty:
        return None
    # Match on pair INDICES. The transformation is named "Bridge Width i-j"
    # while the model carries a human label like "dept4-dept14", so the
    # earlier label-string comparison never matched and put every row in
    # `other` - making selectivity look broken when it was the check that
    # was broken.
    own = frame[frame["model_pair_index"] == frame["perturbed_pair_index"]]
    other = frame.drop(own.index)
    return {
        "rows": int(len(frame)),
        "own_pair_rows": int(len(own)),
        "own_pair_nonzero": int((own["impact"] != 0).sum()),
        "other_pair_rows": int(len(other)),
        "other_pair_exactly_zero": int((other["impact"] == 0).sum()),
        "selectivity_holds": bool((other["impact"] == 0).all()),
    }


def runDataset(dataset, counts=COMMUNITY_COUNTS):
    print("=" * 72)
    print(f"N-COMMUNITY TGAP: {dataset}")
    print("=" * 72)
    directory = os.path.join(OUTPUT_ROOT, dataset)
    os.makedirs(directory, exist_ok=True)

    summaries, allRows = [], []
    for n in counts:
        summary, rows = runOne(dataset, n)
        summaries.append(summary)
        allRows.extend(rows)

    frame = pd.DataFrame(allRows)
    frame.to_csv(os.path.join(directory, "pairwise_results.csv"), index=False)

    for summary in summaries:
        subset = [r for r in allRows
                  if r["n_communities"] == summary["n_communities"]]
        summary["pair_selectivity"] = selectivity(subset, None)

    writeJson({"dataset": dataset, "by_n": summaries},
              os.path.join(directory, "summary.json"))

    print(f"\n  {'N':>3s} {'pairs':>6s} {'modularity':>11s} "
          f"{'lost':>7s} {'selectivity holds':>18s}")
    for summary in summaries:
        holds = summary["pair_selectivity"]
        print(f"  {summary['n_communities']:>3d} "
              f"{summary['community_pairs']:>6d} "
              f"{str(summary['modularity']):>11s} "
              f"{str(summary['modularity_lost_by_merging']):>7s} "
              f"{str(holds['selectivity_holds']) if holds else '-':>18s}")
    print(f"\n  wrote {directory}")
    return summaries


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    datasets = argv or ["email_eu_core"]
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    everything = {d: runDataset(d) for d in datasets}
    writeJson(everything, os.path.join(OUTPUT_ROOT, "summary.json"))
    print("\nTwo communities can express ONE bridge. N communities express "
          "N(N-1)/2,\nand a model can care about some of them and not "
          "others - a question the\ntwo-community formulation cannot ask.")
    return everything


if __name__ == "__main__":
    main()
