# PowerStep Grid - AI-Powered Smart Floor System

مرحبا بك في المستودع الرسمي لمشروع **PowerStep Grid**.
هذا المشروع عبارة عن نظام متكامل (ارضية ذكية لتوليد الطاقة) يدمج بين محاكاة الفيزياء، تحليل البيانات، وثلاثة نماذج ذكاء اصطناعي (AI) تعمل في الوقت الفعلي لاكتشاف الاعطال، تحديد معدل الاشغال، والتنبؤ بمستقبل توليد الطاقة.

**رابط المستودع (GitHub):** https://github.com/saifadel20071234-sudo/saif-adel-_-NOV-AI-3.git

---

## المتطلبات الاساسية (Prerequisites)

- **نسخة بايثون:** Python 3.10 او احدث
- **المكتبات المطلوبة:**
  ```bash
  pip install -r requirements.txt
  ```
  وتشمل:
  - `fastapi` و `uvicorn` (للسيرفر)
  - `tensorflow` / `keras` (للذكاء الاصطناعي LSTM و Autoencoder)
  - `scikit-learn` و `joblib` (للتصنيف RF/SVM)
  - `pandas` و `numpy` (لتحليل البيانات)

---

## احدث المميزات المضافة (New Features)

- **التدريب الهجين (Hybrid Training):** دمج بيانات المحاكاة (Synthetic) مع البيانات الحقيقية من الهاردوير (Real) لتحسين دقة النماذج باسلوب Sim2Real المعتمد في كبرى شركات الذكاء الاصطناعي.
- **مؤشر حماية البيئة (CO2 Tracker):** يحسب مقدار غاز CO2 الذي تم منع انبعاثه بفضل توليد الطاقة النظيفة.
- **تصدير التقارير (CSV Export):** زر لتحميل جميع البيانات التاريخية في ملف Excel بضغطة واحدة.
- **صفحة تحليلات تاريخية (Analytics):** صفحة جديدة تعرض ملخص الايام السابقة.
- **توثيق واجهة البرمجة (API Docs):** صفحة Swagger تفاعلية مدمجة للـ Backend.
- **اشعارات البريد الالكتروني (Email Alerts):** ارسال انذار فوري عند اكتشاف اي اعطال.

---

## كيفية التثبيت والتشغيل (How to Run)

```bash
git clone https://github.com/saifadel20071234-sudo/saif-adel-_-NOV-AI-3.git
cd PowerStep-Grid-main
pip install -r requirements.txt
```

اضغط مرتين على:
- `4_Run_All_AI_Web.bat` — وضع الهاردوير الحقيقي
- `5_Run_All_AI_Web_Demo.bat` — وضع المحاكاة Demo

---

## دليل ملفات المشروع (Project Structure)

### 1 - ملفات التشغيل (Launchers)

| الملف | الوصف |
|-------|-------|
| `4_Run_All_AI_Web.bat` | وضع الهاردوير — يشغل السيرفر ويستقبل بيانات ESP32 مباشرة |
| `5_Run_All_AI_Web_Demo.bat` | وضع Demo — يشغل النظام كاملا بالمحاكاة بدون هاردوير |
| `1_Train_Models.bat` | يدرب كل نماذج الذكاء الاصطناعي من الصفر |
| `wait_and_open.py` | يفتح المتصفح تلقائيا عندما يكون السيرفر جاهزا |

### 2 - واجهة المستخدم والسيرفر (Frontend & Backend)

| الملف | الوصف |
|-------|-------|
| `frontend/index.html` | الداشبورد الرئيسي (Sci-Fi Glassmorphism Design) |
| `frontend/analytics.html` | صفحة التحليلات التاريخية |
| `backend/app.py` | السيرفر (FastAPI) — endpoints: `/api/live`, `/api/history`, `/api/ingest`, `/api/export/csv` |
| `backend/simulator.py` | المحرك الفيزيائي — يحاكي الاقدام ويستدعي نماذج AI في الوقت الفعلي |

### 3 - الهاردوير (Hardware - ESP32)

| الملف | الوصف |
|-------|-------|
| `esp32_hardware_template/` | كود Arduino C++ للـ ESP32 — يقرا الحساسات (فولت + RSSI) ويرسل للسيرفر |

> **مهم:** تاكد ان كود ESP32 يطبع `WiFi.RSSI()` مع الفولت في نفس السطر عشان موديل عد الناس يشتغل.

### 4 - قواعد البيانات والبيانات (Data & DB)

| الملف | الوصف |
|-------|-------|
| `energy_system.db` | قاعدة بيانات SQLite — تسجل كل قراءات الطاقة والتاريخ |
| `*.parquet` | ملفات بيانات Big Data مضغوطة لتدريب الذكاء الاصطناعي |
| `labels.csv` | ملف التصنيفات الزمنية (start_ts, end_ts, label) |
| `labels_from_wifi.csv` | تصنيفات محولة من الجلسة الحقيقية (wifi_dataset.csv) |

### 5 - نماذج الذكاء الاصطناعي (AI Training Scripts)

| الملف | الوصف |
|-------|-------|
| `generate_training_data.py` | يولد بيانات محاكاة بتواريخ متزامنة مع labels.csv |
| `clean_data.py` | يطبق Kalman Filter ويستخرج Features من الاشارة |
| `train_occupancy_classifier.py` | يدرب Random Forest / SVM لتصنيف عدد الاشخاص من RSSI |
| `train_autoencoder_anomaly.py` | يدرب Autoencoder لكشف الاعطال (Anomaly Detection) |
| `train_lstm_forecast.py` | يدرب LSTM للتنبؤ بكمية الطاقة المستقبلية |
| `run_pipeline.py` | يشغل Pipeline الكامل بالترتيب، يدعم `--only` لخطوات بعينها |

### 6 - سكربتات تحويل البيانات الحقيقية (Real Data Conversion) - جديد

هذه السكربتات تمكن **Hybrid Training** — دمج البيانات الحقيقية مع المحاكاة:

**`convert_piezo_data.py`**
يحول ملف CSV الخام من ESP32 (عمود `Raw: X | Voltage: Y V` كنص ملتصق) الى Parquet نظيف.
```bash
python convert_piezo_data.py --date 2026-09-01 --load-ohms 1000000
```

**`convert_wifi_labels.py`**
يحول ملف `wifi_dataset.csv` (فيه timestamp و people_count) الى تنسيق labels.csv.
```bash
python convert_wifi_labels.py
```

**`build_training_energy_dataset.py`**
يدمج بيانات الطاقة الحقيقية مع المحاكاة مع **Normalization مستقل لكل مصدر**.
```bash
python build_training_energy_dataset.py
```

**ترتيب تشغيل سكربتات البيانات الحقيقية:**
```
1. convert_piezo_data.py         --> data_energy_raw_piezo.parquet
2. convert_wifi_labels.py        --> labels_from_wifi.csv
3. build_training_energy_dataset.py --> data_energy_raw_merged.parquet
4. venv\Scripts\python.exe run_pipeline.py --only train_lstm_forecast train_autoencoder_anomaly
```

---

## اشعارات البريد الالكتروني (Email Alerts)

النظام يدعم ارسال ايميل تلقائي عند اكتشاف اعطال. لتفعيلها:
1. افتح `backend/app.py`
2. غير `EMAIL_ENABLED = False` الى `EMAIL_ENABLED = True`
3. ضع بيانات Gmail + App Password

---

*تم اعداد هذا التوثيق ليكون دليلا شاملا للمشروع وتفاصيل الذكاء الاصطناعي المدمج به.*
