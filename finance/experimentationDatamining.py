"""
experimentationDatamining.py

Data-mining experimentation for temporal stock correlation networks.

Research questions:
    RQ1 / H1:
        Do synchronization levels differ across temporal windows?

    RQ2 / H2:
        Is network density associated with mean absolute correlation?

    RQ3 / H3:
        Does within-sector correlation differ from cross-sector correlation?

    RQ4 / H4:
        Are observed network statistics distinguishable from a null model?

The module is designed to be reusable from Python or executable as a script.

Dependencies:
    numpy
    pandas
    scipy
    statsmodels (optional)
    networkx
    CorrGraph.py (with its Cache.py dependency)

Example:
    python experimentationDatamining.py --period 5y --window 6mo --graphs 20
"""

from __future__ import annotations

import argparse
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import networkx as nx
import numpy as np
import pandas as pd
from scipy import stats

from CorrGraphs import CorrGraphs

try:
    import statsmodels.api as sm
except ImportError:  # pragma: no cover
    sm = None


DEFAULT_TICKERS = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "JPM",
    "XOM",
    "JNJ",
]

DEFAULT_SECTORS = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "GOOGL": "Technology",
    "AMZN": "Consumer",
    "NVDA": "Technology",
    "JPM": "Financials",
    "XOM": "Energy",
    "JNJ": "Healthcare",
}


@dataclass
class ExperimentConfig:
    """Configuration shared by all experiments."""

    historic_period: str = "5y"
    sliding_window_period: str = "6mo"
    approx_graphs: int = 20
    alpha: float = 0.05
    strong_correlation_threshold: float = 0.70
    bootstrap_iterations: int = 2000
    block_length: int = 20
    null_iterations: int = 500
    random_seed: int = 42


def _validate_temporal_networks(temporal_networks: pd.Series) -> None:
    if temporal_networks is None or len(temporal_networks) == 0:
        raise ValueError("No temporal networks are available.")


def _graph_correlation_values(graph: nx.Graph) -> np.ndarray:
    return np.asarray(
        [
            abs(float(data["weight"]))
            for _, _, data in graph.edges(data=True)
            if "weight" in data and pd.notna(data["weight"])
        ],
        dtype=float,
    )


def _graph_statistics(
    graph: nx.Graph,
    strong_correlation_threshold: float = 0.70,
) -> Dict[str, float]:
    nodes = graph.number_of_nodes()
    possible_edges = nodes * (nodes - 1) / 2
    edge_count = graph.number_of_edges()

    absolute_correlations = _graph_correlation_values(graph)
    signed_correlations = np.asarray(
        [
            float(data["weight"])
            for _, _, data in graph.edges(data=True)
            if "weight" in data and pd.notna(data["weight"])
        ],
        dtype=float,
    )

    if possible_edges > 0:
        density = edge_count / possible_edges
    else:
        density = np.nan

    if len(absolute_correlations) > 0:
        mean_abs_corr = float(np.mean(absolute_correlations))
        mean_signed_corr = float(np.mean(signed_correlations))
        strong_edge_fraction = float(
            np.mean(absolute_correlations >= strong_correlation_threshold)
        )
    else:
        mean_abs_corr = np.nan
        mean_signed_corr = np.nan
        strong_edge_fraction = np.nan

    clustering = nx.average_clustering(
        graph,
        weight=None,
    ) if nodes > 0 else np.nan

    weighted_strengths = dict(graph.degree(weight="weight"))
    mean_strength = (
        float(np.mean(list(weighted_strengths.values())))
        if weighted_strengths
        else np.nan
    )

    return {
        "n_nodes": float(nodes),
        "n_edges": float(edge_count),
        "density": float(density),
        "mean_abs_corr": mean_abs_corr,
        "mean_signed_corr": mean_signed_corr,
        "strong_edge_fraction": strong_edge_fraction,
        "average_clustering": float(clustering),
        "mean_weighted_strength": mean_strength,
    }




def _mean_graph_statistic(
    graph: nx.Graph,
    statistic: str = "mean_abs_corr",
    threshold: float = 0.70,
) -> float:
    """Return one scalar statistic from a correlation graph."""
    statistics = _graph_statistics(
        graph,
        strong_correlation_threshold=threshold,
    )

    aliases = {
        "mean_abs_corr": "mean_abs_corr",
        "mean_signed_corr": "mean_signed_corr",
        "density": "density",
        "strong_edge_fraction": "strong_edge_fraction",
        "clustering": "average_clustering",
        "average_clustering": "average_clustering",
        "mean_strength": "mean_weighted_strength",
    }

    key = aliases.get(statistic)
    if key is None:
        raise ValueError(
            f"Unsupported statistic '{statistic}'. "
            f"Choose from: {', '.join(sorted(aliases))}."
        )

    return float(statistics[key])

def extract_temporal_features(
    temporal_networks: pd.Series,
    strong_correlation_threshold: float = 0.70,
) -> pd.DataFrame:
    """Convert each temporal graph into one row of numerical features."""
    _validate_temporal_networks(temporal_networks)

    rows = []
    for end_date, graph in temporal_networks.items():
        features = _graph_statistics(
            graph,
            strong_correlation_threshold=strong_correlation_threshold,
        )
        features["end_date"] = pd.Timestamp(end_date)
        features["start_date"] = graph.graph.get("start_date")
        rows.append(features)

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    return result.set_index("end_date").sort_index()


def _bootstrap_mean_difference(
    group_a: np.ndarray,
    group_b: np.ndarray,
    iterations: int,
    rng: np.random.Generator,
) -> Tuple[float, float, float]:
    """Bootstrap mean difference and its percentile confidence interval."""
    group_a = np.asarray(group_a, dtype=float)
    group_b = np.asarray(group_b, dtype=float)

    if len(group_a) == 0 or len(group_b) == 0:
        return np.nan, np.nan, np.nan

    observed = float(np.mean(group_a) - np.mean(group_b))
    bootstrap_differences = np.empty(iterations)

    for index in range(iterations):
        sample_a = rng.choice(group_a, size=len(group_a), replace=True)
        sample_b = rng.choice(group_b, size=len(group_b), replace=True)
        bootstrap_differences[index] = np.mean(sample_a) - np.mean(sample_b)

    lower, upper = np.percentile(bootstrap_differences, [2.5, 97.5])
    return observed, float(lower), float(upper)


def _welch_test(
    group_a: np.ndarray,
    group_b: np.ndarray,
) -> Dict[str, float]:
    if len(group_a) < 2 or len(group_b) < 2:
        return {
            "difference": np.nan,
            "t_statistic": np.nan,
            "p_value": np.nan,
            "cohens_d": np.nan,
        }

    result = stats.ttest_ind(
        group_a,
        group_b,
        equal_var=False,
        nan_policy="omit",
    )

    pooled_std = np.sqrt(
        (
            (len(group_a) - 1) * np.var(group_a, ddof=1)
            + (len(group_b) - 1) * np.var(group_b, ddof=1)
        )
        / (len(group_a) + len(group_b) - 2)
    )

    difference = float(np.mean(group_a) - np.mean(group_b))
    cohens_d = difference / pooled_std if pooled_std > 0 else np.nan

    return {
        "difference": difference,
        "t_statistic": float(result.statistic),
        "p_value": float(result.pvalue),
        "cohens_d": float(cohens_d),
    }


def _permutation_test_difference(
    group_a: np.ndarray,
    group_b: np.ndarray,
    iterations: int,
    rng: np.random.Generator,
) -> Dict[str, float]:
    """Two-sided permutation test for a difference in means."""
    group_a = np.asarray(group_a, dtype=float)
    group_b = np.asarray(group_b, dtype=float)

    observed = float(np.mean(group_a) - np.mean(group_b))
    combined = np.concatenate([group_a, group_b])
    size_a = len(group_a)
    count = 0

    for _ in range(iterations):
        shuffled = rng.permutation(combined)
        perm_a = shuffled[:size_a]
        perm_b = shuffled[size_a:]
        difference = np.mean(perm_a) - np.mean(perm_b)
        if abs(difference) >= abs(observed):
            count += 1

    p_value = (count + 1) / (iterations + 1)
    return {
        "observed_difference": observed,
        "p_value": float(p_value),
        "iterations": float(iterations),
    }


def experiment_rq1_synchronization_groups(
    features: pd.DataFrame,
    alpha: float = 0.05,
    bootstrap_iterations: int = 2000,
    random_seed: int = 42,
) -> Dict[str, object]:
    """
    RQ1/H1: compare network statistics in low- and high-synchronization windows.

    The groups are defined using the median of mean absolute correlation.
    The comparison is descriptive and does not imply causal direction.
    """
    required = {"mean_abs_corr", "density", "average_clustering"}
    missing = required.difference(features.columns)
    if missing:
        raise ValueError(f"Missing feature columns: {sorted(missing)}")

    clean = features.dropna(subset=["mean_abs_corr"]).copy()
    median_value = float(clean["mean_abs_corr"].median())

    low = clean[clean["mean_abs_corr"] < median_value]
    high = clean[clean["mean_abs_corr"] >= median_value]

    rng = np.random.default_rng(random_seed)
    results = []

    for metric in ["density", "average_clustering", "strong_edge_fraction"]:
        if metric not in clean.columns:
            continue

        low_values = low[metric].dropna().to_numpy()
        high_values = high[metric].dropna().to_numpy()

        test = _welch_test(high_values, low_values)
        permutation = _permutation_test_difference(
            high_values,
            low_values,
            iterations=max(1000, bootstrap_iterations // 2),
            rng=rng,
        )
        difference, ci_low, ci_high = _bootstrap_mean_difference(
            high_values,
            low_values,
            iterations=bootstrap_iterations,
            rng=rng,
        )

        results.append(
            {
                "metric": metric,
                "low_n": len(low_values),
                "high_n": len(high_values),
                "low_mean": np.mean(low_values) if len(low_values) else np.nan,
                "high_mean": np.mean(high_values) if len(high_values) else np.nan,
                "difference_high_minus_low": difference,
                "bootstrap_ci_low": ci_low,
                "bootstrap_ci_high": ci_high,
                **test,
                "permutation_p_value": permutation["p_value"],
            }
        )

    return {
        "median_synchronization_threshold": median_value,
        "low_windows": low,
        "high_windows": high,
        "comparisons": pd.DataFrame(results),
        "alpha": alpha,
    }


def experiment_rq2_density_association(
    features: pd.DataFrame,
) -> Dict[str, object]:
    """
    RQ2/H2: quantify the association between mean absolute correlation
    and network density.

    Spearman correlation is included because it is less dependent on
    linearity and normality assumptions. OLS is included as a descriptive
    model when statsmodels is installed.
    """
    required = {"mean_abs_corr", "density"}
    missing = required.difference(features.columns)
    if missing:
        raise ValueError(f"Missing feature columns: {sorted(missing)}")

    clean = features[list(required)].dropna()
    if len(clean) < 3:
        raise ValueError("At least three observations are required.")

    spearman = stats.spearmanr(
        clean["mean_abs_corr"],
        clean["density"],
    )

    result: Dict[str, object] = {
        "n_observations": len(clean),
        "spearman_rho": float(spearman.statistic),
        "spearman_p_value": float(spearman.pvalue),
        "data": clean,
    }

    if sm is not None:
        x = sm.add_constant(clean["mean_abs_corr"])
        model = sm.OLS(clean["density"], x).fit(
            cov_type="HAC",
            cov_kwds={"maxlags": max(1, min(3, len(clean) // 4))},
        )
        result["ols_parameters"] = model.params
        result["ols_p_values"] = model.pvalues
        result["ols_r_squared"] = float(model.rsquared)
        result["ols_summary"] = model.summary()

    return result


def _sector_pair_statistics(
    graph: nx.Graph,
    sectors: Mapping[str, str],
) -> Dict[str, float]:
    within = []
    cross = []

    for ticker_i, ticker_j, data in graph.edges(data=True):
        if ticker_i not in sectors or ticker_j not in sectors:
            continue

        value = abs(float(data["weight"]))
        if sectors[ticker_i] == sectors[ticker_j]:
            within.append(value)
        else:
            cross.append(value)

    within_mean = float(np.mean(within)) if within else np.nan
    cross_mean = float(np.mean(cross)) if cross else np.nan

    return {
        "within_sector_mean_abs_corr": within_mean,
        "cross_sector_mean_abs_corr": cross_mean,
        "within_minus_cross": (
            within_mean - cross_mean
            if not np.isnan(within_mean) and not np.isnan(cross_mean)
            else np.nan
        ),
        "within_edge_count": float(len(within)),
        "cross_edge_count": float(len(cross)),
    }


def experiment_rq3_sector_structure(
    temporal_networks: pd.Series,
    sectors: Mapping[str, str],
    iterations: int = 2000,
    random_seed: int = 42,
) -> Dict[str, object]:
    """
    RQ3/H3: compare within-sector and cross-sector absolute correlations.

    The permutation test randomly shuffles sector labels among the nodes,
    preserving the graph weights while testing whether the observed
    sector partition produces an unusual within-minus-cross difference.
    """
    _validate_temporal_networks(temporal_networks)
    rng = np.random.default_rng(random_seed)

    rows = []
    for end_date, graph in temporal_networks.items():
        row = _sector_pair_statistics(graph, sectors)
        row["end_date"] = pd.Timestamp(end_date)
        rows.append(row)

    observed = pd.DataFrame(rows).set_index("end_date").sort_index()

    null_differences = []
    valid_graphs = []

    for _, graph in temporal_networks.items():
        available_nodes = [
            node for node in graph.nodes if node in sectors
        ]
        if len(available_nodes) < 2:
            continue

        labels = [sectors[node] for node in available_nodes]
        observed_row = _sector_pair_statistics(graph, sectors)
        observed_difference = observed_row["within_minus_cross"]

        if np.isnan(observed_difference):
            continue

        graph_differences = []
        for _ in range(iterations):
            shuffled_labels = rng.permutation(labels)
            shuffled_sectors = dict(zip(available_nodes, shuffled_labels))
            shuffled_row = _sector_pair_statistics(graph, shuffled_sectors)
            if not np.isnan(shuffled_row["within_minus_cross"]):
                graph_differences.append(shuffled_row["within_minus_cross"])

        if graph_differences:
            null_differences.append(
                {
                    "observed": observed_difference,
                    "null_values": np.asarray(graph_differences),
                }
            )
            valid_graphs.append(graph)

    tests = []
    for item in null_differences:
        null_values = item["null_values"]
        observed_value = item["observed"]
        p_value = (
            (np.sum(np.abs(null_values) >= abs(observed_value)) + 1)
            / (len(null_values) + 1)
        )
        tests.append(
            {
                "observed_within_minus_cross": observed_value,
                "null_mean": float(np.mean(null_values)),
                "null_std": float(np.std(null_values, ddof=1))
                if len(null_values) > 1
                else np.nan,
                "permutation_p_value": float(p_value),
                "null_iterations": len(null_values),
            }
        )

    return {
        "temporal_sector_statistics": observed,
        "per_window_permutation_tests": pd.DataFrame(tests),
        "n_valid_windows": len(valid_graphs),
    }


def experiment_rq4_null_model(
    temporal_networks: pd.Series,
    statistic: str = "mean_abs_corr",
    iterations: int = 500,
    strong_correlation_threshold: float = 0.70,
    random_seed: int = 42,
) -> Dict[str, object]:
    """
    RQ4/H4: compare observed graph statistics with an edge-weight
    permutation null model.

    CorrGraph.py stores correlations as edge weights but does not retain
    the return matrix in each graph. Therefore, this implementation
    permutes the observed edge weights within each graph. The topology
    is preserved, while the allocation of weights to edges is disrupted.

    This is a conditional null model and should not be interpreted as
    a full time-series null model.
    """
    _validate_temporal_networks(temporal_networks)
    rng = np.random.default_rng(random_seed)

    observed_values = []
    null_values = []

    for _, graph in temporal_networks.items():
        observed = _mean_graph_statistic(
            graph,
            statistic=statistic,
            threshold=strong_correlation_threshold,
        )
        if np.isnan(observed):
            continue

        edges = list(graph.edges(data=True))
        weights = np.asarray(
            [float(data["weight"]) for _, _, data in edges],
            dtype=float,
        )

        if len(weights) == 0:
            continue

        graph_null = []
        for _ in range(iterations):
            shuffled_weights = rng.permutation(weights)
            null_graph = graph.copy()

            for edge, shuffled_weight in zip(edges, shuffled_weights):
                u, v, _ = edge
                null_graph[u][v]["weight"] = float(shuffled_weight)

            null_statistic = _mean_graph_statistic(
                null_graph,
                statistic=statistic,
                threshold=strong_correlation_threshold,
            )
            if not np.isnan(null_statistic):
                graph_null.append(null_statistic)

        if graph_null:
            observed_values.append(observed)
            null_values.extend(graph_null)

    observed_values = np.asarray(observed_values, dtype=float)
    null_values = np.asarray(null_values, dtype=float)

    if len(observed_values) == 0 or len(null_values) == 0:
        raise ValueError("No valid observed or null statistics were produced.")

    observed_mean = float(np.mean(observed_values))
    null_mean = float(np.mean(null_values))
    null_std = (
        float(np.std(null_values, ddof=1))
        if len(null_values) > 1
        else np.nan
    )

    standardized_difference = (
        (observed_mean - null_mean) / null_std
        if null_std > 0
        else np.nan
    )

    return {
        "statistic": statistic,
        "observed_values": observed_values,
        "null_values": null_values,
        "observed_mean": observed_mean,
        "null_mean": null_mean,
        "null_std": null_std,
        "standardized_difference": float(standardized_difference),
        "iterations_per_window": iterations,
        "interpretation_note": (
            "Null model: edge weights are permuted within each graph. "
            "Graph topology is preserved, but temporal return structure "
            "is not modeled because CorrGraph.py does not retain returns."
        ),
    }

def run_all_experiments(
    tickers: Sequence[str] = DEFAULT_TICKERS,
    sectors: Mapping[str, str] = DEFAULT_SECTORS,
    config: Optional[ExperimentConfig] = None,
    cache_path: str = "./finance/Cache/",
) -> Dict[str, object]:
    """Run the complete experimental workflow and return all results."""
    config = config or ExperimentConfig()

    # CorrGraphs and Cache are implemented in CorrGraph.py.
    # The cache_path argument is retained for API compatibility, but
    # the current CorrGraph.py constructor only accepts tickers.
    if cache_path != "./finance/Cache/":
        warnings.warn(
            "cache_path is not configurable through the supplied "
            "CorrGraph.py constructor; using its default Cache settings."
        )

    corr_graphs = CorrGraphs(tickers)

    temporal_networks = corr_graphs.temporalGraph(
        historicPeriod=config.historic_period,
        slidingWindowPeriod=config.sliding_window_period,
        approxGraphs=config.approx_graphs,
    )

    features = extract_temporal_features(
        temporal_networks,
        strong_correlation_threshold=config.strong_correlation_threshold,
    )

    rq1 = experiment_rq1_synchronization_groups(
        features,
        alpha=config.alpha,
        bootstrap_iterations=config.bootstrap_iterations,
        random_seed=config.random_seed,
    )

    rq2 = experiment_rq2_density_association(features)

    rq3 = experiment_rq3_sector_structure(
        temporal_networks,
        sectors=sectors,
        iterations=config.bootstrap_iterations,
        random_seed=config.random_seed,
    )

    rq4 = experiment_rq4_null_model(
        temporal_networks,
        statistic="mean_abs_corr",
        iterations=config.null_iterations,
        strong_correlation_threshold=config.strong_correlation_threshold,
        random_seed=config.random_seed,
    )

    return {
        "config": config,
        "temporal_networks": temporal_networks,
        "features": features,
        "rq1_synchronization_groups": rq1,
        "rq2_density_association": rq2,
        "rq3_sector_structure": rq3,
        "rq4_null_model": rq4,
    }


def save_results(
    results: Mapping[str, object],
    output_directory: str = "./finance/resultsDatamining",
) -> Path:
    """Save tabular outputs and a compact text report."""
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)

    features = results["features"]
    if isinstance(features, pd.DataFrame):
        features.to_csv(output_path / "temporal_features.csv")

    rq1 = results["rq1_synchronization_groups"]
    if isinstance(rq1, dict):
        comparisons = rq1.get("comparisons")
        if isinstance(comparisons, pd.DataFrame):
            comparisons.to_csv(output_path / "rq1_comparisons.csv", index=False)

    rq2 = results["rq2_density_association"]
    if isinstance(rq2, dict):
        data = rq2.get("data")
        if isinstance(data, pd.DataFrame):
            data.to_csv(output_path / "rq2_data.csv", index=False)

    rq3 = results["rq3_sector_structure"]
    if isinstance(rq3, dict):
        temporal_sector_statistics = rq3.get("temporal_sector_statistics")
        if isinstance(temporal_sector_statistics, pd.DataFrame):
            temporal_sector_statistics.to_csv(
                output_path / "rq3_sector_statistics.csv"
            )

        tests = rq3.get("per_window_permutation_tests")
        if isinstance(tests, pd.DataFrame):
            tests.to_csv(
                output_path / "rq3_permutation_tests.csv",
                index=False,
            )

    rq4 = results["rq4_null_model"]
    if isinstance(rq4, dict):
        pd.DataFrame(
            {
                "observed_values": pd.Series(rq4["observed_values"]),
            }
        ).to_csv(output_path / "rq4_observed_values.csv", index=False)

        pd.DataFrame(
            {
                "null_values": pd.Series(rq4["null_values"]),
            }
        ).to_csv(output_path / "rq4_null_values.csv", index=False)

    report_lines = [
        "Data-mining experimentation report",
        "===================================",
        "",
        f"RQ1 median synchronization threshold: "
        f"{rq1.get('median_synchronization_threshold')}",
        "",
        "RQ1 comparisons:",
        str(rq1.get("comparisons")),
        "",
        "RQ2 density association:",
        f"Spearman rho = {rq2.get('spearman_rho')}",
        f"Spearman p-value = {rq2.get('spearman_p_value')}",
        f"OLS R-squared = {rq2.get('ols_r_squared', 'unavailable')}",
        "",
        "RQ3 sector analysis:",
        str(rq3.get("per_window_permutation_tests")),
        "",
        "RQ4 null model:",
        f"Observed mean = {rq4.get('observed_mean')}",
        f"Null mean = {rq4.get('null_mean')}",
        f"Null standard deviation = {rq4.get('null_std')}",
        f"Standardized difference = {rq4.get('standardized_difference')}",
        "",
        str(rq4.get("interpretation_note")),
    ]

    (output_path / "report.txt").write_text(
        "\n".join(report_lines),
        encoding="utf-8",
    )

    return output_path


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run stock correlation network data-mining experiments."
    )
    parser.add_argument("--period", default="5y")
    parser.add_argument("--window", default="6mo")
    parser.add_argument("--graphs", type=int, default=20)
    parser.add_argument("--cache", default="./finance/Cache/")
    parser.add_argument("--output", default="./finance/resultsDatamining")
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--null-iterations", type=int, default=500)
    parser.add_argument("--threshold", type=float, default=0.70)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main() -> None:
    parser = _build_argument_parser()
    args = parser.parse_args()

    config = ExperimentConfig(
        historic_period=args.period,
        sliding_window_period=args.window,
        approx_graphs=args.graphs,
        bootstrap_iterations=args.bootstrap,
        null_iterations=args.null_iterations,
        strong_correlation_threshold=args.threshold,
        random_seed=args.seed,
    )

    results = run_all_experiments(
        tickers=DEFAULT_TICKERS,
        sectors=DEFAULT_SECTORS,
        config=config,
        cache_path=args.cache,
    )

    output_path = save_results(results, args.output)

    print("Experiments completed.")
    print(f"Results saved to: {output_path.resolve()}")
    print("\nRQ1 comparisons:")
    print(results["rq1_synchronization_groups"]["comparisons"])

    print("\nRQ2 density association:")
    print(
        "Spearman rho:",
        results["rq2_density_association"]["spearman_rho"],
    )
    print(
        "Spearman p-value:",
        results["rq2_density_association"]["spearman_p_value"],
    )

    print("\nRQ3 sector tests:")
    print(results["rq3_sector_structure"]["per_window_permutation_tests"])

    print("\nRQ4 null model:")
    print(
        "Observed mean:",
        results["rq4_null_model"]["observed_mean"],
    )
    print(
        "Null mean:",
        results["rq4_null_model"]["null_mean"],
    )
    print(
        "Standardized difference:",
        results["rq4_null_model"]["standardized_difference"],
    )


if __name__ == "__main__":
    main()
