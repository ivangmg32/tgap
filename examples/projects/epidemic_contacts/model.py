''' The model TGAP explains. '''
import networkx as nx

from core import TemporalGraphModel


class OutbreakReach(TemporalGraphModel):
    ''' Share of pupils in the largest connected group of contacts,
    averaged over the latest `recent` snapshots. '''

    def __init__(self, schools=None, recent=2):
        self.recent = recent

    def predict(self, snapshots):
        shares = []
        for graph in snapshots[-self.recent:]:
            largest = max((len(c) for c in nx.connected_components(graph)),
                          default=0)
            shares.append(largest / max(graph.number_of_nodes(), 1))
        return sum(shares) / len(shares)
