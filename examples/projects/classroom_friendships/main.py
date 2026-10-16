'''
PROJECT - Lonely students in two classrooms.

Two classrooms over a school year. Some students become isolated.
A "loneliness forecast" model extrapolates how many students will have no friend next term.
TGAP asks how a buddy programme - pairing isolated students with classmates - would change the forecast.

    python examples/projects/classroom_friendships/main.py

Everything is written to output/ in this folder; start with TUTORIAL.md.
'''
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))

import pandas as pd                                          # noqa: E402

from examples import toolkit                                 # noqa: E402
from examples.projects.classroom_friendships.concept import IsolatedStudents         # noqa: E402
from examples.projects.classroom_friendships.data import makeData            # noqa: E402
from examples.projects.classroom_friendships.model import LonelinessForecast             # noqa: E402

# ============================== PARAMETERS ==============================
SNAPSHOTS = 8            # how many periods the time span is cut into
ALSO_TEST = ["density", "churn"]   # built-in concepts to compare
DELTAS = [0.1, 0.25]
# ========================================================================


def main(output=None):
    output = output or os.path.join(HERE, "output")
    tutorial = toolkit.Tutorial(
        output, "Lonely students in two classrooms - a TGAP tutorial",
        intro="Would a buddy programme, pairing isolated students with a classmate, change the loneliness forecast?")

    # STEP 1 - the data
    toolkit.step(1, 4, "Loading the data")
    events, groups = makeData()
    snapshots = toolkit.loadEdgeList(events, snapshots=SNAPSHOTS)
    communities = toolkit.loadGroups(groups, snapshots=snapshots)
    frame = pd.read_csv(events)
    tutorial.section("Step 1 - The data (data.py)", (
        "`data/interactions.csv` holds **{0} recorded interactions** between **{1} "
        "students** in {2} groups (`data/groups.csv`). TGAP cuts the time "
        "span into **{3} snapshots**; two students are tied in a snapshot "
        "when they interacted at least once.").format(
            len(frame), snapshots[0].number_of_nodes(), len(communities),
            SNAPSHOTS))
    tutorial.table(frame.head(5), "The first rows of data/interactions.csv")

    # STEP 2 - the model
    model = LonelinessForecast(communities)
    today = model.predict(snapshots)
    toolkit.step(2, 4, "Model: LonelinessForecast -> {0:.3f}".format(today))
    tutorial.section("Step 2 - The model (model.py)",
                     "`LonelinessForecast` counts the students with no tie in every snapshot, fits a straight line through those counts, and extrapolates one period ahead.\n\nOn this data it says **{0:.3f}**."
                     .format(today))

    # STEP 3 - our own concept
    concept = IsolatedStudents(communities)
    before = concept.propertyValue(snapshots)
    after = concept.propertyValue(concept.transform(snapshots, 0.25))
    toolkit.step(3, 4, "Concept '{0}': {1:.3f} -> {2:.3f} after +25%"
                 .format(concept.name, before, after))
    tutorial.section("Step 3 - The concept (concept.py)", (
        "`IsolatedStudents` is the average number of students with no tie. Up: the least connected students lose their ties. Down (the buddy programme): isolated students get one tie to a classmate in their own class.\n\nOn this data it measures **{0:.3f}**; nudged "
        "up by 25% it becomes **{1:.3f}**.").format(before, after))

    # STEP 4 - explain
    toolkit.step(4, 4, "Explaining")
    toolkit.explainAndSave(
        "classroom_friendships", model,
        [concept] + toolkit.transformations(ALSO_TEST, communities),
        snapshots, communities, deltas=DELTAS, folder=output,
        tutorial=tutorial, step="Step 4",
        modelDescription="how many students will have no friend next period")


if __name__ == "__main__":
    main()
