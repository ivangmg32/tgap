''' The model TGAP explains. '''
from core import TemporalGraphModel, interCommunityEdges


class CoordinationFragility(TemporalGraphModel):
    ''' How fragile is coordination between the teams right now?
    0 = robust, 1 = fragile. Averages two warning signs over the last
    `recent` snapshots:
      * silo     - few of the ties cross between the teams;
      * liaison  - most crossing ties run through ONE person, so losing
                   that person would cut the teams apart. '''

    def __init__(self, teams, recent=2):
        self.teams = teams
        self.recent = recent

    def predict(self, snapshots):
        scores = []
        for graph in snapshots[-self.recent:]:
            cross = interCommunityEdges(graph, self.teams)
            silo = 1 - len(cross) / max(graph.number_of_edges(), 1)
            counts = {}
            for u, v in cross:
                counts[u] = counts.get(u, 0) + 1
                counts[v] = counts.get(v, 0) + 1
            liaison = max(counts.values()) / len(cross) if cross else 1.0
            scores.append((silo + liaison) / 2)
        return sum(scores) / len(scores)
