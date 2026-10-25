'''
Tests for the TGAP vs CoDy comparison (compare_explainers).

Two layers:
  * Unit and integration tests on a small slice of the REAL UCI-Messages
    stream (the first 2,500 messages) with a small untrained TGN, so every
    contract is exercised through the real code paths in about a minute.
  * Checks on the saved pilot record (output/compare_explainers), which
    verify the claims the comparison page makes about the real run.

Everything that needs PyTorch skips cleanly without it. Nothing is mocked
except where a test deliberately breaks an input to prove it is refused.
Numbers in the test names refer to the numbered requirements in
docs/17-tgap-vs-cody-comparison.md.
'''

import copy
import os
import unittest
from unittest import mock

import numpy as np

from core.TgnModel import TORCH_AVAILABLE
from core.Transformations import ChurnTransformation

from compare_explainers.config import (LATEST_RECORD, experimentId,
                                       pilotConfig)
from compare_explainers.dataset import (EventStream, archivePath,
                                        chronologicalSplit, historyBefore,
                                        loadUciMessages, streamFingerprint)

DATA_PRESENT = os.path.exists(archivePath(pilotConfig()))
SLICE = 2500


def smallSetup():
    from compare_explainers.tgn_backend import EventTgn, configureTorch
    config = pilotConfig(tgap={"window_days": 2},
                         cody={"max_steps": 6, "candidates_size": 16})
    configureTorch(1)
    full = loadUciMessages(config)
    stream = EventStream(np.array(full.src[:SLICE]), np.array(full.dst[:SLICE]),
                         np.array(full.ts[:SLICE]), full.num_nodes,
                         dict(full.provenance))
    backend = EventTgn(stream.num_nodes, config["model"])
    backend.eval()
    seen = set()
    first = {}
    for e in range(SLICE):
        for n in (int(stream.src[e]), int(stream.dst[e])):
            first.setdefault(n, e)
    for e in range(SLICE - 1, 1500, -1):
        a, b, t = int(stream.src[e]), int(stream.dst[e]), int(stream.ts[e])
        if (stream.ts == t).sum() == 1 and first[a] < e and first[b] < e:
            break
    target = {"event_id": e, "source": a, "destination": b, "timestamp": t}
    return config, full, stream, backend, target


@unittest.skipUnless(DATA_PRESENT, "data/tgbl-uci.zip absent")
class TestDataset(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.config = pilotConfig()
        cls.stream = loadUciMessages(cls.config)

    def test01_canonical_source_is_verified_and_fingerprinted(self):
        p = self.stream.provenance
        self.assertEqual(p["events"], 59835)
        self.assertEqual(p["nodes"], 1899)
        self.assertEqual(len(p["stream_sha256"]), 64)
        self.assertEqual(self.stream.fingerprint(), p["stream_sha256"])
        self.assertTrue(np.all(np.diff(self.stream.ts) >= 0))

    def test15_stream_is_immutable(self):
        with self.assertRaises(ValueError):
            self.stream.src[0] = 5

    def test05_split_is_chronological_and_stable(self):
        a = chronologicalSplit(self.stream, self.config)
        b = chronologicalSplit(self.stream, self.config)
        self.assertEqual(a, b)
        self.assertLess(self.stream.ts[a["train"][1] - 1],
                        self.stream.ts[a["test"][0]])
        self.assertEqual(a["test"][1], len(self.stream))

    def test04_history_excludes_target_and_simultaneous_events(self):
        ts = self.stream.ts
        unique = next(e for e in range(50000, 59000)
                      if (ts == ts[e]).sum() == 1)
        self.assertEqual(historyBefore(self.stream, unique), unique)
        self.assertTrue(np.all(ts[:unique] < ts[unique]))
        shared = next(e for e in range(1, 59000) if ts[e] == ts[e - 1])
        with self.assertRaises(ValueError):
            historyBefore(self.stream, shared)


@unittest.skipUnless(TORCH_AVAILABLE and DATA_PRESENT,
                     "PyTorch or data/tgbl-uci.zip absent")
class TestSharedBaseline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        (cls.config, cls.full, cls.stream, cls.backend,
         cls.target) = smallSetup()
        e = cls.target["event_id"]
        cls.history = (cls.stream.src[:e], cls.stream.dst[:e], cls.stream.ts[:e])
        cls.logit = cls.backend.scoreHistory(*cls.history,
                                             cls.target["source"],
                                             cls.target["destination"])
        from compare_explainers.pipeline import baselineConsistency
        cls.baseline = baselineConsistency(cls.backend, cls.stream, cls.target,
                                           {e: cls.logit}, cls.config,
                                           log=lambda *a: None)

    def test02_cody_dataset_holds_the_same_ids_and_timestamps(self):
        from compare_explainers.cody_adapter import codyDataset
        d = codyDataset(self.stream)
        self.assertTrue(np.array_equal(d.source_node_ids, self.stream.src))
        self.assertTrue(np.array_equal(d.target_node_ids, self.stream.dst))
        self.assertTrue(np.array_equal(d.timestamps, self.stream.ts))
        self.assertTrue(np.array_equal(d.edge_ids, self.stream.event_ids))

    def test03_06_all_paths_read_the_same_query_and_agree(self):
        b = self.baseline
        self.assertTrue(b["passed"], b["reasons"])
        self.assertEqual(b["max_abs_logit_difference"], 0.0)
        history = streamFingerprint(*self.history)
        for path in b["paths"].values():
            self.assertEqual(path["input_fingerprint"], history)
            self.assertEqual(path["logit"], self.logit)

    def test07_both_paths_query_the_same_weights(self):
        fingerprint = self.backend.parameterFingerprint()
        for name in ("tgap_adapter", "cody_wrapper"):
            self.assertEqual(self.baseline["paths"][name]
                             ["parameter_fingerprint"], fingerprint)

    def test08_memory_is_reset_and_rebuilt_for_every_history(self):
        a, b = self.target["source"], self.target["destination"]
        e = self.target["event_id"]
        shorter = self.backend.scoreHistory(self.stream.src[:e - 50],
                                            self.stream.dst[:e - 50],
                                            self.stream.ts[:e - 50], a, b)
        again = self.backend.scoreHistory(*self.history, a, b)
        self.assertEqual(again, self.logit)
        self.assertNotEqual(shorter, self.logit)

    def test09_no_stale_state_after_a_cody_style_branch(self):
        from compare_explainers.cody_adapter import codyDataset, makeWrapper
        wrapper = makeWrapper(self.backend, codyDataset(self.stream), 2)
        e = self.target["event_id"]
        wrapper.reset_model()
        wrapper.initialize(e - 40, memory_label="x")
        wrapper.compute_edge_probabilities_for_subgraph(
            e, np.arange(e - 30, e - 10), result_as_logit=True)
        wrapper.initialize(e - 40, memory_label="x")       # restore
        restored, _ = wrapper.compute_edge_probabilities_for_subgraph(
            e, np.array([], dtype=np.int64), result_as_logit=True)
        self.assertEqual(float(restored), self.logit)
        self.assertEqual(self.backend.scoreHistory(
            *self.history, self.target["source"], self.target["destination"]),
            self.logit)

    def test10_checkpoint_mismatch_is_an_error(self):
        import tempfile
        from compare_explainers.tgn_backend import (CheckpointMismatch,
                                                    loadCheckpoint,
                                                    saveCheckpoint)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "m.pt")
            sha = saveCheckpoint(self.backend, path, {})
            loaded, _ = loadCheckpoint(path, sha)
            self.assertEqual(loaded.parameterFingerprint(),
                             self.backend.parameterFingerprint())
            with self.assertRaises(CheckpointMismatch):
                loadCheckpoint(path, "0" * 64)

    def test10_22_assess_baseline_refuses_differences(self):
        from compare_explainers.pipeline import assessBaseline
        paths = copy.deepcopy(self.baseline["paths"])
        fingerprint = self.backend.parameterFingerprint()
        history = paths["direct_full_replay"]["input_fingerprint"]
        drifted = copy.deepcopy(paths)
        drifted["cody_wrapper"]["logit"] += 1e-3
        self.assertFalse(assessBaseline(drifted, history, fingerprint,
                                        1e-9)["passed"])
        other = copy.deepcopy(paths)
        other["tgap_adapter"]["parameter_fingerprint"] = "f" * 64
        verdict = assessBaseline(other, history, fingerprint, 1e-9)
        self.assertFalse(verdict["passed"])
        self.assertFalse(verdict["same_model"])
        wrongInput = copy.deepcopy(paths)
        wrongInput["cody_wrapper"]["input_fingerprint"] = "0" * 64
        self.assertFalse(assessBaseline(wrongInput, history, fingerprint,
                                        1e-9)["same_input"])


@unittest.skipUnless(TORCH_AVAILABLE and DATA_PRESENT,
                     "PyTorch or data/tgbl-uci.zip absent")
class TestTgapAdapter(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from compare_explainers.tgap_adapter import SnapshotView, runTgap
        (cls.config, cls.full, cls.stream, cls.backend,
         cls.target) = smallSetup()
        e = cls.target["event_id"]
        cls.view = SnapshotView(cls.stream.src[:e], cls.stream.dst[:e],
                                cls.stream.ts[:e], cls.target["timestamp"], 2)
        cls.originalEdges = [sorted(g.edges()) for g in cls.view.snapshots]
        cls.result = runTgap(cls.backend, cls.stream, cls.target, cls.config,
                             log=lambda *a: None)
        cls.primary = next(d for d in cls.result["directions"]
                           if d["direction"] == "Decrease")

    def test11_uses_the_existing_churn_definition(self):
        self.assertEqual(self.result["transformation"],
                         "core.Transformations.Churn.ChurnTransformation")
        churn = ChurnTransformation(communities=None, seed=42)
        self.assertEqual(self.result["plan"]["original_churn"],
                         churn.propertyValue(self.view.snapshots))
        self.assertEqual(self.primary["churn_before"],
                         churn.propertyValue(self.view.snapshots))
        transformed = churn.transform(self.view.snapshots, -0.2)
        self.assertEqual(self.primary["churn_after"],
                         churn.propertyValue(transformed))

    def test12_requested_and_achieved_are_separate_measurements(self):
        p = self.primary
        self.assertEqual(p["requested_delta"], -0.2)
        self.assertAlmostEqual(p["achieved_delta"],
                               (p["churn_after"] - p["churn_before"])
                               / abs(p["churn_before"]))
        self.assertAlmostEqual(p["achieved_delta"],
                               p["achieved_delta_recomputed"])
        if p["status"] == "valid":
            self.assertAlmostEqual(p["normalized_impact"],
                                   p["prediction_change"]
                                   / abs(p["achieved_delta"]))
        self.assertEqual(self.result["model_calls"], 3)

    def test13_latest_snapshot_is_preserved_and_enforced(self):
        from compare_explainers.tgap_adapter import LiftError
        self.assertTrue(self.primary["latest_snapshot_preserved"])
        broken = [g.copy() for g in self.view.snapshots]
        u, v = next(iter(broken[-1].edges()))
        broken[-1].remove_edge(u, v)
        with self.assertRaises(LiftError):
            self.view.lift(broken)

    def test14_unequal_swaps_are_invalid_and_tiny_requests_are_noops(self):
        from compare_explainers.tgap_adapter import LiftError, runTgap
        broken = [g.copy() for g in self.view.snapshots]
        u, v = next(iter(broken[0].edges()))
        broken[0].remove_edge(u, v)               # removal without an addition
        with self.assertRaises(LiftError):
            self.view.lift(broken)
        tiny = pilotConfig(tgap={"window_days": 2, "requested_delta": 1e-6})
        result = runTgap(self.backend, self.stream, self.target, tiny,
                         log=lambda *a: None)
        decrease = next(d for d in result["directions"]
                        if d["direction"] == "Decrease")
        self.assertTrue(decrease["noop"])
        self.assertEqual(decrease["status"], "noop")
        self.assertEqual(decrease["events_readdressed"], 0)

    def test15_original_input_is_never_mutated(self):
        self.assertEqual([sorted(g.edges()) for g in self.view.snapshots],
                         self.originalEdges)
        e = self.target["event_id"]
        self.assertTrue(np.array_equal(self.view.src, self.stream.src[:e]))
        self.assertFalse(self.view.src.flags.writeable)

    def test16_modified_stream_keeps_order_and_records_provenance(self):
        churn = ChurnTransformation(communities=None, seed=42)
        lifted = self.view.lift(churn.transform(self.view.snapshots, -0.2))
        self.assertTrue(lifted.roundTrip)
        self.assertTrue(np.array_equal(lifted.ts, self.view.ts))
        self.assertTrue(np.all(np.diff(lifted.ts) >= 0))
        self.assertEqual(len(lifted.changes), self.primary["events_readdressed"])
        for change in lifted.changes:
            e = change["event_id"]
            self.assertEqual(change["original"],
                             [int(self.view.src[e]), int(self.view.dst[e])])
            self.assertEqual(change["lifted"],
                             [int(lifted.src[e]), int(lifted.dst[e])])
        identical = lifted.fingerprint() == streamFingerprint(
            self.view.src, self.view.dst, self.view.ts)
        self.assertEqual(identical, not lifted.changes)

    def test17_unmappable_transformation_is_not_claimed(self):
        from compare_explainers.pipeline import comparability
        from compare_explainers import tgap_adapter

        def dropsAnEdge(self_, temporalGraph, delta):
            graphs = [g.copy() for g in temporalGraph]
            u, v = next(iter(graphs[0].edges()))
            graphs[0].remove_edge(u, v)
            return graphs
        with mock.patch.object(tgap_adapter.ChurnTransformation, "transform",
                               dropsAnEdge):
            result = tgap_adapter.runTgap(self.backend, self.stream,
                                          self.target, self.config,
                                          log=lambda *a: None)
        self.assertEqual(result["status"], "mapping_invalid")
        self.assertEqual(result["directions"], [])
        record = {"baseline_consistency": {"same_model": True,
                                           "same_input": True,
                                           "passed": True, "reasons": [],
                                           "original_logit": 0.0,
                                           "tolerance": 1e-9},
                  "model": {"parameter_fingerprint": "x"},
                  "target": {"history_fingerprint": "h"},
                  "tgap": result, "cody": None}
        self.assertFalse(comparability(record)["requested_scenario_completed"])


@unittest.skipUnless(TORCH_AVAILABLE and DATA_PRESENT,
                     "PyTorch or data/tgbl-uci.zip absent")
class TestCodyAdapter(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from compare_explainers.cody_adapter import runCody
        (cls.config, cls.full, cls.stream, cls.backend,
         cls.target) = smallSetup()
        e = cls.target["event_id"]
        cls.logit = cls.backend.scoreHistory(
            cls.stream.src[:e], cls.stream.dst[:e], cls.stream.ts[:e],
            cls.target["source"], cls.target["destination"])
        cls.result = runCody(cls.backend, cls.stream, cls.target, cls.config,
                             log=lambda *a: None)

    def test18_the_target_query_is_forwarded(self):
        r = self.result
        self.assertEqual(r["original_logit"], self.logit)
        self.assertTrue(r["original_prediction_path"]["input_is_full_prefix"])
        self.assertEqual(r["original_prediction_path"]["input_events"],
                         self.target["event_id"])
        self.assertIn(self.target["event_id"], r["candidate_event_ids"])

    def test19_outcomes_are_classified_distinctly(self):
        from compare_explainers.cody_adapter import classifyOutcome
        self.assertEqual(classifyOutcome(True, 3, True), "valid_counterfactual")
        self.assertEqual(classifyOutcome(True, 3, False),
                         "reported_counterfactual_not_reproduced")
        self.assertEqual(classifyOutcome(False, 2, False), "no_class_change")
        self.assertEqual(classifyOutcome(False, 0, False), "no_counterfactual")
        self.assertIn(self.result["status"],
                      {"valid_counterfactual", "no_class_change",
                       "no_counterfactual"})
        self.assertEqual(self.result["counterfactual_found"],
                         self.result["status"] == "valid_counterfactual")

    def test20_timeout_is_reported_not_hidden(self):
        from compare_explainers.cody_adapter import runCody
        config = copy.deepcopy(self.config)
        config["cody"]["time_limit_seconds"] = 0
        result = runCody(self.backend, self.stream, self.target, config,
                         log=lambda *a: None)
        self.assertEqual(result["status"], "timeout")
        self.assertFalse(result["counterfactual_found"])
        self.assertEqual(result["events"], [])
        self.assertEqual(result["event_count"], 0)

    def test21_selected_events_and_scores_are_the_real_ones(self):
        r = self.result
        candidates = set(r["candidate_event_ids"])
        for event in r["events"]:
            e = event["event_id"]
            self.assertIn(e, candidates)
            self.assertLess(e, self.target["event_id"])
            self.assertEqual(event["source"], int(self.stream.src[e]))
            self.assertEqual(event["destination"], int(self.stream.dst[e]))
            self.assertEqual(event["timestamp"], int(self.stream.ts[e]))
        if r["events"]:
            ids = [e["event_id"] for e in r["events"]]
            keep = np.setdiff1d(np.arange(self.target["event_id"]), ids)
            exact = self.backend.scoreHistory(
                self.stream.src[keep], self.stream.dst[keep],
                self.stream.ts[keep], self.target["source"],
                self.target["destination"])
            self.assertEqual(r["counterfactual_logit_exact"], exact)
            self.assertEqual(r["sparsity"], len(ids) / r["candidate_size"])


def latestRecord():
    if not os.path.exists(LATEST_RECORD):
        return None
    from compare_explainers.pipeline import loadLatest
    return loadLatest()


RECORD = latestRecord()


@unittest.skipUnless(RECORD is not None, "no saved pilot record")
class TestSavedPilotRecord(unittest.TestCase):
    ''' The claims the comparison page makes about the real run. '''

    def test_record_is_reproducible_from_its_configuration(self):
        self.assertEqual(RECORD["experiment_id"],
                         experimentId(RECORD["configuration"]))

    def test01_05_record_uses_the_canonical_stream_and_split(self):
        if not DATA_PRESENT:
            self.skipTest("data absent")
        config = RECORD["configuration"]
        stream = loadUciMessages(config)
        self.assertEqual(RECORD["dataset"]["stream_sha256"],
                         stream.fingerprint())
        split = chronologicalSplit(stream, config)
        self.assertEqual(RECORD["dataset"]["split"], split)
        t = RECORD["target"]
        self.assertGreaterEqual(t["event_id"], split["test"][0])
        self.assertEqual(int(stream.ts[t["event_id"]]), t["timestamp"])
        self.assertEqual(int(stream.src[t["event_id"]]), t["source"])
        self.assertEqual(int(stream.dst[t["event_id"]]), t["destination"])
        self.assertEqual(historyBefore(stream, t["event_id"]),
                         t["history_events"])
        self.assertEqual(t["history_fingerprint"], streamFingerprint(
            stream.src[:t["event_id"]], stream.dst[:t["event_id"]],
            stream.ts[:t["event_id"]]))

    def test05_target_selection_is_reproducible(self):
        if not DATA_PRESENT:
            self.skipTest("data absent")
        from compare_explainers.target import selectTarget
        config = RECORD["configuration"]
        stream = loadUciMessages(config)
        split = chronologicalSplit(stream, config)
        path = os.path.join(os.path.dirname(LATEST_RECORD), "models",
                            f"tgn_uci_{RECORD['model']['model_key']}_test_logits.npz")
        cached = np.load(path)
        logits = dict(zip(cached["ids"].tolist(), cached["logits"].tolist()))
        target, _ = selectTarget(stream, split, logits, config)
        for key in ("event_id", "source", "destination", "timestamp"):
            self.assertEqual(target[key], RECORD["target"][key])

    def test06_07_baseline_and_shared_model_verified(self):
        b = RECORD["baseline_consistency"]
        self.assertTrue(b["passed"], b["reasons"])
        self.assertLessEqual(b["max_abs_logit_difference"], b["tolerance"])
        c = RECORD["comparability"]
        self.assertEqual(c["comparable"], b["passed"]
                         and c["shared_model_verified"]
                         and c["same_input_verified"]
                         and c["explainer_baselines_agree"])
        model = RECORD["model"]
        from compare_explainers.config import fileSha256
        import paths
        self.assertEqual(fileSha256(os.path.join(paths.ROOT,
                                                 model["checkpoint"])),
                         model["checkpoint_sha256"])

    def test26_failed_runs_are_recorded_with_a_status(self):
        self.assertIn(RECORD["cody"]["status"],
                      {"valid_counterfactual", "no_class_change",
                       "no_counterfactual", "timeout", "execution_failure",
                       "reported_counterfactual_not_reproduced"})
        self.assertIn(RECORD["tgap"]["status"],
                      {"valid", "noop", "invalid", "mapping_invalid"})

    def test27_exports_carry_the_actual_values(self):
        from compare_explainers.export import summaryRows
        rows = {(r["section"], r["field"]): r["value"]
                for r in summaryRows(RECORD)}
        self.assertEqual(rows[("shared.baseline_consistency",
                               "original_logit")],
                         RECORD["baseline_consistency"]["original_logit"])
        self.assertEqual(rows[("cody", "status")], RECORD["cody"]["status"])
        self.assertEqual(rows[("shared.model", "checkpoint_sha256")],
                         RECORD["model"]["checkpoint_sha256"])
        decrease = next(d for d in RECORD["tgap"]["directions"]
                        if d["direction"] == "Decrease")
        self.assertEqual(rows[("tgap.decrease", "achieved_delta")],
                         decrease["achieved_delta"])


@unittest.skipUnless(os.path.isdir(os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "..", "compare_explainers", "third_party")),
    "vendored CoDy absent")
class TestVendoredCody(unittest.TestCase):

    def test_vendored_cody_matches_its_manifest(self):
        import hashlib
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                            "compare_explainers", "third_party")
        with open(os.path.join(root, "cody_manifest.sha256")) as handle:
            for line in handle:
                digest, name = line.split()
                with open(os.path.join(root, name), "rb") as source:
                    self.assertEqual(hashlib.sha256(source.read()).hexdigest(),
                                     digest, name)


if __name__ == "__main__":
    unittest.main()
