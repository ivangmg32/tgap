''' The concept TGAP changes. '''
import random

from core import TemporalGraphTransformation, asPartition


class SwingVoters(TemporalGraphTransformation):
    ''' Share of members who agree with someone in BOTH blocs.

    delta > 0: members who agree only within their bloc gain one agreement
               with a member of the other bloc;
    delta < 0: swing voters lose their agreements across the divide. '''

    name = "Swing Voters"
    preservesEdgeCount = False

    def __init__(self, blocs, seed=42):
        self.blocs = asPartition(blocs)
        self.seed = seed

    def _swing(self, g, n):
        own = self.blocs.communityOf(n)
        sides = {self.blocs.communityOf(m) == own for m in g[n]}
        return sides == {True, False}

    def propertyValue(self, snapshots):
        snapshots = snapshots if isinstance(snapshots, list) else [snapshots]
        return sum(sum(1 for n in g if self._swing(g, n)) / max(len(g), 1)
                   for g in snapshots) / len(snapshots)

    def transformGraph(self, graph, delta):
        g = graph.copy()
        rng = random.Random(self.seed)
        swing = sorted(str(n) for n in g if self._swing(g, n))
        loyal = sorted(str(n) for n in g if g.degree(n) > 0
                       and not self._swing(g, n))
        k = max(1, round(abs(delta) * max(len(swing), 1)))
        if delta > 0:
            for member in loyal[:k]:
                other = self.blocs[1 - self.blocs.communityOf(member)] \
                    if len(self.blocs) == 2 else set(g) - set(
                        self.blocs[self.blocs.communityOf(member)])
                choices = sorted(str(m) for m in other
                                 if not g.has_edge(member, m))
                if choices:
                    g.add_edge(member, choices[rng.randrange(len(choices))])
        elif delta < 0:
            for member in swing[:k]:
                g.remove_edges_from([(member, m) for m in list(g[member])
                                     if not self.blocs.sameCommunity(member,
                                                                     m)])
        return g
