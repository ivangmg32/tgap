'''
WRAPPER 3 - Your own concept, as a plain function.

    python examples/wrapper/03_my_concept.py

A concept is "something about the graph you can turn up or down". You write
how to TURN IT in one snapshot - change(graph, delta) - and, ideally, how to
MEASURE it. delta is a ratio: +0.1 = "10% more of it", -0.1 = "10% less".

Here the concept is "Triangle Closing": friends of friends becoming friends.

Results: output/examples/wrapper_03_my_concept/
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import networkx as nx                          # noqa: E402

from tgap_wrapper import Wrapper               # noqa: E402

w = Wrapper.synthetic("wrapper_03_my_concept")
w.model("trend_clustering")


@w.concept(measure=nx.average_clustering, keepsEdgeCount=False)
def triangle_closing(graph, delta, rng):
    ''' delta > 0: introduce friends of friends. delta < 0: break ties that
    sit inside triangles. `graph` is already a copy - edit it freely;
    `rng` is a seeded random.Random, so results are repeatable. '''
    howMany = round(abs(delta) * graph.number_of_edges())
    if delta > 0:
        pairs = sorted({tuple(sorted((a, b))) for n in sorted(graph)
                        for a in graph[n] for b in graph[n]
                        if a != b and not graph.has_edge(a, b)})
        graph.add_edges_from(rng.sample(pairs, min(howMany, len(pairs))))
    else:
        inside = sorted(tuple(sorted(e)) for e in graph.edges()
                        if set(graph[e[0]]) & set(graph[e[1]]))
        graph.remove_edges_from(rng.sample(inside, min(howMany, len(inside))))


w.concept("density")                            # compare with a built-in
w.explain()
