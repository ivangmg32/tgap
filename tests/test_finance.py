'''
Financial markets in TGAP (finance/ and examples/financial/).

Offline: uses only the prices of Ivan's eight stocks committed in
finance/Cache. Writes only to temporary folders.
'''

import os
import runpy
import shutil
import tempfile
import unittest

import networkx as nx
import numpy as np

import paths
from examples import toolkit
from finance.Cache import Cache
from finance.networks import (correlationNetworks, prepare, sectorPartition,
                              threshold, thresholdReport)
from finance.universe import IVAN_SECTORS, IVAN_TICKERS

FINANCIAL = os.path.join(paths.ROOT, "examples", "financial")


class TestCachedPrices(unittest.TestCase):

    def testDatesAreRealDatesNotText(self):
        ''' Regression: the cache mixes -04:00 and -05:00 offsets, which
        parse_dates left as TEXT, so CorrGraphs.temporalGraph crashed on
        every run that read the cache. '''
        history = Cache("5y").history("AAPL")
        self.assertTrue(str(history.index.dtype).startswith("datetime64"))
        self.assertIsNotNone(history.index.tz)

    def testCachedPricesNeedNoDownloadLibrary(self):
        ''' The cached tickers must load even without yfinance. '''
        for ticker in IVAN_TICKERS:
            self.assertFalse(Cache("5y").history(ticker).empty, ticker)


class TestNetworksBridge(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.weighted, cls.dates = correlationNetworks(IVAN_TICKERS, "5y",
                                                      "6mo", 12)

    def testIvansNetworksAreCompleteAndWeighted(self):
        for graph in self.weighted:
            self.assertEqual(graph.number_of_edges(), 28)     # 8 choose 2
            self.assertAlmostEqual(nx.density(graph), 1.0)
        self.assertEqual(len(self.dates), len(self.weighted))

    def testThresholdKeepsNodesAndOnlyStrongTies(self):
        tied = threshold(self.weighted, 0.3)
        for full, graph in zip(self.weighted, tied):
            self.assertEqual(set(graph.nodes()), set(IVAN_TICKERS))
            for u, v in graph.edges():
                self.assertGreaterEqual(full[u][v]["weight"], 0.3)
        absolute = threshold(self.weighted, 0.3, sign="absolute")
        self.assertGreaterEqual(sum(g.number_of_edges() for g in absolute),
                                sum(g.number_of_edges() for g in tied))

    def testSectorPartitions(self):
        everyOne = sectorPartition(IVAN_TICKERS, IVAN_SECTORS)
        self.assertEqual(len(everyOne), 5)
        focus = sectorPartition(IVAN_TICKERS, IVAN_SECTORS, "Technology")
        self.assertEqual(list(focus.labels), ["Technology", "Other"])
        self.assertEqual(sorted(len(c) for c in focus), [4, 4])
        with self.assertRaises(ValueError):
            sectorPartition(IVAN_TICKERS, IVAN_SECTORS, "Utilities")
        with self.assertRaises(ValueError):
            sectorPartition(["AAPL", "TSLA"], IVAN_SECTORS)

    def testThresholdCheckFindsTheUsableSetting(self):
        report = thresholdReport(self.weighted, sectorPartition(
            IVAN_TICKERS, IVAN_SECTORS, "Technology"))
        usable = set(report.loc[report["usable"], "threshold"].round(2))
        self.assertIn(0.3, usable)
        self.assertNotIn(0.7, usable)          # mostly empty windows

    def testPreparedLikeEveryRealDataset(self):
        market = prepare("test", IVAN_TICKERS, IVAN_SECTORS, minimum=0.3,
                         focus="Technology")
        self.assertEqual(len(market.snapshots), 12)
        self.assertFalse(market.preprocessing[
            "future_information_used_for_node_selection"])
        for key in ("raw_nodes", "retained_nodes", "raw_events",
                    "retained_events", "graph_nodes_are", "snapshot_count"):
            self.assertIn(key, market.meta)


class TestFullProtocol(unittest.TestCase):

    def testRunPreparedOnTheMarket(self):
        from realdata.run_real_data import runPrepared
        import contextlib
        import io
        directory = tempfile.mkdtemp(prefix="tgap-finance-")
        try:
            market = prepare("test", IVAN_TICKERS, IVAN_SECTORS, minimum=0.3,
                             focus="Technology")
            with contextlib.redirect_stdout(io.StringIO()):
                summary = runPrepared(market, market.meta["analysis_mode"],
                                      directory)
            for name in ("tgap_results.csv", "report.md", "summary.json"):
                self.assertTrue(os.path.exists(os.path.join(directory, name)))
            self.assertGreater(summary["valid_rows"], 0)
        finally:
            shutil.rmtree(directory, ignore_errors=True)


class TestIvansStudy(unittest.TestCase):

    def testRq4FlagsAStatisticItCannotTest(self):
        ''' Permuting weights cannot change their mean: the null equals the
        observation by construction, so RQ4 must say "not testable" instead
        of reporting rounding noise as a finding. '''
        from finance.experimentationDatamining import (
            experiment_rq4_null_model)
        from finance.CorrGraphs import CorrGraphs
        series = CorrGraphs(IVAN_TICKERS).temporalGraph("5y", "6mo", 5)
        result = experiment_rq4_null_model(series, "mean_abs_corr",
                                           iterations=20)
        self.assertFalse(result["testable"])
        self.assertTrue(np.isnan(result["standardized_difference"]))
        self.assertIn("NOT TESTABLE", result["interpretation_note"])

    def testNoAvailableStatisticIsTestableOnCompleteGraphs(self):
        ''' The advice in the note must be true: on complete graphs every
        built-in statistic is invariant to permuting the weights. '''
        from finance.experimentationDatamining import (
            experiment_rq4_null_model)
        from finance.CorrGraphs import CorrGraphs
        series = CorrGraphs(IVAN_TICKERS).temporalGraph("5y", "6mo", 4)
        for statistic in ("mean_abs_corr", "mean_signed_corr", "density",
                          "strong_edge_fraction", "clustering",
                          "mean_strength"):
            self.assertFalse(experiment_rq4_null_model(
                series, statistic, iterations=10)["testable"], statistic)


class TestFinancialExamples(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="tgap-fin-examples-")
        self.saved = toolkit.OUTPUT
        toolkit.OUTPUT = self.directory

    def tearDown(self):
        toolkit.OUTPUT = self.saved
        shutil.rmtree(self.directory, ignore_errors=True)

    def _run(self, filename, expected):
        runpy.run_path(os.path.join(FINANCIAL, filename),
                       run_name="example_under_test")["main"]()
        folder = os.path.join(self.directory, "financial",
                              filename[:-3])
        for name in expected:
            self.assertTrue(os.path.exists(os.path.join(folder, name)), name)

    def testStockCorrelations(self):
        self._run("01_stock_correlations.py",
                  ("correlations.csv", "network.png"))

    def testCorrelationsOverTime(self):
        self._run("02_correlations_over_time.py",
                  ("windows.csv", "synchronization.png", "networks.png"))

    def testMarketAsTgapGraph(self):
        self._run("03_market_as_tgap_graph.py",
                  ("threshold_check.csv", "graph_over_time.png"))

    def testExplainAMarketModel(self):
        self._run("04_explain_a_market_model.py",
                  ("explanation.csv", "explanation.png", "sensitivity.png"))

    def testYourOwnMarketModel(self):
        self._run("05_your_own_market_model.py",
                  ("explanation.csv", "explanation.png"))

    def testEveryFinancialExampleIsCovered(self):
        numbered = sorted(n for n in os.listdir(FINANCIAL)
                          if n[:2].isdigit() and n.endswith(".py"))
        self.assertEqual(len(numbered), 7)


if __name__ == "__main__":
    unittest.main()
