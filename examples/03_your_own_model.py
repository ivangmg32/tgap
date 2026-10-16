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
    # STEP 1 - some data to try your model on
    toolkit.step(1, 3, "Building a made-up temporal graph whose groups "
                 "drift apart")
    snapshots, communities = toolkit.syntheticGraph(bridgeDecay=1)

    # STEP 2 - YOUR model (the class above)
    myModel = FragmentationRisk(communities, recent=RECENT)
    toolkit.step(2, 3, "Your model: FragmentationRisk (last {0} snapshots) "
                 "-> predicts {1:.3f}".format(RECENT,
                                              myModel.predict(snapshots)))

    # STEP 3 - explain it with built-in concepts
    toolkit.step(3, 3, "Explaining with: " + ", ".join(TRANSFORMATIONS))
    toolkit.explainAndSave(
        "03_your_own_model", myModel,
        toolkit.transformations(TRANSFORMATIONS, communities),
        snapshots, communities, deltas=DELTAS)
    _ = nx                      # networkx is there for your own predict()

if __name__ == "__main__":
    main()
