'''
IVAN 1 - Prices, returns and risk with Ivan's Cache.

Ivan's Cache.py fetches daily prices from Yahoo Finance once and keeps them
as CSV files in finance/Cache, so later runs are instant and work offline.
This tutorial loads the cached prices, turns them into daily returns (the
input of every correlation network), and compares the stocks' growth and
risk.

    python examples/projects/ivan_price_cache/main.py
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

from finance.Cache import Cache                              # noqa: E402

# ============================== PARAMETERS ==============================
TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "JPM", "XOM", "JNJ"]
PERIOD = "5y"              # cached: 5y and 6mo
VOLATILITY_WINDOW = 30     # trading days in the rolling risk measure
# ========================================================================


def main(output=None):
    output = output or os.path.join(HERE, "output")
    t = toolkit.Tutorial(output, "Prices, returns and risk - Ivan's Cache",
                         intro="How Ivan's Cache provides prices, and how "
                               "prices become the daily returns that every "
                               "correlation network is built from.")

    # STEP 1 - prices from the cache
    toolkit.step(1, 4, "Reading {0} of prices for {1} stocks from the "
                 "cache".format(PERIOD, len(TICKERS)))
    cache = Cache(yfDuration=PERIOD)
    prices = pd.DataFrame({tk: cache.history(tk)["Close"] for tk in TICKERS})
    prices = prices.dropna()
    prices.round(4).to_csv(os.path.join(output, "prices.csv"))
    t.section("Step 1 - Prices from the cache", (
        "`Cache(yfDuration=\"{0}\")` looks for `finance/Cache/<TICKER>_{0}.csv`. "
        "If the file exists it is read (offline); if not, it is downloaded "
        "from Yahoo Finance once and saved. We got **{1} trading days** for "
        "**{2} stocks**, from {3} to {4}.\n\nNote: the cached dates mix two "
        "UTC offsets (summer and winter time). Cache.py converts them to "
        "real dates; before that fix, every run that read the cache "
        "failed.").format(PERIOD, len(prices), len(TICKERS),
                          prices.index[0].date(), prices.index[-1].date()))
    t.table(prices.tail(5).round(2).reset_index().rename(
        columns={"index": "date", "Date": "date"}),
        "The last five days of prices.csv")

    # STEP 2 - growth
    growth = prices / prices.iloc[0]
    fig, ax = plt.subplots(figsize=(8, 4))
    for ticker in TICKERS:
        ax.plot(growth.index, growth[ticker], label=ticker, linewidth=1)
    ax.set_ylabel("value of 1 dollar invested")
    ax.set_title("Growth over {0}".format(PERIOD))
    ax.legend(fontsize=7, ncol=4)
    fig.tight_layout()
    fig.savefig(os.path.join(output, "growth.png"), dpi=150)
    plt.close(fig)
    toolkit.step(2, 4, "Growth: best {0} (x{1:.1f}), worst {2} (x{3:.2f})"
                 .format(growth.iloc[-1].idxmax(), growth.iloc[-1].max(),
                         growth.iloc[-1].idxmin(), growth.iloc[-1].min()))
    t.section("Step 2 - Growth", "Dividing every price by its first value "
              "shows what one dollar invested at the start became.")
    t.image("growth.png", "Value of one dollar invested in each stock.")

    # STEP 3 - returns
    returns = prices.pct_change().dropna()
    returns.round(6).to_csv(os.path.join(output, "returns.csv"))
    summary = pd.DataFrame({
        "stock": TICKERS,
        "mean_daily_return_pct": [100 * returns[tk].mean() for tk in TICKERS],
        "annual_volatility_pct": [100 * returns[tk].std() * np.sqrt(252)
                                  for tk in TICKERS],
    }).sort_values("annual_volatility_pct")
    summary.round(3).to_csv(os.path.join(output, "risk_summary.csv"),
                            index=False)
    toolkit.step(3, 4, "Daily returns: calmest {0}, most volatile {1}"
                 .format(summary.iloc[0]["stock"], summary.iloc[-1]["stock"]))
    t.section("Step 3 - Daily returns", "A **return** is the day-to-day "
              "change in price (+0.01 = +1%). Correlation networks compare "
              "returns, not prices: two stocks that both rise for years "
              "have correlated PRICES even if their daily moves are "
              "unrelated. **Volatility** - the spread of the returns, "
              "scaled to a year - is the usual measure of risk.")
    t.table(summary.round(3), "risk_summary.csv")

    # STEP 4 - rolling risk
    rolling = returns.rolling(VOLATILITY_WINDOW).std() * np.sqrt(252) * 100
    fig, ax = plt.subplots(figsize=(8, 4))
    for ticker in TICKERS:
        ax.plot(rolling.index, rolling[ticker], label=ticker, linewidth=0.8)
    ax.set_ylabel("annualized volatility (%)")
    ax.set_title("Risk over time ({0}-day window)".format(VOLATILITY_WINDOW))
    ax.legend(fontsize=7, ncol=4)
    fig.tight_layout()
    fig.savefig(os.path.join(output, "volatility.png"), dpi=150)
    plt.close(fig)
    toolkit.step(4, 4, "Saved prices, returns, risk table and two charts")
    t.section("Step 4 - Risk changes over time", "Risk is not constant: "
              "calm periods alternate with turbulent ones, and in turbulent "
              "periods stocks tend to move together. That is exactly what "
              "the correlation networks of the next tutorials capture.")
    t.image("volatility.png", "Rolling annualized volatility.")
    t.section("Files in this folder")
    t.bullets(["`prices.csv` - daily closing prices",
               "`returns.csv` - daily returns",
               "`risk_summary.csv` - mean return and volatility per stock",
               "`growth.png`, `volatility.png`"])
    print("      Read first: " + t.save())


if __name__ == "__main__":
    main()
