''' The model TGAP explains. '''
from core import TemporalGraphModel


class BusFactorRisk(TemporalGraphModel):
    ''' Share of all ties in the latest snapshot that touch the two most
    connected people (0 = spread out, 1 = everything runs through two). '''

    def __init__(self, groups=None, top=2):
        self.top = top

    def predict(self, snapshots):
        graph = snapshots[-1]
        if graph.number_of_edges() == 0:
            return 0.0
        leaders = sorted(graph, key=lambda n: (-graph.degree(n), str(n)))
        leaders = set(leaders[:self.top])
        touching = sum(1 for u, v in graph.edges()
                       if u in leaders or v in leaders)
        return touching / graph.number_of_edges()
