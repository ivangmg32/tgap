'''
EXAMPLE 4 - Your own concept (a transformation).

A transformation tells TGAP how to change ONE human-meaningful property of
the graph by a controlled amount `delta` (0.1 = +10 %, -0.1 = -10 %).
You write three things:

    name                        a label for the result
    propertyValue(snapshots)    MEASURE the concept (one number)
    transformGraph(graph, delta)   CHANGE it in one snapshot (return a copy)

TGAP applies transformGraph to every snapshot, measures how far the
property really moved, and reports how much the model's prediction moved.
Nothing in core/ needs editing: your class is simply put in the list.

Here: "Triangle Closing" - how often friends of friends are friends.

    python examples/04_your_own_transformation.py
'''
import os
import random
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import networkx as nx          # noqa: E402

from core import (ClusteringMetric, TemporalGraphTransformation,   # noqa: E402
                  TrendTemporalModel)
from examples import toolkit   # noqa: E402

# ============================== PARAMETERS ==============================
DELTAS = [0.1, 0.25]
ALSO_COMPARE_WITH = ["density", "bridge_width"]    # built-in concepts
# ========================================================================


class TriangleClosing(TemporalGraphTransformation):
    ''' delta > 0: introduce friends of friends (close open triangles).
        delta < 0: break ties that sit inside triangles. '''

    name = "Triangle Closing"
    preservesEdgeCount = False     # we add / remove ties: say so honestly

    def __init__(self, seed=42):
        self.seed = seed

    def propertyValue(self, snapshots):
        snapshots = snapshots if isinstance(snapshots, list) else [snapshots]
        return sum(nx.average_clustering(g) for g in snapshots) \
            / len(snapshots)

    def transformGraph(self, graph, delta):
        g = graph.copy()                       # never change the input
        rng = random.Random(self.seed)         # same input -> same output
        howMany = round(abs(delta) * g.number_of_edges())
        if delta > 0:
            openPairs = sorted({tuple(sorted((a, b)))
                                for n in sorted(g) for a in g[n] for b in g[n]
                                if a != b and not g.has_edge(a, b)})
            g.add_edges_from(rng.sample(openPairs,
                                        min(howMany, len(openPairs))))
        elif delta < 0:
            inTriangles = sorted(tuple(sorted(e)) for e in g.edges()
                                 if set(g[e[0]]) & set(g[e[1]]))
            g.remove_edges_from(rng.sample(inTriangles,
                                           min(howMany, len(inTriangles))))
        return g


def main():
    # STEP 1 - some data
    toolkit.step(1, 4, "Building a made-up temporal graph")
    snapshots, communities = toolkit.syntheticGraph()

    # STEP 2 - try YOUR concept on its own first
    mine = TriangleClosing()
    before = mine.propertyValue(snapshots)
    after = mine.propertyValue(mine.transform(snapshots, 0.25))
    toolkit.step(2, 4, "Your concept '{0}': {1:.3f} -> {2:.3f} after a +25% "
                 "nudge".format(mine.name, before, after))

    # STEP 3 - a model that can react to it
    toolkit.step(3, 4, "Model: trend of the clustering coefficient")
    model = TrendTemporalModel(ClusteringMetric())

    # STEP 4 - explain: your concept next to built-in ones
    toolkit.step(4, 4, "Explaining: {0} + {1}".format(
        mine.name, ", ".join(ALSO_COMPARE_WITH)))
    concepts = [mine] + toolkit.transformations(ALSO_COMPARE_WITH,
                                                communities)
    toolkit.explainAndSave("04_your_own_transformation", model, concepts,
                           snapshots, communities, deltas=DELTAS)

if __name__ == "__main__":
    main()
