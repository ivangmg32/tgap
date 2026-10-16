'''
Shared machinery every concrete transformation builds on.

Kept in one place because these helpers encode decisions that MUST be
identical across transformations - edge canonicalisation, the "prefer not to
disconnect the graph" rule, and the bridge-rewiring engine. Duplicating them
per transformation would let two concepts drift apart silently.

Concrete transformations live one class per file beside this one.
'''

import random

import networkx as nx
import numpy as np

from ..TemporalGraphTransformation import TemporalGraphTransformation
from ..Communities import (
    asPartition,
    detectTwoCommunities,
    interCommunityEdges,
    intraCommunityEdges,
)
from ..GraphMetric import DegreeCentralizationMetric
# Feasibility imports only Communities, so there is no import cycle here.
from ..Feasibility import InfeasibleTransformation, bridgeWidthFeasibility


def _edgeKey(u, v):
    ''' Normalize an undirected edge to a canonical (min, max) tuple so
    edges can be compared across graphs regardless of storage order. '''
    return (u, v) if u <= v else (v, u)


def _snapshots(x):
    ''' Accept either a single graph or a temporal graph (list of
    snapshots) and always return a list - lets propertyValue
    implementations serve both explainers with one code path. '''
    return x if isinstance(x, list) else [x]


def _safeToRemove(graph, edges):
    ''' Helper: from a candidate edge list, prefer edges whose removal
    does NOT disconnect the graph (i.e. edges that are not cut-edges).
    A disconnected graph would make cohesion collapse to zero for a
    boring reason and pollute the explanation. Falls back to the full
    candidate list if every candidate is a cut-edge. '''
    # nx.bridges yields the cut-edges ("bridges" in the graph-theory
    # sense - an unfortunate naming clash with CATALYST's social bridges).
    cutEdges = set()
    for u, v in nx.bridges(graph):
        cutEdges.add((u, v))
        cutEdges.add((v, u))
    safe = [e for e in edges if e not in cutEdges]
    return safe if safe else list(edges)


def setBridgeWidth(graph, communities, targetWidth, rng, strict=False,
                   pair=None):
    ''' Return a copy of `graph` whose bridge has exactly `targetWidth`
    edges (clamped to >= 1 so the communities never fully disconnect),
    keeping node set and TOTAL EDGE COUNT fixed: every bridge added is paid
    for by removing an intra-community edge, and vice versa.

    WHICH bridge, when there are more than two communities:
      pair=None    the aggregate bridge - every edge crossing any community
                   boundary. With two communities there is only one
                   boundary, so this is exactly the historical behaviour.
      pair=(i, j)  the bridge between communities i and j only. Edges are
                   added between those two groups, and the payment is taken
                   from inside those two groups, so no third community is
                   disturbed. For a two-community partition, pair=(0, 1)
                   and pair=None are provably identical - the regression
                   tests assert that edge for edge.

    This is the shared engine behind BridgeWidthTransformation (which
    picks the target from a single delta) and BridgeTrendTransformation
    (which computes a different target per snapshot to reshape the
    trajectory). `rng` is supplied by the caller so each transformation
    controls its own determinism.

    Boundary behavior (documented, tested, NOT silent failures):
    - If the graph runs out of candidates (cross pairs when widening,
      intra edges/pairs when paying), fewer edges move than requested and
      the edge-count anchor may not hold exactly. On tiny or near-complete
      graphs, check the achieved change (see propertyValue /
      explainDetailed) instead of assuming the target was reached.
    - `strict=True` turns that boundary case into an EXPLICIT failure: the
      function raises core.Feasibility.InfeasibleTransformation, carrying
      the measured counts that prove the payment was impossible, instead
      of under-paying and returning a graph with a different edge count.
      Default is False so existing behaviour and existing results are
      unchanged; real-data evaluation screens with strict=True and records
      an "infeasible" status (see realdata/run_real_data.py).
    - Rounding upstream uses Python's round(), which is round-half-to-
      EVEN (round(4.5)=4, round(5.5)=6). Deterministic, but worth knowing
      at exact .5 boundaries. '''
    g = graph.copy()
    partition = asPartition(communities)
    if pair is None:
        # Aggregate mode: widening may connect any two distinct communities,
        # and payment may come from inside any of them.
        crossPairs = [(a, b) for i, j in partition.pairs()
                      for a in partition[i] for b in partition[j]]
        payableCommunities = range(len(partition))
    else:
        i, j = pair
        crossPairs = [(a, b) for a in partition[i] for b in partition[j]]
        payableCommunities = (i, j)

    bridges = interCommunityEdges(g, partition, pair)
    width = len(bridges)
    targetWidth = max(1, targetWidth)  # never sever the last tie
    k = targetWidth - width  # >0: widen, <0: narrow

    if strict and k != 0:
        # Cheap pre-check on the raw pool sizes. This is a NECESSARY
        # condition only: the payment also prefers non-cut edges, which can
        # shrink the usable pool further, so the exact checks below sit at
        # the point where the payment is actually made.
        verdict = bridgeWidthFeasibility(graph, partition, targetWidth,
                                         pair=pair)
        if not verdict["feasible"]:
            raise InfeasibleTransformation(verdict["reason"], verdict)

    if k > 0:
        # --- WIDEN: add k new inter-community edges ---
        # Candidates: all cross pairs that are not edges yet (sorted so
        # the seeded sampling is reproducible).
        candidates = sorted(e for e in crossPairs if not g.has_edge(*e))
        toAdd = rng.sample(candidates, min(k, len(candidates)))
        if strict and len(toAdd) < k:
            raise InfeasibleTransformation(
                "insufficient cross-community non-edges to widen the bridge",
                {"edges_needed": k, "edges_available": len(candidates),
                 "current_width": width, "clamped_target": targetWidth})
        g.add_edges_from(toAdd)
        # Pay for them: remove the same number of intra edges,
        # preferring ones that do not disconnect the graph.
        payable = [e for c in payableCommunities
                   for e in intraCommunityEdges(g, partition, c)]
        intra = _safeToRemove(g, sorted(payable))
        toRemove = rng.sample(intra, min(len(toAdd), len(intra)))
        if strict and len(toRemove) < len(toAdd):
            # The exact failure: fewer removable intra edges than bridge
            # edges added, so the edge count would rise. Reported with the
            # measured pool, which is the post-addition, cut-edge-preferring
            # pool the mechanism really draws from.
            raise InfeasibleTransformation(
                "insufficient removable intra-community edges to preserve "
                "total edge count",
                {"edges_added": len(toAdd),
                 "removable_intra_edges": len(intra),
                 "current_width": width, "clamped_target": targetWidth})
        g.remove_edges_from(toRemove)

    elif k < 0:
        # --- NARROW: remove |k| inter-community edges ---
        toRemove = rng.sample(bridges, -k)
        g.remove_edges_from(toRemove)
        # Pay back: add the same number of intra edges.
        candidates = sorted(
            (a, b) for c in payableCommunities
            for a in partition[c] for b in partition[c]
            if a < b and not g.has_edge(a, b))
        toAdd = rng.sample(candidates, min(len(toRemove), len(candidates)))
        if strict and len(toAdd) < len(toRemove):
            raise InfeasibleTransformation(
                "insufficient intra-community non-edges to preserve total "
                "edge count",
                {"edges_removed": len(toRemove),
                 "intra_nonedges_available": len(candidates),
                 "current_width": width, "clamped_target": targetWidth})
        g.add_edges_from(toAdd)

    # k == 0: already at the target -> graph unchanged.
    return g
