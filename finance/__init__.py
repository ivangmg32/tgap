'''
Financial markets in TGAP: stock correlation networks over time.

Ivan's original work (unchanged in purpose):
    Cache.py                      daily prices from Yahoo Finance, cached per ticker
    CorrGraphs.py                 correlation networks, one per time window
    experimentationDatamining.py  four statistical research questions (RQ1-RQ4)

The TGAP bridge (new):
    universe.py     stock lists and their sectors (Ivan's 8; a wider 30)
    networks.py     correlation networks -> thresholded co-movement graphs
                    with sector communities -> a TGAP dataset
    run_finance.py  the full, validity-gated TGAP protocol on a market

    python -m finance.run_finance                 # Ivan's 8 stocks, offline
    python -m finance.run_finance --wide          # 30 stocks, 6 sectors
    python -m finance.experimentationDatamining   # Ivan's RQ1-RQ4

Step-by-step examples: examples/financial/.
Outputs: output/finance/ (see paths.py).
'''
