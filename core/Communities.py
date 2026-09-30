'''
Helper functions for working with communities (groups of nodes).

The CATALYST "wide bridge" concept is about the redundant ties BETWEEN
groups. Historically TGAP supported exactly two groups, because that is the
setting complex-contagion theory is stated in. Real ecosystems rarely have
exactly two: greedy modularity finds 42 communities in email-Eu-core (which
has 42 real departments), 36 in tgbl-wiki and 60 in bitcoin-otc. Collapsing
those to two discards up to 64% of the graph's modularity.

This module therefore represents a partition of ANY size N >= 1, while
staying byte-compatible with the two-community code that came before.

    THE BACKWARD-COMPATIBILITY TRICK
    Partition subclasses tuple, and its elements are the community node
    sets. So every existing line of the form

        setA, setB = communities

    keeps working unchanged when N == 2, and raises a plain ValueError when
    N != 2 - which is correct, because those call sites genuinely need a
    PAIR. Nothing had to be rewritten to gain N-community support; code that
    needs a pair now asks for a pair explicitly (see `pairs`), and code that
    only needs "are u and v in the same group?" uses `communityOf`.

Design rule (important for the explainer): everything here is
DETERMINISTIC - the same graph always yields the same partition, and the
same partition always yields the same ordering of communities and pairs.
That is what guarantees the STABILITY property of the explanations (same
input, same explanation, every time - see the TSAP evaluation checklist).
'''

import itertools

import networkx as nx
from networkx.algorithms import community


class Partition(tuple):
    ''' A partition of a graph's nodes into N communities, N >= 1.

    Behaves as a tuple of node sets, so it unpacks exactly like the
    (setA, setB) pairs used throughout earlier TGAP versions:

        setA, setB = partition          # works when len(partition) == 2
        partition[0]                    # works for any N
        len(partition)                  # the number of communities, N

    and additionally offers the two lookups section 11 of the design calls
    for - node -> community id, and community id -> nodes:

        partition.communityOf(node)     # -> int index, or None if absent
        partition[i]                    # -> the set of nodes in community i
        partition.pairs()               # -> [(0, 1), (0, 2), (1, 2), ...]

    `labels` is an optional human-readable name per community (e.g. real
    department ids for email-Eu-core). It never affects behaviour; it exists
    so figures and tables can say "Dept 4 - Dept 14" instead of "0 - 1".
    '''

    def __new__(cls, communities, labels=None):
        groups = tuple(set(group) for group in communities)
        if not groups:
            raise ValueError("a partition needs at least one community")
        seen = set()
        for index, group in enumerate(groups):
            overlap = seen & group
            if overlap:
                raise ValueError(
                    f"community {index} overlaps an earlier one on "
                    f"{sorted(overlap)[:5]}; communities must be disjoint")
            seen |= group
        self = super().__new__(cls, groups)
        self._labels = (tuple(labels) if labels is not None
                        else tuple(str(i) for i in range(len(groups))))
        if len(self._labels) != len(groups):
            raise ValueError("one label per community is required")
        # node -> community index, built once. Membership tests dominate
        # every transformation's inner loop, so this must be O(1).
        self._index = {node: i for i, group in enumerate(groups)
                       for node in group}
        return self

    @property
    def labels(self):
        ''' Human-readable name of each community, in community order. '''
        return self._labels

    def communityOf(self, node):
        ''' Community index of `node`, or None when the node is outside the
        partition. None rather than an exception: transformations routinely
        ask about nodes that may have been filtered out, and a missing node
        simply belongs to no community. '''
        return self._index.get(node)

    def sameCommunity(self, u, v):
        ''' True when u and v sit in the SAME community.

        This is the only membership question most transformations ask, and
        it is the reason N-community support was mostly free: the old form
        `(u in setA) == (v in setA)` answers it only for two groups, while
        this answers it for any number. Nodes outside the partition are
        treated as not sharing a community with anything, so a filtered-out
        node can never be mistaken for an insider. '''
        a, b = self._index.get(u), self._index.get(v)
        return a is not None and a == b

    def sizes(self):
        ''' Number of nodes in each community, in community order. '''
        return [len(group) for group in self]

    def nodes(self):
        ''' Every node covered by the partition, sorted for reproducibility. '''
        return sorted(self._index)

    def pairs(self):
        ''' Every unordered community pair (i, j) with i < j, in a fixed
        order. These are the bridges: N communities have N(N-1)/2 of them,
        so two communities have exactly one - which is why the original
        design could leave the pair implicit. '''
        return list(itertools.combinations(range(len(self)), 2))

    def labelOfPair(self, pair):
        ''' "A-B" style name for a community pair, for figures and tables. '''
        i, j = pair
        return f"{self._labels[i]}-{self._labels[j]}"

    def __repr__(self):
        return (f"Partition({len(self)} communities, sizes={self.sizes()})")


def asPartition(communities):
    ''' Accept anything the code base has ever used as a partition and
    return a Partition.

    Callers may legitimately hold a plain `(setA, setB)` tuple from older
    code, a list of sets, or an already-built Partition. Normalising at the
    boundary means the rest of the module never has to care, and no existing
    caller has to be edited. '''
    if isinstance(communities, Partition):
        return communities
    return Partition(communities)


def detectCommunities(graph, n=None):
    ''' Split the graph's nodes into communities with greedy modularity
    maximisation (a standard, deterministic algorithm).

    n=None   keep the communities the algorithm actually found. The number
             is a property of the data, not a parameter.
    n=k      merge down to exactly k communities by keeping the k-1 largest
             and pooling the remainder into the last one. Merging LOSES
             modularity and the amount lost is worth reporting (measured:
             0.00 on decentraland, 0.21 on email-Eu-core).

    NOTE: automatic detection is a convenience for exploration. For real
    experiments, PASS THE PARTITION EXPLICITLY (you usually know it from the
    domain: departments, organisations, teams). Detected communities can
    shift when the graph is perturbed, which would muddy the explanation.
    '''
    found = community.greedy_modularity_communities(graph)
    # greedy_modularity_communities returns communities largest-first.
    if n is None:
        # Natural k: report what the data supports. Empty groups cannot
        # occur here, because every community the detector returns is
        # non-empty by construction.
        return Partition([set(c) for c in found])
    if n < 1:
        raise ValueError("n must be at least 1")
    if n == 1:
        return Partition([set(graph.nodes())])
    kept = [set(c) for c in found[:n - 1]]
    rest = set(graph.nodes()) - set().union(*kept) if kept \
        else set(graph.nodes())
    # EXACTLY n groups, even when some are empty. This matters: the original
    # detectTwoCommunities returned (largest, everything-else) and
    # "everything-else" is empty on a graph the detector sees as one blob.
    # Callers unpack `setA, setB = communities`, so silently returning one
    # group would break them. Preserving the empty group preserves the
    # historical contract exactly.
    groups = kept + [rest]
    while len(groups) < n:
        groups.append(set())
    return Partition(groups)


def detectTwoCommunities(graph):
    ''' Split the graph's nodes into two sets (setA, setB).

    Kept EXACTLY as it was - the largest detected community versus
    everything else - because every published two-community result in this
    project was produced with it. It is now a thin call to
    detectCommunities(graph, n=2); a regression test asserts the two agree
    on the same graphs.

    NOTE: automatic detection is a convenience for exploration. For real
    experiments, PASS THE PARTITION EXPLICITLY (you usually know it from the
    domain: two organizations, two ecosystems, two teams). Detected
    communities can shift when the graph is perturbed, which would muddy
    the explanation. '''
    return detectCommunities(graph, n=2)


def interCommunityEdges(graph, communities, pair=None):
    ''' Return the list of edges whose endpoints lie in DIFFERENT
    communities.

    These edges ARE the bridge in the "wide bridge" sense: the count of them
    is the width of the bridge (how many redundant ties connect groups).

    pair=None    every cross-community edge, whatever groups it joins. With
                 two communities this is exactly the historical behaviour,
                 because there is only one boundary to cross.
    pair=(i, j)  only the edges joining community i to community j - the
                 bridge of ONE specific pair, which is what a transformation
                 needs when N > 2.

    The list is sorted so that callers sampling from it with a seeded random
    generator get reproducible results. '''
    partition = asPartition(communities)
    if pair is None:
        selected = [(u, v) for (u, v) in graph.edges()
                    if not partition.sameCommunity(u, v)
                    and partition.communityOf(u) is not None
                    and partition.communityOf(v) is not None]
    else:
        i, j = pair
        selected = [(u, v) for (u, v) in graph.edges()
                    if {partition.communityOf(u),
                        partition.communityOf(v)} == {i, j}]
    return sorted(selected)


def intraCommunityEdges(graph, communities, community_=None):
    ''' Return the list of edges with BOTH endpoints inside the SAME
    community (i.e. all edges that are not bridges). Sorted for
    reproducibility, same as interCommunityEdges.

    community_=None  edges internal to any community.
    community_=i     edges internal to community i only.
    '''
    partition = asPartition(communities)
    selected = [(u, v) for (u, v) in graph.edges()
                if partition.sameCommunity(u, v)
                and (community_ is None
                     or partition.communityOf(u) == community_)]
    return sorted(selected)


def bridgeMatrix(graph, communities):
    ''' The full pairwise bridge structure: {(i, j): number of edges joining
    community i and community j}, for every i < j.

    This is the N-community generalisation of "bridge width". Section 14 of
    the design asks for exactly this table:

        (A, B) -> 12
        (A, C) ->  5
        (B, C) ->  8

    Every pair is present, including pairs with zero edges, so downstream
    code can rely on the keys without checking. With two communities the
    matrix has a single entry whose value equals the historical bridge
    width - which is the identity the backward-compatibility tests assert.
    '''
    partition = asPartition(communities)
    counts = {pair: 0 for pair in partition.pairs()}
    for u, v in graph.edges():
        a, b = partition.communityOf(u), partition.communityOf(v)
        if a is None or b is None or a == b:
            continue
        counts[(a, b) if a < b else (b, a)] += 1
    return counts


def aggregateBridgeWidth(graph, communities):
    ''' One scalar bridge width for a partition of ANY size.

    DERIVED, NOT CHOSEN. The requirement is that a two-community graph must
    return exactly what the original implementation returned, namely the
    number of inter-community edges. The only aggregate over the pairwise
    matrix that satisfies that for N = 2 and remains a count of real edges
    for N > 2 is the SUM over all pairs - which is simply "how many edges
    cross a community boundary". Any weighted or averaged alternative would
    disagree with the historical value at N = 2 and would therefore break
    every result already published from this code base.

        aggregate = sum over i<j of bridgeMatrix[(i, j)]
                  = |{edges whose endpoints are in different communities}|
    '''
    return float(len(interCommunityEdges(graph, communities)))
