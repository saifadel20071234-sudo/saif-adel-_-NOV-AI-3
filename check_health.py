#!/usr/bin/env python3
"""
check_health.py — فحص شامل لبيئة PowerStep Grid قبل تشغيل البايبلاين.

يفحص:
  1. إصدار Python
  2. جميع الباكدجز المطلوبة وإصداراتها
  3. سلامة syntax جميع ملفات Python في المشروع
  4. وجود الملفات الأساسية (DB، parquet، models، labels)
  5. سلامة قاعدة البيانات وجداولها
  6. وجود نماذج الـ AI وملفات الإعداد

Usage:
    python check_health.py
"""

import sys
import os
import sqlite3
import importlib
import subprocess
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
MODELS_DIR = REPO_ROOT / "models"

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "
INFO = "ℹ️ "

errors   = []
warnings = []


def section(title: str):
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print(f"{'─' * 55}")


def ok(msg: str):
    print(f"  {PASS}  {msg}")


def fail(msg: str):
    print(f"  {FAIL}  {msg}")
    errors.append(msg)


def warn(msg: str):
    print(f"  {WARN} {msg}")
    warnings.append(msg)


def info(msg: str):
    print(f"  {INFO}  {msg}")


# ─────────────────────────────────────────────
# 1. Python version
# ─────────────────────────────────────────────
section("1️⃣  إصدار Python")
major, minor = sys.version_info.major, sys.version_info.minor
ver_str = f"{major}.{minor}.{sys.version_info.micro}"
if major == 3 and minor >= 9:
    ok(f"Python {ver_str}  (≥ 3.9 ✓)")
else:
    fail(f"Python {ver_str}  — محتاج 3.9 أو أحدث")


# ─────────────────────────────────────────────
# 2. الباكدجز المطلوبة
# ─────────────────────────────────────────────
section("2️⃣  الباكدجز المطلوبة")

REQUIRED_PACKAGES = {
    "paho.mqtt":        "paho-mqtt",
    "pandas":           "pandas",
    "numpy":            "numpy",
    "sklearn":          "scikit-learn",
    "tensorflow":       "tensorflow",
    "joblib":           "joblib",
    "streamlit":        "streamlit",
    "plotly":           "plotly",
    "matplotlib":       "matplotlib",
    "seaborn":          "seaborn",
    "qrcode":           "qrcode",
    "requests":         "requests",
    "pyarrow":          "pyarrow",
}

for import_name, pkg_name in REQUIRED_PACKAGES.items():
    try:
        mod = importlib.import_module(import_name)
        version = getattr(mod, "__version__", "?")
        ok(f"{pkg_name:<30} v{version}")
    except ImportError:
        fail(f"{pkg_name:<30} غير مثبت — شغّل: pip install {pkg_name}")

# تحقق خاص من paho.mqtt.enums (موجودة في paho-mqtt >= 2.0 فقط)
try:
    from paho.mqtt.enums import CallbackAPIVersion  # noqa: F401
    ok(f"{'paho-mqtt >= 2.0 (CallbackAPIVersion)':<30} ✓")
except ImportError:
    warn("paho-mqtt < 2.0 — CallbackAPIVersion غير موجودة، قد تظهر تحذيرات. شغّل: pip install --upgrade paho-mqtt")

# تحقق من pandas >= 2.0 (مطلوب لـ .ffill() بدل fillna(method=))
try:
    import pandas as pd
    pd_major = int(pd.__version__.split(".")[0])
    if pd_major >= 2:
        ok(f"{'pandas >= 2.0 (ffill API)':<30} ✓")
    else:
        warn(f"pandas {pd.__version__} — يُفضَّل الترقية لـ 2.x: pip install --upgrade pandas")
except Exception:
    pass


# ─────────────────────────────────────────────
# 3. syntax جميع ملفات Python
# ─────────────────────────────────────────────
section("3️⃣  سلامة Syntax ملفات Python")

py_files = sorted(REPO_ROOT.glob("*.py"))
for py_file in py_files:
    if py_file.name == Path(__file__).name:
        continue  # تخطي هذا الملف نفسه
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(py_file)],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        ok(f"{py_file.name}")
    else:
        err_line = result.stderr.strip().split("\n")[-1]
        fail(f"{py_file.name} — {err_line}")


# ─────────────────────────────────────────────
# 4. الملفات الأساسية
# ─────────────────────────────────────────────
section("4️⃣  الملفات الأساسية")

REQUIRED_FILES = {
    "energy_system.db":            "قاعدة البيانات الرئيسية (شغّل ingest.py أو simulate_sensors.py أولاً)",
    "labels.csv":                  "ملف التصنيفات اليدوية (مطلوب لتدريب مصنف الإشغال)",
}

OPTIONAL_FILES = {
    "data_energy_raw.parquet":       "ناتج fetch_data.py",
    "data_rssi_raw.parquet":         "ناتج fetch_data.py",
    "features_rssi_clean.parquet":   "ناتج clean_data.py",
    "features_rssi_labeled.parquet": "ناتج clean_data.py (مع labels.csv)",
    "data_energy_clean.parquet":     "ناتج clean_data.py",
}

for fname, desc in REQUIRED_FILES.items():
    path = REPO_ROOT / fname
    if path.exists():
        size_kb = path.stat().st_size / 1024
        ok(f"{fname:<40} ({size_kb:.1f} KB)")
    else:
        fail(f"{fname:<40} مفقود — {desc}")

for fname, desc in OPTIONAL_FILES.items():
    path = REPO_ROOT / fname
    if path.exists():
        size_kb = path.stat().st_size / 1024
        ok(f"{fname:<40} ({size_kb:.1f} KB)")
    else:
        warn(f"{fname:<40} غير موجود بعد — {desc}")


# ─────────────────────────────────────────────
# 5. قاعدة البيانات وجداولها
# ─────────────────────────────────────────────
section("5️⃣  قاعدة البيانات SQLite")

db_path = REPO_ROOT / "energy_system.db"
if db_path.exists():
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        expected_tables = ["readings_energy", "readings_rssi", "alerts", "ai_results"]
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {row[0] for row in cursor.fetchall()}
        for table in expected_tables:
            if table in existing:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                ok(f"جدول '{table}' موجود — {count:,} صف")
            else:
                fail(f"جدول '{table}' مفقود — شغّل ingest.py لإنشاء الجداول")
        conn.close()
    except sqlite3.DatabaseError as e:
        fail(f"خطأ في قاعدة البيانات: {e}")
else:
    info("energy_system.db غير موجود — الفحص مُتخطَّى")


# ─────────────────────────────────────────────
# 6. نماذج الـ AI
# ─────────────────────────────────────────────
section("6️⃣  نماذج الـ AI")

AI_MODELS = {
    "models/occupancy_classifier.joblib":       "مصنف الإشغال (Random Forest / SVM)",
    "models/energy_forecast_lstm.keras":        "نموذج التنبؤ بالطاقة (LSTM)",
    "models/energy_scaler.joblib":              "Scaler الطاقة",
    "models/tile_anomaly_autoencoder.keras":    "نموذج كشف الشذوذ (Autoencoder)",
    "models/anomaly_scaler.joblib":             "Scaler الشذوذ",
    "models/anomaly_config.json":               "إعدادات الشذوذ (threshold + columns)",
}

for rel_path, desc in AI_MODELS.items():
    full_path = REPO_ROOT / rel_path
    if full_path.exists():
        size_kb = full_path.stat().st_size / 1024
        ok(f"{rel_path:<50} ({size_kb:.1f} KB)")
    else:
        warn(f"{rel_path:<50} غير موجود — {desc}")

# فحص محتوى anomaly_config.json
config_path = REPO_ROOT / "models/anomaly_config.json"
if config_path.exists():
    try:
        cfg = json.loads(config_path.read_text())
        threshold = cfg.get("threshold")
        columns   = cfg.get("columns", [])
        ok(f"anomaly_config: threshold={threshold:.4f}, {len(columns)} عمود tile")
    except Exception as e:
        fail(f"anomaly_config.json تالف: {e}")


# ─────────────────────────────────────────────
# الملخص النهائي
# ─────────────────────────────────────────────
section("📊  الملخص")

if errors:
    print(f"\n  {FAIL}  {len(errors)} خطأ يجب إصلاحه:")
    for i, e in enumerate(errors, 1):
        print(f"       {i}. {e}")

if warnings:
    print(f"\n  {WARN}  {len(warnings)} تحذير:")
    for i, w in enumerate(warnings, 1):
        print(f"       {i}. {w}")

if not errors and not warnings:
    print(f"\n  {PASS}  كل حاجة تمام — البيئة جاهزة لتشغيل البايبلاين! 🚀")
elif not errors:
    print(f"\n  {PASS}  لا توجد أخطاء — يمكن تشغيل البايبلاين (راجع التحذيرات)")
else:
    print(f"\n  {FAIL}  في أخطاء لازم تتحل الأول قبل تشغيل البايبلاين")

print()
sys.exit(1 if errors else 0)
