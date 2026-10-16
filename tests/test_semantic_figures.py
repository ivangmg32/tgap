'''
Tests for the semantic grouping of concepts and the final global-impact
figure (fig1_final_model_separated_impacts).

WHAT IS BEING PROTECTED
    Putting all five concepts on one comparison axis is not valid (RQ1b):
    Centralization's delta is a rewiring fraction and Bridge Trend's is an
    absolute slope, so neither achieved change is the same kind of quantity
    as a relative change in bridge width, density or churn. Earlier designs
    that pooled across models were removed; the final figure keeps every
    model and every semantic group separate.

    The tests check those properties by INSPECTING THE RENDERED FIGURE
    rather than trusting the docstring: tick labels, axes membership and the
    drawn text are read back off the matplotlib objects.
'''

import ast
import hashlib
import inspect
import os
import shutil
import tempfile
import unittest

import matplotlib
matplotlib.use("Agg")

import paths
from realdata import make_publication as M


def _capture(function, datasets, directory, name):
    ''' Run a figure function and hand back the Figure it drew.

    The functions close their figure, which only unregisters it from pyplot;
    the artists stay reachable, so tick labels and texts can still be read.
    '''
    captured = {}
    original = M.savePublicationFigure

    def spy(fig, path, **kwargs):
        captured["fig"] = fig
        return original(fig, path, **kwargs)

    M.savePublicationFigure = spy
    try:
        function(datasets, os.path.join(directory, name))
    finally:
        M.savePublicationFigure = original
    return captured["fig"]


def _yLabels(ax):
    return [t.get_text() for t in ax.get_yticklabels() if t.get_text()]


def _xLabels(ax):
    return [t.get_text() for t in ax.get_xticklabels() if t.get_text()]


def _conceptOf(label):
    ''' Strip the "  (n=36)" suffix the dot panels append. '''
    return label.split("  (n=")[0].strip()


class FigureCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.mkdtemp(prefix="tgap_figs_")
        cls.datasets = {n: M._load(n) for n in M.CASE_STUDIES}
        cls.groups = M.semanticGroups()
        cls.commensurable = cls.groups[M.COMMENSURABLE]
        cls.other = cls.groups[M.NOT_COMMENSURABLE]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.directory, ignore_errors=True)


class TestSemanticGroups(FigureCase):

    def testGroupingIsNotTakenFromTheStoredDeltaMode(self):
        ''' The regression this whole module exists to prevent.

        The stored delta_mode column says "relative" for Centralization,
        because its REQUESTED delta is relative; its ACHIEVED delta is a
        rewiring fraction. Grouping on that column would put Centralization
        among the commensurable concepts and reintroduce the error.
        '''
        results = self.datasets["email_eu_core"]["results"]
        stored = results[results["transformation"] == "Centralization"]
        self.assertTrue((stored["delta_mode"] == "relative").all(),
                        "fixture assumption: the CSV does record 'relative'")
        self.assertIn("Centralization", self.other,
                      "Centralization must NOT be in the commensurable group")

    def testGroupsPartitionTheRegisteredConcepts(self):
        from core.TransformationRegistry import conceptNames
        union = self.commensurable + self.other
        self.assertCountEqual(union, conceptNames())
        self.assertEqual(set(self.commensurable) & set(self.other), set())

    def testGroupMembershipMatchesTheRq1bRule(self):
        ''' Derived by comparabilityOf, not by a hand-written name list. '''
        from core.Communities import Partition
        from core.TransformationRegistry import get
        from realdata.run_tgn_stability import comparabilityOf
        partition = Partition([{0, 1}, {2, 3}])
        reference = get(self.commensurable[0]).build(communities=partition)
        for concept in self.commensurable:
            comparable, _ = comparabilityOf(
                reference, get(concept).build(communities=partition))
            self.assertTrue(comparable, f"{concept} should be commensurable")
        for concept in self.other:
            comparable, _ = comparabilityOf(
                reference, get(concept).build(communities=partition))
            self.assertFalse(comparable, f"{concept} should not be")


class TestProvenanceAndReproducibility(FigureCase):

    def testPublicationDpiSurvivesAPipelineImport(self):
        ''' Regression: several pipeline modules set savefig.dpi = 200 at
        import time. Importing one mid-run used to silently downgrade every
        publication figure drawn afterwards from 300 dpi to 200, changing
        the pixel dimensions of already-published figures. dpi is now passed
        explicitly, so ambient rcParams cannot decide it. '''
        import matplotlib.image as mimage
        import matplotlib.pyplot as plt
        from realdata.plotting import PUBLICATION_THEME

        directory = os.path.join(self.directory, "dpi")
        os.makedirs(directory, exist_ok=True)
        reference = os.path.join(directory, "ref.png")
        M.figure1FinalModelSeparated(self.datasets, reference)
        before = mimage.imread(reference).shape

        original = dict(plt.rcParams)
        try:
            plt.rcParams.update({"savefig.dpi": 72})     # hostile ambient dpi
            after = os.path.join(directory, "after.png")
            M.figure1FinalModelSeparated(self.datasets, after)
            self.assertEqual(
                mimage.imread(after).shape, before,
                "ambient savefig.dpi changed the published figure size")
        finally:
            plt.rcParams.update(original)
        self.assertEqual(PUBLICATION_THEME["savefig.dpi"], 300)

    def testFiguresAreReproducible(self):
        ''' Two runs, byte-identical PNG and PDF.

        PDF carries a CreationDate by default; savePublicationFigure omits
        it precisely so this check can cover the vector output too.
        '''
        digests = []
        for run in range(2):
            directory = os.path.join(self.directory, f"repro{run}")
            os.makedirs(directory, exist_ok=True)
            M.figure1FinalModelSeparated(self.datasets,
                                         os.path.join(directory, "a.png"))
            M.writeFigureMetadata(os.path.join(directory, "m.json"))
            digests.append({
                name: hashlib.md5(
                    open(os.path.join(directory, name), "rb").read()
                ).hexdigest()
                for name in ("a.png", "a.pdf", "m.json")})
        for name in digests[0]:
            self.assertEqual(digests[0][name], digests[1][name],
                             f"{name} is not reproducible")


class TestFinalFigure(FigureCase):
    ''' fig1_final_model_separated_impacts - THE publication global-impact
    figure. Two independent invariants are protected here:

      1. no aggregation across models, ever;
      2. no non-commensurable concept sharing a panel with the relative
         group.
    '''

    def setUp(self):
        self.fig = _capture(M.figure1FinalModelSeparated, self.datasets,
                            self.directory, "final.png")
        self.panels = []
        for ax in self.fig.axes:
            concepts = [_conceptOf(t) for t in _yLabels(ax)]
            self.panels.append((ax, concepts))

    def _points(self, ax):
        return sum(len(c.get_offsets()) for c in ax.collections)

    # 1
    def testNoAggregationAcrossModels(self):
        ''' Every point is one valid CSV row. Totals are compared per
        (dataset, model, concept): any mean, median or pooled statistic
        would collapse several rows into one point and fail here. '''
        drawn = 0
        for ax, _ in self.panels:
            drawn += self._points(ax)
        expected = sum(len(M._valid(d["results"])) for d in
                       self.datasets.values())
        self.assertEqual(drawn, expected,
                         "the number of plotted points must equal the "
                         "number of valid rows - nothing may be aggregated")

    def testPanelPointCountsMatchThePerModelRowCounts(self):
        counts = {}
        for dataset, data in self.datasets.items():
            valid = M._valid(data["results"])
            for (model, concept), group in valid.groupby(
                    ["model", "transformation"]):
                counts[(dataset, model, concept)] = len(group)
        self.assertEqual(sum(counts.values()),
                         sum(self._points(ax) for ax, _ in self.panels))
        self.assertGreater(max(counts.values()), 1,
                           "fixture must contain multi-row cells, else the "
                           "no-aggregation test proves nothing")

    # 2
    def testEveryModelIsRepresented(self):
        titles = {t for ax, _ in self.panels for t in [ax.get_title()] if t}
        models = {m for data in self.datasets.values()
                  for m in M._valid(data["results"])["model"].unique()}
        self.assertTrue(models)
        self.assertTrue(models.issubset(titles),
                        f"models missing from the figure: {models - titles}")

    # 3, 4, 5
    def testCommensurableConceptsShareAPanel(self):
        shared = [c for _, c in self.panels
                  if set(c) == set(self.commensurable)]
        self.assertTrue(shared,
                        "Bridge Width, Density and Churn must appear "
                        "together in a panel")

    def testNonCommensurableConceptsNeverJoinThatPanel(self):
        for _, concepts in self.panels:
            if not concepts:
                continue
            for concept in self.other:
                if concept in concepts:
                    self.assertEqual(
                        concepts, [concept],
                        f"{concept} must occupy a panel alone, not share "
                        f"one with {concepts}")

    def testCentralizationAndBridgeTrendAreNotInTheSameRow(self):
        ''' They are not comparable with each other either. '''
        for _, concepts in self.panels:
            self.assertFalse(set(self.other).issubset(set(concepts)),
                             "the two non-commensurable concepts must not "
                             "share a row")

    # 6
    def testEachModelPanelHasItsOwnAxis(self):
        populated = [ax for ax, _ in self.panels if self._points(ax)]
        limits = {ax.get_xlim() for ax in populated}
        self.assertGreater(
            len(limits), 1,
            "every panel sharing one x-range would imply a common scale")
        # Specifically: panels in the same row must not all share a range.
        byRow = {}
        for ax in populated:
            byRow.setdefault(round(ax.get_position().y0, 3), set()).add(
                ax.get_xlim())
        self.assertTrue(any(len(v) > 1 for v in byRow.values()),
                        "models within a row share an x-axis")

    # 7
    def testInsufficientCellsAreLabelledNotPlottedAsZero(self):
        ''' decentraland has no valid Bridge Trend row. It must be stated,
        never drawn as a point at zero. '''
        empty = []
        for dataset, data in self.datasets.items():
            valid = M._valid(data["results"])
            present = set(valid["transformation"])
            for concept in self.commensurable + self.other:
                if concept not in present:
                    empty.append((dataset, concept))
        self.assertTrue(empty, "fixture must contain an empty cell")

        labels = [t.get_text() for t in self.fig.findobj(matplotlib.text.Text)]
        self.assertTrue(any("n=0" in l for l in labels),
                        "an empty cell must be labelled n=0")
        for ax, concepts in self.panels:
            if concepts and not self._points(ax):
                self.assertEqual(
                    ax.get_xticks().size, 0,
                    "an empty panel must not carry a numeric axis")

    def testEveryPlottedPointIsARealValidImpact(self):
        real = set()
        for data in self.datasets.values():
            real.update(round(float(v), 9)
                        for v in M._valid(data["results"])["impact"])
        for ax, _ in self.panels:
            for collection in ax.collections:
                for x, _y in collection.get_offsets():
                    self.assertIn(round(float(x), 9), real,
                                  f"plotted value {x} is not a valid impact")

    # 12
    def testNoGlobalRankingLanguage(self):
        text = " ".join(t.get_text() for t in self.fig.findobj(
            matplotlib.text.Text)).lower()
        for banned in ("concept importance", "most important", "dominant",
                       "strongest", "best concept", "ranking of concepts"):
            self.assertNotIn(banned, text)
        self.assertIn("no global ranking", text)
        self.assertIn("descriptive", text)


class TestFinalFigureOutputs(FigureCase):

    # 9, 10, 11
    def testPngAndPdfAreBothProducedAndReproducible(self):
        digests = []
        for run in range(2):
            directory = os.path.join(self.directory, f"final{run}")
            os.makedirs(directory, exist_ok=True)
            target = os.path.join(directory, "final.png")
            M.figure1FinalModelSeparated(self.datasets, target)
            produced = {}
            for suffix in ("png", "pdf"):
                name = target[:-4] + "." + suffix
                self.assertTrue(os.path.exists(name), f"{suffix} not written")
                produced[suffix] = hashlib.md5(
                    open(name, "rb").read()).hexdigest()
            digests.append(produced)
        self.assertEqual(digests[0], digests[1],
                         "the final figure is not reproducible")

    # 8
    def testNoScientificNumberIsHardCoded(self):
        real = set()
        for data in self.datasets.values():
            real.update(round(abs(float(v)), 6)
                        for v in M._valid(data["results"])["impact"])
        real.discard(0.0)
        for function in (M.figure1FinalModelSeparated, M._stripPanel,
                         M.semanticRows):
            tree = ast.parse(inspect.getsource(function).lstrip())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant)
                        and isinstance(node.value, float)
                        and node.value != int(node.value)):
                    self.assertNotIn(
                        round(abs(node.value), 6), real,
                        f"{function.__name__} hard-codes {node.value}")

    def testNoConceptOrModelNameIsHardCoded(self):
        from core.TransformationRegistry import conceptNames
        models = {m for data in self.datasets.values()
                  for m in M._valid(data["results"])["model"].unique()}
        for function in (M.figure1FinalModelSeparated, M._stripPanel,
                         M.semanticRows):
            tree = ast.parse(inspect.getsource(function).lstrip())
            literals = {n.value for n in ast.walk(tree)
                        if isinstance(n, ast.Constant)
                        and isinstance(n.value, str)}
            for name in set(conceptNames()) | models:
                self.assertNotIn(name, literals,
                                 f"{function.__name__} hard-codes {name!r}")

    # 13
    def testThePipelineUsesTheFinalFigureAsTheMainOne(self):
        ''' main() must draw the final figure, and the removed designs that
        pooled across models must not exist at all. '''
        self.assertIn("figure1FinalModelSeparated(",
                      inspect.getsource(M.main))
        for removed in ("figure1ConceptImpacts", "figure2ModelConceptHeatmap",
                        "figure1ACommensurable", "figure1BGrouped",
                        "figure2CGroupedSemanticHeatmap"):
            self.assertFalse(hasattr(M, removed),
                             f"{removed} pooled across models and was "
                             f"removed; it must not come back")

    def testOnlyTheFinalGlobalImpactFigureIsPublished(self):
        ''' Guards the generated tree, not just the source. '''
        if not os.path.exists(M.FIGURES):
            self.skipTest("publication output not generated")
        published = set(os.listdir(M.FIGURES))
        for name in ("fig1_concept_impacts.png",
                     "fig2_model_concept_heatmap.png",
                     "fig1A_commensurable_concept_impacts.png",
                     "fig1B_grouped_concept_impacts.png",
                     "fig2_grouped_semantic_heatmap.png"):
            self.assertNotIn(name, published)
        self.assertIn("fig1_final_model_separated_impacts.png", published)


class TestMetadata(FigureCase):

    def setUp(self):
        self.path = os.path.join(self.directory, "meta.json")
        self.payload = M.writeFigureMetadata(self.path)

    def testFileIsValidJsonOnDisk(self):
        import json
        with open(self.path, encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), self.payload)

    def testEveryCandidateIsDocumented(self):
        candidates = {f["candidate"] for f in self.payload["figures"]}
        self.assertIn("final", candidates)
        for entry in self.payload["figures"]:
            for key in ("figure", "included_concepts", "delta_semantics",
                        "cross_concept_numerical_comparison_allowed",
                        "source_csv", "generation_function", "formats"):
                self.assertIn(key, entry)

    def testComparabilityFlagsMatchTheFigures(self):
        final = {f["candidate"]: f for f in self.payload["figures"]}["final"]
        self.assertFalse(
            final["cross_concept_numerical_comparison_allowed"],
            "the final figure shows both groups; comparison is not allowed")

    def testMetadataConceptsMatchSemanticGroups(self):
        final = {f["candidate"]: f for f in self.payload["figures"]}["final"]
        self.assertCountEqual(final["included_concepts"],
                              self.commensurable + self.other)

    def testGenerationFunctionsResolve(self):
        import importlib
        for entry in self.payload["figures"]:
            module, _, attribute = entry["generation_function"].rpartition(".")
            self.assertTrue(
                hasattr(importlib.import_module(module), attribute),
                f"{entry['generation_function']} does not resolve")

    def testSourceCsvFilesExist(self):
        for entry in self.payload["figures"]:
            for source in entry["source_csv"]:
                # Stored relative to the repository root (paths.relative).
                self.assertFalse(os.path.isabs(source), source)
                self.assertTrue(os.path.exists(os.path.join(paths.ROOT,
                                                            source)), source)


if __name__ == "__main__":
    unittest.main()
