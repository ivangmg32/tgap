'''
The wrapper must make a new study take a few lines, and must say in plain
English what is wrong when those lines are wrong.

  * every example in examples/wrapper/ runs and writes its outputs;
  * functions, objects with predict, built-in names and decorators all work;
  * the check() before explaining catches the usual mistakes.
'''

import contextlib
import io
import os
import random
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest

import paths
from core import TemporalGraphTransformation
from examples import toolkit
from tgap_wrapper import Wrapper

WRAPPER_EXAMPLES = os.path.join(paths.ROOT, "examples", "wrapper")
EXPECTED = ("explanation.csv", "explanation.png", "sensitivity.csv",
            "sensitivity.png", "graph_over_time.csv", "graph_over_time.png",
            "TUTORIAL.md",
            # the paper-style pictures
            "what_changed.png", "when_it_mattered.png", "edge_impact.png",
            "edge_over_time.png", "node_impact.png", "impact_heatmap.png",
            # the global (many-window) pictures and their data
            "beeswarm.png", "boxplot.png", "dependence.png",
            "global_impacts.csv", "global_summary.csv",
            "how_tgap_works.png",
            # the diagnostic pictures
            "side_effects.png", "concept_trajectories.png",
            "validity_map.png", "impacts_by_direction.png",
            "impact_distribution.png", "sparsity.png", "tsap_summary.png")


class WrapperCase(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="tgap-wrapper-")
        self.saved = toolkit.OUTPUT
        toolkit.OUTPUT = self.directory
        self.w = Wrapper.synthetic("study")

    def tearDown(self):
        toolkit.OUTPUT = self.saved
        shutil.rmtree(self.directory, ignore_errors=True)

    def quiet(self, function, *args, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return function(*args, **kwargs)


class TestWrapperExamples(WrapperCase):

    def testEveryExampleRunsAndWritesItsOutputs(self):
        names = sorted(n for n in os.listdir(WRAPPER_EXAMPLES)
                       if n[:2].isdigit() and n.endswith(".py"))
        self.assertGreaterEqual(len(names), 6)
        for name in names:
            with self.subTest(example=name):
                self.quiet(runpy.run_path,
                           os.path.join(WRAPPER_EXAMPLES, name),
                           run_name="wrapper_example_under_test")
                folder = os.path.join(self.directory,
                                      "wrapper_" + name[:-3])
                for expected in EXPECTED:
                    path = os.path.join(folder, expected)
                    self.assertTrue(os.path.exists(path), path)
                    self.assertGreater(os.path.getsize(path), 0, path)


class TestPaperFigures(WrapperCase):

    def testFiguresCanBeTurnedOffAndNeverBreakTheStudy(self):
        self.w.model("trend_bridge_width")
        self.w.concept(["bridge_width", "density"])
        self.quiet(self.w.explain, figures=False)
        folder = os.path.join(self.directory, "study")
        self.assertTrue(os.path.exists(os.path.join(folder,
                                                    "explanation.png")))
        self.assertFalse(os.path.exists(os.path.join(folder,
                                                     "what_changed.png")))

    def testTutorialShowsAndExplainsThePictures(self):
        self.w.model("trend_bridge_width")
        self.w.concept(["bridge_width", "density"])
        self.quiet(self.w.explain)
        with open(os.path.join(self.directory, "study", "TUTORIAL.md"),
                  encoding="utf-8") as handle:
            text = handle.read()
        for name in ("what_changed.png", "when_it_mattered.png",
                     "edge_impact.png", "impact_heatmap.png"):
            self.assertIn("]({0})".format(name), text)
        self.assertIn("Looking inside", text)

    def testGlobalPicturesCoverManyWindowsAndAreReproducible(self):
        import pandas as pd
        self.w.model("trend_bridge_width")
        self.w.concept(["bridge_width", "density"])
        self.quiet(self.w.explain)
        path = os.path.join(self.directory, "study", "global_impacts.csv")
        first = pd.read_csv(path)
        self.assertGreater(first["window_first_snapshot"].nunique(), 2)
        self.assertEqual(set(first["concept"]), {"Bridge Width", "Density"})
        summary = pd.read_csv(os.path.join(self.directory, "study",
                                           "global_summary.csv"))
        self.assertTrue((summary["observations"] > 10).all())
        self.quiet(self.w.explain)                    # same inputs ...
        pd.testing.assert_frame_equal(first, pd.read_csv(path))  # ... same data

    def testModelThatIgnoresEveryTieStillGivesAnHonestPicture(self):
        self.w.model(lambda snapshots: 1.0)
        self.w.concept("density")
        self.quiet(self.w.explain)
        folder = os.path.join(self.directory, "study")
        self.assertGreater(os.path.getsize(
            os.path.join(folder, "edge_impact.png")), 3000)

    def testAFailingPictureIsSkippedNotFatal(self):
        from examples import figures
        saved = figures.edgeImpact
        figures.edgeImpact = lambda *a, **k: 1 / 0
        try:
            self.w.model("trend_bridge_width")
            self.w.concept("density")
            self.quiet(self.w.explain)
        finally:
            figures.edgeImpact = saved
        folder = os.path.join(self.directory, "study")
        self.assertTrue(os.path.exists(os.path.join(folder,
                                                    "what_changed.png")))
        self.assertFalse(os.path.exists(os.path.join(folder,
                                                     "edge_impact.png")))


class TestWaysToAddThings(WrapperCase):

    def testModelAsFunctionDecoratorObjectAndName(self):
        @self.w.model
        def mine(snapshots):
            return float(len(snapshots))
        self.assertEqual(self.w._model.predict(self.w.snapshots), 6.0)
        self.assertTrue(callable(mine))          # decorator returns it

        class Trained(object):
            def predict(self, snapshots):
                return 2.5
        self.w.model(Trained())
        self.assertEqual(self.w._model.predict(self.w.snapshots), 2.5)

        self.w.model(lambda g: g.number_of_edges(), on="last")
        self.assertEqual(self.w._model.predict(self.w.snapshots),
                         self.w.snapshots[-1].number_of_edges())

        self.w.model("trend_bridge_width")
        self.assertIsInstance(self.w._model.predict(self.w.snapshots), float)

    def testConceptAsFunctionInPlaceAndReturning(self):
        @self.w.concept
        def drop_ties(graph, delta):             # edits in place, returns None
            graph.remove_edges_from(
                list(graph.edges())[:round(abs(delta) * 10)])

        @self.w.concept(name="Copy Style", keepsEdgeCount=False)
        def copy_style(graph, delta):
            return graph.copy()

        self.assertEqual([c.name for c in self.w.concepts],
                         ["Drop Ties", "Copy Style"])
        original = self.w.snapshots[0].number_of_edges()
        self.w.concepts[0].transform(self.w.snapshots, 0.5)
        self.assertEqual(self.w.snapshots[0].number_of_edges(), original)

    def testConceptWithSeededRngIsRepeatable(self):
        @self.w.concept(keepsEdgeCount=False)
        def random_tie(graph, delta, rng):
            nodes = sorted(graph)
            graph.add_edge(rng.choice(nodes), rng.choice(nodes))
        first = self.w.concepts[0].transform(self.w.snapshots, 0.1)
        second = self.w.concepts[0].transform(self.w.snapshots, 0.1)
        self.assertEqual([sorted(g.edges()) for g in first],
                         [sorted(g.edges()) for g in second])

    def testBuiltinsByNameAndList(self):
        self.w.concept(["bridge_width", "density"])
        self.w.concept("churn")
        self.assertEqual([c.name for c in self.w.concepts],
                         ["Bridge Width", "Density", "Churn"])

    def testMeasureAveragesOverTheHistory(self):
        self.w.concept(lambda g, d: g, name="Edges",
                       measure=lambda g: g.number_of_edges())
        expected = sum(g.number_of_edges() for g in self.w.snapshots) / 6
        self.assertAlmostEqual(self.w.concepts[0].propertyValue(
            self.w.snapshots), expected)

    def testOverTimeConceptMeasuresTheWholeHistory(self):
        self.w.concept(overTime=lambda snaps, d: snaps, name="Span",
                       measure=lambda snaps: float(len(snaps)))
        self.assertEqual(self.w.concepts[0].propertyValue(self.w.snapshots),
                         6.0)

    def testDuplicateNamesAreRefused(self):
        self.w.concept("density")
        with self.assertRaisesRegex(ValueError, "already added"):
            self.w.concept("density")

    def testBadConceptArgumentsExplainThemselves(self):
        with self.assertRaisesRegex(TypeError, "built-in name"):
            self.w.concept(42)
        with self.assertRaisesRegex(ValueError, "Unknown transformation"):
            self.w.concept("nonsense")
        with self.assertRaisesRegex(ValueError, "Unknown model"):
            self.w.model("nonsense")


class TestCheckExplainsMistakes(WrapperCase):

    def testNothingAddedYet(self):
        with self.assertRaisesRegex(ValueError, "No model yet"):
            self.w.explain()
        self.w.model(lambda s: 1.0)
        with self.assertRaisesRegex(ValueError, "No concepts yet"):
            self.w.explain()

    def testModelThatCrashes(self):
        self.w.model(lambda s: 1 / 0)
        self.w.concept("density")
        with self.assertRaisesRegex(ValueError, "model failed.*ZeroDivision"):
            self.quiet(self.w.check)

    def testModelThatReturnsNotANumber(self):
        for bad in ("text", [1.0], float("nan"), None):
            with self.subTest(value=bad):
                self.w.model(lambda s, b=bad: b)
                self.w.concept("density") if not self.w.concepts else None
                with self.assertRaisesRegex(ValueError, "ONE finite number"):
                    self.quiet(self.w.check)

    def testConceptThatCrashes(self):
        self.w.model(lambda s: 1.0)
        self.w.concept(lambda g, d: 1 / 0, name="Boom")
        with self.assertRaisesRegex(ValueError, "'Boom' failed"):
            self.quiet(self.w.check)

    def testConceptThatReturnsNonsense(self):
        self.w.model(lambda s: 1.0)
        self.w.concept(lambda g, d: "not a graph", name="Nonsense")
        with self.assertRaisesRegex(ValueError, "must return a graph"):
            self.quiet(self.w.check)

    def testClassConceptThatEditsTheOriginalIsRefused(self):
        class Careless(TemporalGraphTransformation):
            name = "Careless"

            def transformGraph(self, graph, delta):
                graph.add_edge("a-new", "node")          # edits the input!
                return graph
        self.w.model(lambda s: 1.0)
        self.w.concept(Careless())
        with self.assertRaisesRegex(ValueError, "changed the ORIGINAL"):
            self.quiet(self.w.check)

    def testWarnings(self):
        self.w.model(lambda s: 1.0)
        counter = [0]

        def unrepeatable(graph, delta):
            counter[0] += 1
            graph.add_edge(*random.Random(counter[0]).sample(
                sorted(graph), 2))
        self.w.concept(unrepeatable, name="Unrepeatable",
                       keepsEdgeCount=False, measure=lambda g: 1.0)
        self.w.concept(lambda g, d: g.add_node("stranger"),
                       name="Adds People", keepsEdgeCount=False)
        self.w.concept(lambda g, d: g.remove_edge(*next(iter(g.edges()))),
                       name="Breaks Promise")
        text = "\n".join(self.quiet(self.w.check))
        self.assertIn("Unrepeatable: gives different graphs", text)
        self.assertIn("Adds People: adds or removes PEOPLE", text)
        self.assertIn("Breaks Promise: promised to keep the number of ties",
                      text)
        self.assertIn("has no measure", text)

    def testGoodSetupGivesNoWarnings(self):
        self.w.model("trend_bridge_width")
        self.w.concept(["bridge_width", "density"])
        self.assertEqual(self.quiet(self.w.check), [])

    def testTooFewSnapshots(self):
        with self.assertRaisesRegex(ValueError, "at least 2"):
            Wrapper("x", [])


@unittest.skipIf(os.name == "nt", "uses a shell launcher")
class TestTgapRunScript(unittest.TestCase):
    ''' `tgap run script FILE` runs any Python file, such as an example or
    your own wrapper study, inside the managed environment. '''

    def setUp(self):
        import json
        self.home = tempfile.mkdtemp(prefix="tgap-home-")
        os.makedirs(os.path.join(self.home, ".venv", "bin"))
        launcher = os.path.join(self.home, ".venv", "bin", "python")
        with open(launcher, "w") as handle:          # keeps THIS environment
            handle.write('#!/bin/sh\nexec "{0}" "$@"\n'.format(
                sys.executable))
        os.chmod(launcher, 0o755)
        with open(os.path.join(self.home, "installation.json"), "w") as f:
            json.dump({"source": paths.ROOT, "tgn": False}, f)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def run_tgap(self, *arguments, cwd=None):
        return subprocess.run(
            [sys.executable, "-B", os.path.join(paths.ROOT, "bootstrap.py"),
             "--home", self.home, "run", "script", *arguments],
            cwd=cwd, capture_output=True, text=True, timeout=300,
            env=dict(os.environ, TGAP_OUTPUT_TEST="1"))

    def testYourOwnFileOutsideTheRepositoryRuns(self):
        folder = tempfile.mkdtemp(prefix="tgap-mine-")
        try:
            with open(os.path.join(folder, "mine.py"), "w") as handle:
                handle.write("import tempfile\n"
                             "from tgap_wrapper import Wrapper\n"
                             "w = Wrapper.synthetic('script_test')\n"
                             "w.model('trend_bridge_width')\n"
                             "w.concept('density')\n"
                             "w.explain(folder=tempfile.mkdtemp())\n")
            result = self.run_tgap("mine.py", cwd=folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("The model predicts", result.stdout)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def testMissingFileIsExplained(self):
        result = self.run_tgap("nope.py")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("There is no file called nope.py", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        result = self.run_tgap()
        self.assertIn("Say which file to run", result.stderr)


class TestRunPyFile(unittest.TestCase):
    ''' `python run.py FILE.py` runs one file - an example or your own. '''

    def run_py(self, *arguments, cwd=None):
        return subprocess.run(
            [sys.executable, "-B", os.path.join(paths.ROOT, "run.py"),
             "--no-venv", *arguments], cwd=cwd, capture_output=True,
            text=True, timeout=300)

    def testYourOwnFileFromAnotherFolder(self):
        folder = tempfile.mkdtemp(prefix="tgap-runpy-")
        try:
            with open(os.path.join(folder, "mine.py"), "w") as handle:
                handle.write("import tempfile\n"
                             "from tgap_wrapper import Wrapper\n"
                             "w = Wrapper.synthetic('runpy_test')\n"
                             "w.model('trend_bridge_width')\n"
                             "w.concept('density')\n"
                             "w.explain(folder=tempfile.mkdtemp())\n")
            result = self.run_py("mine.py", cwd=folder)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("The model predicts", result.stdout)
            self.assertIn("Everything finished successfully", result.stdout)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def testMissingFileIsExplained(self):
        result = self.run_py("nope.py")
        self.assertEqual(result.returncode, 2)
        self.assertIn("There is no file called nope.py", result.stdout)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def testBrokenFileIsExplainedInPlainEnglish(self):
        folder = tempfile.mkdtemp(prefix="tgap-runpy-")
        try:
            with open(os.path.join(folder, "bad.py"), "w") as handle:
                handle.write("from tgap_wrapper import Wrapper\n"
                             "w = Wrapper.synthetic('x')\n"
                             "w.model(lambda s: 1 / 0)\n"
                             "w.concept('density')\n"
                             "w.explain()\n")
            result = self.run_py("bad.py", cwd=folder)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Your model failed on your data", result.stdout)
            self.assertNotIn("Traceback", result.stdout + result.stderr)
        finally:
            shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
