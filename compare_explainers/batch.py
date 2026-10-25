'''
The technical evaluation set and the human-study case bank.

    python -m compare_explainers batch --count 30 --workers 6
    python -m compare_explainers casebank

TECHNICAL SET (preregistered by its rule, not by its outcomes)
    The first `count` eligible test-split targets under the pilot's selection
    rule (seeded permutation, same eligibility). Every attempted case is kept
    with its status - valid counterfactuals, non-flipping results, no result,
    timeouts and failures alike. Nothing is dropped after looking at results.

    Each case runs TGAP (Churn, both directions) and the official CoDy search
    on the same loaded checkpoint and the same history. Baseline consistency
    uses three independent paths: the target-selection stream pass, TGAP's
    own baseline call, and CoDy's own original-score computation (plus the
    weights and input fingerprints each path reports).

CASE BANK (for the human study - NOT for estimating CoDy's success rate)
    From the technical set, in selection order: the demonstration case (the
    first target), then the first comparable case of each CoDy outcome
    category that occurs (valid counterfactual, no class change, no
    counterfactual). A category that never occurs is reported as absent;
    no case is invented to fill it. Because it is stratified by outcome, the
    case bank must not be used to estimate how often CoDy succeeds; use the
    technical set summary for that.

Each case record is cached under records/batch/<batch-id>/ and reused when the
configuration and checkpoint are unchanged.
'''

import json
import os
import time
from datetime import datetime, timezone
from multiprocessing import get_context

import numpy as np

from .config import (OUTPUT_ROOT, RECORDS_DIR, configHash, fileSha256,
                     pilotConfig)
from .dataset import chronologicalSplit, historyBefore, loadUciMessages, \
    streamFingerprint
from .target import selectTargets

BATCH_ROOT = os.path.join(RECORDS_DIR, "batch")
CASEBANK = os.path.join(OUTPUT_ROOT, "casebank.json")
CATEGORIES = ("valid_counterfactual", "no_class_change", "no_counterfactual")

_WORKER = {}


def _init(config):
    from .pipeline import prepareModel, softwareVersions
    from .tgn_backend import configureTorch
    configureTorch(config["inference"]["torch_threads"])
    stream = loadUciMessages(config)
    split = chronologicalSplit(stream, config)
    backend, modelSection, testLogits = prepareModel(
        config, stream, split, log=lambda *a: None)
    _WORKER.update(config=config, stream=stream, split=split, backend=backend,
                   model=modelSection, logits=testLogits,
                   software=softwareVersions())


def runCase(target):
    ''' Both explainers on one target; returns a full case record. Runs in a
    worker process (see _init). Failures are recorded, never raised. '''
    from .cody_adapter import runCody
    from .pipeline import assessBaseline, comparability
    from .tgap_adapter import runTgap
    w = _WORKER
    config, stream, backend = w["config"], w["stream"], w["backend"]
    quiet = lambda *a: None                                  # noqa: E731
    end = historyBefore(stream, target["event_id"])
    target = dict(target, history_fingerprint=streamFingerprint(
        stream.src[:end], stream.dst[:end], stream.ts[:end]))
    timings, record = {}, {}
    started = time.perf_counter()
    try:
        record["tgap"] = runTgap(backend, stream, target, config, quiet)
    except Exception as error:                               # reported
        record["tgap"] = {"status": "execution_failure", "directions": [],
                          "error": f"{type(error).__name__}: {error}"}
    timings["tgap_seconds"] = round(time.perf_counter() - started, 2)
    started = time.perf_counter()
    try:
        record["cody"] = runCody(backend, stream, target, config, quiet)
    except Exception as error:                               # reported
        record["cody"] = {"status": "execution_failure", "events": [],
                          "event_count": 0, "counterfactual_found": False,
                          "error": f"{type(error).__name__}: {error}"}
    timings["cody_seconds"] = round(time.perf_counter() - started, 2)

    paths = {"selection_stream_pass": {
        "logit": w["logits"][target["event_id"]],
        "input_fingerprint": target["history_fingerprint"]}}
    if record["tgap"].get("baseline"):
        b = record["tgap"]["baseline"]
        paths["tgap_adapter"] = {"logit": b["logit"],
                                 "input_fingerprint": b["input_fingerprint"],
                                 "parameter_fingerprint":
                                     b["parameter_fingerprint"]}
    original = (record["cody"] or {}).get("original_prediction_path")
    if original:
        paths["cody_wrapper"] = {"logit": original["logit"],
                                 "input_fingerprint":
                                     original["input_fingerprint"],
                                 "parameter_fingerprint":
                                     original["parameter_fingerprint"]}
    baseline = assessBaseline(paths, target["history_fingerprint"],
                              backend.parameterFingerprint(),
                              config["inference"]["baseline_tolerance"])
    if len(paths) < 3:
        baseline["passed"] = False
        baseline["reasons"].append("an explainer failed before reporting "
                                   "its original score")
    record = {
        "record_version": 2,
        "kind": "case",
        "case_id": f"uci-{target['event_id']}",
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "configuration": config,
        "configuration_hash": configHash(config),
        "software": w["software"],
        "dataset": {**stream.provenance, "split": w["split"]},
        "model": w["model"],
        "target": target,
        "baseline_consistency": baseline,
        "baseline_protocol": ("three independent paths: target-selection "
                              "stream pass, TGAP's baseline call, CoDy's "
                              "original-score computation"),
        "provenance": "precomputed offline by compare_explainers.batch",
        **record,
        "timings": timings,
    }
    record["comparability"] = comparability(record)
    return record


def batchId(config, checkpointSha, count):
    return "b-" + configHash({"config": config, "checkpoint": checkpointSha,
                              "count": count})[:12]


def runBatch(count=30, workers=6, config=None, log=print):
    from .pipeline import prepareModel, _jsonDefault
    from .tgn_backend import configureTorch
    config = config or pilotConfig()
    configureTorch(config["inference"]["torch_threads"])
    stream = loadUciMessages(config)
    split = chronologicalSplit(stream, config)
    backend, model, logits = prepareModel(config, stream, split, log=log)
    targets, examined = selectTargets(stream, split, logits, config, count)
    bid = batchId(config, backend.checkpointSha256, count)
    folder = os.path.join(BATCH_ROOT, bid)
    os.makedirs(folder, exist_ok=True)
    todo = [t for t in targets
            if not os.path.exists(os.path.join(folder, f"uci-{t['event_id']}.json"))]
    log(f"Batch {bid}: {len(targets)} targets, {len(targets) - len(todo)} "
        f"cached, running {len(todo)} on {workers} workers ...")
    started = time.perf_counter()
    if todo:
        with get_context("spawn").Pool(workers, initializer=_init,
                                        initargs=(config,)) as pool:
            for record in pool.imap_unordered(runCase, todo):
                path = os.path.join(folder, record["case_id"] + ".json")
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(record, handle, indent=2, allow_nan=False,
                              default=_jsonDefault)
                log(f"  {record['case_id']}: TGAP {record['tgap']['status']}, "
                    f"CoDy {record['cody']['status']}, "
                    f"{'comparable' if record['comparability']['comparable'] else 'NOT comparable'} "
                    f"({record['timings']})")
    cases = []
    for t in targets:
        path = os.path.join(folder, f"uci-{t['event_id']}.json")
        cases.append({"case_id": f"uci-{t['event_id']}",
                      "selection_rank": t["selection_rank"],
                      "record": os.path.basename(path),
                      "record_sha256": fileSha256(path)})
    manifest = {"batch_id": bid, "count": len(targets),
                "selection_rule": config["target_selection"],
                "examined_candidates": examined,
                "checkpoint_sha256": backend.checkpointSha256,
                "configuration_hash": configHash(config),
                "seconds": round(time.perf_counter() - started, 1),
                "cases": cases}
    with open(os.path.join(folder, "manifest.json"), "w",
              encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    with open(os.path.join(BATCH_ROOT, "latest.json"), "w",
              encoding="utf-8") as handle:
        json.dump({"batch_id": bid}, handle)
    summary = technicalSummary(folder)
    with open(os.path.join(folder, "technical_summary.json"), "w",
              encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    log(json.dumps(summary["counts"], indent=1))
    return folder


def loadBatch(folder=None):
    if folder is None:
        with open(os.path.join(BATCH_ROOT, "latest.json")) as handle:
            folder = os.path.join(BATCH_ROOT, json.load(handle)["batch_id"])
    with open(os.path.join(folder, "manifest.json")) as handle:
        manifest = json.load(handle)
    records = []
    for case in manifest["cases"]:
        path = os.path.join(folder, case["case_id"] + ".json")
        if fileSha256(path) != case["record_sha256"]:
            raise ValueError(f"{case['case_id']} changed after the batch")
        with open(path) as handle:
            records.append(json.load(handle))
    return folder, manifest, records


def technicalSummary(folder):
    ''' Technical outcomes over EVERY attempted case of the technical set. '''
    _, manifest, records = loadBatch(folder)
    cody = [r["cody"]["status"] for r in records]
    tgapPrimary = []
    for r in records:
        t = r["tgap"]
        d = next((x for x in t.get("directions", [])
                  if x["direction"] == t.get("primary_direction")), None)
        tgapPrimary.append(d)
    valid = [d for d in tgapPrimary if d and d["status"] == "valid"]
    achieved = [d["achieved_delta"] for d in valid]
    count = len(records)

    def rate(n):
        return {"n": n, "of": count, "share": round(n / count, 4) if count else None}
    return {
        "batch_id": manifest["batch_id"],
        "cases_attempted": count,
        "note": ("Every attempted case is counted. This is the technical set "
                 "(first eligible targets by the preregistered rule), so "
                 "these rates describe this model and configuration only."),
        "counts": {
            "baseline_verified": rate(sum(r["baseline_consistency"]["passed"] for r in records)),
            "comparable": rate(sum(r["comparability"]["comparable"] for r in records)),
            "tgap_valid_transformation": rate(len(valid)),
            "tgap_noop": rate(sum(1 for d in tgapPrimary if d and d["status"] == "noop")),
            "tgap_invalid_or_failed": rate(sum(1 for d in tgapPrimary if not d or d["status"] not in ("valid", "noop"))),
            "tgap_class_changed": rate(sum(1 for d in valid if d["class_changed"])),
            "cody_valid_counterfactual": rate(cody.count("valid_counterfactual")),
            "cody_no_class_change": rate(cody.count("no_class_change")),
            "cody_no_counterfactual": rate(cody.count("no_counterfactual")),
            "cody_timeout": rate(cody.count("timeout")),
            "cody_execution_failure": rate(cody.count("execution_failure")),
            "cody_not_reproduced": rate(cody.count("reported_counterfactual_not_reproduced")),
        },
        "tgap_achieved_change": ({"min": min(achieved), "median": float(np.median(achieved)),
                                  "max": max(achieved)} if achieved else None),
        "tgap_seconds_median": float(np.median([r["timings"]["tgap_seconds"] for r in records])) if records else None,
        "cody_seconds_median": float(np.median([r["timings"]["cody_seconds"] for r in records])) if records else None,
        "cases": [{"case_id": r["case_id"], "tgap": (d or {}).get("status", r["tgap"]["status"]),
                   "cody": r["cody"]["status"], "comparable": r["comparability"]["comparable"],
                   "original_score": r["baseline_consistency"]["original_probability"]}
                  for r, d in zip(records, tgapPrimary)],
    }


def buildCaseBank(folder=None, log=print):
    ''' Select the human-study cases from the technical set by the rule in
    the module docstring, and write output/compare_explainers/casebank.json. '''
    folder, manifest, records = loadBatch(folder)
    byId = {r["case_id"]: r for r in records}
    ordered = [byId[c["case_id"]] for c in sorted(manifest["cases"], key=lambda c: c["selection_rank"])]
    chosen, absent = [], []
    demo = ordered[0]
    chosen.append((demo, "demonstration case: the first eligible target (the pilot case)"))
    for category in CATEGORIES:
        if any(r is demo for r, _ in chosen) and demo["cody"]["status"] == category \
                and demo["comparability"]["comparable"]:
            continue                                     # demo already covers it
        hit = next((r for r in ordered if r["cody"]["status"] == category
                    and r["comparability"]["comparable"]
                    and all(r is not c for c, _ in chosen)), None)
        if hit:
            chosen.append((hit, f"first comparable case (in selection order) whose CoDy outcome is '{category}'"))
        else:
            absent.append(category)
    root = os.path.dirname(os.path.dirname(OUTPUT_ROOT))
    cases = []
    for record, reason in chosen:
        path = os.path.join(folder, record["case_id"] + ".json")
        cases.append({"case_id": record["case_id"],
                      "record": os.path.relpath(path, root).replace(os.sep, "/"),
                      "record_sha256": fileSha256(path),
                      "inclusion_reason": reason,
                      "cody_status": record["cody"]["status"],
                      "tgap_status": record["tgap"]["status"],
                      "original_score": record["baseline_consistency"]["original_probability"],
                      "selection_rank": record["target"]["selection_rank"]})
    bank = {"batch_id": manifest["batch_id"],
            "rule": ("demonstration case first, then the first comparable "
                     "case of each CoDy outcome category in selection order; "
                     "chosen before any participant data exists"),
            "absent_categories": absent,
            "warning": ("Stratified by CoDy outcome for usability testing. Do "
                        "not use it to estimate CoDy's success rate; see the "
                        "technical summary of the batch."),
            "cases": cases}
    with open(CASEBANK, "w", encoding="utf-8") as handle:
        json.dump(bank, handle, indent=2)
    log(f"Case bank: {[c['case_id'] + ' (' + c['cody_status'] + ')' for c in cases]}; "
        f"absent categories: {absent or 'none'}")
    return bank
