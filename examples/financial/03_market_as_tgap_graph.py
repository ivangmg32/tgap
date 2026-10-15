'''
FINANCE 3 - Turning the market into a graph TGAP can explain.

Ivan's networks connect EVERY pair of stocks (weighted by correlation).
TGAP's concepts - bridge width, density, centralization, churn - are about
which ties EXIST, so we keep only strong ties: two stocks are tied in a
window when their correlation is at least THRESHOLD. Sectors are the
communities, so "bridge width" = strong co-movement ACROSS sectors.

The threshold matters. This example checks several and tells you which ones
give graphs TGAP can work with.

    python examples/financial/03_market_as_tgap_graph.py

Outputs: output/examples/financial/03_market_as_tgap_graph/
    threshold_check.csv    which thresholds are usable, and why
    graph_over_time.csv/.png   the chosen graph, window by window
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from examples import toolkit                                # noqa: E402
from finance.networks import (correlationNetworks,          # noqa: E402
                              sectorPartition, threshold, thresholdReport)
from finance.universe import IVAN_SECTORS                   # noqa: E402

# ============================== PARAMETERS ==============================
SECTORS = IVAN_SECTORS        # {ticker: sector}
FOCUS = "Technology"          # communities: this sector vs the rest
                              # (None = one community per sector)
PERIOD, WINDOW, WINDOWS = "5y", "6mo", 12
THRESHOLD = 0.3               # minimum correlation for a tie
# ========================================================================


def main():
    folder = os.path.join(toolkit.OUTPUT, "financial",
                          "03_market_as_tgap_graph")
    os.makedirs(folder, exist_ok=True)
    tickers = list(SECTORS)

    # STEP 1 - Ivan's weighted networks
    toolkit.step(1, 4, "Correlation networks for {0} stocks".format(
        len(tickers)))
    weighted, dates = correlationNetworks(tickers, PERIOD, WINDOW, WINDOWS)

    # STEP 2 - sectors become the communities
    partition = sectorPartition(tickers, SECTORS, FOCUS)
    toolkit.step(2, 4, "Communities: " + ", ".join(
        "{0} ({1})".format(label, len(group))
        for label, group in zip(partition.labels, partition)))

    # STEP 3 - which thresholds work?
    report = thresholdReport(weighted, partition)
    report.to_csv(os.path.join(folder, "threshold_check.csv"), index=False)
    toolkit.step(3, 4, "Threshold check (usable = TGAP can keep its "
                 "promises on these graphs):")
    for _, row in report.iterrows():
        print("        threshold {0:.1f}: {1:5.1f} ties per window   {2}".format(
            row["threshold"], row["mean_ties"],
            "usable" if row["usable"] else "not usable"))

    # STEP 4 - the chosen graph, window by window
    tied = threshold(weighted, THRESHOLD)
    overTime = toolkit._graphOverTime(tied, partition)
    overTime.insert(1, "window_end", dates)
    overTime.to_csv(os.path.join(folder, "graph_over_time.csv"), index=False)
    toolkit.saveGraphOverTime(overTime, folder, "threshold {0}".format(
        THRESHOLD))
    toolkit.step(4, 4, "With threshold {0}: ties per window {1}".format(
        THRESHOLD, list(overTime["ties"])))
    print("      Results (CSV + PNG): " + folder)


if __name__ == "__main__":
    main()
