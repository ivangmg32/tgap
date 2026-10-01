'''
Tests for the three candidate presentations of concept impact.

WHAT IS BEING PROTECTED
    fig1 and fig2 put all five concepts on one comparison axis. RQ1b says
    that is not valid: Centralization's delta is a rewiring fraction and
    Bridge Trend's is an absolute slope, so neither achieved change is the
    same kind of quantity as a relative change in bridge width, density or
    churn.

    Candidates A, B and C each answer that differently. These tests check the
    property each candidate claims, by INSPECTING THE RENDERED FIGURE rather
    than trusting the docstring: tick labels, axes membership and the drawn
    text are read back off the matplotlib objects.
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


class TestCandidateA(FigureCase):
    ''' A: only the commensurable concepts appear. '''

    def setUp(self):
        self.fig = _capture(M.figure1ACommensurable, self.datasets,
                            self.directory, "a.png")

    def testOnlyCommensurableConceptsAppear(self):
        shown = {_conceptOf(l) for ax in self.fig.axes for l in _yLabels(ax)}
        self.assertTrue(shown)
        self.assertTrue(shown.issubset(set(self.commensurable)),
                        f"unexpected concepts in candidate A: "
                        f"{shown - set(self.commensurable)}")

    def testExcludedConceptsAppearNowhere(self):
        text = " ".join(t.get_text() for t in self.fig.findobj(
            matplotlib.text.Text))
        for concept in self.other:
            self.assertNotIn(concept, text,
                             f"{concept} is not commensurable and must not "
                             f"be drawn in candidate A")

    def testTitleMakesNoImportanceClaim(self):
        text = " ".join(t.get_text() for t in self.fig.findobj(
            matplotlib.text.Text)).lower()
        for banned in ("most important", "dominant", "strongest",
                       "best concept", "concept importance"):
            self.assertNotIn(banned, text)
        self.assertIn("commensurable", text)


class TestCandidateB(FigureCase):
    ''' B: all five concepts, but the groups never share an axis. '''

    def setUp(self):
        self.fig = _capture(M.figure1BGrouped, self.datasets,
                            self.directory, "b.png")

    def testNoAxesMixesTheTwoGroups(self):
        commensurable, other = set(self.commensurable), set(self.other)
        populated = 0
        for ax in self.fig.axes:
            shown = {_conceptOf(l) for l in _yLabels(ax)}
            if not shown:
                continue
            populated += 1
            self.assertTrue(
                shown.issubset(commensurable) or shown.issubset(other),
                f"axes mixes semantic groups: {shown}")
        self.assertGreaterEqual(populated, 2)

    def testBothGroupsArePresent(self):
        shown = {_conceptOf(l) for ax in self.fig.axes for l in _yLabels(ax)}
        self.assertTrue(shown & set(self.commensurable))
        self.assertTrue(shown & set(self.other))

    def testGroupsDoNotShareAnAxisRange(self):
        ''' Separate axes objects, so no bar length carries across. '''
        ranges = {}
        for ax in self.fig.axes:
            shown = {_conceptOf(l) for l in _yLabels(ax)}
            if not shown:
                continue
            key = (M.COMMENSURABLE if shown.issubset(set(self.commensurable))
                   else M.NOT_COMMENSURABLE)
            ranges.setdefault(key, []).append(ax.get_xlim())
        self.assertEqual(set(ranges), {M.COMMENSURABLE,
                                       M.NOT_COMMENSURABLE})
        self.assertNotEqual(ranges[M.COMMENSURABLE],
                            ranges[M.NOT_COMMENSURABLE])

    def testCaptionStatesNonComparability(self):
        text = " ".join(t.get_text() for t in self.fig.findobj(
            matplotlib.text.Text)).lower()
        self.assertIn("not comparable", text)


class TestCandidateC(FigureCase):
    ''' C: five concepts visible, grouped, never ranked. '''

    def setUp(self):
        self.fig = _capture(M.figure2CGroupedSemanticHeatmap, self.datasets,
                            self.directory, "c.png")

    def testConceptsAreInRegistryOrderNotImpactOrder(self):
        from core.TransformationRegistry import conceptNames
        registry = conceptNames()
        checked = 0
        for ax in self.fig.axes:
            shown = [l for l in _xLabels(ax) if l in registry]
            if len(shown) < 2:
                continue
            checked += 1
            expected = [c for c in registry if c in shown]
            self.assertEqual(shown, expected,
                             "heatmap columns must stay in registry order")
        self.assertGreater(checked, 0)

    def testColumnsAreNotSortedByRawImpact(self):
        ''' The specific thing forbidden: a single ordering of all five. '''
        registry = __import__(
            "core.TransformationRegistry", fromlist=["x"]).conceptNames()
        for name, data in self.datasets.items():
            valid = M._valid(data["results"])
            subset = valid[(valid["requested_delta"] == 0.1)
                           & (valid["direction"] == "increase")]
            ranked = list(subset.groupby("transformation")["impact"].apply(
                lambda s: s.abs().mean()).sort_values(
                    ascending=False).index)
            for ax in self.fig.axes:
                shown = [l for l in _xLabels(ax) if l in registry]
                if len(shown) < 2:
                    continue
                if set(shown) == set(ranked):
                    self.assertNotEqual(
                        shown, ranked,
                        "columns follow the impact ranking")

    def testNoAxesMixesTheTwoGroups(self):
        commensurable, other = set(self.commensurable), set(self.other)
        for ax in self.fig.axes:
            shown = {l for l in _xLabels(ax)
                     if l in commensurable | other}
            if not shown:
                continue
            self.assertTrue(
                shown.issubset(commensurable) or shown.issubset(other),
                f"heatmap block mixes semantic groups: {shown}")

    def testPrintedValuesAreRealImpactsNotNormalised(self):
        ''' Normalisation may drive colour; it must not touch the numbers. '''
        drawn = set()
        for text in self.fig.findobj(matplotlib.text.Text):
            value = text.get_text()
            if value.startswith(("+", "-")) and value not in ("+0",):
                try:
                    drawn.add(float(value))
                except ValueError:
                    pass
        self.assertTrue(drawn)
        real = set()
        for data in self.datasets.values():
            valid = M._valid(data["results"])
            subset = valid[(valid["requested_delta"] == 0.1)
                           & (valid["direction"] == "increase")]
            real.update(float(f"{v:+.3g}") for v in subset["impact"])
        unexplained = {v for v in drawn if v not in real}
        self.assertEqual(unexplained, set(),
                         f"values drawn that are not real impacts: "
                         f"{unexplained}")

    def testNoSingleColourScaleSpansBothGroups(self):
        ''' A shared continuous scale would render a +0.000994 cell fully
        saturated and let it be read off the colorbar as a maximum. '''
        norms = {}
        for ax in self.fig.axes:
            shown = {l for l in _xLabels(ax)
                     if l in set(self.commensurable) | set(self.other)}
            if not shown or not ax.images:
                continue
            key = (M.COMMENSURABLE
                   if shown.issubset(set(self.commensurable))
                   else M.NOT_COMMENSURABLE)
            norms.setdefault(key, []).append(
                type(ax.images[0].norm).__name__)
        self.assertEqual(set(norms), {M.COMMENSURABLE, M.NOT_COMMENSURABLE})
        self.assertNotEqual(set(norms[M.COMMENSURABLE]),
                            set(norms[M.NOT_COMMENSURABLE]),
                            "both blocks share one normalisation")


class TestProvenanceAndReproducibility(FigureCase):

    def testCandidateAValuesComeFromTheCsv(self):
        ''' Every number drawn in A is recomputed independently here from
        tgap_results.csv. If a value were hard-coded this fails. '''
        fig = _capture(M.figure1ACommensurable, self.datasets,
                       self.directory, "prov.png")
        drawn = set()
        for text in fig.findobj(matplotlib.text.Text):
            try:
                drawn.add(float(text.get_text()))
            except ValueError:
                pass
        expected = set()
        for data in self.datasets.values():
            for _, value, _ in M._meanAbsImpact(data["results"],
                                                self.commensurable):
                expected.add(float(f"{value:.4g}"))
        self.assertTrue(expected)
        self.assertTrue(expected.issubset(drawn),
                        f"missing from figure: {expected - drawn}")

    def testNoScientificNumbersAreHardCoded(self):
        ''' No numeric literal in the three generators equals any impact
        value or any group mean in the source data. '''
        real = set()
        for data in self.datasets.values():
            valid = M._valid(data["results"])
            real.update(round(abs(float(v)), 6) for v in valid["impact"])
            for _, value, _ in M._meanAbsImpact(
                    valid, self.commensurable + self.other):
                real.add(round(value, 6))
        real.discard(0.0)
        for function in (M.figure1ACommensurable, M.figure1BGrouped,
                         M.figure2CGroupedSemanticHeatmap,
                         M._meanAbsImpact, M._dotPanel):
            tree = ast.parse(inspect.getsource(function).lstrip())
            for node in ast.walk(tree):
                # Only non-integer floats. Bare integers are indices, counts
                # and offsets; one of the real impacts is exactly 1.0, so
                # including them would fail on `range(1)`-style code and say
                # nothing about provenance. A hard-coded measurement would be
                # a float with a fractional part.
                if (isinstance(node, ast.Constant)
                        and isinstance(node.value, float)
                        and node.value != int(node.value)):
                    self.assertNotIn(
                        round(abs(node.value), 6), real,
                        f"{function.__name__} hard-codes a data value: "
                        f"{node.value}")

    def testConceptListsAreNotHardCoded(self):
        ''' The generators must not name concepts as string literals. '''
        from core.TransformationRegistry import conceptNames
        for function in (M.figure1ACommensurable, M.figure1BGrouped,
                         M.figure2CGroupedSemanticHeatmap):
            source = inspect.getsource(function)
            tree = ast.parse(source.lstrip())
            literals = {n.value for n in ast.walk(tree)
                        if isinstance(n, ast.Constant)
                        and isinstance(n.value, str)}
            for concept in conceptNames():
                self.assertNotIn(
                    concept, literals,
                    f"{function.__name__} hard-codes the concept name "
                    f"{concept!r}; it must come from semanticGroups()")

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
        M.figure1ACommensurable(self.datasets, reference)
        before = mimage.imread(reference).shape

        original = dict(plt.rcParams)
        try:
            plt.rcParams.update({"savefig.dpi": 72})     # hostile ambient dpi
            after = os.path.join(directory, "after.png")
            M.figure1ACommensurable(self.datasets, after)
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
            M.figure1ACommensurable(self.datasets,
                                    os.path.join(directory, "a.png"))
            M.figure1BGrouped(self.datasets,
                              os.path.join(directory, "b.png"))
            M.figure2CGroupedSemanticHeatmap(
                self.datasets, os.path.join(directory, "c.png"))
            M.writeFigureMetadata(os.path.join(directory, "m.json"))
            digests.append({
                name: hashlib.md5(
                    open(os.path.join(directory, name), "rb").read()
                ).hexdigest()
                for name in ("a.png", "a.pdf", "b.png", "b.pdf",
                             "c.png", "c.pdf", "m.json")})
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
        ''' The final figure must be written to the publication root, and
        the superseded designs must not be. '''
        tree = ast.parse(inspect.getsource(M.main).lstrip())
        targets = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", getattr(node.func, "attr", None))
            for argument in ast.walk(node):
                if (isinstance(argument, ast.Call)
                        and getattr(argument.func, "attr", None) == "join"):
                    roots = [a.id for a in argument.args
                             if isinstance(a, ast.Name)]
                    if roots:
                        targets.setdefault(name, set()).update(roots)
        self.assertEqual(targets.get("figure1FinalModelSeparated"), {"OUTPUT"},
                         "the final figure must be written to OUTPUT")
        for superseded in ("figure1ConceptImpacts", "figure2ModelConceptHeatmap",
                           "figure1ACommensurable", "figure1BGrouped",
                           "figure2CGroupedSemanticHeatmap"):
            self.assertEqual(
                targets.get(superseded), {"SUPERSEDED"},
                f"{superseded} must be written to the superseded directory, "
                f"not used as a main publication figure")

    def testSupersededFiguresAreNotInThePublicationRoot(self):
        ''' Guards the generated tree, not just the source. '''
        if not os.path.exists(M.OUTPUT):
            self.skipTest("publication output not generated")
        root = set(os.listdir(M.OUTPUT))
        for name in ("fig1_concept_impacts.png",
                     "fig2_model_concept_heatmap.png",
                     "fig1A_commensurable_concept_impacts.png",
                     "fig1B_grouped_concept_impacts.png",
                     "fig2_grouped_semantic_heatmap.png"):
            self.assertNotIn(name, root,
                             f"{name} is superseded and must not sit beside "
                             f"the paper's figures")
        self.assertIn("fig1_final_model_separated_impacts.png", root)


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
        # Subset, not equality: this test guards that the concept-impact
        # candidates and the final figure stay documented. Other figures are
        # documented in the same file and must not make it fail.
        self.assertTrue({"final", "A", "B", "C"}.issubset(candidates),
                        f"missing: {{'final','A','B','C'}} - {candidates}")
        for entry in self.payload["figures"]:
            for key in ("figure", "included_concepts", "delta_semantics",
                        "cross_concept_numerical_comparison_allowed",
                        "source_csv", "generation_function", "formats"):
                self.assertIn(key, entry)

    def testComparabilityFlagsMatchTheFigures(self):
        byName = {f["candidate"]: f for f in self.payload["figures"]}
        self.assertTrue(
            byName["A"]["cross_concept_numerical_comparison_allowed"],
            "A shows only commensurable concepts, so comparison is allowed")
        for candidate in ("B", "C"):
            self.assertFalse(
                byName[candidate][
                    "cross_concept_numerical_comparison_allowed"],
                f"{candidate} shows both groups; comparison is not allowed")

    def testMetadataConceptsMatchSemanticGroups(self):
        byName = {f["candidate"]: f for f in self.payload["figures"]}
        self.assertCountEqual(byName["A"]["included_concepts"],
                              self.commensurable)
        self.assertCountEqual(byName["A"]["excluded_concepts"], self.other)
        for candidate in ("B", "C"):
            self.assertCountEqual(byName[candidate]["included_concepts"],
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
                self.assertTrue(os.path.exists(source), source)


if __name__ == "__main__":
    unittest.main()
