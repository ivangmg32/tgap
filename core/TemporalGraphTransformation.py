'''
Base class for transformations - the heart of the TGAP method.

A transformation changes ONE human-meaningful property of a graph by a
controlled amount `delta`, while keeping everything else as fixed as
possible. The explainer then measures how much the model's output moves.

This is the graph analogue of TSAP's transformVolatility and
transformTrendReverse, and it inherits TSAP's key design rule:

    TSAP anchor rule:  "keep the LAST VALUE of the series fixed", so any
                       change in the prediction comes from the SHAPE of
                       the curve, not from a different starting point.

    TGAP anchor rule:  "keep the NODE SET fixed, and where meaningful the
                       EDGE COUNT too", so any change in the prediction
                       comes from the STRUCTURE of the graph, not from a
                       bigger/smaller graph.

Every concrete transformation must document:
    1. What property it changes.
    2. What `delta` means for it (deltas are ratios: 0.1 = 10%).
    3. What it keeps fixed (its anchor).

Determinism: transformations that involve random choices (e.g. WHICH edge
to rewire) must draw them from a random generator seeded in __init__, and
re-seed it on every call. Same graph + same delta -> same transformed
graph, always. This guarantees the STABILITY of the explanations.
'''


class TemporalGraphTransformation:
    ''' Transform a temporal graph into another temporal graph with a
    property changed by delta. The higher |delta|, the bigger the change. '''

    # Human-readable property name, used in explanation labels and plots
    # (e.g. "Increase Bridge Width (10.0%)"). Override in subclasses.
    name = "Property"

    # How the ACHIEVED property change should be computed by the explainer:
    #   "relative": (pAfter - pBefore) / |pBefore|   (a ratio, like delta)
    #   "absolute": pAfter - pBefore                 (property's own units;
    #               used when pBefore can legitimately be 0, e.g. a slope)
    # See ExplainerBase.explainDetailed for how this feeds normalization.
    deltaMode = "relative"

    # Does this transformation DECLARE that it keeps the total edge count
    # fixed while changing its property? True for every transformation
    # whose anchor includes the edge budget (BridgeWidth, Centralization,
    # BridgeTrend, Churn). DensityTransformation overrides it to False,
    # because the edge count IS its property - changing it is the point,
    # not a violation.
    #
    # Read by core.Feasibility.declaresEdgeCountPreservation, so a
    # transformation states its own promise instead of being classified by
    # name or isinstance elsewhere in the code base.
    preservesEdgeCount = True

    def propertyValue(self, x):
        ''' Measure the scalar property this transformation changes, on an
        input x (a single graph OR a temporal graph - implementations must
        accept both, because both explainers use this).

        Purpose: graphs are DISCRETE, so a requested delta of 10% often
        realizes as a different actual change (6 bridges -> 7 is +16.7%).
        By measuring the property before and after, the explainer can
        normalize impacts by the ACHIEVED change instead of the requested
        one - which is exactly what TSAP's /|delta| means in the continuous
        world, restored for the discrete one.

        Return None if the property is not measurable for this input
        (e.g. a trajectory property on a single graph); the explainer then
        falls back to requested-delta normalization and flags it. '''
        return None

    def transformGraph(self, graph, delta):
        ''' Transform a SINGLE networkx.Graph snapshot, changing this
        transformation's property by ratio delta. Must return a NEW graph
        (never mutate the input - the explainer needs the original intact
        to compute the baseline prediction).
        This must be overridden by subclasses. '''
        raise NotImplementedError("'transformGraph' should be implemented")

    def transform(self, temporalGraph, delta):
        ''' Transform a temporal graph (list of snapshots) by applying the
        single-graph transformation to EVERY snapshot.

        Why every snapshot? The question we ask the model is counterfactual:
        "if the ecosystem's recent history had had 10% wider bridges, what
        would you predict?" - so the property must change consistently
        across the whole observed window, exactly as TSAP's volatility
        change applies to the whole series, not to one time point.

        NOTE - two kinds of transformation live under this base class:
        1. STRUCTURAL transformations (BridgeWidth, Centralization,
           Density) implement transformGraph and inherit this uniform
           over-time behavior.
        2. TEMPORAL transformations (BridgeTrend, Churn) change the
           TRAJECTORY itself - how the property evolves across snapshots.
           They override transform() directly, anchor the LAST snapshot
           (returned untouched, TSAP's "keep the last value fixed" rule
           applied to time), and leave transformGraph unimplemented
           because they have no single-graph meaning. '''
        return [self.transformGraph(g, delta) for g in temporalGraph]
