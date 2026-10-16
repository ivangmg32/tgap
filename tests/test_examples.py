'''
The easy examples and the one-file runner must keep working for everyone.

  * every example in examples/ runs and writes its CSV + PNG outputs;
  * the CSV loader accepts what people really have (Excel's semicolons,
    cp1252 encoding, day-first dates) and explains what it cannot accept;
  * run.py turns failures into plain-English messages, never tracebacks.

Nothing here touches the network or the real output/ folder.
'''

import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest

import paths
from examples import toolkit

EXAMPLES = os.path.join(paths.ROOT, "examples")
EXPECTED = ("explanation.csv", "explanation.png", "sensitivity.csv",
            "sensitivity.png", "graph_over_time.csv", "graph_over_time.png")


class ExampleCase(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="tgap-examples-")
        self.saved = toolkit.OUTPUT
        toolkit.OUTPUT = self.directory          # never write to output/

    def tearDown(self):
        toolkit.OUTPUT = self.saved
        shutil.rmtree(self.directory, ignore_errors=True)


class TestEveryExampleRuns(ExampleCase):

    def _run(self, filename, outputName):
        module = runpy.run_path(os.path.join(EXAMPLES, filename),
                                run_name="example_under_test")
        module["main"]()
        folder = os.path.join(self.directory, outputName)
        for name in EXPECTED:
            path = os.path.join(folder, name)
            self.assertTrue(os.path.exists(path), path)
            self.assertGreater(os.path.getsize(path), 0, path)

    def testQuickstart(self):
        self._run("01_quickstart.py", "01_quickstart")

    def testYourOwnDataset(self):
        self._run("02_your_own_dataset.py", "02_your_own_dataset")

    def testYourOwnModel(self):
        self._run("03_your_own_model.py", "03_your_own_model")

    def testYourOwnTransformation(self):
        self._run("04_your_own_transformation.py",
                  "04_your_own_transformation")

    def testProjectTemplate(self):
        self._run("06_my_project.py", "my_project")

    def testRealDatasetWhenCached(self):
        cached = os.path.join(paths.DATA, "email-Eu-core-temporal.txt.gz")
        if not os.path.exists(cached):
            self.skipTest("email_eu_core not downloaded (no network in tests)")
        self._run("05_real_dataset.py", "05_real_dataset_email_eu_core")

    def testEveryNumberedExampleIsCovered(self):
        numbered = sorted(n for n in os.listdir(EXAMPLES)
                          if n[:2].isdigit() and n.endswith(".py"))
        self.assertEqual(numbered, [
            "01_quickstart.py", "02_your_own_dataset.py",
            "03_your_own_model.py", "04_your_own_transformation.py",
            "05_real_dataset.py", "06_my_project.py"])


class TestLoadingYourCsv(ExampleCase):

    def _write(self, text, encoding="utf-8"):
        path = os.path.join(self.directory, "data.csv")
        with open(path, "wb") as handle:
            handle.write(text.encode(encoding))
        return path

    def testExcelStyleCsvIsAccepted(self):
        ''' Excel on a European Windows: ';', cp1252, day-first dates. '''
        path = self._write("source;target;time\n"
                           "José;Zoë;01/02/2024\nZoë;Ana;05/02/2024\n"
                           "Ana;José;20/03/2024\nJosé;Ana;01/04/2024\n",
                           encoding="cp1252")
        snapshots = toolkit.loadEdgeList(path, snapshots=2)
        self.assertEqual(sorted(snapshots[0].nodes()), ["Ana", "José", "Zoë"])
        self.assertEqual([g.number_of_edges() for g in snapshots], [2, 2])

    def testNumericTimeIsAccepted(self):
        path = self._write("a,b,t\n1,2,0\n2,3,5\n3,1,10\n")
        snapshots = toolkit.loadEdgeList(path, "a", "b", "t", snapshots=2)
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0].number_of_nodes(), 3)

    def testWrongColumnNameIsExplained(self):
        path = self._write("source,target,time\na,b,1\nb,c,2\n")
        with self.assertRaises(ValueError) as caught:
            toolkit.loadEdgeList(path, sourceColumn="sender")
        self.assertIn("'sender'", str(caught.exception))
        self.assertIn("'source'", str(caught.exception))

    def testTooFewSnapshotsIsExplained(self):
        path = self._write("source,target,time\na,b,1\nb,c,2\n")
        with self.assertRaises(ValueError):
            toolkit.loadEdgeList(path, snapshots=1)

    def testUnknownNamesAreExplained(self):
        with self.assertRaises(ValueError) as caught:
            toolkit.model("no_such_model", None)
        self.assertIn("trend_bridge_width", str(caught.exception))
        with self.assertRaises(ValueError):
            toolkit.transformations(["no_such_concept"], None)

    def testPeopleWithoutAGroupGetOne(self):
        edges = self._write("source,target,time\na,b,1\nb,c,2\nc,d,3\n")
        snapshots = toolkit.loadEdgeList(edges, snapshots=2)
        groups = os.path.join(self.directory, "groups.csv")
        with open(groups, "w", encoding="utf-8") as handle:
            handle.write("person,group\na,x\nb,y\n")
        communities = toolkit.loadGroups(groups, snapshots=snapshots)
        self.assertEqual(set().union(*communities), {"a", "b", "c", "d"})


class TestRunnerMessages(unittest.TestCase):
    ''' run.py must explain problems in plain English. '''

    @classmethod
    def setUpClass(cls):
        cls.runner = runpy.run_path(os.path.join(paths.ROOT, "run.py"),
                                 run_name="run_under_test")

    def testCommonFailuresHaveFriendlyMessages(self):
        import urllib.error
        explain = self.runner["explain"]
        cases = [
            (PermissionError(13, "denied", "results.csv"), "open in"),
            (urllib.error.URLError("getaddrinfo failed"), "internet"),
            (ModuleNotFoundError("x", name="torch"), "PyTorch"),
            (FileNotFoundError(2, "missing", "my.csv"), "not found"),
            (ValueError("bad value"), "setting"),
            (KeyboardInterrupt(), "Ctrl+C"),
        ]
        for failure, phrase in cases:
            title, explanation, fixes = explain(failure)
            text = " ".join([title, explanation] + list(fixes))
            self.assertIn(phrase.lower(), text.lower(), type(failure))
            self.assertTrue(fixes, type(failure))

    def testHelpAndUnknownStep(self):
        script = os.path.join(paths.ROOT, "run.py")
        shown = subprocess.run([sys.executable, script, "--help"],
                               capture_output=True, text=True, timeout=60)
        self.assertEqual(shown.returncode, 0)
        self.assertIn("python run.py all", shown.stdout)
        wrong = subprocess.run([sys.executable, script, "nonsense"],
                               capture_output=True, text=True, timeout=60)
        self.assertEqual(wrong.returncode, 2)
        self.assertIn("Unknown step", wrong.stdout)
        self.assertNotIn("Traceback", wrong.stdout + wrong.stderr)


if __name__ == "__main__":
    unittest.main()


class TestExampleProjects(unittest.TestCase):
    ''' Every project in examples/projects runs and writes its outputs,
    including the tutorial, into the folder it is given. '''

    PROJECTS = os.path.join(paths.ROOT, "examples", "projects")

    def testEveryProjectRunsAndWritesATutorial(self):
        import contextlib
        import io
        names = sorted(n for n in os.listdir(self.PROJECTS)
                       if os.path.isfile(os.path.join(self.PROJECTS, n,
                                                      "main.py")))
        self.assertGreaterEqual(len(names), 11)
        for name in names:
            with self.subTest(project=name):
                folder = tempfile.mkdtemp(prefix="tgap-project-")
                try:
                    module = runpy.run_path(
                        os.path.join(self.PROJECTS, name, "main.py"),
                        run_name="project_under_test")
                    with contextlib.redirect_stdout(io.StringIO()):
                        module["main"](output=folder)
                    tutorial = os.path.join(folder, "TUTORIAL.md")
                    self.assertTrue(os.path.exists(tutorial))
                    with open(tutorial, encoding="utf-8") as handle:
                        text = handle.read()
                    self.assertGreater(len(text), 500)
                    for image in [l.split("](")[1].rstrip(")") for l in
                                  text.splitlines() if l.startswith("![")]:
                        self.assertTrue(os.path.exists(os.path.join(
                            folder, image)), image)
                finally:
                    shutil.rmtree(folder, ignore_errors=True)

    def testEveryProjectHasTheStandardFiles(self):
        for name in sorted(os.listdir(self.PROJECTS)):
            folder = os.path.join(self.PROJECTS, name)
            if not os.path.isfile(os.path.join(folder, "main.py")):
                continue
            with self.subTest(project=name):
                self.assertTrue(os.path.exists(os.path.join(folder,
                                                            "README.md")))
                if not name.startswith("ivan_") or \
                        name == "ivan_market_contagion":
                    for part in ("model.py", "concept.py"):
                        self.assertTrue(os.path.exists(os.path.join(
                            folder, part)), part)
