'''
PROJECT - Supply-chain resilience across two regions.

Suppliers and factories in two regions trade with each other over two years.
A "disruption exposure" model asks: if the busiest company failed, how much of the network would be cut off?
TGAP asks whether diversification - companies keeping a second trading partner - lowers that exposure.

    python examples/projects/supply_chain/main.py

Everything is written to output/ in this folder; start with TUTORIAL.md.
'''
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))

import pandas as pd                                          # noqa: E402

from examples import toolkit                                 # noqa: E402
from examples.projects.supply_chain.concept import SupplierDiversification         # noqa: E402
from examples.projects.supply_chain.data import makeData            # noqa: E402
from examples.projects.supply_chain.model import DisruptionExposure             # noqa: E402

# ============================== PARAMETERS ==============================
SNAPSHOTS = 8            # how many periods the time span is cut into
ALSO_TEST = ["centralization", "bridge_width"]   # built-in concepts to compare
DELTAS = [0.1, 0.25]
# ========================================================================


def main(output=None):
    output = output or os.path.join(HERE, "output")
    tutorial = toolkit.Tutorial(
        output, "Supply-chain resilience across two regions - a TGAP tutorial",
        intro="Does supplier diversification - every company keeping a backup trading partner - make the network less exposed to one company failing?")

    # STEP 1 - the data
    toolkit.step(1, 4, "Loading the data")
    events, groups = makeData()
    snapshots = toolkit.loadEdgeList(events, snapshots=SNAPSHOTS)
    communities = toolkit.loadGroups(groups, snapshots=snapshots)
    frame = pd.read_csv(events)
    tutorial.section("Step 1 - The data (data.py)", (
        "`data/orders.csv` holds **{0} orders** between **{1} "
        "companies** in {2} groups (`data/groups.csv`). TGAP cuts the time "
        "span into **{3} snapshots**; two companies are tied in a snapshot "
        "when they traded at least once.").format(
            len(frame), snapshots[0].number_of_nodes(), len(communities),
            SNAPSHOTS))
    tutorial.table(frame.head(5), "The first rows of data/orders.csv")

    # STEP 2 - the model
    model = DisruptionExposure(communities)
    today = model.predict(snapshots)
    toolkit.step(2, 4, "Model: DisruptionExposure -> {0:.3f}".format(today))
    tutorial.section("Step 2 - The model (model.py)",
                     "`DisruptionExposure` removes the most connected company from the latest snapshot and measures the share of the other trading companies that are no longer connected to the main network.\n\nOn this data it says **{0:.3f}**."
                     .format(today))

    # STEP 3 - our own concept
    concept = SupplierDiversification(communities)
    before = concept.propertyValue(snapshots)
    after = concept.propertyValue(concept.transform(snapshots, 0.25))
    toolkit.step(3, 4, "Concept '{0}': {1:.3f} -> {2:.3f} after +25%"
                 .format(concept.name, before, after))
    tutorial.section("Step 3 - The concept (concept.py)", (
        "`SupplierDiversification` is the share of trading companies that have at least TWO partners (a backup). Up: single-partner companies gain a second partner in their region. Down: companies with backups drop one partner.\n\nOn this data it measures **{0:.3f}**; nudged "
        "up by 25% it becomes **{1:.3f}**.").format(before, after))

    # STEP 4 - explain
    toolkit.step(4, 4, "Explaining")
    toolkit.explainAndSave(
        "supply_chain", model,
        [concept] + toolkit.transformations(ALSO_TEST, communities),
        snapshots, communities, deltas=DELTAS, folder=output,
        tutorial=tutorial, step="Step 4",
        modelDescription="the share of companies cut off if the busiest company fails")


if __name__ == "__main__":
    main()
