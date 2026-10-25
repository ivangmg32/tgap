'''
Exports of a comparison record: the full JSON, and long-format CSV files
whose rows keep each method's own metrics in their own section.

    <id>.json              the complete record (written by pipeline)
    <id>_summary.csv       one row per measured value: section, field, value
    <id>_cody_events.csv   the counterfactual event set
    <id>_tgap_changes.csv  the re-addressed history events (TGAP lift)

Nothing here computes a result; it only lays out what the record holds.
'''

import csv
import json


def _flatten(prefix, value, out):
    if isinstance(value, dict):
        for key, item in value.items():
            _flatten(f"{prefix}.{key}" if prefix else str(key), item, out)
    elif isinstance(value, list):
        out[prefix] = json.dumps(value, default=str)
    else:
        out[prefix] = value
    return out


def summaryRows(record):
    rows = []

    def add(section, data):
        for field, value in _flatten("", data, {}).items():
            rows.append({"experiment_id": record["experiment_id"],
                         "section": section, "field": field, "value": value})

    target = {k: v for k, v in record["target"].items()
              if k != "examined_candidates"}
    add("shared.dataset", {k: v for k, v in record["dataset"].items()
                           if k != "preprocessing"})
    add("shared.model", {k: v for k, v in record["model"].items()
                         if k not in ("training",)})
    add("shared.target", target)
    add("shared.baseline_consistency", record["baseline_consistency"])
    add("shared.comparability", record["comparability"])
    add("shared.timings", record["timings"])
    if record.get("tgap"):
        tgap = dict(record["tgap"])
        directions = tgap.pop("directions", [])
        add("tgap", {k: v for k, v in tgap.items() if k != "plan"})
        add("tgap.plan", {k: v for k, v in tgap.get("plan", {}).items()
                          if k != "windows"})
        for direction in directions:
            add(f"tgap.{direction['direction'].lower()}",
                {k: v for k, v in direction.items()
                 if k != "event_changes_sample"})
    if record.get("cody"):
        add("cody", {k: v for k, v in record["cody"].items()
                     if k not in ("events", "candidate_event_ids")})
    return rows


def _write(path, rows, fields=None):
    fields = fields or (list(dict.fromkeys(k for r in rows for k in r))
                        if rows else ["empty"])
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fields})


def writeExports(record, stem):
    _write(stem + "_summary.csv", summaryRows(record),
           ["experiment_id", "section", "field", "value"])
    events = (record.get("cody") or {}).get("events", [])
    _write(stem + "_cody_events.csv",
           [{"experiment_id": record["experiment_id"], **e} for e in events],
           ["experiment_id", "event_id", "order_in_explanation", "source",
            "destination", "timestamp", "days_before_target",
            "involves_a_or_b", "absolute_importance"])
    changes = []
    for direction in (record.get("tgap") or {}).get("directions", []):
        for change in direction.get("event_changes_sample", []):
            changes.append({"experiment_id": record["experiment_id"],
                            "direction": direction["direction"],
                            "event_id": change["event_id"],
                            "window": change["window"],
                            "timestamp": change["timestamp"],
                            "original_source": change["original"][0],
                            "original_destination": change["original"][1],
                            "lifted_source": change["lifted"][0],
                            "lifted_destination": change["lifted"][1]})
    _write(stem + "_tgap_changes.csv", changes,
           ["experiment_id", "direction", "event_id", "window", "timestamp",
            "original_source", "original_destination", "lifted_source",
            "lifted_destination"])
