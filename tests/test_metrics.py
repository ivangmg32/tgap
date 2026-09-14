''' Metric tests: hand-derivable values on canonical graphs. '''

import unittest

import networkx as nx

from core import (DensityMetric, DegreeCentralizationMetric,
                  BridgeWidthMetric, CohesionMetric, ClusteringMetric,
                  makeTwoCommunityGraph)


class TestMetrics(unittest.TestCase):
    def testCentralizationStarIsOne(self):
        # A star is the maximally centralized graph by definition.
        self.assertAlmostEqual(
            DegreeCentralizationMetric().measure(nx.star_graph(6)), 1.0)

    def testCentralizationRingIsZero(self):
        # Everyone has degree 2: perfectly egalitarian.
        self.assertAlmostEqual(
            DegreeCentralizationMetric().measure(nx.cycle_graph(8)), 0.0)

    def testCentralizationTinyGraphIsZero(self):
        self.assertEqual(
            DegreeCentralizationMetric().measure(nx.path_graph(2)), 0.0)

    def testDensityCompleteGraphIsOne(self):
        self.assertAlmostEqual(DensityMetric().measure(nx.complete_graph(5)),
                               1.0)

    def testBridgeWidthExact(self):
        g, comm = makeTwoCommunityGraph(bridgeWidth=6, seed=0)
        self.assertEqual(BridgeWidthMetric(comm).measure(g), 6.0)

    def testCohesionDisconnectedIsZero(self):
        g = nx.Graph()
        g.add_edges_from([(0, 1), (2, 3)])  # two separate pairs
        self.assertEqual(CohesionMetric().measure(g), 0.0)

    def testCohesionDeterministic(self):
        # The seeded eigensolver must return the identical value twice
        # (the bug-2 regression test).
        g, _ = makeTwoCommunityGraph(seed=5)
        m = CohesionMetric()
        self.assertEqual(m.measure(g), m.measure(g))

    def testCohesionSeesThinBridge(self):
        # Same communities, thin vs wide bridge: algebraic connectivity
        # must rank the wide-bridge graph as more cohesive.
        gThin, _ = makeTwoCommunityGraph(bridgeWidth=1, seed=7)
        gWide, _ = makeTwoCommunityGraph(bridgeWidth=12, seed=7)
        m = CohesionMetric()
        self.assertLess(m.measure(gThin), m.measure(gWide))

    def testClusteringTriangleIsOne(self):
        self.assertAlmostEqual(
            ClusteringMetric().measure(nx.complete_graph(3)), 1.0)


if __name__ == "__main__":
    unittest.main()
