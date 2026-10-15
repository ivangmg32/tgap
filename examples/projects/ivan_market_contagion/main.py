'''
IVAN 4 - Contagion between sectors: our own model and concept on Ivan's
networks.

Ivan's correlation networks become a TGAP temporal graph (strong
co-movements as ties, sectors as communities). A "contagion forecast"
predicts how much of the co-movement will cross sectors next window - the
channel through which a shock spreads. TGAP explains it with a new concept,
Sector Decoupling, and checks it against the built-in Bridge Width.

    python examples/projects/ivan_market_contagion/main.py
'''
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(HERE))))

from examples import toolkit                                          # noqa
from examples.projects.ivan_market_contagion.concept import SectorDecoupling  # noqa
from examples.projects.ivan_market_contagion.model import ContagionForecast   # noqa
from finance.networks import prepare                                  # noqa
from finance.universe import IVAN_SECTORS                             # noqa

# ============================== PARAMETERS ==============================
SECTORS = IVAN_SECTORS
FOCUS = "Technology"          # Technology vs the rest (works with 8 stocks)
THRESHOLD = 0.3               # usable for these stocks
PERIOD, WINDOW, WINDOWS = "5y", "6mo", 12
RECENT = 4                    # windows the forecast looks at
DELTAS = [0.1, 0.25]
# ========================================================================


def main(output=None):
    output = output or os.path.join(HERE, "output")
    t = toolkit.Tutorial(output, "Contagion between sectors - a TGAP "
                         "tutorial on Ivan's networks",
                         intro="Does the forecast of cross-sector contagion "
                               "respond to how much sectors decouple? And "
                               "does our own concept agree with the "
                               "built-in one?")

    toolkit.step(1, 4, "Ivan's networks -> a TGAP market graph")
    market = prepare("contagion", list(SECTORS), SECTORS, PERIOD, WINDOW,
                     WINDOWS, THRESHOLD, focus=FOCUS)
    t.section("Step 1 - The market as a temporal graph", (
        "Ivan's `CorrGraphs` builds {0} correlation networks ({1} windows "
        "over {2}). Two stocks are tied when their correlation is at least "
        "**{3}**; the communities are **{4}** vs the rest. "
        "(`finance.networks.prepare` does this.)").format(
            WINDOWS, WINDOW, PERIOD, THRESHOLD, FOCUS))

    model = ContagionForecast(market.communities, RECENT)
    toolkit.step(2, 4, "Model: ContagionForecast -> {0:.3f}".format(
        model.predict(market.snapshots)))
    t.section("Step 2 - The model (model.py)", (
        "`ContagionForecast` predicts that the next window will look like "
        "the recent past: the average share of strong co-movements that "
        "cross sectors over the last {0} windows. Today: **{1:.3f}**."
    ).format(RECENT, model.predict(market.snapshots)))

    concept = SectorDecoupling(market.communities)
    toolkit.step(3, 4, "Concept: Sector Decoupling {0:.3f} -> {1:.3f} after "
                 "+25%".format(concept.propertyValue(market.snapshots),
                               concept.propertyValue(concept.transform(
                                   market.snapshots, 0.25))))
    t.section("Step 3 - The concept (concept.py)", (
        "`SectorDecoupling` is the share of ties that stay inside a sector "
        "(**{0:.3f}** here). It rewires ties between inside and across "
        "while keeping their number fixed. It is the mirror image of the "
        "built-in Bridge Width, which gives us a check: their impacts on "
        "the same model must have opposite signs.").format(
            concept.propertyValue(market.snapshots)))

    toolkit.step(4, 4, "Explaining (with Bridge Width as a cross-check)")
    table = toolkit.explainAndSave(
        "ivan_market_contagion", model,
        [concept] + toolkit.transformations(["bridge_width", "density"],
                                            market.communities),
        market.snapshots, market.communities, deltas=DELTAS, folder=output,
        tutorial=t, step="Step 4",
        modelDescription="the share of co-movement that will cross sectors "
                         "next window")

    first = table[(table["requested_change"] == DELTAS[0])]
    mine = first.loc[first["concept"] == "Sector Decoupling", "impact"]
    builtin = first.loc[first["concept"] == "Bridge Width", "impact"]
    if len(mine) and len(builtin) and mine.iloc[0] and builtin.iloc[0]:
        agree = (mine.iloc[0] > 0) != (builtin.iloc[0] > 0)
        t.section("Cross-check: does TGAP agree with itself?", (
            "More **Sector Decoupling** moves the forecast **{0}**; more "
            "**Bridge Width** moves it **{1}**. {2}").format(
                "up" if mine.iloc[0] > 0 else "down",
                "up" if builtin.iloc[0] > 0 else "down",
                "Opposite directions, as they must be for mirror-image "
                "concepts: the explanation is consistent." if agree else
                "The SAME direction - unexpected for mirror-image concepts; "
                "look at sensitivity.png and the achieved changes before "
                "trusting either number."))
        t.save()
        print("      Cross-check: " + ("consistent" if agree else
                                      "INCONSISTENT - see the tutorial"))


if __name__ == "__main__":
    main()
