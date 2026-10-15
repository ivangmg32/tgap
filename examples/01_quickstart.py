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
    snapshots, communities = toolkit.syntheticGraph(
        SNAPSHOTS, PEOPLE_PER_GROUP, BRIDGE_WIDTH, BRIDGE_DECAY, SEED)
    print("Model: {0} - {1}".format(MODEL, toolkit.MODELS[MODEL][0]))
    toolkit.explainAndSave(
        "01_quickstart",
        toolkit.model(MODEL, communities),
        toolkit.transformations(TRANSFORMATIONS, communities),
        snapshots, communities, deltas=DELTAS)


if __name__ == "__main__":
    main()
