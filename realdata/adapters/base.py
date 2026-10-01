'''
Shared preprocessing: turning timestamped real events into a TGAP-compatible
temporal graph.

TGAP needs a list of undirected networkx graphs over ONE node set, plus a
two-community partition. Six preprocessing decisions get us there, and each
one is a real choice with a real reason - none of them is silent.

DECISION 1 - one-mode projection, not the bipartite graph itself.
    Applies to the two BIPARTITE sources only (tgbl-wiki: a user edits a
    page; Decentraland: a voter votes on a proposal). If we fed the
    bipartite graph to TGAP with communities = (actors, items), then EVERY
    edge would cross between the two sides, so "bridge width" would equal
    the edge count and become an exact duplicate of density. The concept
    would be degenerate. Instead we project onto one side: two actors are
    connected when they touched the same item inside the same time window
    ("co-activity"). Bridge width then means what CATALYST wants it to
    mean - the number of ties between two communities of actors. The six
    UNIPARTITE sources need no projection at all (see edgelist.py).

DECISION 2 - a FIXED node set in every snapshot.
    Real streams have node churn: an actor active in March may be absent
    in April. TGAP's transformations assume the node set does not change
    (the anchor rule), and they would otherwise silently create nodes when
    adding an edge. So we choose the node set once (the retained actors)
    and include every one of them in every snapshot, isolated when
    inactive.
    CONSEQUENCE, stated plainly: snapshots contain isolated nodes and are
    therefore almost never connected, so algebraic-connectivity cohesion
    is 0 everywhere and is NOT used as a prediction target on real data.

DECISION 3 - keep only the most active actors, and always report BOTH
    counts. A one-mode projection turns each item into a clique among the
    actors who touched it, so the edge count grows quadratically;
    restricting to the topN most active actors keeps the projection
    tractable and keeps the graph focused on the part of the ecosystem that
    is actually interacting. This DISCARDS DATA. Every report therefore
    carries raw_nodes AND retained_nodes, raw_events AND retained_events,
    plus the retention percentages: a reader can never mistake the
    filtered graph for the whole dataset (see retentionSummary).

DECISION 4 - WHICH actors are kept depends on the analysis mode, because
    the obvious rule leaks the future. Ranking actors by activity over the
    WHOLE observation period means information from the last year can
    decide who appears in the first year's snapshot:

        2018 -------- 2019 -------- 2020 -------- 2021
                             ^
              selection using all four years leaks 2021 into 2018

    Two modes are therefore provided, and every output file records which
    one produced it:

      "temporal_evaluation" (the DEFAULT for scientific evaluation)
          The first SELECTION_FRACTION of the time span is a selection
          period. Actors are ranked using ONLY events inside it, the
          resulting set is frozen, and the snapshots that TGAP sees are
          built from the REMAINING period only. Selection and evaluation
          are disjoint in time, so no future information can enter.

      "descriptive" (full-period, kept for descriptive analysis)
          The original behaviour: rank over everything, snapshot
          everything. Useful for describing the dataset as a whole, but it
          is NOT leakage-safe and is labelled as such everywhere.

    Ground-truth node labels (email-Eu-core's departments) are a static
    attribute of the people, not something derived from the event stream,
    so label-based selection carries no temporal leakage in either mode.

DECISION 5 - the partition is detected ONCE and frozen, on data from the
    same period as node selection. Detecting communities separately per
    snapshot would mean a change in bridge width could come from the
    detector changing its mind rather than from the data, so a single
    frozen partition is required either way. The question is WHICH data
    detects it:

      "temporal_train"           detection on the selection-period graph
                                 only, then frozen for every later
                                 snapshot. Used in temporal_evaluation
                                 mode.

        selection-period history -> detect 2 communities -> freeze
             -> later snapshots -> TGAP

      "full_period_descriptive"  detection on the union of all snapshots.
                                 Used in descriptive mode; not
                                 leakage-safe, and labelled.

      "ground_truth_labels"      no detection at all (email-Eu-core).

    Every retained node must belong to exactly one of the two communities,
    because interCommunityEdges needs full coverage; detectTwoCommunities
    guarantees this by construction (side B is "all nodes minus side A"),
    so a node with no edges in the selection period still gets a side. How
    many such nodes there were is reported as
    nodes_isolated_in_partition_graph.

DECISION 6 - edge attributes are not used. No current TGAP metric or
    transformation reads an edge weight or sign, so repeated interactions
    collapse to one unweighted edge. Where a dataset ships richer
    information (the bitcoin trust ratings, Decentraland's voting power)
    it is recorded as available-but-unused rather than silently averaged
    away.
'''

import itertools

import networkx as nx
import numpy as np
import pandas as pd

from core.Communities import (detectCommunities, detectTwoCommunities,
                             interCommunityEdges)

# The two analysis modes of DECISION 4. Kept as module constants so every
# adapter, runner and test spells them the same way.
TEMPORAL_EVALUATION = "temporal_evaluation"
DESCRIPTIVE = "descriptive"
ANALYSIS_MODES = (TEMPORAL_EVALUATION, DESCRIPTIVE)

# Fraction of the observed time span used as the selection period in
# temporal_evaluation mode. 0.2 is a deliberate compromise: large enough
# that activity ranking is not dominated by a handful of early events,
# small enough to leave 80% of the span for evaluation. It is a fixed
# constant rather than a tuned parameter, so the rule stays deterministic
# and reproducible.
SELECTION_FRACTION = 0.2


class PreparedDataset:
    ''' Everything one real dataset contributes to a TGAP run.

    snapshots    : list[nx.Graph]  - the temporal graph, oldest first
    communities  : (setA, setB)    - the fixed partition
    labels       : list[str]       - a human label per snapshot (e.g. a date)
    meta         : dict            - dataset metadata for the report
    preprocessing: dict            - the decisions and what they discarded

    meta always carries `analysis_mode`, so no result can be traced back to
    the wrong methodology.
    '''

    def __init__(self, name, snapshots, communities, labels, meta,
                 preprocessing):
        self.name = name
        self.snapshots = snapshots
        self.communities = communities
        self.labels = labels
        self.meta = meta
        self.preprocessing = preprocessing


def checkMode(mode):
    ''' Fail loudly on a typo instead of silently running the wrong
    methodology. '''
    if mode not in ANALYSIS_MODES:
        raise ValueError(f"unknown analysis mode {mode!r}; "
                         f"expected one of {ANALYSIS_MODES}")
    return mode


def temporalSplit(times, fraction=SELECTION_FRACTION):
    ''' Split a numeric timestamp range into a selection period and an
    evaluation period.

    Returns (tMin, cut, tMax) where the selection period is
    [tMin, cut] and the evaluation period is (cut, tMax]. The cut is a
    deterministic function of the observed extremes only - no sorting of
    events, no quantiles over event counts - so it does not move when the
    event ordering changes.
    '''
    tMin, tMax = float(min(times)), float(max(times))
    return tMin, tMin + fraction * (tMax - tMin), tMax


def retentionSummary(rawNodes, retainedNodes, rawEvents, retainedEvents):
    ''' The raw-vs-retained block that every dataset report must carry.

    "raw" = what the source file contains. "retained" = what survives node
    selection and the other filters and therefore actually appears in the
    graphs TGAP sees. Reporting only the second number would make a
    201-node subset of a 986-node institution look like the whole
    institution.
    '''
    return {
        "raw_nodes": int(rawNodes),
        "retained_nodes": int(retainedNodes),
        "nodes_dropped": int(rawNodes - retainedNodes),
        "nodes_retained_pct": round(100.0 * retainedNodes / rawNodes, 2)
                              if rawNodes else 0.0,
        "raw_events": int(rawEvents),
        "retained_events": int(retainedEvents),
        "events_dropped": int(rawEvents - retainedEvents),
        "events_retained_pct": round(100.0 * retainedEvents / rawEvents, 2)
                               if rawEvents else 0.0,
        "events_dropped_pct": round(
            100.0 * (rawEvents - retainedEvents) / rawEvents, 2)
            if rawEvents else 0.0,
    }


def selectionWindowSummary(mode, activityBasis, fraction,
                           eventsTotal, eventsSelection, eventsEvaluation,
                           selectionStart, selectionEnd, evaluationEnd,
                           timeUnit):
    ''' The leakage-control block: what period chose the actors, what
    period was evaluated, and how much data sits outside the selection
    period. Written into preprocessing_summary.json for every dataset so
    the claim "no future information was used" is checkable rather than
    asserted.

    `activityBasis` is what the adapter ranked on ("top_active" or
    "ground_truth_labels"); the reported node_selection_mode combines it
    with the analysis mode, because the same ranking rule leaks or does not
    leak depending on which period it saw:

      ground_truth_labels      static node attribute - never leaks, in
                               either mode
      temporal_train           activity ranked over the selection period
                               only - does not leak
      full_period_descriptive  activity ranked over everything - LEAKS the
                               future into earlier snapshots
    '''
    if activityBasis == "ground_truth_labels":
        nodeSelectionMode, leaks = "ground_truth_labels", False
    elif mode == TEMPORAL_EVALUATION:
        nodeSelectionMode, leaks = "temporal_train", False
    else:
        nodeSelectionMode, leaks = "full_period_descriptive", True

    return {
        "analysis_mode": mode,
        "node_selection_mode": nodeSelectionMode,
        "node_selection_activity_basis": activityBasis,
        "selection_fraction_of_span": fraction,
        "selection_period": f"{selectionStart} .. {selectionEnd}",
        "evaluation_period": f"{selectionEnd} .. {evaluationEnd}",
        "time_unit": timeUnit,
        "events_total": int(eventsTotal),
        "events_in_selection_period": int(eventsSelection),
        "events_in_evaluation_period": int(eventsEvaluation),
        "pct_of_events_outside_selection_period": round(
            100.0 * eventsEvaluation / eventsTotal, 2) if eventsTotal else 0.0,
        # The single field a reviewer will look for.
        "future_information_used_for_node_selection": leaks,
    }


def projectCoActivity(events, actorKey, itemKey, windowKey, keepActors):
    ''' Build one snapshot per time window by one-mode projection.

    events     : iterable of dicts (or rows) with the three keys below
    actorKey   : field naming the node side we project onto
    itemKey    : field naming the side we project THROUGH
    windowKey  : field holding an already-computed window id
    keepActors : the fixed node set (sorted list)

    Two actors get an edge in a window when they touched at least one
    common item in that window. Edges are undirected and unweighted: a
    repeated interaction does not create a second edge, and no weight is
    stored, because none of the current TGAP metrics or transformations
    reads edge weights (DECISION 6).

    Returns (snapshots, windowIds) with windows in increasing time order.
    '''
    byWindow = {}
    for event in events:
        actor = event[actorKey]
        if actor not in keepActors:
            continue
        window = event[windowKey]
        byWindow.setdefault(window, {}).setdefault(
            event[itemKey], set()).add(actor)

    keepSorted = sorted(keepActors)
    snapshots = []
    windowIds = sorted(byWindow)
    for window in windowIds:
        graph = nx.Graph()
        graph.add_nodes_from(keepSorted)     # DECISION 2: fixed node set
        for _, actors in byWindow[window].items():
            actorList = sorted(actors)       # sorted => reproducible
            if len(actorList) > 1:
                graph.add_edges_from(itertools.combinations(actorList, 2))
        snapshots.append(graph)
    return snapshots, windowIds


def aggregateGraph(snapshots, nodes=None):
    ''' Union of every snapshot's edges over a fixed node set. Used to
    build the graph a partition is detected on. '''
    aggregate = nx.Graph()
    aggregate.add_nodes_from(sorted(nodes if nodes is not None
                                    else snapshots[0].nodes()))
    for graph in snapshots:
        aggregate.add_edges_from(sorted(graph.edges()))
    return aggregate


def _partitionFromGraph(graph, source, nCommunities=2):
    ''' Detect communities on `graph` and report the partition with the
    facts a reader needs to judge it.

    nCommunities = 2 (the default) reproduces the historical behaviour
    exactly, via detectTwoCommunities. nCommunities = None keeps the number
    the DATA supports; an integer merges down to that many.

    Coverage is guaranteed by the detector: the last group is defined as
    "every node not already assigned", so every node lands on exactly one
    side, including nodes with no edges at all. Those isolated nodes are
    counted and reported rather than hidden, because a node that never
    interacted in the detection period got its group by default.

    MODULARITY LOSS is reported whenever the partition was merged down.
    Collapsing a graph's natural community structure into two groups
    discards real structure - measured at up to 64% of the modularity on
    these datasets - and a number that large should never be invisible.
    '''
    if nCommunities == 2:
        communities = detectTwoCommunities(graph)
    else:
        communities = detectCommunities(graph, n=nCommunities)
    isolated = sum(1 for _, degree in graph.degree() if degree == 0)
    sizes = communities.sizes()
    nonEmpty = [s for s in sizes if s]
    report = {
        "community_mode": source,
        "n_communities": len(communities),
        "partition_sizes": sizes,
        "partition_graph_edges": graph.number_of_edges(),
        "partition_graph_nodes": graph.number_of_nodes(),
        "nodes_isolated_in_partition_graph": isolated,
        "smaller_side_pct": round(100.0 * min(nonEmpty) / sum(sizes), 2)
                            if nonEmpty and sum(sizes) else 0.0,
        "community_pairs": len(communities.pairs()),
    }
    report.update(_modularityReport(graph, communities))
    return communities, graph, report


def _modularityReport(graph, communities):
    ''' How much community structure the chosen partition captures, and how
    much a merge to this size discarded.

    Reported rather than asserted: whether 2 communities is an acceptable
    simplification is a scientific judgement about each dataset, and the
    reader can only make it with the number in front of them. On
    decentraland the loss is 0.00 (it really is bipolar); on bitcoin-otc it
    is 0.141 of 0.222.
    '''
    from networkx.algorithms import community as _community
    if graph.number_of_edges() == 0:
        return {"modularity": None, "natural_n_communities": None,
                "modularity_natural": None, "modularity_lost_by_merging": None}
    groups = [g for g in communities if g]
    try:
        achieved = float(_community.modularity(graph, groups))
        natural = _community.greedy_modularity_communities(graph)
        best = float(_community.modularity(graph, natural))
    except Exception:
        # Modularity is undefined for some degenerate partitions; report
        # None rather than a misleading number.
        return {"modularity": None, "natural_n_communities": None,
                "modularity_natural": None, "modularity_lost_by_merging": None}
    return {
        "modularity": round(achieved, 4),
        "natural_n_communities": len(natural),
        "modularity_natural": round(best, 4),
        "modularity_lost_by_merging": round(best - achieved, 4),
    }


def fixedPartitionFromAggregate(snapshots):
    ''' DECISION 5, descriptive variant: union every snapshot, detect two
    communities on that aggregate graph, and freeze the partition. Uses the
    whole observation period, so it is NOT leakage-safe; callers must
    label it. Deterministic, so repeated runs give the identical split.

    Returns (communities, aggregate) for backward compatibility. Use
    fixedPartitionWithReport when the run needs the provenance block.
    '''
    communities, aggregate, _ = _partitionFromGraph(
        aggregateGraph(snapshots), "full_period_descriptive")
    return communities, aggregate


def fixedPartitionWithReport(snapshots, mode, trainingSnapshots=None,
                             nodes=None, nCommunities=2):
    ''' DECISION 5, the mode-aware entry point.

    mode == "temporal_evaluation": detect on the selection-period graph
        built from `trainingSnapshots` (which must be supplied) over the
        full retained node set, then freeze.
    mode == "descriptive": detect on the union of all snapshots.

    Returns (communities, partitionGraph, report) where report names the
    community_mode used, so the choice is visible in the output files.
    '''
    checkMode(mode)
    nodes = nodes if nodes is not None else set(snapshots[0].nodes())
    if mode == TEMPORAL_EVALUATION:
        if not trainingSnapshots:
            raise ValueError("temporal_evaluation mode needs "
                             "trainingSnapshots for community detection")
        graph = aggregateGraph(trainingSnapshots, nodes)
        return _partitionFromGraph(graph, "temporal_train", nCommunities)
    return _partitionFromGraph(aggregateGraph(snapshots, nodes),
                               "full_period_descriptive", nCommunities)


def summariseSnapshots(snapshots, communities, labels):
    ''' Basic per-snapshot statistics, for the report and the figures.

    The node column is called retained_nodes, never just "nodes": these are
    the actors that survived selection, not the dataset's population
    (DECISION 3). Cohesion is deliberately absent: see DECISION 2.
    '''
    rows = []
    for index, (graph, label) in enumerate(zip(snapshots, labels)):
        degrees = [d for _, d in graph.degree()]
        rows.append({
            "snapshot_index": index,
            "label": label,
            "retained_nodes": graph.number_of_nodes(),
            "active_retained_nodes": int(sum(1 for d in degrees if d > 0)),
            "edges": graph.number_of_edges(),
            "density": nx.density(graph),
            "average_degree": float(np.mean(degrees)) if degrees else 0.0,
            "max_degree": int(max(degrees)) if degrees else 0,
            "bridge_width": len(interCommunityEdges(graph, communities)),
            "connected_components": nx.number_connected_components(graph),
            "is_connected": bool(nx.is_connected(graph))
                            if graph.number_of_nodes() else False,
        })
    return pd.DataFrame(rows)
