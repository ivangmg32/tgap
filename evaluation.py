'''
TGAP evaluation - the counterpart of TSAP's GummadiEvaluation.py and
PerturbationFaithfulness.py, adapted (not copied) to what TGAP can and
should claim.

Why the evaluation differs from TSAP's: TSAP compares against SHAP on
real stock data, where no ground truth exists, so it can only measure
agreement between an explanation and model-behavior proxies (Spearman
faithfulness). TGAP's synthetic setting is stronger: we can build models
whose TRUE concept sensitivities are derivable analytically, so we can
measure explanation error against ground truth - a stricter test.
The four evaluations:

  1. FAITHFULNESS  - known-truth linear/slope models: sign agreement,
                     dominant-concept recovery, magnitude error vs the
                     analytic sensitivity, Spearman rank correlation.
  2. STABILITY     - deterministic repeatability (must be exact), and
                     ROBUSTNESS across transformation seeds (a different
                     question: how much do impacts depend on WHICH edges
                     the transformation happened to pick?).
  3. EFFICIENCY    - exact model-call counts and wall-clock time.
  4. DELTA SENSITIVITY - impacts across requested deltas; with achieved
                     normalization the impact of a linear model should be
                     (nearly) delta-INVARIANT, while requested-delta
                     normalization fluctuates with rounding. This table
                     is the empirical argument for the default.

Run from the tgap root:   python evaluation.py
Outputs: console tables + CSVs in output/.

Scientific language note: everything here measures MODEL SENSITIVITY to
controlled counterfactual transformations. It is not causal inference
about any real-world system.
'''

import os
import time

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from core import (
    TgapExplainer,
    PersistenceTemporalModel, WeightedMetricModel, SlopeModel,
    BridgeWidthMetric, DegreeCentralizationMetric, DensityMetric,
    ClusteringMetric, CohesionMetric,
    BridgeWidthTransformation, CentralizationTransformation,
    DensityTransformation, BridgeTrendTransformation, ChurnTransformation,
    CallCountingModel, leakageReport,
    makeTemporalGraph,
)

OUTPUT = "output"
os.makedirs(OUTPUT, exist_ok=True)


def makeWorld(seed=42):
    ''' The standard evaluation world: stable width-8 bridge. '''
    return makeTemporalGraph(nSnapshots=6, nPerCommunity=15, bridgeWidth=8,
                             churn=0.05, bridgeDrift=0, seed=seed)


def makeTransformations(comm, seed=42):
    return [BridgeWidthTransformation(comm, seed=seed),
            CentralizationTransformation(comm, seed=seed),
            BridgeTrendTransformation(comm, seed=seed),
            ChurnTransformation(comm, seed=seed)]


##  1. Faithfulness  ##

def evaluateFaithfulness():
    ''' Known-truth models with analytically derivable sensitivities.

    With achieved-relative normalization, a linear term w*p contributes
    an expected impact of w*p0 (semi-elasticity of a linear function);
    SlopeModel's expected BridgeTrend impact is exactly +-1 (pred IS the
    slope, normalized by the slope change). Concepts a model does not
    read have expected impact 0 (up to measured leakage). '''
    print("=" * 70)
    print("1. FAITHFULNESS against analytic ground truth")
    print("=" * 70)
    tg, comm = makeWorld()
    trans = makeTransformations(comm)
    w0 = BridgeWidthMetric(comm).measure(tg[-1])            # 8.0
    c0 = DegreeCentralizationMetric().measure(tg[-1])

    models = {
        "pure-bridge  (pred = bw)": (
            WeightedMetricModel([(1.0, BridgeWidthMetric(comm))]),
            {"Bridge Width": 1.0 * w0, "Centralization": 0.0,
             "Bridge Trend": 0.0, "Churn": 0.0}),
        "bridge+cent  (pred = 2bw+3c)": (
            WeightedMetricModel([(2.0, BridgeWidthMetric(comm)),
                                 (3.0, DegreeCentralizationMetric())]),
            {"Bridge Width": 2.0 * w0, "Centralization": 3.0 * c0,
             "Bridge Trend": 0.0, "Churn": 0.0}),
        "pure-cent    (pred = c)": (
            WeightedMetricModel([(1.0, DegreeCentralizationMetric())]),
            {"Bridge Width": 0.0, "Centralization": 1.0 * c0,
             "Bridge Trend": 0.0, "Churn": 0.0}),
        "trend-of-bw  (pred = slope bw)": (
            SlopeModel(BridgeWidthMetric(comm)),
            {"Bridge Width": None,  # trajectory-shape dependent, no analytic value
             "Centralization": 0.0, "Bridge Trend": 1.0, "Churn": 0.0}),
    }

    rows = []
    for modelName, (model, expected) in models.items():
        e = TgapExplainer(model, trans).explain(tg)
        # Collapse Increase/Decrease into one magnitude per concept
        # (mean of |impact| over both directions).
        measured = {}
        for concept in expected:
            vals = [v for k, v in e.items() if concept in k]
            measured[concept] = float(np.mean(np.abs(vals)))
        # -- dominant-concept recovery --
        expectedKnown = {k: abs(v) for k, v in expected.items()
                         if v is not None}
        trueDominant = max(expectedKnown, key=expectedKnown.get)
        measuredKnown = {k: measured[k] for k in expectedKnown}
        recoveredDominant = max(measuredKnown, key=measuredKnown.get)
        # -- sign agreement (concepts with nonzero expectation) --
        signsOk = all(
            e[f"Increase {c} (10.0%)"] > 0
            for c, v in expected.items() if v is not None and v > 0)
        # -- magnitude error where analytic values exist and nonzero --
        magErrs = [abs(measured[c] - abs(v)) / abs(v)
                   for c, v in expected.items() if v]  # skips 0 and None
        # -- Spearman: measured |impact| vs expected |sensitivity| --
        pairs = [(measured[c], abs(v)) for c, v in expected.items()
                 if v is not None]
        rho, _ = spearmanr([p[0] for p in pairs], [p[1] for p in pairs])
        rows.append({
            "model": modelName,
            "dominant recovered": recoveredDominant == trueDominant,
            "signs agree": signsOk,
            "mean magnitude error %": round(100 * np.mean(magErrs), 2)
            if magErrs else 0.0,
            "spearman rho": round(rho, 3),
        })
        print(f"\n{modelName}")
        for concept in expected:
            exp = expected[concept]
            expStr = "trajectory-dep" if exp is None else f"{abs(exp):8.3f}"
            print(f"   {concept:16s} measured {measured[concept]:8.3f}"
                  f"   expected {expStr}")
    df = pd.DataFrame(rows)
    print("\n", df.to_string(index=False))
    df.to_csv(os.path.join(OUTPUT, "faithfulness.csv"), index=False)
    return df


##  2. Stability  ##

def evaluateStability():
    ''' (a) Deterministic repeatability - must be EXACT.
        (b) Robustness across transformation seeds - the impacts'
        dependence on which particular edges were sampled. These are
        different properties; do not conflate them. '''
    print("\n" + "=" * 70)
    print("2. STABILITY")
    print("=" * 70)
    tg, comm = makeWorld()
    model = WeightedMetricModel([(2.0, BridgeWidthMetric(comm)),
                                 (3.0, DegreeCentralizationMetric())])

    # (a) determinism
    explainer = TgapExplainer(model, makeTransformations(comm))
    runs = [explainer.explain(tg) for _ in range(5)]
    deterministic = all(r == runs[0] for r in runs)
    print(f"Deterministic repeatability (5 runs identical): {deterministic}")
    assert deterministic

    # (b) robustness across transformation seeds
    perSeed = []
    for seed in range(10):
        e = TgapExplainer(model, makeTransformations(comm, seed=seed)
                          ).explain(tg)
        perSeed.append(e)
    keys = list(perSeed[0].keys())
    stats = {k: (float(np.mean([e[k] for e in perSeed])),
                 float(np.std([e[k] for e in perSeed]))) for k in keys}
    print("Across 10 transformation seeds (mean +- std):")
    for k, (mu, sd) in stats.items():
        print(f"   {k:38s} {mu:+9.3f} +- {sd:6.3f}")
    pd.DataFrame([{"label": k, "mean": mu, "std": sd}
                  for k, (mu, sd) in stats.items()]
                 ).to_csv(os.path.join(OUTPUT, "stability.csv"), index=False)
    return stats


##  3. Efficiency  ##

def evaluateEfficiency():
    print("\n" + "=" * 70)
    print("3. EFFICIENCY")
    print("=" * 70)
    tg, comm = makeWorld()
    trans = makeTransformations(comm)
    counter = CallCountingModel(
        PersistenceTemporalModel(BridgeWidthMetric(comm)))
    explainer = TgapExplainer(counter, trans)
    start = time.time()
    explainer.explain(tg)
    elapsed = time.time() - start
    print(f"transformations: {len(trans)}")
    print(f"model calls:     {counter.calls} "
          f"(claimed: 1 + 2x{len(trans)} = {1 + 2 * len(trans)})")
    print(f"wall time:       {elapsed * 1000:.1f} ms per explanation")
    assert counter.calls == 1 + 2 * len(trans)
    return counter.calls, elapsed


##  4. Delta sensitivity  ##

def evaluateDeltaSensitivity():
    ''' For pred = bridgeWidth(last), the true semi-elasticity is w0 = 8
    at every delta. Achieved normalization should return ~8 whenever the
    perturbation moves at least one edge; requested normalization
    fluctuates with the rounding ratio. This is the empirical case for
    the achieved default. '''
    print("\n" + "=" * 70)
    print("4. DELTA SENSITIVITY (pred = bridge width; true value = 8.0)")
    print("=" * 70)
    tg, comm = makeWorld()
    model = WeightedMetricModel([(1.0, BridgeWidthMetric(comm))])
    rows = []
    for delta in (0.05, 0.1, 0.2, 0.3, 0.5):
        eA = TgapExplainer(model, [BridgeWidthTransformation(comm)],
                           defaultDelta=delta).explain(tg)
        eR = TgapExplainer(model, [BridgeWidthTransformation(comm)],
                           defaultDelta=delta,
                           normalization="requested").explain(tg)
        key = f"Increase Bridge Width ({100 * delta}%)"
        rows.append({"requested delta": delta,
                     "achieved-norm impact": round(eA[key], 3),
                     "requested-norm impact": round(eR[key], 3)})
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    df.to_csv(os.path.join(OUTPUT, "delta_sensitivity.csv"), index=False)
    return df


##  5. Leakage quantification  ##

def evaluateLeakage():
    ''' Concept-independence: perturb each concept at delta=+0.1 and
    measure how EVERY panel metric moves. The transformation's own row
    is the intended change; other rows are leakage. '''
    print("\n" + "=" * 70)
    print("5. LEAKAGE PANEL (delta = +0.1, change per metric)")
    print("=" * 70)
    tg, comm = makeWorld()
    panel = {
        "bridge width": BridgeWidthMetric(comm),
        "centralization": DegreeCentralizationMetric(),
        "density": DensityMetric(),
        "clustering": ClusteringMetric(),
        "cohesion": CohesionMetric(),
    }
    intended = {
        "Bridge Width": "bridge width",
        "Centralization": "centralization",
        "Bridge Trend": "bridge width",   # trajectory of bridge width
        "Churn": None,                    # not in the panel (Jaccard)
        "Density": "density",
    }
    rows = []
    transformations = makeTransformations(comm) + \
        [DensityTransformation(comm), DensityTransformation()]
    labels = ["Bridge Width", "Centralization", "Bridge Trend", "Churn",
              "Density (intra-confined)", "Density (UNCONSTRAINED)"]
    for label, t in zip(labels, transformations):
        report = leakageReport(tg, t, 0.1, panel)
        row = {"transformation": label}
        for name, r in report.items():
            row[name] = round(r["change"], 4)
        rows.append(row)
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print("\nReading guide: each transformation's own column is the "
          "intended change;\nevery other nonzero cell is leakage. "
          "Cohesion/clustering movement under bridge\ntransformations is "
          "expected (cohesion DEPENDS on bridges - that is the point).")
    df.to_csv(os.path.join(OUTPUT, "leakage.csv"), index=False)
    return df


if __name__ == "__main__":
    evaluateFaithfulness()
    evaluateStability()
    evaluateEfficiency()
    evaluateDeltaSensitivity()
    evaluateLeakage()
    print("\nAll evaluations finished. CSVs in output/.")
