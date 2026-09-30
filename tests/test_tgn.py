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


if __name__ == "__main__":
    unittest.main()
