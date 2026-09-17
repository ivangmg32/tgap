'''
TGAP paper evaluation suite - eight research questions, reproducible.

Relationship to evaluation.py: evaluation.py stays as the quick
developer-facing check (5 loose experiments, writes to output/). THIS file
is the paper artifact: it answers RQ1-RQ8, writes machine-readable CSVs
and publication figures to output/paper/, and emits a structured
summary.json. Neither overwrites the other's outputs.

    RQ1  known-truth faithfulness      RQ5  delta sensitivity
    RQ2  temporal sensitivity          RQ6  leakage
    RQ3  stability                     RQ7  graph-size robustness
    RQ4  efficiency                    RQ8  normalization ablation

HOW EXPECTATIONS ARE SET. Nothing is hard-coded to match the
implementation. Every expectation carries a KIND that says how much we
can legitimately claim in advance:

  EXACT    - a numeric value that follows mathematically from the model's
             definition. Example: for f = w * meanBridgeWidth under
             achieved-relative normalization, perturbing bridge width by a
             relative amount r gives dF = w * p0 * r, so
             impact = dF / |r| = +- w * p0. Errors are computed against it.
  ZERO     - provably exactly zero, because the transformation leaves the
             quantity the model reads untouched (e.g. a bridge-preserving
             rewiring fed to a model that only reads bridge width).
  MEASURED - no analytic prediction is available; the number is reported
             but no error is computed. Used wherever isolation between
             concepts is NOT guaranteed by the implementation (inspected,
             not assumed).

SCIENTIFIC FRAMING. Every number here measures MODEL SENSITIVITY to a
controlled counterfactual transformation, and the faithfulness of an
explanation to KNOWN model behavior. None of it is causal inference about
any real-world system, and no comparison against SHAP or any other method
is claimed, because none is run here.

Run from the tgap root:   python paper_evaluation.py
'''

import json
import os
import time

import matplotlib
matplotlib.use("Agg")  # file output only; no interactive window
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from core import (
    TgapExplainer,
    PersistenceTemporalModel, TrendTemporalModel,
    WeightedMetricModel, SlopeModel,
    BridgeWidthMetric, DegreeCentralizationMetric, DensityMetric,
    ClusteringMetric, CohesionMetric,
    BridgeWidthTransformation, CentralizationTransformation,
    DensityTransformation, BridgeTrendTransformation, ChurnTransformation,
    CallCountingModel, leakageReport,
    makeTemporalGraph,
)

OUTPUT = os.path.join("output", "paper")
os.makedirs(OUTPUT, exist_ok=True)

# Expectation kinds (see module docstring).
EXACT = "exact"
ZERO = "zero"
MEASURED = "measured"

# One seed drives the whole suite unless an experiment sweeps seeds.
BASE_SEED = 42

# Consistent figure style - readable, not over-styled.
FIG_SIZE = (7.0, 4.2)
plt.rcParams.update({"figure.figsize": FIG_SIZE, "font.size": 10,
                     "axes.grid": True, "grid.alpha": 0.3,
                     "savefig.dpi": 200, "savefig.bbox": "tight"})


##  Shared helpers  ##

def makeWorld(seed=BASE_SEED, nPerCommunity=15, bridgeWidth=8,
              nSnapshots=6, bridgeDrift=0, churn=0.05):
    ''' The standard controlled world: two communities, a bridge of known
    width, mild internal turnover. bridgeDrift != 0 makes the bridge grow
    or decay over time. '''
    return makeTemporalGraph(nSnapshots=nSnapshots,
                             nPerCommunity=nPerCommunity,
                             bridgeWidth=bridgeWidth, churn=churn,
                             bridgeDrift=bridgeDrift, seed=seed)


def makeTransformations(comm, seed=BASE_SEED):
    ''' The five concepts, all given the community partition so that the
    isolation guarantees the implementation DOES provide are active. '''
    return [BridgeWidthTransformation(comm, seed=seed),
            CentralizationTransformation(comm, seed=seed),
            DensityTransformation(comm, seed=seed),
            BridgeTrendTransformation(comm, seed=seed),
            ChurnTransformation(comm, seed=seed)]


def meanMetric(metric, tg):
    ''' A metric averaged over snapshots - the aggregate that
    mode="mean" models and the transformations' propertyValue both use. '''
    return float(np.mean([metric.measure(g) for g in tg]))


def savePlot(fig, name):
    path = os.path.join(OUTPUT, name)
    fig.savefig(path)
    plt.close(fig)
    return path


def saveCsv(rows, name):
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUTPUT, name), index=False)
    return df


def errorFields(expectation, measured):
    ''' Compute error columns only where an analytic ground truth exists.
    MEASURED rows get None - we refuse to invent an expected value. '''
    kind = expectation["kind"]
    if kind == MEASURED:
        return None, None, None, None
    expected = expectation["value"]
    absErr = abs(measured - expected)
    relErr = absErr / abs(expected) if expected != 0 else None
    if kind == ZERO:
        signOk = bool(measured == 0.0)
    else:
        signOk = bool(np.sign(measured) == np.sign(expected))
    return expected, absErr, relErr, signOk


##  RQ1 - known-truth faithfulness  ##

def buildKnownTruthModels(tg, comm):
    ''' Models whose concept sensitivities are derivable by hand, with the
    derivation recorded next to each expectation.

    Aggregation note: the linear models use mode="mean" so that the
    quantity the MODEL reads (mean of a metric over snapshots) is the same
    aggregate the TRANSFORMATION reports as its property. When the two
    disagree (mode="last" against a mean-based property) the analytic
    expectation only holds if the property is constant over time; RQ1 runs
    the persistence model separately to keep that case explicit. '''
    bwMetric = BridgeWidthMetric(comm)
    cMetric = DegreeCentralizationMetric()
    meanBw = meanMetric(bwMetric, tg)
    meanC = meanMetric(cMetric, tg)
    lastBw = float(bwMetric.measure(tg[-1]))

    models = {}

    # A. pure bridge width, averaged over snapshots.
    models["A-pure-bridge (mean)"] = {
        "model": WeightedMetricModel([(1.0, bwMetric)], mode="mean"),
        "terms": [(1.0, "Bridge Width", bwMetric)],
        "expect": {
            # dF = 1 * d(meanBw); impact = dF / |d(meanBw)/meanBw| = meanBw
            "Bridge Width": {"kind": EXACT, "value": meanBw},
            # bridge-preserving rewiring -> the model's input cannot move
            "Centralization": {"kind": ZERO, "value": 0.0},
            "Density": {"kind": ZERO, "value": 0.0},
            "Churn": {"kind": ZERO, "value": 0.0},
            # trend reshaping DOES change the mean width, and the achieved
            # delta is in slope units - no simple closed form
            "Bridge Trend": {"kind": MEASURED},
        },
    }

    # A'. persistence: reads ONLY the last snapshot.
    models["A-persistence (last)"] = {
        "model": PersistenceTemporalModel(bwMetric),
        "terms": [(1.0, "Bridge Width", bwMetric)],
        "expect": {
            # widths are constant in this world, so mean-relative and
            # last-relative changes coincide and impact = lastBw
            "Bridge Width": {"kind": EXACT, "value": lastBw},
            "Centralization": {"kind": ZERO, "value": 0.0},
            "Density": {"kind": ZERO, "value": 0.0},
            "Churn": {"kind": ZERO, "value": 0.0},
            # temporal transformations anchor the last snapshot
            "Bridge Trend": {"kind": ZERO, "value": 0.0},
        },
    }

    # B. pure centralization.
    models["B-pure-centralization"] = {
        "model": WeightedMetricModel([(1.0, cMetric)], mode="mean"),
        "terms": [(1.0, "Centralization", cMetric)],
        "expect": {
            "Centralization": {"kind": EXACT, "value": meanC},
            # NOT claimed zero: swapping intra<->inter edges moves degrees,
            # so centralization can move. Inspected, not assumed - reported.
            "Bridge Width": {"kind": MEASURED},
            "Density": {"kind": MEASURED},
            "Churn": {"kind": MEASURED},
            "Bridge Trend": {"kind": MEASURED},
        },
    }

    # C. two concepts with known weights.
    models["C-weighted (2bw+3c)"] = {
        "model": WeightedMetricModel([(2.0, bwMetric), (3.0, cMetric)],
                                     mode="mean"),
        "terms": [(2.0, "Bridge Width", bwMetric),
                  (3.0, "Centralization", cMetric)],
        "expect": {
            # primary term only; the residual is the centralization
            # leakage contribution, reported separately as expected_full
            "Bridge Width": {"kind": EXACT, "value": 2.0 * meanBw},
            "Centralization": {"kind": EXACT, "value": 3.0 * meanC},
            "Density": {"kind": MEASURED},
            "Churn": {"kind": MEASURED},
            "Bridge Trend": {"kind": MEASURED},
        },
    }

    # D. slope of bridge width - reads the trajectory, not the level.
    models["D-slope-of-bridge"] = {
        "model": SlopeModel(bwMetric),
        "terms": [(1.0, "Bridge Trend", None)],
        "expect": {
            # f IS the slope and BridgeTrend uses absolute deltaMode, so
            # dF == achievedDelta and impact = dF/|dF| = +-1 exactly
            "Bridge Trend": {"kind": EXACT, "value": 1.0},
            # these preserve bridge width in EVERY snapshot -> slope fixed
            "Centralization": {"kind": ZERO, "value": 0.0},
            "Density": {"kind": ZERO, "value": 0.0},
            "Churn": {"kind": ZERO, "value": 0.0},
            # multiplicative width scaling changes the slope; realization
            # depends on rounding, so no closed form
            "Bridge Width": {"kind": MEASURED},
        },
    }
    return models


def rq1Faithfulness(seed=BASE_SEED):
    ''' RQ1: can TGAP recover a dependency that is known in advance?

    For each known-truth model we also compute expected_full: the impact
    implied by the model's own definition using the MEASURED changes of
    every metric the model reads (sum_k w_k * d(p_k) / |achieved|). The
    gap between expected_primary and expected_full is exactly the leakage
    contribution, which keeps the leakage visible instead of folding it
    into an unexplained error. '''
    print("=" * 72)
    print("RQ1  KNOWN-TRUTH FAITHFULNESS")
    print("=" * 72)
    tg, comm = makeWorld(seed=seed)
    transformations = makeTransformations(comm, seed=seed)
    models = buildKnownTruthModels(tg, comm)

    rows = []
    summary = []
    for modelName, spec in models.items():
        # Metrics the model actually reads, so expected_full can be formed.
        panel = {name: metric for _, name, metric in spec["terms"]
                 if metric is not None}
        records = TgapExplainer(spec["model"], transformations
                                ).explainDetailed(tg, leakageMetrics=panel)
        weightByConcept = {name: w for w, name, m in spec["terms"]
                           if m is not None}

        magnitudes = {}
        for r in records:
            concept = r["transformation"]
            expectation = spec["expect"][concept]
            measured = r["impact"]
            direction = "increase" if r["requestedDelta"] > 0 else "decrease"
            # For a "decrease" row the derivable value flips sign.
            signedExpectation = dict(expectation)
            if expectation["kind"] != MEASURED and direction == "decrease":
                signedExpectation["value"] = -expectation["value"]
            expected, absErr, relErr, signOk = errorFields(signedExpectation,
                                                           measured)
            # Leakage-aware expectation, from measured property changes.
            expectedFull = None
            if r["achievedDelta"] not in (None, 0) and weightByConcept:
                expectedFull = sum(
                    weightByConcept[name] * r["leakage"][name]["change"]
                    for name in weightByConcept) / abs(r["achievedDelta"])
            magnitudes.setdefault(concept, []).append(abs(measured))
            rows.append({
                "experiment": "RQ1",
                "model": modelName,
                "concept": concept,
                "direction": direction,
                "expectation_kind": expectation["kind"],
                "expected": expected,
                "expected_full": expectedFull,
                "measured": measured,
                "absolute_error": absErr,
                "relative_error": relErr,
                "sign_correct": signOk,
                "achieved_delta": r["achievedDelta"],
                "requested_delta_value": r["requestedDelta"],
                "overshoot_ratio": (abs(r["achievedDelta"]) /
                                    abs(r["requestedDelta"])
                                    if r["achievedDelta"] else None),
                "normalizer": r["normalizer"],
                "noop": r["noop"],
                "seed": seed,
            })

        # Dominant concept = largest mean |impact| across both directions.
        # The margin to the runner-up is reported because two concepts can
        # come out numerically indistinguishable, in which case "which one
        # dominates" is decided by floating-point noise and the answer
        # should be read as a TIE, not as a recovery or a failure.
        meanMag = {c: float(np.mean(v)) for c, v in magnitudes.items()}
        ranked = sorted(meanMag.items(), key=lambda kv: kv[1], reverse=True)
        dominant = ranked[0][0]
        margin = ranked[0][1] - ranked[1][1] if len(ranked) > 1 else None
        tied = margin is not None and margin <= 1e-9 * max(ranked[0][1], 1.0)
        for row in rows:
            if row["model"] == modelName:
                row["is_dominant"] = (row["concept"] == dominant)

        # Which concept SHOULD dominate: the largest non-zero analytic
        # expectation, when the model has one.
        analytic = {c: abs(e["value"]) for c, e in spec["expect"].items()
                    if e["kind"] == EXACT}
        intended = max(analytic, key=analytic.get) if analytic else None
        recovered = (dominant == intended) if intended else None
        exactRows = [r for r in rows
                     if r["model"] == modelName and r["expectation_kind"] == EXACT]
        zeroRows = [r for r in rows
                    if r["model"] == modelName and r["expectation_kind"] == ZERO]
        # How far each transformation OVERSHOOTS its requested delta. This
        # matters for cross-concept comparison: a transformation whose
        # delta is a mechanism knob rather than a property ratio (e.g.
        # Centralization, where delta = fraction of edges rewired) can move
        # its property by far more than requested, and dividing by that
        # large achieved change shrinks its reported impact relative to
        # concepts that hit their target exactly.
        overshoot = {}
        for r in rows:
            if r["model"] != modelName or not r["achieved_delta"]:
                continue
            ratio = abs(r["achieved_delta"]) / abs(r["requested_delta_value"])
            overshoot.setdefault(r["concept"], []).append(ratio)
        overshootByConcept = {c: float(np.median(v))
                              for c, v in overshoot.items()}
        summary.append({
            "model": modelName,
            "intended_dominant": intended,
            "recovered_dominant": dominant,
            "dominant_correct": recovered,
            "runner_up": ranked[1][0] if len(ranked) > 1 else None,
            "dominant_margin": margin,
            "dominant_tied": tied,
            "exact_rows": len(exactRows),
            "max_relative_error": max(
                [r["relative_error"] for r in exactRows
                 if r["relative_error"] is not None], default=None),
            "zero_rows": len(zeroRows),
            "zero_rows_exactly_zero": sum(1 for r in zeroRows
                                          if r["measured"] == 0.0),
            "signs_correct": sum(1 for r in exactRows if r["sign_correct"]),
            "max_overshoot_ratio": (max(overshootByConcept.values())
                                    if overshootByConcept else None),
            "max_overshoot_concept": (max(overshootByConcept,
                                          key=overshootByConcept.get)
                                      if overshootByConcept else None),
        })
        print(f"\n{modelName}")
        for r in [x for x in rows if x["model"] == modelName]:
            exp = "-" if r["expected"] is None else f"{r['expected']:+.4f}"
            print(f"   {r['concept']:16s} {r['direction']:8s} "
                  f"measured {r['measured']:+9.4f}   expected {exp:>10s}"
                  f"   [{r['expectation_kind']}]")

    saveCsv(rows, "faithfulness.csv")
    print()
    print(pd.DataFrame(summary).to_string(index=False))
    return {"rows": rows, "summary": summary}


##  RQ2 - temporal sensitivity  ##

def rq2TemporalSensitivity(seed=BASE_SEED):
    ''' RQ2: can TGAP tell a history-reading model from a present-only
    model? Same graph, same transformations. BridgeTrend and Churn both
    leave the last snapshot untouched, so a present-only model is
    expected to be exactly insensitive to them, while a trajectory model
    can respond. Run on a DECAYING world, where a trajectory exists. '''
    print()
    print("=" * 72)
    print("RQ2  TEMPORAL SENSITIVITY")
    print("=" * 72)
    tg, comm = makeWorld(seed=seed, bridgeDrift=1)  # bridge thins over time
    bwMetric = BridgeWidthMetric(comm)
    widths = [bwMetric.measure(g) for g in tg]
    print("bridge width per snapshot:", widths)

    temporal = [BridgeTrendTransformation(comm, seed=seed),
                ChurnTransformation(comm, seed=seed)]
    models = {
        "persistence (present only)": PersistenceTemporalModel(bwMetric),
        "slope (trajectory)": SlopeModel(bwMetric),
        "trend-extrapolation (history)": TrendTemporalModel(bwMetric),
    }

    rows = []
    for modelName, model in models.items():
        for r in TgapExplainer(model, temporal).explainDetailed(tg):
            rows.append({
                "experiment": "RQ2",
                "model": modelName,
                "transformation": r["transformation"],
                "direction": "increase" if r["requestedDelta"] > 0 else "decrease",
                "baseline": r["baseline"],
                "transformed": r["transformed"],
                "impact": r["impact"],
                "achieved_delta": r["achievedDelta"],
                "noop": r["noop"],
                "seed": seed,
            })
        print(f"\n{modelName}")
        for row in [x for x in rows if x["model"] == modelName]:
            print(f"   {row['transformation']:14s} {row['direction']:8s} "
                  f"baseline {row['baseline']:+8.4f} -> "
                  f"{row['transformed']:+8.4f}   impact {row['impact']:+9.4f}")

    # Expected pattern, stated in advance: present-only model insensitive.
    persistence = [r for r in rows if r["model"].startswith("persistence")]
    trajectory = [r for r in rows if r["model"].startswith("slope")]
    check = {
        "persistence_all_zero": all(r["impact"] == 0.0 for r in persistence),
        "trajectory_responds_to_trend": any(
            r["impact"] != 0.0 for r in trajectory
            if r["transformation"] == "Bridge Trend"),
        "trajectory_churn_zero": all(
            r["impact"] == 0.0 for r in trajectory
            if r["transformation"] == "Churn"),
    }
    saveCsv(rows, "temporal_sensitivity.csv")
    print("\nconsistency with the predefined expectation:", check)

    fig, ax = plt.subplots()
    labels = sorted({f"{r['transformation']}\n{r['direction']}" for r in rows})
    width = 0.26
    xs = np.arange(len(labels))
    for i, modelName in enumerate(models):
        vals = []
        for lab in labels:
            trans, direction = lab.split("\n")
            match = [r["impact"] for r in rows if r["model"] == modelName
                     and r["transformation"] == trans
                     and r["direction"] == direction]
            vals.append(match[0] if match else 0.0)
        ax.bar(xs + (i - 1) * width, vals, width, label=modelName)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_ylabel("impact (achieved-normalized)")
    ax.set_title("RQ2: response to history-only transformations")
    ax.legend(fontsize=8)
    savePlot(fig, "temporal_sensitivity.png")
    return {"rows": rows, "check": check}


##  RQ3 - stability  ##

def rq3Stability(nSeeds=10):
    ''' RQ3: reproducibility. Three DISTINCT questions, kept separate:

      A. deterministic repeatability - same graph, same seeds, repeated
         runs. Must be exact; anything else is a bug.
      B. variation across GRAPH seeds - different random worlds of the
         same construction. Spread here is a property of the worlds.
      C. variation across TRANSFORMATION seeds - same world, different
         edge choices inside the perturbation. Spread here is a property
         of the method's own randomness.
    '''
    print()
    print("=" * 72)
    print("RQ3  STABILITY")
    print("=" * 72)
    tg, comm = makeWorld()
    model = WeightedMetricModel([(2.0, BridgeWidthMetric(comm)),
                                 (3.0, DegreeCentralizationMetric())],
                                mode="mean")

    # A. exact repeatability
    explainer = TgapExplainer(model, makeTransformations(comm))
    runs = [explainer.explain(tg) for _ in range(5)]
    repeatable = all(r == runs[0] for r in runs)
    print(f"A. deterministic repeatability (5 identical runs): {repeatable}")

    rows = []

    def collect(source, explanations):
        labels = sorted(explanations[0].keys())
        for label in labels:
            vals = np.array([e[label] for e in explanations], dtype=float)
            mean = float(vals.mean())
            std = float(vals.std(ddof=0))
            rows.append({
                "experiment": "RQ3",
                "variation_source": source,
                "label": label,
                "n": len(vals),
                "mean": mean,
                "std": std,
                "min": float(vals.min()),
                "max": float(vals.max()),
                # CV is meaningless when the mean is ~0, so leave it blank
                "coefficient_of_variation": (abs(std / mean)
                                             if abs(mean) > 1e-12 else None),
            })

    # B. across graph seeds (each seed = a different random world)
    perGraph = []
    for seed in range(nSeeds):
        tgS, commS = makeWorld(seed=seed)
        modelS = WeightedMetricModel([(2.0, BridgeWidthMetric(commS)),
                                      (3.0, DegreeCentralizationMetric())],
                                     mode="mean")
        perGraph.append(TgapExplainer(modelS, makeTransformations(commS)
                                      ).explain(tgS))
    collect("graph_seed", perGraph)

    # C. across transformation seeds (same world, different edge picks)
    perTrans = [TgapExplainer(model, makeTransformations(comm, seed=s)
                              ).explain(tg) for s in range(nSeeds)]
    collect("transformation_seed", perTrans)

    df = saveCsv(rows, "stability.csv")
    for source in ("graph_seed", "transformation_seed"):
        print(f"\nB/C. variation across {source} (n={nSeeds}):")
        sub = df[df["variation_source"] == source]
        print(sub[["label", "mean", "std", "min", "max"]].to_string(index=False))

    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    sub = df[df["variation_source"] == "graph_seed"]
    xs = np.arange(len(sub))
    ax.bar(xs, sub["mean"], yerr=sub["std"], capsize=3)
    ax.set_xticks(xs)
    ax.set_xticklabels(sub["label"], rotation=30, ha="right", fontsize=7)
    ax.set_ylabel("impact (mean +- sd)")
    ax.set_title(f"RQ3: variation across {nSeeds} graph seeds")
    savePlot(fig, "stability.png")
    return {"repeatable": bool(repeatable), "rows": rows}


##  RQ4 - efficiency  ##

def rq4Efficiency():
    ''' RQ4: cost. The local explanation should take exactly
    1 + 2K model evaluations for K transformations. The global
    (boxplot) path should take one baseline per input plus one
    evaluation per (delta, input) - i.e. baselines must NOT be
    recomputed inside the delta loop. No comparison against any other
    explanation method is made, because none is run here. '''
    print()
    print("=" * 72)
    print("RQ4  EFFICIENCY")
    print("=" * 72)
    tg, comm = makeWorld()
    allTrans = makeTransformations(comm)
    rows = []

    for k in range(1, len(allTrans) + 1):
        counter = CallCountingModel(
            PersistenceTemporalModel(BridgeWidthMetric(comm)))
        start = time.perf_counter()
        TgapExplainer(counter, allTrans[:k]).explain(tg)
        elapsed = time.perf_counter() - start
        rows.append({
            "experiment": "RQ4", "path": "local explain",
            "transformations": k, "inputs": 1, "deltas": 2,
            "expected_model_calls": 1 + 2 * k,
            "actual_model_calls": counter.calls,
            "matches_expected": counter.calls == 1 + 2 * k,
            "runtime_seconds": elapsed,
        })
        print(f"local  K={k}: expected {1 + 2 * k:2d} calls, "
              f"actual {counter.calls:2d}, {elapsed:.3f}s")

    # Global path: nValues deltas over nInputs graphs.
    nValues, nInputs = 5, 3
    worlds = [makeWorld(seed=s)[0] for s in range(nInputs)]
    counter = CallCountingModel(
        PersistenceTemporalModel(BridgeWidthMetric(comm)))
    start = time.perf_counter()
    TgapExplainer(counter, allTrans).boxplotTrans(
        worlds, trans=allTrans[0], nValues=nValues, show=False)
    elapsed = time.perf_counter() - start
    expected = nInputs + nValues * nInputs
    rows.append({
        "experiment": "RQ4", "path": "global boxplot",
        "transformations": 1, "inputs": nInputs, "deltas": nValues,
        "expected_model_calls": expected,
        "actual_model_calls": counter.calls,
        "matches_expected": counter.calls == expected,
        "runtime_seconds": elapsed,
    })
    print(f"global {nInputs} inputs x {nValues} deltas: expected {expected} "
          f"calls (baselines computed once), actual {counter.calls}, "
          f"{elapsed:.3f}s")
    saveCsv(rows, "efficiency.csv")
    return {"rows": rows,
            "all_match": all(r["matches_expected"] for r in rows)}


##  RQ5 - delta sensitivity  ##

DELTAS = (0.05, 0.10, 0.20, 0.30, 0.50)


def rq5DeltaSensitivity(seed=BASE_SEED):
    ''' RQ5: how do explanations move with the requested perturbation
    size? Graph properties are discrete, so the achieved change can
    differ substantially from the requested one; both are recorded. '''
    print()
    print("=" * 72)
    print("RQ5  DELTA SENSITIVITY")
    print("=" * 72)
    tg, comm = makeWorld(seed=seed)
    bwMetric = BridgeWidthMetric(comm)
    model = WeightedMetricModel([(1.0, bwMetric)], mode="mean")
    analytic = meanMetric(bwMetric, tg)  # the value impact should take
    rows = []
    for delta in DELTAS:
        explainer = TgapExplainer(model, [BridgeWidthTransformation(comm,
                                                                    seed=seed)],
                                  defaultDelta=delta)
        for r in explainer.explainDetailed(tg):
            rows.append({
                "experiment": "RQ5",
                "requested_delta": r["requestedDelta"],
                "direction": "increase" if r["requestedDelta"] > 0 else "decrease",
                "achieved_delta": r["achievedDelta"],
                "baseline": r["baseline"],
                "transformed": r["transformed"],
                "impact": r["impact"],
                "analytic_impact": analytic,
                "normalizer": r["normalizer"],
                "noop": r["noop"],
                "seed": seed,
            })
    df = saveCsv(rows, "delta_sensitivity.csv")
    print(df[["requested_delta", "direction", "achieved_delta", "impact",
              "analytic_impact", "noop"]].to_string(index=False))

    fig, ax = plt.subplots()
    for direction, marker in (("increase", "o"), ("decrease", "s")):
        sub = df[df["direction"] == direction]
        ax.plot(sub["requested_delta"].abs(), sub["impact"], marker=marker,
                label=f"{direction} (achieved-normalized)")
    ax.axhline(analytic, linestyle="--", color="grey",
               label=f"analytic value (+{analytic:g})")
    ax.axhline(-analytic, linestyle="--", color="grey")
    ax.set_xlabel("requested delta (ratio)")
    ax.set_ylabel("impact")
    ax.set_title("RQ5: impact vs requested perturbation size")
    ax.legend(fontsize=8)
    savePlot(fig, "delta_sensitivity.png")
    return {"rows": rows, "analytic": analytic}


##  RQ6 - leakage  ##

def rq6Leakage(seed=BASE_SEED, delta=0.1):
    ''' RQ6: how much does a transformation move properties it did not
    intend to change? Structural properties come from the metric panel;
    temporal properties (bridge-width slope, churn distance to the
    present) come from the temporal transformations' own propertyValue,
    so trajectory concepts are covered too. Zero is reported only where
    the measurement is actually zero. '''
    print()
    print("=" * 72)
    print("RQ6  LEAKAGE")
    print("=" * 72)
    tg, comm = makeWorld(seed=seed)
    panel = {
        "bridge width": BridgeWidthMetric(comm),
        "centralization": DegreeCentralizationMetric(),
        "density": DensityMetric(),
        "clustering": ClusteringMetric(),
        "cohesion": CohesionMetric(),
    }
    # Temporal properties, measured through the transformations that own them.
    trendProbe = BridgeTrendTransformation(comm, seed=seed)
    churnProbe = ChurnTransformation(comm, seed=seed)

    transformations = makeTransformations(comm, seed=seed)
    intended = {
        "Bridge Width": "bridge width",
        "Centralization": "centralization",
        "Density": "density",
        "Bridge Trend": "bridge trend slope",
        "Churn": "churn distance",
    }
    # An unconstrained density transformation is included as a contrast:
    # without the partition it is free to add cross edges.
    transformations = transformations + [DensityTransformation(seed=seed)]
    names = [t.name for t in transformations[:-1]] + ["Density (unconstrained)"]

    rows = []
    for name, trans in zip(names, transformations):
        report = leakageReport(tg, trans, delta, panel)
        tgT = trans.transform(tg, delta)
        report["bridge trend slope"] = {
            "before": trendProbe.propertyValue(tg),
            "after": trendProbe.propertyValue(tgT),
            "change": trendProbe.propertyValue(tgT) - trendProbe.propertyValue(tg)}
        report["churn distance"] = {
            "before": churnProbe.propertyValue(tg),
            "after": churnProbe.propertyValue(tgT),
            "change": churnProbe.propertyValue(tgT) - churnProbe.propertyValue(tg)}
        for prop, r in report.items():
            rows.append({
                "experiment": "RQ6",
                "transformation": name,
                "property": prop,
                "is_intended": prop == intended.get(trans.name)
                               and "unconstrained" not in name,
                "before": r["before"],
                "after": r["after"],
                "change": r["change"],
                "relative_change": (r["change"] / abs(r["before"])
                                    if r["before"] not in (0, 0.0) else None),
                "delta": delta,
                "seed": seed,
            })
    df = saveCsv(rows, "leakage.csv")
    pivot = df.pivot(index="transformation", columns="property",
                     values="change")
    print(f"change in each property at delta = +{delta} "
          f"('*' marks the intended property):")
    print(pivot.to_string())

    fig, ax = plt.subplots(figsize=(8.5, 4.0))
    # Colour by relative change so different units are comparable; the raw
    # change is printed in each cell so nothing is hidden by the scaling.
    rel = df.pivot(index="transformation", columns="property",
                   values="relative_change").astype(float)
    data = rel.to_numpy()
    limit = np.nanmax(np.abs(data)) if np.isfinite(data).any() else 1.0
    im = ax.imshow(data, cmap="RdBu_r", vmin=-limit, vmax=limit, aspect="auto")
    ax.set_xticks(range(len(rel.columns)))
    ax.set_xticklabels(rel.columns, rotation=30, ha="right", fontsize=8)
    ax.set_yticks(range(len(rel.index)))
    ax.set_yticklabels(rel.index, fontsize=8)
    raw = pivot.reindex(index=rel.index, columns=rel.columns).to_numpy()
    for i in range(raw.shape[0]):
        for j in range(raw.shape[1]):
            ax.text(j, i, f"{raw[i, j]:+.3f}", ha="center", va="center",
                    fontsize=6.5)
    ax.set_title(f"RQ6: property change per transformation (delta=+{delta});"
                 f" cells show raw change")
    fig.colorbar(im, ax=ax, label="relative change")
    ax.grid(False)
    savePlot(fig, "leakage.png")
    return {"rows": rows}


##  RQ7 - graph-size / structural robustness  ##

SIZES = (("small", 6, 4), ("medium", 15, 8), ("large", 30, 12))
RQ7_DELTAS = (0.10, 0.25)


def rq7GraphSizeRobustness(nSeeds=5):
    ''' RQ7: is the behavior a property of the method, or only of the one
    small teaching graph? Same construction (two communities, bridge width
    scaled with community size so the structure stays comparable), three
    sizes, several seeds. The analytic expectation for the pure-bridge
    model is recomputed per world, never assumed.

    DISCRETENESS FLOOR. A requested delta only moves an integer-valued
    property of size p when round(p*(1+delta)) != p, i.e. when
    |delta| >= 0.5/p. Small graphs therefore have a HIGHER minimum usable
    delta than large ones: at p=4 nothing below |delta|=0.125 can change
    anything. Each row records that threshold, so a no-op can be checked
    against the prediction rather than read as an error. Two deltas are
    swept: 0.10 (below the small-graph threshold) and 0.25 (above every
    threshold here). Error statistics are reported over non-no-op rows,
    with the no-op rate reported separately and explicitly. '''
    print()
    print("=" * 72)
    print("RQ7  GRAPH-SIZE ROBUSTNESS")
    print("=" * 72)
    rows = []
    for sizeName, nPer, bridgeWidth in SIZES:
        for seed in range(nSeeds):
            tg, comm = makeWorld(seed=seed, nPerCommunity=nPer,
                                 bridgeWidth=bridgeWidth)
            bwMetric = BridgeWidthMetric(comm)
            model = WeightedMetricModel([(1.0, bwMetric)], mode="mean")
            expected = meanMetric(bwMetric, tg)
            threshold = 0.5 / expected if expected else None
            for delta in RQ7_DELTAS:
                trans = BridgeWidthTransformation(comm, seed=seed)
                records = TgapExplainer(model, [trans], defaultDelta=delta
                                        ).explainDetailed(tg)
                for r in records:
                    tgT = trans.transform(tg, r["requestedDelta"])
                    edgesKept = all(a.number_of_edges() == b.number_of_edges()
                                    for a, b in zip(tg, tgT))
                    signed = (expected if r["requestedDelta"] > 0
                              else -expected)
                    rows.append({
                        "experiment": "RQ7",
                        "size": sizeName,
                        "nodes_per_community": nPer,
                        "nominal_bridge_width": bridgeWidth,
                        "mean_bridge_width": expected,
                        "seed": seed,
                        "requested_delta": r["requestedDelta"],
                        "discreteness_threshold": threshold,
                        "above_threshold": abs(r["requestedDelta"]) >= threshold,
                        "direction": ("increase" if r["requestedDelta"] > 0
                                      else "decrease"),
                        "expected": signed,
                        "measured": r["impact"],
                        "absolute_error": abs(r["impact"] - signed),
                        "relative_error": abs(r["impact"] - signed) / expected,
                        "achieved_delta": r["achievedDelta"],
                        "noop": r["noop"],
                        "edge_count_preserved": bool(edgesKept),
                    })
    df = saveCsv(rows, "graph_size_robustness.csv")

    # No-ops are a property of discreteness, not an explanation error, so
    # accuracy is summarised over the rows where a perturbation actually
    # took effect - and the no-op rate is reported next to it.
    active = df[~df["noop"]]
    grouped = df.groupby("size").agg(
        n=("measured", "size"),
        noop_rate=("noop", "mean"),
        threshold=("discreteness_threshold", "first"),
        noop_matches_threshold=("noop", "size"),
        edge_count_preserved_rate=("edge_count_preserved", "mean"))
    # Does every no-op coincide with a below-threshold request?
    agreement = df.groupby("size").apply(
        lambda s: bool((s["noop"] == ~s["above_threshold"]).all()),
        include_groups=False)
    grouped["noop_matches_threshold"] = agreement
    errors = active.groupby("size").agg(
        active_rows=("measured", "size"),
        mean_relative_error=("relative_error", "mean"),
        max_relative_error=("relative_error", "max"))
    grouped = grouped.join(errors).reindex([s[0] for s in SIZES])
    print(grouped.to_string())
    print("\nreading: 'threshold' is the derived minimum |delta| that can "
          "move an integer\nproperty of this size (0.5 / mean bridge width);"
          " 'noop_matches_threshold'\nchecks every no-op against that "
          "prediction. Errors are over non-no-op rows only.")

    fig, ax = plt.subplots()
    data = [active[(active["size"] == s) &
                   (active["direction"] == "increase")]["measured"]
            for s, _, _ in SIZES]
    ax.boxplot(data, tick_labels=[s for s, _, _ in SIZES])
    ax.set_ylabel("impact, Increase Bridge Width")
    ax.set_xlabel("graph size")
    ax.set_title(f"RQ7: bridge-width sensitivity across sizes "
                 f"({nSeeds} seeds, non-no-op rows)")
    savePlot(fig, "global_bridge_sensitivity.png")
    return {"rows": rows,
            "grouped": grouped.reset_index().to_dict("records")}


##  RQ8 - achieved vs requested normalization  ##

def rq8NormalizationAblation(seed=BASE_SEED):
    ''' RQ8: what difference does normalizing by the ACHIEVED property
    change make, versus the REQUESTED delta? The two coincide for
    continuous inputs; graphs are discrete, so a requested 10% on a width
    of 8 is realized as round(8*1.1)=9, an actual change of 12.5%.

    The comparison is run against a model whose correct sensitivity is
    derivable (f = mean bridge width, so the impact should equal the mean
    bridge width), and the error of BOTH modes is reported. The purpose
    is to quantify the effect of discretization, not to favour a mode. '''
    print()
    print("=" * 72)
    print("RQ8  ACHIEVED vs REQUESTED NORMALIZATION")
    print("=" * 72)
    tg, comm = makeWorld(seed=seed)
    bwMetric = BridgeWidthMetric(comm)
    model = WeightedMetricModel([(1.0, bwMetric)], mode="mean")
    analytic = meanMetric(bwMetric, tg)
    rows = []
    for delta in DELTAS:
        byMode = {}
        for mode in ("achieved", "requested"):
            explainer = TgapExplainer(
                model, [BridgeWidthTransformation(comm, seed=seed)],
                defaultDelta=delta, normalization=mode)
            byMode[mode] = explainer.explainDetailed(tg)
        for achievedRec, requestedRec in zip(byMode["achieved"],
                                             byMode["requested"]):
            direction = ("increase" if achievedRec["requestedDelta"] > 0
                         else "decrease")
            truth = analytic if direction == "increase" else -analytic
            rows.append({
                "experiment": "RQ8",
                "requested_delta": achievedRec["requestedDelta"],
                "direction": direction,
                "achieved_delta": achievedRec["achievedDelta"],
                "analytic_impact": truth,
                "impact_achieved": achievedRec["impact"],
                "impact_requested": requestedRec["impact"],
                "error_achieved": abs(achievedRec["impact"] - truth),
                "error_requested": abs(requestedRec["impact"] - truth),
                "noop_achieved": achievedRec["noop"],
                "seed": seed,
            })
    df = saveCsv(rows, "normalization_ablation.csv")
    print(df[["requested_delta", "direction", "achieved_delta",
              "analytic_impact", "impact_achieved", "impact_requested",
              "error_achieved", "error_requested"]].to_string(index=False))

    fig, ax = plt.subplots()
    sub = df[df["direction"] == "increase"]
    ax.plot(sub["requested_delta"], sub["impact_achieved"], marker="o",
            label="achieved normalization")
    ax.plot(sub["requested_delta"], sub["impact_requested"], marker="s",
            label="requested normalization")
    ax.axhline(analytic, linestyle="--", color="grey",
               label=f"analytic value ({analytic:g})")
    ax.set_xlabel("requested delta (ratio)")
    ax.set_ylabel("impact, Increase Bridge Width")
    ax.set_title("RQ8: effect of graph discretization on normalization")
    ax.legend(fontsize=8)
    savePlot(fig, "normalization_ablation.png")
    # Split the error by whether a perturbation actually took effect. Rows
    # below the discreteness floor move nothing, so BOTH modes report an
    # impact of 0 there; counting those rows against either mode would
    # confuse the discreteness limit with a normalization property.
    active = df[~df["noop_achieved"]]
    return {"rows": rows, "analytic": analytic,
            "mean_error_achieved": float(df["error_achieved"].mean()),
            "mean_error_requested": float(df["error_requested"].mean()),
            "active_rows": int(len(active)), "total_rows": int(len(df)),
            "mean_error_achieved_active": float(active["error_achieved"].mean()),
            "mean_error_requested_active": float(active["error_requested"].mean())}


##  Summary  ##

def printSummary(results):
    ''' Report measurements and whether they match the expectations that
    were fixed BEFORE running. No verdicts about the method's quality. '''
    print()
    print("=" * 72)
    print("TGAP PAPER EVALUATION SUMMARY")
    print("=" * 72)

    rq1 = results["RQ1"]["summary"]
    print("\nRQ1 Known-truth faithfulness:")
    for s in rq1:
        err = ("n/a" if s["max_relative_error"] is None
               else f"{100 * s['max_relative_error']:.2f}%")
        note = ""
        if s["dominant_tied"]:
            note = (f"  [TIE with {s['runner_up']}, margin "
                    f"{s['dominant_margin']:.1e} - not a recovery failure]")
        elif s["dominant_correct"] is False:
            note = (f"  [runner-up {s['runner_up']}, margin "
                    f"{s['dominant_margin']:.3f}]")
        print(f"   {s['model']:24s} dominant recovered: "
              f"{str(s['dominant_correct']):5s}  max rel. error: {err:>8s}  "
              f"zero-rows exactly zero: "
              f"{s['zero_rows_exactly_zero']}/{s['zero_rows']}{note}")
    # Unequal effective perturbation sizes are a confound for any
    # cross-concept magnitude comparison, so the overshoot is surfaced
    # rather than left inside the CSV.
    print("   largest achieved/requested delta ratio per model "
          "(1.0 = hit the requested size exactly):")
    for s in rq1:
        if s["max_overshoot_ratio"] is not None:
            print(f"      {s['model']:24s} {s['max_overshoot_concept']:16s} "
                  f"x{s['max_overshoot_ratio']:.2f}")

    print("\nRQ2 Temporal sensitivity:")
    for key, value in results["RQ2"]["check"].items():
        print(f"   {key:32s} {value}")

    rq3 = results["RQ3"]
    graphRows = [r for r in rq3["rows"] if r["variation_source"] == "graph_seed"]
    transRows = [r for r in rq3["rows"]
                 if r["variation_source"] == "transformation_seed"]
    print("\nRQ3 Stability:")
    print(f"   deterministic repeatability (same seed): {rq3['repeatable']}")
    print(f"   max sd across graph seeds:          "
          f"{max(r['std'] for r in graphRows):.4f}")
    print(f"   max sd across transformation seeds: "
          f"{max(r['std'] for r in transRows):.4f}")

    rq4 = results["RQ4"]
    print("\nRQ4 Efficiency:")
    for r in rq4["rows"]:
        print(f"   {r['path']:16s} K={r['transformations']} "
              f"expected {r['expected_model_calls']:2d} calls, actual "
              f"{r['actual_model_calls']:2d}, {r['runtime_seconds']:.3f}s")
    print(f"   all call counts match expectation: {rq4['all_match']}")

    rq5 = results["RQ5"]
    nonNoop = [r for r in rq5["rows"] if not r["noop"]]
    print("\nRQ5 Delta sensitivity:")
    print(f"   analytic impact for this model: {rq5['analytic']:.4f}")
    print(f"   non-noop rows: {len(nonNoop)}/{len(rq5['rows'])}; "
          f"impact range over them: "
          f"[{min(abs(r['impact']) for r in nonNoop):.4f}, "
          f"{max(abs(r['impact']) for r in nonNoop):.4f}]")

    print("\nRQ6 Leakage (largest |change| per transformation, "
          "excluding its intended property):")
    byTrans = {}
    for r in results["RQ6"]["rows"]:
        if r["is_intended"]:
            continue
        cur = byTrans.get(r["transformation"])
        if cur is None or abs(r["change"]) > abs(cur["change"]):
            byTrans[r["transformation"]] = r
    for name, r in byTrans.items():
        print(f"   {name:26s} {r['property']:20s} {r['change']:+.4f}")

    print("\nRQ7 Graph-size robustness (errors over non-no-op rows):")
    for g in results["RQ7"]["grouped"]:
        err = ("n/a" if g["mean_relative_error"] != g["mean_relative_error"]
               else f"{100 * g['mean_relative_error']:6.2f}%")
        print(f"   {g['size']:7s} n={g['n']:3d}  active={g['active_rows']:3.0f}"
              f"  mean rel. error {err:>8s}  no-op rate {g['noop_rate']:.2f}"
              f"  (threshold |delta|>={g['threshold']:.3f}, matches: "
              f"{g['noop_matches_threshold']})")

    rq8 = results["RQ8"]
    print("\nRQ8 Normalization ablation:")
    print(f"   analytic impact: {rq8['analytic']:.4f}")
    print(f"   over rows where a perturbation took effect "
          f"({rq8['active_rows']}/{rq8['total_rows']}):")
    print(f"      mean |error| achieved normalization:  "
          f"{rq8['mean_error_achieved_active']:.4f}")
    print(f"      mean |error| requested normalization: "
          f"{rq8['mean_error_requested_active']:.4f}")
    print(f"   over all rows (includes no-ops, where both modes report 0):")
    print(f"      achieved {rq8['mean_error_achieved']:.4f}   "
          f"requested {rq8['mean_error_requested']:.4f}")
    print()
    print("=" * 72)
    print("All numbers above were produced by this run. They measure model "
          "sensitivity to\ncontrolled counterfactual transformations and "
          "faithfulness to known model behavior;\nthey are not causal "
          "claims, and no comparison to another method is made here.")
    print("=" * 72)


def toJson(results):
    ''' Machine-readable summary. Rows are kept out of the JSON - they are
    already in the CSVs - so the file stays readable. '''
    payload = {
        "seed": BASE_SEED,
        "RQ1_faithfulness": results["RQ1"]["summary"],
        "RQ2_temporal_sensitivity": results["RQ2"]["check"],
        "RQ3_stability": {
            "deterministic_repeatability": results["RQ3"]["repeatable"],
            "max_std_graph_seed": max(
                r["std"] for r in results["RQ3"]["rows"]
                if r["variation_source"] == "graph_seed"),
            "max_std_transformation_seed": max(
                r["std"] for r in results["RQ3"]["rows"]
                if r["variation_source"] == "transformation_seed"),
        },
        "RQ4_efficiency": {
            "all_call_counts_match": results["RQ4"]["all_match"],
            "rows": results["RQ4"]["rows"],
        },
        "RQ5_delta_sensitivity": {"analytic_impact": results["RQ5"]["analytic"]},
        "RQ6_leakage_rows": len(results["RQ6"]["rows"]),
        "RQ7_graph_size": results["RQ7"]["grouped"],
        "RQ8_normalization": {
            "analytic_impact": results["RQ8"]["analytic"],
            "active_rows": results["RQ8"]["active_rows"],
            "total_rows": results["RQ8"]["total_rows"],
            "mean_error_achieved_active":
                results["RQ8"]["mean_error_achieved_active"],
            "mean_error_requested_active":
                results["RQ8"]["mean_error_requested_active"],
            "mean_error_achieved_all": results["RQ8"]["mean_error_achieved"],
            "mean_error_requested_all": results["RQ8"]["mean_error_requested"],
        },
    }
    path = os.path.join(OUTPUT, "summary.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=str)
    return path


def runAll():
    results = {
        "RQ1": rq1Faithfulness(),
        "RQ2": rq2TemporalSensitivity(),
        "RQ3": rq3Stability(),
        "RQ4": rq4Efficiency(),
        "RQ5": rq5DeltaSensitivity(),
        "RQ6": rq6Leakage(),
        "RQ7": rq7GraphSizeRobustness(),
        "RQ8": rq8NormalizationAblation(),
    }
    printSummary(results)
    print("\nwrote CSVs, figures and summary.json to", OUTPUT)
    toJson(results)
    return results


if __name__ == "__main__":
    runAll()
