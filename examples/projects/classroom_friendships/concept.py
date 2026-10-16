''' The concept TGAP changes. '''
import random

from core import TemporalGraphTransformation, asPartition


class IsolatedStudents(TemporalGraphTransformation):
    ''' Average number of students without any tie.

    delta > 0: the least connected students lose their ties;
    delta < 0: isolated students are given one buddy in their own class. '''

    name = "Isolated Students"
    preservesEdgeCount = False
    # The count can legitimately be 0 in a snapshot, so the achieved change is
    # measured in students, not as a percentage.
    deltaMode = "absolute"

    def __init__(self, classes, seed=42):
        self.classes = asPartition(classes)
        self.seed = seed

    def propertyValue(self, snapshots):
        snapshots = snapshots if isinstance(snapshots, list) else [snapshots]
        return sum(sum(1 for n in g if g.degree(n) == 0)
                   for g in snapshots) / len(snapshots)

    def transformGraph(self, graph, delta):
        g = graph.copy()
        rng = random.Random(self.seed)
        k = max(1, round(abs(delta) * len(g) / 4))
        if delta > 0:
            weakest = sorted((n for n in g if g.degree(n) > 0),
                             key=lambda n: (g.degree(n), str(n)))
            for student in weakest[:k]:
                g.remove_edges_from(list(g.edges(student)))
        elif delta < 0:
            alone = sorted(str(n) for n in g if g.degree(n) == 0)
            for student in alone[:k]:
                own = self.classes[self.classes.communityOf(student)]
                buddies = sorted(str(m) for m in own if m != student)
                g.add_edge(student, buddies[rng.randrange(len(buddies))])
        return g
