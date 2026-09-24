'''
Feasibility of a transformation's DECLARED INVARIANT.

Why this module exists
----------------------
A TGAP transformation makes a promise. BridgeWidthTransformation promises
"I will change the bridge width and keep the total edge count fixed":
every new bridge edge is paid for by deleting one intra-community edge.
That promise is what makes the explanation meaningful - the model sees the
same amount of activity, only ROUTED differently.

On real graphs the promise can be impossible to keep. If a snapshot has 28
bridge edges but only 15 intra-community edges, then widening the bridge by
5 edges would need 5 intra edges to delete, and after 15 deletions there is
nothing left to pay with. setBridgeWidth then under-pays and the total edge
count RISES. The perturbation is no longer "the same activity, rerouted" -
it is "more activity" - so the measured sensitivity mixes two concepts and
the row is not a valid explanation result.

Before this module, that case was silently absorbed. This module makes it
EXPLICIT in two complementary ways:

  1. bridgeWidthFeasibility() - a pure inspection. Given a graph, a
     partition and a target width, it counts what the payment would need
     and what is actually available, and says feasible / not feasible with
     a reason. It changes nothing and runs no transformation.

  2. edgeCountFeasibility() - an empirical verification. It runs the
     transformation and checks the invariant snapshot by snapshot, then
     diagnoses any violation with (1). This works for ANY transformation,
     because it tests the promise rather than re-deriving the mechanism.

Nothing here alters existing behaviour: this module is additive, and
setBridgeWidth's `strict` flag (which raises InfeasibleTransformation
instead of under-paying) defaults to off.

Scientific role: a transformation that cannot keep its own invariant has
not produced a counterfactual of the declared concept. Such rows are
reported with a status and EXCLUDED from aggregate conclusions rather than
repaired by guesswork - inventing a repair strategy would invent a
different concept.
'''

from .Communities import interCommunityEdges, intraCommunityEdges


class InfeasibleTransformation(Exception):
    ''' Raised by a transformation running in strict mode when it cannot
    honour its declared invariant.

    `detail` carries the measured counts that prove the infeasibility, so
    a caller can record the exact cause instead of a bare message. '''

    def __init__(self, message, detail=None):
        super().__init__(message)
        self.detail = dict(detail or {})


def bridgeWidthFeasibility(graph, communities, targetWidth):
    ''' Can `graph`'s bridge be set to `targetWidth` while keeping the node
    set AND the total edge count fixed?

    The mechanism being checked is setBridgeWidth's:
      widen by k   -> need k cross-community NON-edges to add,
                      and k intra-community EDGES to delete as payment
      narrow by k  -> need k bridge edges to delete (always available,
                      since k <= current width),
                      and k intra-community NON-edges to add as payment

    Returns a dict with the verdict and every count behind it. Pure
    inspection: the graph is not modified and no transformation is run.
    '''
    setA, setB = communities
    sizeA, sizeB = len(setA), len(setB)

    width = len(interCommunityEdges(graph, communities))
    intraEdges = len(intraCommunityEdges(graph, communities))
    crossPairs = sizeA * sizeB
    intraPairs = sizeA * (sizeA - 1) // 2 + sizeB * (sizeB - 1) // 2

    crossNonEdges = crossPairs - width
    intraNonEdges = intraPairs - intraEdges

    # setBridgeWidth clamps the target to >= 1 so the two communities are
    # never fully severed; feasibility must be judged on the CLAMPED target,
    # because that is the target the mechanism will actually pursue.
    clamped = max(1, int(targetWidth))
    k = clamped - width

    report = {
        "current_width": width,
        "requested_target": int(targetWidth),
        "clamped_target": clamped,
        "edge_change": k,
        "direction": "widen" if k > 0 else ("narrow" if k < 0 else "none"),
        "cross_nonedges_available": crossNonEdges,
        "intra_edges_available": intraEdges,
        "intra_nonedges_available": intraNonEdges,
        "feasible": True,
        "reason": None,
        "shortfall": 0,
    }

    if k > 0:
        if crossNonEdges < k:
            report["feasible"] = False
            report["reason"] = (
                "insufficient cross-community non-edges to widen the bridge")
            report["shortfall"] = k - crossNonEdges
        elif intraEdges < k:
            report["feasible"] = False
            report["reason"] = (
                "insufficient intra-community edges to preserve total "
                "edge count")
            report["shortfall"] = k - intraEdges
    elif k < 0:
        if intraNonEdges < -k:
            report["feasible"] = False
            report["reason"] = (
                "insufficient intra-community non-edges to preserve total "
                "edge count")
            report["shortfall"] = -k - intraNonEdges
    return report


def declaresEdgeCountPreservation(transformation):
    ''' Does this transformation promise to keep the total edge count?

    Read from the transformation's own `preservesEdgeCount` contract
    attribute - no name matching and no isinstance chains, so a new
    transformation declares its own promise. DensityTransformation sets it
    to False because the edge count IS its property: changing it is correct
    behaviour, not a violation. '''
    return bool(getattr(transformation, "preservesEdgeCount", True))


def edgeCountFeasibility(snapshots, transformation, delta,
                         communities=None, strictTransformation=None):
    ''' Verify the edge-count invariant for one (transformation, delta)
    pair on one temporal graph, by MEASUREMENT.

    Runs the transformation and compares the edge count of every snapshot
    before and after. Any mismatch is diagnosed, so the reported reason is
    measured rather than guessed.

    Two sources of a reason, in order of authority:

      strictTransformation  the same transformation built with strict=True.
          Its failure is raised at the exact point where the payment could
          not be made, so its message names the true cause. Pass it
          whenever one is available.
      bridgeWidthFeasibility  a fallback pool-size inspection of the
          violating snapshot. This is a necessary-condition check only: the
          payment prefers non-cut edges, which can shrink the usable pool
          below the raw count, so this fallback can fail to explain a real
          violation. When that happens the reason says so instead of
          inventing a cause.

    Returns a dict:
      declares_preservation  - did the transformation promise this at all
      feasible               - True when the promise held in EVERY snapshot
                               AND strict mode did not raise (always True
                               when nothing was promised)
      reason                 - the authoritative cause, or None
      strict_raised          - did the strict path fail (None if not probed)
      snapshots_checked / snapshots_violating
      edge_count_before / edge_count_after   - summed over snapshots
      violations             - per-snapshot detail records

    This function runs the transformation once (twice with a strict probe);
    it makes no model calls, so it does not affect TGAP's 1 + 2K model-call
    budget.
    '''
    declares = declaresEdgeCountPreservation(transformation)
    communities = communities if communities is not None \
        else getattr(transformation, "communities", None)

    strictRaised, strictReason, strictDetail = None, None, None
    if strictTransformation is not None:
        strictRaised = False
        try:
            strictTransformation.transform(snapshots, delta)
        except InfeasibleTransformation as failure:
            strictRaised = True
            strictReason = str(failure)
            strictDetail = failure.detail

    transformed = transformation.transform(snapshots, delta)
    before = [g.number_of_edges() for g in snapshots]
    after = [g.number_of_edges() for g in transformed]

    report = {
        "declares_preservation": declares,
        "feasible": True,
        "reason": None,
        "strict_raised": strictRaised,
        "strict_reason": strictReason,
        "strict_detail": strictDetail,
        "snapshots_checked": len(snapshots),
        "snapshots_violating": 0,
        "edge_count_before": int(sum(before)),
        "edge_count_after": int(sum(after)),
        "violations": [],
    }
    if not declares:
        return report

    for index, (originalGraph, newGraph, m0, m1) in enumerate(
            zip(snapshots, transformed, before, after)):
        if m0 == m1:
            continue
        detail = {
            "snapshot_index": index,
            "edge_count_before": m0,
            "edge_count_after": m1,
        }
        if communities is not None:
            achievedWidth = len(interCommunityEdges(newGraph, communities))
            diagnosis = bridgeWidthFeasibility(originalGraph, communities,
                                               achievedWidth)
            detail["achieved_width"] = achievedWidth
            detail["diagnosis"] = diagnosis
            detail["reason"] = diagnosis["reason"] or (
                "raw payment pools were large enough for the width reached, "
                "so the shortfall came from the non-cut-edge preference "
                "narrowing the usable pool")
        else:
            detail["reason"] = ("edge count changed and no partition was "
                                "available to diagnose the cause")
        report["violations"].append(detail)

    report["snapshots_violating"] = len(report["violations"])
    if report["violations"] or strictRaised:
        report["feasible"] = False
        # The strict path names the exact failure point; prefer it.
        report["reason"] = strictReason or report["violations"][0]["reason"]
    return report


def bridgeTrendDirection(snapshots, transformation, delta):
    ''' Did BridgeTrendTransformation move the trend the way it was asked
    to, and how much of the trajectory hit the width-1 floor?

    Background (the real-data failure mode this detects). The
    transformation walks backwards through time dividing each target width
    by (1 + delta), so the factor applied to the OLDEST snapshot is
    (1 + delta)^(T-1) - about 8.95 at delta = 0.1 with T = 24. Any target
    below 1 is clamped to 1, because setBridgeWidth never severs the last
    tie. Once several snapshots sit on that floor the intended geometric
    shape is destroyed, and the achieved slope change can even take the
    OPPOSITE sign to the requested one.

    Sign convention, from the transformation's own docstring: delta > 0
    pushes history DOWN, which makes the trajectory RISE, i.e. the slope
    should INCREASE. So the requested direction of the slope change is
    sign(delta).

    Returns a dict with requested/achieved direction, the saturated
    fraction, the before/after width extremes and a status:
      "ok"              moved as requested, nothing clamped to the floor
      "saturated"       moved as requested, but >= 1 snapshot hit the floor
      "wrong_direction" moved against the request (NOT a valid result)
      "no_property_change"  the slope did not move at all
    '''
    communities = transformation.communities
    widthsBefore = [len(interCommunityEdges(g, communities))
                    for g in snapshots]
    transformed = transformation.transform(snapshots, delta)
    widthsAfter = [len(interCommunityEdges(g, communities))
                   for g in transformed]

    slopeBefore = transformation.propertyValue(snapshots)
    slopeAfter = transformation.propertyValue(transformed)
    change = (slopeAfter - slopeBefore) if (slopeBefore is not None
                                            and slopeAfter is not None) else 0.0

    requested = 1 if delta > 0 else (-1 if delta < 0 else 0)
    achieved = 1 if change > 0 else (-1 if change < 0 else 0)

    # A snapshot counts as saturated when it was ABOVE the floor before and
    # sits ON the floor afterwards: that is the clamp biting, not a graph
    # that already had a single bridge edge.
    saturated = sum(1 for b, a in zip(widthsBefore, widthsAfter)
                    if a <= 1 and b > 1)

    if achieved == 0:
        status = "no_property_change"
    elif achieved != requested:
        status = "wrong_direction"
    elif saturated > 0:
        status = "saturated"
    else:
        status = "ok"

    return {
        "requested_delta": delta,
        "requested_direction": requested,
        "achieved_direction": achieved,
        "slope_before": slopeBefore,
        "slope_after": slopeAfter,
        "slope_change": change,
        "snapshots": len(snapshots),
        "compounding_factor": (1.0 + delta) ** (len(snapshots) - 1),
        "snapshots_saturated": saturated,
        "fraction_saturated": saturated / len(snapshots) if snapshots else 0.0,
        "min_bridge_width_before": min(widthsBefore) if widthsBefore else 0,
        "max_bridge_width_before": max(widthsBefore) if widthsBefore else 0,
        "min_bridge_width": min(widthsAfter) if widthsAfter else 0,
        "max_bridge_width": max(widthsAfter) if widthsAfter else 0,
        "status": status,
        "valid_for_analysis": status == "ok",
    }
