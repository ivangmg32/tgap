'''
WRAPPER 6 - Ivan's stock market, with your own model.

    python examples/wrapper/06_stock_market.py

Ivan's price cache and correlation networks (finance/) become a temporal
graph: stocks are people, a strong return correlation is a tie, sectors are
the groups. The wrapper then works exactly as for any other data.

Offline: the eight stocks and five years of prices are cached in the repo.
Results: output/examples/wrapper_06_stock_market/
'''
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from core import interCommunityEdges           # noqa: E402
from finance.networks import prepare           # noqa: E402
from tgap_wrapper import Wrapper               # noqa: E402

# ============================== PARAMETERS ==============================
MINIMUM_CORRELATION = 0.3     # two stocks are "tied" when they move this together
WINDOW, SNAPSHOTS = "6mo", 12
# ========================================================================

market = prepare("wrapper_06", window=WINDOW, snapshots=SNAPSHOTS,
                 minimum=MINIMUM_CORRELATION, focus="Technology")
w = Wrapper("wrapper_06_stock_market", market.snapshots, market.communities)


@w.model
def cross_sector_contagion(snapshots):
    ''' Share of strong co-movements that cross sectors, over the last 4
    windows: high = the market moves as one block. '''
    shares = []
    for graph in snapshots[-4:]:
        cross = len(interCommunityEdges(graph, w.groups))
        shares.append(cross / max(1, graph.number_of_edges()))
    return sum(shares) / len(shares)


w.concept(["bridge_width", "density", "centralization"])
w.explain()
