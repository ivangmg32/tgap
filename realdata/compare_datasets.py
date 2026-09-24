'''
Cross-dataset comparison of the real-data TGAP runs.

    python -m realdata.compare_datasets                      # default mode
    python -m realdata.compare_datasets --mode descriptive
    python -m realdata.compare_datasets --mode both

Reads what run_real_data.py already wrote under
output/real_data_v2/<analysis_mode>/ and produces one comparison table plus
three figures per mode. It computes nothing new about TGAP - it only lines
up results that already exist so patterns across datasets become visible.

Three things this is good for:

 1. Comparing the two GRAPH FAMILIES. tgbl-wiki and Decentraland are
    bipartite and needed a one-mode projection; the other six are
    unipartite observed edges. The projection family discards far more data
    and invents its edges, so it is worth checking whether the two families
    behave differently.

 2. Checking whether a finding is dataset-specific or systematic. A result
    seen on one dataset is an anecdote; the same result on eight
    independently sourced datasets is a pattern.

 3. Comparing the two ANALYSIS MODES. The leakage-safe temporal evaluation
    chooses its actors from the first 20% of the span only, so a dataset
    with high actor turnover ends up with much sparser graphs than the
    descriptive full-period view. That difference is itself a result, and
    the mode is printed in every table so the two are never mixed.

VALIDITY. Only rows flagged valid_for_analysis in tgap_results.csv are used
for impact and no-op statistics: a perturbation that broke its own
edge-count invariant, or a trend perturbation that saturated, is not an
explanation result. The counts of what was excluded are reported alongside.

No claim here is causal, and none of it validates TGAP: real data has no
ground truth.
'''

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .adapters.base import ANALYSIS_MODES, TEMPORAL_EVALUATION

OUTPUT_ROOT = os.path.join("output", "real_data_v2")

# Which family each dataset belongs to, and therefore whether its edges
# were observed or derived by projection.
FAMILY = {
    "tgbl_wiki": "bipartite (projected)",
    "decentraland": "bipartite (projected)",
    "email_eu_core": "unipartite (observed)",
    "tgbl_enron": "unipartite (observed)",
    "tgbl_uci": "unipartite (observed)",
    "sx_mathoverflow": "unipartite (observed)",
    "bitcoin_otc": "unipartite (observed)",
    "bitcoin_alpha": "unipartite (observed)",
}

DOMAIN = {
    "tgbl_wiki": "wiki editing",
    "decentraland": "DAO governance",
    "email_eu_core": "email (institution)",
    "tgbl_enron": "email (corporate)",
    "tgbl_uci": "student messaging",
    "sx_mathoverflow": "Q&A interaction",
    "bitcoin_otc": "crypto trust",
    "bitcoin_alpha": "crypto trust",
}

plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3,
                     "savefig.dpi": 200, "savefig.bbox": "tight"})


def loadAll(root):
    ''' Collect every dataset directory under `root` that has a completed
    run. A directory missing any required file is skipped rather than
    partially reported. '''
    datasets = {}
    if not os.path.isdir(root):
        return datasets
    for name in sorted(os.listdir(root)):
        directory = os.path.join(root, name)
        if not os.path.isdir(directory):
            continue
        required = ["metadata.json", "preprocessing_summary.json",
                    "graph_summary.csv", "tgap_results.csv", "summary.json",
                    "bridge_trend_status.csv",
                    "transformation_feasibility.csv"]
        if not all(os.path.exists(os.path.join(directory, f))
                   for f in required):
            continue

        def read(filename):
            with open(os.path.join(directory, filename), encoding="utf-8") \
                    as handle:
                return json.load(handle)

        datasets[name] = {
            "meta": read("metadata.json"),
            "pre": read("preprocessing_summary.json"),
            "summary": read("summary.json"),
            "graph": pd.read_csv(os.path.join(directory,
                                              "graph_summary.csv")),
            "results": pd.read_csv(os.path.join(directory,
                                                "tgap_results.csv")),
            "trend": pd.read_csv(os.path.join(directory,
                                              "bridge_trend_status.csv")),
            "feasibility": pd.read_csv(os.path.join(
                directory, "transformation_feasibility.csv")),
        }
    return datasets


def buildTable(datasets):
    ''' One row per dataset. Node and event counts always appear as a RAW
    and a RETAINED number, never as a bare "nodes" column. '''
    rows = []
    for name, data in datasets.items():
        graph, summary, pre = data["graph"], data["summary"], data["pre"]
        results = data["results"]
        valid = results[results["valid_for_analysis"]]
        trend = data["trend"]
        noopValid = valid["noop"].fillna(False) if len(valid) else valid["noop"]
        invariance = summary[
            "expected_invariance_history_only_transformations"]
        rows.append({
            "dataset": name,
            "analysis_mode": summary["analysis_mode"],
            "domain": DOMAIN.get(name, "?"),
            "family": FAMILY.get(name, "?"),
            "raw_nodes": pre["raw_nodes"],
            "retained_nodes": pre["retained_nodes"],
            "nodes_retained_pct": pre["nodes_retained_pct"],
            "raw_events": pre["raw_events"],
            "retained_events": pre["retained_events"],
            "events_retained_pct": pre["events_retained_pct"],
            "raw_span_days": round(data["meta"]["raw_span_days"], 1),
            "evaluated_span_days": round(
                data["meta"]["evaluated_span_days"], 1),
            "snapshots": summary["snapshot_count"],
            "partition": "/".join(str(x) for x in pre["partition_sizes"]),
            "community_mode": pre["community_mode"],
            "node_selection_mode": pre["node_selection_mode"],
            "leakage_safe_selection": not pre[
                "future_information_used_for_node_selection"],
            "edges_median": int(graph["edges"].median()),
            "density_median": round(float(graph["density"].median()), 4),
            "bridge_width_min": int(graph["bridge_width"].min()),
            "bridge_width_max": int(graph["bridge_width"].max()),
            "snapshots_zero_bridge": int((graph["bridge_width"] == 0).sum()),
            "connected_snapshots": int(graph["is_connected"].sum()),
            "explanation_rows": int(len(results)),
            "valid_rows": int(len(valid)),
            "invalid_rows": int(len(results) - len(valid)),
            "invalid_pct": round(
                100.0 * (len(results) - len(valid)) / len(results), 1)
                if len(results) else 0.0,
            "edge_count_infeasible_settings":
                summary["edge_count_infeasible_settings"],
            "edge_count_settings_checked":
                summary["edge_count_settings_checked"],
            "noop_rows_valid": int(noopValid.sum()) if len(valid) else 0,
            "noop_pct_valid": round(100.0 * float(noopValid.mean()), 1)
                              if len(valid) else None,
            # Item 6 wording: this is a verified expectation, not a finding.
            "expected_invariance_verified": invariance["verified"],
            "trend_ok": int((trend["status"] == "ok").sum()),
            "trend_settings": int(len(trend)),
            "trend_saturated": int((trend["status"] == "saturated").sum()),
            "trend_wrong_direction": int(
                (trend["status"] == "wrong_direction").sum()),
            "trend_max_saturated_pct": round(
                100 * float(trend["fraction_saturated"].max()), 1),
        })
    return pd.DataFrame(rows).sort_values(["family", "dataset"])


def figureSaturationVersusStatus(datasets, path):
    ''' How often BridgeTrend produced a usable result, against how much of
    the trajectory hit the width-1 floor. Each point is one dataset. '''
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    for name, data in datasets.items():
        trend = data["trend"]
        clamped = 100 * trend["fraction_saturated"].mean()
        usable = 100 * (trend["status"] == "ok").mean()
        marker = "o" if FAMILY.get(name, "").startswith("bipartite") else "s"
        ax.scatter(clamped, usable, s=60, marker=marker)
        ax.annotate(name, (clamped, usable), fontsize=7,
                    textcoords="offset points", xytext=(5, 4))
    ax.set_xlabel("mean % of snapshots clamped to bridge width 1")
    ax.set_ylabel("% of BridgeTrend settings with status 'ok'")
    ax.set_title("BridgeTrend usability vs clamp saturation\n"
                 "(circles = bipartite/projected, squares = unipartite)")
    ax.set_ylim(-5, 105)
    fig.savefig(path)
    plt.close(fig)


def figureNoopVersusBridgeWidth(table, path):
    ''' The discreteness floor, on real data: a property of size p can only
    move when |delta| >= 0.5/p, so datasets whose bridge is thin should
    produce more no-op rows. Computed on valid rows only. '''
    subset = table[table["noop_pct_valid"].notna()]
    if subset.empty:
        return
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.scatter(subset["bridge_width_min"].clip(lower=0.5),
               subset["noop_pct_valid"], s=60)
    for _, row in subset.iterrows():
        ax.annotate(row["dataset"],
                    (max(row["bridge_width_min"], 0.5),
                     row["noop_pct_valid"]),
                    fontsize=7, textcoords="offset points", xytext=(5, 4))
    ax.set_xscale("log")
    ax.set_xlabel("smallest bridge width across snapshots "
                  "(log scale; 0 plotted at 0.5)")
    ax.set_ylabel("% of VALID explanation rows reported as no-op")
    ax.set_title("No-op rate against the thinnest bridge in the series")
    fig.savefig(path)
    plt.close(fig)


def figureImpactHeatmap(datasets, path):
    ''' Which concepts each dataset's bridge-width model responds to.
    Impacts are scaled per dataset (divided by the largest absolute value in
    that row) because their raw magnitudes differ by orders of magnitude.
    The scaling makes the PATTERN comparable, not the magnitudes. Cells with
    no valid row are left blank rather than drawn as zero. '''
    concepts = ["Bridge Width", "Centralization", "Density",
                "Bridge Trend", "Churn"]
    names, matrix = [], []
    for name, data in datasets.items():
        results = data["results"]
        subset = results[results["valid_for_analysis"]
                         & (results["model"] == "trend_bridge_width")
                         & (results["direction"] == "increase")
                         & (results["requested_delta"] == 0.1)]
        if subset.empty:
            continue
        byConcept = subset.set_index("transformation")["impact"]
        row = [byConcept.get(concept, np.nan) for concept in concepts]
        finite = [abs(v) for v in row if v == v]
        scale = max(finite) if finite else 1.0
        matrix.append([v / scale if v == v else np.nan for v in row])
        names.append(name)
    if not matrix:
        return
    data = np.array(matrix, dtype=float)
    fig, ax = plt.subplots(figsize=(7.4, 0.5 * len(names) + 2.4))
    image = ax.imshow(np.ma.masked_invalid(data), cmap="RdBu_r",
                      vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(concepts)))
    ax.set_xticklabels(concepts, rotation=20, ha="right")
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            value = data[i, j]
            ax.text(j, i, "n/a" if value != value else f"{value:+.2f}",
                    ha="center", va="center", fontsize=7)
    ax.set_title("Concept response pattern per dataset (valid rows only)\n"
                 "model: trend of bridge width; scaled per dataset "
                 "(cells are relative, not absolute)")
    ax.grid(False)
    fig.colorbar(image, ax=ax, label="impact / largest |impact| in row")
    fig.savefig(path)
    plt.close(fig)


def observations(table, datasets):
    ''' Cross-dataset observations, computed rather than asserted. Every
    number here comes from the loaded result files. '''
    thin = table[table["bridge_width_min"] <= 5]
    thick = table[table["bridge_width_min"] > 5]
    trendFailing = table[table["trend_ok"] < table["trend_settings"]]
    trendClean = table[table["trend_ok"] == table["trend_settings"]]

    # The BridgeTrend comparison is made at SETTING level, and the question
    # is deliberately NOT "do failed settings clamp more" - status "ok" is
    # DEFINED as zero clamping, so that comparison would be circular. The
    # non-circular question is: among the settings that DID clamp, how much
    # clamping does it take before the achieved direction flips? Both groups
    # below therefore have clamping; only the outcome differs.
    allTrend = pd.concat([d["trend"] for d in datasets.values()])
    clamped = allTrend[allTrend["snapshots_saturated"] > 0]
    held = clamped[clamped["status"] == "saturated"]
    flipped = clamped[clamped["status"] == "wrong_direction"]
    allResults = pd.concat([d["results"] for d in datasets.values()])
    trendRows = allResults[allResults["transformation"] == "Bridge Trend"]
    return {
        "bridge_trend_status_totals":
            allTrend["status"].value_counts().to_dict(),
        "bridge_trend_settings": int(len(allTrend)),
        "bridge_trend_settings_with_clamping": int(len(clamped)),
        "bridge_trend_rows_total": int(len(trendRows)),
        "bridge_trend_rows_valid": int(trendRows["valid_for_analysis"].sum()),
        "among_clamped_settings_direction_held": int(len(held)),
        "among_clamped_settings_direction_flipped": int(len(flipped)),
        "mean_clamped_pct_where_direction_held": (
            round(100 * float(held["fraction_saturated"].mean()), 1)
            if not held.empty else None),
        "mean_clamped_pct_where_direction_flipped": (
            round(100 * float(flipped["fraction_saturated"].mean()), 1)
            if not flipped.empty else None),
        "strict_mode_disagreements_total": int(
            table["edge_count_settings_checked"].sum()
            - sum(int(d["feasibility"]["strict_agrees_with_measurement"].sum())
                  for d in datasets.values())),
        "analysis_mode": table["analysis_mode"].iloc[0],
        "datasets": int(len(table)),
        "total_explanation_rows": int(table["explanation_rows"].sum()),
        "total_valid_rows": int(table["valid_rows"].sum()),
        "total_invalid_rows": int(table["invalid_rows"].sum()),
        "datasets_where_expected_invariance_verified": int(
            table["expected_invariance_verified"].sum()),
        "expected_invariance_note":
            "Verification of an expected invariant, not an empirical "
            "discovery: history-only transformations anchor the last "
            "snapshot and the persistence models read only the last "
            "snapshot, so zero follows from the definitions.",
        "noop_pct_thin_bridge_datasets": (
            round(float(thin["noop_pct_valid"].mean()), 2)
            if not thin.empty else None),
        "noop_pct_thicker_bridge_datasets": (
            round(float(thick["noop_pct_valid"].mean()), 2)
            if not thick.empty else None),
        "datasets_with_any_invalid_bridge_trend": list(
            trendFailing["dataset"]),
        "datasets_with_all_bridge_trend_settings_ok": list(
            trendClean["dataset"]),
        "datasets_with_wrong_direction_bridge_trend": list(
            table[table["trend_wrong_direction"] > 0]["dataset"]),
        "datasets_with_edge_count_infeasible_settings": list(
            table[table["edge_count_infeasible_settings"] > 0]["dataset"]),
        "edge_count_infeasible_settings_total": int(
            table["edge_count_infeasible_settings"].sum()),
        "edge_count_settings_checked_total": int(
            table["edge_count_settings_checked"].sum()),
        "median_nodes_retained_pct": round(
            float(table["nodes_retained_pct"].median()), 2),
        "median_events_retained_pct": round(
            float(table["events_retained_pct"].median()), 2),
    }


def runMode(mode):
    root = os.path.join(OUTPUT_ROOT, mode)
    datasets = loadAll(root)
    if not datasets:
        print(f"no completed runs found under {root}; run "
              f"`python -m realdata.run_real_data --mode {mode}`")
        return None
    table = buildTable(datasets)
    table.to_csv(os.path.join(root, "comparison.csv"), index=False)

    columns = ["dataset", "domain", "family", "snapshots",
               "raw_nodes", "retained_nodes", "nodes_retained_pct",
               "raw_events", "retained_events", "events_retained_pct",
               "partition", "community_mode", "density_median",
               "bridge_width_min", "bridge_width_max",
               "valid_rows", "invalid_rows", "noop_pct_valid",
               "expected_invariance_verified", "trend_ok", "trend_settings",
               "trend_max_saturated_pct"]
    print("=" * 130)
    print(f"CROSS-DATASET COMPARISON   [analysis_mode = {mode}]")
    print("=" * 130)
    print(table[columns].to_string(index=False))

    figures = os.path.join(root, "figures")
    os.makedirs(figures, exist_ok=True)
    figureSaturationVersusStatus(
        datasets, os.path.join(figures, "saturation_vs_trend_status.png"))
    figureNoopVersusBridgeWidth(
        table, os.path.join(figures, "noop_vs_bridge_width.png"))
    figureImpactHeatmap(datasets,
                        os.path.join(figures, "concept_response_heatmap.png"))

    facts = observations(table, datasets)
    with open(os.path.join(root, "comparison_observations.json"),
              "w", encoding="utf-8") as handle:
        json.dump(facts, handle, indent=2)

    print(f"\nCROSS-DATASET OBSERVATIONS   [analysis_mode = {mode}]")
    print(f"  datasets compared: {facts['datasets']}; explanation rows "
          f"{facts['total_explanation_rows']} "
          f"({facts['total_valid_rows']} valid, "
          f"{facts['total_invalid_rows']} excluded)")
    print(f"  median retention: {facts['median_nodes_retained_pct']}% of "
          f"nodes, {facts['median_events_retained_pct']}% of events")
    print(f"  expected invariance verified on "
          f"{facts['datasets_where_expected_invariance_verified']}"
          f"/{facts['datasets']} datasets "
          f"(expected by construction - see note in the JSON)")
    print(f"  mean no-op rate on valid rows, thin-bridge datasets "
          f"(min width <= 5): {facts['noop_pct_thin_bridge_datasets']}%")
    print(f"  mean no-op rate on valid rows, thicker-bridge datasets: "
          f"{facts['noop_pct_thicker_bridge_datasets']}%")
    print(f"  edge-count infeasible settings: "
          f"{facts['edge_count_infeasible_settings_total']}"
          f"/{facts['edge_count_settings_checked_total']} in "
          f"{facts['datasets_with_edge_count_infeasible_settings']}")
    print(f"  BridgeTrend settings: {facts['bridge_trend_status_totals']} "
          f"of {facts['bridge_trend_settings']}; usable rows "
          f"{facts['bridge_trend_rows_valid']}"
          f"/{facts['bridge_trend_rows_total']}")
    print(f"     settings where the width-1 floor was hit at all: "
          f"{facts['bridge_trend_settings_with_clamping']}"
          f"/{facts['bridge_trend_settings']}")
    print(f"       of those, direction HELD    : "
          f"{facts['among_clamped_settings_direction_held']} "
          f"(mean {facts['mean_clamped_pct_where_direction_held']}% of the "
          f"trajectory clamped)")
    print(f"       of those, direction FLIPPED : "
          f"{facts['among_clamped_settings_direction_flipped']} "
          f"(mean {facts['mean_clamped_pct_where_direction_flipped']}% of the "
          f"trajectory clamped)")
    print(f"     datasets with a WRONG-DIRECTION setting: "
          f"{facts['datasets_with_wrong_direction_bridge_trend']}")
    print(f"     datasets with all settings OK: "
          f"{facts['datasets_with_all_bridge_trend_settings_ok']}")
    print(f"  strict-mode vs measurement disagreements: "
          f"{facts['strict_mode_disagreements_total']}"
          f"/{facts['edge_count_settings_checked_total']}")
    print(f"\nwrote comparison.csv, comparison_observations.json and "
          f"3 figures to {root}")
    return table


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    modes = [TEMPORAL_EVALUATION]
    if "--mode" in argv:
        index = argv.index("--mode")
        requested = argv[index + 1]
        del argv[index:index + 2]
        modes = list(ANALYSIS_MODES) if requested == "both" else [requested]
    tables = {}
    for mode in modes:
        tables[mode] = runMode(mode)
        print()
    return tables


if __name__ == "__main__":
    main()
