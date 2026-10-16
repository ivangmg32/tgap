'''
PROJECT - Team silos after a reorganisation.

Two teams, one year of messages. Contact across the teams fades and runs
more and more through one liaison. A "coordination fragility" model warns
when the teams are drifting apart. TGAP asks: what in the teams' history
drives that warning - the number of cross-team ties, or how much they
depend on one person?

    python examples/projects/team_silos/main.py

Everything is written to output/ in this folder; start with TUTORIAL.md.
'''
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))

import pandas as pd                                          # noqa: E402

from examples import toolkit                                 # noqa: E402
from examples.projects.team_silos.concept import LiaisonDependence  # noqa
from examples.projects.team_silos.data import LIAISON, makeData     # noqa
from examples.projects.team_silos.model import CoordinationFragility  # noqa

# ============================== PARAMETERS ==============================
SNAPSHOTS = 8              # the year cut into 8 periods (~6.5 weeks)
RECENT = 2                 # the model reads the last 2 periods
ALSO_TEST = ["bridge_width", "density"]   # built-in concepts to compare
DELTAS = [0.1, 0.25]
# ========================================================================


def main(output=None):
    output = output or os.path.join(HERE, "output")
    tutorial = toolkit.Tutorial(
        output, "Team silos after a reorganisation - a TGAP tutorial",
        intro="Two teams, one year of messages. Does a fragility warning "
              "come from **fewer** cross-team ties, or from **who carries** "
              "them? This tutorial follows the analysis step by step.")

    # STEP 1 - the data
    toolkit.step(1, 4, "Loading one year of messages between two teams")
    messages, teams = makeData()
    snapshots = toolkit.loadEdgeList(messages, snapshots=SNAPSHOTS)
    communities = toolkit.loadGroups(teams, snapshots=snapshots)
    frame = pd.read_csv(messages)
    tutorial.section("Step 1 - The data", (
        "`data/messages.csv` holds **{0} messages** between **{1} people** "
        "in two teams (`data/teams.csv`). TGAP cuts the year into **{2} "
        "snapshots**; two people are tied in a snapshot when they "
        "exchanged at least one message.").format(
            len(frame), snapshots[0].number_of_nodes(), SNAPSHOTS))
    tutorial.table(frame.head(5), "The first rows of data/messages.csv")

    # STEP 2 - the model
    model = CoordinationFragility(communities, RECENT)
    toolkit.step(2, 4, "Model: CoordinationFragility -> {0:.3f}".format(
        model.predict(snapshots)))
    tutorial.section("Step 2 - The model (model.py)", (
        "`CoordinationFragility` averages two warning signs over the last "
        "{0} snapshots: the share of ties that do **not** cross between "
        "the teams, and the share of crossing ties carried by **one** "
        "person. Today it says **{1:.3f}** (0 = robust, 1 = fragile)."
    ).format(RECENT, model.predict(snapshots)))

    # STEP 3 - our own concept
    concept = LiaisonDependence(communities)
    before = concept.propertyValue(snapshots)
    after = concept.propertyValue(concept.transform(snapshots, 0.25))
    toolkit.step(3, 4, "Concept 'Liaison Dependence': {0:.2f} -> {1:.2f} "
                 "after +25%".format(before, after))
    tutorial.section("Step 3 - The concept (concept.py)", (
        "`LiaisonDependence` measures how much of the cross-team contact "
        "goes through the busiest liaison (here mostly `{0}`): **{1:.2f}** "
        "on average. Nudged up by 25% it becomes **{2:.2f}**. It moves "
        "ties to or from the liaison but never changes how many ties "
        "there are - so it is a different question from Bridge Width, "
        "which changes how many ties cross.").format(LIAISON, before, after))

    # STEP 4 - explain
    toolkit.step(4, 4, "Explaining")
    toolkit.explainAndSave(
        "team_silos", model,
        [concept] + toolkit.transformations(ALSO_TEST, communities),
        snapshots, communities, deltas=DELTAS, folder=output,
        tutorial=tutorial, step="Step 4",
        modelDescription="how fragile coordination between the teams is")


if __name__ == "__main__":
    main()
