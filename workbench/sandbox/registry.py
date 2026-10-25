"""Central registry of user-facing names: models, graph concepts, metrics.

Technical identifiers are unchanged everywhere in code and exports; only the
display layer reads these records. Every definition was checked against the
implementation (sandbox/engine.py build of MODELS, core/TemporalGraphModel.py,
core/GraphMetric.py, core/GraphExplainer.py).
"""

MODELS = {
    'persistence_bridge': dict(
        name='Bridge Width — Current Snapshot', technical='Present · bridge width',
        code='PersistenceTemporalModel(BridgeWidthMetric(communities))', reads='only the latest snapshot',
        calculates='the number of connections between the two communities in the latest snapshot',
        output='a count of bridge edges', why='a known-truth baseline: it must ignore every change to the past'),
    'trend_bridge': dict(
        name='Bridge Width — Next-Step Forecast', technical='Forecast · bridge width',
        code='TrendTemporalModel(BridgeWidthMetric(communities))', reads='every snapshot (the whole history)',
        calculates='a straight-line fit of bridge width over time, extended one step into the future',
        output='a forecast count of bridge edges', why='reads history, so it should react to changes in the past'),
    'slope_bridge': dict(
        name='Bridge Width — Historical Slope', technical='Trajectory · bridge slope',
        code='SlopeModel(BridgeWidthMetric(communities))', reads='every snapshot (the whole history)',
        calculates='the slope of the straight-line fit of bridge width over time',
        output='bridge edges gained or lost per snapshot', why='reads only the trend, not the level'),
    'persistence_density': dict(
        name='Network Density — Current Snapshot', technical='Present · density',
        code='PersistenceTemporalModel(DensityMetric())', reads='only the latest snapshot',
        calculates='the share of possible connections that exist in the latest snapshot', output='a fraction from 0 to 1',
        why='a present-only model of overall connectedness'),
    'persistence_centralization': dict(
        name='Network Centralization — Current Snapshot', technical='Present · centralization',
        code='PersistenceTemporalModel(DegreeCentralizationMetric())', reads='only the latest snapshot',
        calculates='how strongly connections concentrate on a few hubs in the latest snapshot (Freeman degree centralization)',
        output='a value from 0 (even) to 1 (one hub)', why='a present-only model of hub concentration'),
    'trend_clustering': dict(
        name='Clustering — Next-Step Forecast', technical='Forecast · clustering',
        code='TrendTemporalModel(ClusteringMetric())', reads='every snapshot (the whole history)',
        calculates='a straight-line forecast of the average clustering coefficient',
        output='a forecast value from 0 to 1', why='a history-reading model of local interconnection'),
}

CONCEPTS = {
    'Bridge Width': 'the number of connections between communities',
    'Bridge Trend': 'how bridge width rises or falls over time (only the past is changed; the latest snapshot stays fixed)',
    'Centralization': 'how strongly connections concentrate on a few hubs',
    'Density': 'how many of the possible connections exist inside communities',
    'Churn': 'how much the past network differs from the latest snapshot',
    'Cohesion': 'how hard the network is to split (algebraic connectivity); measured as a side effect only',
    'Clustering': 'how often a node’s neighbours are connected to each other; measured as a side effect only',
}

# kind: what the number is. better: higher | lower | depends.
METRICS = {
    'normalized_impact': dict(name='Normalized concept impact', short='Normalized impact', kind='Metric',
        definition='change in the model’s output divided by the change in the concept that was actually achieved',
        unit='model-output units per unit of concept change', better='depends',
        reading='The sign shows direction (positive: the output rises when the concept rises); the size shows sensitivity. Not comparable across models with different output units.',
        formula='(prediction after − prediction before) / |achieved change| (core/GraphExplainer.py, explainDetailed)'),
    'requested_normalization': dict(name='Impact normalized by the requested change', short='Requested-change impact', kind='Metric',
        definition='the same output change divided by the change that was asked for',
        unit='model-output units per unit of requested change', better='depends',
        reading='Differs from the normalized impact whenever the graph could not change by exactly the requested amount.',
        formula='(prediction after − prediction before) / |requested change|'),
    'prediction_change': dict(name='Model output change', short='Output change', kind='Metric',
        definition='prediction after the change minus prediction before', unit='the model’s own output units',
        better='depends', reading='Raw difference, not divided by anything.', formula='prediction after − prediction before'),
    'achieved_change': dict(name='Achieved concept change', short='Achieved change', kind='Metric',
        definition='how much the concept really moved, measured after the transformation', unit='relative change (%) or the concept’s own units',
        better='depends', reading='Compare with the requested change: a gap means the graph could not be changed as much as asked.',
        formula='(value after − value before) / |value before| for relative concepts'),
    'validity': dict(name='Transformation validity', short='Validity', kind='Metric',
        definition='whether a requested change could be carried out correctly (edge count kept, moved the right way, not saturated)',
        unit='status per setting', better='higher', reading='Only valid settings support conclusions; excluded settings are not zeros.',
        formula='realdata.run_real_data.rowValidity / sandbox.engine.validity_gate'),
    'noop': dict(name='No-op', short='No-op', kind='Metric', definition='a request that changed neither the concept nor the prediction',
        unit='yes / no', better='depends', reading='A no-op carries no information; it is not a zero-impact result.', formula='achieved change = 0 and output change = 0'),
    'leakage': dict(name='Non-target effect (leakage)', short='Side effect', kind='Metric',
        definition='how much other graph properties changed while one concept was changed', unit='each property’s own units (mean over snapshots)',
        better='lower', reading='Large side effects mean the output change may partly come from other properties.', formula='mean over snapshots of (after − before)'),
    'seed_sd': dict(name='Seed variation', short='Seed spread', kind='Metric', definition='how much the impact varies when random seeds change',
        unit='model-output units per unit of concept change', better='lower', reading='Zero means every repeat gave the same result.', formula='standard deviation across seeds'),
    'model_calls': dict(name='Model-call budget', short='Model calls', kind='Metric', definition='how many times the model was queried',
        unit='count', better='depends', reading='TGAP should use exactly 1 + 2 × (number of concepts) calls per explanation.', formula='1 + 2K'),
    'auc': dict(name='Area under the ROC curve', short='AUC', kind='Metric', definition='how well the model ranks real links above non-links',
        unit='0 to 1 (0.5 = chance)', better='higher', reading='Predictive quality of a learned model, not explanation quality.', formula='Mann–Whitney U statistic'),
    'ap': dict(name='Average precision', short='AP', kind='Metric', definition='area under the precision–recall curve',
        unit='0 to 1 (0.5 = chance on balanced data)', better='higher', reading='Predictive quality, not explanation quality.', formula='mean precision at each recall step'),
}

TYPES = {
    'Model': 'the function that calculates the output TGAP explains',
    'Graph Concept': 'the network property being investigated',
    'Transformation': 'the procedure that changes the graph to move one concept',
    'Metric': 'a quantity used to measure an experimental result',
    'Experimental Condition': 'dataset, snapshot, seed, request size or another setting',
}


def model_name(key):
    m = MODELS.get(key)
    return m['name'] if m else key


def glossary():
    return dict(types=TYPES, models=MODELS, concepts=CONCEPTS, metrics=METRICS)
