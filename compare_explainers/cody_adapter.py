'''
CoDy on the shared prediction, through CoDy's own extension point.

CoDy's README (section 4.1, "Adding a new target model") says a new model is
connected by subclassing cody.implementations.connector.TGNNWrapper. That is
exactly what TgapTgnCoDyWrapper does: it answers CoDy's calls with the
canonical TGN backend, so CoDy's unmodified search (cody.explainer.cody.CoDy,
vendored at the pinned commit in third_party/) queries the very model
instance TGAP queries.

Semantics kept from CoDy's reference TGNWrapper
    initialize(id, label)  roll out events 0..id, back the state up under label
    predict(id)            score event id from the current state (no update)
    subgraph prediction    restore, replay the allowed events, score
    approximate mode       CoDy's own approximation: replay only the
                           non-excluded CANDIDATE events; CoDy re-checks any
                           apparent counterfactual exactly (all events)
One deliberate difference: when no rollout list is given, the reference
wrapper keeps ids "> latest_event_id", which skips the oldest candidate after
a restore. This wrapper keeps ids ">= latest_event_id" (every event from the
restore point on). That is a property of the wrapper, not of CoDy's search.

Timeouts are enforced by the wrapper (it raises when the wall-clock budget is
spent), so no CoDy code is changed to add them.
'''

import logging
import os
import random
import sys
import time

import numpy as np

THIRD_PARTY = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "third_party")
if THIRD_PARTY not in sys.path:
    sys.path.insert(0, THIRD_PARTY)

from .dataset import streamFingerprint  # noqa: E402
from .tgn_backend import requireTorch, sigmoid  # noqa: E402

CODY_UPSTREAM = {
    "repository": "https://github.com/daniel-gomm/CoDy",
    "commit": "0a004c2ad171b7ded59751c2179b64bf7738693a",
    "commit_date": "2025-10-02",
    "license": "MIT (Copyright (c) 2025 Daniel Gomm), "
               "third_party/cody/LICENSE.md",
    "paper": "https://proceedings.mlr.press/v267/qu25b.html",
    "modified": False,
}


class SearchTimeout(RuntimeError):
    pass


class _QuietCodyConstruction:
    ''' CoDy's constructors call logging.basicConfig(level=INFO), which
    would attach a console handler to the host's root logger. Undo exactly
    that side effect (CoDy's code is not edited). '''

    def __enter__(self):
        root = logging.getLogger()
        self.handlers, self.level = list(root.handlers), root.level
        return self

    def __exit__(self, *exc):
        root = logging.getLogger()
        for handler in list(root.handlers):
            if handler not in self.handlers:
                root.removeHandler(handler)
        root.setLevel(self.level)
        return False


def _importCody():
    requireTorch()
    from cody.constants import (COL_ID, COL_NODE_I, COL_NODE_U, COL_STATE,
                                COL_TIMESTAMP)
    from cody.data import ContinuousTimeDynamicGraphDataset, SubgraphGenerator
    from cody.explainer.cody import CoDy
    from cody.implementations.connector import TGNNWrapper
    return dict(COL_ID=COL_ID, COL_NODE_I=COL_NODE_I, COL_NODE_U=COL_NODE_U,
                COL_STATE=COL_STATE, COL_TIMESTAMP=COL_TIMESTAMP,
                Dataset=ContinuousTimeDynamicGraphDataset,
                SubgraphGenerator=SubgraphGenerator, CoDy=CoDy,
                TGNNWrapper=TGNNWrapper)


def codyDataset(stream):
    ''' The canonical stream in CoDy's dataset class - the same arrays, not a
    second preprocessing. user_id = sender, item_id = receiver; UCI has no
    edge or node features, so both feature matrices have zero columns. '''
    import pandas as pd
    c = _importCody()
    events = pd.DataFrame({
        c["COL_NODE_U"]: np.array(stream.src, dtype=np.int64),
        c["COL_NODE_I"]: np.array(stream.dst, dtype=np.int64),
        c["COL_TIMESTAMP"]: np.array(stream.ts, dtype=np.int64),
        c["COL_STATE"]: np.zeros(len(stream), dtype=np.int64),
        c["COL_ID"]: np.arange(len(stream), dtype=np.int64),
    })
    return c["Dataset"](events, np.zeros((len(stream), 0)),
                        np.zeros((stream.num_nodes, 0)), name="uci_messages",
                        directed=False, bipartite=False)


def makeWrapper(backend, dataset, numHops, deadline=None):
    ''' Build the wrapper class lazily so importing this module never
    requires torch. '''
    import torch
    TGNNWrapper = _importCody()["TGNNWrapper"]

    class TgapTgnCoDyWrapper(TGNNWrapper):

        def __init__(self):
            super().__init__(model=backend.modules, dataset=dataset,
                             num_hops=numHops,
                             model_name="TGAP canonical event-level TGN",
                             device="cpu", use_memory=True, batch_size=1)
            self.backend = backend
            self.node_embedding_dimension = backend.config["embedding_dim"]
            self.time_embedding_dimension = backend.config["time_dim"]
            self.deadline = deadline
            self.oracle_calls = 0
            self.predict_calls = 0
            self.replayed_events = 0
            self.prediction_log = {}
            self._replayed = []
            self.reset_model()

        # --- bookkeeping ---
        def _check(self):
            if self.deadline is not None and time.monotonic() > self.deadline:
                raise SearchTimeout("CoDy time limit reached")

        def _replay(self, ids):
            self._check()
            ids = np.asarray(ids, dtype=np.int64)
            if len(ids):
                self.backend.replay(self.dataset.source_node_ids[ids],
                                    self.dataset.target_node_ids[ids],
                                    self.dataset.timestamps[ids])
                self._replayed.append(ids)
                self.replayed_events += len(ids)

        def replayed_input_fingerprint(self):
            ids = (np.concatenate(self._replayed) if self._replayed
                   else np.zeros(0, dtype=np.int64))
            return streamFingerprint(self.dataset.source_node_ids[ids],
                                     self.dataset.target_node_ids[ids],
                                     self.dataset.timestamps[ids]), ids

        def _score(self, eventId, asLogit):
            a = int(self.dataset.source_node_ids[eventId])
            b = int(self.dataset.target_node_ids[eventId])
            logit = self.backend.logit(a, b)
            value = logit if asLogit else sigmoid(logit)
            return torch.tensor([[value]], dtype=torch.float64), logit

        # --- TGNNWrapper interface ---
        def reset_model(self):
            self.backend.eval()
            self.backend.reset()
            self._replayed = []
            self.reset_latest_event_id()

        def get_memory(self):
            return (self.backend.getState(), list(self._replayed))

        def restore_memory(self, memory_backup, event_id):
            state, replayed = memory_backup
            self.backend.setState(state)
            self._replayed = list(replayed)
            self.reset_latest_event_id(event_id + 1)

        def detach_memory(self):
            pass                        # inference only: nothing to detach

        def initialize(self, event_id, show_progress=False, memory_label=None):
            if memory_label is not None and memory_label in self.memory_backups_map:
                backup, backupEventId = self.memory_backups_map[memory_label]
                if backupEventId == event_id:
                    self.restore_memory(backup, event_id)
                    return
                self.reset_model()
            self.rollout_until_event(event_id)
            if memory_label is not None:
                self.memory_backups_map[memory_label] = (self.get_memory(),
                                                         event_id)

        def rollout_until_event(self, event_id=None, batch_data=None,
                                progress_bar=None, event_ids_to_rollout=None):
            end = int(event_id) + 1
            if self.latest_event_id > end:
                raise RuntimeError("cannot roll the memory backwards")
            if event_ids_to_rollout is None:
                ids = np.arange(self.latest_event_id, end)
            else:
                ids = np.sort(np.asarray(event_ids_to_rollout, dtype=np.int64))
                ids = ids[(ids >= self.latest_event_id) & (ids < end)]
            self._replay(ids)
            self.latest_event_id = end

        def predict(self, event_id, result_as_logit=False):
            if self.latest_event_id != event_id:
                raise RuntimeError(
                    f"predict({event_id}) needs the state after event "
                    f"{event_id - 1}; the wrapper is at {self.latest_event_id}")
            self.predict_calls += 1
            out, logit = self._score(event_id, result_as_logit)
            fingerprint, ids = self.replayed_input_fingerprint()
            self.prediction_log.setdefault(int(event_id), {
                "logit": logit, "input_fingerprint": fingerprint,
                "input_events": int(len(ids)),
                "input_is_full_prefix": bool(np.array_equal(
                    ids, np.arange(event_id))),
                "parameter_fingerprint": self.backend.parameterFingerprint()})
            return out, None

        def compute_edge_probabilities_for_subgraph(
                self, event_id, edges_to_drop, result_as_logit=False,
                event_ids_to_rollout=None):
            self._check()
            dropped = np.asarray(edges_to_drop, dtype=np.int64)
            if event_ids_to_rollout is None:
                ids = np.arange(self.latest_event_id, event_id)
            else:
                ids = np.sort(np.asarray(event_ids_to_rollout, dtype=np.int64))
                ids = ids[(ids >= self.latest_event_id) & (ids < event_id)]
            ids = ids[~np.isin(ids, dropped)]
            self._replay(ids)
            self.latest_event_id = event_id
            self.oracle_calls += 1
            out, _ = self._score(event_id, result_as_logit)
            return out, None

        def compute_embeddings(self, *args, **kwargs):
            raise NotImplementedError("not used by CoDy's search")

        def encode_timestamps(self, timestamps):
            raise NotImplementedError("not used by CoDy's search")

        def compute_edge_probabilities(self, *args, **kwargs):
            raise NotImplementedError("not used by CoDy's search")

    with _QuietCodyConstruction():
        return TgapTgnCoDyWrapper()


class _CodyLog(logging.Handler):
    ''' Captures CoDy's own verbose log lines to report how the search
    ended, without editing CoDy. '''

    def __init__(self):
        super().__init__(logging.INFO)
        self.lines = []

    def emit(self, record):
        message = record.getMessage()
        if message.startswith(("Selected node", "Found counterfactual",
                               "Search Tree is fully expanded",
                               "Original prediction")):
            self.lines.append(message)


def classifyOutcome(reportedCounterfactual, eventCount, classChangedExact):
    ''' CoDy's result in one of four categories (timeouts and failures are
    assigned before a result exists):
      valid_counterfactual   CoDy reports a counterfactual AND an exact
                             replay without its events flips the class
      reported_counterfactual_not_reproduced
                             CoDy reports one, the exact replay disagrees
      no_class_change        events returned, class unchanged
      no_counterfactual      the search returned no events at all '''
    if reportedCounterfactual and classChangedExact:
        return "valid_counterfactual"
    if reportedCounterfactual:
        return "reported_counterfactual_not_reproduced"
    if eventCount:
        return "no_class_change"
    return "no_counterfactual"


def runCody(backend, stream, target, config, log=print):
    ''' Run the official CoDy search for the target event. Returns the CoDy
    section of the reproducibility record, for every outcome. '''
    c = _importCody()
    cfg = config["cody"]
    random.seed(cfg["seed"])
    np.random.seed(cfg["seed"])
    dataset = codyDataset(stream)
    eventId = int(target["event_id"])
    started = time.monotonic()
    deadline = started + float(cfg["time_limit_seconds"])
    wrapper = makeWrapper(backend, dataset, cfg["num_hops"], deadline)
    with _QuietCodyConstruction():
        explainer = c["CoDy"](
            wrapper, candidates_size=cfg["candidates_size"],
            selection_policy=cfg["selection_policy"],
            max_steps=cfg["max_steps"], verbose=True,
            approximate_predictions=cfg["approximate_predictions"],
            alpha=cfg["alpha"])
    # CoDy's candidate set, from CoDy's own function (for sparsity and display).
    candidates = c["SubgraphGenerator"](dataset).get_fixed_size_k_hop_temporal_subgraph(
        num_hops=cfg["num_hops"], base_event_id=eventId,
        size=cfg["candidates_size"])
    candidateIds = candidates[c["COL_ID"]].to_numpy()

    handler = _CodyLog()
    root = logging.getLogger()
    previousLevel = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    status, error, example = None, None, None
    log(f"    CoDy: {cfg['selection_policy']} policy, max {cfg['max_steps']} "
        f"steps, {len(candidateIds)} candidate events, time limit "
        f"{cfg['time_limit_seconds']} s ...")
    try:
        example = explainer.explain(eventId)
    except SearchTimeout as exc:
        status, error = "timeout", str(exc)
    except Exception as exc:              # reported, never swallowed silently
        status, error = "execution_failure", f"{type(exc).__name__}: {exc}"
    finally:
        root.removeHandler(handler)
        root.setLevel(previousLevel)
    runtime = time.monotonic() - started

    steps = sum(1 for line in handler.lines if line.startswith("Selected node"))
    fullyExpanded = any(line.startswith("Search Tree is fully expanded")
                        for line in handler.lines)
    original = wrapper.prediction_log.get(eventId)
    base = {
        "upstream": CODY_UPSTREAM,
        "configuration": dict(cfg),
        "wrapper": "compare_explainers.cody_adapter.TgapTgnCoDyWrapper "
                   "(cody.implementations.connector.TGNNWrapper subclass)",
        "candidate_event_ids": candidateIds.tolist(),
        "candidate_size": int(len(candidateIds)),
        "runtime_seconds": round(runtime, 2),
        "search_steps_logged": steps,
        "oracle_calls": wrapper.oracle_calls,
        "events_replayed": wrapper.replayed_events,
        "original_prediction_path": original,
    }
    if example is None:
        return {**base, "status": status, "counterfactual_found": False,
                "error": error, "termination": status,
                "events": [], "event_count": 0,
                "claim": "No CoDy explanation: the search did not finish."}

    eventIds = np.asarray(example.event_ids, dtype=np.int64)
    reported = float(example.counterfactual_prediction)
    originalLogit = float(example.original_prediction)
    # Exact re-verification: full sequential replay of the history without
    # the selected events, independent of CoDy's restore/approximation path.
    exactLogit = None
    if len(eventIds):
        log(f"    CoDy returned {len(eventIds)} events; re-verifying with a "
            "full replay of the history without them ...")
        keep = np.setdiff1d(np.arange(eventId), eventIds)
        exactLogit = backend.scoreHistory(stream.src[keep], stream.dst[keep],
                                          stream.ts[keep], target["source"],
                                          target["destination"])
    classChangedExact = (exactLogit is not None
                         and (originalLogit > 0) != (exactLogit > 0))
    status = classifyOutcome(bool(example.achieves_counterfactual_explanation),
                             len(eventIds), classChangedExact)
    if example.achieves_counterfactual_explanation and \
            cfg["selection_policy"] == "local-gradient" and steps == 0:
        termination = "local-gradient first-level counterfactual (early return)"
    elif fullyExpanded:
        termination = "search tree fully expanded"
    else:
        termination = f"step budget exhausted (max_steps={cfg['max_steps']})"
    importances = example.get_absolute_importances()
    events = []
    for rank, e in enumerate(eventIds.tolist()):
        events.append({
            "event_id": int(e), "order_in_explanation": rank + 1,
            "source": int(stream.src[e]), "destination": int(stream.dst[e]),
            "timestamp": int(stream.ts[e]),
            "days_before_target": round((target["timestamp"]
                                         - int(stream.ts[e])) / 86400.0, 3),
            "involves_a_or_b": bool({int(stream.src[e]), int(stream.dst[e])}
                                    & {target["source"],
                                       target["destination"]}),
            "absolute_importance": (float(importances[rank])
                                    if importances is not None
                                    and len(importances) > rank
                                    and importances[rank] is not None
                                    else None),
        })
    return {
        **base,
        "status": status,
        "termination": termination,
        "counterfactual_found": status == "valid_counterfactual",
        "achieves_counterfactual_explanation_reported":
            bool(example.achieves_counterfactual_explanation),
        "events": events,
        "event_count": int(len(eventIds)),
        "sparsity": (len(eventIds) / len(candidateIds)
                     if len(candidateIds) else None),
        "sparsity_definition": "explanation size / candidate size "
                               "(CoDy repository, evaluate_factual_subgraphs.py)",
        "original_logit": originalLogit,
        "original_probability": sigmoid(originalLogit),
        "counterfactual_logit_reported": reported,
        "counterfactual_probability_reported": sigmoid(reported),
        "counterfactual_logit_exact": exactLogit,
        "counterfactual_probability_exact": (sigmoid(exactLogit)
                                             if exactLogit is not None else None),
        "score_change_exact": (sigmoid(exactLogit) - sigmoid(originalLogit)
                               if exactLogit is not None else None),
        "class_before": "message" if originalLogit > 0 else "no message",
        "class_after_exact": (None if exactLogit is None else
                              "message" if exactLogit > 0 else "no message"),
        "class_changed_exact": classChangedExact,
        "raw_importances": [None if v is None else float(v)
                            for v in example.event_importances.tolist()],
        "error": None,
    }
