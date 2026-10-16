''' The model TGAP explains. '''
import numpy as np

from core import TemporalGraphModel


class LonelinessForecast(TemporalGraphModel):
    ''' Number of students with no tie, extrapolated one period ahead
    with a straight line through every snapshot. '''

    def __init__(self, classes=None):
        pass

    def predict(self, snapshots):
        counts = [sum(1 for n in g if g.degree(n) == 0) for g in snapshots]
        slope, intercept = np.polyfit(np.arange(len(counts)), counts, 1)
        return float(max(0.0, intercept + slope * len(counts)))
