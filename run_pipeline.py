#!/usr/bin/env python3
"""
run_pipeline.py — runs the full PowerStep Grid pipeline in the correct order, step by step.

Order:
  1) fetch_data.py                  energy_system.db (SQLite) -> data_energy_raw.parquet, data_rssi_raw.parquet
  2) clean_data.py (fixed version)  -> features_rssi_clean.parquet, features_rssi_labeled.parquet, data_energy_clean.parquet
  3) train_occupancy_classifier.py  -> models/occupancy_classifier.joblib
  4) train_lstm_forecast.py         -> models/energy_forecast_lstm.keras, models/energy_scaler.joblib
  5) train_autoencoder_anomaly.py   -> models/tile_anomaly_autoencoder.keras, models/anomaly_scaler.joblib, models/anomaly_config.json

Usage:
    python run_pipeline.py                # run every step in order
    python run_pipeline.py --skip-fetch    # start from clean_data (raw parquet files already exist)
    python run_pipeline.py --only clean_data train_occupancy_classifier   # run specific steps only

Important notes:
  - energy_system.db must already contain real data before running this (i.e. ingest.py has
    been running for a while, either from real hardware or from simulate_sensors.py).
  - labels.csv must exist and be up to date (columns: start_ts, end_ts, label) before the
    clean_data step, otherwise only features_rssi_clean.parquet gets produced (not
    features_rssi_labeled.parquet), and the train_occupancy_classifier step will stop.
  - Each step runs as its own subprocess. If a step fails (non-zero exit code), the script
    stops immediately and does not move on to the next step, so you never train a model on
    incomplete or stale data.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
MODELS_DIR = REPO_ROOT / "models"

# each step: (display name, script filename, [files required to exist before running])
PIPELINE_STEPS = [
    ("fetch_data", "fetch_data.py", ["energy_system.db"]),
    ("clean_data", "clean_data.py", ["data_energy_raw.parquet", "data_rssi_raw.parquet"]),
    ("train_occupancy_classifier", "train_occupancy_classifier.py", ["features_rssi_labeled.parquet"]),
    ("train_lstm_forecast", "train_lstm_forecast.py", ["data_energy_clean.parquet"]),
    ("train_autoencoder_anomaly", "train_autoencoder_anomaly.py", ["data_energy_clean.parquet"]),
]

STEP_NAMES = [name for name, _, _ in PIPELINE_STEPS]


def log(msg: str) -> None:
    stamp = time.strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


def check_prereqs(step_name: str, required_files: list[str]) -> bool:
    missing = [f for f in required_files if not (REPO_ROOT / f).exists()]
    if missing:
        log(f"x '{step_name}' blocked — missing file(s): {', '.join(missing)}")
        if step_name == "train_occupancy_classifier" and "features_rssi_labeled.parquet" in missing:
            log("  Likely cause: labels.csv is missing, or its time range doesn't overlap the")
            log("  collected RSSI data, so the clean_data step couldn't merge labels. Check the")
            log("  warnings printed during the clean_data step above.")
        return False
    return True


def run_step(display_name: str, script_name: str, required_files: list[str]) -> bool:
    script_path = REPO_ROOT / script_name
    if not script_path.exists():
        log(f"x Script not found: {script_name}")
        return False

    if not check_prereqs(display_name, required_files):
        return False

    log(f"> Starting: {display_name} ({script_name})")
    result = subprocess.run([sys.executable, str(script_path)], cwd=REPO_ROOT)

    if result.returncode != 0:
        log(f"x Failed: {display_name} (exit code {result.returncode})")
        return False

    log(f"OK Done: {display_name}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the full PowerStep Grid pipeline in the correct order.")
    parser.add_argument(
        "--skip-fetch", action="store_true",
        help="Skip fetch_data.py (use this if data_energy_raw.parquet and data_rssi_raw.parquet already exist)",
    )
    parser.add_argument(
        "--only", nargs="+", choices=STEP_NAMES, default=None,
        help=f"Run only specific steps, in pipeline order. Choices: {', '.join(STEP_NAMES)}",
    )
    args = parser.parse_args()

    MODELS_DIR.mkdir(exist_ok=True)  # prevents joblib.dump / model.save from failing if the folder doesn't exist yet

    steps_to_run = PIPELINE_STEPS
    if args.only:
        wanted = set(args.only)
        steps_to_run = [s for s in PIPELINE_STEPS if s[0] in wanted]
    elif args.skip_fetch:
        steps_to_run = [s for s in PIPELINE_STEPS if s[0] != "fetch_data"]

    log(f"Running {len(steps_to_run)} step(s): {', '.join(s[0] for s in steps_to_run)}")
    log("-" * 60)

    start = time.time()
    for display_name, script_name, required_files in steps_to_run:
        ok = run_step(display_name, script_name, required_files)
        if not ok:
            log("-" * 60)
            log(f"Pipeline stopped at: {display_name}. Fix the issue above and run again.")
            return 1
        log("-" * 60)

    elapsed = time.time() - start
    log(f"OK Pipeline completed in {elapsed:.1f} seconds.")
    log("Trained models are in: models/")
    log("To run the live system: python realtime_inference.py   (and in another terminal: streamlit run dashboard.py)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
