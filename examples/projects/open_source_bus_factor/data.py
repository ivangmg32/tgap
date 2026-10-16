'''
The dataset: half a year of code reviews in an open-source project. Two maintainers do most of the reviewing; most community members are active only now and then.
'''
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GROUPS = {'maintainers': ['maya', 'tom', 'rui', 'ines'], 'community': ['dev01', 'dev02', 'dev03', 'dev04', 'dev05', 'dev06', 'dev07', 'dev08', 'dev09', 'dev10', 'dev11', 'dev12', 'dev13', 'dev14', 'dev15', 'dev16', 'dev17', 'dev18', 'dev19', 'dev20']}


def makeData(seed=5):
    ''' Write data/reviews.csv and data/groups.csv (once) and return
    their paths. '''
    from examples.toolkit import simulateInteractions
    import pandas as pd
    folder = os.path.join(HERE, "data")
    events = os.path.join(folder, "reviews.csv")
    groups = os.path.join(folder, "groups.csv")
    if not (os.path.exists(events) and os.path.exists(groups)):
        os.makedirs(folder, exist_ok=True)
        frame = simulateInteractions(
            GROUPS, 26, withinPerPeriod=3,
            crossPerPeriod=4, hubs={"maya": 8.0, "tom": 6.0}, periodDays=7,
            seed=seed)
        frame.to_csv(events, index=False)
        pd.DataFrame([(p, g) for g, people in GROUPS.items()
                      for p in people],
                     columns=["person", "group"]).to_csv(groups, index=False)
    return events, groups
