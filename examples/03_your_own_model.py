'''
EXAMPLE 3 - Your own model.

A model, for TGAP, is anything with ONE method:

    predict(snapshots) -> a number

`snapshots` is a list of networkx graphs, oldest first. Inside predict you
can do anything: a formula, a scikit-learn model, a neural network. TGAP
never looks inside - it only calls predict.

Below is a tiny "risk score" model. Replace the body of predict with your
own logic and run:

    python examples/03_your_own_model.py
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import networkx as nx          # noqa: E402

from core import TemporalGraphModel, interCommunityEdges   # noqa: E402
from examples import toolkit   # noqa: E402

# ============================== PARAMETERS ==============================
RECENT = 2                 # how many latest snapshots the model looks at
TRANSFORMATIONS = ["bridge_width", "centralization", "density", "churn"]
DELTAS = [0.1, 0.25]
# ========================================================================


class FragmentationRisk(TemporalGraphModel):
    ''' A made-up risk score: high when the groups talk little to each other
    AND activity is concentrated on a few people, in the recent past. '''

    def __init__(self, communities, recent=2):
        self.communities = communities
        self.recent = recent

    def predict(self, snapshots):
        recent = snapshots[-self.recent:]
        score = 0.0
        for graph in recent:
            ties = max(graph.number_of_edges(), 1)
            crossShare = len(interCommunityEdges(graph, self.communities)) \
                / ties
            degrees = [d for _, d in graph.degree()]
            concentration = max(degrees) / max(sum(degrees), 1)
            score += (1 - crossShare) + 5 * concentration
        return score / len(recent)


def main():
    snapshots, communities = toolkit.syntheticGraph(bridgeDecay=1)
    myModel = FragmentationRisk(communities, recent=RECENT)
    print("Your model: FragmentationRisk (looks at the last {0} "
          "snapshots)".format(RECENT))
    toolkit.explainAndSave(
        "03_your_own_model", myModel,
        toolkit.transformations(TRANSFORMATIONS, communities),
        snapshots, communities, deltas=DELTAS)
    print("  Read it as: 'if the past had had 10% more <concept>, the risk "
          "score would move by <impact> per unit of change'.")
    _ = nx                      # networkx is there for your own predict()


if __name__ == "__main__":
    main()
