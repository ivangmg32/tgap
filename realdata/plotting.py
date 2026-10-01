'''
Shared publication plotting: one theme, one save helper, one architecture
figure.

WHY THIS MODULE EXISTS
    Three separate rcParams blocks had drifted apart across the pipeline, so
    "the same" figure could carry different fonts and DPI depending on which
    script produced it. This module holds the one configuration the
    publication figures use.

    It is deliberately small. It does NOT rewrite the existing plotting
    functions, change any axis, or alter what a figure means - it only makes
    the typography and the export consistent.

VECTOR OUTPUT
    savePublicationFigure writes PNG *and* a vector format, because a
    raster figure degrades when a journal rescales it. Diagnostic figures
    stay PNG-only: they exist to be glanced at, and writing three files for
    each of 48 of them wastes space for no gain.
'''

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

# One visual language. Kept identical to the values make_publication.py was
# already using, so existing figures do not change appearance.
POSITIVE = "#b2182b"      # perturbation RAISES the prediction
NEGATIVE = "#2166ac"      # perturbation LOWERS it
NEUTRAL = "#9e9e9e"       # excluded, not applicable, or reference line

PUBLICATION_THEME = {
    "font.size": 9,
    "axes.titlesize": 11,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "figure.titlesize": 11,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "figure.autolayout": False,
}

# Diagnostics: same typography, lower DPI, since they are never printed.
DIAGNOSTIC_THEME = dict(PUBLICATION_THEME, **{"savefig.dpi": 200,
                                              "grid.alpha": 0.3})

VECTOR_FORMAT = "pdf"     # journals accept PDF most reliably


def usePublicationTheme():
    ''' Apply the publication theme to the global matplotlib state. '''
    plt.rcParams.update(PUBLICATION_THEME)


def useDiagnosticTheme():
    plt.rcParams.update(DIAGNOSTIC_THEME)


def savePublicationFigure(fig, path, formats=("png", VECTOR_FORMAT)):
    ''' Save one figure in several formats from a single call.

    `path` may carry an extension or not; the stem is what matters. Returns
    the list of files written, so a caller can report exactly what it
    produced rather than assume.
    '''
    stem = os.path.splitext(path)[0]
    os.makedirs(os.path.dirname(stem) or ".", exist_ok=True)
    written = []
    for suffix in formats:
        target = f"{stem}.{suffix}"
        # PDF embeds a CreationDate by default, which makes two runs of the
        # same figure differ byte-for-byte and defeats any reproducibility
        # check on the vector output. Setting it to None omits it. PNG
        # carries no timestamp and needs nothing.
        # dpi is passed EXPLICITLY, never left to ambient rcParams. Several
        # pipeline modules set savefig.dpi = 200 at import time, so merely
        # importing one of them mid-run used to silently downgrade every
        # publication figure drawn afterwards from 300 dpi to 200. Reading
        # the value from the theme here makes the output independent of
        # import order.
        dpi = PUBLICATION_THEME["savefig.dpi"]
        if suffix == "pdf":
            fig.savefig(target, dpi=dpi, metadata={"CreationDate": None})
        else:
            fig.savefig(target, dpi=dpi)
        written.append(target)
    return written


##  P0.7 - the architecture figure  ##


def _box(ax, x, y, width, height, label, facecolor, fontsize=8.5,
         bold=False, textcolor="black"):
    ax.add_patch(mpatches.FancyBboxPatch(
        (x, y), width, height, boxstyle="round,pad=0.012",
        linewidth=1.0, edgecolor="#444444", facecolor=facecolor, zorder=2))
    ax.text(x + width / 2, y + height / 2, label, ha="center", va="center",
            fontsize=fontsize, zorder=3, color=textcolor,
            fontweight="bold" if bold else "normal")


def _arrow(ax, x1, y1, x2, y2, style="-|>", colour="#333333", width=1.2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=colour,
                                linewidth=width, shrinkA=2, shrinkB=2),
                zorder=1)


def architectureFigure(path):
    ''' The TGAP method, as one publication figure.

    It communicates the SCIENTIFIC pipeline, not a class diagram, and makes
    two things visually explicit:

      1. the single contract the explainer needs - predict(temporalGraph);
      2. the separation between the TGAP core, an optional model
         implementation such as TGN, and the evaluation/publication layer.

    The wording follows the repository: the explainer "requires only the
    predict(temporalGraph) interface". The phrase "model-agnostic" is
    deliberately avoided - it is a claim about a class of models, whereas
    what the code actually guarantees is a narrow interface.
    '''
    usePublicationTheme()
    fig, ax = plt.subplots(figsize=(12.4, 7.0))
    ax.set_xlim(0, 12.4); ax.set_ylim(0, 7.0)
    ax.axis("off"); ax.grid(False)

    core = "#e8eef5"
    model = "#fdece8"
    evaluation = "#eef5e8"

    # --- the vertical scientific pipeline (left/centre) ---
    steps = [
        ("Temporal Graph", 5.90),
        ("Concept / Metric Value", 5.20),
        ("Counterfactual Transformation", 4.50),
        ("model.predict(temporalGraph)", 3.80),
        ("Prediction Difference", 3.10),
        ("Achieved-Delta Normalization", 2.40),
        ("TGAP Explanation", 1.70),
    ]
    boxWidth, boxHeight, left = 3.4, 0.48, 3.6
    for index, (label, y) in enumerate(steps):
        isContract = "predict" in label
        _box(ax, left, y, boxWidth, boxHeight, label,
             model if isContract else core,
             fontsize=9 if isContract else 8.5, bold=isContract)
        if index:
            _arrow(ax, left + boxWidth / 2, steps[index - 1][1],
                   left + boxWidth / 2, y + boxHeight)

    # --- the three explanation outputs ---
    outputs = [("Global", 2.55), ("Local", 4.45), ("Temporal", 6.35)]
    for label, x in outputs:
        _box(ax, x, 0.70, 1.60, 0.44, label, evaluation)
        _arrow(ax, left + boxWidth / 2, steps[-1][1],
               x + 0.80, 1.14)

    # --- the contract annotation: the point of the whole figure ---
    ax.annotate(
        "The explainer requires ONLY this interface.\n"
        "No gradients, hidden layers, attention weights,\n"
        "memory internals or model-specific attributes.",
        xy=(left, steps[3][1] + boxHeight / 2),
        xytext=(0.15, 3.95), fontsize=8.2, va="center", ha="left",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#fff8e1",
                  edgecolor="#c9a227", linewidth=0.9),
        arrowprops=dict(arrowstyle="-|>", color="#c9a227", linewidth=1.2))

    # --- modular separation (right column) ---
    ax.text(10.95, 6.55, "Components", fontsize=9.5, fontweight="bold",
            ha="center")
    components = [
        ("Metric", core), ("Transformation", core), ("Explainer", core),
        ("Model", model), ("Evaluation", evaluation),
        ("Visualization", evaluation),
    ]
    for index, (label, colour) in enumerate(components):
        _box(ax, 10.05, 6.00 - index * 0.52, 1.8, 0.4, label, colour,
             fontsize=8.2)

    # --- layer legend, naming what is and is not part of the core ---
    ax.text(0.15, 6.55, "Layers", fontsize=9.5, fontweight="bold")
    legend = [
        (core, "TGAP core - independent of any model"),
        (model, "Model implementation - replaceable"),
        (evaluation, "Evaluation / publication layer"),
    ]
    for index, (colour, label) in enumerate(legend):
        y = 6.15 - index * 0.34
        ax.add_patch(mpatches.Rectangle((0.15, y), 0.24, 0.2,
                                        facecolor=colour,
                                        edgecolor="#444444", linewidth=0.8))
        ax.text(0.47, y + 0.1, label, fontsize=8, va="center")

    ax.text(6.2, 0.18,
            "Any object providing predict(temporalGraph) -> float can be "
            "explained; TGN is one such implementation, not a requirement.",
            fontsize=8, ha="center", style="italic", color="#444444")
    ax.set_title("TGAP: Temporal Graph Additive exPlanations", fontsize=12.5,
                 fontweight="bold", pad=14)

    written = savePublicationFigure(fig, path)
    plt.close(fig)
    return written
