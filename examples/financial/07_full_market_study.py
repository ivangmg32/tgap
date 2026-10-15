'''
FINANCE 7 - A full TGAP market study (the research workflow).

Everything together, at a realistic size: 30 large US stocks in 6 sectors,
5 years of prices, the threshold check, and the COMPLETE TGAP protocol used
for the eight real datasets - six models, five concepts, three deltas, both
directions, every result checked by the validity gates, plus a report.

Needs internet once (prices are downloaded and then cached) and the
'yfinance' library:  python run.py --with-finance

    python examples/financial/07_full_market_study.py

Outputs: output/examples/financial/07_full_market_study/
    report.md                 start here
    tgap_results.csv          every explanation, with validity flags
    threshold_check.csv       why this threshold
    figures/*.png             heatmap, validity map, trajectories, ...
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from examples import toolkit                                  # noqa: E402
from finance.networks import (correlationNetworks, prepare,   # noqa: E402
                              sectorPartition, thresholdReport)
from finance.universe import WIDE_SECTORS                     # noqa: E402

# ============================== PARAMETERS ==============================
SECTORS = WIDE_SECTORS        # 30 stocks, 6 sectors; edit freely
FOCUS = None                  # None = one community per sector
PERIOD, WINDOW, WINDOWS = "5y", "6mo", 12
THRESHOLD = 0.5               # usable for this universe (checked in step 2)
# ========================================================================


def main():
    import urllib.error
    folder = os.path.join(toolkit.OUTPUT, "financial", "07_full_market_study")
    os.makedirs(folder, exist_ok=True)
    tickers = list(SECTORS)

    # STEP 1 - prices and correlation networks (downloads once)
    toolkit.step(1, 4, "Prices and correlation networks for {0} stocks "
                 "(downloads once)".format(len(tickers)))
    try:
        weighted, _ = correlationNetworks(tickers, PERIOD, WINDOW, WINDOWS)
    except ModuleNotFoundError as missing:
        if getattr(missing, "name", "") != "yfinance":
            raise
        print("        Skipped: some prices are not cached yet and downloading "
              "needs 'yfinance'.\n        Run:  python run.py --with-finance"
              "   then this example again.")
        return
    except (urllib.error.URLError, TimeoutError, ConnectionError) as failure:
        print("        Skipped: no internet to download prices ({0}).".format(
            failure))
        return

    # STEP 2 - is the threshold usable?
    available = sorted(set().union(*(g.nodes() for g in weighted)))
    report = thresholdReport(weighted, sectorPartition(available, SECTORS,
                                                       FOCUS))
    report.to_csv(os.path.join(folder, "threshold_check.csv"), index=False)
    row = report[report["threshold"].round(2) == round(THRESHOLD, 2)]
    usable = bool(row["usable"].iloc[0]) if len(row) else None
    toolkit.step(2, 4, "Threshold {0}: {1}".format(
        THRESHOLD, {True: "usable", False: "NOT usable - see "
                    "threshold_check.csv", None: "not in the check table"}
        [usable]))

    # STEP 3 - the market as a TGAP dataset
    market = prepare("full_market_study", tickers, SECTORS, PERIOD, WINDOW,
                     WINDOWS, THRESHOLD, focus=FOCUS)
    toolkit.step(3, 4, "{0} stocks, {1} windows, communities {2}".format(
        len(market.meta["tickers"]), len(market.snapshots),
        "/".join(str(len(c)) for c in market.communities)))

    # STEP 4 - the complete, validity-gated TGAP protocol
    toolkit.step(4, 4, "Running the full TGAP protocol (about a minute)")
    from realdata.run_real_data import runPrepared
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        summary = runPrepared(market, market.meta["analysis_mode"], folder)
    print("        {0} of {1} explanations passed the validity checks".format(
        summary["valid_rows"], summary["explanation_rows"]))
    t = toolkit.Tutorial(folder, "A full TGAP market study",
                         intro="{0} stocks in {1} sectors, the complete "
                               "validity-gated TGAP protocol.".format(
                                   len(market.meta["tickers"]),
                                   len(market.communities)))
    t.section("Step 1 - Prices and networks", (
        "{0} correlation windows of {1} over {2}; ties = correlation >= "
        "{3}.").format(WINDOWS, WINDOW, PERIOD, THRESHOLD))
    t.section("Step 2 - The threshold check")
    t.table(report, "threshold_check.csv")
    t.section("Step 3 - The full protocol", (
        "Six models x five concepts x three deltas x two directions = 180 "
        "experiments. **{0}** passed the validity checks; the rest are "
        "kept in tgap_results.csv but flagged and left out of any "
        "conclusion.").format(summary["valid_rows"]))
    t.text("Read **report.md** next: it is the full report of this run, in "
           "the same format as the eight real datasets.")
    for figure, caption in (
            ("figures/explanation_heatmap.png", "Which model responds to "
             "which concept."),
            ("figures/validity_map.png", "Which experiments passed the "
             "validity checks.")):
        if os.path.exists(os.path.join(folder, figure)):
            t.image(figure, caption)
    print("      Results (report.md + CSVs + figures + tutorial): " + folder)
    print("      Read first: " + t.save())


if __name__ == "__main__":
    main()
