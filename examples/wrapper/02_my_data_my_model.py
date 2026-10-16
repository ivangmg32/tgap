'''
WRAPPER 2 - Your data and your model.

    python examples/wrapper/02_my_data_my_model.py

DATA   a CSV of "who, with whom, when" and a CSV of "who belongs to which group"
MODEL  one ordinary function: snapshots (list of graphs) -> one number
       Put ANY model in it - a formula, scikit-learn, PyTorch. The wrapper
       only calls  predict(snapshots)  and expects a number back.

Results: output/examples/wrapper_02_my_data_my_model/
'''
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from core import interCommunityEdges           # noqa: E402
from tgap_wrapper import Wrapper               # noqa: E402

DATA = os.path.join(os.path.dirname(HERE), "data")

w = Wrapper.fromCsv("wrapper_02_my_data_my_model",
                    edges=os.path.join(DATA, "sample_edges.csv"),
                    groups=os.path.join(DATA, "sample_groups.csv"),
                    snapshots=6)


@w.model                                        # <- this line is all it takes
def next_cross_team_ties(snapshots):
    ''' Predicts how many ties will cross between the groups in the next
    snapshot: the latest count plus the average change per snapshot. '''
    counts = [len(interCommunityEdges(g, w.groups)) for g in snapshots]
    return counts[-1] + (counts[-1] - counts[0]) / (len(counts) - 1)


w.concept(["bridge_width", "density", "churn"])
w.explain()
