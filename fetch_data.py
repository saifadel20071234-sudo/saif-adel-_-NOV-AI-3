import sqlite3, pandas as pd

DB_PATH = "energy_system.db"

def get_energy(start=None, end=None):
    conn = sqlite3.connect(DB_PATH)
    if start and end:
        q = "SELECT * FROM readings_energy WHERE ts BETWEEN ? AND ?"
        df = pd.read_sql(q, conn, params=(start, end), parse_dates=["ts"])
    else:
        df = pd.read_sql("SELECT * FROM readings_energy", conn, parse_dates=["ts"])
    conn.close()
    return df

def get_rssi(start=None, end=None):
    conn = sqlite3.connect(DB_PATH)
    if start and end:
        q = "SELECT * FROM readings_rssi WHERE ts BETWEEN ? AND ?"
        df = pd.read_sql(q, conn, params=(start, end), parse_dates=["ts"])
    else:
        df = pd.read_sql("SELECT * FROM readings_rssi", conn, parse_dates=["ts"])
    conn.close()
    return df

def export_training_parquet():
    get_energy().to_parquet("data_energy_raw.parquet")
    get_rssi().to_parquet("data_rssi_raw.parquet")
    print("تم تصدير ملفات parquet بنجاح")

if __name__ == "__main__":
    export_training_parquet()