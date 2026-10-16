'''
EXAMPLE 1 - Quickstart: TGAP in 30 seconds.

A made-up temporal graph (two groups of people), a built-in model, and the
built-in concepts. Change any value in PARAMETERS and run again:

    python examples/01_quickstart.py

Outputs (CSV + PNG) go to output/examples/01_quickstart/.
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from examples import toolkit   # noqa: E402

# ============================== PARAMETERS ==============================
SNAPSHOTS = 6              # how many moments in time
PEOPLE_PER_GROUP = 10      # size of each of the two groups
BRIDGE_WIDTH = 8           # ties between the two groups
BRIDGE_DECAY = 0           # ties between groups lost per snapshot (0 = stable;
                           # try 1 with MODEL = "slope_bridge_width")
SEED = 42                  # change it to get a different random graph

# The model TGAP explains. One of:
#   persistence_bridge_width, trend_bridge_width, slope_bridge_width,
#   persistence_density, trend_density, persistence_centralization,
#   trend_clustering
MODEL = "trend_bridge_width"

# The concepts TGAP perturbs. Any of:
#   bridge_width, centralization, density, bridge_trend, churn
TRANSFORMATIONS = ["bridge_width", "centralization", "density",
                   "bridge_trend", "churn"]

DELTAS = [0.1, 0.25]       # size of the nudge: 0.1 = 10 %
# ========================================================================


def main():
    # STEP 1 - the data: a made-up temporal graph (two groups of people)
    toolkit.step(1, 4, "Building a made-up temporal graph: {0} snapshots, "
                 "two groups of {1} people".format(SNAPSHOTS, PEOPLE_PER_GROUP))
    snapshots, communities = toolkit.syntheticGraph(
        SNAPSHOTS, PEOPLE_PER_GROUP, BRIDGE_WIDTH, BRIDGE_DECAY, SEED)

    # STEP 2 - the model TGAP will explain
    toolkit.step(2, 4, "Model: {0} ({1})".format(MODEL,
                                                  toolkit.MODELS[MODEL][0]))
    model = toolkit.model(MODEL, communities)

    # STEP 3 - the concepts TGAP will nudge
    toolkit.step(3, 4, "Concepts to test: " + ", ".join(TRANSFORMATIONS))
    concepts = toolkit.transformations(TRANSFORMATIONS, communities)

    # STEP 4 - explain, print, and save CSV + PNG
    toolkit.step(4, 4, "Explaining")
    toolkit.explainAndSave("01_quickstart", model, concepts, snapshots,
                           communities, deltas=DELTAS)

if __name__ == "__main__":
    main()
