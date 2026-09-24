'''
Adapter for the Decentraland DAO governance dataset.

WHAT THE RAW FILES ACTUALLY CONTAIN (verified by reading them):
    data/raw/votes.csv      13.6 MB, 53,533 rows - one row per vote cast
      columns: Member, Snapshot ID, Created, Proposal Title, Choice #,
               Choice, Vote Weight, Total VP, MANA VP, Names VP, LAND VP,
               Delegated VP, L1 Wearables VP, Rental VP
    data/raw/proposals.csv  0.6 MB, 1,689 rows - one row per proposal
      columns: Proposal ID, Snapshot ID, Author, Type, Title, Started,
               Ended, Threshold, Status, Forum Topic, Total VP, MANA VP,
               LAND VP, NAMES VP, DELEGATED VP, Votes
    measured 4,133 unique voters | 1,816 distinct proposals appear in votes
             (more than the 1,689 rows of proposals.csv, so some voted-on
             proposals have no proposal record - we do not need it here)
             time range 2021-05-24 -> 2023-04-30 (705 days)
             no missing values in Member / Snapshot ID / Created
    Choice # distribution: 1 (yes) 37,251 | 2 (no) 13,332 | 3+ 2,898

    The files are a FROZEN snapshot of the Decentraland DAO Transparency
    export taken 30 April 2023, shipped with the replication package of
    "Vote Delegation and Conformity in DAO Governance" (Ahmed). The live
    export keeps growing, so only the frozen copy is reproducible.

GRAPH REPRESENTATION (and why)
    node        a voter wallet address (Member)
    edge        two voters who voted on the SAME proposal in the window
                ("co-voting")
    timestamp   Created (ISO 8601, UTC)
    snapshot    one calendar month -> 24 snapshots over the 705 days
    direction   undirected
    weights     none

    Why co-voting and not the bipartite voter-proposal graph? In the
    bipartite version every edge crosses between the two sides, so with
    communities = (voters, proposals) the bridge width would simply equal
    the edge count and duplicate density - the concept would carry no
    information. The co-voting projection instead makes bridge width mean
    "how many ties connect two voting blocs", which is exactly the
    CATALYST wide-bridge question.

    Why monthly? DAO governance runs on proposal cycles of days to weeks;
    monthly windows give 24 snapshots with a measured median density of
    0.25 - dense enough for every transformation to operate, and long
    enough for a trajectory.

    Vote choice, voting power and delegated VP are NOT used. The current
    TGAP metrics and transformations read no edge weights or node
    attributes, so adding them would be decoration, not signal. They
    remain available in the raw file for later work.

FILTERING (nothing silent)
    Only the topN most active voters are kept, for the same quadratic
    projection cost reason as the other adapter. Raw AND retained counts for
    both voters and votes are recorded in preprocessing_summary.json.

ANALYSIS MODES (base.py DECISION 4)
    "temporal_evaluation" (default): the voter ranking and the community
    partition use only the first 20% of the 705-day span, and TGAP sees
    only the remaining months, so no future voting behaviour can decide who
    appears in an earlier snapshot.
    "descriptive": the original full-period behaviour, labelled as not
    leakage-safe.
'''

import os

import pandas as pd

from .base import (PreparedDataset, TEMPORAL_EVALUATION, SELECTION_FRACTION,
                   aggregateGraph, checkMode, projectCoActivity,
                   retentionSummary, selectionWindowSummary,
                   _partitionFromGraph)
from ..download import download, fileDigest


def readVotes():
    ''' Load votes.csv with the timestamp parsed. Column names are taken
    from the real header, and we assert them so a future upstream schema
    change fails loudly instead of producing a wrong graph. '''
    path = download("decentraland_votes")
    frame = pd.read_csv(path)
    required = {"Member", "Snapshot ID", "Created"}
    missing = required - set(frame.columns)
    assert not missing, f"decentraland votes.csv missing columns: {missing}"
    frame["timestamp"] = pd.to_datetime(frame["Created"], format="ISO8601",
                                        utc=True)
    return frame, path


def prepare(topVoters=100, windowFreq="MS", mode=TEMPORAL_EVALUATION,
            selectionFraction=SELECTION_FRACTION):
    ''' Download (if needed), preprocess, and return a PreparedDataset.
    windowFreq is a pandas offset alias; "MS" = calendar month start.

    mode == "temporal_evaluation" (default, leakage-safe): the voter ranking
    and the community partition use only the first `selectionFraction` of
    the 705-day span, and the snapshots TGAP explains come from the rest.
    mode == "descriptive": the original full-period behaviour, labelled as
    not leakage-safe.
    '''
    checkMode(mode)
    frame, path = readVotes()

    stamps = frame["timestamp"]
    tMin, tMax = stamps.min(), stamps.max()
    if mode == TEMPORAL_EVALUATION:
        cut = tMin + (tMax - tMin) * selectionFraction
        selection = frame[frame["timestamp"] <= cut]
        evaluation = frame[frame["timestamp"] > cut]
    else:
        cut = tMin
        selection = frame
        evaluation = frame

    # Voter ranking sees ONLY the selection period in temporal mode.
    activity = selection["Member"].value_counts()
    ranked = sorted(activity.items(), key=lambda kv: (-kv[1], kv[0]))
    keptVoters = {member for member, _ in ranked[:topVoters]}

    def windowise(subset):
        ''' Attach a calendar-month window id, in time order, to the rows of
        `subset` that belong to a retained voter. '''
        kept = subset[subset["Member"].isin(keptVoters)].copy()
        # tz is dropped explicitly before to_period(): the timestamps are
        # already UTC, and converting a tz-aware series otherwise warns.
        periods = kept["timestamp"].dt.tz_convert(None).dt.to_period(
            "M" if windowFreq == "MS" else windowFreq)
        ordered = sorted(periods.unique())
        index = {period: i for i, period in enumerate(ordered)}
        kept["window"] = [index[p] for p in periods]
        return kept, ordered

    keptEvaluation, evaluationPeriods = windowise(evaluation)
    snapshots, windowIds = projectCoActivity(
        keptEvaluation[["Member", "Snapshot ID", "window"]].to_dict("records"),
        actorKey="Member", itemKey="Snapshot ID", windowKey="window",
        keepActors=keptVoters)

    if mode == TEMPORAL_EVALUATION:
        keptSelection, _ = windowise(selection)
        trainingSnapshots, _ = projectCoActivity(
            keptSelection[["Member", "Snapshot ID", "window"]].to_dict(
                "records"),
            actorKey="Member", itemKey="Snapshot ID", windowKey="window",
            keepActors=keptVoters)
        communities, partitionGraph, partitionReport = _partitionFromGraph(
            aggregateGraph(trainingSnapshots, keptVoters), "temporal_train")
        partitionSource = ("greedy modularity on the selection-period "
                           "co-voting graph only, then frozen")
    else:
        communities, partitionGraph, partitionReport = _partitionFromGraph(
            aggregateGraph(snapshots, keptVoters), "full_period_descriptive")
        partitionSource = ("greedy modularity on the full-period aggregate "
                           "graph (descriptive; not leakage-safe)")

    labels = [str(evaluationPeriods[w]) for w in windowIds]
    activeInEvaluation = len(
        {n for g in snapshots for n, d in g.degree() if d > 0})
    retention = retentionSummary(int(frame["Member"].nunique()),
                                 len(keptVoters), int(len(frame)),
                                 int(len(keptEvaluation)))
    windowReport = selectionWindowSummary(
        mode, "top_active", selectionFraction,
        eventsTotal=int(len(frame)),
        eventsSelection=int(len(selection)),
        eventsEvaluation=int(len(evaluation)),
        selectionStart=str(tMin.date()),
        selectionEnd=str(cut.date()),
        evaluationEnd=str(tMax.date()),
        timeUnit="calendar date (UTC)")

    meta = {
        "dataset": "decentraland-dao",
        "analysis_mode": mode,
        "description": "Decentraland DAO governance votes (frozen export, "
                       "2023-04-30). 53,533 votes by 4,133 voters on 1,816 "
                       "proposals over 705 days. Bipartite, so it is "
                       "projected onto voters: two voters are linked when "
                       "they voted on the same proposal in the window.",
        "source": "Decentraland DAO Transparency export (frozen 2023-04-30), "
                  "via github.com/Dr-Ali-Ahmed/dao-delegation-replication",
        "raw_file": os.path.basename(path),
        "raw_bytes": os.path.getsize(path),
        "raw_sha256_first_1mb": fileDigest(path),
        **retention,
        "raw_unique_proposals": int(frame["Snapshot ID"].nunique()),
        "raw_time_min": str(tMin),
        "raw_time_max": str(tMax),
        "raw_span_days": int((tMax - tMin).days),
        "evaluated_span_days": int((tMax - cut).days),
        "retained_nodes_active_in_evaluation": activeInEvaluation,
        "graph_family": "bipartite (one-mode projection onto voters)",
        "graph_nodes_are": "voter wallet addresses (Member)",
        "graph_edges_are": "two voters who voted on the same proposal "
                           "in the window",
        "snapshot_interval": "1 calendar month",
        "snapshot_count": len(snapshots),
        "directed": False,
        "weighted": False,
        "edge_weight_used": False,
        "edge_sign_used": False,
        "edge_attributes_available": "Choice # (yes/no/abstain), Vote Weight "
                                     "and six voting-power columns (Total VP, "
                                     "MANA, LAND, NAMES, DELEGATED, Rental); "
                                     "none is used",
        "edge_attributes_note": (
            "The real-data experiments use only temporal interaction "
            "topology. Dataset-specific edge weights and signs are not used "
            "by the existing TGAP transformations or metrics."),
    }
    preprocessing = {
        "analysis_mode": mode,
        "projection": "one-mode, onto voters (bipartite rejected: it makes "
                      "bridge width identical to edge count)",
        "node_selection": f"top {topVoters} voters by vote count, ranked over "
                          f"{len(selection)} selection-period votes",
        "top_voters_kept": topVoters,
        **retention,
        **windowReport,
        "retained_nodes_active_in_evaluation": activeInEvaluation,
        "unique_window_edges": sum(g.number_of_edges() for g in snapshots),
        "events_dropped_selection_period": int(len(frame) - len(evaluation)),
        "events_dropped_node_filter": int(len(evaluation)
                                          - len(keptEvaluation)),
        "vote_choice_used": False,
        "voting_power_used": False,
        "edge_weight_used": False,
        "edge_sign_used": False,
        "unused_fields_note": "Choice #, Vote Weight and the VP columns are "
                              "not used: no current TGAP metric or "
                              "transformation reads edge weights",
        "fixed_node_set": True,
        "isolated_nodes_included": True,
        "partition_source": partitionSource,
        **partitionReport,
        "cohesion_usable": False,
        "cohesion_note": "inactive voters appear as isolated nodes, so "
                         "snapshots are disconnected and algebraic "
                         "connectivity is 0; cohesion is not a target",
    }
    return PreparedDataset("decentraland", snapshots, communities, labels,
                           meta, preprocessing)
