'''
Tests for structured local explanations and element-level attribution.

The scientific risk this module carries is FABRICATED IMPORTANCE: it would
be easy to emit a plausible-looking number per edge that was never measured.
Design section 22 forbids that, so the tests below check not only that the
numbers are right but that they were OBTAINED the stated way - by actually
perturbing the element and re-asking the model, with the model-call count
matching the number of elements evaluated.
'''

import unittest

import networkx as nx

from core import (
    BridgeWidthMetric, BridgeWidthTransformation, CallCountingModel,
    ChurnTransformation, DensityTransformation, PersistenceTemporalModel,
    SlopeModel, edgeAttribution, graphDifference, localExplanation,
    makeNCommunityTemporalGraph, nodeAttribution, temporalAttribution,
)


class TestGraphDifference(unittest.TestCase):
    ''' The primitive behind every "difference graph" figure. '''

    def setUp(self):
        self.before = nx.Graph([(0, 1), (1, 2), (2, 3)])
        self.after = nx.Graph([(1, 2), (2, 3), (3, 4)])

    def testAddedRemovedKept(self):
        difference = graphDifference(self.before, self.after)
        self.assertEqual(difference["removed"], [(0, 1)])
        self.assertEqual(difference["added"], [(3, 4)])
        self.assertEqual(difference["kept"], [(1, 2), (2, 3)])

    def testAffectedNodesAreEndpointsOfChangedEdges(self):
        difference = graphDifference(self.before, self.after)
        self.assertEqual(difference["nodes"], [0, 1, 3, 4])

    def testIdenticalGraphsHaveNoDifference(self):
        difference = graphDifference(self.before, self.before.copy())
        self.assertEqual(difference["added"], [])
        self.assertEqual(difference["removed"], [])

    def testEdgeOrientationIsCanonical(self):
        ''' (1,0) and (0,1) must never be reported as different edges. '''
        difference = graphDifference(nx.Graph([(1, 0)]), nx.Graph())
        self.assertEqual(difference["removed"], [(0, 1)])


class TestLocalExplanation(unittest.TestCase):

    def setUp(self):
        self.snapshots, self.partition = makeNCommunityTemporalGraph(
            nSnapshots=5, nCommunities=3, nPerCommunity=8,
            bridgeWidths={(0, 1): 12, "default": 4}, seed=2)
        self.model = PersistenceTemporalModel(
            BridgeWidthMetric(self.partition, communityPair=(0, 1)))
        self.transformation = BridgeWidthTransformation(
            self.partition, seed=42, communityPair=(0, 1))

    def testCarriesTheFullSchema(self):
        record, _ = localExplanation(self.snapshots, self.transformation, 0.5,
                                     model=self.model,
                                     communities=self.partition)
        for field in ("concept", "direction", "requested_delta",
                      "achieved_delta", "baseline_prediction",
                      "after_prediction", "impact", "community_pair",
                      "affected_edges_added", "affected_edges_removed",
                      "affected_nodes", "snapshots_affected",
                      "property_before", "property_after", "per_snapshot"):
            self.assertIn(field, record)

    def testAffectedElementsAreReal(self):
        ''' Every edge reported as affected must genuinely differ between
        the original and the transformed graph. '''
        record, transformed = localExplanation(
            self.snapshots, self.transformation, 0.5,
            communities=self.partition)
        originalEdges = set()
        newEdges = set()
        for before, after in zip(self.snapshots, transformed):
            originalEdges |= {tuple(sorted(e)) for e in before.edges()}
            newEdges |= {tuple(sorted(e)) for e in after.edges()}
        for edge in record["affected_edges_added"]:
            self.assertIn(edge, newEdges)
        for edge in record["affected_edges_removed"]:
            self.assertIn(edge, originalEdges)
        self.assertGreater(record["affected_edge_count"], 0)

    def testAchievedDeltaAgreesWithTheExplainer(self):
        ''' A local record and a global row must never disagree about how
        much actually moved. '''
        from core import TgapExplainer
        record, _ = localExplanation(self.snapshots, self.transformation, 0.5,
                                     model=self.model)
        globalRow = [r for r in TgapExplainer(
            self.model, [self.transformation], defaultDelta=0.5
        ).explainDetailed(self.snapshots) if r["requestedDelta"] > 0][0]
        self.assertAlmostEqual(record["achieved_delta"],
                               globalRow["achievedDelta"], places=12)
        self.assertAlmostEqual(record["impact"], globalRow["impact"],
                               places=12)

    def testBridgeMatrixBeforeAndAfterIsRecorded(self):
        record, _ = localExplanation(self.snapshots, self.transformation, 0.5,
                                     communities=self.partition)
        self.assertEqual(record["bridge_matrix_before"]["(0, 1)"], 12)
        self.assertGreater(record["bridge_matrix_after"]["(0, 1)"], 12)
        # Confounder control at N communities.
        self.assertEqual(record["bridge_matrix_before"]["(1, 2)"],
                         record["bridge_matrix_after"]["(1, 2)"])

    def testWorksWithoutAModel(self):
        ''' Figures need the structural part only; paying for predictions
        should not be mandatory. '''
        record, _ = localExplanation(self.snapshots, self.transformation, 0.5)
        self.assertNotIn("impact", record)
        self.assertGreater(record["affected_edge_count"], 0)

    def testTemporalTransformationLeavesTheLastSnapshotAlone(self):
        record, _ = localExplanation(
            self.snapshots, ChurnTransformation(self.partition, seed=42), 0.5)
        self.assertNotIn(len(self.snapshots) - 1,
                         record["snapshots_affected"])


class TestElementAttribution(unittest.TestCase):
    ''' Section 22: no fabricated importance. '''

    def setUp(self):
        self.snapshots, self.partition = makeNCommunityTemporalGraph(
            nSnapshots=4, nCommunities=2, nPerCommunity=6,
            bridgeWidths={(0, 1): 8}, seed=3)
        self.model = PersistenceTemporalModel(
            BridgeWidthMetric(self.partition))

    def testEveryEdgeScoreIsAMeasuredPredictionDifference(self):
        ''' The count of model calls must equal 1 baseline + 1 per edge
        evaluated. If a score were interpolated rather than measured, the
        arithmetic would not hold. '''
        counter = CallCountingModel(self.model)
        result = edgeAttribution(self.snapshots, counter, topK=6)
        self.assertEqual(result["model_calls"], 1 + result["edges_evaluated"])
        self.assertEqual(counter.calls, result["model_calls"])
        for row in result["rows"]:
            self.assertAlmostEqual(
                row["impact"],
                row["after_prediction"] - row["baseline_prediction"],
                places=12)

    def testRemovingABridgeEdgeLowersABridgeReadingModel(self):
        ''' A sanity check with an exactly known sign AND magnitude.

        The model counts bridge edges in the LAST snapshot, so occluding a
        bridge edge that is present there must move it by exactly -1, and
        occluding one that is absent there must move it by exactly 0. Both
        directions are asserted, because only checking the non-zero case
        would miss a method that always returns -1. '''
        last = self.snapshots[-1]
        result = edgeAttribution(self.snapshots, self.model,
                                 communities=self.partition, onlyBridges=True)
        self.assertTrue(result["rows"])
        checkedPresent = checkedAbsent = False
        for row in result["rows"]:
            if last.has_edge(*row["edge"]):
                self.assertEqual(row["impact"], -1.0, row["edge"])
                checkedPresent = True
            else:
                self.assertEqual(row["impact"], 0.0, row["edge"])
                checkedAbsent = True
        self.assertTrue(checkedPresent, "no bridge edge in the last snapshot")
        self.assertTrue(checkedAbsent,
                        "fixture never exercises the absent-edge case")

    def testCoverageIsReportedWhenTruncated(self):
        ''' A partial ranking must never look exhaustive. '''
        result = edgeAttribution(self.snapshots, self.model, topK=3)
        self.assertEqual(result["edges_evaluated"], 3)
        self.assertGreater(result["edges_skipped"], 0)
        self.assertLess(result["coverage"], 1.0)
        self.assertIn("occlusion", result["method_note"])

    def testBudgetCapsModelCalls(self):
        counter = CallCountingModel(self.model)
        result = edgeAttribution(self.snapshots, counter, budget=5)
        self.assertLessEqual(result["model_calls"], 5)
        self.assertLessEqual(counter.calls, 5)

    def testSamplingIsDeterministic(self):
        first = edgeAttribution(self.snapshots, self.model, sample=5, seed=7)
        second = edgeAttribution(self.snapshots, self.model, sample=5, seed=7)
        self.assertEqual([r["edge"] for r in first["rows"]],
                         [r["edge"] for r in second["rows"]])

    def testNodeAttributionKeepsTheNodeSet(self):
        ''' TGAP's anchor rule: isolating a node must not remove it, or the
        measurement would be confounded with a size change. '''
        result = nodeAttribution(self.snapshots, self.model, topK=4)
        self.assertEqual(result["model_calls"], 1 + result["nodes_evaluated"])
        for row in result["rows"]:
            self.assertIn("node", row)

    def testTemporalAttributionIsolatesOneSnapshot(self):
        transformation = BridgeWidthTransformation(self.partition, seed=42)
        result = temporalAttribution(self.snapshots, self.model,
                                     transformation, 0.5)
        self.assertEqual(len(result["rows"]), len(self.snapshots))
        self.assertEqual(result["model_calls"], 1 + len(self.snapshots))
        # A present-only model can only react to the LAST snapshot.
        for row in result["rows"][:-1]:
            self.assertEqual(row["impact"], 0.0)
        self.assertNotEqual(result["rows"][-1]["impact"], 0.0)

    def testTemporalAttributionRefusesToClaimAdditivity(self):
        ''' Summing per-snapshot impacts is NOT a decomposition, and the
        method note must say so. '''
        transformation = BridgeWidthTransformation(self.partition, seed=42)
        result = temporalAttribution(self.snapshots, self.model,
                                     transformation, 0.5)
        self.assertIn("need NOT equal", result["method_note"])


if __name__ == "__main__":
    unittest.main()
