'''
FINANCE 5 - Your own market model.

Write any model as a class with predict(snapshots) -> number. Here a simple
"systemic risk" score: the share of stocks that are strongly tied to at
least HALF of the market in the most recent windows. When many stocks move
with everybody, diversification stops working.

TGAP never looks inside predict(); it only asks how the score moves when
the market's past changes in one human-meaningful way.

    python examples/financial/05_your_own_market_model.py
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from core import TemporalGraphModel          # noqa: E402
from examples import toolkit                 # noqa: E402
from finance.networks import prepare         # noqa: E402
from finance.universe import IVAN_SECTORS    # noqa: E402

# ============================== PARAMETERS ==============================
SECTORS = IVAN_SECTORS
FOCUS = "Technology"
THRESHOLD = 0.3
RECENT = 3                    # how many latest windows the model looks at
CONCEPTS = ["bridge_width", "density", "centralization", "churn"]
DELTAS = [0.1, 0.25]
# ========================================================================


class SystemicRisk(TemporalGraphModel):
    ''' Share of stocks tied to at least half of the other stocks,
    averaged over the last `recent` windows (0 = calm, 1 = all together). '''

    def __init__(self, recent=3):
        self.recent = recent

    def predict(self, snapshots):
        scores = []
        for graph in snapshots[-self.recent:]:
            others = max(graph.number_of_nodes() - 1, 1)
            hubs = sum(1 for n in graph if graph.degree(n) >= others / 2)
            scores.append(hubs / max(graph.number_of_nodes(), 1))
        return sum(scores) / len(scores)


def main():
    # STEP 1 - the market
    toolkit.step(1, 3, "Building the market graph")
    market = prepare("example", list(SECTORS), SECTORS, "5y", "6mo", 12,
                     THRESHOLD, focus=FOCUS)

    # STEP 2 - YOUR model
    model = SystemicRisk(RECENT)
    toolkit.step(2, 3, "Your model: SystemicRisk -> today {0:.3f}".format(
        model.predict(market.snapshots)))

    # STEP 3 - explain
    toolkit.step(3, 3, "Explaining with: " + ", ".join(CONCEPTS))
    toolkit.explainAndSave("financial/05_your_own_market_model", model,
                           toolkit.transformations(CONCEPTS,
                                                   market.communities),
                           market.snapshots, market.communities,
                           deltas=DELTAS)


if __name__ == "__main__":
    main()
