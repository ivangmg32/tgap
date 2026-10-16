'''
Tests for the transformation registry, the architecture figure, and the
per-concept TGN stability summary.

The registry's purpose is narrow and worth restating: the explainer was
ALREADY generic, so these tests are not about the explainer. They are about
the layer above it, which used to list the five concept names as literals -
so a new concept would run through the explainer correctly and then vanish
from the cross-dataset figures.

The decisive test is testCustomTransformationReachesThePipeline: a dummy
concept defined in this file, registered at run time, must appear in
everything the pipeline builds, with no core file edited.
'''

import os
import tempfile
import unittest

import networkx as nx

from core import TemporalGraphTransformation, makeTemporalGraph
from core.TransformationRegistry import (
    buildAll, conceptNames, entries, get, names, register, unregister,
)


class DummyTransformation(TemporalGraphTransformation):
    ''' A user concept defined outside core/, registered at run time. '''

    name = "Dummy Edge Count"
    preservesEdgeCount = False

    def __init__(self, communities=None, seed=42):
        self.communities = communities
        self.seed = seed

    def propertyValue(self, x):
        snapshots = x if isinstance(x, list) else [x]
        return float(sum(g.number_of_edges() for g in snapshots))

    def transformGraph(self, graph, delta):
        return graph.copy()


class TestBuiltinRegistrations(unittest.TestCase):

    def testAllFiveShippedConceptsAreRegistered(self):
        for concept in ("Bridge Width", "Centralization", "Density",
                        "Bridge Trend", "Churn"):
            self.assertIn(concept, names())
            self.assertTrue(get(concept).builtin)

    def testCapabilityMetadataReplacesStringComparison(self):
        ''' Bridge Trend needs saturation gating because it reshapes a
        trajectory - a PROPERTY of the concept, now declared rather than
        decided by comparing its name. '''
        self.assertTrue(get("Bridge Trend").needsTrendGating)
        for other in ("Bridge Width", "Centralization", "Density", "Churn"):
            self.assertFalse(get(other).needsTrendGating)

    def testEdgeCountCapabilityComesFromTheClass(self):
        ''' Single source of truth: the registry reads the transformation's
        own declaration rather than keeping a second copy that could
        drift. '''
        self.assertFalse(get("Density").preservesEdgeCount)
        for other in ("Bridge Width", "Centralization", "Bridge Trend",
                      "Churn"):
            self.assertTrue(get(other).preservesEdgeCount)

    def testTemporalFlag(self):
        self.assertTrue(get("Bridge Trend").temporal)
        self.assertTrue(get("Churn").temporal)
        self.assertFalse(get("Bridge Width").temporal)

    def testBuildAllProducesWorkingInstances(self):
        communities = ({0, 1, 2}, {3, 4, 5})
        built = buildAll(communities, seed=42)
        self.assertEqual(len(built), 5)
        self.assertEqual([t.name for t in built],
                         ["Bridge Width", "Centralization", "Density",
                          "Bridge Trend", "Churn"])

    def testNoNameBasedSpecialCasing(self):
        ''' The registry must not BRANCH on concept names.

        Checked against executable code only. Docstrings legitimately quote
        the old `== "Bridge Trend"` pattern while explaining why it was
        replaced, and a naive substring search over the whole file flags
        that explanation as if it were the defect. Parsing the AST and
        inspecting comparison nodes asks the real question: does any
        conditional compare against a concept name?
        '''
        import ast
        import inspect
        import core.TransformationRegistry as registry

        tree = ast.parse(inspect.getsource(registry))
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            for operand in [node.left] + list(node.comparators):
                if (isinstance(operand, ast.Constant)
                        and isinstance(operand.value, str)
                        and operand.value in ("Bridge Width", "Bridge Trend",
                                              "Centralization", "Density",
                                              "Churn")):
                    offenders.append(operand.value)
        self.assertEqual(offenders, [],
                         f"registry branches on concept names: {offenders}")


class TestCustomRegistration(unittest.TestCase):

    def setUp(self):
        self.entry = register("Dummy Edge Count", DummyTransformation,
                              description="test-only concept", replace=True)

    def tearDown(self):
        unregister("Dummy Edge Count")

    def testRegistrationAndDiscovery(self):
        self.assertIn("Dummy Edge Count", names())
        self.assertIn("Dummy Edge Count", conceptNames())
        self.assertFalse(get("Dummy Edge Count").builtin)

    def testCapabilityInferredFromTheClass(self):
        self.assertFalse(self.entry.preservesEdgeCount)

    def testCustomTransformationReachesThePipeline(self):
        ''' THE test. Everything the pipeline builds from the registry must
        include the new concept, with no core file edited. '''
        communities = ({0, 1, 2}, {3, 4, 5})
        built = buildAll(communities, seed=42)
        self.assertIn("Dummy Edge Count", [t.name for t in built])
        self.assertEqual(len(built), 6)

    def testBuiltinOnlyFiltersItOut(self):
        ''' Pipelines that must reproduce the published five exactly can
        still ask for only those. '''
        self.assertNotIn("Dummy Edge Count", conceptNames(builtinOnly=True))
        self.assertEqual(len(entries(builtinOnly=True)), 5)

    def testExplainerExecutesIt(self):
        from core import PersistenceTemporalModel, TgapExplainer
        from core.GraphMetric import DensityMetric
        snapshots, communities = makeTemporalGraph(
            nSnapshots=4, nPerCommunity=6, bridgeWidth=5, seed=1)
        model = PersistenceTemporalModel(DensityMetric())
        explanation = TgapExplainer(
            model, buildAll(communities, seed=42)).explain(snapshots)
        self.assertTrue(any("Dummy Edge Count" in label
                            for label in explanation))

    def testResultsCanBePersisted(self):
        from core import PersistenceTemporalModel, TgapExplainer
        from core.GraphMetric import DensityMetric
        import csv
        snapshots, communities = makeTemporalGraph(
            nSnapshots=4, nPerCommunity=6, bridgeWidth=5, seed=1)
        records = TgapExplainer(
            PersistenceTemporalModel(DensityMetric()),
            buildAll(communities, seed=42)).explainDetailed(snapshots)
        path = os.path.join(tempfile.mkdtemp(), "custom.csv")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["transformation", "impact"],
                extrasaction="ignore")
            writer.writeheader()
            for record in records:
                writer.writerow(record)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("Dummy Edge Count", text)

    def testDuplicateRegistrationIsRefusedUnlessDeliberate(self):
        with self.assertRaises(ValueError):
            register("Dummy Edge Count", DummyTransformation)
        register("Dummy Edge Count", DummyTransformation, replace=True)


class TestPipelineUsesTheRegistry(unittest.TestCase):
    ''' The hard-coded lists the registry exists to remove. '''

    def testCompareDatasetsHasNoLiteralConceptList(self):
        import inspect
        from realdata import compare_datasets
        source = inspect.getsource(compare_datasets.figureImpactHeatmap)
        self.assertIn("conceptNames", source)
        self.assertNotIn('"Bridge Trend", "Churn"', source)

    def testRunRealDataBuildsFromTheRegistry(self):
        import inspect
        from realdata import run_real_data
        source = inspect.getsource(run_real_data.buildTransformations)
        self.assertIn("entries", source)

    def testBuiltinPipelineStillProducesTheSameFiveNames(self):
        communities = ({0, 1, 2}, {3, 4, 5})
        from realdata.run_real_data import buildTransformations
        built = buildTransformations(communities)
        self.assertEqual([t.name for t in built],
                         ["Bridge Width", "Centralization", "Density",
                          "Bridge Trend", "Churn"])


class TestArchitectureFigure(unittest.TestCase):
    ''' Smoke test: the figure must be generated by code, every time. '''

    def testGeneratesPngAndVector(self):
        from realdata.plotting import architectureFigure
        directory = tempfile.mkdtemp()
        written = architectureFigure(os.path.join(directory, "arch"))
        self.assertEqual(len(written), 2)
        for path in written:
            self.assertTrue(os.path.exists(path))
            self.assertGreater(os.path.getsize(path), 5000)
        self.assertTrue(any(p.endswith(".png") for p in written))
        self.assertTrue(any(p.endswith(".pdf") or p.endswith(".svg")
                            for p in written))

    def testSaveHelperHonoursRequestedFormats(self):
        import matplotlib.pyplot as plt
        from realdata.plotting import savePublicationFigure
        figure, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        directory = tempfile.mkdtemp()
        written = savePublicationFigure(figure, os.path.join(directory, "x"),
                                        formats=("png", "svg"))
        plt.close(figure)
        self.assertEqual([os.path.splitext(p)[1] for p in written],
                         [".png", ".svg"])

    def testThemeIsShared(self):
        from realdata.plotting import PUBLICATION_THEME, usePublicationTheme
        import matplotlib.pyplot as plt
        usePublicationTheme()
        self.assertEqual(plt.rcParams["savefig.dpi"],
                         PUBLICATION_THEME["savefig.dpi"])


class TestPerConceptStability(unittest.TestCase):
    ''' The per-concept summary must never become a ranking, and must
    refuse to summarise too few observations. '''

    def testInsufficientSeedsReportedNotManufactured(self):
        from realdata.run_tgn_stability import perConceptStability
        rows = [{"seed": 0, "transformation": "X", "direction": "increase",
                 "requested_delta": 0.1, "delta_mode": "relative",
                 "valid_for_analysis": True, "impact": 1.0,
                 "achieved_delta": 0.1}]
        frame = perConceptStability(rows, minSeeds=2)
        self.assertFalse(bool(frame["sufficient"].iloc[0]))
        self.assertIsNone(frame["mean_impact"].iloc[0])
        self.assertIn("at least 2", frame["insufficient_reason"].iloc[0])

    def testSufficientSeedsAreSummarised(self):
        from realdata.run_tgn_stability import perConceptStability
        rows = [{"seed": s, "transformation": "X", "direction": "increase",
                 "requested_delta": 0.1, "delta_mode": "relative",
                 "valid_for_analysis": True, "impact": float(s),
                 "achieved_delta": 0.1} for s in range(3)]
        frame = perConceptStability(rows, minSeeds=2)
        self.assertTrue(bool(frame["sufficient"].iloc[0]))
        self.assertAlmostEqual(frame["mean_impact"].iloc[0], 1.0)
        self.assertEqual(frame["valid_seeds"].iloc[0], 3)

    def testInvalidRowsAreExcluded(self):
        from realdata.run_tgn_stability import perConceptStability
        rows = [{"seed": s, "transformation": "X", "direction": "increase",
                 "requested_delta": 0.1, "delta_mode": "relative",
                 "valid_for_analysis": s != 0, "impact": float(s),
                 "achieved_delta": 0.1} for s in range(3)]
        frame = perConceptStability(rows, minSeeds=2)
        self.assertEqual(frame["valid_seeds"].iloc[0], 2)

    def testComparabilityFlagTravelsWithTheRow(self):
        ''' So a reader cannot lose the RQ1b restriction when looking at a
        table of per-concept means. '''
        from realdata.run_tgn_stability import perConceptStability
        rows = []
        for concept, mode in (("Bridge Width", "relative"),
                              ("Centralization", "relative"),
                              ("Bridge Trend", "absolute")):
            rows.extend({"seed": s, "transformation": concept,
                         "direction": "increase", "requested_delta": 0.1,
                         "delta_mode": mode, "valid_for_analysis": True,
                         "impact": float(s), "achieved_delta": 0.1}
                        for s in range(3))
        frame = perConceptStability(rows).set_index("concept")
        self.assertTrue(
            frame.loc["Bridge Width", "comparable_with_relative_concepts"])
        self.assertFalse(
            frame.loc["Centralization", "comparable_with_relative_concepts"])
        self.assertFalse(
            frame.loc["Bridge Trend", "comparable_with_relative_concepts"])

    def testNoRankingColumnExists(self):
        from realdata.run_tgn_stability import perConceptStability
        rows = [{"seed": s, "transformation": "X", "direction": "increase",
                 "requested_delta": 0.1, "delta_mode": "relative",
                 "valid_for_analysis": True, "impact": float(s),
                 "achieved_delta": 0.1} for s in range(3)]
        columns = [c.lower() for c in perConceptStability(rows).columns]
        for forbidden in ("rank", "winner", "best", "most_important"):
            self.assertNotIn(forbidden, columns)


if __name__ == "__main__":
    unittest.main()
