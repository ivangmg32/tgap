'''
IVAN 2 - How long should a correlation window be?

Ivan's CorrGraphs.temporalGraph computes correlations over a sliding window
(slidingWindowPeriod). A short window reacts fast but is noisy; a long one
is stable but blurs events. This tutorial builds the same market with three
window lengths and compares what each one sees.

    python examples/projects/ivan_window_length/main.py
'''
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))

import matplotlib                                            # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                              # noqa: E402
import numpy as np                                           # noqa: E402
import pandas as pd                                          # noqa: E402

from examples import toolkit                                 # noqa: E402

from finance.CorrGraphs import CorrGraphs                    # noqa: E402

# ============================== PARAMETERS ==============================
TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "JPM", "XOM", "JNJ"]
PERIOD = "5y"
WINDOWS = ["3mo", "6mo", "1y"]     # the window lengths to compare
GRAPHS = 20                        # networks per window length
# ========================================================================


def main(output=None):
    output = output or os.path.join(HERE, "output")
    t = toolkit.Tutorial(output, "How long should a correlation window be?",
                         intro="The same market seen through three window "
                               "lengths in Ivan's `CorrGraphs.temporalGraph`.")
    rows, curves = [], {}
    for index, window in enumerate(WINDOWS, 1):
        toolkit.step(index, len(WINDOWS) + 1,
                     "Networks with a {0} window".format(window))
        series = CorrGraphs(TICKERS).temporalGraph(PERIOD, window, GRAPHS)
        means = pd.Series({end: np.mean([d["weight"] for _, _, d in
                                         g.edges(data=True)])
                           for end, g in series.items()})
        curves[window] = means
        steps = means.diff().abs().dropna()
        rows.append({"window": window, "networks": len(series),
                     "mean_correlation": means.mean(),
                     "lowest": means.min(), "highest": means.max(),
                     "average_jump_between_networks": steps.mean()})
    table = pd.DataFrame(rows)
    table.round(4).to_csv(os.path.join(output, "comparison.csv"), index=False)

    fig, ax = plt.subplots(figsize=(8, 4))
    for window, means in curves.items():
        ax.plot(means.index, means.values, marker="o", markersize=3,
                label=window + " window")
    ax.set_ylabel("mean correlation")
    ax.set_title("Market synchronization, three window lengths")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(output, "windows.png"), dpi=150)
    plt.close(fig)
    calm = table.loc[table["average_jump_between_networks"].idxmin(),
                     "window"]
    toolkit.step(len(WINDOWS) + 1, len(WINDOWS) + 1,
                 "Smoothest: the {0} window".format(calm))

    t.section("What a window does", (
        "For every network, `temporalGraph` takes the daily returns inside "
        "one window (for example the last 6 months) and correlates every "
        "pair of stocks. {0} networks are spread evenly over {1}.").format(
            GRAPHS, PERIOD))
    t.section("The comparison")
    t.table(table.round(4), "comparison.csv")
    t.image("windows.png", "Mean correlation of each network, for each "
            "window length.")
    t.section("How to read it")
    t.bullets([
        "**Short windows** react quickly to events, but jump around: "
        "`average_jump_between_networks` is largest.",
        "**Long windows** are smooth but slow; a short crisis is averaged "
        "away.",
        "Overlapping windows share data: with {0} networks over {1}, "
        "neighbouring long windows are partly the SAME data, so they look "
        "alike for that reason too.".format(GRAPHS, PERIOD),
        "For TGAP, the window decides what one snapshot means - choose it "
        "before looking at explanations, like the threshold.",
    ])
    print("      Read first: " + t.save())


if __name__ == "__main__":
    main()
