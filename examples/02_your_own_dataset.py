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
    snapshots = toolkit.loadEdgeList(CSV_FILE, SOURCE_COLUMN, TARGET_COLUMN,
                                     TIME_COLUMN, SNAPSHOTS)
    if GROUPS_FILE:
        communities = toolkit.loadGroups(GROUPS_FILE, PERSON_COLUMN,
                                         GROUP_COLUMN, snapshots)
    else:
        communities = toolkit.findCommunities(snapshots, HOW_MANY_GROUPS)
    print("Loaded {0}: {1} people, {2} snapshots, groups of size {3}".format(
        os.path.basename(CSV_FILE), snapshots[0].number_of_nodes(),
        len(snapshots), "/".join(str(len(g)) for g in communities)))
    toolkit.explainAndSave(
        "02_your_own_dataset",
        toolkit.model(MODEL, communities),
        toolkit.transformations(TRANSFORMATIONS, communities),
        snapshots, communities, deltas=DELTAS)


if __name__ == "__main__":
    main()
