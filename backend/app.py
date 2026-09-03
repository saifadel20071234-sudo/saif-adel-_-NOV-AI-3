import asyncio
import threading
import time
import sqlite3
import csv
import io
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, Response
import paho.mqtt.client as mqtt
import json

from simulator import PowerStepSimulator

app = FastAPI(title="PowerStep Grid API")
# يسمح لأي صفحة ويب (حتى لو مفتوحة من ملف على جهازك) بالتواصل مع السيرفر
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

sim = PowerStepSimulator()

# إعدادات الإيميل (اختياري — غيّرها لإعداداتك الحقيقية لتفعيل الإشعارات)
EMAIL_ENABLED = True
EMAIL_SENDER = "saifadel20071234@gmail.com"
EMAIL_PASSWORD = "rnnv vyoi cxju wrvd"
EMAIL_RECEIVER = "saifadel20071234@gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# متغير لمنع تكرار الإشعارات (Cooldown)
_last_alert_time = 0.0
ALERT_COOLDOWN_SECONDS = 300  # 5 دقائق بين كل إشعار


# ============================================================
# اتصال MQTT مع الهاردوير الحقيقي
# ============================================================
mqtt_client = mqtt.Client()

def on_mqtt_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        if msg.topic.startswith("energy/tiles/"):
            tile_id_str = payload.get("tile_id", "").replace("tile_", "")
            if tile_id_str.isdigit():
                power_mw = payload.get("power_mw", 0)
                steps = payload.get("steps", 0)
                sim.inject_real_data(int(tile_id_str), 5.0, power_mw / 5.0, -50.0, steps)
        elif msg.topic.startswith("occupancy/rssi/"):
            rssi = payload.get("rssi", -90)
            sim.inject_real_data(1, 5.0, 0, rssi)
    except Exception as e:
        print(f"MQTT Error: {e}")

mqtt_client.on_message = on_mqtt_message

def start_mqtt_background():
    try:
        mqtt_client.connect("broker.emqx.io", 1883, 60)
        mqtt_client.subscribe([("energy/tiles/+/telemetry", 0), ("occupancy/rssi/+/telemetry", 0)])
        mqtt_client.loop_start()
        print("MQTT Client Connected to EMQX. Real hardware linked to Sci-Fi Dashboard.")
    except Exception as e:
        print(f"MQTT Connection Failed: {e}")


# ============================================================
# تشغيل المحاكاة في خيط منفصل (Background Thread)
# ============================================================
def _simulation_loop():
    global _last_alert_time
    while True:
        sim.tick()
        
        # ربط حالة اللمبة في المحاكي بالهاردوير
        led_state = sim.state.loads.get("corridor_led", {}).get("state", "OFF")
        cmd = "ON" if "ON" in led_state else "OFF"
        if int(time.time()) % 2 == 0:
            try:
                mqtt_client.publish("actuators/relay/corridor_light/cmd", cmd)
            except: pass

        # فحص الإنذارات وإرسال إيميل لو فيه عطل
        if EMAIL_ENABLED:
            snapshot = sim.snapshot()
            if snapshot.get("alerts") and len(snapshot["alerts"]) > 0:
                now = time.time()
                if now - _last_alert_time > ALERT_COOLDOWN_SECONDS:
                    _last_alert_time = now
                    try:
                        alert_texts = [a["text"] for a in snapshot["alerts"]]
                        _send_alert_email(alert_texts)
                    except Exception as e:
                        print(f"Email Error: {e}")
        
        time.sleep(1.0)


def _send_alert_email(alerts: list):
    """إرسال إيميل تنبيهي عند اكتشاف أعطال"""
    body = "⚠️ PowerStep Grid — إنذار أعطال\n\n"
    body += f"الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    body += "الأعطال المكتشفة:\n"
    for i, a in enumerate(alerts, 1):
        body += f"  {i}. {a}\n"
    body += "\nيرجى مراجعة لوحة التحكم فوراً."

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "⚠️ PowerStep Grid Alert — عطل مكتشف!"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
    print("Alert email sent successfully!")


@app.on_event("startup")
def start_background_simulation():
    start_mqtt_background()
    thread = threading.Thread(target=_simulation_loop, daemon=True)
    thread.start()


# ============================================================
# API Endpoints
# ============================================================

@app.get("/api/live")
def get_live():
    """أهم نقطة اتصال — بترجع كل الأرقام اللحظية اللي الداشبورد محتاجاها."""
    return sim.snapshot()


@app.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    """نقطة اتصال WebSocket لدفع البيانات اللحظية للواجهة بشكل دائم."""
    await websocket.accept()
    try:
        while True:
            data = sim.snapshot()
            await websocket.send_json(data)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        print("Client disconnected from WebSocket")


@app.get("/api/history")
def get_history():
    """بيانات تراكمية لرسم الرسم البياني (توليد مقابل استهلاك على مدار اليوم)."""
    return sim.history()


@app.post("/api/ingest")
def ingest_real_reading(payload: dict):
    """
    استقبال قراءات حقيقية من ESP32 فعلي وتوجيهها للمحاكي الهجين.
    """
    tile_id = payload.get("tile_id")
    if tile_id is not None:
        voltage = payload.get("voltage", 0.0)
        current_ma = payload.get("current_ma", 0.0)
        rssi = payload.get("rssi", -90.0)
        
        sim.inject_real_data(tile_id, voltage, current_ma, rssi)
        return {"status": "success", "message": f"Tile {tile_id} updated from hardware"}
    
    return {"status": "error", "message": "Missing tile_id"}


# ============================================================
# تصدير التقارير (Export Reports)
# ============================================================

@app.get("/api/export/csv")
def export_csv():
    """تحميل جميع بيانات الطاقة المحفوظة كملف CSV"""
    db = sqlite3.connect("../energy_system.db")
    cursor = db.execute(
        "SELECT sim_time, sim_hour, cumulative_gen_wh, cumulative_con_wh, soc_wh, footfall, ts "
        "FROM system_metrics ORDER BY id"
    )
    rows = cursor.fetchall()
    db.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Sim_Time", "Sim_Hour", "Generated_Wh", "Consumed_Wh", "Battery_SOC_Wh", "Footfall", "Timestamp"])
    writer.writerows(rows)
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=PowerStep_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"}
    )


# ============================================================
# تحليلات متعددة الأيام (Multi-Day Analytics)
# ============================================================

@app.get("/api/analytics/summary")
def get_analytics_summary():
    """ملخص الأداء العام — إجمالي الطاقة المولدة والمستهلكة وعدد السجلات"""
    db = sqlite3.connect("../energy_system.db")
    
    cursor = db.execute(
        "SELECT COUNT(*), MAX(cumulative_gen_wh), MAX(cumulative_con_wh), AVG(soc_wh), AVG(footfall) "
        "FROM system_metrics"
    )
    row = cursor.fetchone()
    
    # بيانات آخر 24 ساعة مقارنة بأقدم 24 ساعة (للترند)
    cursor2 = db.execute(
        "SELECT sim_hour, cumulative_gen_wh, cumulative_con_wh, soc_wh, footfall, ts "
        "FROM system_metrics ORDER BY id DESC LIMIT 1440"
    )
    recent_rows = cursor2.fetchall()
    
    db.close()
    
    return {
        "total_records": row[0] or 0,
        "peak_generation_wh": round(row[1] or 0, 4),
        "peak_consumption_wh": round(row[2] or 0, 4),
        "avg_battery_soc_wh": round(row[3] or 0, 4),
        "avg_footfall": round(row[4] or 0, 1),
        "recent_data": [
            {
                "sim_hour": r[0], "gen_wh": r[1], "con_wh": r[2],
                "soc_wh": r[3], "footfall": r[4], "ts": r[5]
            }
            for r in reversed(recent_rows[-200:])  # آخر 200 نقطة
        ]
    }


# ============================================================
# معلومات نماذج الذكاء الاصطناعي (AI Models Info)
# ============================================================

import os
import json as _json
from pathlib import Path

@app.get("/api/ai-info")
def get_ai_info():
    """معلومات عن نماذج الذكاء الاصطناعي المحملة — الاسم والدقة وتاريخ التدريب"""
    models_dir = Path("../models")
    demo_mode  = os.environ.get("DEMO_MODE", "0") == "1"
    data_source = "محاكاة (Synthetic)" if demo_mode else "هجين — حقيقي + محاكاة (Hybrid Real)"

    def file_date(path: Path) -> str:
        try:
            ts = path.stat().st_mtime
            from datetime import datetime
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except:
            return "غير متاح"

    # قراءة threshold الـ Autoencoder من ملف الضبط
    anomaly_threshold = None
    anomaly_cfg = models_dir / "anomaly_config.json"
    if anomaly_cfg.exists():
        try:
            anomaly_threshold = _json.loads(anomaly_cfg.read_text())
        except:
            pass

    # ملفات النماذج
    rf_path   = models_dir / "occupancy_classifier.joblib"
    lstm_path = models_dir / "energy_forecast_lstm.keras"
    ae_path   = models_dir / "tile_anomaly_autoencoder.keras"

    models_info = [
        {
            "id": "random_forest",
            "name": "Random Forest Classifier",
            "task": "تصنيف الإشغال — يحدد هل البلاطة مشغولة أم لا",
            "library": "scikit-learn",
            "input_features": ["mean RSSI", "std RSSI", "min RSSI", "max RSSI", "range RSSI", "mean_abs_diff"],
            "output": "empty / occupied",
            "accuracy_note": "دقة 34% على Synthetic بس — ستتحسن لـ 90%+ مع داتا RSSI حقيقية",
            "trained_on": data_source,
            "model_file": str(rf_path.name) if rf_path.exists() else "غير موجود",
            "last_trained": file_date(rf_path) if rf_path.exists() else "لم يُدرَّب بعد",
            "status": "ready" if rf_path.exists() else "missing",
        },
        {
            "id": "lstm",
            "name": "LSTM Forecast Network",
            "task": "التنبؤ بالطاقة — يتوقع كمية الواط القادمة",
            "library": "TensorFlow / Keras",
            "input_features": ["power_mw (تسلسل زمني — نافذة 24 نقطة)"],
            "output": "forecast_w (التوقع المستقبلي بالواط)",
            "accuracy_note": "Validation MAE ≈ 0.0005 (بعد التدريب الهجين)",
            "trained_on": data_source,
            "model_file": str(lstm_path.name) if lstm_path.exists() else "غير موجود",
            "last_trained": file_date(lstm_path) if lstm_path.exists() else "لم يُدرَّب بعد",
            "status": "ready" if lstm_path.exists() else "missing",
        },
        {
            "id": "autoencoder",
            "name": "Autoencoder Anomaly Detector",
            "task": "كشف الأعطال — يكتشف أي شذوذ في قراءات الطاقة",
            "library": "TensorFlow / Keras",
            "input_features": ["power_mw (نافذة 30 نقطة)"],
            "output": "anomaly score — يُصدر إنذاراً لو تجاوز الـ Threshold",
            "accuracy_note": f"Anomaly Threshold = {anomaly_threshold.get('threshold', 'N/A') if anomaly_threshold else 'N/A'}",
            "trained_on": data_source,
            "model_file": str(ae_path.name) if ae_path.exists() else "غير موجود",
            "last_trained": file_date(ae_path) if ae_path.exists() else "لم يُدرَّب بعد",
            "status": "ready" if ae_path.exists() else "missing",
        },
    ]

    return {
        "data_source": data_source,
        "demo_mode": demo_mode,
        "models": models_info,
        "pipeline": [
            "generate_training_data.py → يولد بيانات محاكاة",
            "clean_data.py → Kalman Filter + Feature Extraction",
            "train_occupancy_classifier.py → Random Forest + SVM",
            "train_lstm_forecast.py → LSTM (50 epochs)",
            "train_autoencoder_anomaly.py → Autoencoder (50 epochs)",
        ]
    }




# ============================================================
# تقديم ملفات لوحة التحكم (Frontend)
# ============================================================
app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")

