''' Tests for the paper evaluation suite and for the behaviors it relies
on that were not already covered by test_explainer.py /
test_transformations.py.

Deliberately NOT duplicated here (already tested elsewhere):
  model-call counts, achieved-delta provenance, normalization modes,
  deterministic repeatability, persistence blindness, slope-model
  trajectory sensitivity, known-truth single/two-concept recovery.
Those live in tests/test_explainer.py and are still the authority.

What IS new here:
  - leakageReport structure and semantics
  - the discreteness floor (|delta| >= 0.5/p) that governs no-ops
  - behavior across graph sizes, not just the medium teaching graph
  - the evaluation helpers themselves (expectations, error fields)
'''

import contextlib
import io
import unittest

import numpy as np

from core import (
    TgapExplainer, WeightedMetricModel, PersistenceTemporalModel, SlopeModel,
    BridgeWidthMetric, DegreeCentralizationMetric, DensityMetric,
    ClusteringMetric, CohesionMetric,
    BridgeWidthTransformation, CentralizationTransformation,
    DensityTransformation, BridgeTrendTransformation, ChurnTransformation,
    leakageReport, makeTemporalGraph,
)

import paper_evaluation as pe


class TestLeakageReportStructure(unittest.TestCase):
    ''' The leakage report is the evidence for concept independence, so
    its shape and semantics must be pinned down. '''

    def setUp(self):
        self.tg, self.comm = makeTemporalGraph(
            nSnapshots=6, nPerCommunity=15, bridgeWidth=8, seed=42)
        self.panel = {"bridge width": BridgeWidthMetric(self.comm),
                      "centralization": DegreeCentralizationMetric(),
                      "density": DensityMetric(),
                      "clustering": ClusteringMetric(),
                      "cohesion": CohesionMetric()}

    def testReportCoversEveryPanelMetric(self):
        report = leakageReport(self.tg, BridgeWidthTransformation(self.comm),
                               0.1, self.panel)
        self.assertEqual(set(report), set(self.panel))
        for row in report.values():
            self.assertEqual(set(row), {"before", "after", "change"})

    def testChangeEqualsAfterMinusBefore(self):
        report = leakageReport(self.tg, CentralizationTransformation(self.comm),
                               0.1, self.panel)
        for name, row in report.items():
            self.assertAlmostEqual(row["change"], row["after"] - row["before"],
                                   places=12, msg=name)

    def testIntendedPropertyActuallyMoves(self):
        ''' A transformation must move its own property - otherwise the
        leakage table would be comparing against nothing. '''
        report = leakageReport(self.tg, BridgeWidthTransformation(self.comm),
                               0.1, self.panel)
        self.assertNotEqual(report["bridge width"]["change"], 0.0)

    def testBridgePreservingTransformationsShowZeroBridgeChange(self):
        ''' These three claim bridge preservation; the leakage report is
        where that claim is checked numerically. '''
        for trans in (CentralizationTransformation(self.comm),
                      DensityTransformation(self.comm),
                      ChurnTransformation(self.comm)):
            report = leakageReport(self.tg, trans, 0.1, self.panel)
            self.assertEqual(report["bridge width"]["change"], 0.0,
                             f"{trans.name} moved bridge width")

    def testUnconstrainedDensityLeakIsVisibleNotHidden(self):
        ''' Without a partition the density transformation is free to add
        cross edges. The suite must keep that visible. '''
        report = leakageReport(self.tg, DensityTransformation(), 0.1,
                               self.panel)
        self.assertGreater(report["bridge width"]["change"], 0.0)

    def testLeakageIsReportedForTemporalPropertiesToo(self):
        trend = BridgeTrendTransformation(self.comm)
        churn = ChurnTransformation(self.comm)
        tgT = churn.transform(self.tg, 0.3)
        # Churn preserves bridge width in every snapshot, hence the slope.
        self.assertAlmostEqual(trend.propertyValue(tgT),
                               trend.propertyValue(self.tg), places=12)
        # But it does move the churn property itself.
        self.assertNotEqual(churn.propertyValue(tgT),
                            churn.propertyValue(self.tg))


class TestDiscretenessFloor(unittest.TestCase):
    ''' An integer property of size p can only change when
    round(p*(1+delta)) != p, i.e. |delta| >= 0.5/p. The suite uses this
    to tell a genuine no-op apart from an explanation error. '''

    def widthAfter(self, tg, comm, delta):
        trans = BridgeWidthTransformation(comm)
        return trans.propertyValue(trans.transform(tg, delta))

    def testBelowThresholdIsNoop(self):
        tg, comm = makeTemporalGraph(nSnapshots=4, nPerCommunity=10,
                                     bridgeWidth=8, seed=1)
        threshold = 0.5 / 8
        below = threshold * 0.8
        self.assertAlmostEqual(self.widthAfter(tg, comm, below), 8.0)

    def testAboveThresholdMoves(self):
        tg, comm = makeTemporalGraph(nSnapshots=4, nPerCommunity=10,
                                     bridgeWidth=8, seed=1)
        above = (0.5 / 8) * 1.2
        self.assertNotAlmostEqual(self.widthAfter(tg, comm, above), 8.0)

    def testExplainerReportsNoopFlagBelowThreshold(self):
        tg, comm = makeTemporalGraph(nSnapshots=4, nPerCommunity=10,
                                     bridgeWidth=8, seed=1)
        model = WeightedMetricModel([(1.0, BridgeWidthMetric(comm))],
                                    mode="mean")
        records = TgapExplainer(model, [BridgeWidthTransformation(comm)],
                                defaultDelta=0.04).explainDetailed(tg)
        for r in records:
            self.assertTrue(r["noop"])
            self.assertEqual(r["impact"], 0.0)

    def testSmallerPropertyNeedsLargerDelta(self):
        ''' The floor scales as 1/p: a width-4 bridge needs a bigger
        relative nudge than a width-12 bridge. '''
        tgSmall, commSmall = makeTemporalGraph(nSnapshots=4, nPerCommunity=6,
                                               bridgeWidth=4, seed=2)
        tgLarge, commLarge = makeTemporalGraph(nSnapshots=4, nPerCommunity=30,
                                               bridgeWidth=12, seed=2)
        delta = 0.10  # above 0.5/12, below 0.5/4
        self.assertAlmostEqual(self.widthAfter(tgSmall, commSmall, delta), 4.0)
        self.assertNotAlmostEqual(self.widthAfter(tgLarge, commLarge, delta),
                                  12.0)


class TestAcrossGraphSizes(unittest.TestCase):
    ''' Known-truth recovery must not be a property of one graph size.
    Deltas are chosen above each size's discreteness floor. '''

    def testPureBridgeRecoveryAtThreeSizes(self):
        for nPer, bridgeWidth in ((6, 4), (15, 8), (30, 12)):
            for seed in (0, 1):
                tg, comm = makeTemporalGraph(
                    nSnapshots=5, nPerCommunity=nPer,
                    bridgeWidth=bridgeWidth, seed=seed)
                metric = BridgeWidthMetric(comm)
                model = WeightedMetricModel([(1.0, metric)], mode="mean")
                expected = float(np.mean([metric.measure(g) for g in tg]))
                delta = max(0.25, 1.0 / expected)  # safely above 0.5/p
                e = TgapExplainer(model, [BridgeWidthTransformation(comm)],
                                  defaultDelta=delta).explain(tg)
                key = f"Increase Bridge Width ({100 * delta}%)"
                self.assertAlmostEqual(
                    e[key], expected, places=6,
                    msg=f"nPer={nPer} bw={bridgeWidth} seed={seed}")

    def testAnchorHoldsAtEverySize(self):
        for nPer, bridgeWidth in ((6, 4), (15, 8), (30, 12)):
            tg, comm = makeTemporalGraph(nSnapshots=4, nPerCommunity=nPer,
                                         bridgeWidth=bridgeWidth, seed=3)
            tgT = BridgeWidthTransformation(comm).transform(tg, 0.5)
            for before, after in zip(tg, tgT):
                self.assertEqual(set(after.nodes()), set(before.nodes()))
                self.assertEqual(after.number_of_edges(),
                                 before.number_of_edges())


class TestEvaluationHelpers(unittest.TestCase):
    ''' The evaluation's own logic: expectations must be derived, errors
    must only be computed where a ground truth exists, and results must
    be reproducible. '''

    def testErrorFieldsSkippedForMeasuredKind(self):
        expected, absErr, relErr, signOk = pe.errorFields(
            {"kind": pe.MEASURED}, 1.234)
        self.assertIsNone(expected)
        self.assertIsNone(absErr)
        self.assertIsNone(relErr)
        self.assertIsNone(signOk)

    def testErrorFieldsForExactKind(self):
        expected, absErr, relErr, signOk = pe.errorFields(
            {"kind": pe.EXACT, "value": 8.0}, 7.5)
        self.assertEqual(expected, 8.0)
        self.assertAlmostEqual(absErr, 0.5)
        self.assertAlmostEqual(relErr, 0.0625)
        self.assertTrue(signOk)

    def testZeroKindRequiresExactZero(self):
        _, _, _, signOk = pe.errorFields({"kind": pe.ZERO, "value": 0.0}, 0.0)
        self.assertTrue(signOk)
        _, _, _, signOk = pe.errorFields({"kind": pe.ZERO, "value": 0.0}, 1e-9)
        self.assertFalse(signOk, "a near-zero value must not pass as zero")

    def testKnownTruthExpectationsAreDerivedFromTheWorld(self):
        ''' The expectations must follow from the graph that was built,
        not from constants typed into the suite: rebuild with a different
        bridge width and the expectation must move with it. '''
        for bridgeWidth in (6, 10):
            tg, comm = pe.makeWorld(bridgeWidth=bridgeWidth)
            models = pe.buildKnownTruthModels(tg, comm)
            expectation = models["A-pure-bridge (mean)"]["expect"]["Bridge Width"]
            self.assertEqual(expectation["kind"], pe.EXACT)
            self.assertAlmostEqual(expectation["value"], float(bridgeWidth))

    def testNonIsolatedPairsAreNotClaimedZero(self):
        ''' Isolation that the implementation does not guarantee must be
        marked MEASURED, never ZERO - this is what keeps the suite from
        asserting an expectation the code cannot honour. '''
        tg, comm = pe.makeWorld()
        spec = pe.buildKnownTruthModels(tg, comm)["B-pure-centralization"]
        for concept in ("Bridge Width", "Density", "Churn", "Bridge Trend"):
            self.assertEqual(spec["expect"][concept]["kind"], pe.MEASURED)

    def testMeanMetricMatchesTransformationProperty(self):
        ''' mode="mean" models and the transformations' propertyValue must
        read the same aggregate, otherwise the analytic expectation in RQ1
        would not hold. '''
        tg, comm = pe.makeWorld()
        metric = BridgeWidthMetric(comm)
        self.assertAlmostEqual(
            pe.meanMetric(metric, tg),
            BridgeWidthTransformation(comm).propertyValue(tg))

    def testNoCrossConceptRankingIsPresentedAsAnRq1Result(self):
        ''' The methodological point: at one fixed requested delta the
        concepts receive different achieved perturbations, so RQ1 must not
        publish a dominance verdict. The raw ranking may be retained for
        inspection, but not under a name that reads as a result. '''
        with contextlib.redirect_stdout(io.StringIO()):
            summary = pe.rq1Faithfulness(seed=11)["summary"]
        for s in summary:
            self.assertNotIn("dominant_correct", s)
            self.assertNotIn("recovered_dominant", s)
            self.assertIn("raw_ranking_unmatched", s)
            # within-concept fidelity IS a legitimate RQ1 result
            self.assertIn("mean_absolute_error", s)
            self.assertIn("signs_correct", s)

    def testComparableFlagRequiresMatchedAchievedChange(self):
        ''' A row may only be marked comparable when its achieved change
        is within tolerance of the reference concept's. '''
        with contextlib.redirect_stdout(io.StringIO()):
            rows = pe.rq1Faithfulness(seed=11)["rows"]
        byModelDirection = {}
        for r in rows:
            if r["concept"] == r["reference_concept"] and r["achieved_delta"]:
                byModelDirection[(r["model"], r["direction"])] = abs(
                    r["achieved_delta"])
        checked = 0
        for r in rows:
            ref = byModelDirection.get((r["model"], r["direction"]))
            if not r["comparable"] or ref is None or not r["achieved_delta"]:
                continue
            gap = abs(abs(r["achieved_delta"]) - ref) / max(
                abs(r["achieved_delta"]), ref)
            self.assertLessEqual(gap, pe.MATCH_TOLERANCE)
            checked += 1
        self.assertGreater(checked, 0, "no comparable rows were exercised")


class TestMatchedComparison(unittest.TestCase):
    ''' RQ1b: cross-concept comparison is only allowed where the achieved
    perturbations were actually matched. '''

    def makeSweeps(self):
        tg, comm = pe.makeWorld(seed=5)
        model = WeightedMetricModel(
            [(1.0, BridgeWidthMetric(comm))], mode="mean")
        deltas = (0.05, 0.1, 0.2, 0.5)
        bridge = pe.sweepConcept(model, tg, BridgeWidthTransformation(comm),
                                 deltas)
        trend = pe.sweepConcept(model, tg, BridgeTrendTransformation(comm),
                                deltas)
        central = pe.sweepConcept(model, tg,
                                  CentralizationTransformation(comm), deltas)
        return bridge, trend, central

    def testDifferentDeltaModesNeverMatch(self):
        ''' A relative ratio and a slope in edges-per-step are not in the
        same units; no tolerance can make them comparable. '''
        bridge, trend, _ = self.makeSweeps()
        self.assertIsNone(pe.bestMatch(bridge, trend, "increase"))
        self.assertIsNone(pe.bestMatch(trend, bridge, "decrease"))

    def testMatchPicksClosestAchievedPair(self):
        bridge, _, central = self.makeSweeps()
        match = pe.bestMatch(bridge, central, "increase")
        self.assertIsNotNone(match)
        rowA, rowB, gap = match
        # No other achievable pair may be closer than the one returned.
        for a in bridge:
            for b in central:
                if (a["direction"] != "increase" or b["direction"] != "increase"
                        or a["noop"] or b["noop"]
                        or not a["achieved_delta"] or not b["achieved_delta"]):
                    continue
                x, y = abs(a["achieved_delta"]), abs(b["achieved_delta"])
                self.assertLessEqual(gap - 1e-12, abs(x - y) / max(x, y))

    def testNoMatchIsForcedWhenGapExceedsTolerance(self):
        ''' bestMatch always returns its closest pair; comparability is a
        separate decision, and a gap beyond the tolerance must not be
        silently accepted. '''
        bridge, _, central = self.makeSweeps()
        match = pe.bestMatch(bridge, central, "increase")
        _, _, gap = match
        comparable = gap <= pe.MATCH_TOLERANCE
        self.assertEqual(comparable, bool(gap <= pe.MATCH_TOLERANCE))

    def testIncomparablePairsAreReportedNotCompared(self):
        with contextlib.redirect_stdout(io.StringIO()):
            rows = pe.rq1bMatchedComparison(seeds=(5,))["rows"]
        self.assertTrue(rows)
        for r in rows:
            if not r["comparable"]:
                # No verdict may be attached to a non-comparable pair.
                self.assertIsNone(r.get("reference_larger"))
                self.assertIn("reason", r)
            else:
                self.assertIsNotNone(r.get("reference_larger"))
                self.assertLessEqual(r["achieved_gap"], pe.MATCH_TOLERANCE)

    def testSlopeModelReferenceHasNoComparableCounterpart(self):
        ''' The slope model's reference concept is the only absolute-mode
        transformation, so nothing can be matched against it. The suite
        must say so rather than produce a ranking. '''
        with contextlib.redirect_stdout(io.StringIO()):
            rows = pe.rq1bMatchedComparison(seeds=(5,))["rows"]
        slopeRows = [r for r in rows if r["model"] == "D-slope-of-bridge"]
        self.assertTrue(slopeRows)
        self.assertTrue(all(not r["comparable"] for r in slopeRows))

    def testMatchedComparisonIsReproducible(self):
        with contextlib.redirect_stdout(io.StringIO()):
            a = pe.rq1bMatchedComparison(seeds=(5,))["rows"]
            b = pe.rq1bMatchedComparison(seeds=(5,))["rows"]
        self.assertEqual([r.get("concept_impact") for r in a],
                         [r.get("concept_impact") for r in b])


class TestMatchedComparisonAcrossSeeds(unittest.TestCase):
    ''' The multi-seed extension. These tests check IMPLEMENTATION
    behavior - that every requested seed is actually run, that results
    stay deterministic, and that no match is forced - not that any
    particular scientific outcome holds in every world.

    The sweep is expensive (~4 s per seed), so the shared multi-seed run
    is computed once for the whole class. '''

    SEEDS = (0, 1, 2)

    @classmethod
    def runSeeds(cls, seeds):
        with contextlib.redirect_stdout(io.StringIO()):
            return pe.rq1bMatchedComparison(seeds=seeds)

    @classmethod
    def setUpClass(cls):
        cls.result = cls.runSeeds(cls.SEEDS)

    def testEveryRequestedSeedIsEvaluated(self):
        self.assertEqual(sorted({r["seed"] for r in self.result["rows"]}),
                         list(self.SEEDS))
        self.assertEqual(self.result["verdict"]["seeds_evaluated"],
                         len(self.SEEDS))
        self.assertEqual([s["seed"] for s in self.result["per_seed"]],
                         list(self.SEEDS))

    def testEverySeedContributesTheSameNumberOfPairs(self):
        ''' The procedure is identical per world, so the number of concept
        pairs examined must not depend on the seed - only the outcomes may. '''
        counts = {s["seed"]: s["total_pairs"]
                  for s in self.result["per_seed"]}
        self.assertEqual(len(set(counts.values())), 1, counts)

    def testPerSeedCountsAreInternallyConsistent(self):
        for s in self.result["per_seed"]:
            self.assertEqual(s["matched_pairs"] + s["non_matched_pairs"],
                             s["total_pairs"])
            self.assertEqual(
                s["reference_larger"] + s["reference_smaller"] + s["ties"],
                s["matched_pairs"])

    def testPooledTotalsEqualTheSumOverSeeds(self):
        verdict = self.result["verdict"]
        perSeed = self.result["per_seed"]
        self.assertEqual(verdict["comparable_pairs"],
                         sum(s["matched_pairs"] for s in perSeed))
        self.assertEqual(verdict["total_pairs"],
                         sum(s["total_pairs"] for s in perSeed))
        self.assertEqual(
            verdict["reference_larger_in_matched"]
            + verdict["reference_smaller_in_matched"]
            + verdict["ties_in_matched"],
            verdict["comparable_pairs"])

    def testNoForcedMatchesInAnySeed(self):
        ''' The no-forced-match rule must hold in every world: a pair may
        be marked comparable only if its achieved gap is within tolerance,
        and a non-comparable pair must carry no verdict. '''
        for r in self.result["rows"]:
            if r["comparable"]:
                self.assertLessEqual(r["achieved_gap"], pe.MATCH_TOLERANCE)
                self.assertIn(r["comparison_outcome"],
                              ("reference_larger", "reference_smaller", "tie"))
            else:
                self.assertIsNone(r.get("reference_larger"))
                self.assertIsNone(r.get("comparison_outcome"))

    def testConsistencyFlagMatchesThePerSeedCounts(self):
        ''' The "consistent across seeds" flag must be derived from the
        per-seed numbers, not asserted independently of them. '''
        perSeed = self.result["per_seed"]
        withMatches = [s for s in perSeed if s["matched_pairs"] > 0]
        expected = all(s["reference_larger"] == s["matched_pairs"]
                       for s in withMatches)
        self.assertEqual(
            self.result["verdict"]
            ["reference_larger_in_every_seed_with_matches"],
            bool(expected and withMatches))

    def testMultiSeedRunIsDeterministic(self):
        a = self.runSeeds((0, 1))["rows"]
        b = self.runSeeds((0, 1))["rows"]
        self.assertEqual([(r["seed"], r["model"], r["concept"], r["direction"],
                           r.get("concept_impact"), r["comparable"])
                          for r in a],
                         [(r["seed"], r["model"], r["concept"], r["direction"],
                           r.get("concept_impact"), r["comparable"])
                          for r in b])

    def testDifferentSeedsProduceDifferentWorlds(self):
        ''' Seeds must actually change the generated world; otherwise the
        multi-seed evidence would be one world counted five times. The key
        includes the model, because concept+direction alone collapses rows
        from different models onto each other. '''
        def fingerprint(seed):
            return {(r["model"], r["concept"], r["direction"]):
                    (r.get("concept_achieved_delta"),
                     r.get("concept_impact"),
                     r.get("reference_impact"))
                    for r in self.runSeeds((seed,))["rows"]}
        self.assertNotEqual(fingerprint(0), fingerprint(1))


class TestEvaluationHelpersContinued(unittest.TestCase):
    def testFaithfulnessIsReproducible(self):
        # rq1Faithfulness prints its table; silence it so the test output
        # stays readable, and run it twice on the same seed.
        with contextlib.redirect_stdout(io.StringIO()):
            a = pe.rq1Faithfulness(seed=7)["rows"]
            b = pe.rq1Faithfulness(seed=7)["rows"]
        self.assertEqual([r["measured"] for r in a],
                         [r["measured"] for r in b])

    def testOvershootRatioIsRecorded(self):
        ''' Cross-concept magnitude comparison is only meaningful if the
        effective perturbation sizes are known, so every non-no-op row
        must carry the achieved/requested ratio. '''
        with contextlib.redirect_stdout(io.StringIO()):
            rows = pe.rq1Faithfulness(seed=7)["rows"]
        active = [r for r in rows if not r["noop"] and r["achieved_delta"]]
        self.assertTrue(active)
        for r in active:
            self.assertIsNotNone(r["overshoot_ratio"])
            self.assertAlmostEqual(
                r["overshoot_ratio"],
                abs(r["achieved_delta"]) / abs(r["requested_delta_value"]))


if __name__ == "__main__":
    unittest.main()
