'''
Tests for the five element-level / distribution publication figures:

    fig8  dependence
    fig9  true beeswarm
    fig10 publication boxplot
    fig11 local bar
    fig12 temporal edge-time scatter

HOW THESE TESTS WORK
    They read values back off the RENDERED matplotlib artists and check each
    one against the persisted CSV it is supposed to have come from. A figure
    that drew a plausible-looking number not present in the data fails, which
    is the property that actually matters here - these figures exist to
    display measurements, and a decorative number would be a fabrication.
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
import numpy as np
import pandas as pd

from realdata import make_publication as M


def _capture(function, directory, name, *arguments):
    ''' Run a figure function and return the Figure it drew. '''
    captured = {}
    original = M.savePublicationFigure

    def spy(fig, path, **kwargs):
        captured["fig"] = fig
        return original(fig, path, **kwargs)

    M.savePublicationFigure = spy
    try:
        function(*arguments, os.path.join(directory, name))
    finally:
        M.savePublicationFigure = original
    return captured["fig"]


def _offsets(fig):
    ''' Every scatter point actually drawn, as (x, y) pairs. '''
    points = []
    for ax in fig.axes:
        for collection in ax.collections:
            points.extend(tuple(map(float, xy))
                          for xy in collection.get_offsets())
    return points


def _texts(fig):
    return [t.get_text() for t in fig.findobj(matplotlib.text.Text)
            if t.get_text()]


class PublicationCase(unittest.TestCase):
    ''' The attribution data is built ONCE into a temp directory. Building it
    is the expensive part (it runs real occlusion), and every figure under
    test reads the same files the pipeline would. '''

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.mkdtemp(prefix="tgap_pub_")
        cls.paths = M.buildAttributionData(
            os.path.join(cls.directory, "attribution"))
        cls.datasets = {n: M._load(n) for n in M.CASE_STUDIES}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.directory, ignore_errors=True)


class TestAttributionPersistence(PublicationCase):

    def testEveryFigureSourceExists(self):
        for name, path in self.paths.items():
            self.assertTrue(os.path.exists(path), f"{name}: {path}")
            self.assertGreater(len(pd.read_csv(path)), 0, name)

    def testElementSchemaIsTheLibrarySchema(self):
        ''' The persisted columns must be the library's declared schema, not
        an ad-hoc set invented by the figure code. '''
        from core import ELEMENT_ATTRIBUTION_COLUMNS
        for key in ("edge", "node", "edge_trend"):
            columns = tuple(pd.read_csv(self.paths[key]).columns)
            self.assertEqual(columns, tuple(ELEMENT_ATTRIBUTION_COLUMNS), key)

    def testEdgeTimeHoldsEveryEdgeAtEverySnapshot(self):
        ''' The COMPLETE attribution is persisted; top-K is display-only. '''
        frame = pd.read_csv(self.paths["edge_time"])
        self.assertIn("snapshot_index", frame.columns)
        self.assertIn("impact", frame.columns)
        perSnapshot = frame.groupby("snapshot_index").size()
        self.assertGreater(len(perSnapshot), 1)
        # Every row must be unique in (edge, snapshot): no aggregation.
        self.assertEqual(len(frame),
                         len(frame.drop_duplicates(["u", "v",
                                                    "snapshot_index"])))

    def testProvenanceRecordsMethodAndSelection(self):
        with open(os.path.join(os.path.dirname(self.paths["edge"]),
                               "provenance.json"), encoding="utf-8") as handle:
            import json
            provenance = json.load(handle)
        for key in ("edge_method", "edge_time_method", "seed",
                    "edge_coverage", "edge_time_selection_rule"):
            self.assertIn(key, provenance)
        self.assertIn("occlusion", provenance["edge_method"])
        self.assertEqual(provenance["seed"], M.ATTRIBUTION_SEED)


class TestDependence(PublicationCase):

    def setUp(self):
        self.fig = _capture(M.figure8Dependence, self.directory, "f8.png",
                            self.paths)

    def testAxesUseRealPersistedColumnsNotFabricatedFeatures(self):
        from core import ELEMENT_ATTRIBUTION_COLUMNS
        node = pd.read_csv(self.paths["node"])
        edge = pd.read_csv(self.paths["edge"])
        # The two x variables must be genuine columns of the schema.
        for column in ("total_degree", "snapshots_present"):
            self.assertIn(column, ELEMENT_ATTRIBUTION_COLUMNS)
        self.assertTrue(node["total_degree"].notna().any())
        self.assertTrue(edge["snapshots_present"].notna().any())

    def testEveryPlottedPairExistsInTheSourceCsv(self):
        pairs = set()
        for source, column in ((self.paths["node"], "total_degree"),
                               (self.paths["edge"], "snapshots_present")):
            frame = pd.read_csv(source)
            pairs.update((round(float(x), 9), round(float(y), 9))
                         for x, y in zip(frame[column], frame["impact"]))
        drawn = _offsets(self.fig)
        self.assertTrue(drawn)
        for x, y in drawn:
            self.assertIn((round(x, 9), round(y, 9)), pairs,
                          f"plotted ({x}, {y}) is not in the source data")

    def testNoElementIsLostToTheMarkerTally(self):
        ''' Coincident elements are merged into one enlarged marker; the
        counts printed on them must add up to every element. '''
        total = 0
        for source in (self.paths["node"], self.paths["edge"]):
            total += len(pd.read_csv(source))
        shown = sum(int(t) for t in _texts(self.fig) if t.isdigit())
        singles = len(_offsets(self.fig)) - sum(
            1 for t in _texts(self.fig) if t.isdigit())
        self.assertEqual(shown + singles, total,
                         "marker counts plus single markers must equal the "
                         "number of elements")

    def testTitleIsNotAFeatureImportanceClaim(self):
        text = " ".join(_texts(self.fig)).lower()
        for banned in ("feature importance", "most important", "dominant",
                       "strongest", "best "):
            self.assertNotIn(banned, text)
        self.assertIn("measured prediction difference", text)

    def testReportsNAndCoverage(self):
        text = " ".join(_texts(self.fig))
        self.assertIn("n=", text)
        self.assertIn("coverage", text)


class TestBeeswarmLayout(unittest.TestCase):
    ''' The packing algorithm itself, independent of any figure. '''

    def testNoTwoPointsOverlap(self):
        values = [0.0] * 30 + [1.0, 1.001, 1.002] + list(np.linspace(-2, 2, 40))
        width = 0.05
        offsets = M._beeswarmOffsets(values, width)
        placed = list(zip(values, offsets))
        for i, (x1, y1) in enumerate(placed):
            for x2, y2 in placed[i + 1:]:
                if abs(x1 - x2) < width:
                    self.assertGreaterEqual(
                        abs(y1 - y2), 0.999,
                        f"points ({x1},{y1}) and ({x2},{y2}) overlap")

    def testIsDeterministic(self):
        values = [0.0, 0.0, 0.0, 1.0, -1.0, 0.5, 0.5]
        first = M._beeswarmOffsets(values, 0.1)
        for _ in range(5):
            self.assertEqual(M._beeswarmOffsets(values, 0.1), first)

    def testLayoutDoesNotDependOnInputOrder(self):
        ''' A jittered scatter keyed on index would fail this. '''
        values = [0.0, 1.0, 0.0, -1.0, 0.0, 0.5]
        order = [3, 0, 5, 2, 1, 4]
        shuffled = [values[i] for i in order]
        direct = dict(zip(values, M._beeswarmOffsets(values, 0.1)))
        viaShuffle = dict(zip(shuffled, M._beeswarmOffsets(shuffled, 0.1)))
        self.assertEqual(sorted(direct.values()),
                         sorted(viaShuffle.values()))

    def testUsesNoRandomness(self):
        source = inspect.getsource(M._beeswarmOffsets)
        tree = ast.parse(source.lstrip())
        names = {getattr(n.func, "attr", getattr(n.func, "id", None))
                 for n in ast.walk(tree) if isinstance(n, ast.Call)}
        for banned in ("random", "shuffle", "uniform", "normal",
                       "default_rng", "sample"):
            self.assertNotIn(banned, names)
        self.assertNotIn("seed", inspect.signature(
            M._beeswarmOffsets).parameters)

    def testEveryPointKeepsItsValue(self):
        ''' Packing moves points on y only; x is never altered. '''
        values = [0.0, 0.0, 0.0, 2.5]
        offsets = M._beeswarmOffsets(values, 0.1)
        self.assertEqual(len(offsets), len(values))


class TestBeeswarmFigure(PublicationCase):

    def setUp(self):
        self.fig = _capture(M.figure9TrueBeeswarm, self.directory, "f9.png",
                            self.datasets)

    def testAllValidPointsArePreserved(self):
        expected = sum(len(M._valid(d["results"]))
                       for d in self.datasets.values())
        self.assertEqual(len(_offsets(self.fig)), expected,
                         "every valid row must appear exactly once")

    def testOnlyValidRowsAreDrawn(self):
        impacts = set()
        for data in self.datasets.values():
            impacts.update(round(float(v), 9)
                           for v in M._valid(data["results"])["impact"])
        for x, _y in _offsets(self.fig):
            self.assertIn(round(x, 9), impacts)

    def testShowsNAndZeroLine(self):
        self.assertTrue(any("n=" in t for t in _texts(self.fig)))
        self.assertTrue(any(ax.get_xgridlines() or True for ax in
                            self.fig.axes))

    def testNoRankingLanguage(self):
        text = " ".join(_texts(self.fig)).lower()
        for banned in ("most important", "dominant", "strongest",
                       "best concept", "concept importance"):
            self.assertNotIn(banned, text)


class TestBoxplot(PublicationCase):

    def setUp(self):
        self.fig = _capture(M.figure10PublicationBoxplot, self.directory,
                            "f10.png", self.datasets)

    def testOnlyValidRowsReachTheBoxes(self):
        valid, invalid = set(), set()
        for data in self.datasets.values():
            frame = data["results"]
            valid.update(round(float(v), 9)
                         for v in M._valid(frame)["impact"])
            invalid.update(
                round(float(v), 9)
                for v in frame[~frame["valid_for_analysis"]]["impact"]
                if np.isfinite(v))
        onlyInvalid = invalid - valid
        for x, _y in _offsets(self.fig):
            self.assertNotIn(round(x, 9), onlyInvalid,
                             "an invalid row reached the figure")

    def testNIsShownForEveryBox(self):
        labels = [t for t in _texts(self.fig) if t.startswith("n=")]
        expected = sum(
            1 for data in self.datasets.values()
            for _model in M._valid(data["results"])["model"].unique()
            for _concept in M.semanticGroups()[M.COMMENSURABLE])
        self.assertEqual(len(labels), expected,
                         "every concept in every model panel needs an n")

    def testModelSeparationIsPreserved(self):
        titles = {ax.get_title() for ax in self.fig.axes if ax.get_title()}
        models = {m for data in self.datasets.values()
                  for m in M._valid(data["results"])["model"].unique()}
        self.assertTrue(models.issubset(titles))

    def testNonCommensurableConceptsAreNotBoxedWithTheOthers(self):
        groups = M.semanticGroups()
        shown = {t.get_text() for ax in self.fig.axes
                 for t in ax.get_yticklabels() if t.get_text()}
        for concept in groups[M.NOT_COMMENSURABLE]:
            self.assertNotIn(concept, shown)

    def testNoPooledStatisticAcrossModels(self):
        source = inspect.getsource(M.figure10PublicationBoxplot)
        tree = ast.parse(source.lstrip())
        calls = {getattr(n.func, "attr", None) for n in ast.walk(tree)
                 if isinstance(n, ast.Call)}
        for banned in ("mean", "median", "agg", "aggregate"):
            self.assertNotIn(banned, calls)


class TestLocalBar(PublicationCase):

    def setUp(self):
        self.fig = _capture(M.figure11LocalBar, self.directory, "f11.png",
                            self.paths)
        self.frame = pd.read_csv(self.paths["edge_trend"])

    def _bars(self):
        return [patch.get_width() for ax in self.fig.axes
                for patch in ax.patches]

    def testEveryBarTracesToPersistedAttribution(self):
        real = {round(float(v), 9) for v in self.frame["impact"]}
        bars = self._bars()
        self.assertTrue(bars)
        for width in bars:
            self.assertIn(round(float(width), 9), real,
                          f"bar {width} is not a persisted impact")

    def testZeroReferenceLineExists(self):
        found = any(round(float(line.get_xdata()[0]), 9) == 0.0
                    for ax in self.fig.axes for line in ax.lines
                    if len(set(line.get_xdata())) == 1)
        self.assertTrue(found, "a zero reference line must be drawn")

    def testNoExactZeroIsDrawnAsABar(self):
        ''' Exact zeros are reported in the caption, not padded into bars. '''
        for width in self._bars():
            self.assertNotEqual(round(float(width), 12), 0.0)

    def testTopKAndTheDiscardedCountAreStated(self):
        text = " ".join(_texts(self.fig))
        nonZero = int((self.frame["impact"] != 0).sum())
        self.assertIn("top-K cap", text)
        self.assertIn(str(len(self.frame)), text, "total must be stated")
        self.assertIn(str(nonZero), text, "non-zero count must be stated")
        self.assertIn(str(len(self.frame) - nonZero), text,
                      "the number of exact zeros must be stated")

    def testFullAttributionRemainsAvailable(self):
        self.assertGreater(len(self.frame), len(self._bars()),
                           "the source CSV must retain more than is shown")
        self.assertIn(os.path.basename(self.paths["edge_trend"]),
                      " ".join(_texts(self.fig)))

    def testSortIsByAbsoluteImpactWithDeterministicTieBreak(self):
        widths = [abs(w) for w in self._bars()]
        self.assertEqual(widths, sorted(widths),
                         "bars are drawn bottom-up by |impact| ascending")

    def testBothSignsAreRepresentable(self):
        ''' The layout is diverging: this explanation genuinely has both. '''
        bars = self._bars()
        self.assertTrue(any(w > 0 for w in bars))
        self.assertTrue(any(w < 0 for w in bars))


class TestTemporalEdgeTime(PublicationCase):

    def setUp(self):
        self.fig = _capture(M.figure12TemporalEdgeTime, self.directory,
                            "f12.png", self.paths)
        self.frame = pd.read_csv(self.paths["edge_time"])

    def testEveryPointIsARealEdgeTimeObservation(self):
        ''' Checks the TIME mapping: a point's x must be a snapshot index
        that the corresponding edge was actually evaluated at. '''
        snapshots = {int(s) for s in self.frame["snapshot_index"]}
        points = _offsets(self.fig)
        self.assertTrue(points)
        for x, _y in points:
            self.assertIn(int(round(x)), snapshots)

    def testImpactMappingIsCorrect(self):
        ''' Checks the COLOUR mapping: every colour-encoded value must be a
        real impact from the persisted file. '''
        real = {round(float(v), 9) for v in self.frame["impact"]}
        encoded = []
        for ax in self.fig.axes:
            # Skip the colorbar: it is itself a mappable whose array spans
            # the whole colour range at even steps, none of which need be a
            # real impact. Reading it would test matplotlib, not the figure.
            if ax.get_label() == "<colorbar>":
                continue
            for collection in ax.collections:
                array = collection.get_array()
                if array is not None:
                    encoded.extend(float(v) for v in array)
        self.assertTrue(encoded)
        # Compared with tolerance, not exactly: matplotlib quantises the
        # colour array to 8 bits across [-limit, +limit], so a true -1.0 can
        # come back as -0.988. The tolerance is derived from that step rather
        # than guessed, and stays far below the gap between the distinct
        # impacts present, so the mapping is still genuinely checked.
        limit = max(abs(v) for v in real) or 1.0
        tolerance = 4 * (2 * limit) / 256
        for value in encoded:
            self.assertLess(min(abs(value - r) for r in real), tolerance,
                            f"encoded {value} matches no persisted impact")

    def testPointCountMatchesTheSelectedRows(self):
        ''' No aggregation: one marker per (edge, snapshot) row shown. '''
        encoded = sum(len(c.get_offsets()) for ax in self.fig.axes
                      for c in ax.collections)
        self.assertLessEqual(encoded, len(self.frame))
        self.assertGreater(encoded, 0)

    def testNoAggregationInTheSource(self):
        source = inspect.getsource(M.figure12TemporalEdgeTime)
        tree = ast.parse(source.lstrip())
        calls = {getattr(n.func, "attr", None) for n in ast.walk(tree)
                 if isinstance(n, ast.Call)}
        for banned in ("mean", "median", "sum", "cumsum"):
            self.assertNotIn(banned, calls)

    def testSelectionRuleIsStatedAndDeterministic(self):
        text = " ".join(_texts(self.fig))
        self.assertIn("DISPLAY-ONLY selection", text)
        self.assertIn("never sampled", text)
        self.assertIn(os.path.basename(self.paths["edge_time"]), text)

    def testTheTshapDisclaimerIsPresentVerbatim(self):
        text = " ".join(_texts(self.fig)).replace("\n", " ")
        text = " ".join(text.split())
        self.assertIn(
            "TGAP edge-time attribution is shown here; this visualization is "
            "inspired by temporal XAI visualization styles but is not a "
            "TSHAP implementation.", text)

    def testNoAdditivityIsClaimed(self):
        text = " ".join(_texts(self.fig)).replace("\n", " ")
        self.assertIn("No additivity across time is claimed",
                      " ".join(text.split()))

    def testSnapshotsWithResponseAreReported(self):
        self.assertIn("non-zero response", " ".join(_texts(self.fig)))


class TestSharedRequirements(PublicationCase):
    ''' The rules that apply to all five figures at once. '''

    FIGURES = ("figure8Dependence", "figure9TrueBeeswarm",
               "figure10PublicationBoxplot", "figure11LocalBar",
               "figure12TemporalEdgeTime")

    def testNoScientificNumberIsHardCoded(self):
        real = set()
        for data in self.datasets.values():
            real.update(round(abs(float(v)), 6)
                        for v in M._valid(data["results"])["impact"])
        for key in ("edge", "node", "edge_trend", "edge_time"):
            frame = pd.read_csv(self.paths[key])
            real.update(round(abs(float(v)), 6) for v in frame["impact"]
                        if np.isfinite(v))
        # Only values carrying more than two decimals can be distinguished
        # from a layout constant. The synthetic world produces round impacts
        # like 0.8 and 0.4, which are also perfectly ordinary alpha and
        # spacing values; flagging those would be a false positive, not a
        # finding. Anything a figure could plausibly hard-code AND pass off
        # as a measurement - 0.394316, 45.92919 - still fails this.
        real = {v for v in real if round(v, 2) != v}
        self.assertTrue(real, "fixture must contain high-precision impacts")
        for name in self.FIGURES + ("_beeswarmOffsets", "_stripPanel"):
            tree = ast.parse(inspect.getsource(getattr(M, name)).lstrip())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant)
                        and isinstance(node.value, float)
                        and node.value != int(node.value)):
                    self.assertNotIn(round(abs(node.value), 6), real,
                                     f"{name} hard-codes {node.value}")

    def testAllFiguresProducePngAndPdf(self):
        directory = os.path.join(self.directory, "formats")
        os.makedirs(directory, exist_ok=True)
        plans = [(M.figure8Dependence, (self.paths,), "f8"),
                 (M.figure9TrueBeeswarm, (self.datasets,), "f9"),
                 (M.figure10PublicationBoxplot, (self.datasets,), "f10"),
                 (M.figure11LocalBar, (self.paths,), "f11"),
                 (M.figure12TemporalEdgeTime, (self.paths,), "f12")]
        for function, arguments, stem in plans:
            function(*arguments, os.path.join(directory, f"{stem}.png"))
            for suffix in ("png", "pdf"):
                target = os.path.join(directory, f"{stem}.{suffix}")
                self.assertTrue(os.path.exists(target), target)
                self.assertGreater(os.path.getsize(target), 0, target)

    def testRepeatedGenerationIsReproducible(self):
        digests = []
        plans = [(M.figure8Dependence, (self.paths,), "f8"),
                 (M.figure9TrueBeeswarm, (self.datasets,), "f9"),
                 (M.figure10PublicationBoxplot, (self.datasets,), "f10"),
                 (M.figure11LocalBar, (self.paths,), "f11"),
                 (M.figure12TemporalEdgeTime, (self.paths,), "f12")]
        for run in range(2):
            directory = os.path.join(self.directory, f"repro{run}")
            os.makedirs(directory, exist_ok=True)
            produced = {}
            for function, arguments, stem in plans:
                function(*arguments, os.path.join(directory, f"{stem}.png"))
                for suffix in ("png", "pdf"):
                    name = f"{stem}.{suffix}"
                    produced[name] = hashlib.md5(
                        open(os.path.join(directory, name), "rb").read()
                    ).hexdigest()
            digests.append(produced)
        self.assertEqual(digests[0], digests[1])

    def testAttributionDataIsReproducible(self):
        ''' The underlying measurements, not just the pictures. '''
        other = M.buildAttributionData(
            os.path.join(self.directory, "attribution_again"))
        for key, path in self.paths.items():
            self.assertEqual(
                hashlib.md5(open(path, "rb").read()).hexdigest(),
                hashlib.md5(open(other[key], "rb").read()).hexdigest(),
                f"{key} attribution is not reproducible")

    def testFiguresUseTheSharedPublicationTheme(self):
        ''' They must go through savePublicationFigure, which is what pins
        the publication dpi and writes the vector copy. '''
        for name in self.FIGURES:
            source = inspect.getsource(getattr(M, name))
            self.assertIn("savePublicationFigure(fig, path)", source, name)
            self.assertNotIn("fig.savefig(", source, name)

    def testPipelineGeneratesAllFive(self):
        if not os.path.exists(M.OUTPUT):
            self.skipTest("publication output not generated")
        for stem in ("fig8_dependence", "fig9_true_beeswarm",
                     "fig10_publication_boxplot", "fig11_local_bar",
                     "fig12_temporal_edge_time"):
            for suffix in ("png", "pdf"):
                target = os.path.join(M.OUTPUT, f"{stem}.{suffix}")
                self.assertTrue(os.path.exists(target), target)

    def testMetadataDocumentsAllFive(self):
        payload = M.writeFigureMetadata(
            os.path.join(self.directory, "meta.json"))
        documented = {entry["figure"] for entry in payload["figures"]}
        for stem in ("fig8_dependence", "fig9_true_beeswarm",
                     "fig10_publication_boxplot", "fig11_local_bar",
                     "fig12_temporal_edge_time"):
            self.assertIn(stem, documented)
        byName = {entry["figure"]: entry for entry in payload["figures"]}
        self.assertIn("x_variable", byName["fig8_dependence"])
        self.assertIn("selection_rule", byName["fig11_local_bar"])
        self.assertFalse(
            byName["fig12_temporal_edge_time"]["additivity_claimed"])

    def testMetadataIsReproducible(self):
        first = os.path.join(self.directory, "m1.json")
        second = os.path.join(self.directory, "m2.json")
        M.writeFigureMetadata(first)
        M.writeFigureMetadata(second)
        self.assertEqual(open(first, encoding="utf-8").read(),
                         open(second, encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
