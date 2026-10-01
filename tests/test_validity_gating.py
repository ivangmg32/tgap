'''
Tests for validity gating, including the TGN path.

The scientific rule these protect is simple and absolute: an experiment that
failed its own invariant must never reach a published aggregate. It must
still be VISIBLE in the raw output - hiding failures is as bad as using them
- but it must not be summable.

The TGN runner previously had no gating at all: its rows carried no
`feasible`, `transformation_status` or `valid_for_analysis` column, so they
were aggregated as though every perturbation had succeeded. These tests
assert it now uses the SAME protocol as the metric-model pipeline, not a
second implementation that could drift.
'''

import json
import os
import unittest

import pandas as pd

RESULTS = os.path.join("output", "real_data_v2")
TGN = os.path.join(RESULTS, "tgn", "email_eu_core")
MAIN = os.path.join(RESULTS, "temporal_evaluation")

VALIDITY_COLUMNS = ("feasible", "infeasible_reason", "edge_count_before",
                    "edge_count_after", "edge_count_preserved",
                    "snapshots_violating_edge_count",
                    "transformation_status", "valid_for_analysis")

VALID_STATUSES = {"ok", "edge_count_infeasible", "saturated",
                  "wrong_direction", "no_property_change"}


def available(path):
    return os.path.exists(path)


@unittest.skipUnless(available(os.path.join(TGN, "tgap_results.csv")),
                     "TGN results not generated; run realdata.run_tgn")
class TestTgnValidityGating(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.frame = pd.read_csv(os.path.join(TGN, "tgap_results.csv"))
        with open(os.path.join(TGN, "summary.json"), encoding="utf-8") as h:
            cls.summary = json.load(h)

    def testTgnRowsCarryEveryValidityField(self):
        for column in VALIDITY_COLUMNS:
            self.assertIn(column, self.frame.columns,
                          f"TGN results lack {column}")

    def testStatusVocabularyMatchesTheMainPipeline(self):
        ''' The same status strings, so the two pipelines can be read
        together without a translation table. '''
        self.assertTrue(set(self.frame["transformation_status"])
                        <= VALID_STATUSES)

    def testInfeasibleRowsCarryNoNumbers(self):
        ''' Blanked on purpose: a number that failed its invariant cannot be
        used by accident if it was never written. '''
        infeasible = self.frame[
            self.frame["transformation_status"] == "edge_count_infeasible"]
        if infeasible.empty:
            self.skipTest("no infeasible TGN rows in this run")
        self.assertTrue(infeasible["impact"].isna().all())
        self.assertTrue(infeasible["baseline_prediction"].isna().all())

    def testInvalidRowsArePreservedNotDeleted(self):
        ''' Transparency: failures stay in the raw file. '''
        self.assertEqual(len(self.frame),
                         self.summary["explanation_rows"])
        self.assertGreater(self.summary["invalid_rows"], 0,
                           "expected some invalid rows to be preserved")

    def testSummaryAgreesWithTheCsv(self):
        self.assertEqual(self.summary["valid_rows"],
                         int(self.frame["valid_for_analysis"].sum()))
        self.assertEqual(self.summary["invalid_rows"],
                         int((~self.frame["valid_for_analysis"]).sum()))

    def testNoRawCrossConceptRanking(self):
        ''' The TGN concepts use incompatible perturbation units, so the
        summary must NOT publish a maximum over them. '''
        self.assertNotIn("largest_absolute_impact", self.summary)
        self.assertIn("ranking_note", self.summary)
        self.assertIn("NOT comparable", self.summary["ranking_note"])

    def testFeasibilityDiagnosticsArePersisted(self):
        self.assertTrue(available(os.path.join(
            TGN, "transformation_feasibility.csv")))


@unittest.skipUnless(available(os.path.join(MAIN, "email_eu_core",
                                            "tgap_results.csv")),
                     "real-data results not generated")
class TestInvalidRowsCannotEnterAggregates(unittest.TestCase):
    ''' Section P1.4: the 31/240 edge-count-infeasible settings must stay
    out of every published aggregate, and that must be enforced rather than
    remembered. '''

    @classmethod
    def setUpClass(cls):
        frames = []
        for name in sorted(os.listdir(MAIN)):
            path = os.path.join(MAIN, name, "tgap_results.csv")
            if os.path.exists(path):
                frames.append(pd.read_csv(path))
        cls.frame = pd.concat(frames)

    def testPublicationTableUsesValidRowsOnly(self):
        ''' table2_main_results is built from valid rows; every impact in it
        must be reproducible from a row flagged valid. '''
        path = os.path.join("output", "publication", "table2_main_results.csv")
        if not os.path.exists(path):
            self.skipTest("publication tables not generated")
        table = pd.read_csv(path)
        validImpacts = set(self.frame[self.frame["valid_for_analysis"]]
                           ["impact"].round(6).dropna())
        for impact in table["impact"].round(6):
            self.assertIn(impact, validImpacts,
                          "a publication row is not a valid-row impact")

    def testEveryInvalidRowHasAReason(self):
        invalid = self.frame[~self.frame["valid_for_analysis"]]
        self.assertGreater(len(invalid), 0)
        self.assertTrue((invalid["transformation_status"] != "ok").all())
        infeasible = invalid[
            invalid["transformation_status"] == "edge_count_infeasible"]
        self.assertTrue(infeasible["infeasible_reason"].notna().all(),
                        "an infeasible row has no stated reason")

    def testValidRowsAreAllStatusOk(self):
        valid = self.frame[self.frame["valid_for_analysis"]]
        self.assertTrue((valid["transformation_status"] == "ok").all())

    def testInfeasibleCountIsReported(self):
        ''' The count must be visible, not inferable. '''
        for name in sorted(os.listdir(MAIN)):
            path = os.path.join(MAIN, name, "summary.json")
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as handle:
                summary = json.load(handle)
            self.assertIn("edge_count_infeasible_settings", summary)
            self.assertIn("invalid_rows_by_status", summary)


if __name__ == "__main__":
    unittest.main()
