'''
The shared experiment contract.

ONE configuration object is the single source of truth for both explainers.
Everything that could make the two runs differ - data, split, model, target
rule, decision rule, seeds, explainer parameters, budgets - lives here, and
the configuration hash becomes part of the experiment id. Two records with
the same id were produced from the same contract.
'''

import copy
import hashlib
import json
import os

import paths

OUTPUT_ROOT = os.path.join(paths.OUTPUT, "compare_explainers")
MODELS_DIR = os.path.join(OUTPUT_ROOT, "models")
RECORDS_DIR = os.path.join(OUTPUT_ROOT, "records")
LATEST_RECORD = os.path.join(OUTPUT_ROOT, "latest.json")

# Bumped whenever preprocessing semantics change, so old records are not
# silently read as if they came from the current code.
PREPROCESSING_VERSION = "uci-canonical-1"
CONTRACT_VERSION = "tgap-vs-cody-contract-1"

PILOT_CONFIG = {
    "contract_version": CONTRACT_VERSION,
    "experiment_name": "uci-tgn-pilot",
    "dataset": {
        "id": "uci_messages",
        "source_key": "tgbl_uci",
        "archive": "tgbl-uci.zip",
        "member": "tgbl-uci_edgelist.csv",
        "preprocessing_version": PREPROCESSING_VERSION,
        "timestamp_unit": "seconds since the first message "
                          "(2004-04-15 07:56:01 UTC)",
        "node_id_mapping": "identity: TGB node id n -> TGN memory slot n "
                           "(slot 0 unused)",
        "direction": "sender -> receiver as stored in the file",
    },
    "split": {
        "method": "chronological, by timestamp quantile (as in TGN/CoDy)",
        "train": 0.70,
        "validation": 0.15,
        "test": 0.15,
    },
    "model": {
        "name": "TGN (event-level)",
        "memory_dim": 32,
        "time_dim": 32,
        "embedding_dim": 32,
        "neighbor_size": 10,
        "raw_message": "constant 1.0 per event (UCI has no edge features)",
        "seed": 42,
        "epochs": 10,
        "batch_size": 200,
        "learning_rate": 1e-4,
    },
    "inference": {
        "protocol": "sequential: every history event is replayed one at a "
                    "time, in event-id order, from a reset memory",
        "score": "sigmoid(logit) of the TGN link predictor for (A, B) at t",
        "decision_rule": "predicted class = 'message' when logit > 0 "
                         "(probability > 0.5); CoDy's own counterfactual "
                         "criterion is a sign change of this logit",
        "decision_threshold_probability": 0.5,
        "torch_threads": 1,
        "baseline_tolerance": 1e-9,
    },
    "target_selection": {
        "split": "test",
        "seed": 42,
        "rule": "seeded permutation of test-split events; take the first "
                "event that is eligible",
        "eligibility": [
            "no other event shares its timestamp (history = strictly earlier)",
            "both endpoints sent or received a message before t",
            "the model predicts it correctly as a message (logit > 0)",
        ],
        "max_candidates_examined": 400,
    },
    "tgap": {
        "concept": "churn",
        "direction": "decrease",
        "requested_delta": 0.2,
        "window_days": 10,
        "communities": None,
        "seed": 42,
    },
    "cody": {
        "selection_policy": "spatio-temporal",
        "num_hops": 2,
        "candidates_size": 64,
        "max_steps": 300,
        "alpha": 2 / 3,
        "approximate_predictions": True,
        "time_limit_seconds": 1800,
        "seed": 42,
    },
}


def pilotConfig(**overrides):
    ''' A deep copy of the pilot contract, with optional section overrides,
    e.g. pilotConfig(cody={"max_steps": 50}). Unknown keys are refused so a
    typo cannot silently fall back to a default. '''
    config = copy.deepcopy(PILOT_CONFIG)
    for section, values in overrides.items():
        if section not in config or not isinstance(config[section], dict):
            raise KeyError(f"unknown configuration section: {section}")
        for key, value in values.items():
            if key not in config[section]:
                raise KeyError(f"unknown configuration key: {section}.{key}")
            config[section][key] = value
    return config


def canonicalJson(value):
    ''' Stable JSON: sorted keys, no whitespace variation. '''
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=str)


def configHash(config):
    return hashlib.sha256(canonicalJson(config).encode()).hexdigest()


def experimentId(config):
    return "cmp-" + configHash(config)[:12]


def fileSha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
