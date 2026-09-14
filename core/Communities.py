'''
Helper functions for working with communities (groups of nodes).

The CATALYST "wide bridge" concept is always about TWO groups and the
redundant ties BETWEEN them. Several metrics and transformations therefore
need a partition of the graph into two node sets. This module provides:

    detectTwoCommunities(graph)  - find such a partition automatically
    interCommunityEdges(graph, communities) - list the "bridge" edges

Design rule (important for the explainer): everything here is
DETERMINISTIC - the same graph always yields the same partition. This is
what guarantees the STABILITY property of the explanations (same input,
same explanation, every time - see the TSAP evaluation checklist).
'''

import networkx as nx
from networkx.algorithms import community


def detectTwoCommunities(graph):
    ''' Split the graph's nodes into two sets (setA, setB).

    We use greedy modularity maximization (a standard, deterministic
    community-detection algorithm) and then merge the result down to two
    groups: the largest detected community versus everything else.

    NOTE: automatic detection is a convenience for exploration. For real
    experiments, PASS THE PARTITION EXPLICITLY (you usually know it from
    the domain: two organizations, two ecosystems, two teams). Detected
    communities can shift when the graph is perturbed, which would muddy
    the explanation. '''
    communities = community.greedy_modularity_communities(graph)
    # greedy_modularity_communities returns communities sorted by size,
    # largest first. Keep the largest as side A, merge the rest as side B.
    setA = set(communities[0])
    setB = set(graph.nodes()) - setA
    return setA, setB


def interCommunityEdges(graph, communities):
    ''' Return the list of edges with one endpoint in each community.

    These edges ARE the bridge in the "wide bridge" sense: the count of
    them is the width of the bridge (how many redundant ties connect the
    two groups). The list is sorted so that callers sampling from it with
    a seeded random generator get reproducible results. '''
    setA, setB = communities
    bridges = [
        (u, v) for (u, v) in graph.edges()
        if (u in setA and v in setB) or (u in setB and v in setA)
    ]
    return sorted(bridges)


def intraCommunityEdges(graph, communities):
    ''' Return the list of edges with BOTH endpoints inside the same
    community (i.e. all edges that are not bridges). Sorted for
    reproducibility, same as interCommunityEdges. '''
    setA, setB = communities
    intra = [
        (u, v) for (u, v) in graph.edges()
        if (u in setA and v in setA) or (u in setB and v in setB)
    ]
    return sorted(intra)
