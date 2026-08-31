import pandas as pd, numpy as np, json, joblib
from sklearn.preprocessing import StandardScaler
from keras.models import Model
from keras.layers import Input, Dense

# 1. جلب البيانات: نقوم بقراءة البيانات المنظفة التي تم جمعها مسبقاً
df = pd.read_parquet("data_energy_clean.parquet")

# 2. تجهيز البيانات (Pivot): نحول البيانات بحيث يكون لكل بلاطة عمود خاص بها يمثل الطاقة (power_mw)
# نستخدم ffill() و dropna() لمعالجة أي قيم مفقودة لضمان أن الموديل يتدرب على بيانات "طبيعية" ومكتملة
normal = df.pivot_table(index="ts", columns="tile_id", values="power_mw").ffill().dropna()

# 3. توحيد المقاييس (Scaling): الموديلات العصبية تعمل بشكل أفضل عندما تكون الأرقام بين -1 و 1 أو 0 و 1
# الـ StandardScaler بيوحد المقاييس عشان الموديل ميختلش لو في بلاطة بتطلع طاقة أعلى بكتير من الباقي
scaler = StandardScaler()
X = scaler.fit_transform(normal.values)

# 4. بناء هيكل الموديل (Autoencoder Architecture):
input_dim = X.shape[1] # عدد المدخلات (يمثل عدد البلاطات)

# طبقة الإدخال (المدخلات)
inp = Input(shape=(input_dim,))

# طبقة التشفير (Encoder): بتضغط البيانات وتقلل حجمها للنص تقريباً (لاستخراج الأنماط الطبيعية المهمة فقط)
encoded = Dense(max(2, input_dim // 2), activation="relu")(inp)

# طبقة فك التشفير (Decoder): بتحاول ترجع البيانات المﻀغوطة لشكلها الأصلي
decoded = Dense(input_dim, activation="linear")(encoded)

# تجميع الموديل
autoencoder = Model(inp, decoded)

# 5. تجميع وتدريب الموديل:
# نستخدم 'mse' (متوسط مربع الخطأ) لمعرفة مدى نجاح الموديل في إعادة بناء البيانات
autoencoder.compile(optimizer="adam", loss="mse")

# الموديل بيتدرب إنه يشوف الداتا السليمة (X) ويحاول يطلع نفس الداتا السليمة (X) تاني. 
# لأنه بيتعلم شكل الداتا السليمة بس، فأي داتا فيها عطل مش هيعرف يرجعها لشكلها الأصلي وهيدي نسبة خطأ عالية.
autoencoder.fit(X, X, epochs=100, batch_size=16, validation_split=0.1, verbose=0)

# 6. حساب "الحد الفاصل" للأعطال (Threshold Calculation):
# بنخلي الموديل يختبر نفسه على البيانات السليمة ونشوف أقصى نسبة خطأ بيقع فيها وهو في حالته الطبيعية
recon = autoencoder.predict(X)
errors = np.mean(np.square(X - recon), axis=1)

# الحد الفاصل = متوسط الخطأ الطبيعي + 3 أضعاف الانحراف المعياري (قاعدة إحصائية مشهورة لفلترة الشذوذ)
# لو أي قراءة في المستقبل تخطت الرقم ده، السيستم بيعتبرها فوراً "كسر أو عطل في البلاطة"
threshold = float(np.mean(errors) + 3 * np.std(errors))

# 7. حفظ الموديل والإعدادات عشان السيرفر الحي (FastAPI) يستخدمهم وهو شغال
autoencoder.save("models/tile_anomaly_autoencoder.keras")
joblib.dump(scaler, "models/anomaly_scaler.joblib")
json.dump({"threshold": threshold, "columns": list(normal.columns)}, open("models/anomaly_config.json", "w"))

print(f"تم حفظ نموذج كشف الشذوذ | الحد الفاصل: {threshold:.4f}")