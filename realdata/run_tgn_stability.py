'''
Multi-seed TGN reproducibility, and matched concept comparison.

    python -m realdata.run_tgn_stability                 # email_eu_core
    python -m realdata.run_tgn_stability --seeds 0 1 2

Two things that a single-seed TGN run cannot support:

SEED STABILITY (P0.3)
    One seed tells you what happened once. Retraining the same architecture
    on the same data with a different initialisation can land somewhere
    else, and if it does, a single reported AUC is not a property of the
    method. Five fixed seeds are trained, each with the IDENTICAL temporal
    split, and every quantity is reported per seed AND as mean/std/min/max.

    The seeds are NOT pooled into one experiment. Five trainings of one
    model are five observations of a training procedure, not five
    independent samples of a population, so no confidence interval is
    computed and no significance is claimed. The purpose is
    reproducibility, not inference.

MATCHED COMPARISON (P0.2)
    The five concepts do not share units. Bridge Width, Density and Churn
    move a property by a RELATIVE amount; Centralization's delta is the
    fraction of edges rewired (a mechanism knob, not a property change);
    Bridge Trend's delta is an ABSOLUTE slope change. Ranking their raw
    impacts would compare incomparable quantities.

    The synthetic RQ1b machinery already solves this: sweep each concept
    over many deltas, then compare two concepts only at perturbations whose
    ACHIEVED changes match within a tolerance. That machinery is imported,
    not reimplemented - sweepConcept, bestMatch and MATCH_TOLERANCE come
    from paper_evaluation.

    Comparability is decided by the DATA, not asserted in advance. A pair
    with different deltaMode cannot be matched at all (the achieved changes
    are in different units); a pair with the same deltaMode is matched only
    if achieved magnitudes fall within tolerance. "not comparable" is a
    legitimate, recorded outcome, and no pair is ever forced.

NO RANKING IS PRODUCED by this module, by design.
'''

import os
import sys

import numpy as np
import pandas as pd

from core import CallCountingModel, TgapExplainer
from core.TgnModel import (TORCH_AVAILABLE, buildTgn, evaluateTgn,
                           requireTorch, splitTemporally, trainTgn)
from paper_evaluation import MATCH_TOLERANCE, bestMatch, sweepConcept
from .adapters.base import TEMPORAL_EVALUATION
from .run_real_data import (ADAPTERS, DELTAS, rowValidity, screenBridgeTrend,
                            screenFeasibility, writeJson,
                            buildTransformations as buildGated)
from .run_tgn import EPOCHS, TRAIN_FRACTION, buildTransformations

OUTPUT_ROOT = os.path.join("output", "real_data_v2", "tgn_stability")

# Five fixed seeds. Fixed, not sampled: a reproducibility check must be
# repeatable, and a random choice of seeds would defeat that.
SEEDS = (0, 1, 2, 3, 4)

# Deltas swept for matched comparison. Wider and finer than the three
# headline deltas, because matching needs candidates to choose from.
# Capped below 1.0: BridgeTrend is undefined at delta = -1.
SWEEP_DELTAS = (0.02, 0.05, 0.10, 0.15, 0.25, 0.40, 0.60, 0.90)


def runOneSeed(prepared, seed, epochs=EPOCHS):
    ''' Train, evaluate held out, explain, and gate - for one seed.

    The temporal split is computed from the snapshots alone, so it is
    IDENTICAL for every seed. Only the model initialisation and the
    training sampling change.
    '''
    requireTorch()
    snapshots = prepared.snapshots
    nodeCount = snapshots[0].number_of_nodes() + 1
    trainSnapshots, testSnapshots = splitTemporally(snapshots, TRAIN_FRACTION)

    model = buildTgn(nodeCount, seed=seed)
    losses = trainTgn(model, trainSnapshots, epochs=epochs, seed=seed)
    heldOut = evaluateTgn(model, trainSnapshots, testSnapshots, seed=seed)
    baseline = model.predict(snapshots)

    transformations = buildTransformations(prepared.communities)
    strict = buildGated(prepared.communities, strict=True)
    flags, _ = screenFeasibility(prepared, transformations, strict, DELTAS)
    trendStatuses, _ = screenBridgeTrend(prepared, transformations, DELTAS)

    rows = []
    for delta in DELTAS:
        explainer = TgapExplainer(CallCountingModel(model), transformations,
                                  defaultDelta=delta)
        for record in explainer.explainDetailed(snapshots):
            signed = record["requestedDelta"]
            validity, blank = rowValidity(record["transformation"], signed,
                                          flags, trendStatuses)
            row = {"seed": seed, "transformation": record["transformation"],
                   "direction": "increase" if signed > 0 else "decrease",
                   "requested_delta": signed,
                   "delta_mode": record["deltaMode"], **validity}
            row.update({"achieved_delta": None, "impact": None}
                       if blank else
                       {"achieved_delta": record["achievedDelta"],
                        "impact": record["impact"]})
            rows.append(row)

    return {
        "seed": seed,
        "train_snapshots": len(trainSnapshots),
        "heldout_snapshots": len(testSnapshots),
        "loss_first": losses[0], "loss_last": losses[-1],
        "auc": heldOut["auc"],
        "average_precision": heldOut["average_precision"],
        "accuracy": heldOut["accuracy"],
        "baseline_prediction": baseline,
        "valid_rows": int(sum(1 for r in rows if r["valid_for_analysis"])),
        "total_rows": len(rows),
    }, rows, model


def summarise(values, name):
    ''' mean / std / min / max over the per-seed values.

    Reported WITH the per-seed list, never instead of it: a standard
    deviation over five trainings describes spread, and collapsing the
    seeds into one number would hide an outlier.
    '''
    clean = [v for v in values if v is not None and v == v]
    if not clean:
        return {"quantity": name, "n": 0, "mean": None, "std": None,
                "min": None, "max": None, "per_seed": list(values)}
    return {
        "quantity": name, "n": len(clean),
        "mean": round(float(np.mean(clean)), 6),
        "std": round(float(np.std(clean, ddof=1)), 6) if len(clean) > 1 else 0.0,
        "min": round(float(np.min(clean)), 6),
        "max": round(float(np.max(clean)), 6),
        "per_seed": [None if v is None else round(float(v), 6) for v in values],
    }


##  Matched comparison (P0.2)  ##


def comparabilityOf(first, second):
    ''' Decide whether two concepts may be compared at all.

    The rule is a property of the transformations, not a list of names:

      * different deltaMode -> NOT comparable. One achieved change is a
        ratio, the other is in the property's own units; matching them
        would equate a percentage with a slope.
      * CentralizationTransformation -> NOT comparable to anything by
        matched achieved delta. Its delta is the FRACTION OF EDGES REWIRED
        (a mechanism knob), while its propertyValue is Freeman
        centralization, so an achieved change of 1.5 is not the same kind
        of quantity as a 0.1 relative change in bridge width. This is
        documented in the class itself.
      * otherwise -> comparable in principle; whether a match EXISTS is
        then decided by the sweep and the tolerance.
    '''
    if getattr(first, "deltaMode", "relative") != getattr(second, "deltaMode",
                                                          "relative"):
        return False, (f"different delta units ({first.deltaMode} vs "
                       f"{second.deltaMode}); achieved changes are not "
                       f"expressed in the same quantity")
    for transformation in (first, second):
        if type(transformation).__name__ == "CentralizationTransformation":
            return False, ("Centralization's delta is a rewiring fraction "
                           "(a mechanism knob), not a relative change of "
                           "the measured property, so its achieved delta "
                           "is not commensurable with the others")
    return True, None


def matchedComparison(model, snapshots, transformations, seed):
    ''' Pairwise matched comparison for one trained model.

    Reuses sweepConcept and bestMatch from paper_evaluation; the matching
    algorithm is NOT reimplemented here.
    '''
    sweeps = {}
    for transformation in transformations:
        try:
            sweeps[transformation.name] = sweepConcept(
                model, snapshots, transformation, SWEEP_DELTAS)
        except Exception as failure:          # e.g. an undefined delta
            sweeps[transformation.name] = []
            print(f"      sweep failed for {transformation.name}: {failure}")

    rows = []
    for i, first in enumerate(transformations):
        for second in transformations[i + 1:]:
            comparable, reason = comparabilityOf(first, second)
            for direction in ("increase", "decrease"):
                base = {"seed": seed, "concept_a": first.name,
                        "concept_b": second.name, "direction": direction}
                if not comparable:
                    rows.append({**base, "comparable": False,
                                 "reason": reason,
                                 "requested_delta_a": None,
                                 "requested_delta_b": None,
                                 "achieved_delta_a": None,
                                 "achieved_delta_b": None,
                                 "impact_a": None, "impact_b": None})
                    continue
                match = bestMatch(sweeps.get(first.name, []),
                                  sweeps.get(second.name, []), direction,
                                  tolerance=MATCH_TOLERANCE)
                if not match:
                    rows.append({**base, "comparable": False,
                                 "reason": ("no achieved-delta match within "
                                            f"tolerance {MATCH_TOLERANCE}"),
                                 "requested_delta_a": None,
                                 "requested_delta_b": None,
                                 "achieved_delta_a": None,
                                 "achieved_delta_b": None,
                                 "impact_a": None, "impact_b": None})
                    continue
                # bestMatch returns (rowA, rowB, gap); its rows use the
                # snake_case keys sweepConcept emits.
                a, b, gap = match
                rows.append({
                    **base, "comparable": True, "reason": "matched",
                    "requested_delta_a": a["requested_delta"],
                    "requested_delta_b": b["requested_delta"],
                    "achieved_delta_a": a["achieved_delta"],
                    "achieved_delta_b": b["achieved_delta"],
                    "impact_a": a["impact"], "impact_b": b["impact"],
                    "relative_gap": gap,
                })
    return rows


def main(argv=None):
    if not TORCH_AVAILABLE:
        print("PyTorch / PyTorch Geometric not available - skipping.")
        return None
    argv = list(argv if argv is not None else sys.argv[1:])
    seeds = list(SEEDS)
    if "--seeds" in argv:
        index = argv.index("--seeds")
        seeds = [int(x) for x in argv[index + 1:]]
        argv = argv[:index]
    dataset = argv[0] if argv else "email_eu_core"

    print("=" * 72)
    print(f"TGN SEED STABILITY + MATCHED COMPARISON: {dataset}")
    print("=" * 72)
    prepared = ADAPTERS[dataset](TEMPORAL_EVALUATION)
    directory = os.path.join(OUTPUT_ROOT, dataset)
    os.makedirs(directory, exist_ok=True)

    perSeed, allRows, matchedRows = [], [], []
    splits = set()
    for seed in seeds:
        summary, rows, model = runOneSeed(prepared, seed)
        splits.add((summary["train_snapshots"], summary["heldout_snapshots"]))
        perSeed.append(summary)
        allRows.extend(rows)
        print(f"  seed {seed}: AUC {summary['auc']}  AP "
              f"{summary['average_precision']}  acc {summary['accuracy']}  "
              f"baseline {summary['baseline_prediction']:.4f}  "
              f"valid {summary['valid_rows']}/{summary['total_rows']}")
        matchedRows.extend(matchedComparison(
            model, prepared.snapshots,
            buildTransformations(prepared.communities), seed))

    # Every seed must have used the SAME split, or the numbers are not
    # comparable across seeds.
    assert len(splits) == 1, f"temporal split differed across seeds: {splits}"

    pd.DataFrame(allRows).to_csv(
        os.path.join(directory, "per_seed_explanations.csv"), index=False)
    matched = pd.DataFrame(matchedRows)
    matched.to_csv(os.path.join(directory, "matched_comparison.csv"),
                   index=False)

    stability = [summarise([s[key] for s in perSeed], key)
                 for key in ("auc", "average_precision", "accuracy",
                             "baseline_prediction", "valid_rows")]
    pd.DataFrame(stability).to_csv(
        os.path.join(directory, "seed_stability.csv"), index=False)

    print()
    print(f"  {'quantity':22s} {'mean':>10s} {'std':>10s} {'min':>10s} {'max':>10s}")
    for row in stability:
        print(f"  {row['quantity']:22s} {str(row['mean']):>10s} "
              f"{str(row['std']):>10s} {str(row['min']):>10s} "
              f"{str(row['max']):>10s}")

    comparablePairs = int(matched["comparable"].sum()) if not matched.empty else 0
    print()
    print(f"  matched comparison: {comparablePairs}/{len(matched)} pair-rows "
          f"comparable")
    if not matched.empty:
        for reason, count in matched[~matched["comparable"]][
                "reason"].value_counts().items():
            print(f"      not comparable ({count}): {reason[:60]}")

    writeJson({
        "dataset": dataset,
        "seeds": seeds,
        "epochs": EPOCHS,
        "train_fraction": TRAIN_FRACTION,
        "temporal_split": sorted(splits)[0],
        "split_identical_across_seeds": True,
        "per_seed": perSeed,
        "stability": stability,
        "matched_comparison_rows": len(matched),
        "matched_comparison_comparable": comparablePairs,
        "match_tolerance": MATCH_TOLERANCE,
        "sweep_deltas": list(SWEEP_DELTAS),
        "no_ranking_note": (
            "No ranking of concepts is produced. Raw impacts across concepts "
            "use incompatible perturbation units; only matched pairs are "
            "compared, and a matched comparison reports two numbers side by "
            "side rather than an ordering."),
        "pooling_note": (
            "Seeds are reported per seed and summarised by mean/std/min/max. "
            "They are five runs of one training procedure, not independent "
            "samples of a population, so no confidence interval or "
            "significance test is computed."),
    }, os.path.join(directory, "summary.json"))
    print(f"\n  wrote {directory}")
    return perSeed, matched


if __name__ == "__main__":
    main()
