'''
WRAPPER 5 - A concept that reshapes the whole history.

    python examples/wrapper/05_concept_over_time.py

Some concepts are not about one snapshot but about HOW THINGS CHANGE over
time ("is activity fading?"). Give the wrapper  overTime(snapshots, delta)
instead of change(graph, delta): you receive the whole history (copies) and
return new snapshots. Keep the LAST snapshot as it is - then any change in the
prediction comes from the history, not from the present (TSAP's rule: keep
the last value fixed).

Here: "Growth" - how much bigger the present is than the past. delta > 0
makes older snapshots sparser (activity grew more); delta < 0 fills them in
from their successor (activity grew less). The measure is for the whole
history: measure(snapshots) -> one number.

Results: output/examples/wrapper_05_concept_over_time/
'''
import os
import random
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import numpy as np                             # noqa: E402

from tgap_wrapper import Wrapper               # noqa: E402

w = Wrapper.synthetic("wrapper_05_concept_over_time", snapshots=8)


@w.model
def activity_slope(snapshots):
    ''' How fast activity rises per snapshot (a straight line through the
    tie counts, relative to the average). '''
    ties = [g.number_of_edges() for g in snapshots]
    slope = np.polyfit(range(len(ties)), ties, 1)[0]
    return float(slope / (sum(ties) / len(ties)))




def growth(snapshots, delta):
    rng = random.Random(42)                     # repeatable
    last = len(snapshots) - 1
    for position, graph in enumerate(snapshots[:-1]):
        age = (last - position) / last          # 1 = oldest, 0 = newest
        howMany = round(abs(delta) * age * graph.number_of_edges())
        if delta > 0:                           # thin out the past
            graph.remove_edges_from(rng.sample(
                sorted(graph.edges()), min(howMany, graph.number_of_edges())))
        else:                                   # fill the past in
            later = {tuple(sorted(e)) for e in snapshots[position + 1].edges()}
            missing = sorted(later - {tuple(sorted(e)) for e in graph.edges()})
            graph.add_edges_from(rng.sample(missing, min(howMany, len(missing))))
    return snapshots                            # the last one is untouched


def growthOf(snapshots):
    ties = [g.number_of_edges() for g in snapshots]
    return ties[-1] / (sum(ties) / len(ties))   # latest vs. average


w.concept(overTime=growth, name="Growth", measure=growthOf,
          keepsEdgeCount=False)
w.concept("density")
w.explain()
