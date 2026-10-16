''' Transformation tests: exact correctness, anchors, determinism,
orthogonality, boundary cases, and mutation safety.

Philosophy: every test either asserts a value derivable by hand, or an
invariant the docstrings promise. "It runs" is not a test. '''

import unittest

import networkx as nx

from core import (
    BridgeWidthTransformation, CentralizationTransformation,
    DensityTransformation, BridgeTrendTransformation, ChurnTransformation,
    BridgeWidthMetric, DegreeCentralizationMetric,
    makeTwoCommunityGraph, makeTemporalGraph,
)
from core.Communities import interCommunityEdges


def edgeSet(g):
    ''' Canonical frozen edge set for exact graph comparison. '''
    return {frozenset(e) for e in g.edges()}


def snapshotFingerprint(tg):
    ''' Node+edge fingerprint of every snapshot, for mutation checks. '''
    return [(set(g.nodes()), edgeSet(g)) for g in tg]


class TransformationTestCase(unittest.TestCase):
    def setUp(self):
        # A standard world: 2x15 nodes, exact bridge width 8, mild churn.
        self.tg, self.comm = makeTemporalGraph(
            nSnapshots=6, nPerCommunity=15, bridgeWidth=8,
            churn=0.05, bridgeDrift=0, seed=42)
        self.g = self.tg[-1]

    def width(self, g):
        return len(interCommunityEdges(g, self.comm))


class TestBridgeWidthExact(TransformationTestCase):
    ''' Correctness: exact width targets, per the round(w*(1+delta)) rule. '''

    def testIncreaseTenPercent(self):
        t = BridgeWidthTransformation(self.comm)
        gT = t.transformGraph(self.g, 0.1)
        # round(8 * 1.1) = round(8.8) = 9
        self.assertEqual(self.width(gT), 9)

    def testDecreaseTenPercent(self):
        t = BridgeWidthTransformation(self.comm)
        gT = t.transformGraph(self.g, -0.1)
        self.assertEqual(self.width(gT), round(8 * 0.9))  # 7

    def testZeroDeltaIsIdentity(self):
        t = BridgeWidthTransformation(self.comm)
        gT = t.transformGraph(self.g, 0.0)
        self.assertEqual(edgeSet(gT), edgeSet(self.g))

    def testTinyDeltaIsNoop(self):
        # delta too small to move one whole edge: round(8*1.01)=8.
        t = BridgeWidthTransformation(self.comm)
        gT = t.transformGraph(self.g, 0.01)
        self.assertEqual(edgeSet(gT), edgeSet(self.g))

    def testLargeDeltaCappedByCandidates(self):
        t = BridgeWidthTransformation(self.comm)
        gT = t.transformGraph(self.g, 5.0)  # target 48, plenty of room
        self.assertEqual(self.width(gT), round(8 * 6.0))
        self.assertLessEqual(self.width(gT), 15 * 15)

    def testEdgeCountAndNodesPreserved(self):
        t = BridgeWidthTransformation(self.comm)
        for delta in (0.3, -0.3, 1.0, -0.6):
            gT = t.transformGraph(self.g, delta)
            self.assertEqual(set(gT.nodes()), set(self.g.nodes()))
            self.assertEqual(gT.number_of_edges(),
                             self.g.number_of_edges(),
                             f"edge-count anchor broken at delta={delta}")

    def testNeverSeversLastBridge(self):
        # A world with exactly ONE bridge: narrowing must be a no-op.
        g, comm = makeTwoCommunityGraph(nPerCommunity=6, bridgeWidth=1,
                                        seed=1)
        t = BridgeWidthTransformation(comm)
        gT = t.transformGraph(g, -0.9)
        self.assertEqual(len(interCommunityEdges(gT, comm)), 1)

    def testTinyGraph(self):
        # 2 nodes per side: must not crash, must respect clamp.
        g, comm = makeTwoCommunityGraph(nPerCommunity=2, bridgeWidth=1,
                                        pIntra=0.5, seed=3)
        t = BridgeWidthTransformation(comm)
        for delta in (0.5, -0.5, 2.0):
            gT = t.transformGraph(g, delta)
            self.assertGreaterEqual(len(interCommunityEdges(gT, comm)), 1)

    def testDisconnectedInputDoesNotCrash(self):
        g = nx.Graph()
        g.add_nodes_from(range(8))
        g.add_edges_from([(0, 1), (1, 2), (4, 5), (5, 6), (0, 4)])
        comm = (set(range(4)), set(range(4, 8)))
        gT = BridgeWidthTransformation(comm).transformGraph(g, 0.5)
        self.assertEqual(set(gT.nodes()), set(g.nodes()))


class TestCentralization(TransformationTestCase):
    ''' The centralization rewiring: metric direction, orthogonality. '''

    def testConcentrateRaisesMetric(self):
        t = CentralizationTransformation(self.comm)
        metric = DegreeCentralizationMetric()
        before = metric.measure(self.g)
        after = metric.measure(t.transformGraph(self.g, 0.2))
        self.assertGreater(after, before)

    def testRedistributeLowersMetric(self):
        # First concentrate hard so there is something to redistribute.
        t = CentralizationTransformation(self.comm)
        gC = t.transformGraph(self.g, 0.3)
        metric = DegreeCentralizationMetric()
        self.assertLess(metric.measure(t.transformGraph(gC, -0.2)),
                        metric.measure(gC))

    def testRedistributeLowersMetricUnderTiedMaxDegree(self):
        ''' Regression test for the tied-hub bug found by the
        faithfulness evaluation: Freeman centralization under edge-
        preserving rewiring is C = (n*d_max - 2m)/((n-1)(n-2)), so when
        TWO nodes tie at maximum degree, draining only one of them
        leaves d_max (hence C) unchanged. The fix drains the CURRENT
        top node each step, so decrease must work on every snapshot -
        including those with ties (snapshots 0, 3, 4, 5 of the standard
        world had ties and silently no-oped before the fix). '''
        t = CentralizationTransformation(self.comm)
        metric = DegreeCentralizationMetric()
        for i, g in enumerate(self.tg):
            gT = t.transformGraph(g, -0.1)
            self.assertLess(metric.measure(gT), metric.measure(g),
                            f"decrease no-oped on snapshot {i}")

    def testBridgePreservedExactly(self):
        ''' The bug-1 regression test: with communities given, rewiring
        must preserve every tie's intra/inter status, so bridge width is
        untouched for ANY delta. '''
        t = CentralizationTransformation(self.comm)
        for delta in (0.05, 0.1, 0.3, -0.05, -0.1, -0.3):
            gT = t.transformGraph(self.g, delta)
            self.assertEqual(self.width(gT), self.width(self.g),
                             f"bridge leak at delta={delta}")

    def testAnchorNodeAndEdgeCount(self):
        t = CentralizationTransformation(self.comm)
        for delta in (0.2, -0.2):
            gT = t.transformGraph(self.g, delta)
            self.assertEqual(set(gT.nodes()), set(self.g.nodes()))
            self.assertEqual(gT.number_of_edges(),
                             self.g.number_of_edges())


class TestDensity(TransformationTestCase):
    def testExactEdgeCountChange(self):
        t = DensityTransformation()
        m = self.g.number_of_edges()
        self.assertEqual(t.transformGraph(self.g, 0.2).number_of_edges(),
                         round(m * 1.2))
        self.assertEqual(t.transformGraph(self.g, -0.2).number_of_edges(),
                         round(m * 0.8))

    def testCommunitiesModePreservesBridge(self):
        ''' The audit-#3 fix: with a partition, density changes are
        confined to intra pairs, so bridge width never moves. '''
        t = DensityTransformation(communities=self.comm)
        for delta in (0.2, -0.2):
            gT = t.transformGraph(self.g, delta)
            self.assertEqual(self.width(gT), self.width(self.g))

    def testUnconstrainedModeLeaksIntoBridge(self):
        ''' Document the leak, do not hide it: WITHOUT the partition,
        adding 30% more edges is expected to widen the bridge (the
        non-edge pool is dominated by cross pairs). '''
        gT = DensityTransformation().transformGraph(self.g, 0.3)
        self.assertGreater(self.width(gT), self.width(self.g))

    def testCompleteGraphNoAddCandidates(self):
        g = nx.complete_graph(6)
        gT = DensityTransformation().transformGraph(g, 0.5)
        self.assertEqual(gT.number_of_edges(), g.number_of_edges())


class TestBridgeTrend(TransformationTestCase):
    def testLastSnapshotByteIdentical(self):
        t = BridgeTrendTransformation(self.comm)
        for delta in (0.1, -0.1, 0.3):
            tgT = t.transform(self.tg, delta)
            self.assertEqual(edgeSet(tgT[-1]), edgeSet(self.tg[-1]))
            self.assertEqual(set(tgT[-1].nodes()), set(self.tg[-1].nodes()))

    def testTrajectoryDirection(self):
        ''' delta>0 must produce a RISING width history (earlier widths
        pushed below the anchored present), delta<0 a decaying one. '''
        t = BridgeTrendTransformation(self.comm)
        up = [self.width(g) for g in t.transform(self.tg, 0.1)]
        down = [self.width(g) for g in t.transform(self.tg, -0.1)]
        self.assertLess(up[0], up[-1])       # rises toward the present
        self.assertGreater(down[0], down[-1])  # decays toward the present

    def testCompoundingMatchesTsapRecursion(self):
        ''' Hand-derived targets for constant width 8, delta=+0.1
        (see docs/02, section 10.6): [5, 5, 6, 7, 7, 8]. '''
        t = BridgeTrendTransformation(self.comm)
        widths = [self.width(g) for g in t.transform(self.tg, 0.1)]
        self.assertEqual(widths, [5, 5, 6, 7, 7, 8])

    def testPerSnapshotAnchors(self):
        t = BridgeTrendTransformation(self.comm)
        tgT = t.transform(self.tg, 0.2)
        for g0, gT in zip(self.tg, tgT):
            self.assertEqual(set(gT.nodes()), set(g0.nodes()))
            self.assertEqual(gT.number_of_edges(), g0.number_of_edges())

    def testStaticModeRaises(self):
        with self.assertRaises(NotImplementedError):
            BridgeTrendTransformation(self.comm).transformGraph(self.g, 0.1)


class TestChurn(TransformationTestCase):
    def testLastSnapshotByteIdentical(self):
        t = ChurnTransformation(self.comm)
        for delta in (0.3, -0.3):
            tgT = t.transform(self.tg, delta)
            self.assertEqual(edgeSet(tgT[-1]), edgeSet(self.tg[-1]))

    def testChurnPropertyMovesInDeltaDirection(self):
        t = ChurnTransformation(self.comm)
        base = t.propertyValue(self.tg)
        self.assertGreater(t.propertyValue(t.transform(self.tg, 0.5)), base)
        self.assertLess(t.propertyValue(t.transform(self.tg, -0.5)), base)

    def testBridgePreservedInEverySnapshot(self):
        t = ChurnTransformation(self.comm)
        for delta in (0.5, -0.5):
            for g0, gT in zip(self.tg, t.transform(self.tg, delta)):
                self.assertEqual(self.width(gT), self.width(g0))

    def testEdgeCountPreservedInEverySnapshot(self):
        t = ChurnTransformation(self.comm)
        for delta in (0.5, -0.5):
            for g0, gT in zip(self.tg, t.transform(self.tg, delta)):
                self.assertEqual(gT.number_of_edges(), g0.number_of_edges())

    def testSingleSnapshotPropertyUndefined(self):
        self.assertIsNone(
            ChurnTransformation(self.comm).propertyValue([self.g]))

    def testStaticModeRaises(self):
        with self.assertRaises(NotImplementedError):
            ChurnTransformation(self.comm).transformGraph(self.g, 0.1)


class TestDeterminismAndMutation(TransformationTestCase):
    ''' Same input + same seed + same delta => identical output;
    and the input is NEVER modified. '''

    def allTransformations(self):
        return [BridgeWidthTransformation(self.comm),
                CentralizationTransformation(self.comm),
                DensityTransformation(self.comm),
                BridgeTrendTransformation(self.comm),
                ChurnTransformation(self.comm)]

    def testDeterminism(self):
        for t in self.allTransformations():
            for delta in (0.2, -0.2):
                a = t.transform(self.tg, delta)
                b = t.transform(self.tg, delta)
                for ga, gb in zip(a, b):
                    self.assertEqual(edgeSet(ga), edgeSet(gb),
                                     f"{t.name} nondeterministic")

    def testInputNeverMutated(self):
        before = snapshotFingerprint(self.tg)
        for t in self.allTransformations():
            for delta in (0.3, -0.3):
                t.transform(self.tg, delta)
        after = snapshotFingerprint(self.tg)
        self.assertEqual(before, after, "a transformation mutated its input")

    def testDifferentSeedsDifferentChoices(self):
        ''' Seeds must actually matter (guards against an accidentally
        constant rng): two seeds should generally pick different edges. '''
        a = BridgeWidthTransformation(self.comm, seed=1).transformGraph(
            self.g, 0.5)
        b = BridgeWidthTransformation(self.comm, seed=2).transformGraph(
            self.g, 0.5)
        # Same achieved width...
        self.assertEqual(self.width(a), self.width(b))
        # ...but (almost surely) different edge choices.
        self.assertNotEqual(edgeSet(a), edgeSet(b))


if __name__ == "__main__":
    unittest.main()
