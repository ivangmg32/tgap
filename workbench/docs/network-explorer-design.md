# Network comparison: design evidence and implementation

The rejected prototype placed nodes on a grid to make labels fit. This broke the
node-link structure and did not scale: every connection became DOM content. The
replacement preserves the server's topology-driven coordinates, applying only a
uniform scale and translation shared by every snapshot and panel.

## Research and comparable tools

- [GraphDiaries — Bach, Pietriga & Fekete, TVCG 2014](https://aviz.fr/~bbach/graphdiaries/Bach2013GraphDiaries.pdf): explicit difference highlighting, temporal navigation and small multiples support following network changes. Stable global layouts trade compactness for consistency; they are not universally superior for every task. Applied here: fixed coordinates, a change-volume timeline, linked before/after views and an optional overlaid difference graph. We do not require users to watch an animation to identify edits.
- [DiffSeer — Wen et al.](https://arxiv.org/abs/2302.07609): explicitly encoding graph differences reduces reliance on mentally subtracting views. Its overview/detail approach informs our counts, change list and exact element inspector. We retain a node-link diagram rather than adopting its nested matrix representation because preserving the graph view is a task requirement.
- [Sigma label placement](https://www.sigmajs.org/how-to/labels/styles-positioning/) and [settings](https://www.sigmajs.org/reference/settings/): use density and zoom to control the number of labels. Applied here: measured text bounds, a spatial collision index, priority for changed/selected endpoints, and screen-space labels that remain readable when zoomed. A full name is always available through search and selection; the overview does not promise simultaneous visibility of thousands of names.
- [Cytoscape.js interaction and performance documentation](https://js.cytoscape.org/): graph interaction, preset layouts, touch gestures and Canvas rendering; labels, pixel ratio and expensive edge geometry affect performance. We use a pinned, locally served Cytoscape.js 3.35.0, preset coordinates, straight context edges and bounded device pixel ratio. Native labels are disabled; our collision-aware label layer renders above the network. No runtime CDN is needed.
- [Gephi quickstart](https://gephi.org/quickstart/): attribute/topology filters and separate data inspection complement the graph. Applied here: entire network / changes / change neighborhood / selected neighborhood, node search and a paginated connection register. Filters change the view, never the underlying data.

## Readability and truthful differences

Blue solid edges are added; orange dashed edges are removed. Unchanged connections
remain in the background. The before panel excludes additions, the after panel
excludes removals, and the difference overlay shows both. Counts distinguish
original/transformed edge totals from the union of both. Endpoint outlines mean an
incident connection changed; they do not mean a node was inserted or deleted.

Labels are placed around graph nodes, using leader lines when nearby positions are
occupied. Their boxes cannot overlap each other or visible node bodies. Longer
names may be abbreviated in the diagram; the inspector, search results, table and
CSV retain the complete string. Edge IDs are stable across snapshots. Selection
shows precise endpoint names and presence in both states.

## Scale and lifecycle

Indexes of nodes, edges, changes and adjacency are cached once per view. Canvas
rendering avoids SVG/DOM growth proportional to graph size. The connection table
renders at most 30 rows; the initial change list renders eight items, and search
renders eight matches. No edges are sampled or silently capped. A filtered graph
reports how much of the network is retained.

Networks above 1,500 nodes or 8,000 edges start in the single-panel difference
overlay, with before/after comparison available explicitly. Only visible graph
panels initialize a renderer; hidden renderers are destroyed when switching modes. Resize observers handle responsive
panels and charts opened from collapsed details; cameras retain the same graph
center and scale. Renderers, observers and scheduled work are released when the
Guided view is replaced or the user signs out.

Exports rebuild a self-contained full-network SVG from the indexed model. They do
not capture the DOM viewport or depend on a mounted Canvas, so collapsed cards and
zoomed/panned graphs export the complete extent. PNGs rasterize this SVG. The
bulk-image ZIP contains all rendered chart cards. Large exports deliberately use
adaptive nonoverlapping labels; exact complete connection records remain available
in CSV and JSON rather than becoming an unreadable million-pixel image.

## Validation

`workbench/tests/graph_browser_check.py` checks affine preservation of the input
layout, exact edge counts, linked camera positions, drag/keyboard navigation,
nonoverlapping labels, search, selection, neighborhoods, snapshot boundaries,
mobile page overflow, delayed initialization, full SVG/PNG output and the actual
bulk-download button. Its scale fixture has 5,000 nodes and 25,000 original edges,
with 25 additions and 25 removals. It checks both renderers, exact filtered counts,
bounded DOM rows and pagination through all 25,025 union connections. Timings are
saved to `metrics.json`; these are local measurements, not a guarantee for
arbitrarily large networks or low-end devices.
