'''
EXAMPLE 2 - Your own dataset, from a CSV file.

Your data only needs one row per interaction: who, with whom, when.

    source,target,time
    alice,bruno,2024-01-01
    carla,ines,2024-01-02
    ...

"time" can be a date or a number. Point CSV_FILE at your file, set the
column names, and run:

    python examples/02_your_own_dataset.py

The sample file examples/data/sample_edges.csv (two teams whose contact is
fading) is used until you change it. Outputs go to
output/examples/02_your_own_dataset/.
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from examples import toolkit   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# ============================== PARAMETERS ==============================
CSV_FILE = os.path.join(HERE, "data", "sample_edges.csv")
SOURCE_COLUMN = "source"
TARGET_COLUMN = "target"
TIME_COLUMN = "time"
SNAPSHOTS = 6              # the time span is cut into this many windows

# Communities - who belongs to which group. Either:
#   a CSV with one row per person (set GROUPS_FILE), or
#   GROUPS_FILE = None to let TGAP find HOW_MANY_GROUPS groups by itself.
GROUPS_FILE = os.path.join(HERE, "data", "sample_groups.csv")
PERSON_COLUMN = "person"
GROUP_COLUMN = "group"
HOW_MANY_GROUPS = 2

MODEL = "trend_bridge_width"          # see example 1 for the choices
TRANSFORMATIONS = ["bridge_width", "density", "churn"]
DELTAS = [0.1, 0.25]
# ========================================================================


def main():
    # STEP 1 - read your CSV and cut it into snapshots
    toolkit.step(1, 4, "Reading {0}".format(os.path.basename(CSV_FILE)))
    snapshots = toolkit.loadEdgeList(CSV_FILE, SOURCE_COLUMN, TARGET_COLUMN,
                                     TIME_COLUMN, SNAPSHOTS)
    print("        {0} people, {1} snapshots".format(
        snapshots[0].number_of_nodes(), len(snapshots)))

    # STEP 2 - who belongs to which group
    if GROUPS_FILE:
        communities = toolkit.loadGroups(GROUPS_FILE, PERSON_COLUMN,
                                         GROUP_COLUMN, snapshots)
        source = "from " + os.path.basename(GROUPS_FILE)
    else:
        communities = toolkit.findCommunities(snapshots, HOW_MANY_GROUPS)
        source = "found automatically"
    toolkit.step(2, 4, "Groups ({0}): sizes {1}".format(
        source, "/".join(str(len(g)) for g in communities)))

    # STEP 3 - the model and the concepts
    toolkit.step(3, 4, "Model: {0};  concepts: {1}".format(
        MODEL, ", ".join(TRANSFORMATIONS)))
    model = toolkit.model(MODEL, communities)
    concepts = toolkit.transformations(TRANSFORMATIONS, communities)

    # STEP 4 - explain, print, and save CSV + PNG
    toolkit.step(4, 4, "Explaining")
    toolkit.explainAndSave("02_your_own_dataset", model, concepts, snapshots,
                           communities, deltas=DELTAS)

if __name__ == "__main__":
    main()
