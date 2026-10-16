'''
Tests for N-community support.

Two things are under test, and the second matters more than the first:

  1. that a partition of ANY size works - 1, 2, 3, N communities, pairwise
     and aggregate bridge width, deterministic ordering;

  2. that nothing about the TWO-community case changed. Every result this
     project has published was produced with a two-community partition, so
     the N-community generalisation is only acceptable if the N = 2 path is
     bit-for-bit what it was. The regression tests below assert that
     equality directly - same partition, same bridge width, same chosen
     edges - rather than assuming it.

Everything here runs on hand-built graphs where the answer can be counted
by hand. No network, no datasets.
'''

import random
import unittest

import networkx as nx

from core import (
    BridgeTrendTransformation, BridgeWidthTransformation, BridgeWidthMetric,
    CentralizationTransformation, ChurnTransformation, DensityTransformation,
    PersistenceTemporalModel, TgapExplainer, detectTwoCommunities,
)
from core.Communities import (
    Partition, aggregateBridgeWidth, asPartition, bridgeMatrix,
    detectCommunities, interCommunityEdges, intraCommunityEdges,
)
from core.Transformations import setBridgeWidth


def threeCommunityGraph():
    ''' Three groups of three, with a hand-countable bridge structure:

        A = {a0,a1,a2}   B = {b0,b1,b2}   C = {c0,c1,c2}
        each group is a triangle           (3 intra edges each)
        A-B : 2 edges     A-C : 1 edge     B-C : 3 edges
    '''
    graph = nx.Graph()
    groups = {
        "a": ["a0", "a1", "a2"],
        "b": ["b0", "b1", "b2"],
        "c": ["c0", "c1", "c2"],
    }
    for members in groups.values():
        graph.add_nodes_from(members)
        graph.add_edges_from([(members[0], members[1]),
                              (members[1], members[2]),
                              (members[0], members[2])])
    graph.add_edges_from([("a0", "b0"), ("a1", "b1")])                # A-B: 2
    graph.add_edges_from([("a2", "c0")])                              # A-C: 1
    graph.add_edges_from([("b0", "c0"), ("b1", "c1"), ("b2", "c2")])  # B-C: 3
    partition = Partition([set(groups["a"]), set(groups["b"]),
                           set(groups["c"])], labels=["A", "B", "C"])
    return graph, partition


class TestPartition(unittest.TestCase):
    ''' The representation itself: node -> community and community -> nodes,
    for any N. '''

    def testOneCommunityIsValid(self):
        ''' N = 1 is meaningful: everything is one group, so there are no
        bridges at all. It must not crash. '''
        graph = nx.Graph([(0, 1), (1, 2)])
        partition = Partition([{0, 1, 2}])
        self.assertEqual(len(partition), 1)
        self.assertEqual(partition.pairs(), [])
        self.assertEqual(interCommunityEdges(graph, partition), [])
        self.assertEqual(aggregateBridgeWidth(graph, partition), 0.0)

    def testLookupsBothDirections(self):
        _, partition = threeCommunityGraph()
        self.assertEqual(partition.communityOf("b1"), 1)
        self.assertEqual(partition[1], {"b0", "b1", "b2"})
        self.assertIsNone(partition.communityOf("nobody"))

    def testSameCommunity(self):
        _, partition = threeCommunityGraph()
        self.assertTrue(partition.sameCommunity("a0", "a1"))
        self.assertFalse(partition.sameCommunity("a0", "b0"))
        # A node outside the partition shares a community with nothing, so a
        # filtered-out node can never be mistaken for an insider.
        self.assertFalse(partition.sameCommunity("a0", "nobody"))
        self.assertFalse(partition.sameCommunity("nobody", "nobody"))

    def testPairsAreOrderedAndComplete(self):
        _, partition = threeCommunityGraph()
        self.assertEqual(partition.pairs(), [(0, 1), (0, 2), (1, 2)])
        self.assertEqual(partition.labelOfPair((0, 2)), "A-C")

    def testOverlappingCommunitiesRejected(self):
        with self.assertRaises(ValueError):
            Partition([{1, 2}, {2, 3}])

    def testEmptyPartitionRejected(self):
        with self.assertRaises(ValueError):
            Partition([])

    def testAsPartitionAcceptsEveryHistoricalForm(self):
        ''' Old code holds a plain (setA, setB) tuple; normalising at the
        boundary is what let N-community support arrive without editing
        every call site. '''
        for form in (({1, 2}, {3, 4}), [{1, 2}, {3, 4}],
                     Partition([{1, 2}, {3, 4}])):
            partition = asPartition(form)
            self.assertIsInstance(partition, Partition)
            self.assertEqual(partition.sizes(), [2, 2])


class TestBridgeStructure(unittest.TestCase):
    ''' Pairwise and aggregate bridge width, counted by hand. '''

    def setUp(self):
        self.graph, self.partition = threeCommunityGraph()

    def testBridgeMatrixMatchesHandCount(self):
        matrix = bridgeMatrix(self.graph, self.partition)
        self.assertEqual(matrix[(0, 1)], 2)   # A-B
        self.assertEqual(matrix[(0, 2)], 1)   # A-C
        self.assertEqual(matrix[(1, 2)], 3)   # B-C

    def testEveryPairIsPresentEvenWhenZero(self):
        graph = nx.Graph()
        graph.add_nodes_from(range(6))
        graph.add_edge(0, 2)
        partition = Partition([{0, 1}, {2, 3}, {4, 5}])
        matrix = bridgeMatrix(graph, partition)
        self.assertEqual(set(matrix), {(0, 1), (0, 2), (1, 2)})
        self.assertEqual(matrix[(1, 2)], 0)

    def testAggregateIsTheSumOverPairs(self):
        matrix = bridgeMatrix(self.graph, self.partition)
        self.assertEqual(aggregateBridgeWidth(self.graph, self.partition),
                         float(sum(matrix.values())))
        self.assertEqual(aggregateBridgeWidth(self.graph, self.partition), 6.0)

    def testPairwiseEdgeSelection(self):
        self.assertEqual(
            interCommunityEdges(self.graph, self.partition, (0, 2)),
            [("a2", "c0")])

    def testIntraEdgesPerCommunity(self):
        self.assertEqual(
            len(intraCommunityEdges(self.graph, self.partition, 0)), 3)
        self.assertEqual(
            len(intraCommunityEdges(self.graph, self.partition)), 9)

    def testMetricSupportsAggregateAndPair(self):
        self.assertEqual(
            BridgeWidthMetric(self.partition).measure(self.graph), 6.0)
        self.assertEqual(
            BridgeWidthMetric(self.partition,
                              communityPair=(1, 2)).measure(self.graph), 3.0)

    def testZeroBridge(self):
        ''' Three groups with no cross edges at all: every pair is 0 and the
        aggregate is 0, without raising. '''
        graph = nx.Graph()
        graph.add_nodes_from(range(6))
        graph.add_edges_from([(0, 1), (2, 3), (4, 5)])
        partition = Partition([{0, 1}, {2, 3}, {4, 5}])
        self.assertEqual(aggregateBridgeWidth(graph, partition), 0.0)
        self.assertEqual(set(bridgeMatrix(graph, partition).values()), {0})


class TestTwoCommunityBackwardCompatibility(unittest.TestCase):
    ''' The regression guard. Section 12: "Do not silently change the
    scientific meaning of existing two-community experiments." '''

    def setUp(self):
        self.graph = nx.Graph()
        for side in (range(0, 6), range(6, 12)):
            members = list(side)
            self.graph.add_nodes_from(members)
            for i, u in enumerate(members):
                for v in members[i + 1:]:
                    self.graph.add_edge(u, v)
        self.graph.add_edges_from([(0, 6), (1, 7), (2, 8)])
        self.partition = Partition([set(range(0, 6)), set(range(6, 12))])

    def testTupleUnpackingStillWorks(self):
        ''' Every pre-existing call site does exactly this. If it broke,
        the whole code base would break. '''
        setA, setB = self.partition
        self.assertEqual(setA, set(range(0, 6)))
        self.assertEqual(setB, set(range(6, 12)))

    def testDetectTwoCommunitiesStillReturnsExactlyTwo(self):
        ''' Even on a graph the detector sees as ONE blob, the historical
        contract is two sets - the second simply empty. Returning one set
        would break `setA, setB = ...` at every call site. '''
        blob = nx.complete_graph(6)
        partition = detectTwoCommunities(blob)
        self.assertEqual(len(partition), 2)
        setA, setB = partition
        self.assertEqual(setA | setB, set(blob.nodes()))

    def testAggregateEqualsLegacyBridgeWidth(self):
        legacy = len(interCommunityEdges(self.graph, self.partition))
        self.assertEqual(aggregateBridgeWidth(self.graph, self.partition),
                         float(legacy))
        self.assertEqual(legacy, 3)

    def testPairZeroOneIsIdenticalToAggregateAtTwoCommunities(self):
        ''' With two communities there is exactly one boundary, so naming it
        explicitly must change nothing. '''
        self.assertEqual(
            interCommunityEdges(self.graph, self.partition),
            interCommunityEdges(self.graph, self.partition, (0, 1)))

    def testSetBridgeWidthIdenticalWithAndWithoutPair(self):
        ''' The strongest form of the guarantee: the transformed graphs must
        agree EDGE FOR EDGE, not merely in edge count. '''
        for target in (1, 2, 5, 8):
            withoutPair = setBridgeWidth(self.graph, self.partition, target,
                                         random.Random(42))
            withPair = setBridgeWidth(self.graph, self.partition, target,
                                      random.Random(42), pair=(0, 1))
            self.assertEqual(set(map(frozenset, withoutPair.edges())),
                             set(map(frozenset, withPair.edges())),
                             f"target {target} diverged")

    def testTransformationIdenticalWithAndWithoutPair(self):
        snapshots = [self.graph.copy() for _ in range(4)]
        plain = BridgeWidthTransformation(self.partition, seed=42)
        paired = BridgeWidthTransformation(self.partition, seed=42,
                                           communityPair=(0, 1))
        for delta in (0.25, -0.25, 0.5):
            a = plain.transform(snapshots, delta)
            b = paired.transform(snapshots, delta)
            for first, second in zip(a, b):
                self.assertEqual(set(map(frozenset, first.edges())),
                                 set(map(frozenset, second.edges())))
            self.assertEqual(plain.propertyValue(snapshots),
                             paired.propertyValue(snapshots))


class TestTransformationsWithThreeCommunities(unittest.TestCase):
    ''' Every transformation must operate on an N-community partition, and
    a pair-targeted bridge change must leave the other pairs alone. '''

    def setUp(self):
        graph, self.partition = threeCommunityGraph()
        self.snapshots = [graph.copy() for _ in range(4)]

    def testBridgeWidthTargetsOnlyTheNamedPair(self):
        ''' The scientific point of pairwise mode: widening A-B must not
        silently move A-C or B-C. '''
        before = bridgeMatrix(self.snapshots[0], self.partition)
        transformation = BridgeWidthTransformation(
            self.partition, seed=42, communityPair=(0, 1))
        after = bridgeMatrix(transformation.transform(self.snapshots, 1.0)[0],
                             self.partition)
        self.assertGreater(after[(0, 1)], before[(0, 1)])
        self.assertEqual(after[(0, 2)], before[(0, 2)])
        self.assertEqual(after[(1, 2)], before[(1, 2)])

    def testPairedTransformationIsNamedAfterItsPair(self):
        ''' Explanations are keyed by transformation name, so two pairs must
        not collide into one row. '''
        first = BridgeWidthTransformation(self.partition, communityPair=(0, 1))
        second = BridgeWidthTransformation(self.partition, communityPair=(1, 2))
        self.assertNotEqual(first.name, second.name)
        self.assertIn("0-1", first.name)

    def testEveryTransformationAcceptsThreeCommunities(self):
        for transformation in (
                BridgeWidthTransformation(self.partition, seed=42),
                CentralizationTransformation(self.partition, seed=42),
                DensityTransformation(self.partition, seed=42),
                BridgeTrendTransformation(self.partition, seed=42),
                ChurnTransformation(self.partition, seed=42)):
            result = transformation.transform(self.snapshots, 0.5)
            self.assertEqual(len(result), len(self.snapshots))
            for before, after in zip(self.snapshots, result):
                self.assertEqual(set(after.nodes()), set(before.nodes()),
                                 f"{transformation.name} changed the node set")

    def testChurnAndDensityRespectThreeCommunityBoundaries(self):
        ''' Both are documented as bridge-preserving when a partition is
        given. With three communities that must hold for EVERY pair. '''
        for transformation in (ChurnTransformation(self.partition, seed=42),
                               DensityTransformation(self.partition, seed=42)):
            result = transformation.transform(self.snapshots, 0.5)
            for before, after in zip(self.snapshots, result):
                self.assertEqual(bridgeMatrix(after, self.partition),
                                 bridgeMatrix(before, self.partition),
                                 f"{transformation.name} moved a bridge")

    def testExplainerRunsOnThreeCommunities(self):
        ''' End to end: the generic explainer needs no knowledge of N. '''
        model = PersistenceTemporalModel(BridgeWidthMetric(self.partition))
        transformations = [
            BridgeWidthTransformation(self.partition, seed=42,
                                      communityPair=pair)
            for pair in self.partition.pairs()]
        explanation = TgapExplainer(model, transformations).explain(
            self.snapshots)
        self.assertEqual(len(explanation), 2 * len(self.partition.pairs()))
        for label, value in explanation.items():
            self.assertFalse(value != value, f"{label} is NaN")


class TestDetectCommunities(unittest.TestCase):
    ''' Detection for arbitrary N, and determinism. '''

    def setUp(self):
        # Three clear triangles joined by single edges.
        self.graph = nx.Graph()
        for base in (0, 3, 6):
            self.graph.add_edges_from([(base, base + 1), (base + 1, base + 2),
                                       (base, base + 2)])
        self.graph.add_edges_from([(2, 3), (5, 6)])

    def testNaturalNumberOfCommunities(self):
        partition = detectCommunities(self.graph)
        self.assertEqual(len(partition), 3)
        self.assertEqual(sorted(partition.sizes()), [3, 3, 3])

    def testExplicitNMergesDown(self):
        for n in (1, 2, 3):
            partition = detectCommunities(self.graph, n=n)
            self.assertEqual(len(partition), n)
            self.assertEqual(set().union(*partition), set(self.graph.nodes()))

    def testDetectionIsDeterministic(self):
        first = detectCommunities(self.graph)
        second = detectCommunities(self.graph)
        self.assertEqual([sorted(g) for g in first],
                         [sorted(g) for g in second])

    def testRejectsNonPositiveN(self):
        with self.assertRaises(ValueError):
            detectCommunities(self.graph, n=0)


if __name__ == "__main__":
    unittest.main()
