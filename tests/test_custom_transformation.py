'''
Tests for the PUBLIC EXTENSIBILITY CLAIM.

TGAP's architectural promise is that a researcher can add a new graph
concept without touching the core. A promise that is only stated in a README
rots; these tests assert it mechanically:

  * a transformation defined entirely OUTSIDE core/ is accepted by the
    explainer and produces a complete explanation record;
  * the explainer contains no per-transformation special casing, verified by
    reading its source rather than by trusting the design;
  * the shipped example in examples/MyCustomTransformation.py actually runs.

If someone later adds `if transformation.name == ...` to the explainer, the
source-inspection test below fails.
'''

import inspect
import unittest

import networkx as nx

from core import (
    BridgeWidthMetric, GraphExplainer, PersistenceTemporalModel,
    TemporalGraphTransformation, TgapExplainer, TrendTemporalModel,
)
from core.GraphExplainer import ExplainerBase
from core.GraphMetric import DensityMetric
from examples.MyCustomTransformation import IsolationTransformation


class TriangleCountTransformation(TemporalGraphTransformation):
    ''' A second custom concept, defined here in the test file and nowhere
    else, to prove the explainer needs no advance knowledge of it.

    Concept: how many closed triangles the graph contains. Increasing it
    closes open wedges; decreasing it opens closed ones. '''

    name = "Triangle Count"
    preservesEdgeCount = False

    def propertyValue(self, x):
        snapshots = x if isinstance(x, list) else [x]
        counts = [sum(nx.triangles(g).values()) / 3 for g in snapshots]
        return float(sum(counts)) / len(counts)

    def transformGraph(self, graph, delta):
        g = graph.copy()
        if delta > 0:
            # Close open wedges, deterministically, most-connected first.
            wedges = sorted(
                (u, w) for v in sorted(g.nodes())
                for u in sorted(g.neighbors(v)) for w in sorted(g.neighbors(v))
                if u < w and not g.has_edge(u, w))
            wanted = round(len(wedges) * min(delta, 1.0))
            g.add_edges_from(wedges[:wanted])
        elif delta < 0:
            closing = sorted(
                (u, v) for u, v in sorted(g.edges())
                if set(g.neighbors(u)) & set(g.neighbors(v)))
            wanted = round(len(closing) * min(-delta, 1.0))
            g.remove_edges_from(closing[:wanted])
        return g


def sampleTemporalGraph():
    ''' Two loosely joined clusters over four snapshots, with enough slack
    that a custom transformation can actually move something. '''
    snapshots = []
    for step in range(4):
        graph = nx.Graph()
        graph.add_nodes_from(range(12))
        graph.add_edges_from([(i, j) for i in range(6) for j in range(6)
                              if i < j and (i + j + step) % 3])
        graph.add_edges_from([(i, j) for i in range(6, 12)
                              for j in range(6, 12)
                              if i < j and (i + j + step) % 3])
        graph.add_edges_from([(0, 6), (1, 7), (2, 8)])
        snapshots.append(graph)
    return snapshots


class TestCustomTransformationIsAccepted(unittest.TestCase):
    ''' The core requirement of sections 1, 4 and 37. '''

    def setUp(self):
        self.snapshots = sampleTemporalGraph()
        self.model = TrendTemporalModel(DensityMetric())

    def testExplainerAcceptsATransformationDefinedInThisFile(self):
        explainer = TgapExplainer(self.model, [TriangleCountTransformation()])
        explanation = explainer.explain(self.snapshots)
        self.assertEqual(len(explanation), 2)          # one per direction
        for label, value in explanation.items():
            self.assertIn("Triangle Count", label)
            self.assertFalse(value != value, f"{label} is NaN")

    def testCustomAndBuiltInTransformationsMixFreely(self):
        from core import BridgeWidthTransformation, detectTwoCommunities
        communities = detectTwoCommunities(self.snapshots[-1])
        explainer = TgapExplainer(self.model, [
            BridgeWidthTransformation(communities, seed=42),
            TriangleCountTransformation(),
            IsolationTransformation(seed=42),
        ])
        explanation = explainer.explain(self.snapshots)
        self.assertEqual(len(explanation), 6)

    def testCustomTransformationGetsFullProvenance(self):
        ''' A custom concept must receive the SAME record structure as a
        built-in one - otherwise downstream tables and figures would have to
        special-case it, which is the very thing we are avoiding. '''
        explainer = TgapExplainer(self.model, [TriangleCountTransformation()])
        for record in explainer.explainDetailed(self.snapshots):
            for field in ("label", "transformation", "requestedDelta",
                          "achievedDelta", "deltaMode", "baseline",
                          "transformed", "impact", "normalizer", "noop",
                          "leakage"):
                self.assertIn(field, record)
            self.assertEqual(record["transformation"], "Triangle Count")

    def testModelCallBudgetIsUnchangedByCustomTransformations(self):
        ''' The documented 1 + 2K budget must hold whoever wrote the K
        transformations. '''
        from core import CallCountingModel
        counter = CallCountingModel(self.model)
        transformations = [TriangleCountTransformation(),
                           IsolationTransformation(seed=42)]
        TgapExplainer(counter, transformations).explain(self.snapshots)
        self.assertEqual(counter.calls, 1 + 2 * len(transformations))

    def testStaticExplainerAlsoAcceptsCustomTransformations(self):
        ''' The non-temporal explainer shares the same contract. '''
        explainer = GraphExplainer(
            type("M", (), {"predict": staticmethod(
                lambda g: float(g.number_of_edges()))})(),
            [TriangleCountTransformation()])
        explanation = explainer.explain(self.snapshots[-1])
        self.assertEqual(len(explanation), 2)

    def testDeterministic(self):
        explainer = TgapExplainer(self.model, [IsolationTransformation(seed=7)])
        first = explainer.explain(self.snapshots)
        second = explainer.explain(self.snapshots)
        self.assertEqual(first, second)

    def testTransformationNeverMutatesTheInput(self):
        ''' The explainer computes the baseline from the original graphs, so
        a mutating transformation would silently corrupt every result. '''
        before = [set(map(frozenset, g.edges())) for g in self.snapshots]
        for transformation in (TriangleCountTransformation(),
                               IsolationTransformation(seed=42)):
            transformation.transform(self.snapshots, 0.5)
        after = [set(map(frozenset, g.edges())) for g in self.snapshots]
        self.assertEqual(before, after)


class TestExplainerHasNoTransformationSpecialCasing(unittest.TestCase):
    ''' Section 5: no hard-coded transformation list in the explainer.

    Asserted by inspecting the shipped source, so the guarantee cannot decay
    silently as the file is edited. '''

    def testExplainerSourceNamesNoConcreteTransformation(self):
        source = inspect.getsource(ExplainerBase)
        for concrete in ("BridgeWidthTransformation",
                         "CentralizationTransformation",
                         "DensityTransformation", "ChurnTransformation",
                         "BridgeTrendTransformation"):
            # The lazy default-building helper is the ONE permitted mention,
            # and it lives in _resolveTransformations; it never dispatches on
            # a transformation's identity.
            occurrences = source.count(concrete)
            inDefaults = inspect.getsource(
                ExplainerBase._resolveTransformations).count(concrete)
            self.assertEqual(
                occurrences, inDefaults,
                f"{concrete} is named in the explainer outside the default "
                f"builder - that is per-transformation special casing")

    def testExplainerUsesOnlyTheDocumentedContract(self):
        ''' Everything the explainer asks of a transformation must be part
        of the published interface, or custom classes will fail. '''
        source = inspect.getsource(ExplainerBase)
        contract = {"name", "propertyValue", "deltaMode", "transform",
                    "transformGraph"}
        used = {attribute for attribute in
                ("name", "propertyValue", "deltaMode", "transform",
                 "transformGraph", "communities", "seed", "strict")
                if f"trans.{attribute}" in source}
        self.assertTrue(used <= contract,
                        f"explainer reaches past the contract: {used - contract}")


class TestShippedExample(unittest.TestCase):
    ''' The public example must actually run - documentation that does not
    execute is worse than none. '''

    def testExampleRunsEndToEnd(self):
        from examples import MyCustomTransformation
        MyCustomTransformation.main()

    def testIsolationMeasuresWhatItClaims(self):
        graph = nx.Graph()
        graph.add_nodes_from(range(5))
        graph.add_edge(0, 1)
        self.assertEqual(IsolationTransformation().propertyValue([graph]), 3.0)

    def testIsolationDeclaresItDoesNotPreserveEdgeCount(self):
        ''' The most common mistake when writing a transformation: the
        feasibility gate would otherwise flag every run as a violation. '''
        from core import declaresEdgeCountPreservation
        self.assertFalse(
            declaresEdgeCountPreservation(IsolationTransformation()))

    def testIsolationMovesItsOwnPropertyInBothDirections(self):
        ''' The fixture must already contain isolated actors - see the
        zero-property test below for why. '''
        snapshots = sampleTemporalGraph()
        for index, graph in enumerate(snapshots):
            graph.remove_edges_from(list(graph.edges(index)))
        transformation = IsolationTransformation(seed=42)
        before = transformation.propertyValue(snapshots)
        self.assertGreater(before, 0.0, "fixture has no isolated actors")
        more = transformation.propertyValue(
            transformation.transform(snapshots, 1.0))
        fewer = transformation.propertyValue(
            transformation.transform(snapshots, -1.0))
        self.assertGreater(more, before)
        self.assertLess(fewer, before)

    def testIsolationCannotGrowFromZero(self):
        ''' A documented limitation of ANY relative-delta transformation,
        worth pinning here because the example is what researchers copy.

        The target is round(current * (1 + delta)). When the property is 0
        the target is 0 for every delta, so the transformation is a no-op
        and TGAP reports achievedDelta 0 with noop=True. This is the same
        family as the discreteness floor: a relative change of a quantity
        that is zero is not defined, and the honest response is to report
        that nothing moved rather than to invent a starting value. '''
        snapshots = sampleTemporalGraph()      # fully connected: no isolates
        transformation = IsolationTransformation(seed=42)
        self.assertEqual(transformation.propertyValue(snapshots), 0.0)
        after = transformation.transform(snapshots, 1.0)
        self.assertEqual(transformation.propertyValue(after), 0.0)
        record = TgapExplainer(
            TrendTemporalModel(DensityMetric()), [transformation]
        ).explainDetailed(snapshots)[0]
        self.assertEqual(record["achievedDelta"], 0.0)
        self.assertTrue(record["noop"])


if __name__ == "__main__":
    unittest.main()
