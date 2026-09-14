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

from .TemporalGraphTransformation import TemporalGraphTransformation
from .Communities import (
    detectTwoCommunities,
    interCommunityEdges,
    intraCommunityEdges,
)
from .GraphMetric import DegreeCentralizationMetric


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


def setBridgeWidth(graph, communities, targetWidth, rng):
    ''' Return a copy of `graph` whose bridge between the two communities
    has exactly `targetWidth` edges (clamped to >= 1 so the communities
    never fully disconnect), keeping node set and TOTAL EDGE COUNT fixed:
    every bridge added is paid for by removing an intra-community edge,
    and vice versa.

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
    - Rounding upstream uses Python's round(), which is round-half-to-
      EVEN (round(4.5)=4, round(5.5)=6). Deterministic, but worth knowing
      at exact .5 boundaries. '''
    g = graph.copy()
    setA, setB = communities

    bridges = interCommunityEdges(g, communities)
    width = len(bridges)
    targetWidth = max(1, targetWidth)  # never sever the last tie
    k = targetWidth - width  # >0: widen, <0: narrow

    if k > 0:
        # --- WIDEN: add k new inter-community edges ---
        # Candidates: all cross pairs that are not edges yet (sorted so
        # the seeded sampling is reproducible).
        candidates = sorted(
            (a, b) for a in setA for b in setB if not g.has_edge(a, b)
        )
        toAdd = rng.sample(candidates, min(k, len(candidates)))
        g.add_edges_from(toAdd)
        # Pay for them: remove the same number of intra edges,
        # preferring ones that do not disconnect the graph.
        intra = _safeToRemove(g, intraCommunityEdges(g, communities))
        toRemove = rng.sample(intra, min(len(toAdd), len(intra)))
        g.remove_edges_from(toRemove)

    elif k < 0:
        # --- NARROW: remove |k| inter-community edges ---
        toRemove = rng.sample(bridges, -k)
        g.remove_edges_from(toRemove)
        # Pay back: add the same number of intra edges.
        candidates = sorted(
            [(a, b) for a in setA for b in setA if a < b and not g.has_edge(a, b)]
            + [(a, b) for a in setB for b in setB if a < b and not g.has_edge(a, b)]
        )
        toAdd = rng.sample(candidates, min(len(toRemove), len(candidates)))
        g.add_edges_from(toAdd)

    # k == 0: already at the target -> graph unchanged.
    return g


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

    def __init__(self, communities=None, seed=42):
        # communities: optional (setA, setB). Pass explicitly for real
        # experiments (see Communities.py); auto-detected per call if None.
        self.communities = communities
        self.seed = seed

    def transformGraph(self, graph, delta):
        # Re-seed on every call: same input -> same output (stability).
        rng = random.Random(self.seed)
        communities = self.communities
        if communities is None:
            communities = detectTwoCommunities(graph)
        # Target width = current width scaled by (1 + delta), rounded to a
        # whole number of edges (graphs are discrete; see module note).
        width = len(interCommunityEdges(graph, communities))
        target = round(width * (1 + delta))
        # All the add/remove/pay-for-it mechanics live in setBridgeWidth.
        return setBridgeWidth(graph, communities, target, rng)

    def propertyValue(self, x):
        ''' Property = mean bridge width across snapshots (for a single
        graph, simply its bridge width). Mean rather than last-snapshot,
        because the structural transformation scales EVERY snapshot. '''
        widths = []
        for g in _snapshots(x):
            communities = self.communities
            if communities is None:
                communities = detectTwoCommunities(g)
            widths.append(len(interCommunityEdges(g, communities)))
        return float(np.mean(widths))


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
        (i.e. the status-preservation constraint is switched off). '''
        if self.communities is None:
            return True
        setA, _ = self.communities
        return (a in setA) == (b in setA)

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


class BridgeTrendTransformation(TemporalGraphTransformation):
    ''' Change the TREND of the bridge width across snapshots - the
    direct TGAP port of TSAP's transformTrendReverse, and the natural
    language for CATALYST's "bridge decay" scenario.

    This transformation is INHERENTLY TEMPORAL: it reshapes a trajectory,
    so it overrides transform() on the whole snapshot list and has no
    single-graph mode (transformGraph raises).

    Property : the slope of the bridge-width series w_0..w_{T-1}.
               delta > 0 -> history is pushed DOWN, so the same present
               is reached from below: a RISING (recovering) trajectory.
               delta < 0 -> history is pushed UP: a DECAYING trajectory.
    Delta    : compounding per-step ratio, exactly as in TSAP: walking
               backwards from the last snapshot, each step's width is
               divided by (1 + delta), so the effect grows the further
               back in time you go.
    Anchor   : the LAST SNAPSHOT is returned completely untouched - the
               TSAP anchor rule ("keep the last value fixed") applied in
               the time dimension. A model that only reads the present
               (e.g. PersistenceTemporalModel) must be exactly blind to
               this transformation; only models that read the trajectory
               can react. Within each earlier snapshot, node set and edge
               count are preserved by setBridgeWidth as usual.
    '''

    name = "Bridge Trend"

    # The property is a SLOPE, which is legitimately 0 for a stable
    # bridge - so a relative achieved change would divide by zero.
    # "absolute" tells the explainer to use (slopeAfter - slopeBefore)
    # in the slope's own units (edges per snapshot-step).
    deltaMode = "absolute"

    def __init__(self, communities, seed=42):
        # communities is REQUIRED here (no auto-detection): the whole
        # point is to steer one well-defined bridge through time, so the
        # partition must be the same in every snapshot.
        self.communities = communities
        self.seed = seed

    def propertyValue(self, x):
        ''' Property = OLS slope of the bridge-width series across
        snapshots (edges per step). Undefined (None) for fewer than two
        snapshots - a single graph has no trajectory. '''
        snapshots = _snapshots(x)
        if len(snapshots) < 2:
            return None
        widths = [len(interCommunityEdges(g, self.communities))
                  for g in snapshots]
        slope, _ = np.polyfit(np.arange(len(widths)), widths, 1)
        return float(slope)

    def transformGraph(self, graph, delta):
        raise NotImplementedError(
            "BridgeTrendTransformation changes a trajectory across "
            "snapshots; it has no meaning for a single graph. Use it "
            "with TgapExplainer (temporal), not GraphExplainer.")

    def transform(self, temporalGraph, delta):
        # 1. Read the current trajectory of the property.
        widths = [len(interCommunityEdges(g, self.communities))
                  for g in temporalGraph]

        # 2. Compute the target trajectory with TSAP's backward recursion
        #    (transformTrendReverse, verbatim, on the width series):
        #    keep the last value; walking backwards, rebuild each point
        #    from the ORIGINAL step and divide by (1 + delta).
        target = [float(w) for w in widths]
        i = len(target) - 2
        while i >= 0:
            origChange = widths[i] - widths[i + 1]
            target[i] = (target[i + 1] + origChange) / (1 + delta)
            i = i - 1

        # 3. Realize the target in the graphs: earlier snapshots get
        #    their bridge width set to the (rounded) target; the last
        #    snapshot is the anchor and passes through untouched.
        result = []
        for t, g in enumerate(temporalGraph[:-1]):
            # Per-snapshot seed stream: deterministic, but different
            # snapshots make independent edge choices.
            rng = random.Random(self.seed + t)
            result.append(setBridgeWidth(
                g, self.communities, round(target[t]), rng))
        result.append(temporalGraph[-1].copy())
        return result


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
        preservation constraint is switched off). '''
        if self.communities is None:
            return True
        setA, _ = self.communities
        return (u in setA) == (v in setA)

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

    def __init__(self, communities=None, seed=42):
        self.communities = communities
        self.seed = seed

    def _isIntra(self, u, v):
        ''' True if (u, v) stays inside one community; with no partition
        given, every pair qualifies (constraint switched off). '''
        if self.communities is None:
            return True
        setA, _ = self.communities
        return (u in setA) == (v in setA)

    def transformGraph(self, graph, delta):
        g = graph.copy()
        rng = random.Random(self.seed)

        m = g.number_of_edges()
        k = round(m * (1 + delta)) - m
        if k > 0:
            # Add k edges between (eligible) pairs not connected yet.
            candidates = sorted(e for e in nx.non_edges(g)
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
