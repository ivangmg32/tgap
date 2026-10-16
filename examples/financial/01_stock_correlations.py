'''
FINANCE 1 - Which stocks move together?

The simplest start: take some stocks, compute how strongly their daily
returns move together (correlation, -1..+1), and draw it as a network.
Uses Ivan's CorrGraphs and his cached prices - works offline.

    python examples/financial/01_stock_correlations.py

Outputs: output/examples/financial/01_stock_correlations/
    correlations.csv     every pair, strongest first
    network.png          the correlation network (red = together, blue = opposite)
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import pandas as pd                       # noqa: E402

from examples import toolkit              # noqa: E402
from finance.CorrGraphs import CorrGraphs  # noqa: E402

# ============================== PARAMETERS ==============================
TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "JPM", "XOM", "JNJ"]
PERIOD = "6mo"            # how much price history: 6mo or 5y are cached
# ========================================================================


def main():
    folder = os.path.join(toolkit.OUTPUT, "financial", "01_stock_correlations")
    os.makedirs(folder, exist_ok=True)

    # STEP 1 - prices -> daily returns -> one correlation network
    toolkit.step(1, 3, "Correlating {0} stocks over the last {1}".format(
        len(TICKERS), PERIOD))
    network = CorrGraphs(TICKERS).graph(yfPeriod=PERIOD)

    # STEP 2 - every pair, strongest co-movement first
    pairs = pd.DataFrame(
        [{"stock_a": u, "stock_b": v, "correlation": round(d["weight"], 3)}
         for u, v, d in network.edges(data=True)]
    ).sort_values("correlation", ascending=False)
    pairs.to_csv(os.path.join(folder, "correlations.csv"), index=False)
    toolkit.step(2, 3, "Strongest and weakest pairs:")
    for _, row in pd.concat([pairs.head(3), pairs.tail(2)]).iterrows():
        print("        {0:>5s} - {1:<5s}  {2:+.2f}".format(
            row["stock_a"], row["stock_b"], row["correlation"]))

    # STEP 3 - draw it (Ivan's plot, saved to a file)
    CorrGraphs(TICKERS).plotGraph(network, path=os.path.join(
        folder, "network.png"))
    toolkit.step(3, 3, "Saved the network picture and the table")
    t = toolkit.Tutorial(folder, "Which stocks move together?",
                         intro="One correlation network for {0} stocks, "
                               "built with Ivan's `CorrGraphs.graph`."
                               .format(len(TICKERS)))
    t.section("Step 1 - From prices to correlations", (
        "Daily closing prices over the last {0} (from Ivan's cache) become "
        "daily returns, and every pair of stocks gets a **correlation** "
        "between -1 and +1: +1 = they always move together, 0 = unrelated, "
        "-1 = they move in opposite directions.").format(PERIOD))
    t.section("Step 2 - Every pair, strongest first")
    t.table(pairs, "correlations.csv", maxRows=10)
    t.section("Step 3 - The network")
    t.image("network.png", "Every stock is a node; every pair is joined. "
            "Red = moving together, blue = opposite; thicker = stronger.")
    t.text("Every pair is connected, so the network is **complete**. "
           "Example 3 shows why TGAP needs a threshold on top of this.")
    print("      Results (CSV + PNG + tutorial): " + folder)
    print("      Read first: " + t.save())


if __name__ == "__main__":
    main()
