'''
TGAP - Temporal Graph Additive exPlanations.

TGAP is the graph counterpart of TSAP (Time-Series Additive exPlanations).
The idea is identical:

    1. Take a model that looks at a (temporal) graph and outputs one number.
    2. Transform the graph in a HUMAN-MEANINGFUL way (e.g. "widen the bridges
       between communities by 10%").
    3. Measure how much the model's output moves.
    4. That movement, divided by the size of the nudge, IS the explanation.

Correspondence with the TSAP code base (tsap_v2.1):

    TSAP                                TGAP
    ----------------------------------  ----------------------------------
    TsModel.predict(series) -> float    GraphModel.predict(graph) -> float
                                        TemporalGraphModel.predict(tg) -> float
    transformVolatility / Trend         BridgeWidthTransformation,
                                        CentralizationTransformation, ...
    TsapExplainer                       GraphExplainer / TgapExplainer
    (no equivalent)                     Metric.measure(graph) -> float

Data conventions used everywhere in this package:

    graph          = a networkx.Graph (undirected, simple)
    temporalGraph  = a Python list of networkx.Graph snapshots,
                     ordered oldest -> newest (like a time-series of graphs)
    communities    = a pair (setA, setB) of node sets partitioning the graph
    delta          = a ratio: 0.1 means "change the property by 10%"

This __init__ re-exports the public classes so users can simply write:

    from core import TgapExplainer, BridgeWidthMetric, ...
'''

from .GraphMetric import (
    Metric,
    DensityMetric,
    DegreeCentralizationMetric,
    BridgeWidthMetric,
    CohesionMetric,
    ClusteringMetric,
)
from .GraphModel import GraphModel, MetricGraphModel
from .TemporalGraphModel import (
    TemporalGraphModel,
    PersistenceTemporalModel,
    TrendTemporalModel,
    WeightedMetricModel,
    SlopeModel,
)
from .TemporalGraphTransformation import TemporalGraphTransformation
from .Transformations import (
    # structural (uniform over time)
    BridgeWidthTransformation,
    CentralizationTransformation,
    DensityTransformation,
    # temporal (reshape the trajectory, last snapshot anchored)
    BridgeTrendTransformation,
    ChurnTransformation,
)
from .GraphExplainer import GraphExplainer
from .TemporalGraphExplainer import TgapExplainer
from .Communities import detectTwoCommunities, interCommunityEdges
from .SyntheticData import (
    makeTwoCommunityGraph,
    makeTemporalGraph,
    makeScenario,
    SCENARIOS,
)
from .Feasibility import (
    InfeasibleTransformation,
    bridgeWidthFeasibility,
    edgeCountFeasibility,
    bridgeTrendDirection,
    declaresEdgeCountPreservation,
)
from .Diagnostics import (
    CallCountingModel,
    leakageReport,
    formatLeakageReport,
    panelValue,
)
