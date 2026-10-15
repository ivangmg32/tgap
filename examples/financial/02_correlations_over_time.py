'''
FINANCE 2 - The market changes over time.

Correlations are not fixed: in a crisis, stocks move together much more.
Ivan's CorrGraphs builds one correlation network per sliding time window,
which gives a TEMPORAL GRAPH - exactly what TGAP explains.

    python examples/financial/02_correlations_over_time.py

Outputs: output/examples/financial/02_correlations_over_time/
    windows.csv            mean correlation of each window
    synchronization.png    the market's "togetherness" over time
    networks.png           six of the windows, side by side
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import matplotlib                          # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt            # noqa: E402
import numpy as np                         # noqa: E402
import pandas as pd                        # noqa: E402

from examples import toolkit               # noqa: E402
from finance.CorrGraphs import CorrGraphs  # noqa: E402

# ============================== PARAMETERS ==============================
TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "JPM", "XOM", "JNJ"]
PERIOD = "5y"             # total price history (5y is cached)
WINDOW = "6mo"            # length of each correlation window
WINDOWS = 12              # how many windows, spread over the history
# ========================================================================


def main():
    folder = os.path.join(toolkit.OUTPUT, "financial",
                          "02_correlations_over_time")
    os.makedirs(folder, exist_ok=True)

    # STEP 1 - one correlation network per window (Ivan's temporalGraph)
    toolkit.step(1, 3, "Building {0} correlation networks of {1} each over "
                 "{2}".format(WINDOWS, WINDOW, PERIOD))
    builder = CorrGraphs(TICKERS)
    series = builder.temporalGraph(PERIOD, WINDOW, WINDOWS)

    # STEP 2 - how synchronized was the market in each window?
    rows = []
    for end, graph in series.items():
        weights = [d["weight"] for _, _, d in graph.edges(data=True)]
        rows.append({"window_end": end.strftime("%Y-%m-%d"),
                     "mean_correlation": round(float(np.mean(weights)), 3),
                     "pairs_above_0.5": int(sum(w >= 0.5 for w in weights))})
    table = pd.DataFrame(rows)
    table.to_csv(os.path.join(folder, "windows.csv"), index=False)
    calm = table.loc[table["mean_correlation"].idxmin()]
    busy = table.loc[table["mean_correlation"].idxmax()]
    toolkit.step(2, 3, "Most synchronized window ends {0} (mean {1:+.2f}); "
                 "least ends {2} ({3:+.2f})".format(
                     busy["window_end"], busy["mean_correlation"],
                     calm["window_end"], calm["mean_correlation"]))

    # STEP 3 - pictures
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    ax.plot(table["window_end"], table["mean_correlation"], marker="o")
    ax.set_ylabel("mean correlation")
    ax.set_title("How much the market moves together")
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(folder, "synchronization.png"), dpi=150)
    plt.close(fig)
    builder.plotTemporalGraph(nFrames=6, path=os.path.join(folder,
                                                           "networks.png"))
    toolkit.step(3, 3, "Saved the table and two pictures")
    t = toolkit.Tutorial(folder, "The market changes over time",
                         intro="One correlation network per time window, "
                               "with Ivan's `CorrGraphs.temporalGraph` - a "
                               "temporal graph of the market.")
    t.section("Step 1 - One network per window", (
        "{0} windows of {1} each, spread over {2}. Each window gives one "
        "complete correlation network, like example 1.").format(
            WINDOWS, WINDOW, PERIOD))
    t.section("Step 2 - How synchronized was each window?", (
        "The most synchronized window ends on **{0}** (mean correlation "
        "{1:+.2f}), the least on **{2}** ({3:+.2f}).").format(
            busy["window_end"], busy["mean_correlation"],
            calm["window_end"], calm["mean_correlation"]))
    t.table(table, "windows.csv")
    t.image("synchronization.png", "Mean correlation per window: high = "
            "the market moves as one.")
    t.image("networks.png", "Six of the windows: the links change shape "
            "and strength over time.")
    print("      Results (CSV + PNG + tutorial): " + folder)
    print("      Read first: " + t.save())


if __name__ == "__main__":
    main()
