# contrib/

Code that lives in this repository but is **not part of the TGAP pipeline**.
Nothing in `core/`, `realdata/`, `experiments/` or `tests/` imports from here.

| folder | what it is | author |
|---|---|---|
| `finance/` | Temporal stock-correlation graphs from Yahoo Finance (`CorrGraphs.py`, `Cache.py`) and a data-mining experiment over them (`experimentationDatamining.py`, results in `resultsDatamining/`). Needs `yfinance`, which is not in `requirements.txt`. | Iván García-Magariño |
| `drafts/` | Early NetworkX sketch of a DAO graph. | Iván García-Magariño |

Run the finance experiment from its own folder, because its modules import
each other by bare name:

```bash
cd contrib/finance
python experimentationDatamining.py --period 5y --window 6mo --graphs 20
```

The cache and results folders are resolved relative to the scripts, so the
paths do not depend on where you run them from.
