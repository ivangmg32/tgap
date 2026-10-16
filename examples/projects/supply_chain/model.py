''' The model TGAP explains. '''
import networkx as nx

from core import TemporalGraphModel


class DisruptionExposure(TemporalGraphModel):
    ''' Share of trading companies cut off from the main network if the
    most connected company in the latest snapshot fails. '''

    def __init__(self, regions=None):
        pass

    def predict(self, snapshots):
        graph = snapshots[-1].copy()
        trading = [n for n in graph if graph.degree(n) > 0]
        if len(trading) < 3:
            return 0.0
        hub = max(sorted(trading, key=str), key=graph.degree)
        graph.remove_node(hub)
        graph.remove_nodes_from([n for n in list(graph)
                                 if n not in trading])
        largest = max((len(c) for c in nx.connected_components(graph)),
                      default=0)
        return 1 - largest / (len(trading) - 1)
