'''
Tests for core.Feasibility - the module that decides whether a
transformation kept the invariant it promised.

Everything here runs on HAND-BUILT graphs where the right answer can be
counted by hand, and nothing touches the network or the real datasets. That
is deliberate: the feasibility rules are about graph arithmetic, so they
should be provable on five-node examples, not inferred from a large file.

The four situations under test:

  feasible widening     enough cross non-edges to add AND enough
                        intra-community edges to pay with -> edge count
                        preserved exactly.
  infeasible widening   more bridge edges than intra edges, so the payment
                        is impossible -> permissive mode silently changes
                        the edge count, strict mode raises.
  trend saturation      a long history pushed below the width-1 floor.
  trend wrong direction the achieved trend moving against the request.
'''

import random
import unittest

import networkx as nx

from core import (
    BridgeTrendTransformation, BridgeWidthTransformation,
    CentralizationTransformation, ChurnTransformation, DensityTransformation,
    InfeasibleTransformation, bridgeTrendDirection, bridgeWidthFeasibility,
    declaresEdgeCountPreservation, edgeCountFeasibility,
)
from core.Communities import interCommunityEdges, intraCommunityEdges
from core.Transformations import setBridgeWidth


def feasibleGraph():
    ''' Two communities of four nodes. Each side is a complete K4 (6 intra
    edges each, 12 in total) and there are 2 bridge edges.

    Counted by hand: cross pairs = 4 x 4 = 16, of which 2 are edges, so 14
    cross non-edges are available to widen with, and 12 intra edges are
    available to pay with. Widening by a few edges is comfortably feasible.
    '''
    setA = {"a0", "a1", "a2", "a3"}
    setB = {"b0", "b1", "b2", "b3"}
    graph = nx.Graph()
    graph.add_nodes_from(sorted(setA | setB))
    for side in (sorted(setA), sorted(setB)):
        for i, u in enumerate(side):
            for v in side[i + 1:]:
                graph.add_edge(u, v)
    graph.add_edge("a0", "b0")
    graph.add_edge("a1", "b1")
    return graph, (setA, setB)


def infeasibleGraph():
    ''' Three nodes per side, SIX bridge edges and only ONE intra edge.

    This is the real-data shape that motivated the whole gate: two groups
    that interact with each other far more than internally. Widening by
    50% needs round(6 * 1.5) - 6 = 3 new bridges, and therefore 3 intra
    edges to delete - but only one exists.
    '''
    setA = {"a0", "a1", "a2"}
    setB = {"b0", "b1", "b2"}
    graph = nx.Graph()
    graph.add_nodes_from(sorted(setA | setB))
    graph.add_edges_from([("a0", "b0"), ("a0", "b1"), ("a1", "b0"),
                          ("a1", "b1"), ("a2", "b2"), ("a0", "b2")])
    graph.add_edge("a0", "a1")           # the ONLY intra edge
    return graph, (setA, setB)


class TestContractAttribute(unittest.TestCase):
    ''' Which transformations promise to preserve the edge count. Read from
    the transformation itself, never from its name. '''

    def testEveryTransformationDeclaresItsPromise(self):
        communities = ({"a"}, {"b"})
        self.assertTrue(declaresEdgeCountPreservation(
            BridgeWidthTransformation(communities)))
        self.assertTrue(declaresEdgeCountPreservation(
            CentralizationTransformation(communities)))
        self.assertTrue(declaresEdgeCountPreservation(
            BridgeTrendTransformation(communities)))
        self.assertTrue(declaresEdgeCountPreservation(
            ChurnTransformation(communities)))
        # Density is the documented exception: the edge count IS its
        # property, so it promises nothing about it.
        self.assertFalse(declaresEdgeCountPreservation(
            DensityTransformation(communities)))


class TestBridgeWidthFeasibleCase(unittest.TestCase):
    ''' Test E and G: the feasible case must be reported feasible, and the
    edge count must actually be preserved. '''

    def setUp(self):
        self.graph, self.communities = feasibleGraph()

    def testHandCountedPoolsMatchTheInspection(self):
        report = bridgeWidthFeasibility(self.graph, self.communities, 5)
        self.assertEqual(report["current_width"], 2)
        self.assertEqual(report["cross_nonedges_available"], 14)
        self.assertEqual(report["intra_edges_available"], 12)
        self.assertEqual(report["edge_change"], 3)
        self.assertTrue(report["feasible"])
        self.assertIsNone(report["reason"])

    def testEdgeCountIsPreservedWhenFeasible(self):
        before = self.graph.number_of_edges()
        for target in (3, 5, 8):
            result = setBridgeWidth(self.graph, self.communities, target,
                                    random.Random(42))
            self.assertEqual(result.number_of_edges(), before,
                             f"target {target} changed the edge count")
            self.assertEqual(set(result.nodes()), set(self.graph.nodes()))

    def testNarrowingIsInfeasibleWhenBothSidesAreComplete(self):
        ''' The mirror-image failure, found by this test suite rather than
        assumed: NARROWING pays back by ADDING an intra-community edge, and
        both sides here are already complete K4s, so there is no intra
        non-edge to add. The gate catches it in the same way as the widening
        shortage - which is why both directions are screened separately.
        '''
        report = bridgeWidthFeasibility(self.graph, self.communities, 1)
        self.assertEqual(report["intra_nonedges_available"], 0)
        self.assertFalse(report["feasible"])
        self.assertIn("intra-community non-edges", report["reason"])
        with self.assertRaises(InfeasibleTransformation):
            setBridgeWidth(self.graph, self.communities, 1,
                           random.Random(42), strict=True)

    def testStrictModeAgreesAndDoesNotRaise(self):
        result = setBridgeWidth(self.graph, self.communities, 5,
                                random.Random(42), strict=True)
        self.assertEqual(result.number_of_edges(),
                         self.graph.number_of_edges())
        self.assertEqual(len(interCommunityEdges(result, self.communities)), 5)

    def testTransformationReportsFeasibleOnATemporalGraph(self):
        snapshots = [self.graph.copy() for _ in range(4)]
        transformation = BridgeWidthTransformation(self.communities, seed=7)
        strict = BridgeWidthTransformation(self.communities, seed=7,
                                           strict=True)
        report = edgeCountFeasibility(snapshots, transformation, 0.5,
                                      self.communities,
                                      strictTransformation=strict)
        self.assertTrue(report["feasible"])
        self.assertEqual(report["snapshots_violating"], 0)
        self.assertEqual(report["edge_count_before"],
                         report["edge_count_after"])
        self.assertFalse(report["strict_raised"])


class TestBridgeWidthInfeasibleCase(unittest.TestCase):
    ''' Test F: when the payment is impossible the failure must be explicit,
    and the permissive path must be shown to violate the invariant (that is
    exactly the behaviour the gate exists to catch). '''

    def setUp(self):
        self.graph, self.communities = infeasibleGraph()

    def testHandCountedShortfall(self):
        self.assertEqual(len(interCommunityEdges(self.graph,
                                                 self.communities)), 6)
        self.assertEqual(len(intraCommunityEdges(self.graph,
                                                 self.communities)), 1)
        report = bridgeWidthFeasibility(self.graph, self.communities, 9)
        self.assertFalse(report["feasible"])
        self.assertIn("intra-community edges", report["reason"])
        self.assertEqual(report["shortfall"], 2)   # needs 3, has 1

    def testPermissiveModeSilentlyChangesTheEdgeCount(self):
        ''' Documents the behaviour being gated: without strict mode the
        transformation under-pays, so the total edge count rises. '''
        before = self.graph.number_of_edges()
        result = setBridgeWidth(self.graph, self.communities, 9,
                                random.Random(42))
        self.assertGreater(result.number_of_edges(), before)

    def testStrictModeRaisesWithMeasuredDetail(self):
        with self.assertRaises(InfeasibleTransformation) as caught:
            setBridgeWidth(self.graph, self.communities, 9,
                           random.Random(42), strict=True)
        self.assertIn("intra-community edges", str(caught.exception))
        self.assertTrue(caught.exception.detail)

    def testTransformationReportsInfeasibleOnATemporalGraph(self):
        snapshots = [self.graph.copy() for _ in range(3)]
        transformation = BridgeWidthTransformation(self.communities, seed=7)
        strict = BridgeWidthTransformation(self.communities, seed=7,
                                           strict=True)
        report = edgeCountFeasibility(snapshots, transformation, 0.5,
                                      self.communities,
                                      strictTransformation=strict)
        self.assertFalse(report["feasible"])
        self.assertTrue(report["strict_raised"])
        self.assertEqual(report["snapshots_violating"], 3)
        self.assertNotEqual(report["edge_count_before"],
                            report["edge_count_after"])
        self.assertIn("edge count", report["reason"])

    def testDensityIsNeverReportedAsViolating(self):
        ''' The edge count IS Density's property, so a changed edge count
        must not be counted against it. '''
        snapshots = [self.graph.copy() for _ in range(3)]
        report = edgeCountFeasibility(
            snapshots, DensityTransformation(self.communities, seed=7), 0.5,
            self.communities)
        self.assertFalse(report["declares_preservation"])
        self.assertTrue(report["feasible"])
        self.assertEqual(report["snapshots_violating"], 0)


def trendSnapshots(widths, sideSize=6):
    ''' Build a temporal graph whose bridge widths are exactly `widths`,
    with a generous intra-community pool in every snapshot so that
    setBridgeWidth is never blocked by a shortage of payment - the only
    limit left is the width-1 floor, which is what these tests are about. '''
    setA = {f"a{i}" for i in range(sideSize)}
    setB = {f"b{i}" for i in range(sideSize)}
    crossPairs = [(a, b) for a in sorted(setA) for b in sorted(setB)]
    snapshots = []
    for width in widths:
        graph = nx.Graph()
        graph.add_nodes_from(sorted(setA | setB))
        for side in (sorted(setA), sorted(setB)):
            for i, u in enumerate(side):
                for v in side[i + 1:]:
                    graph.add_edge(u, v)          # full intra pool
        graph.add_edges_from(crossPairs[:width])
        snapshots.append(graph)
    return snapshots, (setA, setB)


class TestBridgeTrendSaturation(unittest.TestCase):
    ''' Test H: the width-1 floor must be DETECTED, with the short-history
    and boundary cases behaving sensibly. '''

    def testShortHistoryIsNotSaturated(self):
        ''' Two snapshots: the compounding factor is (1 + delta)^1, far too
        small to push anything to the floor. '''
        snapshots, communities = trendSnapshots([6, 6])
        report = bridgeTrendDirection(
            snapshots, BridgeTrendTransformation(communities, seed=1), 0.1)
        self.assertEqual(report["snapshots_saturated"], 0)
        self.assertAlmostEqual(report["compounding_factor"], 1.1)
        self.assertNotEqual(report["status"], "saturated")

    def testLongHistorySaturatesAtTheFloor(self):
        ''' Twelve snapshots at delta = 0.5: the factor reaching the oldest
        snapshot is 1.5^11 = 86.5, so early targets fall below 1 and are
        clamped. '''
        snapshots, communities = trendSnapshots([6] * 12)
        report = bridgeTrendDirection(
            snapshots, BridgeTrendTransformation(communities, seed=1), 0.5)
        self.assertGreater(report["compounding_factor"], 80)
        self.assertGreater(report["snapshots_saturated"], 0)
        self.assertEqual(report["min_bridge_width"], 1)
        self.assertEqual(report["status"], "saturated")
        self.assertFalse(report["valid_for_analysis"])

    def testIncreaseAndDecreaseAreBothMeasured(self):
        snapshots, communities = trendSnapshots([4] * 8)
        transformation = BridgeTrendTransformation(communities, seed=1)
        up = bridgeTrendDirection(snapshots, transformation, 0.25)
        down = bridgeTrendDirection(snapshots, transformation, -0.25)
        self.assertEqual(up["requested_direction"], 1)
        self.assertEqual(down["requested_direction"], -1)
        # The anchor: the last snapshot's width is never touched.
        for report in (up, down):
            self.assertEqual(report["max_bridge_width_before"], 4)

    def testLastSnapshotIsAlwaysTheAnchor(self):
        snapshots, communities = trendSnapshots([2, 3, 4, 5, 6])
        transformation = BridgeTrendTransformation(communities, seed=1)
        for delta in (0.1, -0.1, 0.5, -0.5):
            result = transformation.transform(snapshots, delta)
            self.assertEqual(
                len(interCommunityEdges(result[-1], communities)),
                len(interCommunityEdges(snapshots[-1], communities)),
                f"delta {delta} moved the anchored last snapshot")

    def testStatusIsOkWhenNothingClamps(self):
        snapshots, communities = trendSnapshots([20, 22, 24, 26])
        report = bridgeTrendDirection(
            snapshots, BridgeTrendTransformation(communities, seed=1), 0.1)
        self.assertEqual(report["snapshots_saturated"], 0)
        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["valid_for_analysis"])


class _FixedTrend(BridgeTrendTransformation):
    ''' A BridgeTrendTransformation that returns a prescribed trajectory.

    Why a stub. The wrong-direction failure needs an achieved trajectory
    that moves against the request; whether a PARTICULAR real graph can be
    driven there depends on its cross-pair capacity, so constructing one
    would make the test about the graph rather than about the detector. The
    detector is what is under test here, so the trajectory is supplied
    directly. The saturation tests above use the real transformation on real
    graph arithmetic, so both paths are covered.
    '''

    def __init__(self, communities, after):
        super().__init__(communities)
        self._after = after

    def transform(self, temporalGraph, delta):
        return self._after


class TestBridgeTrendWrongDirection(unittest.TestCase):
    ''' Test I: a trend that moved against the request must be flagged
    wrong_direction and must never count as a valid result. '''

    def testWrongDirectionIsDetected(self):
        before, communities = trendSnapshots([1, 2, 3, 4])   # slope +1
        after, _ = trendSnapshots([4, 4, 4, 4])              # slope 0
        report = bridgeTrendDirection(
            before, _FixedTrend(communities, after), 0.1)
        self.assertEqual(report["requested_direction"], 1)
        self.assertEqual(report["achieved_direction"], -1)
        self.assertEqual(report["status"], "wrong_direction")
        self.assertFalse(report["valid_for_analysis"])

    def testWrongDirectionTheOtherWayRound(self):
        before, communities = trendSnapshots([4, 3, 2, 1])   # slope -1
        after, _ = trendSnapshots([1, 1, 1, 1])              # slope 0
        report = bridgeTrendDirection(
            before, _FixedTrend(communities, after), -0.1)
        self.assertEqual(report["requested_direction"], -1)
        self.assertEqual(report["achieved_direction"], 1)
        self.assertEqual(report["status"], "wrong_direction")

    def testAnUnmovedTrendIsItsOwnStatus(self):
        before, communities = trendSnapshots([3, 3, 3, 3])
        after, _ = trendSnapshots([3, 3, 3, 3])
        report = bridgeTrendDirection(
            before, _FixedTrend(communities, after), 0.1)
        self.assertEqual(report["achieved_direction"], 0)
        self.assertEqual(report["status"], "no_property_change")
        self.assertFalse(report["valid_for_analysis"])

    def testCorrectDirectionWithoutClampingIsValid(self):
        before, communities = trendSnapshots([6, 6, 6, 6])   # slope 0
        after, _ = trendSnapshots([3, 4, 5, 6])              # slope +1
        report = bridgeTrendDirection(
            before, _FixedTrend(communities, after), 0.25)
        self.assertEqual(report["status"], "ok")
        self.assertTrue(report["valid_for_analysis"])


if __name__ == "__main__":
    unittest.main()
