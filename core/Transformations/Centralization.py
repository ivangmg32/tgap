'''
Concrete graph transformations - the TGAP analogues of TSAP's
transformVolatility and transformTrendReverse.

Each one changes a single interpretable structural property by a ratio
delta, deterministically (seeded), returning a new graph. See the base
class in TemporalGraphTransformation.py for the design rules (anchor,
determinism, never mutate the input).

A note on discreteness, worth understanding before reading plots:
a time-series value can change by exactly 10%, but a graph has a WHOLE
NUMBER of edges - you cannot add 0.6 of a bridge. We therefore round to
the nearest integer number of edge changes. Consequence: sensitivity
curves (plotTrans) look STEPPY for graphs, not smooth like TSAP's. That
is not a bug; it is the honest geometry of discrete structures.

A note on property overlap: just like TSAP's volatility transformation
slightly affects the trend (they share the same anchor), rewiring edges
toward a hub can occasionally touch a bridge edge, etc. Perfectly
orthogonal structural properties do not exist; we document the leakage
instead of pretending it away.
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
from .Base import _snapshots


class CentralizationTransformation(TemporalGraphTransformation):
    ''' Change how CENTRALIZED the graph is around its biggest hub.

    Property : concentration of ties on the highest-degree node
               (measured by DegreeCentralizationMetric).
    Delta    : the fraction of ALL edges that get rewired. delta=+0.1
               moves ~10% of the edges onto the hub ("power concentrates");
               delta=-0.1 moves ~10% of the hub's edges away from it
               ("power redistributes").
    Anchor   : node set and total edge count are preserved - edges are
               REWIRED (one endpoint moved), never created or destroyed.
               Additionally, when `communities` is given, every rewiring
               PRESERVES the tie's intra/inter status, so bridge width is
               left exactly untouched: centralization then changes
               ORTHOGONALLY to bridge width, and the two explanations do
               not contaminate each other.
    Leakage  : only when communities=None. Without a partition we cannot
               know which edges are bridges, so repointing an edge onto
               the hub may turn an intra-community tie into a cross-
               community one (or vice versa), changing bridge width as a
               side effect. We measured this leakage to be LARGE on
               two-community graphs - always pass `communities` when you
               are also explaining bridge width.
    '''

    name = "Centralization"

    def __init__(self, communities=None, seed=42):
        # communities: optional (setA, setB). Strongly recommended - see
        # the Anchor/Leakage notes above.
        self.communities = communities
        self.seed = seed

    def _sameSide(self, a, b):
        ''' True if nodes a and b belong to the same community.
        With no partition given, everything counts as the same side
        (i.e. the status-preservation constraint is switched off).

        Asks the partition directly instead of testing membership of one
        set, so this works for ANY number of communities. For two
        communities `(a in setA) == (b in setA)` gave the same answer, which
        is why the generalisation needed no change of behaviour. '''
        if self.communities is None:
            return True
        return asPartition(self.communities).sameCommunity(a, b)

    def transformGraph(self, graph, delta):
        g = graph.copy()
        rng = random.Random(self.seed)

        m = g.number_of_edges()
        k = round(abs(delta) * m)  # how many edges to rewire
        if k == 0 or m == 0:
            return g

        # The hub = highest-degree node. Ties broken by node id, so the
        # choice is deterministic.
        hub = max(sorted(g.nodes()), key=lambda n: g.degree(n))

        if delta > 0:
            # --- CONCENTRATE: repoint edges onto the hub ---
            # For each edge (u, v) we DETACH endpoint u and reattach it to
            # the hub, giving (hub, v). To preserve the tie's intra/inter
            # status, the detached endpoint u must live on the hub's side
            # (then u -> hub swaps two same-side nodes and the status of
            # the tie towards v is unchanged).
            candidates = []
            for u, v in sorted(g.edges()):
                if hub in (u, v):
                    continue  # already a hub tie: nothing to concentrate
                # Orient the pair so that the detached endpoint is on the
                # hub's side; skip edges where neither endpoint is.
                if self._sameSide(u, hub):
                    candidates.append((u, v))
                elif self._sameSide(v, hub):
                    candidates.append((v, u))
            rng.shuffle(candidates)
            rewired = 0
            for u, v in candidates:
                if rewired >= k:
                    break
                # Skip if the hub is already tied to v (adding would merge
                # two edges into one and shrink the edge count, violating
                # the anchor).
                if not g.has_edge(hub, v):
                    g.remove_edge(u, v)
                    g.add_edge(hub, v)
                    rewired += 1
        else:
            # --- REDISTRIBUTE: drain the CURRENTLY most-connected node ---
            # Mathematical necessity, found by the faithfulness harness:
            # under edge-count-preserving rewiring, Freeman centralization
            # collapses to C = (n*d_max - 2m)/((n-1)(n-2)) - the sum term
            # is constant, so C moves ONLY if the maximum degree moves.
            # Draining a single fixed hub silently achieves dC = 0
            # whenever another node is TIED at d_max (the original bug).
            # So each step re-identifies the current top-degree node and
            # takes an edge from IT - ties get drained one by one and
            # d_max genuinely falls.
            rewired = 0
            attempts = 0
            while rewired < k and attempts < 4 * k + 20:  # bounded loop
                attempts += 1
                top = max(sorted(g.nodes()), key=lambda n: g.degree(n))
                neighbors = sorted(g.neighbors(top))
                if not neighbors:
                    break
                v = neighbors[rng.randrange(len(neighbors))]
                # Give this tie to the currently poorest node (lowest
                # degree, ties broken by id) that is on TOP's side
                # (status preservation), is not v or top, and is not
                # already tied to v. Note v's degree is unchanged by the
                # move (loses top, gains receiver), so only top (-1) and
                # receiver (+1) move - receiver starts minimal, so it
                # cannot itself become the new maximum.
                receivers = sorted(g.nodes(), key=lambda n: (g.degree(n), n))
                receiver = next(
                    (r for r in receivers
                     if r not in (top, v)
                     and self._sameSide(r, top)
                     and not g.has_edge(r, v)),
                    None,
                )
                if receiver is None:
                    continue  # this v had no valid receiver; try another
                g.remove_edge(top, v)
                g.add_edge(receiver, v)
                rewired += 1

        return g

    def propertyValue(self, x):
        ''' Property = mean Freeman degree centralization across
        snapshots. NOTE the semantic gap this bridges: this
        transformation's `delta` is the FRACTION OF EDGES REWIRED (a
        mechanism knob), not a relative change of centralization itself.
        Measuring the metric before/after lets the explainer normalize by
        the centralization change actually achieved, making impacts
        comparable with the other concepts. '''
        metric = DegreeCentralizationMetric()
        return float(np.mean([metric.measure(g) for g in _snapshots(x)]))
