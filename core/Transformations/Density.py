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
from .Base import _edgeKey, _snapshots, _safeToRemove


class DensityTransformation(TemporalGraphTransformation):
    ''' Change the overall DENSITY (total number of edges).

    Property : total edge count.
    Delta    : relative change. delta=+0.1 -> 10% more edges (added
               between random unconnected pairs); delta=-0.1 -> 10% fewer
               (removed, preferring non-cut-edges to avoid disconnection).
    Anchor   : node set preserved. The edge count is deliberately NOT
               preserved here - the edge count IS the property being
               changed (just as TSAP's volatility transformation is
               allowed to change the volatility). When `communities` is
               given, added/removed edges are confined to INTRA-community
               pairs, so bridge width is preserved exactly.
    Leakage  : LARGE when communities=None on community-structured
               graphs: the pool of unconnected pairs is dominated by
               cross-community pairs (two sparse blobs have ~|A|x|B|
               cross non-edges), so "add 10% more edges" mostly WIDENS
               THE BRIDGE as a side effect. Pass `communities` whenever
               bridge width is also being explained.
    '''

    name = "Density"

    # The edge count IS this transformation's property, so it makes no
    # edge-count promise. core.Feasibility reads this attribute, which is
    # why a changed edge count here is never reported as a violation.
    preservesEdgeCount = False

    def __init__(self, communities=None, seed=42):
        self.communities = communities
        self.seed = seed

    def _isIntra(self, u, v):
        ''' True if (u, v) stays inside one community; with no partition
        given, every pair qualifies (constraint switched off).

        Works for ANY number of communities, so confining density changes
        to intra-community pairs preserves the ENTIRE pairwise bridge
        matrix, not merely one bridge. '''
        if self.communities is None:
            return True
        return asPartition(self.communities).sameCommunity(u, v)

    def transformGraph(self, graph, delta):
        g = graph.copy()
        rng = random.Random(self.seed)

        m = g.number_of_edges()
        k = round(m * (1 + delta)) - m
        if k > 0:
            # Add k edges between (eligible) pairs not connected yet.
            # _edgeKey BEFORE sorting. nx.non_edges derives pairs from set
            # arithmetic, so the ORIENTATION it yields them in depends on the
            # hash of the node labels - and Python randomises string hashes
            # per process. Without canonicalisation the same pair arrives as
            # ('28','3') in one run and ('3','28') in the next, sorting to
            # different positions, so the seeded sample picked different
            # edges across runs. Measured: ~30 of 1,440 real-data rows moved
            # between otherwise identical runs. Integer-labelled synthetic
            # graphs were unaffected (hash(int) == int), which is why this
            # survived the synthetic suite.
            candidates = sorted(_edgeKey(*e) for e in nx.non_edges(g)
                                if self._isIntra(*e))
            g.add_edges_from(rng.sample(candidates, min(k, len(candidates))))
        elif k < 0:
            # Remove |k| (eligible) edges, avoiding cut-edges where possible.
            eligible = sorted(e for e in g.edges() if self._isIntra(*e))
            candidates = _safeToRemove(g, eligible)
            g.remove_edges_from(rng.sample(candidates, min(-k, len(candidates))))
        return g

    def propertyValue(self, x):
        ''' Property = mean edge count across snapshots. (Edge count and
        density differ only by the constant n(n-1)/2, so their RELATIVE
        changes are identical - we use the count, the simpler number.) '''
        return float(np.mean([g.number_of_edges() for g in _snapshots(x)]))
