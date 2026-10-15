'''
From stock prices to a TGAP temporal graph.

Ivan's CorrGraphs builds, for each time window, a COMPLETE weighted graph:
every pair of stocks is joined by an edge whose weight is the correlation of
their daily returns. TGAP's concepts (bridge width, density, centralization,
churn, bridge trend) work on which ties EXIST, and on a complete graph every
tie exists - nothing can be added, rewired or churned, and density is 1 in
every window. So TGAP needs one extra, explicit step:

    prices --(Ivan: CorrGraphs.temporalGraph)--> weighted complete graphs
           --(threshold: keep correlation >= t)--> "co-movement" graphs
           --(sectors)--> communities  -->  TGAP

Two stocks are TIED in a window when their returns moved together strongly
(correlation >= threshold). Sectors are the communities, so:

    bridge width   = strong co-movement ACROSS sectors (contagion / coupling)
    density        = overall market synchronization
    centralization = one stock driving the co-movement
    churn          = how much the co-movement pattern changes over time

The threshold is a modelling choice and must be fixed BEFORE looking at
explanations. thresholdReport() shows, for several thresholds, whether the
resulting graphs are usable (enough ties, no empty windows, the edge-count
promise of the bridge transformations can be kept).
'''

import os
import sys

import networkx as nx
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import (                                         # noqa: E402
    BridgeWidthTransformation, Partition, edgeCountFeasibility,
    interCommunityEdges,
)
from realdata.adapters.base import (                       # noqa: E402
    PreparedDataset, TEMPORAL_EVALUATION,
)

from .CorrGraphs import CorrGraphs                         # noqa: E402
from .universe import IVAN_SECTORS                         # noqa: E402


def correlationNetworks(tickers, period="5y", window="6mo", snapshots=12,
                        quiet=True):
    ''' Ivan's temporal correlation networks, unchanged: one complete
    weighted graph per window, oldest first, with each window's end date.

    period   : how much price history (Yahoo Finance style: 1y, 2y, 5y, 10y)
    window   : length of each correlation window (30d, 3mo, 6mo, 1y)
    snapshots: how many windows, spread evenly over the history

    Returns (graphs, endDates). '''
    builder = CorrGraphs(list(tickers))
    if quiet:
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            series = builder.temporalGraph(historicPeriod=period,
                                           slidingWindowPeriod=window,
                                           approxGraphs=int(snapshots))
        for line in captured.getvalue().splitlines():
            if line.startswith(("No valid data", "No prices found")):
                print("  " + line)
    else:
        series = builder.temporalGraph(historicPeriod=period,
                                       slidingWindowPeriod=window,
                                       approxGraphs=int(snapshots))
    graphs = list(series)
    if len(graphs) < 2:
        raise ValueError(
            "Only {0} correlation window(s) could be built from {1} of price "
            "history with {2} windows. Use a longer PERIOD or a shorter "
            "WINDOW.".format(len(graphs), period, window))
    dates = [pd.Timestamp(d).strftime("%Y-%m-%d") for d in series.index]
    return graphs, dates


def threshold(graphs, minimum=0.3, sign="positive"):
    ''' Keep a tie only where the correlation is strong.

    sign="positive": correlation >= minimum (stocks moving TOGETHER - the
                     usual reading of market synchronization and contagion)
    sign="absolute": |correlation| >= minimum (also strong opposite moves)

    Every stock stays in every snapshot (isolated when it has no strong
    tie), because TGAP keeps the set of nodes fixed. '''
    if sign not in ("positive", "absolute"):
        raise ValueError("sign must be 'positive' or 'absolute'")
    nodes = sorted(set().union(*(g.nodes() for g in graphs)))
    result = []
    for graph in graphs:
        tied = nx.Graph()
        tied.add_nodes_from(nodes)
        for u, v, data in graph.edges(data=True):
            weight = float(data.get("weight", 0.0))
            value = weight if sign == "positive" else abs(weight)
            if value >= minimum:
                tied.add_edge(u, v)
        result.append(tied)
    return result


def sectorPartition(tickers, sectors=None, focus=None):
    ''' Communities from sector labels (a static attribute of each company,
    so choosing them uses no information from the price data).

    focus=None         one community per sector
    focus="Technology" two communities: that sector versus everything else
                       (fewer, larger groups - more robust with few stocks)
    '''
    sectors = dict(IVAN_SECTORS if sectors is None else sectors)
    missing = [t for t in tickers if t not in sectors]
    if missing:
        raise ValueError("No sector given for: " + ", ".join(missing) +
                         ". Add them to SECTORS.")
    if focus is not None:
        inside = {t for t in tickers if sectors[t] == focus}
        if not inside:
            raise ValueError("No stock belongs to the sector {0!r}. Sectors "
                             "present: {1}".format(focus, sorted(
                                 {sectors[t] for t in tickers})))
        outside = set(tickers) - inside
        if not outside:
            raise ValueError("Every stock is in {0!r}; nothing to compare "
                             "it with.".format(focus))
        return Partition([inside, outside], labels=[focus, "Other"])
    names = sorted({sectors[t] for t in tickers})
    if len(names) < 2:
        raise ValueError("All stocks are in one sector; TGAP needs at least "
                         "two communities.")
    return Partition([{t for t in tickers if sectors[t] == n} for n in names],
                     labels=names)


def thresholdReport(graphs, partition, thresholds=(0.2, 0.3, 0.4, 0.5, 0.6,
                                                   0.7), sign="positive"):
    ''' Is each threshold usable for TGAP? One row per threshold.

    usable requires: no empty window, and the bridge transformations able to
    keep their edge-count promise for a +-10% nudge. A window with NO
    cross-sector tie is allowed - sectors genuinely decouple in calm markets,
    and TGAP handles a zero-width bridge - but it is counted, because a
    relative change of a zero bridge is not defined for that window. '''
    rows = []
    for t in thresholds:
        tied = threshold(graphs, t, sign)
        ties = [g.number_of_edges() for g in tied]
        bridges = [len(interCommunityEdges(g, partition)) for g in tied]
        promise = all(
            edgeCountFeasibility(tied, BridgeWidthTransformation(partition),
                                 d, partition)["feasible"]
            for d in (0.1, -0.1))
        empty = sum(1 for n in ties if n == 0)
        usable = bool(empty == 0 and promise)
        rows.append({
            "threshold": t,
            "mean_ties": round(float(np.mean(ties)), 1),
            "min_ties": int(min(ties)),
            "empty_windows": int(empty),
            "min_cross_sector_ties": int(min(bridges)),
            "windows_without_cross_ties": int(sum(1 for b in bridges
                                                  if b == 0)),
            "edge_count_promise_kept": promise,
            "usable": usable,
        })
    return pd.DataFrame(rows)


def prepare(name="market", tickers=None, sectors=None, period="5y",
            window="6mo", snapshots=12, minimum=0.3, sign="positive",
            focus=None):
    ''' A TGAP-ready dataset from stock prices, in the same form as the
    eight real datasets (realdata.adapters), so the full real-data protocol
    - validity gating, six models, leakage, report, figures - runs on it
    unchanged (see finance/run_finance.py). '''
    sectors = dict(IVAN_SECTORS if sectors is None else sectors)
    tickers = list(tickers if tickers is not None else sectors)
    weighted, dates = correlationNetworks(tickers, period, window, snapshots)
    available = sorted(set().union(*(g.nodes() for g in weighted)))
    partition = sectorPartition(available, sectors, focus)
    tied = threshold(weighted, minimum, sign)

    pairs = sum(g.number_of_edges() for g in weighted)
    kept = sum(g.number_of_edges() for g in tied)
    preprocessing = {
        "source": "Yahoo Finance daily closing prices (cached in finance/Cache)",
        "raw_nodes": len(tickers),
        "retained_nodes": len(available),
        "nodes_retained_pct": round(100 * len(available) / len(tickers), 2),
        "raw_events": int(pairs),
        "retained_events": int(kept),
        "events_retained_pct": round(100 * kept / pairs, 2) if pairs else 0.0,
        "event_definition": "a stock pair in one window; retained when its "
                            "correlation passes the threshold",
        "price_history": period,
        "correlation_window": window,
        "windows": len(tied),
        "window_end_dates": dates,
        "correlation_threshold": minimum,
        "threshold_sign": sign,
        "selection_period": "none - tickers chosen by the user in advance",
        "evaluation_period": "{0} .. {1}".format(dates[0], dates[-1]),
        "selection_fraction_of_span": 0.0,
        "node_selection_mode": "user_chosen_tickers",
        "future_information_used_for_node_selection": False,
        "community_mode": "sector_labels" + (
            "" if focus is None else " ({0} vs other)".format(focus)),
        "partition_sizes": [len(c) for c in partition],
        "partition_labels": list(partition.labels),
        "note": "Correlation windows overlap when the window is longer than "
                "the spacing between window ends; consecutive snapshots then "
                "share part of their data.",
    }
    meta = {
        "dataset": name,
        "description": "Stock co-movement networks: two stocks are tied in "
                       "a window when the correlation of their daily returns "
                       "is at least {0} ({1}). Communities are sectors."
                       .format(minimum, sign),
        "graph_nodes_are": "stocks (tickers)",
        "graph_edges_are": "strong return correlation within one window",
        "snapshot_count": len(tied),
        "snapshot_interval": "{0} correlation windows, ends spread evenly "
                             "over {1}".format(window, period),
        # Retention counts, side by side (the report reads them here).
        **{k: preprocessing[k] for k in (
            "raw_nodes", "retained_nodes", "nodes_retained_pct",
            "raw_events", "retained_events", "events_retained_pct")},
        "analysis_mode": TEMPORAL_EVALUATION,
        "family": "financial correlation network (thresholded)",
        "domain": "stock market",
        "tickers": available,
        "sectors": {t: sectors[t] for t in available},
        "edge_weight_used": False,
        "edge_weight_available": "correlation (used only for the threshold)",
        "edge_sign_used": sign == "absolute",
    }
    return PreparedDataset(name, tied, partition, dates, meta, preprocessing)
