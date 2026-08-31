import pandas as pd, numpy as np, joblib
from sklearn.preprocessing import MinMaxScaler
import tensorflow as tf
from keras.models import Sequential
from keras.layers import LSTM, Dense, Dropout
from keras.callbacks import EarlyStopping

# 1. جلب البيانات وتجهيزها كسلسلة زمنية (Time-Series)
df = pd.read_parquet("data_energy_clean.parquet")

# بنجمع الطاقة المولدة في كل دقيقة عشان نعمل سلسلة زمنية منتظمة (الدقيقة 1 كذا، الدقيقة 2 كذا...)
series = df.groupby(pd.Grouper(key="ts", freq="1min"))["power_mw"].sum().fillna(0).values.reshape(-1, 1)

# 2. توحيد المقاييس (Scaling): من 0 لـ 1 لأن الـ LSTM حساس جداً للأرقام الكبيرة وبيتدرب أسرع على الأرقام الصغيرة
scaler = MinMaxScaler()
scaled = scaler.fit_transform(series)

# 3. تجهيز الداتا بنظام الـ (Lookback)
# Lookback = 30 معناها: الموديل هيبص على آخر 30 دقيقة، عشان يتوقع الدقيقة الـ 31
LOOKBACK = 30
def make_sequences(data, lookback):
    X, y = [], []
    for i in range(lookback, len(data)):
        X.append(data[i-lookback:i, 0]) # الـ 30 دقيقة السابقة (المدخلات)
        y.append(data[i, 0])            # الدقيقة اللي بعدها مباشرة (الهدف اللي عايزين نتوقعه)
    return np.array(X), np.array(y)

X, y = make_sequences(scaled, LOOKBACK)
# تعديل شكل الـ Array عشان يتناسب مع متطلبات الـ LSTM
X = X.reshape((X.shape[0], X.shape[1], 1))

# 4. تقسيم البيانات زمنياً (مهم جداً!)
# في السلاسل الزمنية مينفعش نخلط الداتا عشوائي (زي الـ Random Forest)، لازم التدريب يكون على الماضي، والاختبار يكون على المستقبل
split = int(len(X) * 0.8)
X_train, X_test = X[:split], X[split:]
y_train, y_test = y[:split], y[split:]

# 5. بناء هيكل الموديل (LSTM Architecture)
model = Sequential([
    # طبقة LSTM (Long Short-Term Memory): ذاكرة طويلة المدى، بتفهم التسلسل الزمني للبيانات وعلاقتها ببعض
    LSTM(64, activation="tanh", input_shape=(LOOKBACK, 1), return_sequences=False),
    
    # طبقة Dropout: بتقفل 20% من الخلايا عشوائياً عشان تمنع الموديل إنه "يحفظ" الداتا صم (يمنع الـ Overfitting)
    Dropout(0.2),
    
    # طبقة Dense للربط والاستنتاج
    Dense(32, activation="relu"),
    
    # طبقة المخرجات: خلية واحدة بس بتطلع رقم واحد (كمية الطاقة المتوقعة)
    Dense(1)
])

# 'mse' لحساب الخطأ، و 'mae' لقياس متوسط الخطأ المطلق
model.compile(optimizer="adam", loss="mse", metrics=["mae"])

# 6. التدريب مع الإيقاف المبكر (Early Stopping)
# الموديل هيتدرب 50 لفة، بس لو مالقاش أي تحسن لمدة 5 لفات ورا بعض هيوقف لوحده عشان مياخدش وقت عالفاضي
es = EarlyStopping(monitor="val_loss", patience=5, restore_best_weights=True)
model.fit(X_train, y_train, validation_data=(X_test, y_test), epochs=50, batch_size=16, callbacks=[es])

# 7. حفظ الموديل لاستخدامه لاحقاً في السيرفر وقت تشغيل النظام
model.save("models/energy_forecast_lstm.keras")
joblib.dump(scaler, "models/energy_scaler.joblib")
print("تم حفظ نموذج التنبؤ بالطاقة بنجاح")