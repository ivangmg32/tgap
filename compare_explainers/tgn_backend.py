'''
The canonical TGN backend that BOTH explainers call.

WHY NOT core.TgnModel.TgnTemporalGraphModel AS IT IS (compatibility audit)
    TGAP's existing TGN adapter is snapshot-based by design:
      * its input is a list of networkx snapshots; the snapshot INDEX is the
        timestamp, repeated messages inside a window collapse to one edge;
      * its output is ONE number per temporal graph - the mean probability
        of all edges of the last snapshot - not the score of a link;
      * it is trained in-process on each run; no checkpoint exists.
    CoDy explains the score of ONE event (A -> B at t) of a continuous-time
    event stream and removes individual past events. A mean over the last
    snapshot has no "event to explain", and snapshot-index time cannot
    represent removing one message. So the existing adapter cannot be
    queried by CoDy without changing its prediction semantics.

WHAT THIS FILE DOES INSTEAD
    It builds ONE event-level TGN from the same building blocks TGAP's TGN
    uses - core.TgnModel.GraphAttentionEmbedding and LinkPredictor, PyG's
    TGNMemory / IdentityMessage / LastAggregator / LastNeighborLoader, the
    same 32/32/32 dimensions and neighbour size 10 as core.TgnModel.buildTgn -
    and trains it once on the UCI-Messages training split. The checkpoint is
    saved with its SHA-256. TGAP and CoDy then call the SAME loaded instance:

        score(history events, A, B, t) -> logit

    The differences from buildTgn are exactly the ones the event stream
    needs: real timestamps instead of snapshot indices, a constant one-value
    message (UCI has no edge features; real time differences already break
    the memory symmetry that forced buildTgn's degree message), and the
    neighbour edges' true times in the attention layer (buildTgn passes
    zeros there because snapshots have no within-window time).

INFERENCE PROTOCOL: SEQUENTIAL
    Every history event is replayed one at a time, in event-id order, from a
    reset memory. Batching would make the score depend on where batch
    boundaries fall, and CoDy restores memory mid-stream; with batch size 1
    every path - full replay, CoDy's restore-then-replay, TGAP's transformed
    replay - performs the same operations in the same order, so equal inputs
    give bit-identical scores. Training uses the standard batched PyG loop
    (batch 200); the sequential protocol is its batch-size-1 limit and is
    the protocol used for every reported number, including test metrics.
'''

import hashlib
import json
import os
import random
import time

import numpy as np

from core.TgnModel import TORCH_AVAILABLE, requireTorch

if TORCH_AVAILABLE:
    import torch
    from torch_geometric.nn.models.tgn import (IdentityMessage,
                                               LastAggregator,
                                               LastNeighborLoader, TGNMemory)
    from core.TgnModel import GraphAttentionEmbedding, LinkPredictor

from .config import fileSha256

# Buffers that hold replay STATE, not learned parameters. They are excluded
# from the parameter fingerprint and reset before a checkpoint is written.
STATE_BUFFERS = ("memory.memory", "memory.last_update", "memory._assoc")


class CheckpointMismatch(RuntimeError):
    ''' The checkpoint on disk is not the one the experiment recorded. '''


def configureTorch(threads):
    requireTorch()
    torch.set_num_threads(int(threads))
    torch.use_deterministic_algorithms(True, warn_only=True)


class EventTgn:
    ''' A TGN over a continuous-time event stream, with exact state
    save/restore so an explainer can branch from a shared prefix. '''

    def __init__(self, numNodes, modelConfig):
        requireTorch()
        self.numNodes = int(numNodes)
        self.config = dict(modelConfig)
        torch.manual_seed(int(modelConfig["seed"]))
        memoryDim = modelConfig["memory_dim"]
        timeDim = modelConfig["time_dim"]
        embeddingDim = modelConfig["embedding_dim"]
        self.rawMessageDim = 1
        self.memory = TGNMemory(
            self.numNodes, raw_msg_dim=self.rawMessageDim,
            memory_dim=memoryDim, time_dim=timeDim,
            message_module=IdentityMessage(self.rawMessageDim, memoryDim,
                                           timeDim),
            aggregator_module=LastAggregator())
        self.embedding = GraphAttentionEmbedding(
            memoryDim, embeddingDim, self.rawMessageDim, self.memory.time_enc)
        self.predictor = LinkPredictor(embeddingDim)
        self.modules = torch.nn.ModuleDict({
            "memory": self.memory, "embedding": self.embedding,
            "predictor": self.predictor})
        self.loader = LastNeighborLoader(self.numNodes,
                                         size=modelConfig["neighbor_size"])
        self._assoc = torch.empty(self.numNodes, dtype=torch.long)
        # Time of the k-th inserted neighbour edge (loader e_id k).
        self._edgeTime = torch.zeros(1 << 16, dtype=torch.long)
        self._one = torch.ones(1, self.rawMessageDim)
        self.checkpointPath = None
        self.checkpointSha256 = None
        self.replayedEvents = 0         # cumulative, for cost reporting

    ##  State  ##

    def eval(self):
        self.modules.eval()

    def reset(self):
        ''' Fresh memory and neighbour store: nothing has been seen. '''
        self.memory.reset_state()
        self.loader.reset_state()

    def getState(self):
        ''' A complete copy of the replay state (cheap: ~0.5 MB). Message
        stores hold immutable tensor tuples that PyG replaces rather than
        edits, so a shallow dict copy is an exact snapshot. '''
        return {
            "memory": self.memory.memory.detach().clone(),
            "last_update": self.memory.last_update.clone(),
            "msg_s": dict(self.memory.msg_s_store),
            "msg_d": dict(self.memory.msg_d_store),
            "neighbors": self.loader.neighbors.clone(),
            "e_id": self.loader.e_id.clone(),
            "cur_e_id": int(self.loader.cur_e_id),
        }

    def setState(self, state):
        with torch.no_grad():
            self.memory.memory.copy_(state["memory"])
            self.memory.last_update.copy_(state["last_update"])
        self.memory.msg_s_store = dict(state["msg_s"])
        self.memory.msg_d_store = dict(state["msg_d"])
        self.loader.neighbors.copy_(state["neighbors"])
        self.loader.e_id.copy_(state["e_id"])
        # Edge times at positions < cur_e_id were written once, in order, and
        # are never overwritten by a replay that starts at cur_e_id.
        self.loader.cur_e_id = state["cur_e_id"]

    ##  Replay and scoring (eval mode)  ##

    def _recordEdgeTimes(self, times):
        start = int(self.loader.cur_e_id)
        end = start + len(times)
        if end > len(self._edgeTime):
            grown = torch.zeros(max(end, 2 * len(self._edgeTime)),
                                dtype=torch.long)
            grown[:len(self._edgeTime)] = self._edgeTime
            self._edgeTime = grown
        self._edgeTime[start:end] = times

    def replay(self, src, dst, ts):
        ''' Feed events into memory one at a time, in the given order. '''
        src = torch.from_numpy(np.array(src, dtype=np.int64))
        dst = torch.from_numpy(np.array(dst, dtype=np.int64))
        ts = torch.from_numpy(np.array(ts, dtype=np.int64))
        with torch.no_grad():
            for i in range(len(ts)):
                s, d, t = src[i:i + 1], dst[i:i + 1], ts[i:i + 1]
                self.memory.update_state(s, d, t, self._one)
                self._recordEdgeTimes(t)
                self.loader.insert(s, d)
        self.replayedEvents += len(ts)

    def _embed(self, nodes):
        n_id, edgeIndex, eId = self.loader(nodes)
        self._assoc[n_id] = torch.arange(n_id.size(0))
        z, lastUpdate = self.memory(n_id)
        z = self.embedding(z, lastUpdate, edgeIndex, self._edgeTime[eId],
                           torch.ones(eId.size(0), self.rawMessageDim))
        return z

    def logit(self, source, destination, t=None):
        ''' Logit that `source` messages `destination`, given the current
        memory. `t` is accepted for interface clarity; the TGN reads time
        through memory last_update and neighbour edge times, as in PyG. '''
        with torch.no_grad():
            nodes = torch.tensor(sorted({int(source), int(destination)}))
            z = self._embed(nodes)
            out = self.predictor(z[self._assoc[torch.tensor([int(source)])]],
                                 z[self._assoc[torch.tensor([int(destination)])]])
        return float(out.reshape(-1)[0])

    def scoreHistory(self, src, dst, ts, source, destination, t=None):
        ''' THE prediction function: reset, replay the whole history, score.
        Same inputs -> bit-identical output (deterministic, sequential). '''
        self.eval()
        self.reset()
        self.replay(src, dst, ts)
        return self.logit(source, destination, t)

    ##  Identity  ##

    def parameterFingerprint(self):
        ''' SHA-256 over the learned parameters (state buffers excluded).
        Computed from the live instance, so each explainer path can report
        exactly which weights it queried. '''
        digest = hashlib.sha256()
        for name, tensor in sorted(self.modules.state_dict().items()):
            if name in STATE_BUFFERS:
                continue
            digest.update(name.encode())
            digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
        return digest.hexdigest()


def sigmoid(x):
    return float(1.0 / (1.0 + np.exp(-x)))


##  Training  ##


def _averagePrecision(scores, labels):
    order = np.argsort(-np.asarray(scores), kind="stable")
    labels = np.asarray(labels)[order]
    hits = np.cumsum(labels)
    precision = hits / np.arange(1, len(labels) + 1)
    return float((precision * labels).sum() / max(labels.sum(), 1))


def _auc(scores, labels):
    scores, labels = np.asarray(scores), np.asarray(labels)
    pos, neg = scores[labels == 1], scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    ranks = np.argsort(np.argsort(np.concatenate([pos, neg]),
                                  kind="stable"), kind="stable") + 1
    # Average ranks for ties (Mann-Whitney U with tie correction).
    allScores = np.concatenate([pos, neg])
    _, inverse, counts = np.unique(allScores, return_inverse=True,
                                   return_counts=True)
    sums = np.bincount(inverse, weights=ranks)
    ranks = (sums / counts)[inverse]
    u = ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2
    return float(u / (len(pos) * len(neg)))


def trainEventTgn(stream, split, modelConfig, log=print):
    ''' Standard PyG TGN training on the training split, model selection by
    validation AP (batched evaluation, as in the PyG reference loop).
    Returns (model, trainingReport). '''
    requireTorch()
    seed = int(modelConfig["seed"])
    random.seed(seed)
    np.random.seed(seed)
    model = EventTgn(stream.num_nodes, modelConfig)
    generator = torch.Generator().manual_seed(seed)
    optimizer = torch.optim.Adam(model.modules.parameters(),
                                 lr=modelConfig["learning_rate"])
    criterion = torch.nn.BCEWithLogitsLoss()
    batchSize = int(modelConfig["batch_size"])
    trainEnd = split["train"][1]
    validationStart, validationEnd = split["validation"]
    src = torch.from_numpy(np.array(stream.src, dtype=np.int64))
    dst = torch.from_numpy(np.array(stream.dst, dtype=np.int64))
    ts = torch.from_numpy(np.array(stream.ts, dtype=np.int64))
    low, high = 1, stream.num_nodes

    def step(begin, end, train):
        s, d, t = src[begin:end], dst[begin:end], ts[begin:end]
        negative = torch.randint(low, high, (s.size(0),), generator=generator)
        n_id = torch.cat([s, d, negative]).unique()
        n_id, edgeIndex, eId = model.loader(n_id)
        model._assoc[n_id] = torch.arange(n_id.size(0))
        z, lastUpdate = model.memory(n_id)
        z = model.embedding(z, lastUpdate, edgeIndex, model._edgeTime[eId],
                            torch.ones(eId.size(0), 1))
        positive = model.predictor(z[model._assoc[s]], z[model._assoc[d]])
        negativeOut = model.predictor(z[model._assoc[s]],
                                      z[model._assoc[negative]])
        model.memory.update_state(s, d, t, torch.ones(s.size(0), 1))
        model._recordEdgeTimes(t)
        model.loader.insert(s, d)
        return positive, negativeOut

    history, best = [], None
    started = time.perf_counter()
    for epoch in range(int(modelConfig["epochs"])):
        model.modules.train()
        model.reset()
        losses = []
        for begin in range(0, trainEnd, batchSize):
            end = min(begin + batchSize, trainEnd)
            optimizer.zero_grad()
            positive, negative = step(begin, end, True)
            loss = (criterion(positive, torch.ones_like(positive))
                    + criterion(negative, torch.zeros_like(negative)))
            loss.backward()
            optimizer.step()
            model.memory.detach()
            losses.append(loss.item())
        # Validation continues from the end-of-training memory.
        model.modules.eval()
        scores, labels = [], []
        with torch.no_grad():
            for begin in range(validationStart, validationEnd, batchSize):
                end = min(begin + batchSize, validationEnd)
                positive, negative = step(begin, end, False)
                scores += positive.sigmoid().flatten().tolist()
                scores += negative.sigmoid().flatten().tolist()
                labels += [1] * positive.numel() + [0] * negative.numel()
        ap = _averagePrecision(scores, labels)
        history.append({"epoch": epoch + 1, "loss": float(np.mean(losses)),
                        "validation_ap_batched": round(ap, 6)})
        log(f"    epoch {epoch + 1:2d}: loss {np.mean(losses):.4f}  "
            f"validation AP (batched) {ap:.4f}")
        if best is None or ap > best[0]:
            best = (ap, epoch + 1,
                    {k: v.detach().clone()
                     for k, v in model.modules.state_dict().items()})

    model.modules.load_state_dict(best[2])
    model.eval()
    model.reset()
    report = {
        "epochs_run": int(modelConfig["epochs"]),
        "selected_epoch": best[1],
        "selection": "highest validation AP (batched PyG evaluation)",
        "history": history,
        "training_seconds": round(time.perf_counter() - started, 1),
        "train_events": trainEnd,
        "negative_sampling": "uniform random destination node id, seeded",
    }
    return model, report


def streamingEvaluation(model, stream, split, seed, log=print):
    ''' Held-out metrics under the SEQUENTIAL protocol used for every
    explanation: replay the stream one event at a time; before each
    validation/test event, score it and one seeded random negative.
    Also returns every test event's logit (used by target selection). '''
    requireTorch()
    rng = np.random.default_rng(seed)
    model.eval()
    model.reset()
    validationStart = split["validation"][0]
    testStart = split["test"][0]
    log("    replaying the training history ...")
    model.replay(stream.src[:validationStart], stream.dst[:validationStart],
                 stream.ts[:validationStart])
    metrics = {}
    testLogits = {}
    for name, (begin, end) in (("validation", split["validation"]),
                               ("test", split["test"])):
        scores, labels = [], []
        log(f"    scoring the {name} split one event at a time "
            f"({end - begin} events) ...")
        for e in range(begin, end):
            a, b = int(stream.src[e]), int(stream.dst[e])
            negative = int(rng.integers(1, stream.num_nodes))
            while negative == b:
                negative = int(rng.integers(1, stream.num_nodes))
            positive = model.logit(a, b)
            scores += [positive, model.logit(a, negative)]
            labels += [1, 0]
            if name == "test":
                testLogits[e] = positive
            model.replay(stream.src[e:e + 1], stream.dst[e:e + 1],
                         stream.ts[e:e + 1])
        scores = np.asarray(scores)
        labels = np.asarray(labels)
        metrics[name] = {
            "average_precision": round(_averagePrecision(scores, labels), 4),
            "auc": round(_auc(scores, labels), 4),
            "accuracy": round(float(((scores > 0) == (labels == 1)).mean()), 4),
            "positives": int(labels.sum()),
            "negatives": int((labels == 0).sum()),
            "chance_level": 0.5,
        }
    metrics["protocol"] = ("sequential replay; one seeded uniform-random "
                           "negative destination per held-out event; "
                           "balanced, so chance AP/AUC/accuracy = 0.5")
    return metrics, testLogits


##  Checkpoints  ##


def saveCheckpoint(model, path, extra):
    requireTorch()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    model.reset()
    with torch.no_grad():
        model.memory._assoc.zero_()   # scratch buffer: make the file canonical
    torch.save({"state_dict": model.modules.state_dict(),
                "num_nodes": model.numNodes,
                "model_config": model.config,
                "extra": extra}, path)
    model.checkpointPath = path
    model.checkpointSha256 = fileSha256(path)
    with open(path + ".json", "w", encoding="utf-8") as handle:
        json.dump({"sha256": model.checkpointSha256,
                   "parameter_fingerprint": model.parameterFingerprint(),
                   "num_nodes": model.numNodes,
                   "model_config": model.config, **extra}, handle, indent=2)
    return model.checkpointSha256


def loadCheckpoint(path, expectedSha256=None):
    ''' Load a checkpoint, refusing it if its bytes are not the recorded
    ones. A mismatch is an error, never a warning: comparing explanations
    of two different weight sets would be meaningless. '''
    requireTorch()
    actual = fileSha256(path)
    if expectedSha256 is not None and actual != expectedSha256:
        raise CheckpointMismatch(
            f"checkpoint {path} has SHA-256 {actual}, but the experiment "
            f"recorded {expectedSha256}")
    payload = torch.load(path, map_location="cpu", weights_only=False)
    model = EventTgn(payload["num_nodes"], payload["model_config"])
    model.modules.load_state_dict(payload["state_dict"])
    model.eval()
    model.reset()
    model.checkpointPath = path
    model.checkpointSha256 = actual
    return model, payload.get("extra", {})
