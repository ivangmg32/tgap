''' The concept TGAP changes. '''
import random

from core import TemporalGraphTransformation, asPartition


class SectorDecoupling(TemporalGraphTransformation):
    ''' The share of strong co-movements that stay INSIDE a sector.

    delta > 0: cross-sector ties are rewired into ties inside a sector
               (sectors move more on their own - decoupling);
    delta < 0: ties inside sectors are rewired across sectors (coupling).
    The number of ties never changes: only which pairs move together.

    This is deliberately the mirror image of the built-in Bridge Width, so
    the tutorial can check that TGAP agrees with itself: their impacts on
    the same model should have OPPOSITE signs. '''

    name = "Sector Decoupling"
    preservesEdgeCount = True

    def __init__(self, sectors, seed=42):
        self.sectors = asPartition(sectors)
        self.seed = seed

    def _inside(self, g):
        return [(u, v) for u, v in g.edges()
                if self.sectors.sameCommunity(u, v)]

    def propertyValue(self, snapshots):
        snapshots = snapshots if isinstance(snapshots, list) else [snapshots]
        return sum(len(self._inside(g)) / max(g.number_of_edges(), 1)
                   for g in snapshots) / len(snapshots)

    def transformGraph(self, graph, delta):
        g = graph.copy()
        rng = random.Random(self.seed)
        inside = sorted(tuple(sorted(e)) for e in self._inside(g))
        across = sorted(tuple(sorted(e)) for e in g.edges()
                        if not self.sectors.sameCommunity(*e))
        k = round(abs(delta) * max(len(inside), 1))
        nodes = sorted(g)
        if delta > 0:
            free = [(a, b) for i, a in enumerate(nodes) for b in nodes[i + 1:]
                    if self.sectors.sameCommunity(a, b)
                    and not g.has_edge(a, b)]
            n = min(k, len(across), len(free))
            g.remove_edges_from(rng.sample(across, n))
            g.add_edges_from(rng.sample(free, n))
        elif delta < 0:
            free = [(a, b) for i, a in enumerate(nodes) for b in nodes[i + 1:]
                    if not self.sectors.sameCommunity(a, b)
                    and not g.has_edge(a, b)]
            n = min(k, len(inside), len(free))
            g.remove_edges_from(rng.sample(inside, n))
            g.add_edges_from(rng.sample(free, n))
        return g
