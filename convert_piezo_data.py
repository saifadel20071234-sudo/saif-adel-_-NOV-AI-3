"""
convert_piezo_data.py — Fixes the malformed live_piezo_data.csv export and
reshapes it into the raw-energy schema expected by clean_data.py
(columns: ts, tile_id, power_mw).

WHY THIS IS NEEDED
-------------------
The source file has a logging bug: the whole "Raw: 108 | Voltage: 0.348 V"
string was written into a single "Raw_Value" cell instead of being split
into two numeric columns, and the real "Voltage" column is empty for every
row. This script parses that string with a regex to recover the two real
numbers.

IMPORTANT — POWER IS NOT COMPUTED HERE
----------------------------------------
The file only contains an ADC voltage reading taken directly on the ESP32
analog pin (see esp32_hardware_template.ino: analogRead(PIEZO_PIN)). That is
an open-circuit-style voltage sample, not a measurement of power delivered
into a real load. Turning it into power_mw requires knowing the actual
harvesting circuit (rectifier + load/storage impedance the piezo is driving).
Guessing a resistance value here would silently inject fabricated numbers
into model training, which is worse than leaving the column out.

So this script outputs cleaned raw_adc + voltage columns, ready for merging,
and leaves power_mw as an explicit next step once the real circuit constant
is known (see compute_power_mw() below for where to plug it in).

USAGE
-----
python convert_piezo_data.py --date 2026-09-01
(the source file only has HH:MM:SS, no date — pass the collection date
explicitly so timestamps sort correctly against other sessions/days)
"""

import argparse
import re
import sys
from datetime import datetime

import pandas as pd

RAW_VALUE_PATTERN = re.compile(r"Raw:\s*(\d+)\s*\|\s*Voltage:\s*([\d.]+)\s*V")


def parse_raw_value_column(raw_series: pd.Series) -> pd.DataFrame:
    """Extract raw_adc (int) and voltage (float) out of the mangled string column."""
    extracted = raw_series.str.extract(RAW_VALUE_PATTERN)
    extracted.columns = ["raw_adc", "voltage"]
    n_failed = extracted["raw_adc"].isna().sum()
    if n_failed:
        print(f"WARNING: {n_failed} row(s) did not match the expected 'Raw: X | Voltage: Y V' pattern and were dropped.")
    extracted["raw_adc"] = pd.to_numeric(extracted["raw_adc"], errors="coerce")
    extracted["voltage"] = pd.to_numeric(extracted["voltage"], errors="coerce")
    return extracted


def compute_power_mw(voltage: pd.Series, load_ohms: float | None) -> pd.Series | None:
    """
    Placeholder conversion — DO NOT trust these numbers for real training
    until load_ohms reflects the actual harvesting circuit.
    P(mW) = V^2 / R * 1000
    Returns None (no column added) if load_ohms is not provided.
    """
    if load_ohms is None:
        return None
    return (voltage ** 2 / load_ohms) * 1000.0


def main():
    parser = argparse.ArgumentParser(description="Convert live_piezo_data.csv to raw-energy schema")
    parser.add_argument("--input", default="live_piezo_data.csv")
    parser.add_argument("--output", default="data_energy_raw_piezo.parquet")
    parser.add_argument("--date", required=True, help="Collection date (YYYY-MM-DD) — the source file only has time-of-day")
    parser.add_argument("--tile-id", default="tile_1", help="Tile identifier to assign (single-tile hardware today)")
    parser.add_argument("--load-ohms", type=float, default=None,
                         help="Known load/sense resistance in ohms to estimate power_mw. "
                              "Omit to skip power_mw entirely (recommended until the real circuit value is confirmed).")
    args = parser.parse_args()

    try:
        collection_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    except ValueError:
        sys.exit(f"ERROR: --date must be YYYY-MM-DD, got '{args.date}'")

    df = pd.read_csv(args.input)
    if not {"Time", "Raw_Value"}.issubset(df.columns):
        sys.exit(f"ERROR: expected columns Time, Raw_Value — found {list(df.columns)}")

    parsed = parse_raw_value_column(df["Raw_Value"])
    df = pd.concat([df[["Time"]], parsed], axis=1).dropna(subset=["raw_adc", "voltage"])

    # Rebuild full timestamps from the supplied date + the HH:MM:SS column.
    # Rows sharing the same second keep their original file order (stable sort).
    df["ts"] = pd.to_datetime(collection_date.isoformat() + " " + df["Time"], errors="coerce")
    n_bad_ts = df["ts"].isna().sum()
    if n_bad_ts:
        print(f"WARNING: {n_bad_ts} row(s) had an unparseable Time value and were dropped.")
        df = df.dropna(subset=["ts"])

    df["tile_id"] = args.tile_id

    power_mw = compute_power_mw(df["voltage"], args.load_ohms)
    if power_mw is not None:
        df["power_mw"] = power_mw
        print(f"NOTE: power_mw estimated using load_ohms={args.load_ohms}. "
              f"Verify this against the real harvesting circuit before training on it.")
    else:
        print("power_mw NOT computed (no --load-ohms given). "
              "clean_energy() in clean_data.py requires a power_mw column — "
              "add one (via --load-ohms, or a better physics-based formula) before running the pipeline.")

    out_cols = ["ts", "tile_id", "raw_adc", "voltage"] + (["power_mw"] if power_mw is not None else [])
    result = df[out_cols].sort_values("ts").reset_index(drop=True)
    result.to_parquet(args.output, index=False)

    print(f"\nParsed {len(result)} valid rows out of {len(pd.read_csv(args.input))} source rows.")
    print(f"Time range: {result['ts'].min()} -> {result['ts'].max()}")
    print(f"Saved -> {args.output}")


if __name__ == "__main__":
    main()
