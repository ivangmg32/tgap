# Financial-market examples — from two stocks to a full study

Stock markets as temporal graphs: each stock is a node, and two stocks are
tied when their prices move together. These seven scripts go step by step
from "which stocks move together?" to the complete research workflow. Each
has a **PARAMETERS** block at the top: change it, run, look at the results.

```sh
python examples/financial/01_stock_correlations.py     # one example
python run.py examples                                 # all examples
```

| step | file | what you learn | needs |
|---|---|---|---|
| 1 | [`01_stock_correlations.py`](01_stock_correlations.py) | which stocks move together (one correlation network) | nothing extra |
| 2 | [`02_correlations_over_time.py`](02_correlations_over_time.py) | the market changes: one network per time window | nothing extra |
| 3 | [`03_market_as_tgap_graph.py`](03_market_as_tgap_graph.py) | turn correlations into a graph TGAP can explain, and pick a threshold | nothing extra |
| 4 | [`04_explain_a_market_model.py`](04_explain_a_market_model.py) | explain a market forecast with TGAP | nothing extra |
| 5 | [`05_your_own_market_model.py`](05_your_own_market_model.py) | explain **your own** market model (a systemic-risk score) | nothing extra |
| 6 | [`06_ivans_datamining_study.py`](06_ivans_datamining_study.py) | Ivan's statistical study, RQ1–RQ4, with your settings | nothing extra |
| 7 | [`07_full_market_study.py`](07_full_market_study.py) | the full research workflow: 30 stocks, 6 sectors, every result validity-checked, a report | internet once + `python run.py --with-finance` |

Examples 1–6 use Ivan's eight stocks (AAPL, MSFT, GOOGL, AMZN, NVDA, JPM,
XOM, JNJ), whose prices are stored in the repository, so they work offline.
Results go to `output/examples/financial/<example>/`.

## The idea in one picture

```text
daily prices --> returns --> correlation per window      (Ivan: CorrGraphs)
             --> keep pairs with correlation >= threshold (a "tie")
             --> sectors become the communities
             --> TGAP explains a model of this temporal graph
```

With sectors as communities, TGAP's concepts read naturally:

| concept | in a market |
|---|---|
| bridge width | strong co-movement **across** sectors (coupling, contagion) |
| density | overall synchronization of the market |
| centralization | one stock driving the co-movement |
| churn | how much the co-movement pattern changes over time |
| bridge trend | is cross-sector coupling rising or falling? |

## Choosing the threshold (important)

Ivan's networks connect every pair of stocks, and TGAP cannot change a graph
that already has every tie. The threshold decides which ties exist, so it
must be fixed **before** looking at explanations. Example 3 (or
`python -m finance.run_finance --check`) shows which thresholds are usable:

- too low: almost every pair is tied, and TGAP cannot keep its promise of
  changing one concept while holding the number of ties fixed;
- too high: windows with no ties at all.

Measured: **0.3** for Ivan's 8 stocks (Technology vs the rest), **0.5** for
the 30-stock universe (6 sectors).

## Your own stocks

Change `SECTORS` in any example to your own `{ticker: sector}` dictionary,
e.g. `{"TSLA": "Auto", "F": "Auto", "GM": "Auto", "AAPL": "Tech", ...}`.
New tickers are downloaded once from Yahoo Finance (needs
`python run.py --with-finance` and internet) and then cached in
`finance/Cache/`. Give at least two stocks per sector, ideally four or more:
a sector of one stock has no ties inside it, which limits what TGAP can test.

## Where the code lives

`finance/` — Ivan's `Cache.py`, `CorrGraphs.py` and
`experimentationDatamining.py`, plus the TGAP bridge `networks.py`,
`universe.py` and `run_finance.py` (see [`finance/__init__.py`](../../finance/__init__.py)).
