"""
convert_wifi_labels.py — Converts wifi_dataset.csv (timestamp + people_count)
into the labels.csv format merge_labels.py expects (start_ts, end_ts, label).

WHY THIS IS NEEDED
-------------------
merge_labels() joins ground-truth labels onto RSSI feature windows using
time ranges, not per-row labels. So instead of one label per timestamp, we
need contiguous blocks: "from this time to that time, the label was X".

IMPORTANT — THIS FILE ALONE DOES NOT TRAIN THE OCCUPANCY CLASSIFIER
----------------------------------------------------------------------
occupancy_classifier needs RAW RSSI SIGNAL READINGS (the wifi dBm value
itself) as the model's input features (mean/std/min/max/range of RSSI in
a time window). wifi_dataset.csv only has the *ground truth* people_count
— it is the answer key, not the RSSI signal it should be paired with.

This script prepares the label side of the pipeline (labels.csv). To
actually train, you still need a raw RSSI log (ts, node_id, rssi) covering
this same 2026-08-31 23:22 -> 2026-09-01 01:44 window from the ESP32.
Without that, merge_labels() has nothing to join these labels onto.

USAGE
-----
python convert_wifi_labels.py
"""

import pandas as pd

INPUT = "wifi_dataset.csv"
OUTPUT = "labels_from_wifi.csv"


def people_count_to_label(count: int) -> str:
    """Binary label matching the model's actual decision rule:
    simulator.py checks `state != "empty"`, so anything else than
    'empty' is treated as occupied."""
    return "empty" if count == 0 else "occupied"


def main():
    df = pd.read_csv(INPUT, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["label"] = df["people_count"].apply(people_count_to_label)

    # Collapse consecutive rows with the same label into (start_ts, end_ts) blocks.
    df["block"] = (df["label"] != df["label"].shift()).cumsum()
    blocks = df.groupby("block").agg(
        start_ts=("timestamp", "first"),
        end_ts=("timestamp", "last"),
        label=("label", "first"),
        n_readings=("label", "count"),
    ).reset_index(drop=True)

    # end_ts should be exclusive per merge_labels()'s mask (ts < end_ts), so
    # nudge each block's end to just after its last real reading.
    blocks["end_ts"] = blocks["end_ts"] + pd.Timedelta(seconds=1)

    blocks[["start_ts", "end_ts", "label"]].to_csv(OUTPUT, index=False)

    print(f"Source rows: {len(df)}")
    print(f"Collapsed into {len(blocks)} labeled time blocks -> {OUTPUT}")
    print(blocks["label"].value_counts().to_string())
    print("\nREMINDER: merge_labels.py still needs a matching raw RSSI parquet "
          "(ts, node_id, rssi) for this same time window to actually produce "
          "trainable features. This labels file alone is not sufficient.")


if __name__ == "__main__":
    main()
