'''
IVAN 5 - Does the explanation survive a different threshold?

Turning Ivan's correlation networks into a TGAP graph needs a threshold, and
any threshold is a choice. A finding worth reporting should not depend on
it. This tutorial explains the same model at every usable threshold and
checks whether the DIRECTION of each concept's impact stays the same.

    python examples/projects/ivan_threshold_robustness/main.py
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

from core import TgapExplainer                               # noqa: E402
from examples import toolkit                                 # noqa: E402
from finance.networks import (correlationNetworks, prepare,  # noqa: E402
                              sectorPartition, thresholdReport)
from finance.universe import IVAN_SECTORS                    # noqa: E402

# ============================== PARAMETERS ==============================
SECTORS = IVAN_SECTORS
FOCUS = "Technology"
THRESHOLDS = [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5]
MODEL = "trend_bridge_width"            # cross-sector coupling forecast
CONCEPTS = ["bridge_width", "bridge_trend", "density", "churn"]
DELTA = 0.1
# ========================================================================


def main(output=None):
    output = output or os.path.join(HERE, "output")
    t = toolkit.Tutorial(output, "Does the explanation survive a different "
                         "threshold?",
                         intro="The same model, explained at every usable "
                               "threshold. A robust finding keeps its "
                               "direction.")

    toolkit.step(1, 3, "Checking which thresholds are usable")
    weighted, _ = correlationNetworks(list(SECTORS), "5y", "6mo", 12)
    partition = sectorPartition(list(SECTORS), SECTORS, FOCUS)
    check = thresholdReport(weighted, partition, THRESHOLDS)
    check.to_csv(os.path.join(output, "threshold_check.csv"), index=False)
    usable = list(check.loc[check["usable"], "threshold"])
    t.section("Step 1 - Which thresholds can be used?", (
        "A threshold is usable when no window is empty and TGAP can keep "
        "its promise of changing one concept while holding the number of "
        "ties fixed. Usable here: **{0}**.").format(
            ", ".join("{0:g}".format(x) for x in usable) or "none"))
    t.table(check, "threshold_check.csv")

    toolkit.step(2, 3, "Explaining {0} at {1} thresholds".format(
        MODEL, len(usable)))
    rows = []
    for value in usable:
        market = prepare("robustness", list(SECTORS), SECTORS,
                         minimum=value, focus=FOCUS)
        model = toolkit.model(MODEL, market.communities)
        explainer = TgapExplainer(model, toolkit.transformations(
            CONCEPTS, market.communities), defaultDelta=DELTA)
        for record in explainer.explainDetailed(market.snapshots):
            if record["requestedDelta"] > 0:
                rows.append({"threshold": value,
                             "concept": record["transformation"],
                             "impact": record["impact"],
                             "nothing_changed": record["noop"]})
    table = pd.DataFrame(rows)
    table.to_csv(os.path.join(output, "impacts_by_threshold.csv"),
                 index=False)

    verdicts = []
    for concept, part in table.groupby("concept", sort=False):
        moved = part[~part["nothing_changed"] & (part["impact"].abs() > 1e-12)]
        signs = set(np.sign(moved["impact"]))
        verdict = ("no effect at any threshold" if moved.empty else
                   "ROBUST: always {0}".format("up" if signs == {1.0}
                                              else "down")
                   if len(signs) == 1 else
                   "NOT robust: the direction depends on the threshold")
        verdicts.append({"concept": concept,
                         "thresholds_with_an_effect": len(moved),
                         "verdict": verdict})
    verdicts = pd.DataFrame(verdicts)
    verdicts.to_csv(os.path.join(output, "verdicts.csv"), index=False)

    fig, ax = plt.subplots(figsize=(7.5, 4))
    for concept, part in table.groupby("concept", sort=False):
        ax.plot(part["threshold"], part["impact"], marker="o", label=concept)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xlabel("correlation threshold")
    ax.set_ylabel("impact (increase, delta {0:g})".format(DELTA))
    ax.set_title("Is the explanation robust to the threshold?")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(output, "robustness.png"), dpi=150)
    plt.close(fig)

    toolkit.step(3, 3, "Verdicts: " + "; ".join(
        "{0}: {1}".format(r["concept"], r["verdict"].split(":")[0])
        for _, r in verdicts.iterrows()))
    t.section("Step 2 - The impact at each threshold")
    t.table(table, "impacts_by_threshold.csv")
    t.image("robustness.png", "Impact of increasing each concept, at each "
            "usable threshold. Lines that stay on one side of zero are "
            "robust.")
    t.section("Step 3 - Verdicts")
    t.table(verdicts, "verdicts.csv")
    t.text("Only ROBUST findings should be reported without qualification. "
           "A direction that flips with the threshold says more about the "
           "modelling choice than about the market.")
    print("      Read first: " + t.save())


if __name__ == "__main__":
    main()
