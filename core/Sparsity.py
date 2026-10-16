'''
SPARSITY of a TGAP explanation.

An explanation is useful only if a human can hold it in their head. A
method that spreads attribution thinly over every concept explains nothing,
even when every number is technically correct. Sparsity measures that.

WHY NO THRESHOLD IS NEEDED (the reason this definition is defensible)
    Most attribution methods need an arbitrary cut-off - "count features
    with |attribution| < 0.01 as zero" - because gradient- and
    sampling-based scores are never exactly zero. TGAP is different: its
    transformations are built to leave the other concepts untouched, so a
    model that cannot see a concept returns EXACTLY 0.0, not 1e-9.

    Measured example (core/SyntheticData world, PersistenceTemporalModel on
    BridgeWidthMetric): Bridge Width +8.0, and Centralization, Density and
    Churn all exactly +0.0000.

    So the primary definition below counts exact zeros and introduces NO
    threshold. An optional threshold is available for models whose outputs
    carry floating-point noise (a trained network, for instance), and when
    it is used it is recorded in the result so no reader has to guess.

TWO LEVELS, both scientifically meaningful, deliberately kept separate:

    conceptSparsity   over the CONCEPT vector - "of the concepts I probed,
                      how many does this model actually respond to?" This is
                      the headline number, because concepts are what TGAP
                      explains.

    elementSparsity   over per-EDGE or per-NODE attribution - "of the graph
                      elements I perturbed, how many mattered?" Only
                      meaningful when element attribution was actually run
                      (core/LocalExplanation.py), and it must never be
                      reported as if it were the concept-level figure: the
                      denominators are different objects.

A NOTE ON WHAT SPARSITY IS NOT
    High sparsity is not automatically good. A model that genuinely depends
    on four concepts SHOULD produce a dense explanation, and a sparse
    explanation of it would be wrong. Sparsity describes the explanation,
    not its quality, and this module deliberately returns measurements
    rather than verdicts.
'''


def _classify(values, threshold):
    ''' Split attribution magnitudes into carrying / not-carrying.

    threshold=None  exactly zero counts as not carrying (no cut-off)
    threshold=t     |value| <= t counts as not carrying (t is recorded)
    '''
    carrying, inactive = [], []
    for value in values:
        if value is None or value != value:      # None or NaN
            continue
        magnitude = abs(value)
        if (magnitude == 0.0) if threshold is None else (magnitude <= threshold):
            inactive.append(value)
        else:
            carrying.append(value)
    return carrying, inactive


def _summarise(carrying, inactive, threshold, level):
    total = len(carrying) + len(inactive)
    return {
        "level": level,
        "threshold": threshold,
        "threshold_free": threshold is None,
        # numerator / denominator reported explicitly, as required: a
        # sparsity value without its counts cannot be audited.
        "numerator_inactive": len(inactive),
        "denominator_total": total,
        "active": len(carrying),
        "sparsity": (len(inactive) / total) if total else None,
        "density": (len(carrying) / total) if total else None,
        "undefined_reason": None if total else
                            "no attribution values to measure",
    }


def conceptSparsity(records, threshold=None, validOnly=True):
    ''' Sparsity of a CONCEPT-level explanation.

    records : the list returned by ExplainerBase.explainDetailed, or any
              iterable of dicts carrying "impact". Rows produced by the
              real-data pipeline may also carry "valid_for_analysis"; when
              validOnly is True those are respected, so an experiment that
              failed its own invariant cannot inflate or deflate sparsity.

    Returns a dict with level, threshold, numerator, denominator, active
    count, sparsity and density.

        sparsity = (concepts with no response) / (concepts probed)

    1.0 means the model responded to nothing; 0.0 means it responded to
    everything. Both extremes are legitimate results about the model.

    NO-OP ROWS. A row flagged noop had no property change at all, so the
    model was never actually probed on that concept. Counting it as "the
    model does not respond" would be wrong - the experiment did not take
    place. Such rows are EXCLUDED from the denominator and counted
    separately as `noop_excluded`.
    '''
    usable, noops, invalid = [], 0, 0
    for record in records or []:
        if validOnly and record.get("valid_for_analysis") is False:
            invalid += 1
            continue
        if record.get("noop"):
            noops += 1
            continue
        usable.append(record.get("impact"))

    carrying, inactive = _classify(usable, threshold)
    result = _summarise(carrying, inactive, threshold, "concept")
    result["noop_excluded"] = noops
    result["invalid_excluded"] = invalid
    if result["denominator_total"] == 0:
        result["undefined_reason"] = (
            "every row was a no-op or invalid, so the model was never "
            "probed; sparsity is undefined rather than 1.0")
    return result


def elementSparsity(attribution, threshold=None):
    ''' Sparsity of EDGE- or NODE-level attribution.

    attribution : the dict returned by LocalExplanation.edgeAttribution or
                  nodeAttribution (its "rows" are used), or a plain list of
                  such rows.

    Returns the same shape as conceptSparsity, plus `coverage` carried
    through from the attribution when present.

    COVERAGE MATTERS HERE AND MUST BE READ WITH THE NUMBER. Element
    attribution may be truncated by topK / sample / budget, in which case
    the denominator is the set of elements ACTUALLY EVALUATED, not the whole
    graph. A sparsity of 0.9 over 10 of 5,000 edges says something much
    weaker than the same figure over all 5,000, so `coverage` and
    `elements_total` travel with the result instead of being dropped.
    '''
    if isinstance(attribution, dict):
        rows = attribution.get("rows", [])
        coverage = attribution.get("coverage")
        total = attribution.get("edges_total", attribution.get("nodes_total"))
    else:
        rows, coverage, total = list(attribution or []), None, None

    carrying, inactive = _classify([r.get("impact") for r in rows], threshold)
    result = _summarise(carrying, inactive, threshold, "element")
    result["coverage"] = coverage
    result["elements_total_in_graph"] = total
    result["partial"] = bool(coverage is not None and coverage < 1.0)
    if result["partial"]:
        result["partial_note"] = (
            "attribution was truncated (topK/sample/budget), so the "
            "denominator is the elements evaluated, not the whole graph")
    return result


def sparsityReport(records, attribution=None, threshold=None):
    ''' Both levels in one record, for the evaluation layer and tables.

    The two are returned side by side but NEVER combined into a single
    figure: their denominators are different kinds of object (concepts
    versus graph elements), so an average of them would mean nothing.
    '''
    report = {"concept": conceptSparsity(records, threshold=threshold)}
    if attribution is not None:
        report["element"] = elementSparsity(attribution, threshold=threshold)
    report["note"] = (
        "Concept and element sparsity are reported separately and must not "
        "be averaged or compared: the denominators are different objects. "
        "Sparsity describes the explanation, not its quality - a model that "
        "genuinely depends on many concepts should produce a dense "
        "explanation.")
    return report
