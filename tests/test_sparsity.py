'''
Tests for the sparsity metric.

The scientific risk with a sparsity metric is that it is trivially easy to
produce a plausible number from an indefensible definition. These tests
therefore pin the DEFINITION, not just the arithmetic:

  * exact zeros are what make the primary definition threshold-free, so a
    test asserts TGAP really does produce exact zeros;
  * no-op rows are excluded from the denominator, because a perturbation
    that never happened is not evidence that the model ignores the concept;
  * invalid rows are excluded, so a failed experiment cannot move the
    metric;
  * concept-level and element-level sparsity are never combined.
'''

import unittest

from core import (
    BridgeWidthMetric, BridgeWidthTransformation, CentralizationTransformation,
    ChurnTransformation, DensityTransformation, PersistenceTemporalModel,
    TgapExplainer, TrendTemporalModel, edgeAttribution, makeTemporalGraph,
)
from core.GraphMetric import DensityMetric
from core.Sparsity import (
    conceptSparsity, elementSparsity, sparsityReport,
)


class TestConceptSparsityDefinition(unittest.TestCase):
    ''' The definition itself, on hand-made records where the answer is
    obvious by inspection. '''

    def testAllZeroMeansFullySparse(self):
        records = [{"impact": 0.0} for _ in range(4)]
        result = conceptSparsity(records)
        self.assertEqual(result["sparsity"], 1.0)
        self.assertEqual(result["numerator_inactive"], 4)
        self.assertEqual(result["denominator_total"], 4)
        self.assertEqual(result["active"], 0)

    def testNoZerosMeansFullyDense(self):
        records = [{"impact": v} for v in (1.0, -2.0, 0.5, 9.9)]
        result = conceptSparsity(records)
        self.assertEqual(result["sparsity"], 0.0)
        self.assertEqual(result["density"], 1.0)

    def testMixedCountsCorrectly(self):
        records = [{"impact": v} for v in (8.0, 0.0, 0.0, -3.0)]
        result = conceptSparsity(records)
        self.assertEqual(result["numerator_inactive"], 2)
        self.assertEqual(result["denominator_total"], 4)
        self.assertEqual(result["sparsity"], 0.5)

    def testDefaultIsThresholdFree(self):
        ''' The claim that makes this definition defensible. A tiny but
        non-zero impact must count as ACTIVE by default - it is a real
        response, however small. '''
        result = conceptSparsity([{"impact": 1e-12}, {"impact": 0.0}])
        self.assertTrue(result["threshold_free"])
        self.assertIsNone(result["threshold"])
        self.assertEqual(result["active"], 1)
        self.assertEqual(result["sparsity"], 0.5)

    def testThresholdIsHonouredAndRecorded(self):
        ''' A threshold is allowed for noisy models, but it must appear in
        the output so nobody has to guess what produced the number. '''
        result = conceptSparsity([{"impact": 1e-12}, {"impact": 0.0}],
                                 threshold=1e-9)
        self.assertFalse(result["threshold_free"])
        self.assertEqual(result["threshold"], 1e-9)
        self.assertEqual(result["sparsity"], 1.0)

    def testNoopRowsLeaveTheDenominator(self):
        ''' A no-op means the perturbation never changed the property, so
        the model was never probed. Counting it as "does not respond" would
        invent evidence. '''
        records = [{"impact": 8.0, "noop": False},
                   {"impact": 0.0, "noop": True},
                   {"impact": 0.0, "noop": True}]
        result = conceptSparsity(records)
        self.assertEqual(result["denominator_total"], 1)
        self.assertEqual(result["noop_excluded"], 2)
        self.assertEqual(result["sparsity"], 0.0)

    def testInvalidRowsAreExcluded(self):
        records = [{"impact": 8.0, "valid_for_analysis": True},
                   {"impact": 0.0, "valid_for_analysis": False}]
        result = conceptSparsity(records)
        self.assertEqual(result["denominator_total"], 1)
        self.assertEqual(result["invalid_excluded"], 1)

    def testUndefinedRatherThanOneWhenNothingWasProbed(self):
        ''' If every row was a no-op, sparsity is UNDEFINED. Returning 1.0
        would assert the model ignores every concept, which the experiment
        never tested. '''
        result = conceptSparsity([{"impact": 0.0, "noop": True}])
        self.assertIsNone(result["sparsity"])
        self.assertIn("undefined", result["undefined_reason"])

    def testEmptyInput(self):
        result = conceptSparsity([])
        self.assertIsNone(result["sparsity"])
        self.assertEqual(result["denominator_total"], 0)


class TestConceptSparsityOnRealExplanations(unittest.TestCase):
    ''' The metric applied to explanations TGAP actually produces. '''

    @classmethod
    def setUpClass(cls):
        cls.snapshots, cls.communities = makeTemporalGraph(
            nSnapshots=6, nPerCommunity=10, bridgeWidth=8, seed=1)
        cls.transformations = [
            BridgeWidthTransformation(cls.communities, seed=42),
            CentralizationTransformation(cls.communities, seed=42),
            DensityTransformation(cls.communities, seed=42),
            ChurnTransformation(cls.communities, seed=42)]

    def testTgapProducesExactZeros(self):
        ''' The premise of the threshold-free definition. If this ever
        fails, the default definition must be revisited rather than quietly
        given a threshold. '''
        model = PersistenceTemporalModel(BridgeWidthMetric(self.communities))
        records = TgapExplainer(model, self.transformations).explainDetailed(
            self.snapshots)
        zeros = [r["impact"] for r in records if r["impact"] == 0.0]
        self.assertGreater(len(zeros), 0, "no exact zeros to rely on")
        for value in zeros:
            self.assertEqual(value, 0.0)        # exactly, not approximately

    def testSelectiveModelGivesHighSparsity(self):
        ''' A model reading one concept should produce a sparse
        explanation. '''
        model = PersistenceTemporalModel(BridgeWidthMetric(self.communities))
        records = TgapExplainer(model, self.transformations).explainDetailed(
            self.snapshots)
        result = conceptSparsity(records)
        self.assertGreater(result["sparsity"], 0.5)
        self.assertEqual(result["active"], 2)   # increase + decrease of one

    def testSparsityIsDeterministic(self):
        model = TrendTemporalModel(DensityMetric())
        explainer = TgapExplainer(model, self.transformations)
        first = conceptSparsity(explainer.explainDetailed(self.snapshots))
        second = conceptSparsity(explainer.explainDetailed(self.snapshots))
        self.assertEqual(first["sparsity"], second["sparsity"])


class TestElementSparsity(unittest.TestCase):

    def setUp(self):
        self.snapshots, self.communities = makeTemporalGraph(
            nSnapshots=4, nPerCommunity=6, bridgeWidth=5, seed=2)
        self.model = PersistenceTemporalModel(
            BridgeWidthMetric(self.communities))

    def testAcceptsAnAttributionDict(self):
        attribution = edgeAttribution(self.snapshots, self.model, topK=8)
        result = elementSparsity(attribution)
        self.assertEqual(result["level"], "element")
        self.assertEqual(result["denominator_total"],
                         attribution["edges_evaluated"])

    def testPartialCoverageIsFlagged(self):
        ''' A sparsity figure over 8 of 200 edges says much less than the
        same figure over all 200, so the truncation must travel with it. '''
        attribution = edgeAttribution(self.snapshots, self.model, topK=8)
        result = elementSparsity(attribution)
        self.assertTrue(result["partial"])
        self.assertIn("truncated", result["partial_note"])
        self.assertLess(result["coverage"], 1.0)

    def testFullCoverageIsNotFlagged(self):
        attribution = edgeAttribution(self.snapshots, self.model)
        result = elementSparsity(attribution)
        self.assertFalse(result["partial"])
        self.assertEqual(result["coverage"], 1.0)


class TestSparsityReport(unittest.TestCase):

    def testBothLevelsReturnedSeparately(self):
        snapshots, communities = makeTemporalGraph(
            nSnapshots=4, nPerCommunity=6, bridgeWidth=5, seed=3)
        model = PersistenceTemporalModel(BridgeWidthMetric(communities))
        records = TgapExplainer(model, [
            BridgeWidthTransformation(communities, seed=42),
            DensityTransformation(communities, seed=42)]).explainDetailed(
            snapshots)
        attribution = edgeAttribution(snapshots, model, topK=5)
        report = sparsityReport(records, attribution)
        self.assertIn("concept", report)
        self.assertIn("element", report)
        # The two must never be merged into one figure.
        self.assertNotIn("sparsity", report)
        self.assertIn("must not", report["note"])

    def testElementLevelOmittedWhenNoAttributionGiven(self):
        report = sparsityReport([{"impact": 1.0}])
        self.assertIn("concept", report)
        self.assertNotIn("element", report)


if __name__ == "__main__":
    unittest.main()
