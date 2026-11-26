'''
The pilot comparison, end to end, with a reproducibility record.

Order of work (each stage gates the next):
    A  data      canonical UCI-Messages stream, fingerprinted, split
    B  model     ONE TGN checkpoint (trained once, then loaded by hash)
    C  target    explainer-blind deterministic selection
    D  baseline  the same original score through every path, or stop
    E  TGAP      Churn via TgapExplainer on the same model and history
    F  CoDy      official CoDy search on the same model and history
    G  verify    same weights + same input on both paths, then write
'''

import json
import os
import platform
import subprocess
import time
from datetime import datetime, timezone

import numpy as np

import paths

from .config import (LATEST_RECORD, MODELS_DIR, RECORDS_DIR, configHash,
                     experimentId, fileSha256, pilotConfig)
from .dataset import (chronologicalSplit, historyBefore, loadUciMessages,
                      streamFingerprint)
from .target import selectTarget
from .tgn_backend import (CheckpointMismatch, configureTorch, loadCheckpoint,
                          saveCheckpoint, sigmoid, streamingEvaluation,
                          trainEventTgn)


def _relative(path):
    return os.path.relpath(path, paths.ROOT).replace(os.sep, "/")


def softwareVersions():
    versions = {"python": platform.python_version(),
                "platform": platform.platform()}
    for module in ("torch", "torch_geometric", "numpy", "pandas", "networkx"):
        try:
            versions[module] = __import__(module).__version__
        except Exception:                 # pragma: no cover
            versions[module] = None
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=paths.ROOT,
                                capture_output=True, text=True,
                                timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"],
                               cwd=paths.ROOT, capture_output=True, text=True,
                               timeout=10).stdout.strip() != ""
        versions["tgap_git_commit"] = commit or None
        versions["tgap_git_dirty"] = dirty
    except Exception:                     # pragma: no cover
        versions["tgap_git_commit"] = None
    return versions


def modelKey(config, stream):
    ''' The checkpoint is a function of data, split and model settings only;
    explainer settings never cause retraining. '''
    return configHash({"stream": stream.fingerprint(), "split": config["split"],
                       "model": config["model"]})[:12]


def prepareModel(config, stream, split, retrain=False, log=print):
    ''' Load the recorded checkpoint, or train it once. Returns
    (backend, modelSection, testLogits). '''
    key = modelKey(config, stream)
    path = os.path.join(MODELS_DIR, f"tgn_uci_{key}.pt")
    meta = path + ".json"
    logitsPath = os.path.join(MODELS_DIR, f"tgn_uci_{key}_test_logits.npz")
    if os.path.exists(path) and os.path.exists(meta) and not retrain:
        with open(meta, encoding="utf-8") as handle:
            recorded = json.load(handle)
        log(f"  B. loading checkpoint {_relative(path)}")
        backend, extra = loadCheckpoint(path, recorded["sha256"])
        if backend.parameterFingerprint() != recorded["parameter_fingerprint"]:
            raise CheckpointMismatch("parameter fingerprint differs from the "
                                     "recorded one")
    else:
        log("  B. training the TGN once (it is then reused by hash) ...")
        backend, training = trainEventTgn(stream, split, config["model"], log)
        log("     sequential held-out evaluation ...")
        evaluation, logits = streamingEvaluation(
            backend, stream, split, config["model"]["seed"], log)
        extra = {"training": training, "evaluation": evaluation,
                 "model_key": key, "stream_sha256": stream.fingerprint(),
                 "split": split}
        saveCheckpoint(backend, path, extra)
        np.savez(logitsPath, ids=np.array(list(logits), dtype=np.int64),
                 logits=np.array(list(logits.values()), dtype=np.float64),
                 checkpoint_sha256=np.array(backend.checkpointSha256))
        with open(meta, encoding="utf-8") as handle:
            recorded = json.load(handle)
    cached = np.load(logitsPath)
    if str(cached["checkpoint_sha256"]) != backend.checkpointSha256:
        raise CheckpointMismatch("cached test scores belong to another "
                                 "checkpoint")
    testLogits = dict(zip(cached["ids"].tolist(), cached["logits"].tolist()))
    section = {
        "implementation": "compare_explainers.tgn_backend.EventTgn "
                          "(core.TgnModel GraphAttentionEmbedding + "
                          "LinkPredictor; PyG TGNMemory, IdentityMessage, "
                          "LastAggregator, LastNeighborLoader)",
        "configuration": config["model"],
        "checkpoint": _relative(path),
        "checkpoint_sha256": backend.checkpointSha256,
        "parameter_fingerprint": recorded["parameter_fingerprint"],
        "model_key": key,
        "training": extra.get("training"),
        "evaluation": extra.get("evaluation"),
        "why_not_the_existing_tgap_tgn_adapter": (
            "core.TgnModel.TgnTemporalGraphModel reads snapshots (time = "
            "snapshot index) and returns the MEAN probability of the last "
            "snapshot's edges; it scores no single link and keeps no "
            "checkpoint. CoDy explains one event of an event stream, so it "
            "cannot query that adapter without changing its semantics. One "
            "event-level TGN built from the same modules is trained instead "
            "and both explainers call it."),
    }
    return backend, section, testLogits


def baselineConsistency(backend, stream, target, testLogits, config, log=print):
    ''' The original score of the target through every independent path.
    The comparison is only "comparable" if all agree within tolerance and
    all read the same input. '''
    from .cody_adapter import codyDataset, makeWrapper
    from .tgap_adapter import SnapshotView, TargetLinkTgnModel

    end = historyBefore(stream, target["event_id"])
    a, b, t = target["source"], target["destination"], target["timestamp"]
    history = streamFingerprint(stream.src[:end], stream.dst[:end],
                                stream.ts[:end])
    log("  D. baseline consistency: direct replay ...")
    direct = backend.scoreHistory(stream.src[:end], stream.dst[:end],
                                  stream.ts[:end], a, b, t)
    log("     ... TGAP path (snapshots -> lift -> TGN) ...")
    view = SnapshotView(stream.src[:end], stream.dst[:end], stream.ts[:end],
                        t, config["tgap"]["window_days"])
    tgapModel = TargetLinkTgnModel(backend, view, a, b)
    tgapModel.predict(view.snapshots)
    tgapCall = tgapModel.calls[0]
    log("     ... CoDy path (TGNNWrapper initialize + predict) ...")
    wrapper = makeWrapper(backend, codyDataset(stream),
                          config["cody"]["num_hops"])
    wrapper.reset_model()
    wrapper.initialize(target["event_id"] - 1)
    wrapper.predict(target["event_id"], result_as_logit=True)
    codyCall = wrapper.prediction_log[target["event_id"]]
    paths_ = {
        "direct_full_replay": {"logit": direct, "input_fingerprint": history},
        "selection_stream_pass": {"logit": testLogits[target["event_id"]],
                                  "input_fingerprint": history},
        "tgap_adapter": {"logit": tgapCall["logit"],
                         "input_fingerprint": tgapCall["input_fingerprint"],
                         "parameter_fingerprint":
                             tgapCall["parameter_fingerprint"]},
        "cody_wrapper": {"logit": codyCall["logit"],
                         "input_fingerprint": codyCall["input_fingerprint"],
                         "parameter_fingerprint":
                             codyCall["parameter_fingerprint"]},
    }
    return assessBaseline(paths_, history, backend.parameterFingerprint(),
                          config["inference"]["baseline_tolerance"])


def assessBaseline(paths_, historyFingerprint, parameterFingerprint, tolerance):
    ''' Pure decision function (unit-tested): do all paths agree? '''
    logits = [p["logit"] for p in paths_.values()]
    spread = float(max(logits) - min(logits))
    sameInput = all(p["input_fingerprint"] == historyFingerprint
                    for p in paths_.values())
    sameModel = all(p.get("parameter_fingerprint", parameterFingerprint)
                    == parameterFingerprint for p in paths_.values())
    agree = spread <= tolerance
    reasons = []
    if not agree:
        reasons.append(f"original logits differ by {spread:.3e} "
                       f"(tolerance {tolerance:.1e})")
    if not sameInput:
        reasons.append("the paths did not read the same history")
    if not sameModel:
        reasons.append("the paths did not query the same weights")
    for p in paths_.values():
        p["probability"] = sigmoid(p["logit"])
    reference = (paths_.get("direct_full_replay")
                 or next(iter(paths_.values())))["logit"]
    return {"paths": paths_, "max_abs_logit_difference": spread,
            "tolerance": tolerance, "scores_agree": agree,
            "same_input": sameInput, "same_model": sameModel,
            "passed": agree and sameInput and sameModel, "reasons": reasons,
            "original_logit": reference,
            "original_probability": sigmoid(reference),
            "original_class": "message" if reference > 0 else "no message"}


def comparability(record):
    ''' What the record may be called. Derived, never asserted. '''
    baseline = record["baseline_consistency"]
    model = record["model"]
    tgap, cody = record.get("tgap") or {}, record.get("cody") or {}
    sharedModel = (baseline["same_model"]
                   and tgap.get("baseline", {}).get("parameter_fingerprint")
                   == model["parameter_fingerprint"]
                   and (cody.get("original_prediction_path") or {}).get(
                       "parameter_fingerprint") == model["parameter_fingerprint"])
    sameInput = (baseline["same_input"]
                 and tgap.get("baseline", {}).get("input_fingerprint")
                 == record["target"]["history_fingerprint"]
                 and (cody.get("original_prediction_path") or {}).get(
                     "input_fingerprint") == record["target"]["history_fingerprint"])
    explainerBaselines = []
    if tgap.get("baseline"):
        explainerBaselines.append(tgap["baseline"]["logit"])
    if cody.get("original_logit") is not None:
        explainerBaselines.append(cody["original_logit"])
    explainersAgree = all(abs(x - baseline["original_logit"])
                          <= baseline["tolerance"] for x in explainerBaselines)
    reasons = list(baseline["reasons"])
    if not sharedModel:
        reasons.append("shared-model condition not verified on both "
                       "explainer paths")
    if not sameInput:
        reasons.append("same-input condition not verified on both "
                       "explainer paths")
    if not explainersAgree:
        reasons.append("an explainer's internal original score differs from "
                       "the baseline")
    comparable = (baseline["passed"] and sharedModel and sameInput
                  and explainersAgree)
    return {
        "comparable": comparable,
        "label": ("scientific comparison: same model, same input, same "
                  "original score" if comparable else
                  "NOT COMPARABLE - technical demonstration only"),
        "shared_model_verified": sharedModel,
        "same_input_verified": sameInput,
        "explainer_baselines_agree": explainersAgree,
        "tgap_status": tgap.get("status"),
        "cody_status": cody.get("status"),
        "requested_scenario_completed": (comparable
                                         and tgap.get("status") == "valid"
                                         and cody.get("status") not in
                                         (None, "timeout",
                                          "execution_failure")),
        "reasons": reasons,
    }


def run(config=None, retrain=False, allowNonComparable=False, log=print,
        write=True):
    config = config or pilotConfig()
    configureTorch(config["inference"]["torch_threads"])
    expId = experimentId(config)
    timings = {}
    clock = time.perf_counter()
    log("=" * 72)
    log(f"TGAP vs CoDy  [{expId}]  {config['experiment_name']}")
    log("=" * 72)

    log("  A. loading the canonical UCI-Messages stream ...")
    stream = loadUciMessages(config)
    split = chronologicalSplit(stream, config)
    timings["data_seconds"] = round(time.perf_counter() - clock, 2)

    clock = time.perf_counter()
    backend, modelSection, testLogits = prepareModel(config, stream, split,
                                                     retrain, log)
    timings["model_seconds"] = round(time.perf_counter() - clock, 2)

    clock = time.perf_counter()
    target, examined = selectTarget(stream, split, testLogits, config)
    end = historyBefore(stream, target["event_id"])
    target["history_fingerprint"] = streamFingerprint(
        stream.src[:end], stream.dst[:end], stream.ts[:end])
    target["target_in_history"] = bool(end > target["event_id"])
    target["latest_history_timestamp"] = int(stream.ts[end - 1])
    target["examined_candidates"] = examined
    log(f"  C. target: event {target['event_id']}  {target['source']} -> "
        f"{target['destination']} at t={target['timestamp']} "
        f"(day {target['timestamp_days']}), {end} history events")
    timings["target_seconds"] = round(time.perf_counter() - clock, 2)

    clock = time.perf_counter()
    baseline = baselineConsistency(backend, stream, target, testLogits,
                                   config, log)
    timings["baseline_seconds"] = round(time.perf_counter() - clock, 2)
    log(f"     original logit {baseline['original_logit']:.9f} "
        f"(p = {baseline['original_probability']:.6f}); spread "
        f"{baseline['max_abs_logit_difference']:.2e}; "
        f"{'PASSED' if baseline['passed'] else 'FAILED'}")

    record = {
        "record_version": 1,
        "experiment_id": expId,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "configuration": config,
        "configuration_hash": configHash(config),
        "software": softwareVersions(),
        "dataset": {**stream.provenance, "split": split},
        "model": modelSection,
        "target": target,
        "baseline_consistency": baseline,
        "tgap": None,
        "cody": None,
        "timings": timings,
    }

    if baseline["passed"] or allowNonComparable:
        from .tgap_adapter import runTgap
        from .cody_adapter import runCody
        clock = time.perf_counter()
        log("  E. TGAP ...")
        record["tgap"] = runTgap(backend, stream, target, config, log)
        timings["tgap_seconds"] = round(time.perf_counter() - clock, 2)
        primary = next((d for d in record["tgap"]["directions"]
                        if d["direction"] == record["tgap"].get(
                            "primary_direction")), None)
        if primary:
            log(f"     {primary['label']}: churn {primary['churn_before']:.6f}"
                f" -> {primary['churn_after']:.6f} (achieved "
                f"{primary['achieved_delta']:+.4f}); p "
                f"{primary['original_probability']:.6f} -> "
                f"{primary['modified_probability']:.6f}; impact "
                f"{primary['normalized_impact']}; status {primary['status']}")
        clock = time.perf_counter()
        log("  F. CoDy ...")
        record["cody"] = runCody(backend, stream, target, config, log)
        timings["cody_seconds"] = round(time.perf_counter() - clock, 2)
        log(f"     status {record['cody']['status']}; "
            f"{record['cody']['event_count']} events; "
            f"{record['cody']['termination']}; "
            f"{record['cody']['runtime_seconds']} s")
    else:
        log("  Baseline check FAILED: explainers not run "
            "(pass --allow-noncomparable for a technical demonstration).")

    record["comparability"] = comparability(record)
    log(f"  G. {record['comparability']['label']}")
    if write:
        writeRecord(record)
    return record


def writeRecord(record):
    os.makedirs(RECORDS_DIR, exist_ok=True)
    path = os.path.join(RECORDS_DIR, record["experiment_id"] + ".json")
    text = json.dumps(record, indent=2, allow_nan=False, default=_jsonDefault)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    with open(LATEST_RECORD, "w", encoding="utf-8") as handle:
        json.dump({"experiment_id": record["experiment_id"],
                   "record": _relative(path),
                   "record_sha256": fileSha256(path)}, handle, indent=2)
    from .export import writeExports
    writeExports(record, os.path.join(RECORDS_DIR, record["experiment_id"]))
    return path


def _jsonDefault(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serialisable: {type(value)}")


def loadLatest():
    with open(LATEST_RECORD, encoding="utf-8") as handle:
        pointer = json.load(handle)
    path = os.path.join(paths.ROOT, pointer["record"])
    if fileSha256(path) != pointer["record_sha256"]:
        raise ValueError("the latest record changed after it was written")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
