'''
Structured LOCAL explanations: what changed, where, and by how much.

The explainer's `explainDetailed` answers "how much does this concept move
the prediction". That is a GLOBAL statement about a concept. A local
explanation answers the complementary question:

    which specific edges, nodes and snapshots did the perturbation touch,
    and what did the graph look like before and after?

Nothing here re-runs the model beyond what it already needs, and nothing
here invents an importance score. Two distinct things live in this module
and they must not be confused:

  LOCAL EXPLANATION (localExplanation)
      A concept-level perturbation, with its affected graph elements
      recorded. The impact belongs to the CONCEPT; the edges are simply
      the ones the transformation happened to move. An edge appearing here
      is NOT a claim that this edge matters.

  ELEMENT ATTRIBUTION (edgeAttribution / nodeAttribution)
      An impact per graph element, obtained by ACTUALLY PERTURBING THAT
      ELEMENT and re-asking the model - explicit occlusion. Every number is
      a measured prediction difference, never an interpolation or a
      heuristic. Design section 22 forbids fabricated edge importance, so
      the method is named in the output ("occlusion") and the model-call
      cost is reported alongside.

COST. Element attribution is O(number of elements) model calls, against the
concept-level 1 + 2K. On large graphs that is the difference between 11
calls and tens of thousands, so `topK`, `sample` and `budget` are provided
and whatever they discarded is reported rather than silently dropped.
'''

import random

from .Communities import asPartition, bridgeMatrix, interCommunityEdges


def _edgeSet(graph):
    return {frozenset(edge) for edge in graph.edges()}


def graphDifference(before, after):
    ''' What a transformation did to one snapshot, as three edge sets.

    Returns a dict with:
        removed  edges present before and absent after
        added    edges absent before and present after
        kept     edges present in both
        nodes    nodes touched by a removed or added edge
    Edges are (u, v) tuples in canonical order so they can be compared and
    sorted reproducibly.
    '''
    beforeEdges, afterEdges = _edgeSet(before), _edgeSet(after)
    removed = sorted(tuple(sorted(e)) for e in beforeEdges - afterEdges)
    added = sorted(tuple(sorted(e)) for e in afterEdges - beforeEdges)
    kept = sorted(tuple(sorted(e)) for e in beforeEdges & afterEdges)
    touched = sorted({node for edge in removed + added for node in edge})
    return {"removed": removed, "added": added, "kept": kept,
            "nodes": touched}


def localExplanation(temporalGraph, transformation, delta, model=None,
                     communities=None):
    ''' A complete local explanation record for ONE (transformation, delta).

    Carries the schema of design section 21: what was changed, by how much,
    what the model said before and after, and exactly which graph elements
    moved in which snapshots.

    model=None is allowed: the structural part (affected edges, nodes,
    snapshots, property before/after) needs no model at all, which makes
    this usable for figures without paying for predictions.
    '''
    partition = asPartition(communities) if communities is not None else None
    transformed = transformation.transform(temporalGraph, delta)

    perSnapshot, addedAll, removedAll, nodesAll, changedIndices = [], [], [], set(), []
    for index, (before, after) in enumerate(zip(temporalGraph, transformed)):
        difference = graphDifference(before, after)
        if difference["added"] or difference["removed"]:
            changedIndices.append(index)
        addedAll.extend(difference["added"])
        removedAll.extend(difference["removed"])
        nodesAll.update(difference["nodes"])
        perSnapshot.append({
            "snapshot_index": index,
            "edges_before": before.number_of_edges(),
            "edges_after": after.number_of_edges(),
            "edges_added": len(difference["added"]),
            "edges_removed": len(difference["removed"]),
            "nodes_affected": len(difference["nodes"]),
        })

    propertyBefore = transformation.propertyValue(temporalGraph)
    propertyAfter = transformation.propertyValue(transformed)

    record = {
        "concept": transformation.name,
        "transformation": type(transformation).__name__,
        "direction": "increase" if delta > 0 else "decrease",
        "requested_delta": delta,
        "delta_mode": getattr(transformation, "deltaMode", "relative"),
        "property_before": propertyBefore,
        "property_after": propertyAfter,
        "community_pair": getattr(transformation, "communityPair", None),
        "snapshots_total": len(temporalGraph),
        "snapshots_affected": changedIndices,
        "affected_edges_added": addedAll,
        "affected_edges_removed": removedAll,
        "affected_edge_count": len(addedAll) + len(removedAll),
        "affected_nodes": sorted(nodesAll),
        "affected_node_count": len(nodesAll),
        "per_snapshot": perSnapshot,
    }

    # achieved_delta uses the same rule as the explainer, so a local record
    # and a global row never disagree about how much actually moved.
    if propertyBefore is not None and propertyAfter is not None:
        if record["delta_mode"] == "relative" and propertyBefore != 0:
            record["achieved_delta"] = ((propertyAfter - propertyBefore)
                                        / abs(propertyBefore))
        else:
            record["achieved_delta"] = propertyAfter - propertyBefore
    else:
        record["achieved_delta"] = None

    if partition is not None:
        record["bridge_matrix_before"] = {
            str(k): v for k, v in bridgeMatrix(temporalGraph[-1],
                                               partition).items()}
        record["bridge_matrix_after"] = {
            str(k): v for k, v in bridgeMatrix(transformed[-1],
                                               partition).items()}

    if model is not None:
        baseline = model.predict(temporalGraph)
        after = model.predict(transformed)
        achieved = record["achieved_delta"]
        record.update({
            "baseline_prediction": baseline,
            "after_prediction": after,
            "prediction_change": after - baseline,
            "model_calls": 2,
        })
        if achieved:
            record["impact"] = (after - baseline) / abs(achieved)
            record["normalizer"] = "achieved"
        elif after == baseline:
            record["impact"] = 0.0
            record["normalizer"] = "achieved"
            record["noop"] = True
        else:
            record["impact"] = (after - baseline) / abs(delta)
            record["normalizer"] = "requested"
    return record, transformed


##  Element-level attribution by explicit occlusion  ##


def _candidateEdges(temporalGraph, communities=None, onlyBridges=False):
    universe = set()
    for graph in temporalGraph:
        for u, v in graph.edges():
            universe.add(tuple(sorted((u, v))))
    if onlyBridges and communities is not None:
        partition = asPartition(communities)
        bridges = set()
        for graph in temporalGraph:
            bridges.update(tuple(sorted(e))
                           for e in interCommunityEdges(graph, partition))
        universe &= bridges
    return sorted(universe)


def edgeAttribution(temporalGraph, model, communities=None, topK=None,
                    sample=None, budget=None, seed=42, onlyBridges=False):
    ''' Impact per EDGE, measured by removing that edge and re-asking the
    model (occlusion).

    This is a real perturbation per edge, not an approximation:

        impact(e) = model(graph without e) - model(graph)

    Every value is a measured prediction difference. No edge receives a
    score by interpolation, attention weight, or any other proxy.

    topK    : after a cheap structural pre-rank (edges that appear in the
              most snapshots first), keep only the K most promising. The
              pre-rank costs no model calls.
    sample  : evaluate a random subset of this size (seeded).
    budget  : hard ceiling on model calls, applied last.

    Whatever was skipped is reported in the result, because a silent cap
    would make a partial ranking look exhaustive.
    '''
    candidates = _candidateEdges(temporalGraph, communities, onlyBridges)
    total = len(candidates)

    if sample is not None and sample < len(candidates):
        candidates = sorted(random.Random(seed).sample(candidates, sample))
    if topK is not None and topK < len(candidates):
        # Structural pre-rank: an edge present in more snapshots has more
        # opportunity to matter. Costs zero model calls.
        presence = {e: sum(1 for g in temporalGraph if g.has_edge(*e))
                    for e in candidates}
        candidates = sorted(sorted(candidates,
                                   key=lambda e: (-presence[e], e))[:topK])
    if budget is not None:
        candidates = candidates[:max(0, budget - 1)]

    baseline = model.predict(temporalGraph)
    calls = 1
    rows = []
    for edge in candidates:
        perturbed = []
        for graph in temporalGraph:
            copy = graph.copy()
            if copy.has_edge(*edge):
                copy.remove_edge(*edge)
            perturbed.append(copy)
        value = model.predict(perturbed)
        calls += 1
        rows.append({
            "element": "edge",
            "edge": edge,
            "u": edge[0], "v": edge[1],
            "snapshots_present": sum(1 for g in temporalGraph
                                     if g.has_edge(*edge)),
            "baseline_prediction": baseline,
            "after_prediction": value,
            "impact": value - baseline,
            "method": "occlusion (edge removed from every snapshot)",
        })
    rows.sort(key=lambda r: (-abs(r["impact"]), r["edge"]))
    return {
        "rows": rows,
        "baseline": baseline,
        "model_calls": calls,
        "edges_total": total,
        "edges_evaluated": len(rows),
        "edges_skipped": total - len(rows),
        "coverage": (len(rows) / total) if total else 0.0,
        "selection": {"topK": topK, "sample": sample, "budget": budget,
                      "onlyBridges": onlyBridges, "seed": seed},
        "method_note": (
            "Method: occlusion. "
            "impact(e) = model(temporal graph with e removed from every "
            "snapshot) - model(temporal graph). Each value is one measured "
            "prediction difference; nothing is interpolated. When coverage "
            "< 1 the ranking is partial and must be reported as such."),
    }


def nodeAttribution(temporalGraph, model, topK=None, budget=None, seed=42):
    ''' Impact per NODE, measured by isolating that node (removing all of
    its edges) and re-asking the model.

    The node itself is KEPT in the graph, because TGAP's anchor rule fixes
    the node set - removing the node would change the node set and confound
    the measurement with a size change.
    '''
    nodes = sorted({n for g in temporalGraph for n in g.nodes()})
    total = len(nodes)
    if topK is not None and topK < len(nodes):
        degree = {n: sum(g.degree(n) for g in temporalGraph if n in g)
                  for n in nodes}
        nodes = sorted(sorted(nodes, key=lambda n: (-degree[n], n))[:topK])
    if budget is not None:
        nodes = nodes[:max(0, budget - 1)]

    baseline = model.predict(temporalGraph)
    calls = 1
    rows = []
    for node in nodes:
        perturbed = []
        for graph in temporalGraph:
            copy = graph.copy()
            if node in copy:
                copy.remove_edges_from(list(copy.edges(node)))
            perturbed.append(copy)
        value = model.predict(perturbed)
        calls += 1
        rows.append({
            "element": "node",
            "node": node,
            "total_degree": sum(g.degree(node) for g in temporalGraph
                                if node in g),
            "baseline_prediction": baseline,
            "after_prediction": value,
            "impact": value - baseline,
            "method": "occlusion (node isolated; node set preserved)",
        })
    rows.sort(key=lambda r: (-abs(r["impact"]), r["node"]))
    return {"rows": rows, "baseline": baseline, "model_calls": calls,
            "nodes_total": total, "nodes_evaluated": len(rows),
            "nodes_skipped": total - len(rows),
            "coverage": (len(rows) / total) if total else 0.0}


def temporalAttribution(temporalGraph, model, transformation, delta):
    ''' Impact per SNAPSHOT: apply the transformation to ONE snapshot at a
    time and measure the prediction change.

    Answers "WHEN did this concept matter?", which the concept-level
    explanation cannot: it perturbs every snapshot at once, so a single
    number hides whether the effect came from last month or from a year ago.

    Costs 1 + T model calls for T snapshots.
    '''
    baseline = model.predict(temporalGraph)
    calls = 1
    rows = []
    for index in range(len(temporalGraph)):
        single = transformation.transform(temporalGraph, delta)
        # Keep ONLY this snapshot's change; restore the rest. This isolates
        # the time dimension while leaving the perturbation itself identical
        # to the one the concept-level explanation used.
        hybrid = [single[index] if i == index else graph
                  for i, graph in enumerate(temporalGraph)]
        value = model.predict(hybrid)
        calls += 1
        difference = graphDifference(temporalGraph[index], single[index])
        rows.append({
            "snapshot_index": index,
            "concept": transformation.name,
            "requested_delta": delta,
            "baseline_prediction": baseline,
            "after_prediction": value,
            "impact": value - baseline,
            "edges_added": len(difference["added"]),
            "edges_removed": len(difference["removed"]),
            "nodes_affected": len(difference["nodes"]),
        })
    return {"rows": rows, "baseline": baseline, "model_calls": calls,
            "method_note": (
                "Only one snapshot is perturbed per row; all others are the "
                "originals. The sum of per-snapshot impacts need NOT equal "
                "the all-snapshot impact, because the model is not additive "
                "over time - reporting them as a decomposition would be "
                "wrong.")}
