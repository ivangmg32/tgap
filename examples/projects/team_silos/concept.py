''' The concept TGAP changes. '''
import random

from core import TemporalGraphTransformation, asPartition, interCommunityEdges


class LiaisonDependence(TemporalGraphTransformation):
    ''' The share of cross-team ties that go through the busiest liaison.

    delta > 0: cross-team ties are handed TO the liaison (one endpoint is
               moved to the liaison, on the same team);
    delta < 0: the liaison hands ties to the least-connected teammate.
    The number of ties, and of cross-team ties, never changes - only WHO
    carries them. '''

    name = "Liaison Dependence"
    preservesEdgeCount = True

    def __init__(self, teams, seed=42):
        self.teams = asPartition(teams)
        self.seed = seed

    def _liaison(self, graph):
        counts = {}
        for u, v in interCommunityEdges(graph, self.teams):
            counts[u] = counts.get(u, 0) + 1
            counts[v] = counts.get(v, 0) + 1
        return max(sorted(counts), key=counts.get) if counts else None, counts

    def propertyValue(self, snapshots):
        snapshots = snapshots if isinstance(snapshots, list) else [snapshots]
        shares = []
        for graph in snapshots:
            liaison, counts = self._liaison(graph)
            cross = sum(counts.values()) / 2
            shares.append(counts[liaison] / cross if liaison else 0.0)
        return sum(shares) / len(shares)

    def transformGraph(self, graph, delta):
        g = graph.copy()                       # never change the input
        rng = random.Random(self.seed)         # same input -> same output
        k = round(abs(delta) * len(interCommunityEdges(g, self.teams)))
        for _ in range(k):
            # Re-find the busiest liaison at EVERY step: when several people
            # are tied at the top, handing away one tie from a fixed person
            # would leave the maximum - the measured property - unchanged.
            liaison, counts = self._liaison(g)
            if liaison is None:
                break
            team = self.teams[self.teams.communityOf(liaison)]
            if delta > 0:
                # a cross-team tie held by a teammate moves to the liaison
                movable = sorted(
                    (a, b) if a in team else (b, a)
                    for a, b in interCommunityEdges(g, self.teams)
                    if liaison not in (a, b)
                    and not g.has_edge(liaison, b if a in team else a))
                if not movable:
                    break
                mine, other = movable[rng.randrange(len(movable))]
                g.remove_edge(mine, other)
                g.add_edge(liaison, other)
            else:
                # the liaison hands one tie to the quietest teammate
                options = [(other, m) for other in sorted(g[liaison])
                           if other not in team
                           for m in sorted(team, key=lambda p: (
                               counts.get(p, 0), p))
                           if m != liaison and not g.has_edge(m, other)]
                if not options:
                    break
                other, quiet = options[0]
                g.remove_edge(liaison, other)
                g.add_edge(quiet, other)
        return g
