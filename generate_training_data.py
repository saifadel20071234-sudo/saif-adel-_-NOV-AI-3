"""
generate_training_data.py — يولّد بيانات محاكاة مباشرةً في energy_system.db
بدون الحاجة لـ MQTT broker.

يولّد:
  - readings_energy: 3 بلاطات × ~2000 قراءة
  - readings_rssi:   corridor_node_1 × ~2000 قراءة

بعد التشغيل، شغّل:
    venv\Scripts\python.exe run_pipeline.py
"""

import sqlite3, random, math, json
from datetime import datetime, timedelta

DB_PATH = "energy_system.db"
TILE_IDS = ["tile_1", "tile_2", "tile_3"]
NODE_IDS = ["corridor_node_1"]

# ─── إنشاء الجداول ───────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS readings_energy(
    id INTEGER PRIMARY KEY AUTOINCREMENT, tile_id TEXT, power_mw REAL,
    energy_wh_delta REAL, ts TEXT)""")
c.execute("""CREATE TABLE IF NOT EXISTS readings_rssi(
    id INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT, rssi REAL, ts TEXT)""")
c.execute("""CREATE TABLE IF NOT EXISTS alerts(
    id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, message TEXT,
    severity TEXT, ts TEXT, resolved INTEGER DEFAULT 0)""")
c.execute("""CREATE TABLE IF NOT EXISTS ai_results(
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, payload TEXT, ts TEXT)""")
conn.commit()

# ─── دوال المحاكاة ────────────────────────────────────────────────────────────
def busy_factor(hour: float) -> float:
    """ذروة عند مواعيد المحاضرات: 8, 10, 12, 16"""
    peaks = [8, 10, 12, 16]
    factor = 0.05
    for p in peaks:
        factor += math.exp(-((hour - p) ** 2) / 0.5)
    return min(factor, 1.0)

def simulate_energy(tile_id: str, intensity: float, ts: str) -> dict:
    steps = max(0, int(random.gauss(intensity * 5, 1)))
    energy_wh = steps * random.uniform(0.0004, 0.0009)
    power_mw = (energy_wh * 3600 * 1000) / 5
    # أحياناً شذوذ عشوائي (5% من الوقت)
    if random.random() < 0.05:
        power_mw *= random.uniform(3, 6)
    return {
        "tile_id": tile_id,
        "power_mw": round(power_mw, 2),
        "energy_wh_delta": round(energy_wh, 5),
        "ts": ts
    }

def simulate_rssi(node_id: str, intensity: float, ts: str) -> dict:
    baseline = -55
    noise = random.gauss(0, 1.5 + intensity * 3)
    return {
        "node_id": node_id,
        "rssi": round(baseline + noise, 1),
        "ts": ts
    }

# ─── توليد البيانات ───────────────────────────────────────────────────────────
DAYS = 3          # عدد أيام المحاكاة
INTERVAL_SEC = 5  # فترة القراءة بالثواني

print(f"جاري توليد بيانات {DAYS} أيام بفترة {INTERVAL_SEC} ثواني...")

# التعديل: تثبيت تاريخ البداية عشان يتطابق مع التواريخ الثابتة في ملف labels.csv 
# (عشان الداتا تتدمج صح وميطلعش Error في التدريب)
start_time = datetime.fromisoformat("2026-08-23T17:35:36")
end_time = start_time + timedelta(days=DAYS)
current = start_time
energy_rows = []
rssi_rows   = []

while current <= end_time:
    hour      = current.hour + current.minute / 60
    intensity = busy_factor(hour)
    ts_str    = current.isoformat()

    for tile in TILE_IDS:
        r = simulate_energy(tile, intensity, ts_str)
        energy_rows.append((r["tile_id"], r["power_mw"], r["energy_wh_delta"], r["ts"]))

    for node in NODE_IDS:
        r = simulate_rssi(node, intensity, ts_str)
        rssi_rows.append((r["node_id"], r["rssi"], r["ts"]))

    current += timedelta(seconds=INTERVAL_SEC)

# حفظ بشكل دفعي (أسرع بكثير من INSERT واحدة واحدة)
c.executemany(
    "INSERT INTO readings_energy(tile_id, power_mw, energy_wh_delta, ts) VALUES (?,?,?,?)",
    energy_rows
)
c.executemany(
    "INSERT INTO readings_rssi(node_id, rssi, ts) VALUES (?,?,?)",
    rssi_rows
)
conn.commit()
conn.close()

print(f"تم! energy: {len(energy_rows):,} صف | rssi: {len(rssi_rows):,} صف")
print("الخطوة الجاية: python run_pipeline.py")
