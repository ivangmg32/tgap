'''
Concrete graph transformations - the TGAP analogues of TSAP's
transformVolatility and transformTrendReverse.

ONE TRANSFORMATION PER FILE. Each concept is independently readable,
testable and replaceable, and a researcher adding a new one writes a new
file here without touching the explainer or any existing transformation.

    Base.py             shared engine (edge canonicalisation, safe removal,
                        setBridgeWidth) - not a transformation itself
    BridgeWidth.py      BridgeWidthTransformation
    Centralization.py   CentralizationTransformation
    Density.py          DensityTransformation
    BridgeTrend.py      BridgeTrendTransformation
    Churn.py            ChurnTransformation

This package replaced a single 665-line module. Import paths are unchanged -
`from core.Transformations import BridgeWidthTransformation` works exactly as
it did - because the package deliberately carries the module's old name.

ADDING YOUR OWN: you do NOT need to edit this file. Write a class that
implements the TemporalGraphTransformation contract (see
core/TemporalGraphTransformation.py) anywhere you like, and pass an instance
to TgapExplainer. Re-exporting here is a convenience for the transformations
that ship with TGAP, not a registration requirement. A worked example lives
in examples/MyCustomTransformation.py.

Each one changes a single interpretable structural property by a ratio
delta, deterministically (seeded), returning a new graph.

A note on discreteness, worth understanding before reading plots:
a time-series value can change by exactly 10%, but a graph has a WHOLE
NUMBER of edges - you cannot add 0.6 of a bridge. We therefore round to
the nearest integer number of edge changes. Consequence: sensitivity
curves (plotTrans) look STEPPY for graphs, not smooth like TSAP's. That
is not a bug; it is the honest geometry of discrete structures.

A note on property overlap: just like TSAP's volatility transformation
slightly affects the trend (they share the same anchor), rewiring edges
toward a hub can occasionally touch a bridge edge, etc. Perfectly
orthogonal structural properties do not exist; we document the leakage
instead of pretending it away.
'''

from .Base import setBridgeWidth, _edgeKey, _snapshots, _safeToRemove
from .BridgeWidth import BridgeWidthTransformation
from .Centralization import CentralizationTransformation
from .Density import DensityTransformation
from .BridgeTrend import BridgeTrendTransformation
from .Churn import ChurnTransformation

__all__ = [
    "BridgeWidthTransformation",
    "CentralizationTransformation",
    "DensityTransformation",
    "BridgeTrendTransformation",
    "ChurnTransformation",
    "setBridgeWidth",
]
