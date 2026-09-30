'''
A complete, runnable example of a USER-DEFINED TGAP transformation.

    python -m examples.MyCustomTransformation

THE POINT OF THIS FILE
    Nothing in core/ knows this class exists. It lives outside the package,
    it is not registered anywhere, and no core file was edited to make it
    work. That is the whole extensibility claim: a researcher invents a new
    graph concept, implements it here, passes it to TgapExplainer, and gets
    an explanation.

    If you can read this file, you can write your own concept.

WHAT THE CONTRACT ACTUALLY REQUIRES
    Subclass core.TemporalGraphTransformation and provide:

      name              str   - labels the explanation row
      propertyValue(x)  float - MEASURE the concept you are changing
      transformGraph(graph, delta)  OR  transform(temporalGraph, delta)

    Everything else is optional and has a sane default:

      deltaMode           "relative" (default) or "absolute"
      preservesEdgeCount  True (default) - does this concept promise to keep
                          the total edge count fixed?

    Implement transformGraph for a STRUCTURAL concept (applied to each
    snapshot independently). Implement transform for a TEMPORAL concept
    (one that reshapes the trajectory itself, like BridgeTrend).

THE CONCEPT IMPLEMENTED HERE: "isolation"
    How many actors are completely disconnected in a snapshot?

    This is a genuine CATALYST question - an ecosystem where many members
    sit with no ties is fragile in a way a dense one is not - and it is not
    covered by any of the five built-in concepts. It is also a good example
    because it is NOT edge-count preserving, which shows how to declare that
    honestly rather than pretend otherwise.
'''

import random

import networkx as nx

from core import (
    BridgeWidthMetric, PersistenceTemporalModel, TemporalGraphTransformation,
    TgapExplainer, TrendTemporalModel, makeTemporalGraph,
)
from core.GraphMetric import DensityMetric


class IsolationTransformation(TemporalGraphTransformation):
    ''' Change how many actors are ISOLATED (have no ties at all).

    Property  : the number of degree-0 nodes, averaged over snapshots.
    Delta     : relative change of that count. delta=+0.5 means "make 50%
                more actors isolated"; delta=-0.5 means "reconnect half of
                the isolated actors".
    Mechanism : to ISOLATE a node, every one of its edges is removed. To
                RECONNECT an isolated node, it is joined to the
                highest-degree node that is not already a neighbour.
    Anchor    : the NODE SET is preserved, always. The edge count is NOT -
                see below.
    Feasibility: isolating needs non-isolated nodes to strip; reconnecting
                needs isolated nodes to attach. When the graph has neither,
                the transformation is a no-op and propertyValue reports an
                achieved change of 0, which TGAP records as `noop`.
    Limitations: stripping a high-degree node removes many edges at once, so
                the achieved change in OTHER properties (density in
                particular) can be large. That is leakage, and TGAP's
                leakage panel will show it - it is not hidden.

    Determinism: all choices are made from a generator seeded in __init__
                 and re-seeded on every call, so the same input always
                 yields the same output.
    '''

    name = "Isolation"

    # The concept IS a change in connectivity, and stripping a node's edges
    # necessarily changes the edge count. Declaring False here is what stops
    # core.Feasibility from reporting every run as an invariant violation -
    # the same declaration DensityTransformation makes, and for the same
    # reason. Getting this wrong is the most common mistake when writing a
    # new transformation.
    preservesEdgeCount = False

    def __init__(self, seed=42):
        self.seed = seed

    def propertyValue(self, x):
        ''' The concept, measured. TGAP divides the prediction change by the
        change in THIS number, so it must be the quantity the
        transformation actually manipulates - not a proxy for it. '''
        snapshots = x if isinstance(x, list) else [x]
        counts = [sum(1 for _, degree in g.degree() if degree == 0)
                  for g in snapshots]
        return float(sum(counts)) / len(counts)

    def transformGraph(self, graph, delta):
        ''' Structural concept: applied to each snapshot independently.
        Must return a NEW graph - never mutate the input, because the
        explainer still needs the original to compute the baseline. '''
        g = graph.copy()
        rng = random.Random(self.seed)

        isolated = sorted(n for n, degree in g.degree() if degree == 0)
        connected = sorted(n for n, degree in g.degree() if degree > 0)
        target = round(len(isolated) * (1 + delta))
        change = target - len(isolated)

        if change > 0 and connected:
            # ISOLATE: strip every edge from `change` connected nodes,
            # preferring the least connected so the damage is smallest.
            victims = sorted(connected, key=lambda n: (g.degree(n), n))
            for node in victims[:change]:
                g.remove_edges_from(list(g.edges(node)))
        elif change < 0 and isolated:
            # RECONNECT: attach isolated nodes to the current hub.
            for node in isolated[:-change]:
                others = sorted(n for n in g.nodes()
                                if n != node and not g.has_edge(node, n))
                if not others:
                    continue
                hub = max(others, key=lambda n: (g.degree(n), n))
                g.add_edge(node, hub)
        return g


def main():
    ''' Run TGAP with the custom concept beside two built-in ones.

    Note what is NOT here: no import from a registry, no decorator, no
    configuration file, no edit to core/. The transformation is simply an
    object in a list.
    '''
    snapshots, communities = makeTemporalGraph(
        nSnapshots=6, nPerCommunity=10, bridgeWidth=8, seed=1)

    # Make the example non-trivial: give some snapshots isolated actors, so
    # the concept has something to move.
    for index, graph in enumerate(snapshots[:-1]):
        for node in sorted(graph.nodes())[:index + 1]:
            graph.remove_edges_from(list(graph.edges(node)))

    from core import BridgeWidthTransformation, DensityTransformation

    transformations = [
        BridgeWidthTransformation(communities, seed=42),   # built in
        DensityTransformation(communities, seed=42),       # built in
        IsolationTransformation(seed=42),                  # YOURS
    ]

    model = TrendTemporalModel(DensityMetric())
    explainer = TgapExplainer(model, transformations, defaultDelta=0.5)

    print("=" * 66)
    print("TGAP with a user-defined transformation")
    print("=" * 66)
    print(f"  model        : trend of density over {len(snapshots)} snapshots")
    print(f"  isolated now : {IsolationTransformation().propertyValue(snapshots):.2f}"
          f" actors per snapshot (mean)")
    print()

    for record in explainer.explainDetailed(snapshots):
        mark = "  <- custom" if record["transformation"] == "Isolation" else ""
        print(f"  {record['label']:38s} impact {record['impact']:>10.4f}"
              f"   achieved {record['achievedDelta']:>7.3f}{mark}")

    print()
    print("  core/ was not modified to make this work.")


if __name__ == "__main__":
    main()
