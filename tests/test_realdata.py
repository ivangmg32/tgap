'''
Tests for the real-data integration layer.

These tests use the CACHED downloads in realdata/data/ and skip cleanly if
they are absent, so the suite never depends on network access. Run
`python -m realdata.download` once to populate the cache.

They check implementation behaviour - that loading, preprocessing and
snapshot construction are correct, deterministic, leakage-safe, and produce
something TGAP can actually consume. They do NOT assert any scientific
conclusion about the real datasets: real data has no ground truth, so there
is nothing to assert against. In particular no test requires a finding such
as "concept X matters most" to hold.

The methodological properties under test, one class or method each:
  raw vs retained counts are both reported and consistent
  node selection in temporal mode uses only the selection period
  community detection in temporal mode uses only the selection period
  changing the future cannot change the selection
  descriptive mode is available, labelled, and genuinely different
  the edge-count invariant either holds or is reported infeasible
  bitcoin weights and signs are declared unused
'''

import os
import unittest

import networkx as nx

from core import (
    TgapExplainer, PersistenceTemporalModel, SlopeModel,
    BridgeWidthMetric, BridgeWidthTransformation,
    CentralizationTransformation, ChurnTransformation,
    BridgeTrendTransformation, DensityTransformation,
    CallCountingModel, edgeCountFeasibility,
)
from core.Communities import interCommunityEdges
from realdata import download
from realdata.adapters import base, decentraland, edgelist, tgbl_wiki
from realdata.adapters.base import (DESCRIPTIVE, SELECTION_FRACTION,
                                    TEMPORAL_EVALUATION, temporalSplit)


def cached(name):
    ''' Path of a cached raw file, or None when it has not been fetched. '''
    _, filename = download.SOURCES[name]
    path = os.path.join(download.DATA_DIR, filename)
    return path if os.path.exists(path) else None


class TestDownloadModule(unittest.TestCase):
    ''' The download layer itself, without touching the network. '''

    def testEverySourceHasUrlAndFilename(self):
        for name, (url, filename) in download.SOURCES.items():
            self.assertTrue(url.startswith("https://"), name)
            self.assertTrue(filename, name)

    def testRejectedDatasetsAreDocumentedWithReasons(self):
        ''' A dataset we chose not to use must carry a written reason, so
        the rejection is auditable rather than implicit. '''
        for name in ("tgbl-review", "tgbl-coin", "tgbl-flight"):
            self.assertIn(name, download.REJECTED)
            self.assertGreater(len(download.REJECTED[name]), 20)

    def testDigestIsStableForTheSameFile(self):
        path = cached("decentraland_votes")
        if not path:
            self.skipTest("decentraland votes.csv not downloaded")
        self.assertEqual(download.fileDigest(path), download.fileDigest(path))


class TestModeConstants(unittest.TestCase):
    ''' The two analysis modes must be named in exactly one place. '''

    def testModesAreDeclaredAndValidated(self):
        self.assertEqual(base.ANALYSIS_MODES,
                         (TEMPORAL_EVALUATION, DESCRIPTIVE))
        self.assertEqual(base.checkMode(TEMPORAL_EVALUATION),
                         TEMPORAL_EVALUATION)
        with self.assertRaises(ValueError):
            base.checkMode("temporal")           # a plausible typo

    def testSelectionFractionIsAFixedDocumentedConstant(self):
        self.assertGreater(SELECTION_FRACTION, 0.0)
        self.assertLess(SELECTION_FRACTION, 1.0)

    def testTemporalSplitIsDeterministicAndOrdered(self):
        times = [0.0, 10.0, 50.0, 100.0]
        first = temporalSplit(times, 0.2)
        self.assertEqual(first, temporalSplit(list(reversed(times)), 0.2))
        tMin, cut, tMax = first
        self.assertEqual((tMin, cut, tMax), (0.0, 20.0, 100.0))


class TestTemporalNodeSelection(unittest.TestCase):
    ''' Test B and D: node selection must see only the selection period, and
    changing the future must not change who is selected.

    Built on a hand-made event stream so the leakage is unambiguous: two
    actors dominate EARLY, two different actors dominate LATE and are more
    active overall. A full-period ranking therefore picks the late pair
    (that is the leak); a selection-period ranking picks the early pair.
    '''

    config = {"nodeSelection": "top_active", "topN": 2}

    def setUp(self):
        early = [("a", "b", float(t)) for t in range(10)]          # t 0..9
        late = [("x", "y", float(t)) for t in range(50, 90)]       # t 50..89
        self.events = early + late

    def split(self, events):
        tMin, cut, tMax = temporalSplit([t for _, _, t in events],
                                        SELECTION_FRACTION)
        return ([e for e in events if e[2] <= cut],
                [e for e in events if e[2] > cut])

    def testFullPeriodRankingWouldLeakTheFuture(self):
        ''' The behaviour being fixed, stated as a test so the difference is
        visible rather than asserted in prose. '''
        keep, _, _, _ = edgelist.selectNodes(self.config, self.events)
        self.assertEqual(keep, {"x", "y"})

    def testSelectionPeriodRankingPicksOnlyEarlyActors(self):
        selection, _ = self.split(self.events)
        keep, _, _, mode = edgelist.selectNodes(self.config, selection)
        self.assertEqual(keep, {"a", "b"})
        self.assertEqual(mode, "top_active")

    def testChangingTheFutureCannotChangeTheSelection(self):
        ''' The decisive leakage test: replace every post-cut event with
        events among completely different actors. A leakage-safe selection
        must return the identical node set. '''
        selection, evaluation = self.split(self.events)
        baseline, _, _, _ = edgelist.selectNodes(self.config, selection)

        mutatedFuture = [(f"new{i}", f"new{i+1}", t)
                         for i, (_, _, t) in enumerate(evaluation)]
        mutated = selection + mutatedFuture
        mutatedSelection, _ = self.split(mutated)
        after, _, _, _ = edgelist.selectNodes(self.config, mutatedSelection)

        self.assertEqual(baseline, after)
        # And the control: the full-period ranking DOES change, which is
        # what makes the previous assertion meaningful.
        leaky, _, _, _ = edgelist.selectNodes(self.config, mutated)
        self.assertNotEqual(leaky, edgelist.selectNodes(
            self.config, self.events)[0])

    def testRankingIsDeterministicUnderReordering(self):
        shuffled = list(reversed(self.events))
        self.assertEqual(edgelist.selectNodes(self.config, self.events)[0],
                         edgelist.selectNodes(self.config, shuffled)[0])


class TestTrainingPeriodCommunityDetection(unittest.TestCase):
    ''' Test C: in temporal mode the partition must come from the selection
    period, not from the evaluation snapshots.

    The two periods are built to DISAGREE: the training graph splits
    {0,1,2} from {3,4,5}, while the evaluation snapshots connect the nodes
    the other way round. Whichever partition comes back therefore names its
    own source.
    '''

    def setUp(self):
        self.nodes = set(range(6))

        def graph(edges):
            g = nx.Graph()
            g.add_nodes_from(sorted(self.nodes))
            g.add_edges_from(edges)
            return g

        # Training: two clear triangles, {0,1,2} and {3,4,5}.
        self.training = [graph([(0, 1), (1, 2), (0, 2),
                                (3, 4), (4, 5), (3, 5)])]
        # Evaluation: the opposite grouping, {0,3}, {1,4}, {2,5} chained.
        self.evaluation = [graph([(0, 3), (3, 1), (1, 4), (4, 2), (2, 5)])]

    def testTemporalModeDetectsOnTheTrainingGraph(self):
        communities, graph, report = base.fixedPartitionWithReport(
            self.evaluation, TEMPORAL_EVALUATION,
            trainingSnapshots=self.training, nodes=self.nodes)
        self.assertEqual(report["community_mode"], "temporal_train")
        self.assertEqual(sorted(report["partition_sizes"]), [3, 3])
        sides = {frozenset(communities[0]), frozenset(communities[1])}
        self.assertEqual(sides, {frozenset({0, 1, 2}), frozenset({3, 4, 5})})
        # The partition graph is the TRAINING union, not the evaluation one.
        self.assertEqual(graph.number_of_edges(),
                         self.training[0].number_of_edges())

    def testDescriptiveModeDetectsOnTheFullPeriod(self):
        communities, graph, report = base.fixedPartitionWithReport(
            self.evaluation, DESCRIPTIVE, nodes=self.nodes)
        self.assertEqual(report["community_mode"], "full_period_descriptive")
        self.assertEqual(graph.number_of_edges(),
                         self.evaluation[0].number_of_edges())
        sides = {frozenset(communities[0]), frozenset(communities[1])}
        self.assertNotEqual(sides,
                            {frozenset({0, 1, 2}), frozenset({3, 4, 5})})

    def testTemporalModeRefusesToGuessWithoutATrainingPeriod(self):
        with self.assertRaises(ValueError):
            base.fixedPartitionWithReport(self.evaluation,
                                          TEMPORAL_EVALUATION)

    def testEveryNodeGetsExactlyOneSideIncludingIsolatedOnes(self):
        ''' A node with no edge in the selection period still needs a side,
        because interCommunityEdges requires full coverage. How many such
        nodes there were must be reported, not hidden. '''
        lonely = nx.Graph()
        lonely.add_nodes_from(sorted(self.nodes | {99}))
        lonely.add_edges_from([(0, 1), (1, 2)])
        communities, _, report = base.fixedPartitionWithReport(
            self.evaluation, TEMPORAL_EVALUATION,
            trainingSnapshots=[lonely], nodes=self.nodes | {99})
        setA, setB = communities
        self.assertEqual(setA | setB, self.nodes | {99})
        self.assertEqual(setA & setB, set())
        self.assertGreater(report["nodes_isolated_in_partition_graph"], 0)


class TestRetentionSummary(unittest.TestCase):
    ''' Test A, at unit level: the raw-vs-retained block must be arithmetic,
    not narrative. '''

    def testPercentagesAndDropsAreConsistent(self):
        report = base.retentionSummary(986, 201, 332334, 16643)
        self.assertEqual(report["raw_nodes"], 986)
        self.assertEqual(report["retained_nodes"], 201)
        self.assertEqual(report["nodes_dropped"], 785)
        self.assertAlmostEqual(report["nodes_retained_pct"], 20.39, places=2)
        self.assertEqual(report["events_dropped"], 332334 - 16643)
        self.assertAlmostEqual(report["events_retained_pct"] +
                               report["events_dropped_pct"], 100.0, places=1)

    def testEmptyDatasetDoesNotDivideByZero(self):
        report = base.retentionSummary(0, 0, 0, 0)
        self.assertEqual(report["nodes_retained_pct"], 0.0)
        self.assertEqual(report["events_retained_pct"], 0.0)


class TestProjection(unittest.TestCase):
    ''' The shared preprocessing, on a hand-built event stream where the
    correct answer is obvious. '''

    def setUp(self):
        # Two windows. Window 0: actors a,b share item X; c is alone on Y.
        # Window 1: a,b,c all share item Z (a triangle).
        self.events = [
            {"actor": "a", "item": "X", "w": 0},
            {"actor": "b", "item": "X", "w": 0},
            {"actor": "c", "item": "Y", "w": 0},
            {"actor": "a", "item": "Z", "w": 1},
            {"actor": "b", "item": "Z", "w": 1},
            {"actor": "c", "item": "Z", "w": 1},
        ]
        self.keep = {"a", "b", "c"}

    def project(self):
        return base.projectCoActivity(self.events, "actor", "item", "w",
                                      self.keep)

    def testSnapshotCountEqualsWindowCount(self):
        snapshots, windows = self.project()
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(windows, [0, 1])

    def testEdgesAreTheCoActivityPairs(self):
        snapshots, _ = self.project()
        self.assertEqual(set(map(frozenset, snapshots[0].edges())),
                         {frozenset(("a", "b"))})
        self.assertEqual(set(map(frozenset, snapshots[1].edges())),
                         {frozenset(("a", "b")), frozenset(("a", "c")),
                          frozenset(("b", "c"))})

    def testNodeSetIsFixedAndIncludesInactiveActors(self):
        ''' DECISION 2: every snapshot carries every kept actor, isolated
        when inactive. TGAP's anchor rule needs this. '''
        snapshots, _ = self.project()
        for graph in snapshots:
            self.assertEqual(set(graph.nodes()), self.keep)
        self.assertEqual(snapshots[0].degree("c"), 0)  # c is isolated there

    def testActorsOutsideKeepSetAreDropped(self):
        self.events.append({"actor": "zzz", "item": "X", "w": 0})
        snapshots, _ = self.project()
        for graph in snapshots:
            self.assertNotIn("zzz", graph.nodes())

    def testRepeatedInteractionsDoNotDuplicateEdges(self):
        self.events.extend([{"actor": "a", "item": "X", "w": 0},
                            {"actor": "b", "item": "X", "w": 0}])
        snapshots, _ = self.project()
        self.assertEqual(snapshots[0].number_of_edges(), 1)

    def testProjectionIsDeterministic(self):
        first, _ = self.project()
        second, _ = self.project()
        for a, b in zip(first, second):
            self.assertEqual(set(map(frozenset, a.edges())),
                             set(map(frozenset, b.edges())))

    def testPartitionCoversEveryNodeExactlyOnce(self):
        snapshots, _ = self.project()
        (setA, setB), aggregate = base.fixedPartitionFromAggregate(snapshots)
        self.assertEqual(setA | setB, set(snapshots[0].nodes()))
        self.assertEqual(setA & setB, set())
        self.assertEqual(set(aggregate.nodes()), set(snapshots[0].nodes()))

    def testSummaryNamesTheNodeColumnRetained(self):
        ''' The node column must never be a bare "nodes": these are the
        actors that survived selection, not the dataset's population. '''
        snapshots, windows = self.project()
        communities, _ = base.fixedPartitionFromAggregate(snapshots)
        frame = base.summariseSnapshots(snapshots, communities,
                                        [str(w) for w in windows])
        self.assertEqual(len(frame), len(snapshots))
        self.assertIn("retained_nodes", frame.columns)
        self.assertIn("active_retained_nodes", frame.columns)
        self.assertNotIn("nodes", frame.columns)
        for column in ("edges", "density", "bridge_width", "average_degree",
                       "connected_components"):
            self.assertIn(column, frame.columns)
        self.assertEqual(list(frame["edges"]), [1, 3])


class RealDatasetTestCase(unittest.TestCase):
    ''' Shared checks that any prepared real dataset must satisfy. Each
    adapter is prepared once per class because preprocessing streams a
    large file. '''

    prepared = None

    def assertTgapCompatible(self, prepared):
        ''' The contract TGAP relies on: a non-empty list of undirected
        networkx graphs over one fixed node set, plus a partition of that
        node set. '''
        self.assertGreater(len(prepared.snapshots), 1)
        nodes = set(prepared.snapshots[0].nodes())
        for graph in prepared.snapshots:
            self.assertIsInstance(graph, nx.Graph)
            self.assertFalse(graph.is_directed())
            self.assertEqual(set(graph.nodes()), nodes)
        setA, setB = prepared.communities
        self.assertEqual(setA | setB, nodes)
        self.assertEqual(setA & setB, set())
        self.assertEqual(len(prepared.labels), len(prepared.snapshots))

    def assertMetadataMatchesTheGraphs(self, prepared):
        self.assertEqual(prepared.meta["snapshot_count"],
                         len(prepared.snapshots))
        self.assertEqual(prepared.meta["retained_nodes"],
                         prepared.snapshots[0].number_of_nodes())
        self.assertFalse(prepared.meta["directed"])
        self.assertFalse(prepared.meta["weighted"])
        self.assertIn(prepared.meta["analysis_mode"], base.ANALYSIS_MODES)

    def assertRawAndRetainedAreBothReported(self, prepared):
        ''' Test A: nowhere may the retained subset stand in for the whole
        dataset. Both counts, and their ratio, must be present and
        consistent in metadata AND in the preprocessing summary. '''
        for block in (prepared.meta, prepared.preprocessing):
            for key in ("raw_nodes", "retained_nodes", "nodes_retained_pct",
                        "raw_events", "retained_events",
                        "events_retained_pct"):
                self.assertIn(key, block)
            self.assertGreaterEqual(block["raw_nodes"],
                                    block["retained_nodes"])
            self.assertGreaterEqual(block["raw_events"],
                                    block["retained_events"])
            self.assertAlmostEqual(
                block["nodes_retained_pct"],
                100.0 * block["retained_nodes"] / block["raw_nodes"],
                places=1)
        self.assertEqual(prepared.meta["retained_nodes"],
                         prepared.snapshots[0].number_of_nodes())

    def assertLeakageControlIsDocumented(self, prepared):
        ''' Test B/D at integration level: the report must name the periods,
        and in temporal mode must declare that no future information was
        used for selection. '''
        pre = prepared.preprocessing
        for key in ("analysis_mode", "node_selection_mode",
                    "selection_period", "evaluation_period",
                    "selection_fraction_of_span",
                    "events_in_selection_period",
                    "events_in_evaluation_period",
                    "pct_of_events_outside_selection_period",
                    "future_information_used_for_node_selection",
                    "community_mode"):
            self.assertIn(key, pre)
        if pre["analysis_mode"] == TEMPORAL_EVALUATION:
            self.assertFalse(pre["future_information_used_for_node_selection"])
            self.assertIn(pre["community_mode"],
                          ("temporal_train", "ground_truth_labels"))

    def assertFilteringIsDocumented(self, prepared):
        ''' Nothing may be discarded silently. '''
        pre = prepared.preprocessing
        for key in ("retained_events", "events_dropped",
                    "events_dropped_pct", "partition_sizes"):
            self.assertIn(key, pre)
        self.assertGreaterEqual(pre["events_dropped"], 0)
        self.assertEqual(sum(pre["partition_sizes"]),
                         prepared.snapshots[0].number_of_nodes())

    def assertEdgeAttributesDeclaredUnused(self, prepared):
        ''' Item 7, applied to every dataset rather than only bitcoin: what
        the source offers and what TGAP reads must both be stated. '''
        self.assertFalse(prepared.meta["edge_weight_used"])
        self.assertFalse(prepared.meta["edge_sign_used"])
        self.assertTrue(prepared.meta["edge_attributes_available"])
        self.assertIn("topology", prepared.meta["edge_attributes_note"])

    def assertTgapRuns(self, prepared):
        ''' TGAP must actually produce an explanation, with the documented
        model-call budget of 1 + 2K. '''
        transformations = [
            BridgeWidthTransformation(prepared.communities, seed=42),
            CentralizationTransformation(prepared.communities, seed=42),
        ]
        model = CallCountingModel(PersistenceTemporalModel(
            BridgeWidthMetric(prepared.communities)))
        explanation = TgapExplainer(model, transformations).explain(
            prepared.snapshots)
        self.assertEqual(len(explanation), 2 * len(transformations))
        self.assertEqual(model.calls, 1 + 2 * len(transformations))
        for value in explanation.values():
            self.assertFalse(value != value, "impact must not be NaN")

    def assertExpectedInvarianceHolds(self, prepared):
        ''' The expected invariance, on real data. This is a VERIFICATION of
        something that follows from the definitions - the temporal
        transformations return the last snapshot untouched and the
        persistence model reads only the last snapshot - not an empirical
        discovery. It is tested because an implementation slip would break
        it. '''
        model = PersistenceTemporalModel(
            BridgeWidthMetric(prepared.communities))
        explanation = TgapExplainer(model, [
            BridgeTrendTransformation(prepared.communities, seed=42),
            ChurnTransformation(prepared.communities, seed=42),
        ]).explain(prepared.snapshots)
        for label, value in explanation.items():
            self.assertEqual(value, 0.0, label)

    def assertEdgeCountInvariantHoldsOrIsReported(self, prepared):
        ''' The replacement for the old "the anchor usually holds" check.

        The node set must ALWAYS be preserved. The edge count must EITHER be
        preserved, OR the feasibility gate must report the setting as
        infeasible with a reason. Silent violation is the one outcome this
        test forbids.
        '''
        for name, transformation in (
                ("Bridge Width",
                 BridgeWidthTransformation(prepared.communities, seed=42)),
                ("Centralization",
                 CentralizationTransformation(prepared.communities, seed=42)),
                ("Bridge Trend",
                 BridgeTrendTransformation(prepared.communities, seed=42))):
            strict = type(transformation)(prepared.communities, seed=42,
                                          strict=True) \
                if name != "Centralization" else None
            for delta in (0.25, -0.25):
                report = edgeCountFeasibility(
                    prepared.snapshots, transformation, delta,
                    prepared.communities, strictTransformation=strict)
                transformed = transformation.transform(prepared.snapshots,
                                                       delta)
                for before, after in zip(prepared.snapshots, transformed):
                    self.assertEqual(set(after.nodes()), set(before.nodes()),
                                     "node set must always be preserved")
                if report["edge_count_before"] == report["edge_count_after"]:
                    continue
                self.assertFalse(
                    report["feasible"],
                    f"{name} at delta {delta} changed the edge count "
                    f"({report['edge_count_before']} -> "
                    f"{report['edge_count_after']}) but was not reported "
                    f"infeasible")
                self.assertTrue(report["reason"],
                                f"{name} at delta {delta} was reported "
                                f"infeasible without a reason")

    def assertPreparationIsDeterministic(self, prepareFunction):
        first = prepareFunction()
        second = prepareFunction()
        self.assertEqual(len(first.snapshots), len(second.snapshots))
        self.assertEqual(first.communities, second.communities)
        for a, b in zip(first.snapshots, second.snapshots):
            self.assertEqual(set(map(frozenset, a.edges())),
                             set(map(frozenset, b.edges())))

    def assertRetainedNodesAppearInTheSelectionPeriod(self, prepared):
        ''' A consequence of leakage-safe selection that can be checked
        without re-reading the source file: every retained actor must have
        been chosen by the selection period, so none of them can be a node
        that only exists later. Verified via the reported counts. '''
        pre = prepared.preprocessing
        if pre["analysis_mode"] != TEMPORAL_EVALUATION:
            return
        self.assertGreater(pre["events_in_selection_period"], 0)
        self.assertGreater(pre["events_in_evaluation_period"], 0)
        self.assertLessEqual(pre["retained_nodes_active_in_evaluation"],
                             pre["retained_nodes"])


class TestDecentraland(RealDatasetTestCase):
    @classmethod
    def setUpClass(cls):
        if not cached("decentraland_votes"):
            raise unittest.SkipTest("decentraland votes.csv not downloaded")
        cls.prepared = decentraland.prepare()

    def testTgapCompatible(self):
        self.assertTgapCompatible(self.prepared)

    def testMetadata(self):
        self.assertMetadataMatchesTheGraphs(self.prepared)
        self.assertEqual(self.prepared.meta["dataset"], "decentraland-dao")
        # Measured from the real file; a change here means the upstream
        # frozen snapshot is not the one this pipeline was built against.
        self.assertEqual(self.prepared.meta["raw_events"], 53533)
        self.assertEqual(self.prepared.meta["raw_nodes"], 4133)

    def testRawAndRetained(self):
        self.assertRawAndRetainedAreBothReported(self.prepared)

    def testLeakageControl(self):
        self.assertLeakageControlIsDocumented(self.prepared)
        self.assertRetainedNodesAppearInTheSelectionPeriod(self.prepared)

    def testFilteringDocumented(self):
        self.assertFilteringIsDocumented(self.prepared)

    def testEdgeAttributesDeclaredUnused(self):
        self.assertEdgeAttributesDeclaredUnused(self.prepared)

    def testSnapshotsAreMonthlyAndOrdered(self):
        labels = self.prepared.labels
        self.assertEqual(labels, sorted(labels))
        self.assertEqual(self.prepared.meta["snapshot_interval"],
                         "1 calendar month")

    def testBridgeWidthIsMeasurableAndNonTrivial(self):
        ''' The partition must actually separate something, otherwise the
        bridge-width concept would carry no information here. '''
        widths = [len(interCommunityEdges(g, self.prepared.communities))
                  for g in self.prepared.snapshots]
        self.assertGreater(max(widths), 0)
        self.assertGreater(len(set(widths)), 1)

    def testTgapRuns(self):
        self.assertTgapRuns(self.prepared)

    def testExpectedInvarianceHolds(self):
        self.assertExpectedInvarianceHolds(self.prepared)

    def testEdgeCountInvariant(self):
        self.assertEdgeCountInvariantHoldsOrIsReported(self.prepared)

    def testDeterministic(self):
        self.assertPreparationIsDeterministic(decentraland.prepare)


class TestTgblWiki(RealDatasetTestCase):
    @classmethod
    def setUpClass(cls):
        if not cached("tgbl_wiki"):
            raise unittest.SkipTest("tgbl-wiki archive not downloaded")
        cls.prepared = tgbl_wiki.prepare()

    def testTgapCompatible(self):
        self.assertTgapCompatible(self.prepared)

    def testMetadata(self):
        self.assertMetadataMatchesTheGraphs(self.prepared)
        self.assertEqual(self.prepared.meta["dataset"], "tgbl-wiki")
        # Measured from the real edge list.
        self.assertEqual(self.prepared.meta["raw_events"], 157474)
        self.assertEqual(self.prepared.meta["raw_unique_items"], 1000)
        self.assertAlmostEqual(self.prepared.meta["raw_span_days"], 31.0,
                               places=2)

    def testRawAndRetained(self):
        self.assertRawAndRetainedAreBothReported(self.prepared)

    def testLeakageControl(self):
        self.assertLeakageControlIsDocumented(self.prepared)
        self.assertRetainedNodesAppearInTheSelectionPeriod(self.prepared)

    def testFilteringDocumented(self):
        self.assertFilteringIsDocumented(self.prepared)

    def testEdgeAttributesDeclaredUnused(self):
        self.assertEdgeAttributesDeclaredUnused(self.prepared)

    def testHeaderIsValidated(self):
        ''' readEvents asserts the real header, so an upstream schema
        change fails loudly instead of producing a wrong graph. '''
        path = cached("tgbl_wiki")
        events = tgbl_wiki.readEvents(path)
        self.assertEqual(len(events), 157474)
        self.assertEqual(set(events[0]), {"user", "item", "time"})

    def testTgapRuns(self):
        self.assertTgapRuns(self.prepared)

    def testExpectedInvarianceHolds(self):
        self.assertExpectedInvarianceHolds(self.prepared)

    def testTrajectoryModelDoesReactToTrend(self):
        ''' The companion of the invariance check: a model that reads the
        trajectory must respond to a trajectory transformation. '''
        model = SlopeModel(BridgeWidthMetric(self.prepared.communities))
        explanation = TgapExplainer(model, [
            BridgeTrendTransformation(self.prepared.communities, seed=42)
        ]).explain(self.prepared.snapshots)
        self.assertTrue(any(v != 0.0 for v in explanation.values()),
                        explanation)

    def testEdgeCountInvariant(self):
        self.assertEdgeCountInvariantHoldsOrIsReported(self.prepared)

    def testDeterministic(self):
        self.assertPreparationIsDeterministic(tgbl_wiki.prepare)


class TestEdgeListAdapterConfig(unittest.TestCase):
    ''' The unipartite adapter's configuration, checked without loading
    any data. '''

    def testEveryDatasetIsFullyDocumented(self):
        for name, config in edgelist.DATASETS.items():
            for key in ("source_key", "format", "columns", "windowDays",
                        "nodeSelection", "description", "url_note",
                        "nodes_are", "edges_are", "unused_fields",
                        "edge_attributes_available"):
                self.assertIn(key, config, f"{name} missing {key}")
            self.assertIn(config["source_key"], download.SOURCES, name)

    def testBitcoinTimestampColumnIsThree(self):
        ''' Regression guard for a real bug caught during development: the
        SNAP bitcoin files are SOURCE,TARGET,RATING,TIME, so time is column
        3. Reading column 2 (as the other SNAP files use) silently yields a
        span of 0 days instead of ~1900. '''
        for name in ("bitcoin_otc", "bitcoin_alpha"):
            self.assertEqual(edgelist.DATASETS[name]["columns"][2], 3, name)

    def testBitcoinRatingIsDeclaredAvailableAndUnused(self):
        ''' Test K: the bitcoin datasets carry a signed trust rating. It is
        not used, and the configuration must say so in both places rather
        than leaving a reader to assume the graph is weighted. '''
        for name in ("bitcoin_otc", "bitcoin_alpha"):
            config = edgelist.DATASETS[name]
            self.assertIn("RATING", config["edge_attributes_available"])
            self.assertIn("RATING", config["unused_fields"])
            self.assertIn("-10..+10", config["edge_attributes_available"])

    def testCollegeMsgDuplicationIsRecorded(self):
        ''' tgbl-uci was verified to be the same data as SNAP's CollegeMsg.
        The rejection must stay documented so the pair is never presented
        as two independent datasets. '''
        self.assertIn("SNAP CollegeMsg", download.REJECTED)
        self.assertIn("tgbl-uci", download.REJECTED["SNAP CollegeMsg"])


class EdgeListDatasetMixin(RealDatasetTestCase):
    ''' Shared checks for every unipartite dataset. '''

    datasetName = None

    @classmethod
    def setUpClass(cls):
        if cls.datasetName is None:
            raise unittest.SkipTest("base class")
        config = edgelist.DATASETS[cls.datasetName]
        if not cached(config["source_key"]):
            raise unittest.SkipTest(f"{cls.datasetName} not downloaded")
        cls.prepared = edgelist.prepare(cls.datasetName)

    def testTgapCompatible(self):
        self.assertTgapCompatible(self.prepared)

    def testMetadata(self):
        self.assertMetadataMatchesTheGraphs(self.prepared)

    def testRawAndRetained(self):
        self.assertRawAndRetainedAreBothReported(self.prepared)

    def testLeakageControl(self):
        self.assertLeakageControlIsDocumented(self.prepared)
        self.assertRetainedNodesAppearInTheSelectionPeriod(self.prepared)

    def testFilteringDocumented(self):
        self.assertFilteringIsDocumented(self.prepared)

    def testEdgeAttributesDeclaredUnused(self):
        self.assertEdgeAttributesDeclaredUnused(self.prepared)

    def testSelectionUsedOnlyTheSelectionPeriodEvents(self):
        ''' Test B, against the real file: the retained node set must be
        exactly what a ranking over selection-period events alone produces.
        Recomputed here independently of the adapter's own bookkeeping. '''
        config = edgelist.DATASETS[self.datasetName]
        if config["nodeSelection"] != "top_active":
            self.skipTest("this dataset selects nodes from static labels")
        events, _ = edgelist.readEdgeList(config)
        _, cut, _ = temporalSplit([t for _, _, t in events],
                                  SELECTION_FRACTION)
        selection = [e for e in events if e[2] <= cut]
        expected, _, _, _ = edgelist.selectNodes(config, selection)
        self.assertEqual(set(self.prepared.snapshots[0].nodes()), expected)

    def testNoProjectionWasUsed(self):
        ''' The whole point of this family: edges are observed, not derived,
        so the preprocessing record must say so. '''
        self.assertEqual(self.prepared.preprocessing["projection"],
                         "none - edges are observed directly between actors")
        self.assertIn("unipartite", self.prepared.meta["graph_family"])

    def testNoSelfLoops(self):
        for graph in self.prepared.snapshots:
            self.assertEqual(list(nx.selfloop_edges(graph)), [])

    def testSpanIsPlausible(self):
        ''' A wrong timestamp column shows up immediately as an absurd
        span, which is how the bitcoin bug was found. '''
        self.assertGreater(self.prepared.meta["raw_span_days"], 1.0)

    def testEvaluatedSpanIsShorterThanRawSpan(self):
        ''' Test J, half of it: in temporal mode the evaluation period is a
        strict subset of the observation period. '''
        self.assertLess(self.prepared.meta["evaluated_span_days"],
                        self.prepared.meta["raw_span_days"])

    def testTgapRuns(self):
        self.assertTgapRuns(self.prepared)

    def testExpectedInvarianceHolds(self):
        self.assertExpectedInvarianceHolds(self.prepared)

    def testEdgeCountInvariant(self):
        self.assertEdgeCountInvariantHoldsOrIsReported(self.prepared)

    def testDeterministic(self):
        self.assertPreparationIsDeterministic(
            lambda: edgelist.prepare(self.datasetName))


class TestEmailEuCore(EdgeListDatasetMixin):
    datasetName = "email_eu_core"

    def testPartitionIsGroundTruthNotDetected(self):
        ''' The one dataset in the project whose communities are real
        organisational units rather than an algorithm's opinion. Department
        labels are a static attribute, so this partition carries no temporal
        leakage in either mode. '''
        self.assertIn("ground-truth",
                      self.prepared.preprocessing["partition_source"])
        self.assertEqual(self.prepared.preprocessing["community_mode"],
                         "ground_truth_labels")
        # The two largest departments, measured from the labels file.
        self.assertEqual(sorted(self.prepared.preprocessing[
            "partition_sizes"]), [92, 109])

    def testMeasuredRawFacts(self):
        self.assertEqual(self.prepared.meta["raw_events"], 332334)


class TestTgblEnron(EdgeListDatasetMixin):
    datasetName = "tgbl_enron"

    def testMeasuredRawFacts(self):
        self.assertEqual(self.prepared.meta["raw_events"], 125235)


class TestTgblUci(EdgeListDatasetMixin):
    datasetName = "tgbl_uci"

    def testMeasuredRawFacts(self):
        self.assertEqual(self.prepared.meta["raw_events"], 59835)


class TestSxMathoverflow(EdgeListDatasetMixin):
    datasetName = "sx_mathoverflow"

    def testMeasuredRawFacts(self):
        self.assertEqual(self.prepared.meta["raw_events"], 506550)


class TestBitcoinOtc(EdgeListDatasetMixin):
    datasetName = "bitcoin_otc"

    def testTimestampColumnGivesAMultiYearSpan(self):
        self.assertGreater(self.prepared.meta["raw_span_days"], 1000)

    def testMeasuredRawFacts(self):
        self.assertEqual(self.prepared.meta["raw_events"], 35592)

    def testWeightAndSignMetadataOnThePreparedDataset(self):
        ''' Test K at integration level: the prepared dataset itself, not
        only the config, must declare the rating unused. '''
        self.assertFalse(self.prepared.meta["edge_weight_used"])
        self.assertFalse(self.prepared.meta["edge_sign_used"])
        self.assertFalse(self.prepared.preprocessing["edge_weight_used"])
        self.assertFalse(self.prepared.preprocessing["edge_sign_used"])
        self.assertIn("RATING",
                      self.prepared.meta["edge_attributes_available"])
        for graph in self.prepared.snapshots:
            for _, _, data in graph.edges(data=True):
                self.assertEqual(data, {}, "edges must carry no attributes")


class TestBitcoinAlpha(EdgeListDatasetMixin):
    datasetName = "bitcoin_alpha"

    def testMeasuredRawFacts(self):
        self.assertEqual(self.prepared.meta["raw_events"], 24186)


class TestAnalysisModesDiffer(unittest.TestCase):
    ''' Test J: both modes must be available, clearly labelled, and actually
    different - otherwise the leakage fix would be cosmetic. One dataset is
    enough here; the per-dataset classes above already cover the default
    mode everywhere. '''

    @classmethod
    def setUpClass(cls):
        if not cached("bitcoin_alpha"):
            raise unittest.SkipTest("bitcoin_alpha not downloaded")
        cls.temporal = edgelist.prepare("bitcoin_alpha",
                                        mode=TEMPORAL_EVALUATION)
        cls.descriptive = edgelist.prepare("bitcoin_alpha", mode=DESCRIPTIVE)

    def testBothModesAreLabelled(self):
        self.assertEqual(self.temporal.meta["analysis_mode"],
                         TEMPORAL_EVALUATION)
        self.assertEqual(self.descriptive.meta["analysis_mode"], DESCRIPTIVE)
        self.assertEqual(self.temporal.preprocessing["analysis_mode"],
                         TEMPORAL_EVALUATION)
        self.assertEqual(self.descriptive.preprocessing["analysis_mode"],
                         DESCRIPTIVE)

    def testOnlyDescriptiveModeUsesFutureInformation(self):
        self.assertFalse(self.temporal.preprocessing[
            "future_information_used_for_node_selection"])
        self.assertTrue(self.descriptive.preprocessing[
            "future_information_used_for_node_selection"])

    def testCommunityModeFollowsTheAnalysisMode(self):
        self.assertEqual(self.temporal.preprocessing["community_mode"],
                         "temporal_train")
        self.assertEqual(self.descriptive.preprocessing["community_mode"],
                         "full_period_descriptive")

    def testDescriptiveModeCoversTheWholeSpan(self):
        self.assertAlmostEqual(self.descriptive.meta["evaluated_span_days"],
                               self.descriptive.meta["raw_span_days"],
                               places=3)
        self.assertLess(self.temporal.meta["evaluated_span_days"],
                        self.temporal.meta["raw_span_days"])

    def testTheTwoModesProduceDifferentGraphs(self):
        ''' If they were identical the leakage-safe mode would be doing
        nothing. Reported so the size of the difference is visible. '''
        self.assertNotEqual(len(self.temporal.snapshots),
                            len(self.descriptive.snapshots))
        self.assertNotEqual(self.temporal.meta["retained_events"],
                            self.descriptive.meta["retained_events"])

    def testRawFactsAreIdenticalInBothModes(self):
        ''' The mode changes what is RETAINED, never what the source file
        contains. '''
        for key in ("raw_nodes", "raw_events", "raw_span_days"):
            self.assertEqual(self.temporal.meta[key],
                             self.descriptive.meta[key], key)


class TestDensityTransformationOnRealGraphs(unittest.TestCase):
    ''' Density is the one transformation that is allowed to change the
    edge count, so it gets its own check on a real graph. '''

    def testConfinedDensityPreservesBridgeWidth(self):
        if not cached("decentraland_votes"):
            self.skipTest("decentraland votes.csv not downloaded")
        prepared = decentraland.prepare()
        transformation = DensityTransformation(prepared.communities, seed=42)
        transformed = transformation.transform(prepared.snapshots, 0.2)
        for before, after in zip(prepared.snapshots, transformed):
            self.assertEqual(
                len(interCommunityEdges(after, prepared.communities)),
                len(interCommunityEdges(before, prepared.communities)))


if __name__ == "__main__":
    unittest.main()
