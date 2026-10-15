'''
PROJECT - Super-spreaders in a contact network.

Contacts between pupils of two schools during one term.
An "outbreak reach" model estimates how large a share of pupils an infection could reach.
TGAP asks how much that depends on a few highly connected pupils - super-spreaders.

    python examples/projects/epidemic_contacts/main.py

Everything is written to output/ in this folder; start with TUTORIAL.md.
'''
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))

import pandas as pd                                          # noqa: E402

from examples import toolkit                                 # noqa: E402
from examples.projects.epidemic_contacts.concept import SuperSpreaders         # noqa: E402
from examples.projects.epidemic_contacts.data import makeData            # noqa: E402
from examples.projects.epidemic_contacts.model import OutbreakReach             # noqa: E402

# ============================== PARAMETERS ==============================
SNAPSHOTS = 6            # how many periods the time span is cut into
ALSO_TEST = ["density", "bridge_width"]   # built-in concepts to compare
DELTAS = [0.1, 0.25]
# ========================================================================


def main(output=None):
    output = output or os.path.join(HERE, "output")
    tutorial = toolkit.Tutorial(
        output, "Super-spreaders in a contact network - a TGAP tutorial",
        intro="How much does the reach of an outbreak depend on a few very connected pupils?")

    # STEP 1 - the data
    toolkit.step(1, 4, "Loading the data")
    events, groups = makeData()
    snapshots = toolkit.loadEdgeList(events, snapshots=SNAPSHOTS)
    communities = toolkit.loadGroups(groups, snapshots=snapshots)
    frame = pd.read_csv(events)
    tutorial.section("Step 1 - The data (data.py)", (
        "`data/contacts.csv` holds **{0} recorded contacts** between **{1} "
        "pupils** in {2} groups (`data/groups.csv`). TGAP cuts the time "
        "span into **{3} snapshots**; two pupils are tied in a snapshot "
        "when they were in close contact at least once.").format(
            len(frame), snapshots[0].number_of_nodes(), len(communities),
            SNAPSHOTS))
    tutorial.table(frame.head(5), "The first rows of data/contacts.csv")

    # STEP 2 - the model
    model = OutbreakReach(communities)
    today = model.predict(snapshots)
    toolkit.step(2, 4, "Model: OutbreakReach -> {0:.3f}".format(today))
    tutorial.section("Step 2 - The model (model.py)",
                     "`OutbreakReach` is the share of pupils in the largest connected group of contacts, averaged over the latest two snapshots: an infection starting anywhere in it could reach all of it.\n\nOn this data it says **{0:.3f}**."
                     .format(today))

    # STEP 3 - our own concept
    concept = SuperSpreaders(communities)
    before = concept.propertyValue(snapshots)
    after = concept.propertyValue(concept.transform(snapshots, 0.25))
    toolkit.step(3, 4, "Concept '{0}': {1:.3f} -> {2:.3f} after +25%"
                 .format(concept.name, before, after))
    tutorial.section("Step 3 - The concept (concept.py)", (
        "`SuperSpreaders` is the share of contacts that involve the most connected 10% of pupils. Up: contacts move TO those pupils. Down: contacts move away from them to the least connected classmates. The number of contacts, and of contacts across schools, never changes.\n\nOn this data it measures **{0:.3f}**; nudged "
        "up by 25% it becomes **{1:.3f}**.").format(before, after))

    # STEP 4 - explain
    toolkit.step(4, 4, "Explaining")
    toolkit.explainAndSave(
        "epidemic_contacts", model,
        [concept] + toolkit.transformations(ALSO_TEST, communities),
        snapshots, communities, deltas=DELTAS, folder=output,
        tutorial=tutorial, step="Step 4",
        modelDescription="the share of pupils an infection could reach")


if __name__ == "__main__":
    main()
