'''
Synthetic temporal-graph generator for developing and validating TGAP.

Why synthetic data first? Same reason TSAP validated against models whose
behavior is known: with real FOSS/DeFi data (WP2) everything is uncertain
at once. Here WE choose the ground truth - two communities, a bridge of a
known width, a known amount of churn, an optional known bridge decay - so
when the explainer speaks we can check whether it tells the truth.

The generated world, in ASCII:

      community A            bridge            community B
      (dense blob)      (bridgeWidth edges)    (dense blob)
        o--o--o        ====================      o--o--o
       /|  |  |\       ====================     /|  |  |\
      o-o--o--o-o                              o-o--o--o-o

A temporal graph is a list of such snapshots where, from one snapshot to
the next, some intra-community edges are rewired ("churn": people change
collaborators) and the bridge optionally loses edges over time
("bridgeDrift": the CATALYST bridge-decay scenario that early-warning
models are supposed to catch).
'''

import random

import networkx as nx


def makeTwoCommunityGraph(nPerCommunity=15, pIntra=0.3, bridgeWidth=6,
                          seed=42, nPerCommunityB=None):
    ''' Build one snapshot: two communities joined by a bridge.

    nPerCommunity  : nodes in community A (nodes 0..nA-1).
    nPerCommunityB : nodes in community B (nodes nA..nA+nB-1);
                     defaults to nPerCommunity (equal sizes). Unequal
                     sizes matter for testing: real ecosystems are
                     asymmetric (a big org collaborating with a small
                     one), and several algorithms behave differently
                     when |A| != |B|.
    pIntra         : probability of an edge between two nodes of the SAME
                     community (controls how dense each blob is).
    bridgeWidth    : exact number of inter-community edges.
    seed           : random seed - same seed, same graph (reproducibility).

    Returns (graph, communities) where communities = (setA, setB), ready
    to be passed to BridgeWidthMetric / BridgeWidthTransformation. '''
    rng = random.Random(seed)
    nA = nPerCommunity
    nB = nPerCommunityB if nPerCommunityB is not None else nPerCommunity
    setA = set(range(nA))
    setB = set(range(nA, nA + nB))

    g = nx.Graph()
    g.add_nodes_from(range(nA + nB))

    # 1. A path backbone inside each community guarantees each blob is
    #    connected regardless of how the random edges fall.
    for i in range(nA - 1):
        g.add_edge(i, i + 1)                 # backbone of A: 0-1-2-...
    for i in range(nB - 1):
        g.add_edge(nA + i, nA + i + 1)       # backbone of B: nA-(nA+1)-...

    # 2. Random intra-community edges with probability pIntra.
    for part in (sorted(setA), sorted(setB)):
        for i in range(len(part)):
            for j in range(i + 2, len(part)):  # +2: backbone already did i+1
                if rng.random() < pIntra:
                    g.add_edge(part[i], part[j])

    # 3. Exactly bridgeWidth inter-community edges, sampled at random.
    crossPairs = [(a, b) for a in sorted(setA) for b in sorted(setB)]
    g.add_edges_from(rng.sample(crossPairs, bridgeWidth))

    return g, (setA, setB)


def makeTemporalGraph(nSnapshots=8, nPerCommunity=15, pIntra=0.3,
                      bridgeWidth=6, churn=0.05, bridgeDrift=0, seed=42,
                      nPerCommunityB=None):
    ''' Build a temporal graph: a list of snapshots evolving over time.

    nSnapshots  : how many snapshots (oldest -> newest).
    churn       : fraction of intra-community edges rewired between
                  consecutive snapshots (0.05 = 5% of collaborations
                  change partners each step). Models ordinary turnover.
    bridgeDrift : how many bridge edges are LOST per step. 0 = stable
                  bridge; 1 = the bridge thins by one tie every step -
                  the "bridge decay" pattern an early-warning model
                  should pick up. (Negative values would widen it.)
    Other parameters as in makeTwoCommunityGraph.

    Returns (temporalGraph, communities) where temporalGraph is the list
    of snapshots and communities the fixed (setA, setB) partition. '''
    g, communities = makeTwoCommunityGraph(
        nPerCommunity=nPerCommunity, pIntra=pIntra,
        bridgeWidth=bridgeWidth, seed=seed,
        nPerCommunityB=nPerCommunityB)
    setA, setB = communities

    rng = random.Random(seed + 1)  # separate stream from the base graph
    temporalGraph = [g]
    for _ in range(nSnapshots - 1):
        g = g.copy()

        # --- churn: rewire a fraction of intra-community edges ---
        intra = sorted(
            (u, v) for (u, v) in g.edges()
            if (u in setA and v in setA) or (u in setB and v in setB)
        )
        nRewire = round(churn * len(intra))
        for u, v in rng.sample(intra, nRewire):
            # Node u drops the tie to v and forms a new tie inside its
            # own community (a person switching collaborators).
            part = sorted(setA if u in setA else setB)
            candidates = [w for w in part
                          if w != u and not g.has_edge(u, w)]
            if candidates:
                g.remove_edge(u, v)
                g.add_edge(u, rng.choice(candidates))

        # --- drift: the bridge slowly thins (or widens) ---
        bridges = sorted(
            (u, v) for (u, v) in g.edges()
            if (u in setA and v in setB) or (u in setB and v in setA)
        )
        if bridgeDrift > 0:
            # Remove bridgeDrift bridge edges, but never the last one.
            nRemove = min(bridgeDrift, len(bridges) - 1)
            if nRemove > 0:
                g.remove_edges_from(rng.sample(bridges, nRemove))
        elif bridgeDrift < 0:
            # Widen: add |bridgeDrift| new cross edges.
            candidates = [(a, b) for a in sorted(setA) for b in sorted(setB)
                          if not g.has_edge(a, b)]
            nAdd = min(-bridgeDrift, len(candidates))
            g.add_edges_from(rng.sample(candidates, nAdd))

        temporalGraph.append(g)

    return temporalGraph, communities


##  Scenario registry: controlled worlds with known ground truth  ##

# Each scenario is a named configuration whose driving structural story
# we know by construction. Used by the faithfulness evaluation to ask:
# "does TGAP identify the concept that actually characterizes this world?"
SCENARIOS = {
    "stable":          "constant bridge width, mild churn",
    "growing-bridge":  "bridge gains one tie per snapshot (positive trend)",
    "decaying-bridge": "bridge loses one tie per snapshot (negative trend)",
    "high-churn":      "25% of intra ties turn over per snapshot",
    "low-churn":       "1% of intra ties turn over per snapshot",
    "centralizing":    "ties progressively concentrate on a hub over time",
    "decentralizing":  "an initially centralized graph flattens over time",
    "asymmetric":      "community B twice the size of community A",
    "sparse":          "thin communities (pIntra=0.12)",
    "dense":           "thick communities (pIntra=0.6)",
}


def makeScenario(name, nSnapshots=6, nPerCommunity=15, seed=42):
    ''' Build a named ground-truth scenario.

    Returns (temporalGraph, communities, info) where info records the
    scenario's known ground truth: its name, a human description, and
    `groundTruth` - a dict of facts the evaluation can test against
    (e.g. {"bridgeTrendSign": -1} for the decaying bridge).

    All scenarios share the node-numbering convention (A first, then B)
    and are fully determined by `seed`. '''
    if name not in SCENARIOS:
        raise ValueError(f"unknown scenario '{name}'; "
                         f"choose from {sorted(SCENARIOS)}")
    info = {"name": name, "description": SCENARIOS[name], "groundTruth": {}}
    kwargs = dict(nSnapshots=nSnapshots, nPerCommunity=nPerCommunity,
                  bridgeWidth=8, churn=0.05, seed=seed)

    if name == "stable":
        tg, communities = makeTemporalGraph(**kwargs)
        info["groundTruth"] = {"bridgeTrendSign": 0}
    elif name == "growing-bridge":
        tg, communities = makeTemporalGraph(bridgeDrift=-1, **kwargs)
        info["groundTruth"] = {"bridgeTrendSign": +1}
    elif name == "decaying-bridge":
        tg, communities = makeTemporalGraph(bridgeDrift=+1, **kwargs)
        info["groundTruth"] = {"bridgeTrendSign": -1}
    elif name == "high-churn":
        kwargs["churn"] = 0.25
        tg, communities = makeTemporalGraph(**kwargs)
        info["groundTruth"] = {"churnLevel": "high"}
    elif name == "low-churn":
        kwargs["churn"] = 0.01
        tg, communities = makeTemporalGraph(**kwargs)
        info["groundTruth"] = {"churnLevel": "low"}
    elif name in ("centralizing", "decentralizing"):
        # Build a stable world, then progressively rewire each snapshot
        # toward (or away from) the hub by REUSING the centralization
        # transformation with a per-snapshot growing delta. Snapshot 0 is
        # untouched; snapshot t gets |delta| = 0.06*t. Deterministic.
        from .Transformations import CentralizationTransformation
        tg, communities = makeTemporalGraph(**kwargs)
        sign = +1 if name == "centralizing" else -1
        trans = CentralizationTransformation(communities, seed=seed)
        tg = [trans.transformGraph(g, sign * 0.06 * t) if t > 0 else g
              for t, g in enumerate(tg)]
        info["groundTruth"] = {"centralizationTrendSign": sign}
    elif name == "asymmetric":
        tg, communities = makeTemporalGraph(
            nPerCommunityB=2 * nPerCommunity, **kwargs)
        info["groundTruth"] = {"sizeRatio": 2}
    elif name == "sparse":
        kwargs["pIntra"] = 0.12
        tg, communities = makeTemporalGraph(**kwargs)
        info["groundTruth"] = {"regime": "sparse"}
    elif name == "dense":
        kwargs["pIntra"] = 0.6
        tg, communities = makeTemporalGraph(**kwargs)
        info["groundTruth"] = {"regime": "dense"}

    return tg, communities, info
