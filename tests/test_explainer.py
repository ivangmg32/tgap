''' Explainer tests: normalization math, efficiency (exact model-call
counts), stability, faithfulness on known-truth models, and provenance
records. '''

import unittest

from core import (
    TgapExplainer,
    PersistenceTemporalModel, TrendTemporalModel,
    WeightedMetricModel, SlopeModel,
    BridgeWidthMetric, DegreeCentralizationMetric,
    BridgeWidthTransformation, CentralizationTransformation,
    BridgeTrendTransformation, ChurnTransformation,
    CallCountingModel,
    makeTemporalGraph, makeScenario,
)


class ExplainerTestCase(unittest.TestCase):
    def setUp(self):
        # Standard stable world: width exactly 8 in every snapshot.
        self.tg, self.comm = makeTemporalGraph(
            nSnapshots=6, nPerCommunity=15, bridgeWidth=8,
            churn=0.05, bridgeDrift=0, seed=42)
        self.structural = [BridgeWidthTransformation(self.comm),
                           CentralizationTransformation(self.comm)]


class TestNormalization(ExplainerTestCase):
    def testAchievedIsTrueSensitivity(self):
        ''' Persistence-of-width model: impact must equal the current
        width exactly (+-8), because achieved normalization recovers
        d(pred)/d(log width) = width for pred = width. '''
        model = PersistenceTemporalModel(BridgeWidthMetric(self.comm))
        e = TgapExplainer(model, self.structural).explain(self.tg)
        self.assertEqual(e["Increase Bridge Width (10.0%)"], +8.0)
        self.assertEqual(e["Decrease Bridge Width (10.0%)"], -8.0)

    def testRequestedModeMatchesTsapFormula(self):
        ''' Legacy mode: divide by the requested 0.1. Width 8, delta
        +0.1 -> round(8.8)=9, so +1 edge / 0.1 = +10; -0.1 -> 7 -> -10. '''
        model = PersistenceTemporalModel(BridgeWidthMetric(self.comm))
        e = TgapExplainer(model, self.structural,
                          normalization="requested").explain(self.tg)
        self.assertEqual(e["Increase Bridge Width (10.0%)"], +10.0)
        self.assertEqual(e["Decrease Bridge Width (10.0%)"], -10.0)

    def testNoopReportedHonestly(self):
        ''' A delta too small to move one edge must yield impact 0 and
        noop=True in the detailed record, not a fake sensitivity. '''
        model = PersistenceTemporalModel(BridgeWidthMetric(self.comm))
        explainer = TgapExplainer(
            model, [BridgeWidthTransformation(self.comm)], defaultDelta=0.01)
        records = explainer.explainDetailed(self.tg)
        for r in records:
            self.assertEqual(r["impact"], 0.0)
            self.assertTrue(r["noop"])

    def testProvenanceFields(self):
        model = PersistenceTemporalModel(BridgeWidthMetric(self.comm))
        r = TgapExplainer(model, self.structural).explainDetailed(self.tg)[0]
        self.assertEqual(r["transformation"], "Bridge Width")
        self.assertEqual(r["requestedDelta"], 0.1)
        self.assertAlmostEqual(r["achievedDelta"], 1 / 8)  # 8 -> 9
        self.assertEqual(r["normalizer"], "achieved")
        self.assertEqual(r["deltaMode"], "relative")


class TestEfficiency(ExplainerTestCase):
    def testExplainCostsOnePlusTwoK(self):
        ''' The complexity claim, verified by counting: 1 baseline +
        2 calls per transformation. Achieved normalization and property
        measurement must add ZERO model calls. '''
        counter = CallCountingModel(
            PersistenceTemporalModel(BridgeWidthMetric(self.comm)))
        TgapExplainer(counter, self.structural).explain(self.tg)
        self.assertEqual(counter.calls, 1 + 2 * len(self.structural))

    def testBoxplotBaselineNotRecomputed(self):
        ''' After the audit-#5 fix: len(xs) baselines + nValues*len(xs)
        perturbed predictions - not a baseline per (delta, x) pair. '''
        counter = CallCountingModel(
            PersistenceTemporalModel(BridgeWidthMetric(self.comm)))
        explainer = TgapExplainer(counter, self.structural)
        xs = [self.tg, self.tg]
        nValues = 3
        explainer.boxplotTrans(xs, trans=self.structural[0],
                               nValues=nValues, show=False)
        self.assertEqual(counter.calls, len(xs) + nValues * len(xs))


class TestStability(ExplainerTestCase):
    def testDeterministicStability(self):
        ''' Same graph, model, seed, delta: byte-identical explanations,
        run after run. '''
        model = TrendTemporalModel(BridgeWidthMetric(self.comm))
        explainer = TgapExplainer(model, [
            BridgeWidthTransformation(self.comm),
            CentralizationTransformation(self.comm),
            BridgeTrendTransformation(self.comm),
            ChurnTransformation(self.comm)])
        self.assertEqual(explainer.explain(self.tg),
                         explainer.explain(self.tg))


class TestFaithfulnessKnownTruth(ExplainerTestCase):
    ''' Models with pen-and-paper-derivable explanations. '''

    def testLinearModelRecoverySingleConcept(self):
        ''' pred = bridgeWidth(last). Expected impact of the bridge
        transformation under achieved-relative normalization:
        weight * width = 1 * 8 (up to leakage = 0 here, since the model
        reads ONLY bridge width). Centralization impact must be 0. '''
        model = WeightedMetricModel([(1.0, BridgeWidthMetric(self.comm))])
        e = TgapExplainer(model, self.structural).explain(self.tg)
        self.assertEqual(e["Increase Bridge Width (10.0%)"], 8.0)
        self.assertEqual(e["Increase Centralization (10.0%)"], 0.0)
        self.assertEqual(e["Decrease Centralization (10.0%)"], 0.0)

    def testLinearModelTwoConcepts(self):
        ''' pred = 2*bridgeWidth + 3*centralization. Bridge impact should
        be ~2*8 = 16 plus bounded leakage through the centralization term
        (bridge rewiring moves degrees slightly). Dominant concept must
        be recovered. '''
        model = WeightedMetricModel([
            (2.0, BridgeWidthMetric(self.comm)),
            (3.0, DegreeCentralizationMetric()),
        ])
        e = TgapExplainer(model, self.structural).explain(self.tg)
        self.assertAlmostEqual(e["Increase Bridge Width (10.0%)"], 16.0,
                               delta=1.5)  # leakage tolerance, measured
        # Concept recovery: bridge dominates centralization.
        self.assertGreater(abs(e["Increase Bridge Width (10.0%)"]),
                           abs(e["Increase Centralization (10.0%)"]))
        # Sign agreement: both concepts have positive weights.
        self.assertGreater(e["Increase Bridge Width (10.0%)"], 0)
        self.assertGreater(e["Increase Centralization (10.0%)"], 0)

    def testSlopeModelReadsOnlyTrajectory(self):
        ''' pred = slope of width series. Must react to BridgeTrend with
        the right signs, and be EXACTLY blind to churn (which never
        touches any snapshot's width). '''
        model = SlopeModel(BridgeWidthMetric(self.comm))
        e = TgapExplainer(model, [
            BridgeTrendTransformation(self.comm),
            ChurnTransformation(self.comm)]).explain(self.tg)
        self.assertGreater(e["Increase Bridge Trend (10.0%)"], 0)
        self.assertLess(e["Decrease Bridge Trend (10.0%)"], 0)
        self.assertEqual(e["Increase Churn (10.0%)"], 0.0)
        self.assertEqual(e["Decrease Churn (10.0%)"], 0.0)

    def testPersistenceBlindToHistory(self):
        ''' The blindness theorem: temporal transformations anchor the
        last snapshot; a present-only model cannot react. '''
        model = PersistenceTemporalModel(BridgeWidthMetric(self.comm))
        e = TgapExplainer(model, [
            BridgeTrendTransformation(self.comm),
            ChurnTransformation(self.comm)]).explain(self.tg)
        for value in e.values():
            self.assertEqual(value, 0.0)


class TestScenariosAndDefaults(unittest.TestCase):
    def testAllScenariosBuild(self):
        from core import SCENARIOS
        for name in SCENARIOS:
            tg, comm, info = makeScenario(name)
            self.assertEqual(info["name"], name)
            self.assertGreater(len(tg), 1)
            setA, setB = comm
            for g in tg:
                self.assertEqual(set(g.nodes()), setA | setB)

    def testScenarioTrendGroundTruth(self):
        ''' The decaying/growing scenarios must actually have the trend
        their ground truth claims (measured, not assumed). '''
        for name, sign in (("decaying-bridge", -1), ("growing-bridge", +1)):
            tg, comm, info = makeScenario(name)
            slope = BridgeTrendTransformation(comm).propertyValue(tg)
            self.assertEqual(info["groundTruth"]["bridgeTrendSign"], sign)
            self.assertGreater(sign * slope, 0)

    def testLazyDefaultsAreLeakFree(self):
        ''' TgapExplainer(model) with NO transformations: the defaults
        must share one detected partition, so default centralization
        cannot leak into default bridge width. On the synthetic world
        detection recovers the planted partition, so the bridge-width
        impacts match the explicit-partition ones. '''
        tg, comm = makeTemporalGraph(nSnapshots=6, nPerCommunity=15,
                                     bridgeWidth=8, seed=42)
        model = PersistenceTemporalModel(BridgeWidthMetric(comm))
        e = TgapExplainer(model).explain(tg)  # no transformations passed
        self.assertEqual(e["Increase Centralization (10.0%)"], 0.0)
        self.assertEqual(e["Increase Bridge Width (10.0%)"], 8.0)


if __name__ == "__main__":
    unittest.main()
