'''
EXAMPLE 5 - One of the eight real datasets shipped with TGAP.

The dataset is downloaded once (into data/) and then cached. Preprocessing
is leakage-safe: people and groups are chosen from the first 20 % of the
time span, and TGAP explains snapshots from the remaining 80 %.

    python examples/05_real_dataset.py
'''
import os
import sys
import urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from examples import toolkit   # noqa: E402

# ============================== PARAMETERS ==============================
# One of: email_eu_core (1.6 MB, recommended), bitcoin_alpha, bitcoin_otc,
#         tgbl_uci, tgbl_enron, sx_mathoverflow, decentraland, tgbl_wiki
DATASET = "email_eu_core"
MODEL = "trend_bridge_width"
TRANSFORMATIONS = ["bridge_width", "centralization", "density", "churn"]
DELTAS = [0.1, 0.25]
# ========================================================================


def main():
    from realdata.run_real_data import ADAPTERS
    if DATASET not in ADAPTERS:
        raise ValueError("Unknown DATASET {0!r}. Choose one of: {1}".format(
            DATASET, ", ".join(ADAPTERS)))

    # STEP 1 - download once (cached in data/) and preprocess
    toolkit.step(1, 3, "Preparing {0} (downloads once, then works "
                 "offline)".format(DATASET))
    try:
        prepared = ADAPTERS[DATASET]("temporal_evaluation", 2)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as failure:
        print("        Skipped: the dataset could not be downloaded ({0}). "
              "Connect to the internet and run again; the other examples "
              "work offline.".format(failure))
        return
    print("        {0} people, {1} snapshots".format(
        prepared.snapshots[0].number_of_nodes(), len(prepared.snapshots)))

    # STEP 2 - model and concepts
    toolkit.step(2, 3, "Model: {0};  concepts: {1}".format(
        MODEL, ", ".join(TRANSFORMATIONS)))
    model = toolkit.model(MODEL, prepared.communities)
    concepts = toolkit.transformations(TRANSFORMATIONS, prepared.communities)

    # STEP 3 - explain, print, and save CSV + PNG
    toolkit.step(3, 3, "Explaining")
    toolkit.explainAndSave("05_real_dataset_" + DATASET, model, concepts,
                           prepared.snapshots, prepared.communities,
                           deltas=DELTAS)

if __name__ == "__main__":
    main()
