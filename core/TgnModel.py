'''
A learned temporal-graph model behind TGAP's existing model interface.

WHY THIS FILE IS SHAPED THE WAY IT IS
    TGAP explains a model through ONE method: predict(temporalGraph) -> float
    (Ivan's TemporalGraphModel contract). Everything below exists to satisfy
    that contract with a trained TGN, and nothing above this file knows a
    neural network is involved.

    That separation is the point. TGAP must NOT depend on gradients, hidden
    layers, attention weights, memory internals or any framework - only on
    the prediction. Swapping TGN for a future model means writing another
    adapter, not touching the explainer.

        Email-Eu-core events
              |
              v
        TGN (torch_geometric)         <- all the deep learning lives here
              |
              v
        TgnTemporalGraphModel         <- the adapter: snapshots -> float
              |
              v
        predict(temporalGraph)        <- Ivan's contract
              |
              v
        TgapExplainer                 <- unchanged, framework-agnostic

WHAT THE MODEL PREDICTS
    Link-prediction quality on the most recent snapshot, expressed as one
    number: the mean predicted probability that the edges actually present
    in the last snapshot exist. A structural perturbation that removes or
    reroutes ties changes which pairs are queried and what the memory has
    seen, so the number moves - which is exactly what TGAP measures.

    This is a DERIVED scalar, not a native TGN output. TGN natively scores
    individual candidate links; TGAP needs one number per temporal graph, so
    the adapter aggregates. The choice of aggregate is documented here
    rather than hidden, because it defines what the explanations are about.

TORCH IS AN OPTIONAL DEPENDENCY
    Importing this module without torch installed raises a clear message
    instead of an ImportError traceback, and every other part of TGAP keeps
    working. The test suite skips TGN tests when torch is absent.
'''

import numpy as np

try:
    import torch
    from torch.nn import Linear
    from torch_geometric.nn import TransformerConv
    from torch_geometric.nn.models.tgn import (
        IdentityMessage, LastAggregator, LastNeighborLoader, TGNMemory,
    )
    TORCH_AVAILABLE = True
except Exception as exc:                      # pragma: no cover
    TORCH_AVAILABLE = False
    _IMPORT_ERROR = exc

from .TemporalGraphModel import TemporalGraphModel


def requireTorch():
    ''' Fail with an actionable message rather than a stack trace. '''
    if not TORCH_AVAILABLE:
        raise ImportError(
            "TGN support needs PyTorch and PyTorch Geometric:\n"
            "    pip install torch --index-url "
            "https://download.pytorch.org/whl/cpu\n"
            "    pip install torch_geometric\n"
            "On Windows this also needs the Microsoft VC++ 2015-2022 "
            "redistributable, without which torch's c10.dll fails to load "
            f"(WinError 1114).\nOriginal error: {_IMPORT_ERROR}")


if TORCH_AVAILABLE:

    class GraphAttentionEmbedding(torch.nn.Module):
        ''' Node embeddings from TGN memory plus a graph-attention layer.

        This is the standard TGN embedding module: memory state carries what
        each node has experienced, and the attention layer mixes in the
        current neighbourhood. Time differences enter as an edge feature, so
        recent interactions weigh differently from old ones. '''

        def __init__(self, inChannels, outChannels, messageDimension,
                     timeEncoder):
            super().__init__()
            self.timeEncoder = timeEncoder
            edgeDimension = messageDimension + timeEncoder.out_channels
            self.conv = TransformerConv(inChannels, outChannels // 2, heads=2,
                                        dropout=0.1, edge_dim=edgeDimension)

        def forward(self, x, lastUpdate, edgeIndex, t, messages):
            relativeTime = lastUpdate[edgeIndex[0]] - t
            encoded = self.timeEncoder(relativeTime.to(x.dtype))
            edgeAttributes = torch.cat([encoded, messages], dim=-1)
            return self.conv(x, edgeIndex, edgeAttributes)

    class LinkPredictor(torch.nn.Module):
        ''' Scores a candidate link from the two endpoint embeddings. '''

        def __init__(self, dimension):
            super().__init__()
            self.source = Linear(dimension, dimension)
            self.target = Linear(dimension, dimension)
            self.out = Linear(dimension, 1)

        def forward(self, zSource, zTarget):
            hidden = self.source(zSource) + self.target(zTarget)
            return self.out(hidden.relu())


class TgnTemporalGraphModel(TemporalGraphModel):
    ''' Ivan's TemporalGraphModel contract, satisfied by a trained TGN.

    predict(temporalGraph) -> float
        Mean predicted probability of the edges present in the LAST
        snapshot, after replaying the whole temporal graph through TGN
        memory. Range (0, 1); higher means the model finds the present
        structure more consistent with the history it just saw.

    WHY THE LAST SNAPSHOT. TGAP's temporal transformations anchor the last
    snapshot deliberately, so a present-only readout gives the same expected
    invariance the metric-based persistence models give - which makes the
    learned model directly comparable with them instead of a special case.

    DETERMINISM. Memory is reset before every prediction and the events are
    replayed in a fixed order, so the same temporal graph always yields the
    same number. Without the reset, prediction n would depend on prediction
    n-1 and TGAP's stability property would be lost - the single most
    important detail in this adapter.

    COST. Each predict() replays every event, so TGAP's 1 + 2K model calls
    become 1 + 2K full replays. Budget accordingly on large graphs.
    '''

    def __init__(self, memory, embedding, predictor, neighborLoader,
                 nodeCount, device=None, assocMap=None):
        requireTorch()
        self.memory = memory
        self.embedding = embedding
        self.predictor = predictor
        self.neighborLoader = neighborLoader
        self.nodeCount = nodeCount
        self.device = device or torch.device("cpu")
        self.assoc = (assocMap if assocMap is not None
                      else torch.empty(nodeCount, dtype=torch.long,
                                       device=self.device))
        # Fixed mapping from graph node label -> contiguous integer id. TGN
        # indexes memory by position, so the mapping must not change between
        # calls or memory would be read for the wrong actor.
        self.nodeIndex = {}

    ##  Ivan's contract  ##

    def predict(self, temporalGraph):
        ''' The only method TGAP calls. '''
        requireTorch()
        if not temporalGraph:
            return 0.0
        events = self._eventsFrom(temporalGraph)
        if not events:
            return 0.0

        self.memory.eval()
        self.embedding.eval()
        self.predictor.eval()
        # Reset before every prediction: see DETERMINISM above.
        self.memory.reset_state()
        self.neighborLoader.reset_state()

        with torch.no_grad():
            self._replay(events[:-1] if len(events) > 1 else events)
            scores = self._scoreSnapshot(events[-1])
        return float(scores) if scores == scores else 0.0

    ##  Internals  ##

    def _identifier(self, node):
        ''' Stable contiguous id for a node label. '''
        if node not in self.nodeIndex:
            self.nodeIndex[node] = len(self.nodeIndex)
        return self.nodeIndex[node]

    def _eventsFrom(self, temporalGraph):
        ''' One (source, destination, time) batch per snapshot.

        The snapshot index is the timestamp: TGAP hands us discrete
        snapshots, not the original event stream, so time resolution is the
        snapshot. Edges are sorted so the replay order is deterministic. '''
        batches = []
        for index, graph in enumerate(temporalGraph):
            edges = sorted((self._identifier(u), self._identifier(v))
                           for u, v in graph.edges())
            if not edges:
                batches.append(None)
                continue
            source = torch.tensor([u for u, _ in edges], dtype=torch.long)
            destination = torch.tensor([v for _, v in edges], dtype=torch.long)
            # TGN stores last_update as a Long tensor, so timestamps must
            # be integers - a Float here fails with a dtype mismatch deep
            # inside memory.update_state.
            time = torch.full((len(edges),), index, dtype=torch.long)
            batches.append((source, destination, time))
        return [b for b in batches if b is not None]

    def _replay(self, batches):
        ''' Feed history into TGN memory without scoring anything. '''
        for source, destination, time in batches:
            nodes = torch.cat([source, destination])
            if int(nodes.max()) >= self.nodeCount:
                continue                    # node outside the trained space
            message = torch.zeros(source.size(0), self.memory.raw_msg_dim)
            self.memory.update_state(source, destination, time, message)
            self.neighborLoader.insert(source, destination)

    def _scoreSnapshot(self, batch):
        ''' Mean predicted probability of the edges in this snapshot. '''
        source, destination, time = batch
        nodes = torch.cat([source, destination])
        if int(nodes.max()) >= self.nodeCount:
            return 0.0
        neighbourNodes, edgeIndex, edgeIds = self.neighborLoader(
            torch.unique(nodes))
        self.assoc[neighbourNodes] = torch.arange(neighbourNodes.size(0),
                                                  device=self.device)
        memoryState, lastUpdate = self.memory(neighbourNodes)
        messages = torch.zeros(edgeIndex.size(1), self.memory.raw_msg_dim)
        embeddings = self.embedding(
            memoryState, lastUpdate, edgeIndex,
            torch.zeros(edgeIndex.size(1), dtype=torch.long), messages)
        logits = self.predictor(embeddings[self.assoc[source]],
                                embeddings[self.assoc[destination]])
        return torch.sigmoid(logits).mean().item()


def buildTgn(nodeCount, memoryDimension=32, timeDimension=32,
             embeddingDimension=32, seed=42, device=None):
    ''' Construct an UNTRAINED TGN wired into the adapter.

    Exposed separately from training so tests can exercise the adapter
    without a training run, and so a researcher can plug in different
    dimensions without editing the adapter.
    '''
    requireTorch()
    torch.manual_seed(seed)
    device = device or torch.device("cpu")

    memory = TGNMemory(
        nodeCount, raw_msg_dim=1, memory_dim=memoryDimension,
        time_dim=timeDimension,
        message_module=IdentityMessage(1, memoryDimension, timeDimension),
        aggregator_module=LastAggregator(),
    ).to(device)
    embedding = GraphAttentionEmbedding(
        memoryDimension, embeddingDimension, 1, memory.time_enc).to(device)
    predictor = LinkPredictor(embeddingDimension).to(device)
    loader = LastNeighborLoader(nodeCount, size=10, device=device)

    return TgnTemporalGraphModel(memory, embedding, predictor, loader,
                                 nodeCount, device=device)


def trainTgn(model, temporalGraph, epochs=3, learningRate=1e-3, seed=42):
    ''' Train the TGN on a temporal graph by self-supervised link
    prediction: present edges are positives, random node pairs are
    negatives.

    This is deliberately a SMALL training loop. The scientific claim of this
    project is about the EXPLAINER, not about beating a link-prediction
    benchmark; the model only needs to be a genuinely learned, non-trivial
    function for TGAP to explain. Reporting it as state of the art would be
    unsupported.

    Returns the per-epoch mean loss, so a caller can show the model actually
    learned something rather than asserting it.
    '''
    requireTorch()
    torch.manual_seed(seed)
    parameters = (list(model.memory.parameters())
                  + list(model.embedding.parameters())
                  + list(model.predictor.parameters()))
    optimizer = torch.optim.Adam(parameters, lr=learningRate)
    criterion = torch.nn.BCEWithLogitsLoss()

    batches = model._eventsFrom(temporalGraph)
    history = []
    for _ in range(epochs):
        model.memory.train()
        model.embedding.train()
        model.predictor.train()
        model.memory.reset_state()
        model.neighborLoader.reset_state()
        losses = []
        for source, destination, time in batches:
            if int(torch.cat([source, destination]).max()) >= model.nodeCount:
                continue
            optimizer.zero_grad()
            negative = torch.randint(0, model.nodeCount, (source.size(0),),
                                     dtype=torch.long)
            nodes = torch.cat([source, destination, negative])
            neighbourNodes, edgeIndex, _ = model.neighborLoader(
                torch.unique(nodes))
            model.assoc[neighbourNodes] = torch.arange(
                neighbourNodes.size(0), device=model.device)
            memoryState, lastUpdate = model.memory(neighbourNodes)
            messages = torch.zeros(edgeIndex.size(1), model.memory.raw_msg_dim)
            embeddings = model.embedding(
                memoryState, lastUpdate, edgeIndex,
                torch.zeros(edgeIndex.size(1), dtype=torch.long), messages)
            positiveOut = model.predictor(embeddings[model.assoc[source]],
                                          embeddings[model.assoc[destination]])
            negativeOut = model.predictor(embeddings[model.assoc[source]],
                                          embeddings[model.assoc[negative]])
            loss = (criterion(positiveOut, torch.ones_like(positiveOut))
                    + criterion(negativeOut, torch.zeros_like(negativeOut)))
            loss.backward()
            optimizer.step()
            # detach_() stops gradients flowing back through memory into a
            # previous batch; without it the graph is retained across the
            # whole replay and training fails on the second batch.
            model.memory.detach()
            model.neighborLoader.insert(source, destination)
            losses.append(float(loss))
        history.append(float(np.mean(losses)) if losses else float("nan"))
    return history
