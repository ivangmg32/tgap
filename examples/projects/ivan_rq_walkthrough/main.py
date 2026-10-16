'''
IVAN 3 - Ivan's research questions, one at a time.

finance/experimentationDatamining.py answers four research questions about
stock correlation networks. run_all_experiments runs them together; this
tutorial runs each one on its own and explains its hypothesis, method and
result.

    python examples/projects/ivan_rq_walkthrough/main.py
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

from finance import experimentationDatamining as study      # noqa: E402
from finance.CorrGraphs import CorrGraphs                    # noqa: E402
from finance.universe import IVAN_SECTORS                    # noqa: E402

# ============================== PARAMETERS ==============================
SECTORS = IVAN_SECTORS
PERIOD, WINDOW, GRAPHS = "5y", "6mo", 20
STRONG = 0.70             # what counts as a strong correlation
ITERATIONS = 300          # bootstrap / permutation draws (Ivan: 2000 / 500)
SEED = 42
# ========================================================================


def main(output=None):
    output = output or os.path.join(HERE, "output")
    t = toolkit.Tutorial(output, "Ivan's research questions, one at a time",
                         intro="Each research question in "
                               "`experimentationDatamining.py`: what it "
                               "asks, how it is tested, what came out.")

    # STEP 0 - the networks and their features
    toolkit.step(1, 5, "Building {0} networks ({1} windows over {2})".format(
        GRAPHS, WINDOW, PERIOD))
    networks = CorrGraphs(list(SECTORS)).temporalGraph(PERIOD, WINDOW, GRAPHS)
    features = study.extract_temporal_features(networks, STRONG)
    features.round(4).to_csv(os.path.join(output, "features.csv"))
    t.section("Step 0 - The networks", (
        "{0} correlation networks, one per {1} window. For each, Ivan's code "
        "computes features such as the mean absolute correlation, the share "
        "of strong correlations (>= {2}) and the density.").format(
            len(networks), WINDOW, STRONG))
    t.table(features.reset_index().round(3).head(6),
            "The first rows of features.csv")

    # RQ1
    toolkit.step(2, 5, "RQ1 - calm versus synchronized windows")
    rq1 = study.experiment_rq1_synchronization_groups(
        features, bootstrap_iterations=ITERATIONS, random_seed=SEED)
    rq1["comparisons"].round(4).to_csv(os.path.join(output, "rq1.csv"),
                                       index=False)
    t.section("RQ1 - Do synchronization levels differ across windows?", (
        "**Hypothesis:** windows where the market is highly synchronized "
        "differ structurally from calm ones.\n\n**Method:** split the "
        "windows at the median mean-correlation ({0:.3f}) into a low and a "
        "high group, then compare each feature between the groups with a "
        "Welch t-test, a bootstrap confidence interval and a permutation "
        "test.").format(rq1["median_synchronization_threshold"]))
    t.table(rq1["comparisons"][["metric", "low_mean", "high_mean",
                                "p_value", "permutation_p_value"]].round(4)
            if "low_mean" in rq1["comparisons"] else rq1["comparisons"].round(4),
            "rq1.csv")
    t.text("**Reading:** features with a small p-value (< 0.05) really "
           "differ between calm and synchronized windows. Density cannot "
           "differ: Ivan's networks connect every pair of stocks, so "
           "density is always 1 (its p-value is empty for that reason).")

    # RQ2
    toolkit.step(3, 5, "RQ2 - density and correlation")
    rq2 = study.experiment_rq2_density_association(features)
    t.section("RQ2 - Is density associated with mean absolute correlation?",
              ("**Method:** Spearman rank correlation between density and "
               "mean absolute correlation across windows (plus an OLS fit "
               "when statsmodels is installed).\n\n**Result:** Spearman "
               "rho = {0}.\n\n**Reading:** with complete networks density "
               "is constant, so there is nothing to correlate - the result "
               "is undefined (nan), not 'no association'. A thresholded "
               "network (see examples/financial/03) would make density "
               "vary.").format(rq2.get("spearman_rho")))

    # RQ3
    toolkit.step(4, 5, "RQ3 - within versus across sectors")
    rq3 = study.experiment_rq3_sector_structure(
        networks, SECTORS, iterations=ITERATIONS,
        random_seed=SEED)
    tests = rq3["per_window_permutation_tests"]
    tests.round(4).to_csv(os.path.join(output, "rq3.csv"), index=False)
    above = int((tests["observed_within_minus_cross"] > 0).sum())
    significant = int((tests["permutation_p_value"] < 0.05).sum())
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.bar(range(len(tests)), tests["observed_within_minus_cross"],
           color=["#c0392b" if p < 0.05 else "#9aa5b1"
                  for p in tests["permutation_p_value"]])
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("window (oldest -> newest)")
    ax.set_ylabel("within minus across sector")
    ax.set_title("RQ3: do stocks correlate more inside their sector?")
    fig.tight_layout()
    fig.savefig(os.path.join(output, "rq3.png"), dpi=150)
    plt.close(fig)
    t.section("RQ3 - Do stocks correlate more within a sector?", (
        "**Method:** in each window, the mean correlation of same-sector "
        "pairs minus that of cross-sector pairs, tested against {0} random "
        "shuffles of the sector labels.\n\n**Result:** within-sector "
        "correlation is higher in **{1} of {2}** windows, significantly "
        "(p < 0.05) in **{3}**.").format(ITERATIONS, above, len(tests),
                                         significant))
    t.image("rq3.png", "Red bars: significant at p < 0.05. Grey: not "
            "significant. Note: with 8 stocks, only Technology has more "
            "than one member, so this mostly measures how tech stocks move "
            "together.")

    # RQ4
    toolkit.step(5, 5, "RQ4 - the null model")
    rq4 = study.experiment_rq4_null_model(networks, "mean_abs_corr",
                                          iterations=ITERATIONS // 3,
                                          random_seed=SEED)
    t.section("RQ4 - Are the statistics different from a null model?", (
        "**Method:** shuffle the correlation values among the edges of each "
        "network and compare the statistic with the shuffled versions.\n\n"
        "**Result:** {0}.\n\n**Reading:** {1}").format(
            "standardized difference {0:.3f}".format(
                rq4["standardized_difference"]) if rq4["testable"]
            else "**not testable**",
            rq4["interpretation_note"]))
    t.section("Files in this folder")
    t.bullets(["`features.csv` - one row per network",
               "`rq1.csv`, `rq3.csv` - the test tables", "`rq3.png`"])
    print("      Read first: " + t.save())


if __name__ == "__main__":
    main()
