''' The concept TGAP changes. '''
import random

from core import TemporalGraphTransformation


class NewcomerOnboarding(TemporalGraphTransformation):
    ''' Share of people who take part (have at least one tie).

    delta > 0: quiet people get a first tie to an active contributor who is
               not one of the two busiest people (onboarding through the
               community, not through the maintainers);
    delta < 0: the least active participants drop out (lose their ties). '''

    name = "Newcomer Onboarding"
    preservesEdgeCount = False     # ties are added or removed: said honestly

    def __init__(self, groups=None, seed=42):
        self.seed = seed

    def propertyValue(self, snapshots):
        snapshots = snapshots if isinstance(snapshots, list) else [snapshots]
        return sum(sum(1 for n in g if g.degree(n) > 0) / max(len(g), 1)
                   for g in snapshots) / len(snapshots)

    def transformGraph(self, graph, delta):
        g = graph.copy()
        rng = random.Random(self.seed)
        active = sorted((n for n in g if g.degree(n) > 0),
                        key=lambda n: (g.degree(n), str(n)))
        quiet = sorted(str(n) for n in g if g.degree(n) == 0)
        k = max(1, round(abs(delta) * len(active))) if active else 0
        if delta > 0 and quiet and len(active) > 2:
            mentors = active[:-2]              # everyone but the two busiest
            for person in quiet[:k]:
                g.add_edge(person, mentors[rng.randrange(len(mentors))])
        elif delta < 0:
            for person in active[:k]:
                g.remove_edges_from(list(g.edges(person)))
        return g
