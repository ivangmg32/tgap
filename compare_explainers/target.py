'''
Deterministic, explainer-blind target selection.

The rule is fixed in the configuration BEFORE either explainer runs and uses
only the data and the model's original prediction - never an explainer
output - so a target cannot be picked because one method looks good on it.

Rule: take the test-split events in a seeded random order and return the
first one that is eligible. Every candidate examined before it is recorded
with its exclusion reasons.

Eligibility (each criterion is needed for a well-defined comparison):
  1. Unique timestamp. The history is "every event strictly before t"; a
     simultaneous event would be neither clearly past nor clearly future.
  2. Both endpoints appeared before t. A node with no history has a blank
     memory: neither explainer would have anything to explain.
  3. The model predicts the observed message correctly (logit > 0). This
     mirrors CoDy's own default evaluation setting ("correct predictions
     only") and makes a counterfactual well-posed: flip a correct "message".
'''

import numpy as np


def firstAppearance(stream):
    ''' Event id at which each node first sends or receives a message. '''
    first = np.full(stream.num_nodes, np.iinfo(np.int64).max, dtype=np.int64)
    ids = stream.event_ids
    np.minimum.at(first, stream.src, ids)
    np.minimum.at(first, stream.dst, ids)
    return first


def selectTargets(stream, split, testLogits, config, count=1):
    rule = config["target_selection"]
    if rule["split"] != "test":
        raise ValueError("the pilot selects its target from the test split")
    begin, end = split["test"]
    order = np.random.default_rng(rule["seed"]).permutation(
        np.arange(begin, end))
    first = firstAppearance(stream)
    timestamps, counts = np.unique(stream.ts, return_counts=True)
    multiplicity = dict(zip(timestamps.tolist(), counts.tolist()))

    examined, chosen = [], []
    for rank, eventId in enumerate(order[:rule["max_candidates_examined"]]):
        eventId = int(eventId)
        a, b, t = int(stream.src[eventId]), int(stream.dst[eventId]), \
            int(stream.ts[eventId])
        reasons = []
        if multiplicity[t] != 1:
            reasons.append(f"{multiplicity[t]} events share timestamp {t}")
        if first[a] >= eventId:
            reasons.append(f"source {a} has no history before t")
        if first[b] >= eventId:
            reasons.append(f"destination {b} has no history before t")
        logit = testLogits.get(eventId)
        if logit is None:
            reasons.append("no original score available")
        elif not logit > 0:
            reasons.append(f"model predicts no message (logit {logit:.4f})")
        if reasons:
            examined.append({"rank": rank, "event_id": eventId,
                             "excluded": True, "reasons": reasons})
            continue
        examined.append({"rank": rank, "event_id": eventId,
                         "excluded": False, "reasons": []})
        pairMask = (((stream.src[:eventId] == a) & (stream.dst[:eventId] == b))
                    | ((stream.src[:eventId] == b) & (stream.dst[:eventId] == a)))
        chosen.append({
            "event_id": eventId,
            "source": a,
            "destination": b,
            "timestamp": t,
            "timestamp_days": round(t / 86400.0, 4),
            "split": "test",
            "ground_truth": "the message A -> B was observed at t "
                            "(positive link, label 1)",
            "ground_truth_label": 1,
            "history_events": eventId,
            "prior_messages_between_a_and_b": int(pairMask.sum()),
            "selection_rank": rank,
            "selection_rule": rule["rule"],
            "eligibility": rule["eligibility"],
            "selection_seed": rule["seed"],
        })
        if len(chosen) == count:
            break
    if not chosen:
        raise RuntimeError(
            f"no eligible target among the first "
            f"{rule['max_candidates_examined']} candidates")
    return chosen, examined


def selectTarget(stream, split, testLogits, config):
    ''' The first eligible target (the pilot / demonstration case). '''
    targets, examined = selectTargets(stream, split, testLogits, config, 1)
    return targets[0], examined
