"""Starter skeleton and worked examples for writing a custom TGAP
transformation in the Guided User Study. Every sample is checked by
tests/test_guided.py: it must pass the restricted interpreter and run."""

SKELETON = '''from core import TemporalGraphTransformation
import networkx as nx

class MyConcept(TemporalGraphTransformation):
    # 1) A short, unique name. It appears in every chart.
    name = "My concept"

    # 2) How the achieved change is measured:
    #    "relative" -> (after - before) / |before|   (e.g. +10%)
    #    "absolute" -> after - before                 (e.g. +3 edges)
    deltaMode = "relative"

    # 3) Be honest: does transformGraph keep the number of edges?
    #    TGAP checks this promise and marks broken runs as invalid.
    preservesEdgeCount = False

    def propertyValue(self, x):
        # 4) MEASURE your concept. x is one graph or a list of snapshots.
        #    Return one number. Here: average number of edges.
        graphs = x if isinstance(x, list) else [x]
        return sum(g.number_of_edges() for g in graphs) / len(graphs)

    def transformGraph(self, graph, delta):
        # 5) CHANGE your concept on one snapshot.
        #    delta > 0 means "increase", delta < 0 means "decrease";
        #    abs(delta) is the requested size (0.1 = 10%).
        #    Always start from a copy - never edit the input graph.
        g = graph.copy()
        # TODO: add or remove edges here
        return g
'''

SAMPLES = [
    dict(id='thin_or_thicken', title='Thin or thicken the network', level='Beginner',
         idea='Removes a share of edges (decrease) or adds edges between unconnected pairs (increase). The measured concept is the average edge count.',
         code='''from core import TemporalGraphTransformation
import networkx as nx

class ThinOrThicken(TemporalGraphTransformation):
    name = "Edge volume"
    deltaMode = "relative"
    preservesEdgeCount = False

    def propertyValue(self, x):
        graphs = x if isinstance(x, list) else [x]
        return sum(g.number_of_edges() for g in graphs) / len(graphs)

    def transformGraph(self, graph, delta):
        g = graph.copy()
        k = int(round(abs(delta) * g.number_of_edges()))
        if delta < 0:
            edges = sorted(g.edges())
            for u, v in edges[:k]:
                g.remove_edge(u, v)
        else:
            nodes = sorted(g.nodes())
            added = 0
            for u in nodes:
                for v in nodes:
                    if added < k and u < v and not g.has_edge(u, v):
                        g.add_edge(u, v)
                        added = added + 1
        return g
'''),
    dict(id='calm_the_hub', title='Calm the busiest node', level='Intermediate',
         idea='Finds the node with the most ties, then removes a share of its edges (decrease) or connects it to new nodes (increase). The measured concept is the largest degree, averaged over snapshots.',
         code='''from core import TemporalGraphTransformation
import networkx as nx

class CalmTheHub(TemporalGraphTransformation):
    name = "Hub degree"
    deltaMode = "relative"
    preservesEdgeCount = False

    def propertyValue(self, x):
        graphs = x if isinstance(x, list) else [x]
        return sum(max([d for n, d in g.degree()] + [0]) for g in graphs) / len(graphs)

    def transformGraph(self, graph, delta):
        g = graph.copy()
        if g.number_of_edges() == 0:
            return g
        ranked = sorted([(d, n) for n, d in g.degree()])
        hub = ranked[-1][1]
        ties = sorted(g.neighbors(hub))
        k = max(1, int(round(abs(delta) * len(ties))))
        if delta < 0:
            for other in ties[:k]:
                g.remove_edge(hub, other)
        else:
            strangers = [n for n in sorted(g.nodes()) if n != hub and not g.has_edge(hub, n)]
            for other in strangers[:k]:
                g.add_edge(hub, other)
        return g
'''),
    dict(id='fade_the_past', title='Fade the past (temporal)', level='Advanced',
         idea='A temporal concept: it removes past edges (decrease) or brings present ties into the past (increase) in every snapshot except the latest one, so the present stays fixed and only history changes. Compare a present-only model with a forecast model!',
         code='''from core import TemporalGraphTransformation
import networkx as nx

class FadeThePast(TemporalGraphTransformation):
    name = "Past activity"
    deltaMode = "relative"
    preservesEdgeCount = False

    def propertyValue(self, x):
        graphs = x if isinstance(x, list) else [x]
        past = graphs[:-1] if len(graphs) > 1 else graphs
        return sum(g.number_of_edges() for g in past) / len(past)

    def transform(self, graphs, delta):
        out = []
        for i, graph in enumerate(graphs):
            g = graph.copy()
            if i < len(graphs) - 1:
                k = int(round(abs(delta) * g.number_of_edges()))
                if delta < 0:
                    for u, v in sorted(g.edges())[:k]:
                        g.remove_edge(u, v)
                else:
                    # bring forward ties that exist in the present but not yet in the past
                    present = sorted(graphs[-1].edges())
                    new = [(u, v) for u, v in present if not g.has_edge(u, v)]
                    for u, v in new[:k]:
                        g.add_edge(u, v)
            out.append(g)
        return out
'''),
]

API_REFERENCE = [
    ('Graph basics', ['g = graph.copy()', 'g.nodes()  /  g.edges()', 'g.number_of_nodes()  /  g.number_of_edges()', 'g.degree()  /  g.degree(node)', 'g.neighbors(node)']),
    ('Editing', ['g.has_edge(u, v)', 'g.add_edge(u, v)  /  g.add_edges_from(list)', 'g.remove_edge(u, v)  /  g.remove_edges_from(list)']),
    ('NetworkX helpers', ['nx.density(g)', 'nx.average_clustering(g)', 'nx.isolates(g)', 'nx.number_of_selfloops(g)']),
    ('Python you can use', ['if / else, for loops, list/set/dict comprehensions', 'len sum min max abs round sorted range enumerate zip', 'int float list set tuple isinstance any all']),
    ('Not available', ['import (other than the two header lines), files, network', 'while loops, lambda, try/except, decorators', 'private attributes (names starting with _)']),
]

RULES = [
    'Return a new graph (or the same number of snapshots) - never edit the input.',
    'Keep every node; only add or remove edges, and no self-loops.',
    'Use delta: positive = increase, negative = decrease, abs(delta) = size.',
    'Give the class a unique name that differs from the built-in concepts.',
    'Set preservesEdgeCount truthfully; broken promises make a run invalid.',
]
