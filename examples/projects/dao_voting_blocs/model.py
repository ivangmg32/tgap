''' The model TGAP explains. '''
from core import TemporalGraphModel, asPartition


class Polarization(TemporalGraphModel):
    ''' Within-bloc agreement density minus across-bloc agreement density,
    over the latest `recent` snapshots. '''

    def __init__(self, blocs, recent=2):
        self.blocs = asPartition(blocs)
        self.recent = recent

    def predict(self, snapshots):
        scores = []
        for graph in snapshots[-self.recent:]:
            inside = sum(1 for u, v in graph.edges()
                         if self.blocs.sameCommunity(u, v))
            across = graph.number_of_edges() - inside
            insidePairs = sum(len(b) * (len(b) - 1) / 2 for b in self.blocs)
            total = graph.number_of_nodes() * (graph.number_of_nodes() - 1) / 2
            acrossPairs = total - insidePairs
            scores.append(inside / max(insidePairs, 1)
                          - across / max(acrossPairs, 1))
        return sum(scores) / len(scores)
