''' The model TGAP explains. '''
import numpy as np

from core import TemporalGraphModel, interCommunityEdges


class ContagionForecast(TemporalGraphModel):
    ''' Next window's share of strong co-movements that CROSS sectors -
    the channel through which a shock in one sector spreads to another.
    Forecast = the average share over the last `recent` windows ("the next
    window will look like the recent past"). '''

    def __init__(self, sectors, recent=4):
        self.sectors = sectors
        self.recent = recent

    def predict(self, snapshots):
        shares = [len(interCommunityEdges(g, self.sectors))
                  / max(g.number_of_edges(), 1)
                  for g in snapshots[-self.recent:]]
        return float(np.mean(shares))
