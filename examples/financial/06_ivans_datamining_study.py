'''
FINANCE 6 - Ivan's statistical study (RQ1-RQ4), with your settings.

Ivan's experimentationDatamining asks four research questions about how
stock correlation networks behave over time:

    RQ1  Do synchronization levels differ between calm and busy windows?
    RQ2  Is network density associated with mean absolute correlation?
    RQ3  Do stocks correlate more within a sector than across sectors?
    RQ4  Are the observed statistics distinguishable from a null model?

    python examples/financial/06_ivans_datamining_study.py

Outputs: output/examples/financial/06_ivans_datamining_study/
    report.txt and one CSV per research question
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from examples import toolkit                                  # noqa: E402
from finance.experimentationDatamining import (               # noqa: E402
    ExperimentConfig, run_all_experiments, save_results)
from finance.universe import IVAN_SECTORS                     # noqa: E402

# ============================== PARAMETERS ==============================
SECTORS = IVAN_SECTORS
PERIOD, WINDOW, WINDOWS = "5y", "6mo", 20
STRONG_CORRELATION = 0.70     # what counts as a "strong" correlation
BOOTSTRAP = 500               # Ivan's default is 2000 (slower, tighter CIs)
NULL_ITERATIONS = 200         # Ivan's default is 500
SEED = 42
# ========================================================================


def main():
    folder = os.path.join(toolkit.OUTPUT, "financial",
                          "06_ivans_datamining_study")

    # STEP 1 - settings
    config = ExperimentConfig(
        historic_period=PERIOD, sliding_window_period=WINDOW,
        approx_graphs=WINDOWS, bootstrap_iterations=BOOTSTRAP,
        null_iterations=NULL_ITERATIONS,
        strong_correlation_threshold=STRONG_CORRELATION, random_seed=SEED)
    toolkit.step(1, 3, "{0} stocks, {1} windows of {2} over {3}".format(
        len(SECTORS), WINDOWS, WINDOW, PERIOD))

    # STEP 2 - run the four research questions
    toolkit.step(2, 3, "Running RQ1-RQ4 (about a minute)")
    results = run_all_experiments(tickers=list(SECTORS), sectors=SECTORS,
                                  config=config)

    # STEP 3 - save and summarize
    save_results(results, folder)
    rq3 = results["rq3_sector_structure"]["per_window_permutation_tests"]
    rq4 = results["rq4_null_model"]
    toolkit.step(3, 3, "Summary:")
    print("        RQ3: within-sector correlation exceeds cross-sector in "
          "{0} of {1} windows".format(
              int((rq3["observed_within_minus_cross"] > 0).sum()), len(rq3)))
    print("        RQ4: " + ("testable, standardized difference {0:.2f}"
                             .format(rq4["standardized_difference"])
                             if rq4.get("testable", True) else
                             "NOT testable with this statistic (see report)"))
    print("      Results (report + CSVs): " + folder)


if __name__ == "__main__":
    main()
