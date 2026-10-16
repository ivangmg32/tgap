'''
The dataset: a school year of interactions in two classes. Activity slowly falls, so more students end up without anyone to talk to.
'''
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GROUPS = {'class_a': ['sa01', 'sa02', 'sa03', 'sa04', 'sa05', 'sa06', 'sa07', 'sa08', 'sa09', 'sa10', 'sa11', 'sa12', 'sa13', 'sa14'], 'class_b': ['sb01', 'sb02', 'sb03', 'sb04', 'sb05', 'sb06', 'sb07', 'sb08', 'sb09', 'sb10', 'sb11', 'sb12', 'sb13', 'sb14']}


def makeData(seed=21):
    ''' Write data/interactions.csv and data/groups.csv (once) and return
    their paths. '''
    from examples.toolkit import simulateInteractions
    import pandas as pd
    folder = os.path.join(HERE, "data")
    events = os.path.join(folder, "interactions.csv")
    groups = os.path.join(folder, "groups.csv")
    if not (os.path.exists(events) and os.path.exists(groups)):
        os.makedirs(folder, exist_ok=True)
        frame = simulateInteractions(
            GROUPS, 32, withinPerPeriod=lambda p: 4 - 2.5 * p / 32,
            crossPerPeriod=1, hubs=None, periodDays=7,
            seed=seed)
        frame.to_csv(events, index=False)
        pd.DataFrame([(p, g) for g, people in GROUPS.items()
                      for p in people],
                     columns=["person", "group"]).to_csv(groups, index=False)
    return events, groups
