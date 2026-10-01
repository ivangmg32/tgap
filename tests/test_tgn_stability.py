'''
Tests for TGN seed stability and matched concept comparison.

Two scientific rules are enforced here:

  * seeds must not be pooled and the split must be identical across them,
    otherwise "stability" would be measuring the split rather than the
    model;
  * concepts with incompatible perturbation units must NEVER be compared,
    and a match must never be forced. "not comparable" is a legitimate
    result and the tests require it to appear.
'''

import json
import os
import unittest

import pandas as pd

from core.TgnModel import TORCH_AVAILABLE
from realdata.run_tgn_stability import SEEDS, comparabilityOf

RESULTS = os.path.join("output", "real_data_v2", "tgn_stability",
                       "email_eu_core")


class TestComparabilityRule(unittest.TestCase):
    ''' The rule is a property of the transformations, not a hard-coded
    list of names - so it keeps working when someone adds a concept. '''

    def setUp(self):
        from core import (BridgeTrendTransformation, BridgeWidthTransformation,
                          CentralizationTransformation, ChurnTransformation,
                          DensityTransformation)
        communities = ({0, 1, 2}, {3, 4, 5})
        self.bridgeWidth = BridgeWidthTransformation(communities, seed=42)
        self.density = DensityTransformation(communities, seed=42)
        self.churn = ChurnTransformation(communities, seed=42)
        self.centralization = CentralizationTransformation(communities,
                                                           seed=42)
        self.bridgeTrend = BridgeTrendTransformation(communities, seed=42)

    def testRelativeConceptsAreComparableInPrinciple(self):
        for first, second in ((self.bridgeWidth, self.density),
                              (self.bridgeWidth, self.churn),
                              (self.density, self.churn)):
            comparable, reason = comparabilityOf(first, second)
            self.assertTrue(comparable, f"{first.name}/{second.name}: {reason}")

    def testAbsoluteDeltaModeBlocksComparison(self):
        ''' Bridge Trend's achieved change is a slope, not a ratio. '''
        comparable, reason = comparabilityOf(self.bridgeWidth,
                                             self.bridgeTrend)
        self.assertFalse(comparable)
        self.assertIn("delta units", reason)

    def testCentralizationIsNeverComparable(self):
        ''' Its delta is a rewiring fraction, not a relative change of the
        measured property. '''
        for other in (self.bridgeWidth, self.density, self.churn):
            comparable, reason = comparabilityOf(self.centralization, other)
            self.assertFalse(comparable)
            self.assertIn("rewiring fraction", reason)

    def testRuleIsSymmetric(self):
        for first, second in ((self.bridgeWidth, self.bridgeTrend),
                              (self.centralization, self.density)):
            self.assertEqual(comparabilityOf(first, second)[0],
                             comparabilityOf(second, first)[0])

    def testRuleReadsTransformationPropertiesNotNames(self):
        ''' A new user transformation with relative deltaMode must be
        comparable without anyone editing a list. '''
        from core import TemporalGraphTransformation

        class MyConcept(TemporalGraphTransformation):
            name = "My Concept"
            deltaMode = "relative"

            def propertyValue(self, x):
                return 1.0

            def transformGraph(self, graph, delta):
                return graph.copy()

        comparable, _ = comparabilityOf(MyConcept(), self.bridgeWidth)
        self.assertTrue(comparable)


@unittest.skipUnless(
    os.path.exists(os.path.join(RESULTS, "summary.json")),
    "stability results not generated; run realdata.run_tgn_stability")
class TestSeedStabilityOutputs(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(RESULTS, "summary.json"),
                  encoding="utf-8") as handle:
            cls.summary = json.load(handle)
        cls.stability = pd.read_csv(os.path.join(RESULTS,
                                                 "seed_stability.csv"))
        cls.matched = pd.read_csv(os.path.join(RESULTS,
                                               "matched_comparison.csv"))
        cls.perSeed = pd.read_csv(os.path.join(RESULTS,
                                               "per_seed_explanations.csv"))

    def testFiveFixedSeedsWereUsed(self):
        self.assertEqual(self.summary["seeds"], list(SEEDS))
        self.assertEqual(len(self.summary["per_seed"]), len(SEEDS))

    def testEverySeedIsRecordedInEveryRow(self):
        ''' Rule D of the consistency check: every scientific TGN output
        records its seed. '''
        self.assertIn("seed", self.perSeed.columns)
        self.assertEqual(set(self.perSeed["seed"]), set(SEEDS))
        self.assertIn("seed", self.matched.columns)

    def testSplitIsIdenticalAcrossSeeds(self):
        ''' If the split moved between seeds, the spread would be measuring
        the split rather than the model. '''
        self.assertTrue(self.summary["split_identical_across_seeds"])
        splits = {(s["train_snapshots"], s["heldout_snapshots"])
                  for s in self.summary["per_seed"]}
        self.assertEqual(len(splits), 1)

    def testPerSeedValuesAreReportedNotOnlySummarised(self):
        ''' Collapsing five runs into a mean would hide an outlier. '''
        for _, row in self.stability.iterrows():
            self.assertTrue(row["per_seed"])
            self.assertEqual(len(eval(row["per_seed"])), len(SEEDS))

    def testSummaryStatisticsAreConsistent(self):
        for _, row in self.stability.iterrows():
            values = [v for v in eval(row["per_seed"]) if v is not None]
            if not values:
                continue
            self.assertLessEqual(row["min"], row["mean"] + 1e-9)
            self.assertGreaterEqual(row["max"], row["mean"] - 1e-9)
            self.assertAlmostEqual(row["min"], min(values), places=5)
            self.assertAlmostEqual(row["max"], max(values), places=5)

    def testNoPoolingOrSignificanceClaimed(self):
        self.assertIn("not independent samples",
                      self.summary["pooling_note"])

    def testNoRankingIsProduced(self):
        self.assertIn("No ranking", self.summary["no_ranking_note"])


@unittest.skipUnless(
    os.path.exists(os.path.join(RESULTS, "matched_comparison.csv")),
    "matched comparison not generated")
class TestMatchedComparisonOutputs(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.matched = pd.read_csv(os.path.join(RESULTS,
                                               "matched_comparison.csv"))

    def testSchemaHasEveryRequiredField(self):
        for column in ("seed", "concept_a", "concept_b", "direction",
                       "requested_delta_a", "requested_delta_b",
                       "achieved_delta_a", "achieved_delta_b",
                       "impact_a", "impact_b", "comparable", "reason"):
            self.assertIn(column, self.matched.columns)

    def testNotComparableIsALegitimateRecordedState(self):
        incomparable = self.matched[~self.matched["comparable"]]
        self.assertGreater(len(incomparable), 0)
        self.assertTrue(incomparable["reason"].notna().all())

    def testIncomparablePairsCarryNoNumbers(self):
        ''' A forced numerical comparison is exactly what this must
        prevent. '''
        incomparable = self.matched[~self.matched["comparable"]]
        for column in ("achieved_delta_a", "achieved_delta_b",
                       "impact_a", "impact_b"):
            self.assertTrue(incomparable[column].isna().all(),
                            f"{column} present on an incomparable pair")

    def testComparablePairsCarryBothSidesAndAMatchedDelta(self):
        comparable = self.matched[self.matched["comparable"]]
        if comparable.empty:
            self.skipTest("no comparable pairs in this run")
        for column in ("achieved_delta_a", "achieved_delta_b",
                       "impact_a", "impact_b"):
            self.assertTrue(comparable[column].notna().all())

    def testCentralizationAndBridgeTrendAreNeverCompared(self):
        for concept in ("Centralization", "Bridge Trend"):
            rows = self.matched[
                (self.matched["concept_a"] == concept)
                | (self.matched["concept_b"] == concept)]
            self.assertFalse(rows["comparable"].any(),
                             f"{concept} was compared despite incompatible "
                             f"perturbation units")

    def testNoWinnerColumnExists(self):
        ''' The output must not encode an ordering. '''
        for forbidden in ("winner", "rank", "best", "larger", "dominant"):
            self.assertNotIn(forbidden, [c.lower() for c in
                                         self.matched.columns])


if __name__ == "__main__":
    unittest.main()
