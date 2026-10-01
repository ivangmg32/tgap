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

    KNOWN LIMITATION on long histories (measured, not hypothetical). The
    backward recursion divides by (1 + delta) at every step, so the factor
    reaching the OLDEST snapshot is (1 + delta)^(T-1) - about 8.95 at
    delta = 0.1 with T = 24 snapshots. Targets below 1 are clamped to 1 by
    setBridgeWidth, which never severs the last tie. When many snapshots
    sit on that floor the intended geometric shape is lost, and the
    achieved slope change can take the OPPOSITE sign to the requested one.
    The recursion is kept verbatim from TSAP deliberately (changing it
    would change the concept, and would change the synthetic results this
    project reports). Instead the condition is DETECTED and such rows are
    marked invalid: see core.Feasibility.bridgeTrendDirection, which
    returns status "saturated" or "wrong_direction". Rows that are not
    "ok" must not be used in aggregate conclusions.
    '''

    name = "Bridge Trend"

    # The property is a SLOPE, which is legitimately 0 for a stable
    # bridge - so a relative achieved change would divide by zero.
    # "absolute" tells the explainer to use (slopeAfter - slopeBefore)
    # in the slope's own units (edges per snapshot-step).
    deltaMode = "absolute"

    def __init__(self, communities, seed=42, strict=False,
                 communityPair=None):
        # communities is REQUIRED here (no auto-detection): the whole
        # point is to steer one well-defined bridge through time, so the
        # partition must be the same in every snapshot.
        # strict: see BridgeWidthTransformation - raises instead of
        # silently changing a snapshot's edge count. Default off.
        self.communities = communities
        self.seed = seed
        self.strict = strict
        # See BridgeWidthTransformation: steer ONE pair's bridge through
        # time, or the aggregate bridge when None.
        self.communityPair = communityPair
        if communityPair is not None:
            i, j = communityPair
            self.name = f"Bridge Trend {i}-{j}"

    def propertyValue(self, x):
        ''' Property = OLS slope of the bridge-width series across
        snapshots (edges per step). Undefined (None) for fewer than two
        snapshots - a single graph has no trajectory. '''
        snapshots = _snapshots(x)
        if len(snapshots) < 2:
            return None
        widths = [len(interCommunityEdges(g, self.communities,
                                          self.communityPair))
                  for g in snapshots]
        slope, _ = np.polyfit(np.arange(len(widths)), widths, 1)
        return float(slope)

    def transformGraph(self, graph, delta):
        raise NotImplementedError(
            "BridgeTrendTransformation changes a trajectory across "
            "snapshots; it has no meaning for a single graph. Use it "
            "with TgapExplainer (temporal), not GraphExplainer.")

    def transform(self, temporalGraph, delta):
        # delta = -1 makes the recursion below divide by (1 + delta) = 0.
        # Previously that surfaced as a bare ZeroDivisionError from inside
        # the loop, which told the caller nothing about why. The value is
        # genuinely outside the transformation's domain - "scale the
        # trajectory by a factor of zero" has no meaning - so it is rejected
        # explicitly rather than repaired. This is a guard, NOT a change of
        # semantics: every other delta behaves exactly as before.
        if delta == -1:
            raise ValueError(
                "BridgeTrendTransformation is undefined at delta = -1: the "
                "backward recursion divides by (1 + delta), which is zero. "
                "Use a delta strictly greater than -1.")

        # 1. Read the current trajectory of the property.
        widths = [len(interCommunityEdges(g, self.communities,
                                          self.communityPair))
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
                g, self.communities, round(target[t]), rng,
                strict=self.strict, pair=self.communityPair))
        result.append(temporalGraph[-1].copy())
        return result
