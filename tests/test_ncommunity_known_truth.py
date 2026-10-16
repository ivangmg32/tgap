'''
N-community KNOWN-TRUTH tests (design section 33).

Real data has no ground truth, so a wrong implementation there looks like an
interesting finding. Here the bridge between every community pair is placed
by construction, so every expectation below is an exact equality rather than
a tolerance - and a regression shows up as a failure, not as a plausible
number.

Three things are checked:

  1. the generators really produce the bridge structure they claim;
  2. TGAP recovers the truth on an N-community world - a model reading one
     pair's bridge must respond to that pair and be EXACTLY blind to the
     others;
  3. the two-community case still reproduces legacy behaviour.
'''

import unittest

import numpy as np

from core import (
    BridgeWidthMetric, BridgeWidthTransformation, PersistenceTemporalModel,
    SlopeModel, TgapExplainer, TrendTemporalModel,
)
from core.Communities import aggregateBridgeWidth, bridgeMatrix
from core.SyntheticData import (
    makeNCommunityGraph, makeNCommunityTemporalGraph, makeTemporalGraph,
)


class TestGeneratorTruth(unittest.TestCase):
    ''' The generator must deliver exactly the world it was asked for,
    otherwise every "known truth" below is built on sand. '''

    def testExactBridgeWidthsPerPair(self):
        wanted = {(0, 1): 10, (0, 2): 4, (1, 2): 7}
        graph, partition = makeNCommunityGraph(
            nCommunities=3, nPerCommunity=8, bridgeWidths=wanted, seed=1)
        self.assertEqual(bridgeMatrix(graph, partition), wanted)

    def testAggregateIsTheSumOfTheTruth(self):
        wanted = {(0, 1): 10, (0, 2): 4, (1, 2): 7}
        graph, partition = makeNCommunityGraph(
            nCommunities=3, nPerCommunity=8, bridgeWidths=wanted, seed=1)
        self.assertEqual(aggregateBridgeWidth(graph, partition), 21.0)

    def testDefaultAppliesToUnnamedPairs(self):
        graph, partition = makeNCommunityGraph(
            nCommunities=4, nPerCommunity=6,
            bridgeWidths={(0, 1): 9, "default": 2}, seed=1)
        matrix = bridgeMatrix(graph, partition)
        self.assertEqual(matrix[(0, 1)], 9)
        for pair in partition.pairs():
            if pair != (0, 1):
                self.assertEqual(matrix[pair], 2, f"pair {pair}")

    def testDriftProducesAnExactSlope(self):
        snapshots, partition = makeNCommunityTemporalGraph(
            nSnapshots=5, nCommunities=3, nPerCommunity=8,
            bridgeWidths={(0, 1): 5, "default": 3},
            bridgeDrift={(0, 1): 2}, seed=1)
        drifting = [bridgeMatrix(g, partition)[(0, 1)] for g in snapshots]
        steady = [bridgeMatrix(g, partition)[(0, 2)] for g in snapshots]
        self.assertEqual(drifting, [5, 7, 9, 11, 13])
        self.assertEqual(steady, [3, 3, 3, 3, 3])
        slope = np.polyfit(np.arange(len(drifting)), drifting, 1)[0]
        self.assertAlmostEqual(slope, 2.0, places=9)

    def testGeneratorIsDeterministic(self):
        first, _ = makeNCommunityGraph(3, 8, bridgeWidths={"default": 5},
                                       seed=7)
        second, _ = makeNCommunityGraph(3, 8, bridgeWidths={"default": 5},
                                        seed=7)
        self.assertEqual(sorted(map(sorted, first.edges())),
                         sorted(map(sorted, second.edges())))

    def testImpossibleBridgeIsRejected(self):
        ''' Asking for more edges than the pair can hold must fail loudly,
        not silently deliver fewer and quietly invalidate the truth. '''
        with self.assertRaises(ValueError):
            makeNCommunityGraph(nCommunities=2, nPerCommunity=3,
                                bridgeWidths={(0, 1): 100})

    def testSingleCommunityHasNoBridges(self):
        graph, partition = makeNCommunityGraph(nCommunities=1,
                                               nPerCommunity=10, seed=1)
        self.assertEqual(partition.pairs(), [])
        self.assertEqual(aggregateBridgeWidth(graph, partition), 0.0)


class TestTgapRecoversNCommunityTruth(unittest.TestCase):
    ''' The scientific test: on a world whose answer we built, does TGAP
    report it? '''

    def setUp(self):
        # Three communities. Only the A-B bridge is wide; a model that reads
        # A-B must react to A-B and to nothing else.
        self.snapshots, self.partition = makeNCommunityTemporalGraph(
            nSnapshots=6, nCommunities=3, nPerCommunity=10,
            bridgeWidths={(0, 1): 20, (0, 2): 6, (1, 2): 6}, seed=3)

    def testPersistenceModelRecoversItsOwnPairAndIsBlindToOthers(self):
        ''' The N-community analogue of the two-community concept-selectivity
        result: exact zeros, not small numbers. '''
        model = PersistenceTemporalModel(
            BridgeWidthMetric(self.partition, communityPair=(0, 1)))
        transformations = [
            BridgeWidthTransformation(self.partition, seed=42,
                                      communityPair=pair)
            for pair in self.partition.pairs()]
        explanation = TgapExplainer(model, transformations).explain(
            self.snapshots)

        own = [v for label, v in explanation.items() if "0-1" in label]
        others = [v for label, v in explanation.items() if "0-1" not in label]
        self.assertTrue(all(abs(v) > 0 for v in own),
                        f"model did not react to its own pair: {own}")
        for value in others:
            self.assertEqual(value, 0.0,
                             f"model reacted to a pair it cannot see: "
                             f"{explanation}")

    def testEachPairIsRecoveredByItsOwnModel(self):
        ''' Every pair in turn: N models, N concepts, a clean diagonal. '''
        for pair in self.partition.pairs():
            model = PersistenceTemporalModel(
                BridgeWidthMetric(self.partition, communityPair=pair))
            explanation = TgapExplainer(model, [
                BridgeWidthTransformation(self.partition, seed=42,
                                          communityPair=other)
                for other in self.partition.pairs()
            ]).explain(self.snapshots)
            tag = f"{pair[0]}-{pair[1]}"
            for label, value in explanation.items():
                if tag in label:
                    self.assertNotEqual(value, 0.0,
                                        f"{tag} model blind to {tag}")
                else:
                    self.assertEqual(value, 0.0,
                                     f"{tag} model reacted to {label}")

    def testAggregateModelRespondsToEveryPair(self):
        ''' The complement: a model reading the AGGREGATE bridge must react
        to a change in ANY pair, because every pair contributes to the sum. '''
        model = PersistenceTemporalModel(BridgeWidthMetric(self.partition))
        for pair in self.partition.pairs():
            explanation = TgapExplainer(model, [
                BridgeWidthTransformation(self.partition, seed=42,
                                          communityPair=pair)
            ]).explain(self.snapshots)
            self.assertTrue(any(v != 0.0 for v in explanation.values()),
                            f"aggregate model blind to pair {pair}")

    def testSlopeModelRecoversAKnownPairwiseTrend(self):
        ''' A known trajectory, not just a known level. The A-B bridge grows
        by exactly 2 per snapshot; the slope model's baseline must BE that
        slope. '''
        snapshots, partition = makeNCommunityTemporalGraph(
            nSnapshots=6, nCommunities=3, nPerCommunity=10,
            bridgeWidths={(0, 1): 6, "default": 5},
            bridgeDrift={(0, 1): 3}, seed=5)
        model = SlopeModel(BridgeWidthMetric(partition, communityPair=(0, 1)))
        self.assertAlmostEqual(model.predict(snapshots), 3.0, places=9)
        steady = SlopeModel(BridgeWidthMetric(partition, communityPair=(0, 2)))
        self.assertAlmostEqual(steady.predict(snapshots), 0.0, places=9)

    def testPairTransformationDoesNotDisturbOtherPairs(self):
        ''' The confounder control, at N communities: changing A-B must leave
        the A-C and B-C bridges EXACTLY as they were. '''
        before = bridgeMatrix(self.snapshots[0], self.partition)
        transformation = BridgeWidthTransformation(
            self.partition, seed=42, communityPair=(0, 1))
        for delta in (0.5, -0.5):
            after = bridgeMatrix(
                transformation.transform(self.snapshots, delta)[0],
                self.partition)
            self.assertNotEqual(after[(0, 1)], before[(0, 1)])
            self.assertEqual(after[(0, 2)], before[(0, 2)])
            self.assertEqual(after[(1, 2)], before[(1, 2)])


class TestTwoCommunityStillMatchesLegacy(unittest.TestCase):
    ''' Section 12 again, from the synthetic side: the N-community machinery
    must not have changed what the two-community generators produce. '''

    def testLegacyGeneratorUnchangedAndConsistent(self):
        snapshots, communities = makeTemporalGraph(
            nSnapshots=5, nPerCommunity=10, bridgeWidth=8, seed=1)
        setA, setB = communities                 # legacy unpacking
        self.assertEqual(len(setA) + len(setB),
                         snapshots[0].number_of_nodes())
        for graph in snapshots:
            matrix = bridgeMatrix(graph, communities)
            self.assertEqual(len(matrix), 1)     # one pair only
            self.assertEqual(aggregateBridgeWidth(graph, communities),
                             float(matrix[(0, 1)]))

    def testTwoCommunityKnownTruthViaTheNGenerator(self):
        ''' The N-generator with N=2 must behave like the legacy world. '''
        graph, partition = makeNCommunityGraph(
            nCommunities=2, nPerCommunity=12,
            bridgeWidths={(0, 1): 9}, seed=1)
        self.assertEqual(len(partition), 2)
        self.assertEqual(aggregateBridgeWidth(graph, partition), 9.0)
        self.assertEqual(BridgeWidthMetric(partition).measure(graph), 9.0)
        self.assertEqual(
            BridgeWidthMetric(partition, communityPair=(0, 1)).measure(graph),
            9.0)


if __name__ == "__main__":
    unittest.main()
