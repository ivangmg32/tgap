'''
Adapter for TGB's tgbl-wiki dataset.

WHAT THE RAW FILE ACTUALLY CONTAINS (verified by reading it, not assumed):
    archive  tgbl-wiki-v2.zip, 40.9 MB
    member   tgbl-wiki_edgelist_v2.csv, 559.9 MB uncompressed
    header   user_id, item_id, timestamp, state_label,
             comma_separated_list_of_features
    rows     176 comma-separated fields each: the 5 named columns, where
             the last "column" is really 172 edit-feature values. We read
             only the first three fields and ignore the features, which is
             why a 560 MB file streams in a few seconds.
    measured 157,474 events | 8,227 unique users | 1,000 unique items
             timestamps 0.0 .. 2,678,373.0 (float seconds from the start,
             i.e. exactly 31.00 days)

GRAPH REPRESENTATION (and why)
    node        a Wikipedia PAGE (item_id)
    edge        two pages co-edited by the same user inside the window
    timestamp   the event timestamp, seconds from the dataset start
    snapshot    one 2-day window -> 16 snapshots over the 31 days
    direction   undirected
    weights     none (unweighted; repeated co-edits do not add edges)

    Why project onto PAGES rather than users? Both were measured. The
    user-user projection (two users who edited the same page) is extremely
    sparse: ~70 active users and only ~34 edges per day, density 0.007,
    because Wikipedia editors rarely touch the same page on the same day.
    The page-page projection is denser and gives a usable structure, and
    it still carries a natural community meaning: pages edited by the same
    people form thematic clusters. With 2-day windows the measured
    aggregate partition is a balanced 38 / 62 split, and bridge width
    varies from 9 to 87 across snapshots - a real signal to explain.

    Why 2-day windows? A measured trade-off. Daily windows give 31
    snapshots but density 0.010; 4-day windows give density ~0.03 but only
    8 snapshots, too few for a trajectory. 2 days keeps 16 snapshots at
    density ~0.029.

FILTERING (nothing silent)
    Only the topN most active pages are kept, because a one-mode
    projection turns every user into a clique over the pages they edited,
    so cost grows quadratically. Raw AND retained counts for both pages and
    events are recorded in the run's preprocessing_summary.json, so the
    filtered graph can never be mistaken for the whole dataset.

ANALYSIS MODES (base.py DECISION 4)
    "temporal_evaluation" (default): the top pages are ranked using only
    the first 20% of the 31-day span, and TGAP sees only the remaining
    span, so no future edit activity can decide which pages appear in an
    earlier snapshot. The partition is detected on the selection period
    alone and frozen.
    "descriptive": the original full-period behaviour, labelled as not
    leakage-safe.
'''

import io
import os
import zipfile
from collections import Counter

from .base import (PreparedDataset, TEMPORAL_EVALUATION, SELECTION_FRACTION,
                   aggregateGraph, checkMode, projectCoActivity,
                   retentionSummary, selectionWindowSummary, temporalSplit,
                   _partitionFromGraph)
from ..download import download, fileDigest

EDGELIST_MEMBER = "tgbl-wiki_edgelist_v2.csv"
SECONDS_PER_DAY = 86400.0


def readEvents(path):
    ''' Stream the edge list, keeping only (user, item, timestamp).

    We deliberately do not use pandas here: the file has 176 columns of
    which we need 3, and a full parse would allocate hundreds of MB of
    edit features we never look at. Manual comma scanning keeps this at a
    few seconds and a few MB.
    '''
    events = []
    with zipfile.ZipFile(path) as archive:
        with archive.open(EDGELIST_MEMBER) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8")
            header = text.readline()            # consumed, not parsed
            assert header.startswith("user_id,item_id,timestamp"), \
                f"unexpected tgbl-wiki header: {header[:80]!r}"
            for line in text:
                first = line.find(",")
                second = line.find(",", first + 1)
                third = line.find(",", second + 1)
                events.append({
                    "user": line[:first],
                    "item": line[first + 1:second],
                    "time": float(line[second + 1:third]),
                })
    return events


def prepare(topItems=100, windowDays=2, mode=TEMPORAL_EVALUATION,
            selectionFraction=SELECTION_FRACTION):
    ''' Download (if needed), preprocess, and return a PreparedDataset.

    mode == "temporal_evaluation" (default, leakage-safe): the page ranking
    and the community partition are computed from the first
    `selectionFraction` of the time span only, and the snapshots TGAP
    explains come from the remaining span.
    mode == "descriptive": full-period ranking and snapshots, as
    originally implemented. Not leakage-safe; labelled everywhere.
    '''
    checkMode(mode)
    path = download("tgbl_wiki")
    events = readEvents(path)

    times = [e["time"] for e in events]
    tMin, cut, tMax = temporalSplit(times, selectionFraction)
    if mode == TEMPORAL_EVALUATION:
        selectionEvents = [e for e in events if e["time"] <= cut]
        evaluationEvents = [e for e in events if e["time"] > cut]
        evaluationStart = cut
    else:
        selectionEvents = events
        evaluationEvents = events
        evaluationStart = tMin

    # Page ranking sees ONLY the selection period in temporal mode.
    selectionActivity = Counter(e["item"] for e in selectionEvents)
    ranked = sorted(selectionActivity.items(), key=lambda kv: (-kv[1], kv[0]))
    keptItems = {item for item, _ in ranked[:topItems]}

    window = SECONDS_PER_DAY * windowDays

    def windowed(stream, start):
        ''' Attach a window id measured from `start`, keeping only events on
        the retained pages. Returns a new list; the caller's dicts are not
        mutated, so the two periods cannot contaminate each other. '''
        return [dict(event, window=int((event["time"] - start) // window))
                for event in stream if event["item"] in keptItems]

    evaluationKept = windowed(evaluationEvents, evaluationStart)
    snapshots, windowIds = projectCoActivity(
        evaluationKept, actorKey="item", itemKey="user", windowKey="window",
        keepActors=keptItems)

    if mode == TEMPORAL_EVALUATION:
        trainingKept = windowed(selectionEvents, tMin)
        trainingSnapshots, _ = projectCoActivity(
            trainingKept, actorKey="item", itemKey="user", windowKey="window",
            keepActors=keptItems)
        communities, partitionGraph, partitionReport = _partitionFromGraph(
            aggregateGraph(trainingSnapshots, keptItems), "temporal_train")
        partitionSource = ("greedy modularity on the selection-period "
                           "co-edit graph only, then frozen")
    else:
        communities, partitionGraph, partitionReport = _partitionFromGraph(
            aggregateGraph(snapshots, keptItems), "full_period_descriptive")
        partitionSource = ("greedy modularity on the full-period aggregate "
                           "graph (descriptive; not leakage-safe)")

    dayOffset = (evaluationStart - tMin) / SECONDS_PER_DAY
    labels = [f"d{int(dayOffset + w * windowDays)}-"
              f"d{int(dayOffset + (w + 1) * windowDays)}" for w in windowIds]

    rawItems = Counter(e["item"] for e in events)
    activeInEvaluation = len(
        {n for g in snapshots for n, d in g.degree() if d > 0})
    retention = retentionSummary(len(rawItems), len(keptItems), len(events),
                                 len(evaluationKept))
    selectionEnd = (f"{(cut - tMin) / SECONDS_PER_DAY:.1f}d"
                    if mode == TEMPORAL_EVALUATION else "0.0d")
    windowReport = selectionWindowSummary(
        mode, "top_active", selectionFraction,
        eventsTotal=len(events),
        eventsSelection=len(selectionEvents),
        eventsEvaluation=len(evaluationEvents),
        selectionStart="0.0d",
        selectionEnd=selectionEnd,
        evaluationEnd=f"{(tMax - tMin) / SECONDS_PER_DAY:.1f}d",
        timeUnit="days from the first event in the raw file")

    meta = {
        "dataset": "tgbl-wiki",
        "analysis_mode": mode,
        "description": "Wikipedia edit stream (TGB). 157,474 edits by 8,227 "
                       "users on 1,000 pages over 31 days. Bipartite, so it "
                       "is projected onto pages: two pages are linked when "
                       "the same user edited both inside the window.",
        "source": "Temporal Graph Benchmark (TGB); archive URL from "
                  "tgb/utils/info.py DATA_URL_DICT",
        "raw_file": os.path.basename(path),
        "raw_bytes": os.path.getsize(path),
        "raw_sha256_first_1mb": fileDigest(path),
        # raw_nodes counts PAGES, the side we project onto; the users are
        # reported separately because they are not graph nodes here.
        **retention,
        "raw_unique_users": len(set(e["user"] for e in events)),
        "raw_unique_items": len(rawItems),
        "raw_time_min_seconds": min(times),
        "raw_time_max_seconds": max(times),
        "raw_span_days": (tMax - tMin) / SECONDS_PER_DAY,
        "evaluated_span_days": (tMax - evaluationStart) / SECONDS_PER_DAY,
        "retained_nodes_active_in_evaluation": activeInEvaluation,
        "graph_family": "bipartite (one-mode projection onto pages)",
        "graph_nodes_are": "Wikipedia pages (item_id)",
        "graph_edges_are": "two pages co-edited by the same user in the window",
        "snapshot_interval": f"{windowDays} days",
        "snapshot_count": len(snapshots),
        "directed": False,
        "weighted": False,
        "edge_weight_used": False,
        "edge_sign_used": False,
        "edge_attributes_available": "172 numeric edit features per event, "
                                     "plus a state_label; none is an edge "
                                     "weight between two pages",
        "edge_attributes_note": (
            "The real-data experiments use only temporal interaction "
            "topology. Dataset-specific edge weights and signs are not used "
            "by the existing TGAP transformations or metrics."),
    }
    preprocessing = {
        "analysis_mode": mode,
        "projection": "one-mode, onto pages (see module docstring for why "
                      "the user-user projection was rejected as too sparse)",
        "node_selection": f"top {topItems} pages by edit count, ranked over "
                          f"{len(selectionEvents)} selection-period events",
        "top_items_kept": topItems,
        **retention,
        **windowReport,
        "retained_nodes_active_in_evaluation": activeInEvaluation,
        "unique_window_edges": sum(g.number_of_edges() for g in snapshots),
        "events_dropped_selection_period": (
            len(events) - len(evaluationEvents)),
        "events_dropped_node_filter": (len(evaluationEvents)
                                       - len(evaluationKept)),
        "window_days": windowDays,
        "fixed_node_set": True,
        "isolated_nodes_included": True,
        "edge_weight_used": False,
        "edge_sign_used": False,
        "partition_source": partitionSource,
        **partitionReport,
        "cohesion_usable": False,
        "cohesion_note": "snapshots contain isolated inactive pages, so they "
                         "are disconnected and algebraic connectivity is 0; "
                         "cohesion is not used as a prediction target",
    }
    return PreparedDataset("tgbl_wiki", snapshots, communities, labels,
                           meta, preprocessing)
