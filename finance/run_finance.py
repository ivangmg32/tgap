'''
Run TGAP on a stock market, with the same protocol as the real datasets.

    python -m finance.run_finance                          # Ivan's 8 stocks
    python -m finance.run_finance --wide                   # 30 stocks, 6 sectors
    python -m finance.run_finance --threshold 0.4 --focus Technology
    python -m finance.run_finance --check                  # which thresholds work

Writes output/finance/<name>/ with exactly the files a real dataset gets
(tgap_results.csv with validity flags, feasibility, leakage, diagnostics,
report.md, figures, plus insight.md with the paper-style pictures drawn
on the stock network) - realdata.run_real_data.runPrepared does the work, so
finance is explained, gated and reported identically to every other dataset.
'''

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths                                               # noqa: E402

from .networks import (correlationNetworks, prepare,       # noqa: E402
                       sectorPartition, thresholdReport)
from .universe import (IVAN_SECTORS, IVAN_TICKERS,         # noqa: E402
                       WIDE_SECTORS, WIDE_TICKERS)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m finance.run_finance",
        description="TGAP on stock correlation networks.")
    parser.add_argument("--wide", action="store_true",
                        help="30 stocks in 6 sectors (downloads once) instead "
                             "of Ivan's 8 cached stocks")
    parser.add_argument("--period", default="5y")
    parser.add_argument("--window", default="6mo")
    parser.add_argument("--snapshots", type=int, default=12)
    parser.add_argument("--threshold", type=float, default=None,
                        help="minimum correlation for a tie (default: 0.3 "
                             "for 8 stocks, 0.5 for the wide universe)")
    parser.add_argument("--focus", default=None,
                        help="two communities: this sector vs the rest")
    parser.add_argument("--check", action="store_true",
                        help="only report which thresholds are usable")
    args = parser.parse_args(argv)

    tickers, sectors = ((WIDE_TICKERS, WIDE_SECTORS) if args.wide
                        else (IVAN_TICKERS, IVAN_SECTORS))
    name = "wide_market" if args.wide else "ivan_market"
    # With 8 stocks, 4 of the 5 sectors hold ONE stock: a single-stock group
    # has no internal ties, so the bridge transformations can never keep
    # their edge-count promise (measured: unusable at every threshold).
    # Technology vs the rest (4 vs 4) is the grouping that works.
    focus = args.focus if args.focus is not None else (
        None if args.wide else "Technology")
    minimum = args.threshold if args.threshold is not None else (
        0.5 if args.wide else 0.3)

    if args.check:
        graphs, _ = correlationNetworks(tickers, args.period, args.window,
                                        args.snapshots)
        available = sorted(set().union(*(g.nodes() for g in graphs)))
        report = thresholdReport(graphs,
                                 sectorPartition(available, sectors, focus))
        print(report.to_string(index=False))
        return report

    from realdata.run_real_data import runPrepared
    prepared = prepare(name, tickers, sectors, args.period, args.window,
                       args.snapshots, minimum, focus=focus)
    print("=" * 72)
    print("FINANCE: {0}  ({1} stocks, {2} windows, threshold {3})".format(
        name, len(prepared.meta["tickers"]), len(prepared.snapshots),
        minimum))
    print("=" * 72)
    directory = os.path.join(paths.FINANCE, name)
    result = runPrepared(prepared, prepared.meta["analysis_mode"], directory)

    # The paper-style pictures drawn on the stock network itself (where and
    # when the models react). A failure here never loses the main results.
    try:
        from .insight import insightFigures
        print("  drawing the paper-style pictures (stocks, ties, windows) ...")
        insightFigures(prepared, directory)
        with open(os.path.join(directory, "report.md"), "a",
                  encoding="utf-8") as handle:
            handle.write("\n**More pictures:** which stocks and ties each "
                         "model leans on, and in which window - see "
                         "[insight.md](insight.md).\n")
        print("  wrote {0}".format(os.path.join(directory, "insight.md")))
    except Exception as error:                     # noqa: BLE001
        print("  (could not draw the insight pictures: {0}: {1})".format(
            type(error).__name__, error))
    return result


if __name__ == "__main__":
    main()
