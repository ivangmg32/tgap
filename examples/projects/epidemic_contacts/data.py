'''
The dataset: a term of close contacts in two schools. A few pupils (sports captains, bus riders) meet far more people than the rest.
'''
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GROUPS = {'school_north': ['n01', 'n02', 'n03', 'n04', 'n05', 'n06', 'n07', 'n08', 'n09', 'n10', 'n11', 'n12', 'n13', 'n14', 'n15'], 'school_south': ['s01', 's02', 's03', 's04', 's05', 's06', 's07', 's08', 's09', 's10', 's11', 's12', 's13', 's14', 's15']}


def makeData(seed=41):
    ''' Write data/contacts.csv and data/groups.csv (once) and return
    their paths. '''
    from examples.toolkit import simulateInteractions
    import pandas as pd
    folder = os.path.join(HERE, "data")
    events = os.path.join(folder, "contacts.csv")
    groups = os.path.join(folder, "groups.csv")
    if not (os.path.exists(events) and os.path.exists(groups)):
        os.makedirs(folder, exist_ok=True)
        frame = simulateInteractions(
            GROUPS, 12, withinPerPeriod=3,
            crossPerPeriod=4, hubs={"n01": 6.0, "n02": 5.0, "s01": 6.0}, periodDays=7,
            seed=seed)
        frame.to_csv(events, index=False)
        pd.DataFrame([(p, g) for g, people in GROUPS.items()
                      for p in people],
                     columns=["person", "group"]).to_csv(groups, index=False)
    return events, groups
