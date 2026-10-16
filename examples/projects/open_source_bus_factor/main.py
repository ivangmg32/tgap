'''
PROJECT - Bus factor in an open-source project.

A small open-source project: a few maintainers and a larger, shifting community of contributors.
A "bus factor risk" model says how much the project depends on its top two people.
TGAP asks whether onboarding more newcomers would lower that risk - or raise it.

    python examples/projects/open_source_bus_factor/main.py

Everything is written to output/ in this folder; start with TUTORIAL.md.
'''
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))

import pandas as pd                                          # noqa: E402

from examples import toolkit                                 # noqa: E402
from examples.projects.open_source_bus_factor.concept import NewcomerOnboarding         # noqa: E402
from examples.projects.open_source_bus_factor.data import makeData            # noqa: E402
from examples.projects.open_source_bus_factor.model import BusFactorRisk             # noqa: E402

# ============================== PARAMETERS ==============================
SNAPSHOTS = 8            # how many periods the time span is cut into
ALSO_TEST = ["centralization", "density"]   # built-in concepts to compare
DELTAS = [0.1, 0.25]
# ========================================================================


def main(output=None):
    output = output or os.path.join(HERE, "output")
    tutorial = toolkit.Tutorial(
        output, "Bus factor in an open-source project - a TGAP tutorial",
        intro="Would bringing more newcomers into the conversation make the project less dependent on its top maintainers?")

    # STEP 1 - the data
    toolkit.step(1, 4, "Loading the data")
    events, groups = makeData()
    snapshots = toolkit.loadEdgeList(events, snapshots=SNAPSHOTS)
    communities = toolkit.loadGroups(groups, snapshots=snapshots)
    frame = pd.read_csv(events)
    tutorial.section("Step 1 - The data (data.py)", (
        "`data/reviews.csv` holds **{0} code reviews and comments** between **{1} "
        "people** in {2} groups (`data/groups.csv`). TGAP cuts the time "
        "span into **{3} snapshots**; two people are tied in a snapshot "
        "when they reviewed or commented on each other's work.").format(
            len(frame), snapshots[0].number_of_nodes(), len(communities),
            SNAPSHOTS))
    tutorial.table(frame.head(5), "The first rows of data/reviews.csv")

    # STEP 2 - the model
    model = BusFactorRisk(communities)
    today = model.predict(snapshots)
    toolkit.step(2, 4, "Model: BusFactorRisk -> {0:.3f}".format(today))
    tutorial.section("Step 2 - The model (model.py)",
                     "`BusFactorRisk` is the share of all ties that touch the two most connected people in the latest snapshot. High means that if those two left, most of the collaboration would go with them.\n\nOn this data it says **{0:.3f}**."
                     .format(today))

    # STEP 3 - our own concept
    concept = NewcomerOnboarding(communities)
    before = concept.propertyValue(snapshots)
    after = concept.propertyValue(concept.transform(snapshots, 0.25))
    toolkit.step(3, 4, "Concept '{0}': {1:.3f} -> {2:.3f} after +25%"
                 .format(concept.name, before, after))
    tutorial.section("Step 3 - The concept (concept.py)", (
        "`NewcomerOnboarding` measures the share of people who take part at all (have at least one tie). Up: quiet people get a first tie to an active contributor who is NOT a top maintainer. Down: the least active people drop out.\n\nOn this data it measures **{0:.3f}**; nudged "
        "up by 25% it becomes **{1:.3f}**.").format(before, after))

    # STEP 4 - explain
    toolkit.step(4, 4, "Explaining")
    toolkit.explainAndSave(
        "open_source_bus_factor", model,
        [concept] + toolkit.transformations(ALSO_TEST, communities),
        snapshots, communities, deltas=DELTAS, folder=output,
        tutorial=tutorial, step="Step 4",
        modelDescription="how much the project depends on its two most connected people")


if __name__ == "__main__":
    main()
