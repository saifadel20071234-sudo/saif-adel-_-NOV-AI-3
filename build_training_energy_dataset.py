"""
build_training_energy_dataset.py — Produces one merged, training-ready raw
energy dataset (source-tagged + normalized) from:
  1. Real ESP32 hardware readings (data_energy_raw_piezo.parquet)
  2. Simulated readings (energy_system.db -> readings_energy, from
     generate_training_data.py)

WHY NORMALIZE PER SOURCE
--------------------------
The real hardware (piezo across a confirmed 1MΩ load) produces power on the
order of 1e-4 to 1e-2 mW. The simulation's ENERGY_PER_STEP_J assumption
produces power on the order of 100s of mW — roughly a 40,000x gap. Merging
the raw values as-is would make any model (autoencoder, LSTM) treat "this
reading came from real hardware" as the dominant signal instead of the
actual generation/occupancy patterns we want it to learn.

Rather than inventing a physical calibration constant we have no basis for
(that would mean guessing unknown mechanical/circuit details), each source
is independently scaled to its own [0, 1] range (min-max) before merging.
This is a standard, defensible ML practice for combining heterogeneous
sensor sources — it preserves the *shape* of each source's temporal pattern
without letting absolute unit mismatch dominate.

The original untouched values are kept in `power_mw_raw` for reference/audit.
Training scripts should use `power_mw` (the normalized column) as the model
input going forward.

OUTPUT
------
data_energy_raw_merged.parquet — columns: ts, tile_id, source, power_mw_raw, power_mw
"""

import sqlite3
import pandas as pd

REAL_PATH = "data_energy_raw_piezo.parquet"
SIM_DB = "energy_system.db"
OUTPUT = "data_energy_raw_merged.parquet"


def load_real() -> pd.DataFrame:
    df = pd.read_parquet(REAL_PATH)
    if "power_mw" not in df.columns:
        raise SystemExit(
            "ERROR: data_energy_raw_piezo.parquet has no power_mw column. "
            "Re-run convert_piezo_data.py with --load-ohms first."
        )
    df = df[["ts", "tile_id", "power_mw"]].copy()
    df["source"] = "real"
    return df


def load_simulated() -> pd.DataFrame:
    conn = sqlite3.connect(SIM_DB)
    df = pd.read_sql("SELECT tile_id, power_mw, ts FROM readings_energy", conn)
    conn.close()
    df["ts"] = pd.to_datetime(df["ts"])
    df["source"] = "simulated"
    return df[["ts", "tile_id", "power_mw", "source"]]


def minmax_normalize_per_source(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={"power_mw": "power_mw_raw"})
    df["power_mw"] = 0.0
    for source, group in df.groupby("source"):
        lo, hi = group["power_mw_raw"].min(), group["power_mw_raw"].max()
        span = (hi - lo) or 1.0  # guard against a flat/constant source
        df.loc[group.index, "power_mw"] = (group["power_mw_raw"] - lo) / span
    return df


def main():
    real = load_real()
    sim = load_simulated()

    print(f"Real readings:      {len(real):,} rows  (tiles: {sorted(real['tile_id'].unique())})")
    print(f"Simulated readings: {len(sim):,} rows  (tiles: {sorted(sim['tile_id'].unique())})")

    combined = pd.concat([real, sim], ignore_index=True)
    combined = minmax_normalize_per_source(combined)
    combined = combined.sort_values("ts").reset_index(drop=True)

    combined.to_parquet(OUTPUT, index=False)

    print(f"\nMerged: {len(combined):,} rows -> {OUTPUT}")
    print("\nPer-source raw power_mw range (unaltered, kept for audit):")
    print(combined.groupby("source")["power_mw_raw"].agg(["min", "max", "mean"]))
    print("\nPer-source normalized power_mw range (0-1, used for training):")
    print(combined.groupby("source")["power_mw"].agg(["min", "max", "mean"]))


if __name__ == "__main__":
    main()
