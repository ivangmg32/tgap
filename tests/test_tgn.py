'''
Tests for the TGN model adapter.

Every test skips cleanly when PyTorch is absent, so the suite never depends
on a heavy optional dependency. What matters here is not that the network
is accurate - it is deliberately small and briefly trained - but that it
honours the contracts TGAP relies on:

  * predict(temporalGraph) -> float, i.e. Ivan's TemporalGraphModel
    interface and nothing more;
  * DETERMINISM, because TGAP's stability property depends on it. TGN keeps
    MEMORY between calls, so an adapter that forgot to reset it would make
    every prediction depend on the previous one and silently destroy
    stability. That is the single most important thing asserted below;
  * that TGAP needs no access to gradients, memory or attention.
'''

import unittest

from core import (
    BridgeWidthTransformation, CallCountingModel, DensityTransformation,
    TgapExplainer, makeTemporalGraph,
)
from core.TemporalGraphModel import TemporalGraphModel
from core.TgnModel import TORCH_AVAILABLE, buildTgn, requireTorch, trainTgn


@unittest.skipUnless(TORCH_AVAILABLE, "PyTorch / PyTorch Geometric absent")
class TestTgnAdapter(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.snapshots, cls.communities = makeTemporalGraph(
            nSnapshots=5, nPerCommunity=8, bridgeWidth=6, seed=1)
        cls.nodeCount = cls.snapshots[0].number_of_nodes() + 1
        cls.model = buildTgn(cls.nodeCount, seed=42)
        cls.losses = trainTgn(cls.model, cls.snapshots, epochs=3, seed=42)

    def testImplementsIvansContract(self):
        self.assertIsInstance(self.model, TemporalGraphModel)
        value = self.model.predict(self.snapshots)
        self.assertIsInstance(value, float)

    def testPredictionIsAProbability(self):
        value = self.model.predict(self.snapshots)
        self.assertGreater(value, 0.0)
        self.assertLess(value, 1.0)

    def testPredictionIsDeterministic(self):
        ''' THE critical test. TGN carries memory across calls; without the
        reset in predict(), call n would depend on call n-1 and TGAP's
        stability guarantee would silently fail. '''
        first = self.model.predict(self.snapshots)
        second = self.model.predict(self.snapshots)
        third = self.model.predict(self.snapshots)
        self.assertEqual(first, second)
        self.assertEqual(second, third)

    def testPredictionSurvivesInterleavedCalls(self):
        ''' Predicting a DIFFERENT graph in between must not change the
        answer - the exact situation TGAP creates when it alternates
        baseline and perturbed inputs. '''
        before = self.model.predict(self.snapshots)
        perturbed = DensityTransformation(self.communities, seed=1).transform(
            self.snapshots, 0.5)
        self.model.predict(perturbed)
        self.assertEqual(self.model.predict(self.snapshots), before)

    def testTrainingReducesLoss(self):
        ''' Not a performance claim - just evidence the model is a genuinely
        learned function rather than a random one. '''
        self.assertEqual(len(self.losses), 3)
        self.assertLess(self.losses[-1], self.losses[0])

    def testTrainingIsReproducible(self):
        again = buildTgn(self.nodeCount, seed=42)
        losses = trainTgn(again, self.snapshots, epochs=3, seed=42)
        self.assertEqual([round(x, 6) for x in losses],
                         [round(x, 6) for x in self.losses])

    def testEmptyInputDoesNotCrash(self):
        self.assertEqual(self.model.predict([]), 0.0)

    def testTgapExplainsTheLearnedModel(self):
        transformations = [
            BridgeWidthTransformation(self.communities, seed=42),
            DensityTransformation(self.communities, seed=42)]
        explanation = TgapExplainer(self.model, transformations).explain(
            self.snapshots)
        self.assertEqual(len(explanation), 4)
        for label, value in explanation.items():
            self.assertFalse(value != value, f"{label} is NaN")

    def testModelCallBudgetHoldsForTheLearnedModel(self):
        transformations = [
            BridgeWidthTransformation(self.communities, seed=42),
            DensityTransformation(self.communities, seed=42)]
        counter = CallCountingModel(self.model)
        TgapExplainer(counter, transformations).explain(self.snapshots)
        self.assertEqual(counter.calls, 1 + 2 * len(transformations))

    def testTgapNeverTouchesModelInternals(self):
        ''' Section 20: TGAP must not depend on gradients, hidden layers or
        memory internals. Asserted by handing the explainer a wrapper that
        exposes ONLY predict, and checking it still works. '''

        class PredictOnly(TemporalGraphModel):
            def __init__(self, inner):
                self._inner = inner

            def predict(self, temporalGraph):
                return self._inner.predict(temporalGraph)

        explanation = TgapExplainer(
            PredictOnly(self.model),
            [DensityTransformation(self.communities, seed=42)]
        ).explain(self.snapshots)
        self.assertEqual(len(explanation), 2)


class TestTgnOptionalDependency(unittest.TestCase):
    ''' The package must remain usable without torch. '''

    def testRequireTorchMessageIsActionable(self):
        if TORCH_AVAILABLE:
            requireTorch()          # must not raise when present
            return
        with self.assertRaises(ImportError) as caught:
            requireTorch()
        self.assertIn("pip install torch", str(caught.exception))

    def testCoreImportsWithoutTorch(self):
        ''' core/ must never hard-depend on torch: importing the package has
        to work on a machine that has never installed it. '''
        import importlib
        import core
        importlib.reload(core)
        self.assertTrue(hasattr(core, "TgapExplainer"))



@unittest.skipUnless(TORCH_AVAILABLE, "PyTorch / PyTorch Geometric absent")
class TestHeldOutEvaluation(unittest.TestCase):
    ''' Training loss falling does not prove a model learned anything
    GENERALISABLE - it can fall while the model memorises. These tests cover
    the held-out protocol, and the regression that made it necessary. '''

    @classmethod
    def setUpClass(cls):
        from core.TgnModel import evaluateTgn, splitTemporally
        cls.evaluateTgn, cls.splitTemporally = staticmethod(evaluateTgn), \
            staticmethod(splitTemporally)
        cls.snapshots, _ = makeTemporalGraph(
            nSnapshots=10, nPerCommunity=8, bridgeWidth=6, seed=1)

    def testSplitIsTemporalNotRandom(self):
        ''' Every test snapshot must come strictly AFTER every training one.
        A random split would leak the future into training and report a
        score nobody could achieve in practice. '''
        train, test = self.splitTemporally(self.snapshots, 0.7)
        self.assertTrue(train and test)
        self.assertEqual(len(train) + len(test), len(self.snapshots))
        # Identity, not equality: the test part must be the literal tail.
        for index, graph in enumerate(test):
            self.assertIs(graph, self.snapshots[len(train) + index])

    def testSplitAlwaysLeavesSomethingToEvaluate(self):
        for fraction in (0.1, 0.5, 0.9, 0.99):
            train, test = self.splitTemporally(self.snapshots, fraction)
            self.assertTrue(train, f"fraction {fraction} left no training data")
            self.assertTrue(test, f"fraction {fraction} left nothing held out")

    def testMemoryDiffersAcrossNodes(self):
        ''' REGRESSION. TGN was given all-zero messages while memory also
        starts at zero, so every node's memory updated identically - a
        symmetry that never broke. Every embedding was then the same, every
        candidate link scored the same, and held-out AUC was EXACTLY 0.500
        however long it trained. Messages now carry endpoint degrees, which
        is real structural signal. If memory ever becomes uniform again,
        this test fails before anyone publishes an explanation of a model
        that cannot tell two nodes apart. '''
        import torch
        train, _ = self.splitTemporally(self.snapshots, 0.7)
        model = buildTgn(self.snapshots[0].number_of_nodes() + 1, seed=42)
        trainTgn(model, train, epochs=5, seed=42)
        model.memory.reset_state()
        model.neighborLoader.reset_state()
        with torch.no_grad():
            for source, destination, time, message in model._eventsFrom(train):
                model.memory.update_state(source, destination, time, message)
                model.neighborLoader.insert(source, destination)
            memory, _ = model.memory(torch.arange(10))
        self.assertGreater(float(memory.std(dim=0).mean()), 0.0,
                           "TGN memory is identical for every node")

    def testEvaluationReportsBalancedClassesAndChanceLevel(self):
        train, test = self.splitTemporally(self.snapshots, 0.7)
        model = buildTgn(self.snapshots[0].number_of_nodes() + 1, seed=42)
        result = self.evaluateTgn(model, train, test, seed=42)
        self.assertEqual(result["positives"], result["negatives"],
                         "classes must be balanced for chance to be 0.5")
        self.assertEqual(result["chance_level"], 0.5)
        for key in ("average_precision", "auc", "accuracy"):
            self.assertGreaterEqual(result[key], 0.0)
            self.assertLessEqual(result[key], 1.0)

    def testEvaluationIsDeterministic(self):
        train, test = self.splitTemporally(self.snapshots, 0.7)
        model = buildTgn(self.snapshots[0].number_of_nodes() + 1, seed=42)
        trainTgn(model, train, epochs=3, seed=42)
        first = self.evaluateTgn(model, train, test, seed=42)
        second = self.evaluateTgn(model, train, test, seed=42)
        self.assertEqual(first["auc"], second["auc"])
        self.assertEqual(first["average_precision"],
                         second["average_precision"])

    def testAveragePrecisionAndAucOnKnownInput(self):
        ''' The two metrics are implemented by hand (to avoid a
        scikit-learn dependency), so they are checked against cases whose
        answer is known by inspection. '''
        from core.TgnModel import _areaUnderRoc, _averagePrecision
        # Perfect ranking: every positive above every negative.
        self.assertAlmostEqual(_averagePrecision([0.9, 0.8, 0.2, 0.1],
                                                 [1, 1, 0, 0]), 1.0)
        self.assertAlmostEqual(_areaUnderRoc([0.9, 0.8, 0.2, 0.1],
                                             [1, 1, 0, 0]), 1.0)
        # Inverted ranking.
        self.assertAlmostEqual(_areaUnderRoc([0.1, 0.2, 0.8, 0.9],
                                             [1, 1, 0, 0]), 0.0)
        # All tied - the degenerate case the regression above produced.
        self.assertAlmostEqual(_areaUnderRoc([0.5] * 4, [1, 1, 0, 0]), 0.5)

if __name__ == "__main__":
    unittest.main()
