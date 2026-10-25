'''
TGAP on the shared prediction: the existing Churn transformation, applied
through the existing TgapExplainer, scored by the canonical TGN.

THE REPRESENTATION GAP, AND HOW IT IS CLOSED
    TGAP's Churn (core/Transformations/Churn.py) is defined on SNAPSHOTS:
    per earlier snapshot, the share of its edge set that disagrees with the
    last snapshot (mean Jaccard distance). The TGN consumes EVENTS. So:

      1. events before t  ->  snapshots     (TGAP's representation)
      2. ChurnTransformation.transform      (TGAP's own code, unchanged)
      3. snapshots        ->  events        (the "lift", below)
      4. TGN scores the lifted history      (the canonical backend)

    Step 1 follows the real-data adapters' decisions: undirected edges,
    repeated messages in a window collapse to one edge, fixed node set
    (every node with history), windows of `window_days` anchored so the
    LAST window is [t - W, t). The last snapshot is the "latest snapshot"
    TGAP keeps fixed.

    Step 3 is the one new modelling decision, so it is spelled out:
    Churn changes edges by remove-one-add-one swaps inside an earlier
    snapshot. For each such snapshot the removed pairs and added pairs are
    sorted and paired one-to-one; every message of a removed pair in that
    window is RE-ADDRESSED to its paired added pair, keeping its timestamp
    and its position in the stream, and keeping its orientation (a message
    from the lower to the higher node id of the old pair goes from the lower
    to the higher node id of the new pair). Consequences:
      * the number of events, every timestamp and the ordering are
        unchanged - activity volume and timing are not part of the
        intervention, only WHO interacted in the history;
      * events in the last window are byte-identical (the anchor);
      * re-addressed events are synthetic: they never happened. Each one is
        listed with its original event id, old pair and new pair;
      * the mapping is checked by a ROUND TRIP: re-snapshotting the lifted
        stream must give exactly Churn's transformed snapshots. If it does
        not, the run is marked mapping_invalid and nothing is claimed.
'''

import math

import networkx as nx
import numpy as np

from core.TemporalGraphExplainer import TgapExplainer
from core.TemporalGraphModel import TemporalGraphModel
from core.Transformations import ChurnTransformation
from core.GraphMetric import DegreeCentralizationMetric, DensityMetric

from .dataset import streamFingerprint
from .tgn_backend import sigmoid

SECONDS_PER_DAY = 86400


class LiftError(ValueError):
    ''' A transformed snapshot list cannot be represented as an event
    history under the documented mapping. '''


def _key(u, v):
    return (u, v) if u <= v else (v, u)


class SnapshotView:
    ''' TGAP's snapshot view of one prediction's history, plus the inverse
    mapping back to events. Holds the ORIGINAL arrays read-only. '''

    def __init__(self, src, dst, ts, targetTime, windowDays):
        self.src = np.array(src, dtype=np.int64)
        self.dst = np.array(dst, dtype=np.int64)
        self.ts = np.array(ts, dtype=np.int64)
        for array in (self.src, self.dst, self.ts):
            array.setflags(write=False)
        if len(self.ts) and self.ts.max() >= targetTime:
            raise ValueError("history contains events at or after t")
        self.targetTime = int(targetTime)
        self.windowSeconds = int(windowDays * SECONDS_PER_DAY)
        age = self.targetTime - self.ts                     # >= 1
        fromEnd = (age - 1) // self.windowSeconds           # 0 = last window
        self.count = int(fromEnd.max()) + 1
        self.window = (self.count - 1 - fromEnd).astype(np.int64)
        self.window.setflags(write=False)
        self.nodes = sorted(set(self.src.tolist()) | set(self.dst.tolist()))
        self.keys = [_key(int(a), int(b)) for a, b in zip(self.src, self.dst)]
        self.edgeEvents = [dict() for _ in range(self.count)]
        for e, (w, k) in enumerate(zip(self.window.tolist(), self.keys)):
            self.edgeEvents[w].setdefault(k, []).append(e)
        self.snapshots = self._build(self.keys)

    def _build(self, keys):
        snapshots = [nx.Graph() for _ in range(self.count)]
        for g in snapshots:
            g.add_nodes_from(self.nodes)
        for w, k in zip(self.window.tolist(), keys):
            snapshots[w].add_edge(*k)
        return snapshots

    def windowBounds(self):
        bounds = []
        for w in range(self.count):
            end = self.targetTime - (self.count - 1 - w) * self.windowSeconds
            bounds.append({"window": w + 1,
                           "start": max(end - self.windowSeconds, 0),
                           "end": end,
                           "events": int((self.window == w).sum()),
                           "edges": self.snapshots[w].number_of_edges()})
        return bounds

    def lift(self, transformed):
        ''' Map a transformed snapshot list back to an event history.
        Returns a new immutable LiftedHistory; never edits the original. '''
        if len(transformed) != self.count:
            raise LiftError(f"{len(transformed)} snapshots, expected "
                            f"{self.count}")
        last = {_key(*e) for e in transformed[-1].edges()}
        if last != {_key(*e) for e in self.snapshots[-1].edges()}:
            raise LiftError("the latest snapshot was changed; Churn's anchor "
                            "requires it to stay fixed")
        src, dst = self.src.copy(), self.dst.copy()
        changes = []
        for w in range(self.count - 1):
            original = set(self.edgeEvents[w])
            new = {_key(*e) for e in transformed[w].edges()}
            removed, added = sorted(original - new), sorted(new - original)
            if len(removed) != len(added):
                raise LiftError(
                    f"snapshot {w + 1}: {len(removed)} edges removed but "
                    f"{len(added)} added; only edge swaps can be mapped to "
                    "events without inventing or deleting activity")
            for old, newPair in zip(removed, added):
                for e in self.edgeEvents[w][old]:
                    forward = int(self.src[e]) == old[0]
                    src[e], dst[e] = (newPair if forward else newPair[::-1])
                    changes.append({
                        "event_id": int(e), "window": w + 1,
                        "timestamp": int(self.ts[e]),
                        "original": [int(self.src[e]), int(self.dst[e])],
                        "lifted": [int(src[e]), int(dst[e])]})
        lifted = LiftedHistory(src, dst, self.ts, changes)
        # ROUND TRIP: the lifted events must reproduce the snapshots exactly.
        rebuilt = self._build([_key(int(a), int(b)) for a, b in zip(src, dst)])
        for w in range(self.count):
            if ({_key(*e) for e in rebuilt[w].edges()}
                    != {_key(*e) for e in transformed[w].edges()}):
                raise LiftError(f"round trip failed at snapshot {w + 1}")
        lifted.roundTrip = True
        lifted.lastWindowIdentical = bool(np.array_equal(
            src[self.window == self.count - 1],
            self.src[self.window == self.count - 1]) and np.array_equal(
            dst[self.window == self.count - 1],
            self.dst[self.window == self.count - 1]))
        return lifted


class LiftedHistory:
    ''' An immutable event history derived from a transformation. '''

    def __init__(self, src, dst, ts, changes):
        self.src, self.dst, self.ts = src, dst, ts
        for array in (self.src, self.dst):
            array.setflags(write=False)
        self.changes = changes
        self.roundTrip = False
        self.lastWindowIdentical = False

    def fingerprint(self):
        return streamFingerprint(self.src, self.dst, self.ts)


class TargetLinkTgnModel(TemporalGraphModel):
    ''' TGAP's model contract, predict(temporalGraph) -> float, answered by
    the canonical TGN for the FIXED target link (A, B) at t.

    The output is the TGN's probability that A messages B at t, after
    replaying the history the snapshots describe (lifted to events). Every
    call is logged, so the run can report exactly which input produced
    which score. '''

    def __init__(self, backend, view, source, destination):
        self.backend = backend
        self.view = view
        self.source = int(source)
        self.destination = int(destination)
        self.calls = []

    def predict(self, temporalGraph):
        lifted = self.view.lift(temporalGraph)
        logit = self.backend.scoreHistory(lifted.src, lifted.dst, lifted.ts,
                                          self.source, self.destination,
                                          self.view.targetTime)
        self.calls.append({"snapshots": temporalGraph, "lifted": lifted,
                           "logit": logit, "probability": sigmoid(logit),
                           "input_fingerprint": lifted.fingerprint(),
                           "parameter_fingerprint":
                               self.backend.parameterFingerprint()})
        return sigmoid(logit)


def churnFeasibility(view, delta):
    ''' Why the achieved Churn change can differ from the request, measured
    per earlier snapshot with the same arithmetic ChurnTransformation uses
    (no model involved). For a decrease, each snapshot needs
    round(|delta| x disagreeing edges) swaps, but can only copy as many edges
    as the latest snapshot has that it lacks. For an increase, swaps are
    limited by the edges it shares with the latest snapshot. '''
    last = {_key(*e) for e in view.snapshots[-1].edges()}
    rows = []
    for w in range(view.count - 1):
        here = {_key(*e) for e in view.snapshots[w].edges()}
        if delta < 0:
            pool, partner = len(here - last), len(last - here)
        else:
            pool, partner = len(here & last), None
        requested = round(abs(delta) * pool)
        possible = pool if partner is None else min(pool, partner)
        rows.append({"snapshot": w + 1, "eligible_edges": pool,
                     "requested_swaps": requested,
                     "applied_swaps": min(requested, possible),
                     "limited": min(requested, possible) < requested})
    limited = [r["snapshot"] for r in rows if r["limited"]]
    if delta < 0 and limited:
        cause = (f"In {len(limited)} of {len(rows)} earlier periods fewer swaps "
                 "were possible than requested, because the latest period has "
                 "only a limited number of connections that can be copied "
                 "into the past.")
    elif limited:
        cause = (f"In {len(limited)} of {len(rows)} earlier periods fewer swaps "
                 "were possible than requested.")
    else:
        cause = "Every requested swap was possible in every earlier period."
    return {"periods": rows, "limited_periods": limited,
            "requested_swaps_total": sum(r["requested_swaps"] for r in rows),
            "applied_swaps_total": sum(r["applied_swaps"] for r in rows),
            "cause": cause,
            "measure_note": ("Churn is a ratio (Jaccard distance), so swapping "
                             "a share of edges does not change it by exactly "
                             "the same share.")}


def churnPlan(view, config):
    ''' What the user is shown BEFORE the intervention runs. '''
    tgap = config["tgap"]
    churn = ChurnTransformation(communities=tgap["communities"],
                                seed=tgap["seed"])
    bounds = view.windowBounds()
    return {
        "concept": "Churn",
        "definition": "mean Jaccard distance between each earlier "
                      "snapshot's edge set and the latest snapshot's edge "
                      "set (0 = history identical to the present, 1 = "
                      "completely different); "
                      "ChurnTransformation.propertyValue",
        "original_churn": churn.propertyValue(view.snapshots),
        "requested_direction": tgap["direction"],
        "requested_delta": -abs(tgap["requested_delta"])
                           if tgap["direction"] == "decrease"
                           else abs(tgap["requested_delta"]),
        "window_days": tgap["window_days"],
        "snapshots": view.count,
        "temporal_scope": f"snapshots 1-{view.count - 1} (all history before "
                          f"the latest {tgap['window_days']}-day window)",
        "latest_snapshot": bounds[-1],
        "windows": bounds,
        "constraints": [
            "the latest snapshot is kept exactly (TGAP's Churn anchor)",
            "every snapshot keeps its node set and edge count "
            "(remove-one-add-one swaps)",
            "no community constraint (communities=None): every edge is "
            "churn-eligible",
            "lift to events keeps the number, timing and order of events; "
            "only the addressee pair of swapped messages changes",
        ],
        "transformation_seed": tgap["seed"],
    }


def runTgap(backend, stream, target, config, log=print):
    ''' Run TGAP's own explainer for Churn on the target's history. Returns
    the TGAP section of the reproducibility record. '''
    tgap = config["tgap"]
    if tgap["concept"] != "churn":
        raise ValueError("the pilot scenario is defined for Churn only")
    end = target["event_id"]
    view = SnapshotView(stream.src[:end], stream.dst[:end], stream.ts[:end],
                        target["timestamp"], tgap["window_days"])
    plan = churnPlan(view, config)
    churn = ChurnTransformation(communities=tgap["communities"],
                                seed=tgap["seed"])
    model = TargetLinkTgnModel(backend, view, target["source"],
                               target["destination"])
    explainer = TgapExplainer(model, [churn],
                              defaultDelta=abs(tgap["requested_delta"]))
    log(f"    TGAP: {view.count} snapshots, original churn "
        f"{plan['original_churn']:.6f}; running TgapExplainer "
        "(baseline + increase + decrease = 3 full TGN replays) ...")
    try:
        records = explainer.explainDetailed(
            view.snapshots, leakageMetrics={"Density": DensityMetric(),
                                            "Centralization":
                                                DegreeCentralizationMetric()})
    except LiftError as error:
        result = {"status": "mapping_invalid", "plan": plan,
                  "error": str(error), "directions": [],
                  "claim": "No TGAP result is reported: the transformed "
                           "history could not be mapped to TGN input."}
        if model.calls:                 # the baseline call itself succeeded
            first = model.calls[0]
            result["baseline"] = {
                "logit": first["logit"], "probability": first["probability"],
                "input_fingerprint": first["input_fingerprint"],
                "parameter_fingerprint": first["parameter_fingerprint"]}
        return result
    # explainDetailed calls predict in a fixed order: baseline, +d, -d.
    baselineCall, perturbedCalls = model.calls[0], model.calls[1:]
    directions = []
    for record, call in zip(records, perturbedCalls):
        directions.append(_directionResult(record, call, baselineCall, view,
                                           churn, target))
    requested = "Decrease" if tgap["direction"] == "decrease" else "Increase"
    primary = next(d for d in directions if d["direction"] == requested)
    return {
        "status": primary["status"],
        "plan": plan,
        "baseline": {"logit": baselineCall["logit"],
                     "probability": baselineCall["probability"],
                     "input_fingerprint": baselineCall["input_fingerprint"],
                     "parameter_fingerprint":
                         baselineCall["parameter_fingerprint"]},
        "primary_direction": requested,
        "directions": directions,
        "model_calls": len(model.calls),
        "expected_model_calls": 1 + 2 * 1,
        "explainer": "core.TemporalGraphExplainer.TgapExplainer"
                     ".explainDetailed (normalization='achieved')",
        "transformation": "core.Transformations.Churn.ChurnTransformation",
    }


def _directionResult(record, call, baselineCall, view, churn, target):
    transformed = call["snapshots"]
    lifted = call["lifted"]
    p0 = churn.propertyValue(view.snapshots)
    pT = churn.propertyValue(transformed)
    edgeCounts = [(g.number_of_edges(), h.number_of_edges())
                  for g, h in zip(view.snapshots, transformed)]
    swapsPerWindow = []
    for w in range(view.count - 1):
        before = {_key(*e) for e in view.snapshots[w].edges()}
        after = {_key(*e) for e in transformed[w].edges()}
        swapsPerWindow.append(len(before - after))
    endpoints = {target["source"], target["destination"]}
    touching = [c for c in lifted.changes
                if endpoints & set(c["original"]) or endpoints & set(c["lifted"])]
    noop = bool(record["noop"]) or (not lifted.changes and pT == p0)
    edgeCountPreserved = all(a == b for a, b in edgeCounts)
    status = ("noop" if noop else
              "valid" if (lifted.roundTrip and lifted.lastWindowIdentical
                          and edgeCountPreserved) else "invalid")
    impact = record["impact"]
    if impact is not None and not math.isfinite(impact):
        impact, status = None, "invalid"
    return {
        "direction": "Decrease" if record["requestedDelta"] < 0 else "Increase",
        "label": record["label"],
        "requested_delta": record["requestedDelta"],
        "churn_before": p0,
        "churn_after": pT,
        "achieved_delta": record["achievedDelta"],
        "achieved_delta_recomputed": (pT - p0) / abs(p0) if p0 else None,
        "original_probability": record["baseline"],
        "modified_probability": record["transformed"],
        "original_logit": baselineCall["logit"],
        "modified_logit": call["logit"],
        "prediction_change": record["transformed"] - record["baseline"],
        "class_before": "message" if baselineCall["logit"] > 0 else "no message",
        "class_after": "message" if call["logit"] > 0 else "no message",
        "class_changed": (baselineCall["logit"] > 0) != (call["logit"] > 0),
        "normalized_impact": impact,
        "normalizer": record["normalizer"],
        "noop": noop,
        "status": status,
        "latest_snapshot_preserved": lifted.lastWindowIdentical,
        "edge_count_preserved_every_snapshot": edgeCountPreserved,
        "lift_round_trip": lifted.roundTrip,
        "edge_swaps_per_snapshot": swapsPerWindow,
        "edges_swapped_total": int(sum(swapsPerWindow)),
        "events_readdressed": len(lifted.changes),
        "events_readdressed_touching_a_or_b": len(touching),
        "events_total": int(len(lifted.ts)),
        "event_changes_sample": lifted.changes[:200],
        "modified_input_fingerprint": call["input_fingerprint"],
        "feasibility": churnFeasibility(view, record["requestedDelta"]),
        "leakage": record["leakage"],
        "side_effects": {
            "event_count_and_timestamps": "unchanged by construction",
            "synthetic_events": len(lifted.changes),
            "density_change_mean_over_snapshots":
                record["leakage"].get("Density", {}).get("change"),
            "centralization_change_mean_over_snapshots":
                record["leakage"].get("Centralization", {}).get("change"),
        },
    }
