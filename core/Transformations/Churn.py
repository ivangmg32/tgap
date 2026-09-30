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


class ChurnTransformation(TemporalGraphTransformation):
    ''' Change the CHURN of the structure - how much of the graph's
    history differs from its present. This is the temporal analogue of
    TSAP's volatility: volatility is how much a series wiggles around
    its anchor; churn is how much past snapshots' edges differ from the
    last snapshot's.

    Inherently temporal: overrides transform(); transformGraph raises.

    Property : per earlier snapshot, the set of edges that DISAGREE with
               the last snapshot (present in one but not the other).
    Delta    : delta < 0 -> REDUCE churn: a fraction |delta| of the
               disagreeing edges are flipped to agree with the last
               snapshot (history becomes calmer / more like the present).
               delta > 0 -> INCREASE churn: a fraction delta of the
               agreeing edges are swapped for edges that exist in
               neither graph (history becomes noisier).
    Anchor   : the LAST SNAPSHOT is untouched (models reading only the
               present must be blind to churn). Node set and edge count
               of every snapshot are preserved: changes are done as
               remove-one-add-one swaps. When `communities` is given,
               only INTRA-community edges are churned, so every
               snapshot's bridge width is also preserved exactly
               (orthogonality with the bridge transformations).
    '''

    name = "Churn"

    def __init__(self, communities=None, seed=42):
        self.communities = communities
        self.seed = seed

    def transformGraph(self, graph, delta):
        raise NotImplementedError(
            "ChurnTransformation compares snapshots across time; it has "
            "no meaning for a single graph. Use it with TgapExplainer.")

    def _isIntra(self, u, v):
        ''' True if the edge (u, v) stays inside one community.
        With no partition given, every edge qualifies (the bridge-
        preservation constraint is switched off).

        Works for ANY number of communities: churning only edges that stay
        inside a community leaves every pairwise bridge untouched, not just
        the single bridge of a two-community partition. '''
        if self.communities is None:
            return True
        return asPartition(self.communities).sameCommunity(u, v)

    def propertyValue(self, x):
        ''' Property = mean Jaccard DISTANCE between each earlier
        snapshot's edge set and the last snapshot's, over the churn-
        eligible universe (intra edges when a partition is given - the
        same universe the transformation operates on).

        Jaccard distance J(E1, E2) = |symmetric difference| / |union|:
        0 = identical edge sets, 1 = completely disjoint. The mean over
        history is a single number for "how much does the past disagree
        with the present" - churn, made measurable. None for a single
        snapshot (no history to disagree). '''
        snapshots = _snapshots(x)
        if len(snapshots) < 2:
            return None
        lastEdges = {_edgeKey(u, v) for u, v in snapshots[-1].edges()
                     if self._isIntra(u, v)}
        distances = []
        for g in snapshots[:-1]:
            gEdges = {_edgeKey(u, v) for u, v in g.edges()
                      if self._isIntra(u, v)}
            union = gEdges | lastEdges
            if not union:
                distances.append(0.0)
            else:
                distances.append(len(gEdges ^ lastEdges) / len(union))
        return float(np.mean(distances))

    def transform(self, temporalGraph, delta):
        last = temporalGraph[-1]
        lastEdges = {_edgeKey(u, v) for u, v in last.edges()}

        result = []
        for t, g in enumerate(temporalGraph[:-1]):
            rng = random.Random(self.seed + t)  # deterministic per snapshot
            g = g.copy()
            gEdges = {_edgeKey(u, v) for u, v in g.edges()}

            if delta < 0:
                # --- CALM the history: flip disagreements into agreements ---
                # onlyHere: edges g has but the present does not (they will
                # be removed); onlyLast: edges the present has but g does
                # not (they will be added). Paired one-for-one so the edge
                # count never moves.
                onlyHere = sorted(e for e in gEdges - lastEdges
                                  if self._isIntra(*e))
                onlyLast = sorted(e for e in lastEdges - gEdges
                                  if self._isIntra(*e))
                n = min(round(-delta * len(onlyHere)),
                        len(onlyHere), len(onlyLast))
                if n > 0:
                    toRemove = rng.sample(onlyHere, n)
                    toAdd = rng.sample(onlyLast, n)
                    g.remove_edges_from(toRemove)
                    g.add_edges_from(toAdd)

            elif delta > 0:
                # --- AGITATE the history: flip agreements into noise ---
                # Swap edges shared with the present for pairs connected
                # in NEITHER graph, increasing the disagreement.
                common = sorted(e for e in gEdges & lastEdges
                                if self._isIntra(*e))
                # Prefer removals that do not disconnect the snapshot.
                common = _safeToRemove(g, common)
                nodes = sorted(g.nodes())
                fresh = sorted(
                    (a, b)
                    for i, a in enumerate(nodes) for b in nodes[i + 1:]
                    if _edgeKey(a, b) not in gEdges
                    and _edgeKey(a, b) not in lastEdges
                    and self._isIntra(a, b)
                )
                n = min(round(delta * len(common)), len(common), len(fresh))
                if n > 0:
                    toRemove = rng.sample(common, n)
                    toAdd = rng.sample(fresh, n)
                    g.remove_edges_from(toRemove)
                    g.add_edges_from(toAdd)

            result.append(g)

        # The anchor: the present is returned exactly as it was.
        result.append(last.copy())
        return result
