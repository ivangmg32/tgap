'''
FINANCE 4 - Explain a model of the market with TGAP.

A model looks at the history of the market graph and predicts one number.
Here: "how many strong cross-sector ties will there be next window?" -
a simple contagion / coupling forecast. TGAP then asks: if the past had had
10% more cross-sector co-movement (or more synchronization, or more churn),
how would that forecast change?

    python examples/financial/04_explain_a_market_model.py

Outputs: output/examples/financial/04_explain_a_market_model/
    explanation.csv/.png, sensitivity.csv/.png, graph_over_time.csv/.png
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from examples import toolkit                 # noqa: E402
from finance.networks import prepare         # noqa: E402
from finance.universe import IVAN_SECTORS    # noqa: E402

# ============================== PARAMETERS ==============================
SECTORS = IVAN_SECTORS
FOCUS = "Technology"          # Technology vs the rest (works with 8 stocks)
THRESHOLD = 0.3               # usable for these stocks (see example 3)
PERIOD, WINDOW, WINDOWS = "5y", "6mo", 12

# The model (see examples/01_quickstart.py for the list). For a market:
#   trend_bridge_width   - cross-sector coupling, extrapolated
#   trend_density        - overall synchronization, extrapolated
#   persistence_centralization - is one stock driving the co-movement?
MODEL = "trend_bridge_width"
CONCEPTS = ["bridge_width", "density", "churn", "bridge_trend"]
DELTAS = [0.1, 0.25]
# ========================================================================


def main():
    # STEP 1 - the market as a temporal graph
    toolkit.step(1, 3, "Building the market graph ({0} stocks, threshold "
                 "{1})".format(len(SECTORS), THRESHOLD))
    market = prepare("example", list(SECTORS), SECTORS, PERIOD, WINDOW,
                     WINDOWS, THRESHOLD, focus=FOCUS)

    # STEP 2 - the model and the concepts
    toolkit.step(2, 3, "Model: {0} - {1}".format(MODEL,
                                                 toolkit.MODELS[MODEL][0]))
    model = toolkit.model(MODEL, market.communities)
    concepts = toolkit.transformations(CONCEPTS, market.communities)

    # STEP 3 - explain
    toolkit.step(3, 3, "Explaining with: " + ", ".join(CONCEPTS))
    toolkit.explainAndSave("financial/04_explain_a_market_model", model,
                           concepts, market.snapshots, market.communities,
                           deltas=DELTAS)


if __name__ == "__main__":
    main()
