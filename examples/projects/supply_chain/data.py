'''
The dataset: two years of orders between suppliers and factories in Asia and Europe. One large distributor handles much of the trade, many small companies have a single partner.
'''
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GROUPS = {'asia': ['as01', 'as02', 'as03', 'as04', 'as05', 'as06', 'as07', 'as08', 'as09', 'as10', 'as11', 'as12'], 'europe': ['eu01', 'eu02', 'eu03', 'eu04', 'eu05', 'eu06', 'eu07', 'eu08', 'eu09', 'eu10', 'eu11', 'eu12']}


def makeData(seed=31):
    ''' Write data/orders.csv and data/groups.csv (once) and return
    their paths. '''
    from examples.toolkit import simulateInteractions
    import pandas as pd
    folder = os.path.join(HERE, "data")
    events = os.path.join(folder, "orders.csv")
    groups = os.path.join(folder, "groups.csv")
    if not (os.path.exists(events) and os.path.exists(groups)):
        os.makedirs(folder, exist_ok=True)
        frame = simulateInteractions(
            GROUPS, 24, withinPerPeriod=2,
            crossPerPeriod=2, hubs={"as01": 10.0}, periodDays=30,
            seed=seed)
        frame.to_csv(events, index=False)
        pd.DataFrame([(p, g) for g, people in GROUPS.items()
                      for p in people],
                     columns=["person", "group"]).to_csv(groups, index=False)
    return events, groups
