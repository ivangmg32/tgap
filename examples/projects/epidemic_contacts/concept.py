''' The concept TGAP changes. '''
import random

from core import TemporalGraphTransformation, asPartition


class SuperSpreaders(TemporalGraphTransformation):
    ''' Share of contacts that involve the most connected 10% of pupils.

    delta > 0: contacts are moved TO those pupils;
    delta < 0: contacts are moved AWAY from them to the least connected
               pupil of the same school.
    Moving one end of a contact within the same school keeps both the number
    of contacts and the number of contacts across schools unchanged. '''

    name = "Super-Spreaders"
    preservesEdgeCount = True

    def __init__(self, schools, seed=42, top=0.1):
        self.schools = asPartition(schools)
        self.seed = seed
        self.top = top

    def _spreaders(self, g):
        ranked = sorted(g, key=lambda n: (-g.degree(n), str(n)))
        return set(ranked[:max(1, round(self.top * len(ranked)))])

    def propertyValue(self, snapshots):
        snapshots = snapshots if isinstance(snapshots, list) else [snapshots]
        shares = []
        for g in snapshots:
            top = self._spreaders(g)
            shares.append(sum(1 for u, v in g.edges() if u in top or v in top)
                          / max(g.number_of_edges(), 1))
        return sum(shares) / len(shares)

    def transformGraph(self, graph, delta):
        g = graph.copy()
        rng = random.Random(self.seed)
        top = self._spreaders(g)
        k = round(abs(delta) * g.number_of_edges())
        for _ in range(k):
            if delta > 0:
                # a contact between two ordinary pupils: one end moves to a
                # spreader of the same school
                moves = [(u, v, s) for u, v in sorted(g.edges())
                         if u not in top and v not in top
                         for s in sorted(top, key=str)
                         if self.schools.sameCommunity(u, s)
                         and not g.has_edge(s, v)]
                if not moves:
                    break
                u, v, s = moves[rng.randrange(len(moves))]
                g.remove_edge(u, v)
                g.add_edge(s, v)
            else:
                moves = []
                for s in sorted(top, key=str):
                    school = self.schools[self.schools.communityOf(s)]
                    quiet = sorted((p for p in school if p not in top),
                                   key=lambda p: (g.degree(p), str(p)))
                    for v in sorted(g[s], key=str):
                        for q in quiet:
                            if q != v and not g.has_edge(q, v):
                                moves.append((s, v, q))
                                break
                if not moves:
                    break
                s, v, q = moves[rng.randrange(len(moves))]
                g.remove_edge(s, v)
                g.add_edge(q, v)
        return g
