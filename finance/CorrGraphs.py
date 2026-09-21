
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
        self.temporalNetworks = []

    def _buildGraph(self, returns):
        """Build a NetworkX graph from return correlations."""

        corr_matrix = returns.corr()

        G = nx.Graph()
        G.add_nodes_from(corr_matrix.columns)

        for i, ticker1 in enumerate(corr_matrix.columns):
            for ticker2 in corr_matrix.columns[i + 1:]:
                correlation = corr_matrix.loc[ticker1, ticker2]

                if pd.notna(correlation):
                    G.add_edge(
                        ticker1,
                        ticker2,
                        weight=correlation
                    )

        return G

    def graph(self, yfPeriod="6mo"):
        """Calculate correlations and store the NetworkX graph."""

        cache = Cache(yfDuration=yfPeriod)
        prices = pd.DataFrame()

        for ticker in self.tickers:
            history = cache.history(ticker)

            if history.empty or "Close" not in history.columns:
                print(f"No valid data for {ticker}")
                continue

            prices[ticker] = history["Close"]

        prices = prices.dropna()

        if prices.shape[1] < 2:
            raise ValueError("At least two valid tickers are required.")

        returns = prices.pct_change().dropna()

        self.network = self._buildGraph(returns)

        return self.network

    
    def temporalGraph(
        self,
        historicPeriod="5y",
        slidingWindowPeriod="6mo",
        approxGraphs=10
    ):
        """Build correlation graphs indexed by window ending date."""

        if approxGraphs < 1:
            raise ValueError("approxGraphs must be at least 1.")

        # Retrieve historical prices
        cache = Cache(yfDuration=historicPeriod)
        prices = pd.DataFrame()

        for ticker in self.tickers:
            history = cache.history(ticker)

            if history.empty or "Close" not in history.columns:
                print(f"No valid data for {ticker}")
                continue

            prices[ticker] = history["Close"]

        prices = prices.dropna()

        if prices.shape[1] < 2:
            raise ValueError("At least two valid tickers are required.")

        # Calculate daily returns
        returns = prices.pct_change().dropna()

        if len(returns) < 2:
            raise ValueError("Not enough historical data.")

        # Parse sliding window duration
        #window_offset = pd.tseries.frequencies.to_offset(
        #    slidingWindowPeriod
        #)
        window_offset = self._periodToOffset(
            slidingWindowPeriod
        )

        # Actual trading dates available as window endings
        dates = returns.index

        # Determine valid ending dates
        valid_dates = dates[
            dates >= dates[0] + window_offset
        ]

        if len(valid_dates) == 0:
            raise ValueError(
                "Sliding window is longer than available history."
            )

        # Select approximately evenly distributed actual dates
        n_graphs = min(approxGraphs, len(valid_dates))

        indices = np.linspace(
            0,
            len(valid_dates) - 1,
            n_graphs,
            dtype=int
        )

        ending_dates = valid_dates[indices]

        # Build graphs indexed by actual ending date
        temporal_series = {}

        for end_date in ending_dates:

            start_date = end_date - window_offset

            window_returns = returns.loc[
                (returns.index >= start_date) &
                (returns.index <= end_date)
            ]

            if len(window_returns) < 2:
                continue

            G = self._buildGraph(window_returns)

            # Store temporal metadata
            G.graph["start_date"] = window_returns.index[0]
            G.graph["end_date"] = end_date
            G.graph["period"] = slidingWindowPeriod

            temporal_series[end_date] = G

        # Pandas Series indexed by the ending date
        self.temporalNetworks = pd.Series(
            temporal_series,
            dtype=object
        ).sort_index()

        if len(self.temporalNetworks) > 0:
            self.network = self.temporalNetworks.iloc[-1]

        return self.temporalNetworks

    
    def _periodToOffset(self, period):
        """Convert yfinance period string to a calendar offset."""

        if period.endswith("mo"):
            months = int(period[:-2])
            return pd.DateOffset(months=months)

        if period.endswith("y"):
            years = int(period[:-1])
            return pd.DateOffset(years=years)

        if period.endswith("d"):
            days = int(period[:-1])
            return pd.DateOffset(days=days)

        raise ValueError(
            f"Unsupported period: {period}. "
            "Use formats such as '30d', '6mo', or '5y'."
        )


    def _periodToDays(self, period):
        """Convert a yfinance period string to approximate days."""

        units = {
            "d": 1,
            "mo": 30,
            "y": 365
        }

        for unit, days in units.items():
            if period.endswith(unit):
                value = period[:-len(unit)]
                return int(value) * days

        raise ValueError(
            f"Unsupported period: {period}. "
            "Use formats such as '30d', '6mo', or '5y'."
        )
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

    def plotTemporalGraph(self, nFrames=6):
        """Plot selected temporal graphs with their ending dates."""

        if self.temporalNetworks is None or len(self.temporalNetworks) == 0:
            raise ValueError(
                "No temporal graphs available. Call temporalGraph() first."
            )

        nFrames = min(nFrames, len(self.temporalNetworks))

        if nFrames < 1:
            raise ValueError("nFrames must be at least 1.")

        # Select evenly distributed graph positions
        indices = np.linspace(
            0,
            len(self.temporalNetworks) - 1,
            nFrames,
            dtype=int
        )

        nCols = min(3, nFrames)
        nRows = int(np.ceil(nFrames / nCols))

        fig, axes = plt.subplots(
            nRows,
            nCols,
            figsize=(6 * nCols, 5 * nRows),
            squeeze=False
        )

        axes = axes.flatten()

        for plotIndex, graphIndex in enumerate(indices):

            # Retrieve graph and its actual date index
            end_date = self.temporalNetworks.index[graphIndex]
            G = self.temporalNetworks.iloc[graphIndex]

            ax = axes[plotIndex]

            pos = nx.spring_layout(G, seed=42, k=1.5)

            edges = list(G.edges(data=True))

            edge_colors = [
                "red" if data["weight"] >= 0 else "blue"
                for _, _, data in edges
            ]

            edge_widths = [
                0.5 + 5 * abs(data["weight"])
                for _, _, data in edges
            ]

            nx.draw_networkx_nodes(
                G,
                pos,
                ax=ax,
                node_color="lightgray",
                node_size=1200,
                edgecolors="black",
                linewidths=1
            )

            nx.draw_networkx_labels(
                G,
                pos,
                ax=ax,
                font_size=8,
                font_weight="bold"
            )

            nx.draw_networkx_edges(
                G,
                pos,
                ax=ax,
                edgelist=[(u, v) for u, v, _ in edges],
                edge_color=edge_colors,
                width=edge_widths,
                alpha=0.7
            )

            # Display the actual ending date
            ax.set_title(
                f"Window ending: {end_date.strftime('%Y-%m-%d')}",
                fontsize=11
            )

            ax.axis("off")

        for ax in axes[nFrames:]:
            ax.axis("off")

        fig.suptitle(
            "Temporal Stock Correlation Networks",
            fontsize=16
        )

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

    # Generate temporal correlation graphs
    corr_graphs.temporalGraph(
        historicPeriod="5y",
        slidingWindowPeriod="6mo",
        approxGraphs=20
    )

    # Display 6 evenly distributed temporal frames
    corr_graphs.plotTemporalGraph(nFrames=6)


if __name__ == "__main__":
    main()