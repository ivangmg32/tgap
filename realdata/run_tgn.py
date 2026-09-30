'''
Explain a TRAINED TGN with TGAP, on Email-Eu-core.

    python -m realdata.run_tgn                    # email_eu_core
    python -m realdata.run_tgn decentraland       # any prepared dataset

This is the chain section 18 of the design asks for, end to end:

    Email-Eu-core temporal events
        -> leakage-safe preprocessing (realdata/adapters)
        -> TGN trained by self-supervised link prediction
        -> TgnTemporalGraphModel.predict(temporalGraph) -> float
        -> TgapExplainer with the usual five concepts
        -> impact per concept
        -> output/real_data_v2/tgn/<dataset>/

WHY THIS MATTERS SCIENTIFICALLY
    Every other model in this project is a closed-form graph metric, so a
    sceptic can object that TGAP only ever explained functions whose
    behaviour was obvious in advance. A trained neural network removes that
    objection: nobody knows a priori which structural concept a TGN's
    link-prediction score depends on. Whatever TGAP reports here is
    genuinely informative about the model rather than a restatement of its
    definition.

HONEST SCOPE
    The TGN is trained briefly and is NOT tuned for benchmark performance.
    The claim is "TGAP explains a real learned temporal-graph model", not
    "this TGN is competitive". Reporting it as the latter would be
    unsupported. Training loss is written to the output so a reader can see
    what was actually achieved rather than take it on trust.
'''

import json
import os
import sys
import time

from core import (
    BridgeTrendTransformation, BridgeWidthTransformation, CallCountingModel,
    CentralizationTransformation, ChurnTransformation, DensityTransformation,
)
from core.TemporalGraphExplainer import TgapExplainer
from core.TgnModel import TORCH_AVAILABLE, buildTgn, requireTorch, trainTgn
from .run_real_data import ADAPTERS, DELTAS, SEED, writeJson
from .adapters.base import TEMPORAL_EVALUATION

OUTPUT_ROOT = os.path.join("output", "real_data_v2", "tgn")
EPOCHS = 5


def buildTransformations(communities):
    ''' The same five concepts used for every metric-based model, so the
    learned model's explanation is directly comparable with theirs. '''
    return [
        BridgeWidthTransformation(communities, seed=SEED),
        CentralizationTransformation(communities, seed=SEED),
        DensityTransformation(communities, seed=SEED),
        BridgeTrendTransformation(communities, seed=SEED),
        ChurnTransformation(communities, seed=SEED),
    ]


def runDataset(key, mode=TEMPORAL_EVALUATION, epochs=EPOCHS):
    requireTorch()
    print("=" * 72)
    print(f"TGN + TGAP: {key}   [analysis_mode = {mode}]")
    print("=" * 72)

    prepared = ADAPTERS[key](mode)
    snapshots = prepared.snapshots
    nodeCount = snapshots[0].number_of_nodes()
    print(f"  snapshots     : {len(snapshots)}")
    print(f"  nodes         : {nodeCount}")
    print(f"  partition     : {prepared.preprocessing['partition_sizes']} "
          f"[{prepared.preprocessing['community_mode']}]")

    # nodeCount + 1 because TGN indexes memory by contiguous id and the
    # adapter assigns ids lazily; the spare slot avoids an off-by-one when
    # a perturbation introduces a node the replay had not yet numbered.
    model = buildTgn(nodeCount + 1, seed=SEED)

    started = time.perf_counter()
    losses = trainTgn(model, snapshots, epochs=epochs, seed=SEED)
    trainingSeconds = time.perf_counter() - started
    print(f"  training      : {epochs} epochs in {trainingSeconds:.1f}s")
    print(f"  loss by epoch : {[round(l, 4) for l in losses]}")
    if len(losses) > 1 and losses[-1] < losses[0]:
        print(f"  -> loss fell {losses[0]:.4f} -> {losses[-1]:.4f}: the model "
              f"learned something")
    else:
        print(f"  -> loss did NOT fall; treat the explanation with caution")

    baseline = model.predict(snapshots)
    print(f"  baseline      : {baseline:.6f} "
          f"(mean predicted probability of the present snapshot's edges)")

    transformations = buildTransformations(prepared.communities)
    rows = []
    for delta in DELTAS:
        counter = CallCountingModel(model)
        explainer = TgapExplainer(counter, transformations,
                                  defaultDelta=delta)
        started = time.perf_counter()
        for record in explainer.explainDetailed(snapshots):
            rows.append({
                "dataset": key,
                "analysis_mode": mode,
                "model": "tgn_link_prediction",
                "transformation": record["transformation"],
                "direction": "increase" if record["requestedDelta"] > 0
                             else "decrease",
                "requested_delta": record["requestedDelta"],
                "achieved_delta": record["achievedDelta"],
                "baseline_prediction": record["baseline"],
                "after_prediction": record["transformed"],
                "prediction_change": record["transformed"] - record["baseline"],
                "impact": record["impact"],
                "normalizer": record["normalizer"],
                "noop": record["noop"],
                "seed": SEED,
            })
        print(f"  delta {delta:<5} : {counter.calls} model calls "
              f"(= 1 + 2x{len(transformations)}) in "
              f"{time.perf_counter() - started:.1f}s")

    directory = os.path.join(OUTPUT_ROOT, key)
    os.makedirs(directory, exist_ok=True)

    import pandas as pd
    frame = pd.DataFrame(rows)
    frame.to_csv(os.path.join(directory, "tgap_results.csv"), index=False)

    reference = frame[(frame["requested_delta"] == DELTAS[0])
                      & (frame["direction"] == "increase")]
    print()
    print(f"  {'concept':18s} {'achieved':>10s} {'impact':>12s}")
    for _, row in reference.iterrows():
        print(f"  {row['transformation']:18s} {row['achieved_delta']:>10.4f} "
              f"{row['impact']:>12.4f}")

    summary = {
        "dataset": key,
        "analysis_mode": mode,
        "model": "TGN (torch_geometric) + link-prediction readout",
        "nodes": nodeCount,
        "snapshots": len(snapshots),
        "training_epochs": epochs,
        "training_seconds": round(trainingSeconds, 2),
        "loss_by_epoch": losses,
        "loss_decreased": bool(len(losses) > 1 and losses[-1] < losses[0]),
        "baseline_prediction": baseline,
        "model_calls_per_delta": 1 + 2 * len(transformations),
        "deltas": list(DELTAS),
        "seed": SEED,
        "explanation_rows": len(frame),
        "largest_absolute_impact": (
            frame.loc[frame["impact"].abs().idxmax(),
                      ["transformation", "direction", "impact"]].to_dict()
            if not frame.empty else None),
        "scope_note": (
            "The TGN is trained briefly and is not tuned for benchmark "
            "performance. The claim demonstrated here is that TGAP can "
            "explain a genuinely learned temporal-graph model through the "
            "predict(temporalGraph) contract alone - no gradients, no access "
            "to memory or attention internals."),
    }
    writeJson(summary, os.path.join(directory, "summary.json"))
    print(f"\n  wrote {directory}")
    return summary


def main(argv=None):
    if not TORCH_AVAILABLE:
        print("PyTorch / PyTorch Geometric not available - skipping TGN.")
        print("Install with:")
        print("    pip install torch --index-url "
              "https://download.pytorch.org/whl/cpu")
        print("    pip install torch_geometric")
        return None
    argv = list(argv if argv is not None else sys.argv[1:])
    keys = argv or ["email_eu_core"]
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    summaries = {key: runDataset(key) for key in keys}
    writeJson(summaries, os.path.join(OUTPUT_ROOT, "summary.json"))
    print("\nTGAP explained a trained TGN through predict(temporalGraph) "
          "alone.\nNothing in core/ knows a neural network was involved.")
    return summaries


if __name__ == "__main__":
    main()
