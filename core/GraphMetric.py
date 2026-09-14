'''
Metrics: functions that summarize a graph as one number.

The base class Metric is the interface agreed in the scaffolding:
    measure(graph) -> float

Metrics play two roles in TGAP:
1. As the QUANTITY BEING PREDICTED by a TemporalGraphModel
   (e.g. "predict next quarter's bridge width").
2. As a KNOWN-TRUTH model via MetricGraphModel, to validate the explainer.

The concrete metrics below implement the candidate ecosystem-health
measures from CATALYST objective O3 (bridge width / redundancy,
centralization, cohesion), in their simplest defensible form.
'''

import networkx as nx

from .Communities import detectTwoCommunities, interCommunityEdges


class Metric:
    ''' For measuring the impact on the model output on a temporal graph,
    programmers and the framework will use this wrapper. '''

    def measure(self, graph):
        ''' Return a numerical value measuring a given graph.
        This must be overridden by the implementations. '''
        raise NotImplementedError("'measure' method should be implemented")


class DensityMetric(Metric):
    ''' Density = fraction of possible edges that actually exist (0..1).
    The simplest global measure of "how connected" a graph is. '''

    def measure(self, graph):
        return nx.density(graph)


class DegreeCentralizationMetric(Metric):
    ''' Freeman degree centralization (0..1).

    Intuition: how star-like is the graph?
      0 = perfectly egalitarian (everyone has the same number of ties)
      1 = a pure star (one hub holds all the ties)

    High centralization is a CATALYST risk signal: power/activity
    concentrated in one actor means a single point of failure
    (the "coordinator burnout" scenario from the proposal).

    Formula: sum over nodes of (maxDegree - degree_i), divided by the
    maximum this sum could take in any graph of the same size, which is
    (n-1)*(n-2) for an undirected graph. '''

    def measure(self, graph):
        n = graph.number_of_nodes()
        if n < 3:
            return 0.0  # centralization is undefined/trivial below 3 nodes
        degrees = [d for _, d in graph.degree()]
        maxDegree = max(degrees)
        return sum(maxDegree - d for d in degrees) / ((n - 1) * (n - 2))


class BridgeWidthMetric(Metric):
    ''' The width of the bridge between two communities = the number of
    edges crossing between them. This is the most direct operationalization
    of the CATALYST "wide bridge" concept: each crossing edge is one
    redundant tie, and the count is how many ties must fail before the
    two communities disconnect (along this partition).

    communities: optional (setA, setB) partition. Pass it explicitly for
    real experiments; if None, it is auto-detected per call (convenient
    but slower and less stable - see Communities.py). '''

    def __init__(self, communities=None):
        self.communities = communities

    def measure(self, graph):
        communities = self.communities
        if communities is None:
            communities = detectTwoCommunities(graph)
        return float(len(interCommunityEdges(graph, communities)))


class ClusteringMetric(Metric):
    ''' Average clustering coefficient (0..1): the probability that two
    of a node's neighbors are themselves connected ("my friends know
    each other"), averaged over nodes.

    In TGAP this is primarily a LEAKAGE PROBE: no transformation targets
    clustering, so movement in this metric under a transformation is a
    measured, unintended side effect - exactly what the concept-
    independence analysis needs to quantify. '''

    def measure(self, graph):
        if graph.number_of_nodes() == 0:
            return 0.0
        return float(nx.average_clustering(graph))


class CohesionMetric(Metric):
    ''' Cohesion = algebraic connectivity (the "Fiedler value").

    Intuition: how hard is it to cut the graph into two pieces?
      0        = already disconnected
      small    = a thin bottleneck exists somewhere (fragile!)
      larger   = well-knit, robust to edge failures

    This is a classic robustness measure from spectral graph theory and a
    natural single-number proxy for "ecosystem cohesion". It is also
    sensitive to exactly the thing CATALYST cares about: a graph held
    together by ONE narrow bridge has near-zero algebraic connectivity
    even if both sides are internally dense.

    seed: networkx computes this value with a RANDOMIZED eigensolver;
    left unseeded, the same graph can yield slightly different numbers
    on each call, which would break the STABILITY of the explanations
    (same input, same explanation). We therefore always pass a fixed
    seed. '''

    def __init__(self, seed=42):
        self.seed = seed

    def measure(self, graph):
        # A disconnected graph has, by definition, zero cohesion.
        # (networkx would raise an error, so we check first.)
        if graph.number_of_nodes() < 2 or not nx.is_connected(graph):
            return 0.0
        return float(nx.algebraic_connectivity(graph, seed=self.seed))
