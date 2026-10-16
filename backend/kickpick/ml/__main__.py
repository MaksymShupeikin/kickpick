"""Run with: python -m kickpick.ml {export,train,forecast} --help."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import os
from pathlib import Path
import time


def export(output, as_of):
    import pandas as pd
    from .features import build_features, FEATURE_VERSION, HORIZON_HOURS, LEAGUES, RESULT_DELAY_HOURS
    from .source import connect, read_source, SOURCE_SQL
    from .training import write_json

    if output.exists():
        raise ValueError("Export directory already exists; choose a new snapshot path")
    if as_of.tzinfo is None:
        raise ValueError("--as-of must include a timezone")
    query = SOURCE_SQL
    started = time.perf_counter()
    with connect() as connection:
        raw = read_source(connection, as_of)
    query_seconds = time.perf_counter() - started
    print(f"SQL snapshot: {len(raw)} matches in {query_seconds:.2f}s; DB connection closed", flush=True)
    features = build_features(raw)
    output.mkdir(parents=True)
    raw.to_parquet(output / "source.parquet", index=False)
    features.to_parquet(output / "features.parquet", index=False)
    manifest = {
        "as_of": as_of.isoformat(), "exported_at": datetime.now(timezone.utc).isoformat(),
        "feature_version": FEATURE_VERSION, "forecast_horizon_hours": HORIZON_HOURS,
        "result_delay_hours_approximation": RESULT_DELAY_HOURS, "leagues": list(LEAGUES),
        "source_matches": len(raw), "finished_matches": int((raw["status"] == "FT").sum()),
        "upcoming_matches": int((raw["status"] == "NS").sum()),
        "sql_seconds": query_seconds, "total_seconds": time.perf_counter() - started,
        "sql_sha256": hashlib.sha256(query.encode()).hexdigest(),
        "source_sha256": hashlib.sha256((output / "source.parquet").read_bytes()).hexdigest(),
        "features_sha256": hashlib.sha256((output / "features.parquet").read_bytes()).hexdigest(),
        "packages": {name: importlib.metadata.version(name) for name in
                     ("catboost", "pandas", "numpy", "scikit-learn", "scipy", "psycopg")},
        "warning": "Reconstructed backtest, not a historical observed_at snapshot; see README.",
    }
    write_json(output / "manifest.json", manifest)
    print(f"Features saved: {output}; total {manifest['total_seconds']:.1f}s", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Offline match predictions: export → train → forecast")
    commands = parser.add_subparsers(dest="command", required=True)
    now = datetime.now(timezone.utc)
    exp = commands.add_parser("export", help="Read-only SQL joins + causal rolling features")
    exp.add_argument("--output", required=True, type=Path)
    exp.add_argument("--as-of", type=datetime.fromisoformat, default=now)
    fit = commands.add_parser("train", help="Fit models, choose on validation, calibrate, evaluate test")
    fit.add_argument("--dataset", required=True, type=Path)
    fit.add_argument("--output", required=True, type=Path)
    fit.add_argument("--threads", type=int, default=2, choices=range(1, 5))
    refresh = commands.add_parser("refit", help="Refresh the frozen recipe on recent data; no test-score claim")
    refresh.add_argument("--dataset", required=True, type=Path)
    refresh.add_argument("--template", required=True, type=Path, help="report.json of the chosen experiment")
    refresh.add_argument("--output", required=True, type=Path)
    refresh.add_argument("--threads", type=int, default=2, choices=range(1, 5))
    predict = commands.add_parser("forecast", help="Export eligible next-24h forecasts; no API mutation")
    predict.add_argument("--dataset", required=True, type=Path)
    predict.add_argument("--model", required=True, type=Path)
    predict.add_argument("--output", required=True, type=Path)
    predict.add_argument("--as-of", type=datetime.fromisoformat, default=now)
    worker = commands.add_parser("worker", help="Publish future forecasts and settle results periodically")
    worker.add_argument("--model", required=True, type=Path)
    worker.add_argument("--interval", type=int, default=600, help="Seconds between cycles, minimum 60")
    worker.add_argument("--report", type=Path)
    worker.add_argument("--once", action="store_true")
    quality = commands.add_parser("quality", help="Report actual prospective accuracy, excluding voids")
    quality.add_argument("--output", required=True, type=Path)
    quality.add_argument("--days", type=int, default=180)
    args = parser.parse_args()
    threads = args.threads if args.command in ("train", "refit") else 2
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ[name] = str(threads)
    if args.command == "export":
        export(args.output, args.as_of)
    elif args.command == "train":
        from threadpoolctl import threadpool_limits
        from .training import train
        with threadpool_limits(limits=threads):
            train(args.dataset, args.output, threads)
    elif args.command == "refit":
        from threadpoolctl import threadpool_limits
        from .refit import refit
        with threadpool_limits(limits=threads):
            refit(args.dataset, args.template, args.output, threads=threads)
    elif args.command == "worker":
        if args.interval < 60:
            parser.error("--interval must be at least 60 seconds")
        from .worker import run_worker
        run_worker(args.model, interval=args.interval, report_path=args.report, once=args.once)
    elif args.command == "quality":
        if not 1 <= args.days <= 365:
            parser.error("--days must be between 1 and 365")
        from .source import connect
        from .evaluation import quality_report, save_report
        with connect() as connection:
            report = quality_report(connection, days=args.days)
        save_report(args.output, report)
        print(f"Prospective quality report: {args.output}; groups={len(report['groups'])}")
    elif args.command == "forecast":
        from .training import forecast
        forecast(args.dataset, args.model, args.output, args.as_of)


if __name__ == "__main__":
    main()
