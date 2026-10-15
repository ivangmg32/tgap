'''
EXAMPLE 6 - YOUR PROJECT TEMPLATE. Copy this file and make it yours.

All four parts in one place - change any of them independently:

    1. DATA            your CSV of interactions (or the sample)
    2. COMMUNITIES     your groups CSV, or let TGAP find them
    3. MODEL           a built-in one by name, or your own class
    4. CONCEPTS        built-in ones by name, plus your own class

    cp examples/06_my_project.py examples/my_study.py     (macOS / Linux)
    copy examples\\06_my_project.py examples\\my_study.py   (Windows)
    python examples/my_study.py

Outputs (CSV + PNG) go to output/examples/<RUN_NAME>/.
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import TemporalGraphModel, TemporalGraphTransformation  # noqa: E402
from examples import toolkit   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# ============================== PARAMETERS ==============================
RUN_NAME = "my_project"                       # name of the output folder

# 1. DATA
CSV_FILE = os.path.join(HERE, "data", "sample_edges.csv")
SOURCE_COLUMN, TARGET_COLUMN, TIME_COLUMN = "source", "target", "time"
SNAPSHOTS = 6

# 2. COMMUNITIES  (None = detect HOW_MANY_GROUPS automatically)
GROUPS_FILE = os.path.join(HERE, "data", "sample_groups.csv")
PERSON_COLUMN, GROUP_COLUMN = "person", "group"
HOW_MANY_GROUPS = 2

# 3. MODEL: a built-in name (see example 1) or "mine" for MyModel below
MODEL = "mine"

# 4. CONCEPTS: built-in names, plus MyConcept below if USE_MY_CONCEPT
CONCEPTS = ["bridge_width", "density", "churn"]
USE_MY_CONCEPT = True

DELTAS = [0.1, 0.25]
# ========================================================================


class MyModel(TemporalGraphModel):
    ''' Replace predict() with your model. It receives the list of
    snapshots (oldest first) and must return one number. '''

    def __init__(self, communities):
        self.communities = communities

    def predict(self, snapshots):
        # Example: average number of ties per person in the latest snapshot.
        latest = snapshots[-1]
        return 2 * latest.number_of_edges() / max(latest.number_of_nodes(), 1)


class MyConcept(TemporalGraphTransformation):
    ''' Replace with your concept. Example: "Quiet Members" - the share of
    people with no tie at all.
        delta > 0  silences more people (the least active lose their ties)
        delta < 0  brings quiet people back (each gets one tie to the most
                   active person) '''

    name = "Quiet Members"
    preservesEdgeCount = False

    def propertyValue(self, snapshots):
        snapshots = snapshots if isinstance(snapshots, list) else [snapshots]
        quiet = [sum(1 for n in g if g.degree(n) == 0) / max(len(g), 1)
                 for g in snapshots]
        return sum(quiet) / len(quiet)

    def transformGraph(self, graph, delta):
        g = graph.copy()                         # never change the input
        byActivity = sorted(g, key=lambda n: (g.degree(n), str(n)))
        active = [n for n in byActivity if g.degree(n) > 0]
        quiet = [n for n in byActivity if g.degree(n) == 0]
        if delta > 0 and active:
            for person in active[:max(1, round(delta * len(active)))]:
                g.remove_edges_from(list(g.edges(person)))
        elif delta < 0 and quiet and active:
            hub = active[-1]
            for person in quiet[:max(1, round(-delta * len(quiet)))]:
                g.add_edge(person, hub)
        return g


def main():
    snapshots = toolkit.loadEdgeList(CSV_FILE, SOURCE_COLUMN, TARGET_COLUMN,
                                     TIME_COLUMN, SNAPSHOTS)
    if GROUPS_FILE:
        communities = toolkit.loadGroups(GROUPS_FILE, PERSON_COLUMN,
                                         GROUP_COLUMN, snapshots)
    else:
        communities = toolkit.findCommunities(snapshots, HOW_MANY_GROUPS)

    model = MyModel(communities) if MODEL == "mine" \
        else toolkit.model(MODEL, communities)
    concepts = toolkit.transformations(CONCEPTS, communities)
    if USE_MY_CONCEPT:
        concepts.append(MyConcept())

    print("Run '{0}': {1} people, {2} snapshots, model {3}".format(
        RUN_NAME, snapshots[0].number_of_nodes(), len(snapshots), MODEL))
    toolkit.explainAndSave(RUN_NAME, model, concepts, snapshots,
                           communities, deltas=DELTAS)


if __name__ == "__main__":
    main()
