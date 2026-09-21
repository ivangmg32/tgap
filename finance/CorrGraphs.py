
import numpy as np
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt

from Cache import Cache


class CorrGraphs:
    """Builds and visualizes stock correlation networks."""

    def __init__(self, tickers):
        """Initialize with a list of stock tickers."""
        self.tickers = tickers
        self.network = None

    def graph(self, yfPeriod="6mo"):
        """Calculate correlations and store the NetworkX graph."""

        # Create cache for the requested period
        cache = Cache(yfDuration=yfPeriod)

        # Download historical closing prices
        prices = pd.DataFrame()

        for ticker in self.tickers:
            history = cache.history(ticker)

            if history.empty or "Close" not in history.columns:
                print(f"No valid data for {ticker}")
                continue

            prices[ticker] = history["Close"]

        # Remove dates with missing data
        prices = prices.dropna()

        if prices.shape[1] < 2:
            raise ValueError("At least two valid tickers are required.")

        if prices.shape[0] < 2:
            raise ValueError("Not enough historical data.")

        # Calculate daily percentage returns
        returns = prices.pct_change().dropna()

        # Calculate the correlation matrix
        corr_matrix = returns.corr()

        # Convert correlation matrix into a NetworkX graph
        G = nx.Graph()

        # Add stock tickers as nodes
        G.add_nodes_from(corr_matrix.columns)

        # Add edges with correlation weights
        for i, ticker1 in enumerate(corr_matrix.columns):
            for ticker2 in corr_matrix.columns[i + 1:]:
                correlation = corr_matrix.loc[ticker1, ticker2]

                if pd.notna(correlation):
                    G.add_edge(
                        ticker1,
                        ticker2,
                        weight=correlation
                    )

        # Store the graph internally
        self.network = G

        return G

    def plotGraph(self, graph=None):
        """Plot the stored graph or a supplied NetworkX graph."""

        # Use the supplied graph or the last stored graph
        G = graph if graph is not None else self.network

        if G is None:
            raise ValueError("No graph available. Call graph() first.")

        if len(G.nodes) == 0:
            raise ValueError("The graph contains no nodes.")

        # Create a reproducible spring layout
        pos = nx.spring_layout(G, seed=42, k=1.5)

        # Extract edge correlations
        edges = list(G.edges(data=True))

        # Red = positive, blue = negative
        edge_colors = [
            "red" if data["weight"] >= 0 else "blue"
            for _, _, data in edges
        ]

        # Width proportional to absolute correlation
        edge_widths = [
            0.5 + 5 * abs(data["weight"])
            for _, _, data in edges
        ]

        # Node and label styling
        plt.figure(figsize=(12, 9))

        nx.draw_networkx_nodes(
            G,
            pos,
            node_color="lightgray",
            node_size=1800,
            edgecolors="black",
            linewidths=1.2
        )

        nx.draw_networkx_labels(
            G,
            pos,
            font_size=10,
            font_weight="bold"
        )

        nx.draw_networkx_edges(
            G,
            pos,
            edgelist=[(u, v) for u, v, _ in edges],
            edge_color=edge_colors,
            width=edge_widths,
            alpha=0.7
        )

        # Add correlation legend
        from matplotlib.lines import Line2D

        legend_elements = [
            Line2D(
                [0], [0],
                color="red",
                lw=3,
                label="Positive correlation"
            ),
            Line2D(
                [0], [0],
                color="blue",
                lw=3,
                label="Negative correlation"
            )
        ]

        plt.legend(handles=legend_elements, loc="best")

        plt.title("Stock Correlation Network")
        plt.axis("off")
        plt.tight_layout()
        plt.show()


def main():
    """Create and display a correlation graph for eight stocks."""

    tickers = [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "NVDA",
        "JPM",
        "XOM",
        "JNJ"
    ]

    # Create the correlation graph object
    corr_graphs = CorrGraphs(tickers)

    # Calculate correlations for the last six months
    corr_graphs.graph(yfPeriod="6mo")

    # Display the graph
    corr_graphs.plotGraph()


if __name__ == "__main__":
    main()