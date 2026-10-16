'''
PROJECT - Voting blocs in a DAO.

A decentralised organisation (DAO) where members vote on proposals. Two blocs form.
A "polarization" model measures how much more members vote with their own bloc than across.
TGAP asks how swing voters - members who vote with both blocs - affect polarization.

    python examples/projects/dao_voting_blocs/main.py

Everything is written to output/ in this folder; start with TUTORIAL.md.
'''
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))

import pandas as pd                                          # noqa: E402

from examples import toolkit                                 # noqa: E402
from examples.projects.dao_voting_blocs.concept import SwingVoters         # noqa: E402
from examples.projects.dao_voting_blocs.data import makeData            # noqa: E402
from examples.projects.dao_voting_blocs.model import Polarization             # noqa: E402

# ============================== PARAMETERS ==============================
SNAPSHOTS = 6            # how many periods the time span is cut into
ALSO_TEST = ["bridge_width", "density"]   # built-in concepts to compare
DELTAS = [0.1, 0.25]
# ========================================================================


def main(output=None):
    output = output or os.path.join(HERE, "output")
    tutorial = toolkit.Tutorial(
        output, "Voting blocs in a DAO - a TGAP tutorial",
        intro="Do swing voters, who side with both blocs, reduce the polarization of a DAO?")

    # STEP 1 - the data
    toolkit.step(1, 4, "Loading the data")
    events, groups = makeData()
    snapshots = toolkit.loadEdgeList(events, snapshots=SNAPSHOTS)
    communities = toolkit.loadGroups(groups, snapshots=snapshots)
    frame = pd.read_csv(events)
    tutorial.section("Step 1 - The data (data.py)", (
        "`data/co_votes.csv` holds **{0} pairs of members voting the same way** between **{1} "
        "members** in {2} groups (`data/groups.csv`). TGAP cuts the time "
        "span into **{3} snapshots**; two members are tied in a snapshot "
        "when they voted the same way on at least one proposal.").format(
            len(frame), snapshots[0].number_of_nodes(), len(communities),
            SNAPSHOTS))
    tutorial.table(frame.head(5), "The first rows of data/co_votes.csv")

    # STEP 2 - the model
    model = Polarization(communities)
    today = model.predict(snapshots)
    toolkit.step(2, 4, "Model: Polarization -> {0:.3f}".format(today))
    tutorial.section("Step 2 - The model (model.py)",
                     "`Polarization` compares how densely members agree WITHIN their bloc with how densely they agree ACROSS blocs, in the latest two snapshots. 0 = no blocs; close to 1 = members only ever agree with their own bloc.\n\nOn this data it says **{0:.3f}**."
                     .format(today))

    # STEP 3 - our own concept
    concept = SwingVoters(communities)
    before = concept.propertyValue(snapshots)
    after = concept.propertyValue(concept.transform(snapshots, 0.25))
    toolkit.step(3, 4, "Concept '{0}': {1:.3f} -> {2:.3f} after +25%"
                 .format(concept.name, before, after))
    tutorial.section("Step 3 - The concept (concept.py)", (
        "`SwingVoters` measures the share of members who agree with someone in BOTH blocs. Up: single-bloc members gain one agreement across the divide. Down: swing voters lose their agreements with the other bloc.\n\nOn this data it measures **{0:.3f}**; nudged "
        "up by 25% it becomes **{1:.3f}**.").format(before, after))

    # STEP 4 - explain
    toolkit.step(4, 4, "Explaining")
    toolkit.explainAndSave(
        "dao_voting_blocs", model,
        [concept] + toolkit.transformations(ALSO_TEST, communities),
        snapshots, communities, deltas=DELTAS, folder=output,
        tutorial=tutorial, step="Step 4",
        modelDescription="how much more members vote within their bloc than across")


if __name__ == "__main__":
    main()
