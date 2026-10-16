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
from .Base import _snapshots, setBridgeWidth


class BridgeWidthTransformation(TemporalGraphTransformation):
    ''' Change the WIDTH OF THE BRIDGE between two communities.

    Property : number of inter-community edges (the redundant ties that
               make a bridge "wide" in the CATALYST sense).
    Delta    : relative change of that number. delta=+0.1 means
               newWidth = round(width * 1.1); with width 10 -> 11 bridges.
    Anchor   : node set AND total edge count are preserved. Every bridge
               added is paid for by removing one intra-community edge
               (and vice versa), so the model sees the same amount of
               activity, only ROUTED differently. This is the graph
               equivalent of TSAP holding the last value fixed.
    Leakage  : swapping intra<->inter edges necessarily changes the
               internal density of the communities a little. Unavoidable
               under a fixed edge budget; kept small because only a few
               edges move.
    '''

    name = "Bridge Width"

    def __init__(self, communities=None, seed=42, strict=False,
                 communityPair=None):
        # communities: optional (setA, setB). Pass explicitly for real
        # experiments (see Communities.py); auto-detected per call if None.
        # strict: raise InfeasibleTransformation instead of under-paying
        # when the edge-count invariant cannot be kept (default off, so
        # behaviour is unchanged unless a caller asks for it).
        self.communities = communities
        self.seed = seed
        self.strict = strict
        # communityPair=(i, j) targets ONE bridge when the partition has more
        # than two communities. None means the aggregate bridge (every
        # boundary), which for a two-community partition is the same thing.
        self.communityPair = communityPair
        if communityPair is not None:
            i, j = communityPair
            self.name = f"Bridge Width {i}-{j}"

    def transformGraph(self, graph, delta):
        # Re-seed on every call: same input -> same output (stability).
        rng = random.Random(self.seed)
        communities = self.communities
        if communities is None:
            communities = detectTwoCommunities(graph)
        # Target width = current width scaled by (1 + delta), rounded to a
        # whole number of edges (graphs are discrete; see module note).
        width = len(interCommunityEdges(graph, communities,
                                        self.communityPair))
        target = round(width * (1 + delta))
        # All the add/remove/pay-for-it mechanics live in setBridgeWidth.
        return setBridgeWidth(graph, communities, target, rng,
                              strict=self.strict, pair=self.communityPair)

    def propertyValue(self, x):
        ''' Property = mean bridge width across snapshots (for a single
        graph, simply its bridge width). Mean rather than last-snapshot,
        because the structural transformation scales EVERY snapshot. '''
        widths = []
        for g in _snapshots(x):
            communities = self.communities
            if communities is None:
                communities = detectTwoCommunities(g)
            widths.append(len(interCommunityEdges(g, communities,
                                                  self.communityPair)))
        return float(np.mean(widths))
