'''
Generic adapter for UNIPARTITE temporal edge lists.

Why this file exists as one adapter rather than six. Every dataset here
arrives in the same shape - a stream of (source, target, timestamp) rows
where source and target live in the SAME id space - so they need the same
preprocessing and differ only in file format and parameters. Each dataset
is therefore a configuration entry in DATASETS below, documented in place,
and the code path is shared and tested once.

THE IMPORTANT DIFFERENCE FROM THE BIPARTITE ADAPTERS. tgbl-wiki and
Decentraland are bipartite (user->page, voter->proposal), so they need a
one-mode projection, which both costs data (56-72% of events dropped) and
invents the edges rather than observing them. The datasets in this file are
ALREADY actor-to-actor: person A emails person B. So:

  * NO projection is needed - edges are observed, not derived.
  * Far less data is discarded (only the topN node filter applies).
  * "Bridge width" counts real observed ties between two communities.

That makes these datasets a cleaner test of TGAP than the bipartite pair,
and the two families are worth comparing precisely because they differ.

Measured facts for every dataset (read from the files, not assumed) are in
DATASETS and are re-derived at run time into metadata.json.

GROUND-TRUTH COMMUNITIES. email-Eu-core is special and valuable: SNAP ships
department labels for all 1,005 people, so the two-community partition can
come from the real organisational structure instead of a detection
algorithm. We restrict to the two largest departments (department 4 with
109 people and department 14 with 92) and the partition IS those
departments. Bridge width then literally counts emails between two real
departments. Every other dataset in the project uses a detected partition,
so this one is the control case.

SHARED PREPROCESSING DECISIONS (same spirit as adapters/base.py)
 1. Direction is dropped: TGAP's metrics and transformations are
    undirected, so A->B and B->A become the same edge. Recorded as
    directed=False; the raw direction is still in the source file.
 2. Self-loops are dropped. They inflate degree without expressing a tie
    between two actors, and Freeman centralization counts degree.
 3. Repeated interactions inside a window collapse to ONE edge, and no
    weight is stored, because no current metric reads edge weights. For
    the bitcoin datasets this means the trust RATING is deliberately
    unused - see the per-dataset notes.
 4. Fixed node set: the selected nodes appear in every snapshot, isolated
    when inactive, because TGAP's anchor rule assumes a constant node set.
    Consequence: snapshots are usually disconnected, so cohesion
    (algebraic connectivity) is 0 and is not used as a prediction target.
 5. Node selection either keeps the topN most active nodes (tractability
    and focus) or uses a ground-truth label subset. Both raw and retained
    counts are always reported, for nodes and for events.
 6. WHICH events may inform that selection depends on the analysis mode
    (base.py DECISION 4). In the default "temporal_evaluation" mode the
    activity ranking sees only the first 20% of the time span and TGAP sees
    only the remaining 80%, so no future information can decide who appears
    in an earlier snapshot. "descriptive" mode reproduces the original
    full-period behaviour and is labelled as not leakage-safe.
'''

import gzip
import io
import itertools
import os
import zipfile
from collections import Counter
from datetime import datetime, timezone

import networkx as nx

from .base import (PreparedDataset, TEMPORAL_EVALUATION, SELECTION_FRACTION,
                   aggregateGraph, checkMode, fixedPartitionWithReport,
                   retentionSummary, selectionWindowSummary, temporalSplit,
                   _partitionFromGraph)
from ..download import download, fileDigest

SECONDS_PER_DAY = 86400.0


# Each entry documents what the file really contains and why the window was
# chosen. windowDays is picked so that every dataset yields roughly 15-25
# snapshots: enough for a trajectory (BridgeTrend needs one) without making
# individual snapshots too sparse to perturb.
DATASETS = {
    "email_eu_core": {
        "source_key": "email_eu_core",
        "labels_key": "email_eu_core_labels",
        "format": "gzip_text",
        "separator": None,          # whitespace
        "columns": (0, 1, 2),       # SRC DST TIME
        "epoch": False,             # seconds from the start of the study
        "windowDays": 40,           # 803.9 days -> ~21 snapshots
        "nodeSelection": "labels",
        "labelGroups": 2,           # the two largest departments
        "description": "European research institution email network (SNAP). "
                       "332,334 emails between 1,005 members over 803.9 "
                       "days. Ships ground-truth department labels.",
        "url_note": "snap.stanford.edu/data/email-Eu-core-temporal.html",
        "nodes_are": "institution members (anonymised ids)",
        "edges_are": "an email sent between two members in the window",
        "unused_fields": "message direction (graph is undirected)",
        "edge_attributes_available": "none beyond direction; the file is "
                                    "SRC DST TIME only",
    },
    "tgbl_enron": {
        "source_key": "tgbl_enron",
        "format": "zip_csv",
        "member": "tgbl-enron_edgelist.csv",
        "separator": ",",
        "columns": (0, 1, 2),       # header: u,i,ts,label,idx
        "hasHeader": True,
        "epoch": False,
        "windowDays": 60,           # 1316.4 days -> ~22 snapshots
        "nodeSelection": "top_active",
        "topN": 120,
        "description": "Enron corporate email network (TGB). 125,235 emails "
                       "among ~184 employees over 1316.4 days. Note the "
                       "header is u,i,ts,label,idx - NOT the tgbl-wiki "
                       "schema, which is why each adapter validates its own.",
        "url_note": "TGB DATA_URL_DICT entry tgbl-enron",
        "nodes_are": "Enron employees (anonymised ids)",
        "edges_are": "an email between two employees in the window",
        "unused_fields": "label, idx",
        "edge_attributes_available": "label (TGB link-prediction target) "
                                    "and idx; neither is an edge weight",
    },
    "tgbl_uci": {
        "source_key": "tgbl_uci",
        "format": "zip_csv",
        "member": "tgbl-uci_edgelist.csv",
        "separator": ",",
        "columns": (0, 1, 2),
        "hasHeader": True,
        "epoch": False,
        "windowDays": 10,           # 193.7 days -> ~20 snapshots
        "nodeSelection": "top_active",
        "topN": 120,
        "description": "UCI online-community private messages (TGB). 59,835 "
                       "messages among 1,899 students over 193.7 days. "
                       "VERIFIED IDENTICAL to SNAP's CollegeMsg dataset "
                       "(same event count, node count and timestamp "
                       "offsets), so CollegeMsg is deliberately NOT included "
                       "as a separate dataset.",
        "url_note": "TGB DATA_URL_DICT entry tgbl-uci",
        "nodes_are": "students in an online community",
        "edges_are": "a private message between two students in the window",
        "unused_fields": "label, idx",
        "edge_attributes_available": "label and idx; neither is an edge "
                                    "weight",
    },
    "sx_mathoverflow": {
        "source_key": "sx_mathoverflow",
        "format": "gzip_text",
        "separator": None,
        "columns": (0, 1, 2),
        "epoch": True,              # unix seconds
        "windowDays": 120,          # 2350.3 days -> ~20 snapshots
        "nodeSelection": "top_active",
        "topN": 120,
        "description": "MathOverflow question-answer-comment interactions "
                       "(SNAP). 506,550 interactions among 24,818 users over "
                       "2350.3 days - the longest span in the project.",
        "url_note": "snap.stanford.edu/data/sx-mathoverflow.html",
        "nodes_are": "MathOverflow users",
        "edges_are": "an answer/comment interaction between two users",
        "unused_fields": "interaction type (a2q / c2q / c2a are merged)",
        "edge_attributes_available": "interaction type is encoded by WHICH "
                                    "of the three files a row came from; "
                                    "the three are merged here",
    },
    "bitcoin_otc": {
        "source_key": "bitcoin_otc",
        "format": "gzip_text",
        "separator": ",",
        "columns": (0, 1, 3),       # SOURCE,TARGET,RATING,TIME - time is 3
        "epoch": True,
        "windowDays": 90,           # 1903.3 days -> ~22 snapshots
        "nodeSelection": "top_active",
        "topN": 120,
        "description": "Bitcoin OTC web-of-trust (SNAP). 35,592 trust "
                       "ratings among 5,881 traders over 1903.3 days. NOTE "
                       "the timestamp is the FOURTH column; reading column 3 "
                       "as time (as in the other files) silently yields a "
                       "span of 0 days.",
        "url_note": "snap.stanford.edu/data/soc-sign-bitcoin-otc.html",
        "nodes_are": "Bitcoin OTC traders",
        "edges_are": "a trust rating given between two traders",
        "unused_fields": "RATING (-10..+10). No current TGAP metric reads "
                         "edge weights or signs, so it is recorded as "
                         "unused rather than silently averaged away.",
        "edge_attributes_available": "RATING, integer -10..+10 in column 2, "
                                    "carrying BOTH a sign (distrust vs "
                                    "trust) and a magnitude (how strongly). "
                                    "Available in the raw file, unused by "
                                    "TGAP - see the edge_weight_used / "
                                    "edge_sign_used metadata fields.",
    },
    "bitcoin_alpha": {
        "source_key": "bitcoin_alpha",
        "format": "gzip_text",
        "separator": ",",
        "columns": (0, 1, 3),
        "epoch": True,
        "windowDays": 90,           # 1901.0 days -> ~22 snapshots
        "nodeSelection": "top_active",
        "topN": 120,
        "description": "Bitcoin Alpha web-of-trust (SNAP). 24,186 trust "
                       "ratings among 3,783 traders over 1901.0 days. Same "
                       "structure as bitcoin-otc on a different platform, so "
                       "the pair tests whether results transfer between two "
                       "similar ecosystems.",
        "url_note": "snap.stanford.edu/data/soc-sign-bitcoin-alpha.html",
        "nodes_are": "Bitcoin Alpha traders",
        "edges_are": "a trust rating given between two traders",
        "unused_fields": "RATING (-10..+10), as for bitcoin-otc",
        "edge_attributes_available": "RATING, integer -10..+10 in column 2, "
                                    "sign and magnitude, as for "
                                    "bitcoin-otc. Unused by TGAP.",
    },
}


def readEdgeList(config):
    ''' Read (source, target, timestamp) triples from whichever format the
    dataset uses. Column positions come from the config because they really
    do differ between files - the bitcoin files put time in column 3 while
    the SNAP text files put it in column 2. '''
    path = download(config["source_key"])
    sourceCol, targetCol, timeCol = config["columns"]
    separator = config["separator"]
    events = []

    def parse(lines):
        if config.get("hasHeader"):
            next(lines)
        for line in lines:
            parts = line.split(separator) if separator else line.split()
            if len(parts) <= max(config["columns"]):
                continue                      # skip malformed/blank lines
            events.append((parts[sourceCol].strip(),
                           parts[targetCol].strip(),
                           float(parts[timeCol])))

    if config["format"] == "gzip_text":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            parse(handle)
    elif config["format"] == "zip_csv":
        with zipfile.ZipFile(path) as archive:
            with archive.open(config["member"]) as raw:
                parse(io.TextIOWrapper(raw, encoding="utf-8"))
    else:
        raise ValueError(f"unknown format {config['format']}")
    return events, path


def readLabels(config):
    ''' Ground-truth node labels, when the dataset ships them. Format is
    "node label" per line. '''
    path = download(config["labels_key"])
    labels = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) >= 2:
                labels[parts[0].strip()] = parts[1].strip()
    return labels


def selectNodes(config, events):
    ''' Choose the fixed node set, and say how it was chosen.

    "labels"     : keep the members of the N largest ground-truth groups,
                   and use those groups AS the partition. No detection.
                   The labels are a STATIC attribute of the people, not
                   something computed from the event stream, so this route
                   carries no temporal leakage in either analysis mode.
    "top_active" : keep the topN nodes by number of incident events, counted
                   over WHATEVER events the caller passes in. In
                   temporal_evaluation mode the caller passes only the
                   selection-period events, which is what makes the
                   selection leakage-safe; in descriptive mode it passes
                   everything.

    Returns (keep, groundTruthPartition or None, note, selectionMode).
    '''
    if config["nodeSelection"] == "labels":
        labels = readLabels(config)
        sizes = Counter(labels.values())
        groups = [g for g, _ in sizes.most_common(config["labelGroups"])]
        keep = {n for n, g in labels.items() if g in groups}
        partition = tuple(
            {n for n in keep if labels[n] == g} for g in groups)
        note = (f"ground-truth labels; kept the {config['labelGroups']} "
                f"largest groups {groups} with sizes "
                f"{[len(p) for p in partition]}")
        return keep, partition, note, "ground_truth_labels"

    activity = Counter()
    for source, target, _ in events:
        activity[source] += 1
        activity[target] += 1
    # most_common breaks ties by insertion order, which depends on file
    # order; sort by (-count, node) so the kept set is reproducible.
    ranked = sorted(activity.items(), key=lambda kv: (-kv[1], kv[0]))
    keep = {node for node, _ in ranked[:config["topN"]]}
    note = (f"top {config['topN']} nodes by incident events, counted over "
            f"{len(events)} events; {len(activity)} nodes were candidates")
    return keep, None, note, "top_active"


def buildSnapshots(events, keep, windowDays, start=None):
    ''' Aggregate observed edges into fixed-length windows.

    No projection: these edges are observed directly. Self-loops are
    dropped, direction is dropped, and repeated interactions inside a
    window collapse to one edge.

    `start` fixes the left edge of window 0. The caller passes the start of
    the EVALUATION period in temporal_evaluation mode, so snapshot
    boundaries do not depend on data from the selection period.
    '''
    times = [t for _, _, t in events]
    start = min(times) if start is None else start
    window = SECONDS_PER_DAY * windowDays
    keepSorted = sorted(keep)

    byWindow = {}
    dropped = {"self_loops": 0, "node_filtered": 0}
    for source, target, timestamp in events:
        if source not in keep or target not in keep:
            dropped["node_filtered"] += 1
            continue
        if source == target:
            dropped["self_loops"] += 1
            continue
        index = int((timestamp - start) // window)
        byWindow.setdefault(index, set()).add(
            (source, target) if source <= target else (target, source))

    windowIds = sorted(byWindow)
    snapshots = []
    for index in windowIds:
        graph = nx.Graph()
        graph.add_nodes_from(keepSorted)     # fixed node set
        graph.add_edges_from(sorted(byWindow[index]))
        snapshots.append(graph)
    return snapshots, windowIds, dropped, start


def makeLabels(config, windowIds, start, dayOffset=0.0):
    ''' A readable label per snapshot: a UTC date when the timestamps are
    unix epoch, otherwise a day offset from the start of the STUDY (not
    from the start of the evaluation period), so labels stay comparable
    between the two analysis modes. '''
    windowDays = config["windowDays"]
    labels = []
    for index in windowIds:
        offset = index * windowDays
        if config["epoch"]:
            moment = datetime.fromtimestamp(
                start + offset * SECONDS_PER_DAY, tz=timezone.utc)
            labels.append(moment.strftime("%Y-%m-%d"))
        else:
            absolute = dayOffset + offset
            labels.append(f"d{int(absolute)}-{int(absolute + windowDays)}")
    return labels


def prepare(name, mode=TEMPORAL_EVALUATION,
            selectionFraction=SELECTION_FRACTION):
    ''' Download (if needed), preprocess, and return a PreparedDataset.

    mode == "temporal_evaluation" (default, leakage-safe)
        The first `selectionFraction` of the observed time span is the
        SELECTION period. Node selection and community detection see only
        it; the snapshots TGAP explains are built only from the remaining
        span. The two periods are disjoint, so no future information can
        enter the selection step.

    mode == "descriptive"
        Full-period selection and full-period snapshots - the original
        behaviour. Not leakage-safe; every output file records the mode.
    '''
    checkMode(mode)
    config = DATASETS[name]
    events, path = readEdgeList(config)

    times = [t for _, _, t in events]
    tMin, cut, tMax = temporalSplit(times, selectionFraction)
    if mode == TEMPORAL_EVALUATION:
        selectionEvents = [e for e in events if e[2] <= cut]
        evaluationEvents = [e for e in events if e[2] > cut]
        evaluationStart = cut
    else:
        # Descriptive: one undivided period plays both roles.
        selectionEvents = events
        evaluationEvents = events
        evaluationStart = tMin

    keep, groundTruthPartition, selectionNote, selectionMode = selectNodes(
        config, selectionEvents)
    snapshots, windowIds, dropped, start = buildSnapshots(
        evaluationEvents, keep, config["windowDays"], start=evaluationStart)

    # Community detection on the SAME period that chose the nodes.
    if groundTruthPartition is not None:
        communities = groundTruthPartition
        # No detection happens here, so there is no "partition graph" in the
        # same sense as the detected case. We report the EVALUATION aggregate
        # instead, which makes nodes_isolated_in_partition_graph mean
        # "retained people who sent or received nothing in the evaluation
        # period" - a different, still useful number, and the field is
        # populated rather than left absent.
        partitionGraph = aggregateGraph(snapshots, keep)
        isolated = sum(1 for _, d in partitionGraph.degree() if d == 0)
        partitionReport = {
            "community_mode": "ground_truth_labels",
            "partition_sizes": [len(communities[0]), len(communities[1])],
            "partition_graph_edges": partitionGraph.number_of_edges(),
            "partition_graph_nodes": partitionGraph.number_of_nodes(),
            "nodes_isolated_in_partition_graph": isolated,
            "smaller_side_pct": round(
                100.0 * min(len(communities[0]), len(communities[1]))
                / len(keep), 2),
        }
        partitionSource = ("ground-truth labels (no detection, no temporal "
                           "leakage: labels are a static attribute)")
    elif mode == TEMPORAL_EVALUATION:
        trainingSnapshots, _, _, _ = buildSnapshots(
            selectionEvents, keep, config["windowDays"], start=tMin)
        communities, partitionGraph, partitionReport = _partitionFromGraph(
            aggregateGraph(trainingSnapshots, keep), "temporal_train")
        partitionSource = ("greedy modularity on the selection-period graph "
                           "only, then frozen for every later snapshot")
    else:
        communities, partitionGraph, partitionReport = \
            fixedPartitionWithReport(snapshots, mode, nodes=keep)
        partitionSource = ("greedy modularity on the full-period aggregate "
                           "graph (descriptive; not leakage-safe)")

    dayOffset = (evaluationStart - tMin) / SECONDS_PER_DAY
    labels = makeLabels(config, windowIds, start, dayOffset)

    rawNodes = {n for e in events for n in e[:2]}
    retainedEvents = (len(evaluationEvents) - dropped["node_filtered"]
                      - dropped["self_loops"])
    uniqueWindowEdges = sum(g.number_of_edges() for g in snapshots)
    activeInEvaluation = len(
        {n for g in snapshots for n, d in g.degree() if d > 0})

    retention = retentionSummary(len(rawNodes), len(keep), len(events),
                                 retainedEvents)
    selectionEnd = (f"{(cut - tMin) / SECONDS_PER_DAY:.1f}d"
                    if mode == TEMPORAL_EVALUATION else "0.0d")
    window = selectionWindowSummary(
        mode, selectionMode, selectionFraction,
        eventsTotal=len(events),
        eventsSelection=len(selectionEvents),
        eventsEvaluation=len(evaluationEvents),
        selectionStart="0.0d",
        selectionEnd=selectionEnd,
        evaluationEnd=f"{(tMax - tMin) / SECONDS_PER_DAY:.1f}d",
        timeUnit="days from the first event in the raw file")

    meta = {
        "dataset": name.replace("_", "-"),
        "analysis_mode": mode,
        "source": config["url_note"],
        "description": config["description"],
        "raw_file": os.path.basename(path),
        "raw_bytes": os.path.getsize(path),
        "raw_sha256_first_1mb": fileDigest(path),
        # RAW vs RETAINED, never conflated. raw_* describe the source file;
        # retained_* describe the graphs TGAP actually explains.
        **retention,
        "raw_span_days": (tMax - tMin) / SECONDS_PER_DAY,
        "evaluated_span_days": (tMax - evaluationStart) / SECONDS_PER_DAY,
        "retained_nodes_active_in_evaluation": activeInEvaluation,
        "graph_family": "unipartite (observed actor-actor edges, "
                        "no projection)",
        "graph_nodes_are": config["nodes_are"],
        "graph_edges_are": config["edges_are"],
        "snapshot_interval": f"{config['windowDays']} days",
        "snapshot_count": len(snapshots),
        "directed": False,
        "weighted": False,
        # Item 7 transparency: what the dataset offers and what TGAP uses.
        "edge_weight_used": False,
        "edge_sign_used": False,
        "edge_attributes_available": config.get("edge_attributes_available",
                                                "none"),
        "edge_attributes_note": (
            "The real-data experiments use only temporal interaction "
            "topology. Dataset-specific edge weights and signs are not used "
            "by the existing TGAP transformations or metrics, so they are "
            "recorded as available-but-unused rather than averaged away."),
    }
    preprocessing = {
        "analysis_mode": mode,
        "projection": "none - edges are observed directly between actors",
        "node_selection": selectionNote,
        **retention,
        **window,
        "retained_nodes_active_in_evaluation": activeInEvaluation,
        # unique_window_edges is the deduplicated count that actually
        # appears in the graphs; retained_events counts raw events that
        # survived every filter, so the two differ by repeat interactions.
        "unique_window_edges": uniqueWindowEdges,
        "events_dropped_selection_period": (
            len(events) - len(evaluationEvents)),
        "events_dropped_node_filter": dropped["node_filtered"],
        "events_dropped_self_loops": dropped["self_loops"],
        "direction_dropped": True,
        "self_loops_dropped": True,
        "repeated_interactions": "collapsed to one edge per window",
        "unused_fields": config["unused_fields"],
        "edge_weight_used": False,
        "edge_sign_used": False,
        "edge_attributes_available": config.get("edge_attributes_available",
                                                "none"),
        "window_days": config["windowDays"],
        "fixed_node_set": True,
        "isolated_nodes_included": True,
        "partition_source": partitionSource,
        **partitionReport,
        "cohesion_usable": False,
        "cohesion_note": "inactive nodes appear isolated, so snapshots are "
                         "disconnected and algebraic connectivity is 0; "
                         "cohesion is not used as a prediction target",
    }
    return PreparedDataset(name, snapshots, communities, labels, meta,
                           preprocessing)
