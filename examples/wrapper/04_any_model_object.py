'''
WRAPPER 4 - A model that is a trained object (scikit-learn style).

    python examples/wrapper/04_any_model_object.py

Real models are usually objects that were trained on data. Hand the object to
the wrapper: if it has a  predict  method that accepts the snapshots, that is
all TGAP needs. Below, a tiny model "trained" on the data to forecast the
number of ties between the groups; replace it with your own (a scikit-learn pipeline, a
PyTorch module wrapped in a class, ...). Only the method name matters.

If your library wants a different input (a feature vector, a tensor), do the
conversion INSIDE predict - that is the one place where graph meets model.

Results: output/examples/wrapper_04_any_model_object/
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import numpy as np                             # noqa: E402

from core import interCommunityEdges           # noqa: E402
from tgap_wrapper import Wrapper               # noqa: E402


class CrossTieForecaster(object):
    ''' A least-squares line through the number of ties between the groups
    in the last `window` snapshots, extended one step. '''

    def __init__(self, groups, window=4):
        self.groups = groups
        self.window = window

    def features(self, snapshots):               # graphs -> numbers
        return [len(interCommunityEdges(g, self.groups))
                for g in snapshots[-self.window:]]

    def predict(self, snapshots):                 # numbers -> one number
        y = self.features(snapshots)
        slope, intercept = np.polyfit(range(len(y)), y, 1)
        return float(intercept + slope * len(y))


w = Wrapper.synthetic("wrapper_04_any_model_object", bridgeDecay=1)
w.model(CrossTieForecaster(w.groups))           # an object with .predict
w.concept(["bridge_width", "density", "bridge_trend"])
w.explain()
