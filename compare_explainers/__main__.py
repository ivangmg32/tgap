'''
    python -m compare_explainers run [--retrain] [--allow-noncomparable]
                                     [--max-steps N] [--time-limit S]
    python -m compare_explainers status
    python -m compare_explainers export [--out DIR]
'''

import argparse
import json
import os
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m compare_explainers")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the TGAP vs CoDy pilot")
    run.add_argument("--retrain", action="store_true",
                     help="train a new checkpoint even if one exists")
    run.add_argument("--allow-noncomparable", action="store_true",
                     help="run the explainers even if the baseline check "
                          "fails (record is labelled non-comparable)")
    run.add_argument("--max-steps", type=int, default=None)
    run.add_argument("--time-limit", type=int, default=None)
    run.add_argument("--policy", default=None,
                     choices=["random", "temporal", "spatio-temporal",
                              "local-gradient"])
    batch = sub.add_parser("batch", help="technical set: run both explainers on N targets")
    batch.add_argument("--count", type=int, default=30)
    batch.add_argument("--workers", type=int, default=6)
    sub.add_parser("casebank", help="select the human-study case bank from the latest batch")
    sub.add_parser("status", help="summarise the latest record")
    export = sub.add_parser("export", help="write JSON/CSV of the latest record")
    export.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    if args.command == "run":
        from .config import pilotConfig
        from .pipeline import run as runPipeline
        cody = {}
        if args.max_steps is not None:
            cody["max_steps"] = args.max_steps
        if args.time_limit is not None:
            cody["time_limit_seconds"] = args.time_limit
        if args.policy is not None:
            cody["selection_policy"] = args.policy
        config = pilotConfig(**({"cody": cody} if cody else {}))
        record = runPipeline(config, retrain=args.retrain,
                             allowNonComparable=args.allow_noncomparable)
        return 0 if record["comparability"]["comparable"] else 2

    if args.command == "batch":
        from .batch import runBatch
        runBatch(args.count, args.workers)
        return 0
    if args.command == "casebank":
        from .batch import buildCaseBank
        buildCaseBank()
        return 0
    from .pipeline import loadLatest
    try:
        record = loadLatest()
    except FileNotFoundError:
        print("No comparison has been run yet: "
              "python -m compare_explainers run")
        return 1
    if args.command == "status":
        c = record["comparability"]
        print(json.dumps({"experiment_id": record["experiment_id"],
                          "created_utc": record["created_utc"], **c},
                         indent=2))
        return 0
    from .export import writeExports
    out = args.out or os.getcwd()
    os.makedirs(out, exist_ok=True)
    stem = os.path.join(out, record["experiment_id"])
    with open(stem + ".json", "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
    writeExports(record, stem)
    print(f"Wrote {stem}.json and CSV files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
