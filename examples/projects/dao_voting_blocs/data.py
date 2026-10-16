'''
The dataset: a year of governance votes. Two blocs vote together internally; agreement across the blocs is rare and falls over the year.
'''
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GROUPS = {'bloc_a': ['a01', 'a02', 'a03', 'a04', 'a05', 'a06', 'a07', 'a08', 'a09', 'a10', 'a11', 'a12'], 'bloc_b': ['b01', 'b02', 'b03', 'b04', 'b05', 'b06', 'b07', 'b08', 'b09', 'b10', 'b11', 'b12']}


def makeData(seed=11):
    ''' Write data/co_votes.csv and data/groups.csv (once) and return
    their paths. '''
    from examples.toolkit import simulateInteractions
    import pandas as pd
    folder = os.path.join(HERE, "data")
    events = os.path.join(folder, "co_votes.csv")
    groups = os.path.join(folder, "groups.csv")
    if not (os.path.exists(events) and os.path.exists(groups)):
        os.makedirs(folder, exist_ok=True)
        frame = simulateInteractions(
            GROUPS, 24, withinPerPeriod=5,
            crossPerPeriod=lambda p: 4 - 3 * p / 24, hubs=None, periodDays=15,
            seed=seed)
        frame.to_csv(events, index=False)
        pd.DataFrame([(p, g) for g, people in GROUPS.items()
                      for p in people],
                     columns=["person", "group"]).to_csv(groups, index=False)
    return events, groups
