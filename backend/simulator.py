"""
PowerStep Grid — Simulation Engine
===================================
يحاكي هذا الملف سلوك النظام الفيزيائي بالكامل: توليد الطاقة من البلاط،
الاستهلاك، شحن وحدة التخزين، كشف الإشغال، وتنبيهات الذكاء الاصطناعي.

مهم: هذا الملف مصمَّم ليكون "مصدر بيانات" فقط. لوحة التحكم (frontend) وواجهة
الـ API (app.py) لا تعرفان أصلاً إن البيانات محاكاة — فلما تتوفر بلاطات
حقيقية وحساسات ESP32، كل اللي محتاجينه هو استبدال دالة tick() هنا بقراءة
فعلية قادمة من /api/ingest، وباقي النظام (API + Dashboard) يفضل شغال
بدون أي تعديل. راجع دالة ingest_real_reading() في app.py.
"""

import math
import random
import time
from collections import deque
from dataclasses import dataclass, field

import os
import sqlite3
import json
import joblib
import numpy as np
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import tensorflow as tf

# Load AI Models
try:
    occupancy_model = joblib.load("../models/occupancy_classifier.joblib")
    autoencoder = tf.keras.models.load_model("../models/tile_anomaly_autoencoder.keras")
    anomaly_scaler = joblib.load("../models/anomaly_scaler.joblib")
    anomaly_cfg = json.load(open("../models/anomaly_config.json"))
    lstm_model = tf.keras.models.load_model("../models/energy_forecast_lstm.keras")
    energy_scaler = joblib.load("../models/energy_scaler.joblib")
    AI_AVAILABLE = True
except Exception as e:
    print(f"Warning: AI Models not loaded. Fallback to simulation. Error: {e}")
    AI_AVAILABLE = False


# ============================================================
# إعدادات المحاكاة (Simulation Configuration)
# ============================================================

NUM_TILES = 12                 # عدد بلاطات التوليد في النموذج التجريبي
ENERGY_PER_STEP_J = 2.0        # جول/خطوة (افتراض بلاطة كهرومغناطيسية مهندَسة)
STORAGE_CAPACITY_WH = 3.0      # سعة وحدة التخزين (مكثفات + بطارية صغيرة)
BASE_LOAD_W = 3.0              # حمل ثابت: حساسات + بوابة ESP32 (يجب أن يعمل دائمًا)
LED_LOAD_W = 2.0               # إضاءة إرشادية LED (تعمل فقط عند وجود إشغال)
CHARGING_LOAD_W = 5.0          # محطة شحن تجريبية (تعمل فقط عند فائض تخزين)
SIM_SPEED = 90                 # 1 ثانية حقيقية = 90 ثانية محاكاة (يوم كامل خلال ~7 دقائق)
DAY_START_HOUR = 7.0
DAY_END_HOUR = 18.0
FAULTY_TILE_ID = 5              # بلاطة تتدهور كفاءتها تدريجيًا (لاختبار الصيانة التنبؤية)
HISTORY_MAXLEN = 600             # عدد النقاط المحفوظة لرسم الرسم البياني التراكمي


def footfall_rate(hour: float) -> float:
    """معدل الخطوات في الدقيقة بناءً على الساعة من اليوم (ذروات عند تبديل المحاضرات)."""
    peaks = [8, 10, 12, 14, 16]
    rate = 3.0
    for p in peaks:
        rate += 40 * math.exp(-((hour - p) ** 2) / (2 * 0.15 ** 2))
    return rate


@dataclass
class Tile:
    id: int
    efficiency: float = 1.0          # 1.0 = كفاءة كاملة
    cumulative_wh: float = 0.0
    is_real_hardware: bool = False    # هل البلاطة متصلة بهاردوير حقيقي؟
    last_real_update: float = 0.0    # آخر وقت وصلت فيه بيانات من الهاردوير

    def step_energy_j(self, base_energy_j: float) -> float:
        noise = random.uniform(0.85, 1.15)
        return base_energy_j * self.efficiency * noise


@dataclass
class SimState:
    sim_hour: float = DAY_START_HOUR
    day_number: int = 1

    generation_w: float = 0.0
    consumption_w: float = 0.0
    dc_load_w: float = 0.0

    storage_soc_wh: float = STORAGE_CAPACITY_WH * 0.5
    cumulative_gen_wh: float = 0.0
    cumulative_con_wh: float = 0.0

    footfall_now: float = 0.0
    occupancy: bool = False
    power_source: str = "harvested"   # "harvested" أو "grid_backup"

    tiles: list = field(default_factory=lambda: [Tile(i) for i in range(1, NUM_TILES + 1)])
    loads: dict = field(default_factory=dict)
    alerts: list = field(default_factory=list)

    history_t: deque = field(default_factory=lambda: deque(maxlen=HISTORY_MAXLEN))
    history_gen: deque = field(default_factory=lambda: deque(maxlen=HISTORY_MAXLEN))
    history_con: deque = field(default_factory=lambda: deque(maxlen=HISTORY_MAXLEN))
    history_soc: deque = field(default_factory=lambda: deque(maxlen=HISTORY_MAXLEN))
    history_footfall: deque = field(default_factory=lambda: deque(maxlen=HISTORY_MAXLEN))
    
    lstm_buffer: deque = field(default_factory=lambda: deque(maxlen=30))
    forecast_w: float = 0.0


class PowerStepSimulator:
    """محرك المحاكاة الرئيسي — استدعِ tick() كل ثانية تقريبًا."""

    def __init__(self):
        self.state = SimState()
        
        # 1. إعداد قاعدة البيانات (Setup DB)
        self.db = sqlite3.connect("../energy_system.db", check_same_thread=False)
        self.db.execute('''
            CREATE TABLE IF NOT EXISTS system_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sim_time TEXT,
                sim_hour REAL,
                cumulative_gen_wh REAL,
                cumulative_con_wh REAL,
                soc_wh REAL,
                footfall REAL,
                ts DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.db.commit()
        
        # 2. استرجاع التاريخ من الداتابيز عشان الرسم البياني ميبدأش من الصفر
        try:
            cursor = self.db.execute(
                "SELECT sim_hour, cumulative_gen_wh, cumulative_con_wh, soc_wh, footfall "
                "FROM system_metrics ORDER BY id DESC LIMIT ?", (HISTORY_MAXLEN,)
            )
            rows = cursor.fetchall()
            
            if rows:
                # تحديث الحالة الحالية عشان نكمل المحاكاة من مكان ما وقفت
                last_row = rows[0]
                self.state.sim_hour = float(last_row[0])
                self.state.cumulative_gen_wh = float(last_row[1])
                self.state.cumulative_con_wh = float(last_row[2])
                self.state.storage_soc_wh = float(last_row[3])
                
                # تعبئة الـ Deques (بترتيب عكسي عشان نرجع ترتيب الزمن الصح)
                for row in reversed(rows):
                    self.state.history_t.append(round(row[0], 3))
                    self.state.history_gen.append(round(row[1], 4))
                    self.state.history_con.append(round(row[2], 4))
                    self.state.history_soc.append(round(row[3], 4))
                    self.state.history_footfall.append(round(row[4], 1))
        except Exception as e:
            print(f"Error loading history from DB: {e}")
        
        self._last_real_time = time.time()
        self._elapsed_sim_seconds_today = (self.state.sim_hour - DAY_START_HOUR) * 3600.0

    def inject_real_data(self, tile_id: int, voltage: float, current_ma: float, rssi: float):
        """تحديث بيانات البلاطة من قراءات هاردوير حقيقية (Hybrid Mode)"""
        for t in self.state.tiles:
            if t.id == tile_id:
                t.voltage = voltage
                t.current_ma = current_ma
                t.rssi = rssi
                t.is_real_hardware = True
                t.last_real_update = time.time()
                break

    # -------------------------------------------------------
    def tick(self):
        now = time.time()
        dt_real = now - self._last_real_time
        self._last_real_time = now
        dt_sim_sec = dt_real * SIM_SPEED
        dt_sim_min = dt_sim_sec / 60.0

        s = self.state
        self._elapsed_sim_seconds_today += dt_sim_sec
        s.sim_hour = DAY_START_HOUR + (self._elapsed_sim_seconds_today / 3600.0)

        if s.sim_hour >= DAY_END_HOUR:
            self._start_new_day()
            return

        self._simulate_tile_degradation(dt_min=dt_sim_min)
        self._simulate_generation(dt_sim_min)
        self._simulate_occupancy_and_loads(dt_sim_min)
        self._simulate_storage(dt_sim_min)
        self._update_history()
        self._update_alerts()

    # -------------------------------------------------------
    def _start_new_day(self):
        s = self.state
        s.day_number += 1
        s.sim_hour = DAY_START_HOUR
        self._elapsed_sim_seconds_today = 0.0
        s.cumulative_gen_wh = 0.0
        s.cumulative_con_wh = 0.0
        s.history_t.clear(); s.history_gen.clear(); s.history_con.clear()
        s.history_soc.clear(); s.history_footfall.clear()

    # -------------------------------------------------------
    def _simulate_tile_degradation(self, dt_min):
        """بلاطة واحدة تفقد كفاءتها تدريجيًا لمحاكاة عطل حقيقي يكتشفه الذكاء الاصطناعي."""
        for tile in self.state.tiles:
            if tile.id == FAULTY_TILE_ID:
                progress = min(self._elapsed_sim_seconds_today / (3600 * 6), 1.0)
                tile.efficiency = max(0.55, 1.0 - progress * 0.45)

    # -------------------------------------------------------
    def _simulate_generation(self, dt_min):
        s = self.state
        base_rate = footfall_rate(s.sim_hour)
        steps_this_tick = max(0, random.gauss(base_rate * dt_min, math.sqrt(max(base_rate * dt_min, 0.01))))
        s.footfall_now = steps_this_tick / max(dt_min, 1e-6)  # steps/min تقريبي للعرض
        
        total_energy_wh = 0.0
        
        for tile in s.tiles:
            # Hybrid Mode: Skip simulation if real hardware is sending data
            if tile.is_real_hardware:
                if time.time() - tile.last_real_update < 5.0:
                    power_w = tile.voltage * (tile.current_ma / 1000.0)
                    energy_wh = power_w * (dt_min / 60.0)
                    tile.cumulative_wh += energy_wh
                    total_energy_wh += energy_wh
                    continue
                else:
                    # Timeout! Hardware disconnected, revert to simulation
                    tile.is_real_hardware = False
            
            # Normal Simulation
            share = steps_this_tick / NUM_TILES
            sim_energy_j = tile.step_energy_j(ENERGY_PER_STEP_J) * share
            sim_energy_wh = sim_energy_j / 3600.0
            tile.cumulative_wh += sim_energy_wh
            total_energy_wh += sim_energy_wh

        s.generation_w = (total_energy_wh / max(dt_min / 60.0, 1e-9)) if dt_min > 0 else 0.0
        s.cumulative_gen_wh += total_energy_wh

    # -------------------------------------------------------
    def _simulate_occupancy_and_loads(self, dt_min):
        s = self.state
        
        # محاكاة إشارة الواي فاي (RSSI) وتمريرها لموديل الذكاء الاصطناعي
        base_rssi = -70
        rssi_noise = s.footfall_now * 2.0
        rssi_vals = [base_rssi + random.uniform(-rssi_noise, rssi_noise) for _ in range(5)]
        
        if AI_AVAILABLE:
            arr = np.array(rssi_vals)
            feats = np.array([[arr.mean(), arr.std(), arr.min(), arr.max(),
                               arr.max() - arr.min(), np.mean(np.abs(np.diff(arr)))]])
            state = occupancy_model.predict(feats)[0]
            s.occupancy = (state != "empty")
        else:
            occupancy_prob = min(0.97, s.footfall_now / 25.0)
            s.occupancy = random.random() < occupancy_prob

        led_on = s.occupancy
        charging_on = s.storage_soc_wh > (STORAGE_CAPACITY_WH * 0.8)

        s.dc_load_w = BASE_LOAD_W + (LED_LOAD_W if led_on else 0) + (CHARGING_LOAD_W if charging_on else 0)

        energy_wh = s.dc_load_w * (dt_min / 60.0)
        s.cumulative_con_wh += energy_wh
        s.consumption_w = s.dc_load_w

        s.loads = {
            "sensors_gateway": {"name": "حساسات النظام + بوابة ESP32", "state": "ON (دائم)", "priority": "حرج"},
            "corridor_led": {"name": "إضاءة LED إرشادية بالممر", "state": "ON (تلقائي)" if led_on else "OFF (لا يوجد إشغال)", "priority": "متوسط"},
            "charging_station": {"name": "محطة شحن USB تجريبية", "state": "ON (فائض تخزين)" if charging_on else "Standby", "priority": "منخفض"},
        }

    # -------------------------------------------------------
    def _simulate_storage(self, dt_min):
        s = self.state
        gen_wh = s.generation_w * (dt_min / 60.0)
        con_wh = s.dc_load_w * (dt_min / 60.0)
        net_wh = gen_wh - con_wh
        s.storage_soc_wh = max(0.0, min(STORAGE_CAPACITY_WH, s.storage_soc_wh + net_wh))

        if s.storage_soc_wh <= STORAGE_CAPACITY_WH * 0.05 and s.dc_load_w > 0:
            s.power_source = "grid_backup"
        elif s.storage_soc_wh > STORAGE_CAPACITY_WH * 0.15:
            s.power_source = "harvested"

    # -------------------------------------------------------
    def _update_history(self):
        s = self.state
        s.history_t.append(round(s.sim_hour, 3))
        s.history_gen.append(round(s.cumulative_gen_wh, 4))
        s.history_con.append(round(s.cumulative_con_wh, 4))
        s.history_soc.append(round(s.storage_soc_wh, 4))
        s.history_footfall.append(round(s.footfall_now, 1))

        # Database Logging: حفظ كل دقيقة محاكاة في قاعدة البيانات
        try:
            hh = int(s.sim_hour) % 24
            mm = int((s.sim_hour % 1) * 60)
            sim_time_str = f"{hh:02d}:{mm:02d}"
            self.db.execute(
                "INSERT INTO system_metrics (sim_time, sim_hour, cumulative_gen_wh, cumulative_con_wh, soc_wh, footfall) VALUES (?, ?, ?, ?, ?, ?)",
                (sim_time_str, s.sim_hour, s.cumulative_gen_wh, s.cumulative_con_wh, s.storage_soc_wh, s.footfall_now)
            )
            self.db.commit()
        except Exception as e:
            print(f"DB Error: {e}")

        if AI_AVAILABLE:
            # تغذية موديل LSTM بآخر 30 قراءة للطاقة (بالميللي واط)
            s.lstm_buffer.append(s.generation_w * 1000.0)
            if len(s.lstm_buffer) == 30:
                try:
                    arr = np.array(s.lstm_buffer).reshape(-1, 1)
                    seq = energy_scaler.transform(arr).reshape(1, 30, 1)
                    pred_scaled = lstm_model.predict(seq, verbose=0)
                    pred_mw = energy_scaler.inverse_transform(pred_scaled)[0][0]
                    s.forecast_w = max(0.0, float(pred_mw) / 1000.0)
                except Exception as e:
                    pass

    # -------------------------------------------------------
    def _update_alerts(self):
        s = self.state
        alerts = []

        if AI_AVAILABLE:
            # استدعاء الموديل (Autoencoder) لكشف الأعطال المخفية
            try:
                # توليد بيانات طاقة لتمريرها للموديل
                tile_powers = {str(t.id): t.step_energy_j(ENERGY_PER_STEP_J) * t.efficiency for t in s.tiles}
                row = np.array([[tile_powers.get(str(c), 0.0) for c in anomaly_cfg["columns"]]])
                X_anom = anomaly_scaler.transform(row)
                recon = autoencoder.predict(X_anom, verbose=0)
                error = float(np.mean(np.square(X_anom - recon)))
                if error > anomaly_cfg["threshold"]:
                    alerts.append({"level": "danger", "text": f"[AI Alert] كشف شذوذ غير طبيعي في كفاءة التوليد (Error: {error:.2f})"})
            except Exception as e:
                pass
        else:
            for tile in s.tiles:
                if tile.efficiency < 0.80:
                    drop = round((1 - tile.efficiency) * 100)
                    alerts.append({"level": "warning", "text": f"بلاطة #{tile.id}: تراجع في الأداء (-{drop}%) — يُنصح بالفحص"})

        if s.storage_soc_wh > STORAGE_CAPACITY_WH * 0.9:
            alerts.append({"level": "info", "text": "وحدة التخزين قاربت على الامتلاء الكامل"})

        for peak in [8, 10, 12, 14, 16]:
            if 0 < (peak - s.sim_hour) * 60 <= 20:
                alerts.append({"level": "success", "text": f"نافذة فائض طاقة متوقعة الساعة {peak}:00"})

        if s.footfall_now > 35:
            alerts.append({"level": "warning", "text": "كثافة حركة عالية عند المدخل الآن"})

        if s.power_source == "grid_backup":
            alerts.append({"level": "danger", "text": "التخزين منخفض — تم التحويل للشبكة الاحتياطية"})

        s.alerts = alerts[:6]

    # -------------------------------------------------------
    def snapshot(self) -> dict:
        s = self.state
        self_sufficiency = (s.cumulative_gen_wh / s.cumulative_con_wh * 100) if s.cumulative_con_wh > 0 else 0.0
        hh = int(s.sim_hour)
        mm = int((s.sim_hour - hh) * 60)
        return {
            "day": s.day_number,
            "sim_time": f"{hh:02d}:{mm:02d}",
            "generation_w": round(s.generation_w, 2),
            "forecast_w": round(s.forecast_w, 2),
            "consumption_w": round(s.consumption_w, 2),
            "self_sufficiency_pct": round(min(self_sufficiency, 100), 1),
            "storage_soc_pct": round((s.storage_soc_wh / STORAGE_CAPACITY_WH) * 100, 1),
            "cumulative_gen_wh": round(s.cumulative_gen_wh, 3),
            "cumulative_con_wh": round(s.cumulative_con_wh, 3),
            "footfall": round(s.footfall_now, 1),
            "occupancy": s.occupancy,
            "power_source": s.power_source,
            "loads": s.loads,
            "alerts": s.alerts,
            "tiles": [{"id": t.id, "efficiency_pct": round(t.efficiency * 100, 1),
                       "cumulative_wh": round(t.cumulative_wh, 4),
                       "stepped_on": random.random() < min(s.footfall_now / 30.0, 0.4)} for t in s.tiles],
        }

    def history(self) -> dict:
        s = self.state
        return {
            "t": list(s.history_t),
            "gen_wh": list(s.history_gen),
            "con_wh": list(s.history_con),
            "soc_wh": list(s.history_soc),
            "footfall": list(s.history_footfall),
        }
