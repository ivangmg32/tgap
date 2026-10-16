''' The concept TGAP changes. '''
import random

from core import TemporalGraphTransformation, asPartition


class SupplierDiversification(TemporalGraphTransformation):
    ''' Share of trading companies with at least two partners.

    delta > 0: companies with a single partner gain a second one in their
               own region;
    delta < 0: companies with backups lose one partner (never their last). '''

    name = "Supplier Diversification"
    preservesEdgeCount = False

    def __init__(self, regions, seed=42):
        self.regions = asPartition(regions)
        self.seed = seed

    def propertyValue(self, snapshots):
        snapshots = snapshots if isinstance(snapshots, list) else [snapshots]
        shares = []
        for g in snapshots:
            trading = [n for n in g if g.degree(n) > 0]
            shares.append(sum(1 for n in trading if g.degree(n) >= 2)
                          / max(len(trading), 1))
        return sum(shares) / len(shares)

    def transformGraph(self, graph, delta):
        g = graph.copy()
        rng = random.Random(self.seed)
        trading = [n for n in g if g.degree(n) > 0]
        k = max(1, round(abs(delta) * len(trading)))
        if delta > 0:
            single = sorted(str(n) for n in trading if g.degree(n) == 1)
            for company in single[:k]:
                own = self.regions[self.regions.communityOf(company)]
                options = sorted(str(m) for m in own if m != company
                                 and not g.has_edge(company, m))
                if options:
                    g.add_edge(company, options[rng.randrange(len(options))])
        elif delta < 0:
            backed = sorted((n for n in trading if g.degree(n) >= 2),
                            key=lambda n: (g.degree(n), str(n)))
            for company in backed[:k]:
                partners = sorted((m for m in g[company] if g.degree(m) >= 2),
                                  key=str)
                if partners and g.degree(company) >= 2:
                    g.remove_edge(company, partners[0])
        return g
