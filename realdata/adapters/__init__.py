''' Dataset adapters: one module per dataset, plus shared preprocessing. '''

from .base import (
    # analysis modes and the leakage-safe temporal split
    ANALYSIS_MODES,
    DESCRIPTIVE,
    TEMPORAL_EVALUATION,
    SELECTION_FRACTION,
    checkMode,
    temporalSplit,
    # preprocessing
    projectCoActivity,
    aggregateGraph,
    fixedPartitionFromAggregate,
    fixedPartitionWithReport,
    summariseSnapshots,
    # reporting blocks
    retentionSummary,
    selectionWindowSummary,
    PreparedDataset,
)
