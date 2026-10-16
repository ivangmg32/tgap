'''
The dataset: one year of messages between two teams after a reorganisation.
Contact across teams fades, and most of what is left runs through one
person (a "liaison").
'''
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TEAMS = {
    "product": ["ana", "ben", "cleo", "dev", "eli", "fay", "gus", "hana"],
    "engineering": ["ivo", "jo", "kai", "lea", "max", "nia", "oli", "pia"],
}
LIAISON = "dev"


def makeData(weeks=52, seed=3):
    ''' Write data/messages.csv and data/teams.csv (once) and return
    their paths. '''
    from examples.toolkit import simulateInteractions
    import pandas as pd
    folder = os.path.join(HERE, "data")
    messages = os.path.join(folder, "messages.csv")
    teams = os.path.join(folder, "teams.csv")
    if not (os.path.exists(messages) and os.path.exists(teams)):
        os.makedirs(folder, exist_ok=True)
        frame = simulateInteractions(
            TEAMS, weeks, withinPerPeriod=6,
            # cross-team contact fades from 6 to 1 message a week
            crossPerPeriod=lambda week: 6 - 5 * week / weeks,
            hubs={LIAISON: 6.0}, seed=seed)
        frame.to_csv(messages, index=False)
        pd.DataFrame([(p, t) for t, people in TEAMS.items() for p in people],
                     columns=["person", "group"]).to_csv(teams, index=False)
    return messages, teams
