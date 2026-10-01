'''
Tests for attribution persistence, edge-time attribution, and the
BridgeTrend delta = -1 guard.

Three gaps are covered here:

  * attribution results used to exist only inside a plotting function, so a
    figure could not be regenerated from stored data and nobody could audit
    the rows behind it. These tests pin the persisted SCHEMA.

  * snapshot-concept attribution was previously the only temporal object,
    and it is NOT edge-time attribution. The two are now distinct and the
    tests assert they stay distinct.

  * BridgeTrend divided by (1 + delta) with no guard, so delta = -1 raised a
    bare ZeroDivisionError from deep inside a loop.
'''

import csv
import os
import tempfile
import unittest

from core import (
    BridgeTrendTransformation, BridgeWidthMetric, BridgeWidthTransformation,
    ELEMENT_ATTRIBUTION_COLUMNS, PersistenceTemporalModel,
    TEMPORAL_ATTRIBUTION_COLUMNS, TrendTemporalModel, edgeAttribution,
    edgeTimeAttribution, makeTemporalGraph, temporalAttribution,
    writeElementAttribution, writeTemporalAttribution,
)


def readCsv(path):
    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with open(path, encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    return header, rows


class AttributionFixture(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.snapshots, cls.communities = makeTemporalGraph(
            nSnapshots=5, nPerCommunity=6, bridgeWidth=5, seed=2)
        cls.persistence = PersistenceTemporalModel(
            BridgeWidthMetric(cls.communities))
        cls.trajectory = TrendTemporalModel(
            BridgeWidthMetric(cls.communities))
        cls.directory = tempfile.mkdtemp(prefix="tgap-attr-test-")


class TestElementAttributionPersistence(AttributionFixture):

    def testSchemaIsFixedAndOrdered(self):
        ''' A stable column order means a stale or reordered column cannot
        appear silently between runs. '''
        attribution = edgeAttribution(self.snapshots, self.persistence,
                                      topK=6)
        path = writeElementAttribution(
            attribution, os.path.join(self.directory, "edge.csv"),
            dataset="synthetic", model="persistence", seed=42)
        header, rows = readCsv(path)
        self.assertEqual(tuple(header), ELEMENT_ATTRIBUTION_COLUMNS)
        self.assertEqual(len(rows), attribution["edges_evaluated"])

    def testProvenanceSurvivesTheRoundTrip(self):
        ''' The method string and the coverage are the two fields whose loss
        would misrepresent the result: a truncated ranking without its
        coverage looks exhaustive. '''
        attribution = edgeAttribution(self.snapshots, self.persistence,
                                      topK=4)
        path = writeElementAttribution(
            attribution, os.path.join(self.directory, "edge2.csv"),
            dataset="synthetic", model="persistence", seed=42)
        _, rows = readCsv(path)
        for row in rows:
            self.assertIn("occlusion", row["method"])
            self.assertEqual(row["dataset"], "synthetic")
            self.assertEqual(row["seed"], "42")
            self.assertTrue(row["coverage"])
            self.assertTrue(row["u"] and row["v"])

    def testImpactIsPreservedExactly(self):
        attribution = edgeAttribution(self.snapshots, self.persistence,
                                      topK=5)
        path = writeElementAttribution(
            attribution, os.path.join(self.directory, "edge3.csv"))
        _, rows = readCsv(path)
        written = [float(r["impact"]) for r in rows]
        expected = [r["impact"] for r in attribution["rows"]]
        self.assertEqual(written, expected)

    def testNoGraphObjectsArePersisted(self):
        ''' Storing perturbed graphs would multiply output size for no
        analytical gain - they are reconstructible from the seed. '''
        attribution = edgeAttribution(self.snapshots, self.persistence,
                                      topK=3)
        path = writeElementAttribution(
            attribution, os.path.join(self.directory, "edge4.csv"))
        text = open(path, encoding="utf-8").read()
        self.assertNotIn("Graph", text)
        self.assertLess(os.path.getsize(path), 20000)


class TestTemporalAttributionPersistence(AttributionFixture):

    def testSchemaAndRequiredFields(self):
        transformation = BridgeWidthTransformation(self.communities, seed=42)
        attribution = temporalAttribution(self.snapshots, self.persistence,
                                          transformation, 0.5)
        path = writeTemporalAttribution(
            attribution, os.path.join(self.directory, "temporal.csv"),
            dataset="synthetic", model="persistence", seed=42,
            achievedDelta=0.5)
        header, rows = readCsv(path)
        self.assertEqual(tuple(header), TEMPORAL_ATTRIBUTION_COLUMNS)
        self.assertEqual(len(rows), len(self.snapshots))
        for field in ("snapshot_index", "concept", "requested_delta",
                      "achieved_delta", "baseline_prediction",
                      "after_prediction", "impact", "edges_added",
                      "edges_removed", "nodes_affected"):
            self.assertIn(field, header)

    def testAttributionLevelIsRecorded(self):
        ''' The column that stops snapshot-concept attribution being
        mistaken for edge-time attribution. '''
        transformation = BridgeWidthTransformation(self.communities, seed=42)
        attribution = temporalAttribution(self.snapshots, self.persistence,
                                          transformation, 0.5)
        path = writeTemporalAttribution(
            attribution, os.path.join(self.directory, "temporal2.csv"))
        _, rows = readCsv(path)
        for row in rows:
            self.assertEqual(row["attribution_level"], "snapshot_concept")


class TestEdgeTimeAttribution(AttributionFixture):
    ''' The genuinely new object: one edge at one time. '''

    def testPerturbsOneEdgeInOneSnapshot(self):
        result = edgeTimeAttribution(self.snapshots, self.persistence,
                                     snapshotIndex=4, topK=3)
        self.assertEqual(result["model_calls"], 1 + len(result["rows"]))
        for row in result["rows"]:
            self.assertEqual(row["snapshot_index"], 4)
            self.assertEqual(row["element"], "edge_time")
            self.assertAlmostEqual(
                row["impact"],
                row["after_prediction"] - row["baseline_prediction"],
                places=12)

    def testPresentOnlyModelRespondsOnlyAtTheLastSnapshot(self):
        ''' A present-only model CANNOT respond to an edge removed from an
        earlier snapshot. Exactly zero is the correct answer. '''
        result = edgeTimeAttribution(self.snapshots, self.persistence, topK=4)
        self.assertEqual(result["snapshots_with_any_response"],
                         [len(self.snapshots) - 1])

    def testTrajectoryModelRespondsAcrossTime(self):
        result = edgeTimeAttribution(self.snapshots, self.trajectory, topK=4)
        self.assertGreater(len(result["snapshots_with_any_response"]), 1)

    def testAllZeroIsReportedNotHidden(self):
        ''' If nothing responds, the result must SAY so rather than be
        plotted as a blank panel. '''
        class Constant:
            def predict(self, temporalGraph):
                return 1.0
        result = edgeTimeAttribution(self.snapshots, Constant(), topK=2)
        self.assertTrue(result["all_zero"])
        self.assertEqual(result["snapshots_with_any_response"], [])
        self.assertIn("does NOT mean", result["method_note"])

    def testDistinctFromSnapshotConceptAttribution(self):
        ''' The two temporal objects must not be interchangeable. '''
        concept = temporalAttribution(
            self.snapshots, self.persistence,
            BridgeWidthTransformation(self.communities, seed=42), 0.5)
        edgeTime = edgeTimeAttribution(self.snapshots, self.persistence,
                                       topK=2)
        self.assertIn("concept", concept["rows"][0])
        self.assertNotIn("edge", concept["rows"][0])
        self.assertIn("edge", edgeTime["rows"][0])
        self.assertNotIn("concept", edgeTime["rows"][0])


class TestBridgeTrendDeltaGuard(unittest.TestCase):
    ''' Regression: delta = -1 divides by (1 + delta) = 0. '''

    def setUp(self):
        self.snapshots, self.communities = makeTemporalGraph(
            nSnapshots=5, nPerCommunity=6, bridgeWidth=6, seed=1)
        self.transformation = BridgeTrendTransformation(self.communities,
                                                        seed=42)

    def testDeltaMinusOneRaisesAClearError(self):
        with self.assertRaises(ValueError) as caught:
            self.transformation.transform(self.snapshots, -1)
        message = str(caught.exception)
        self.assertIn("-1", message)
        self.assertIn("divides by", message)

    def testNotAZeroDivisionError(self):
        ''' The point of the guard: a caller should learn WHY, not get a
        bare arithmetic error from inside a loop. '''
        try:
            self.transformation.transform(self.snapshots, -1)
        except ZeroDivisionError:
            self.fail("still raising a bare ZeroDivisionError")
        except ValueError:
            pass

    def testNeighbouringDeltasStillWork(self):
        ''' The guard must not change behaviour anywhere else. '''
        for delta in (-0.99, -0.5, -0.1, 0.1, 0.5, 1.0):
            result = self.transformation.transform(self.snapshots, delta)
            self.assertEqual(len(result), len(self.snapshots))


if __name__ == "__main__":
    unittest.main()
