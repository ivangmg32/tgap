'''
TGAP end-to-end examples - the counterpart of TSAP's CaseStudy*.py files.

Run from the tgap root folder:

    python examples.py              # with interactive plotly charts
    python examples.py --no-show    # console output only (CI / smoke test)

What it demonstrates, in order:
  1. KNOWN-TRUTH SANITY CHECK: explain a model whose behavior we know
     exactly (persistence of BridgeWidthMetric), and verify the
     explanation says what it must say. This is the "write a trivial
     model and check TSAP tells the truth" exercise, applied to TGAP.
  2. LOCAL EXPLANATION of a cohesion-forecasting model on a decaying
     ecosystem (summary bars + sensitivity curves).
  3. GLOBAL EXPLANATION across many synthetic ecosystems (boxplots).
'''

import sys

from core import (
    # metrics
    BridgeWidthMetric, CohesionMetric, DegreeCentralizationMetric,
    # models
    PersistenceTemporalModel, TrendTemporalModel,
    # structural transformations (uniform over time)
    BridgeWidthTransformation, CentralizationTransformation,
    # temporal transformations (reshape the trajectory)
    BridgeTrendTransformation, ChurnTransformation,
    # explainer + data
    TgapExplainer, makeTemporalGraph,
)

# --no-show: keep plots off (everything still computes; figures are
# returned by the plot methods but not opened in a browser).
SHOW = "--no-show" not in sys.argv


def sanityCheck():
    ''' Explain a model we fully understand, and CHECK the explanation.

    Model: persistence of bridge width -> prediction = number of bridge
    edges in the last snapshot. Ground truth we can compute by hand
    (default ACHIEVED-change normalization; see ExplainerBase.__init__):

      * "Increase Bridge Width (10%)":  6 bridges -> round(6*1.1) = 7.
        Achieved relative change = (7-6)/6 = 1/6 (16.7%, NOT the
        requested 10% - graphs are discrete). Prediction moves +1.
        impact = +1 / (1/6) = +6.0  ... which is exactly the current
        width, i.e. the true derivative d(pred)/d(log width) of this
        model. The explainer recovers the model's real sensitivity.
      * "Decrease Bridge Width (10%)":  round(6*0.9) = 5; achieved
        change -1/6; impact = -1 / (1/6) = -6.0. Symmetric, as the
        model really is.
      * Centralization: with the partition given, its rewiring PRESERVES
        every tie's intra/inter status (see Transformations.py), so
        bridge width cannot change -> impact must be EXACTLY zero.
      * Legacy check: with normalization="requested" (TSAP's literal
        formula) the same setup must give the old +10/-10 - inflated by
        the rounding ratio (1/6)/(1/10) = 1.67. Keeping both modes
        testable documents WHY achieved is the default.

    If the explainer reports anything else, the explainer is lying. '''
    print("=" * 60)
    print("1. SANITY CHECK: known-truth model (bridge-width persistence)")
    print("=" * 60)

    temporalGraph, communities = makeTemporalGraph(
        nSnapshots=6, nPerCommunity=15, bridgeWidth=6, churn=0.05, seed=42)

    # Pass the TRUE partition everywhere (metric + BOTH transformations),
    # so nothing depends on community detection and the centralization
    # rewiring is bridge-preserving.
    model = PersistenceTemporalModel(BridgeWidthMetric(communities))
    explainer = TgapExplainer(
        model,
        transformations=[
            BridgeWidthTransformation(communities),
            CentralizationTransformation(communities),
        ])

    print("Baseline prediction (bridge width of last snapshot):",
          model.predict(temporalGraph))
    explanation = explainer.explain(temporalGraph)
    for key, value in explanation.items():
        print(f"  {key:38s} -> {value:+.3f}")

    # Automatic verification of the hand-computed truth:
    assert explanation["Increase Bridge Width (10.0%)"] == +6.0, \
        "impact must be +1 / (1/6) = +6.0 (the model's true sensitivity)"
    assert explanation["Decrease Bridge Width (10.0%)"] == -6.0, \
        "impact must be -1 / (1/6) = -6.0"
    assert explanation["Increase Centralization (10.0%)"] == 0.0, \
        "status-preserving rewiring must leave bridge width untouched"
    assert explanation["Decrease Centralization (10.0%)"] == 0.0, \
        "status-preserving rewiring must leave bridge width untouched"

    # Legacy TSAP-parity mode: dividing by the REQUESTED delta gives the
    # rounding-inflated +-10 (see the docstring above for the math).
    legacy = TgapExplainer(
        model,
        transformations=[BridgeWidthTransformation(communities)],
        normalization="requested").explain(temporalGraph)
    assert legacy["Increase Bridge Width (10.0%)"] == +10.0
    assert legacy["Decrease Bridge Width (10.0%)"] == -10.0
    print("Sanity check PASSED: achieved (+-6.0) and requested (+-10.0) "
          "normalizations both match their hand-derived values.\n")


def localExplanation():
    ''' Explain a cohesion-forecasting model on a decaying ecosystem.

    The ecosystem: two communities whose bridge LOSES one tie per
    snapshot (bridgeDrift=1) - the CATALYST bridge-decay scenario.
    The model: linear trend extrapolation of CohesionMetric (algebraic
    connectivity), i.e. "predict next period's cohesion".

    The interesting question the explanation answers: which structural
    property does predicted cohesion depend on most - the width of the
    bridge, or how centralized the communities are?

    Heads-up on reading the result: "Increase Bridge Width" can come out
    NEGATIVE here, and that is correct, not a bug. The transformation is
    MULTIPLICATIVE (each snapshot's width scaled by 1+delta), so wide
    early snapshots gain several bridges while the thin late ones gain
    none (rounding). That makes the measured cohesion DECAY STEEPER, and
    a trend-extrapolating model therefore predicts LOWER next-period
    cohesion. The explanation is faithfully exposing how this model
    reasons: it looks at the slope, not the level. (Compare with the
    persistence model in the sanity check, which looks only at the last
    snapshot.) '''
    print("=" * 60)
    print("2. LOCAL EXPLANATION: cohesion forecast on a decaying bridge")
    print("=" * 60)

    temporalGraph, communities = makeTemporalGraph(
        nSnapshots=8, nPerCommunity=15, bridgeWidth=8,
        churn=0.05, bridgeDrift=1, seed=7)

    # Show the decay so the reader sees the scenario in numbers.
    widths = [BridgeWidthMetric(communities).measure(g)
              for g in temporalGraph]
    print("Bridge width per snapshot (decaying):", widths)

    model = TrendTemporalModel(CohesionMetric())
    explainer = TgapExplainer(
        model,
        transformations=[
            BridgeWidthTransformation(communities),
            CentralizationTransformation(communities),
        ])

    print("Predicted next-period cohesion:", round(model.predict(temporalGraph), 4))
    explanation = explainer.explain(temporalGraph)
    for key, value in explanation.items():
        print(f"  {key:38s} -> {value:+.4f}")

    # Concept-independence check: how much do OTHER properties move when
    # we perturb bridge width? (Intended change vs unintended leakage.)
    from core import (DensityMetric, ClusteringMetric, leakageReport,
                      formatLeakageReport)
    panel = {
        "bridge width": BridgeWidthMetric(communities),
        "centralization": DegreeCentralizationMetric(),
        "density": DensityMetric(),
        "clustering": ClusteringMetric(),
    }
    report = leakageReport(temporalGraph,
                           BridgeWidthTransformation(communities), 0.1,
                           panel)
    print("\nLeakage panel for Increase Bridge Width (10%):"
          " ('*' = the intended property)")
    print(formatLeakageReport(report, intendedName="bridge width"))

    # The TSAP-style visuals (each returns the figure; opened if SHOW):
    explainer.plotSummary(temporalGraph,
                          title="Cohesion forecast - decaying ecosystem",
                          show=SHOW)
    explainer.plotTrans(temporalGraph,
                        trans=BridgeWidthTransformation(communities),
                        minDelta=-0.5, maxDelta=0.5, nValues=21,
                        yName="cohesion", show=SHOW)
    explainer.plotTrans(temporalGraph,
                        trans=CentralizationTransformation(communities),
                        minDelta=-0.3, maxDelta=0.3, nValues=21,
                        yName="cohesion", show=SHOW)
    print()


def globalExplanation():
    ''' Global explanation: does the cohesion model react to bridge
    width CONSISTENTLY, across many different ecosystems?

    We generate several synthetic ecosystems (different seeds = different
    random structure) and boxplot the impact distribution per delta.
    Tight boxes = a systematic effect; wide boxes = it depends on the
    particular ecosystem. '''
    print("=" * 60)
    print("3. GLOBAL EXPLANATION: many ecosystems, one boxplot")
    print("=" * 60)

    listOfTemporalGraphs = []
    communitiesList = []
    for seed in range(5):
        tg, communities = makeTemporalGraph(
            nSnapshots=6, nPerCommunity=12, bridgeWidth=6,
            churn=0.05, seed=seed)
        listOfTemporalGraphs.append(tg)
        communitiesList.append(communities)

    # All generated ecosystems share the same node numbering, so the
    # partition of the first one is valid for all (nodes 0..11 vs 12..23).
    communities = communitiesList[0]

    model = TrendTemporalModel(CohesionMetric())
    explainer = TgapExplainer(model)
    explainer.boxplotTrans(
        listOfTemporalGraphs,
        trans=BridgeWidthTransformation(communities),
        minDelta=-0.4, maxDelta=0.4, nValues=5,
        yName="cohesion", show=SHOW)
    print("Global boxplot computed over", len(listOfTemporalGraphs),
          "ecosystems.\n")


def temporalProperties():
    ''' The genuinely TEMPORAL transformations: explain what a model
    thinks about the TRAJECTORY, not just the structure.

    World: a STABLE ecosystem (constant bridge width 8, some churn).
    Two models on the same bridge-width metric:
      * trend model       - reads the whole history (fits a slope)
      * persistence model - reads ONLY the last snapshot

    Known truth we verify automatically:
      1. BLINDNESS: both temporal transformations anchor the last
         snapshot, so the persistence model's impacts must be EXACTLY
         zero - it cannot see changes to history it never reads.
      2. SENSITIVITY: for the trend model, "Increase Bridge Trend"
         (history pushed down -> rising trajectory) must RAISE the
         predicted next width, and "Decrease" must LOWER it.
      3. ORTHOGONALITY: churn (given the partition) only touches
         intra-community edges, so it changes NO snapshot's bridge
         width -> exactly zero impact on both bridge-width models.

    Then, to show churn is not a no-op in general, we explain a
    COHESION model with it: rewiring history's intra edges does change
    past cohesion values, so a trend model on cohesion reacts. '''
    print("=" * 60)
    print("4. TEMPORAL TRANSFORMATIONS: trajectory, not just structure")
    print("=" * 60)

    temporalGraph, communities = makeTemporalGraph(
        nSnapshots=6, nPerCommunity=15, bridgeWidth=8,
        churn=0.1, bridgeDrift=0, seed=11)
    widths = [BridgeWidthMetric(communities).measure(g)
              for g in temporalGraph]
    print("Bridge width per snapshot (stable):", widths)

    transformations = [
        BridgeTrendTransformation(communities),
        ChurnTransformation(communities),
    ]
    trendExplainer = TgapExplainer(
        TrendTemporalModel(BridgeWidthMetric(communities)), transformations)
    persistExplainer = TgapExplainer(
        PersistenceTemporalModel(BridgeWidthMetric(communities)),
        transformations)

    print("\nTrend model (reads the whole history):")
    trendExplanation = trendExplainer.explain(temporalGraph)
    for key, value in trendExplanation.items():
        print(f"  {key:38s} -> {value:+.3f}")

    print("Persistence model (reads only the last snapshot):")
    persistExplanation = persistExplainer.explain(temporalGraph)
    for key, value in persistExplanation.items():
        print(f"  {key:38s} -> {value:+.3f}")

    # 1. Blindness of the present-only model to changes in history:
    for key, value in persistExplanation.items():
        assert value == 0.0, \
            f"persistence model cannot react to history ({key})"
    # 2. Sensitivity of the trajectory-reading model:
    assert trendExplanation["Increase Bridge Trend (10.0%)"] > 0, \
        "a rising bridge history must raise the trend forecast"
    assert trendExplanation["Decrease Bridge Trend (10.0%)"] < 0, \
        "a decaying bridge history must lower the trend forecast"
    # 3. Orthogonality: intra-only churn never moves bridge width:
    assert trendExplanation["Increase Churn (10.0%)"] == 0.0
    assert trendExplanation["Decrease Churn (10.0%)"] == 0.0
    print("Temporal known-truth checks PASSED "
          "(blindness, sensitivity, orthogonality).\n")

    # Churn DOES matter to a model that reads structure, not bridges:
    cohesionExplainer = TgapExplainer(
        TrendTemporalModel(CohesionMetric()),
        transformations=[ChurnTransformation(communities)])
    print("Churn as seen by a cohesion-trend model (non-zero expected):")
    for key, value in cohesionExplainer.explain(temporalGraph).items():
        print(f"  {key:38s} -> {value:+.4f}")
    cohesionExplainer.plotSummary(
        temporalGraph, title="Cohesion forecast - churn sensitivity",
        show=SHOW)
    print()


if __name__ == "__main__":
    sanityCheck()
    localExplanation()
    globalExplanation()
    temporalProperties()
    print("All examples finished.")
