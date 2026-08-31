import pandas as pd, joblib
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns

# 1. جلب البيانات: نقرأ ملف الـ Parquet اللي بيحتوي على الخصائص (Features) المستخرجة مسبقاً
df = pd.read_parquet("features_rssi_labeled.parquet")

# X (المدخلات): هي الخصائص الرياضية لقراءات الحساس (المتوسط، الانحراف المعياري، إلخ)
X = df[["mean", "std", "min", "max", "range", "mean_abs_diff"]]

# y (المخرجات): هو التصنيف أو الـ Label اللي عايزين الموديل يتوقعه (طفل، بالغ، عربة)
y = df["label"]

# 2. تقسيم البيانات: 80% لتدريب الموديل، و 20% لاختبار ذكائه
# بنستخدم stratify=y عشان نتأكد إن نسبة (الأطفال للكبار للعربيات) متساوية في عينة التدريب والاختبار
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

# ==============================================================
# --- الموديل الأول: Random Forest (الغابة العشوائية) ---
# ==============================================================
# خوارزمية سريعة جداً وفعالة في التصنيف، بتعتمد على بناء عدد كبير من "أشجار القرار"
rf = RandomForestClassifier(random_state=42)

# الـ GridSearchCV بيجرب كذا إعداد للموديل (زي عدد الأشجار وعمقها) عشان يختار "الأفضل" أوتوماتيكياً
rf_grid = GridSearchCV(rf, {"n_estimators": [100, 200], "max_depth": [5, 10, None]}, cv=5, n_jobs=-1)
rf_grid.fit(X_train, y_train)

# ==============================================================
# --- الموديل الثاني: SVM (Support Vector Machine) ---
# ==============================================================
# خوارزمية دقيقة بس بطيئة جداً لو الداتا كبيرة (لأنها بتستهلك وقت كبير O(n²))
SVM_MAX_SAMPLES = 5000
# لو الداتا أكبر من 5000، بناخد عينة صغيرة بس ندرب عليها الـ SVM عشان التدريب مياخدش ساعات
if len(X_train) > SVM_MAX_SAMPLES:
    X_svm, _, y_svm, _ = train_test_split(
        X_train, y_train, train_size=SVM_MAX_SAMPLES, stratify=y_train, random_state=42
    )
    print(f"SVM: يتدرب على {SVM_MAX_SAMPLES:,} عينة (من {len(X_train):,}) لتسريع التدريب")
else:
    X_svm, y_svm = X_train, y_train

# الـ Pipeline بيوحد المقاييس (Scaler) الأول، وبعدين يدخلها على الـ SVM
svm_pipe = Pipeline([("scaler", StandardScaler()), ("svc", SVC(kernel="rbf"))])
svm_grid = GridSearchCV(svm_pipe, {"svc__C": [1, 10], "svc__gamma": ["scale", "auto"]}, cv=3)
svm_grid.fit(X_svm, y_svm)

# 3. اختبار الموديلين وطباعة النتيجة:
for name, model in [("RandomForest", rf_grid.best_estimator_), ("SVM", svm_grid.best_estimator_)]:
    preds = model.predict(X_test)
    print(f"\n=== {name} ===")
    
    # بيطبع تقرير الدقة (Accuracy, F1-score) عشان الدكاترة
    print(classification_report(y_test, preds))
    
    # بنرسم مصفوفة الخطأ (Confusion Matrix) عشان نشوف الموديل اتلخبط بين إيه وإيه
    classes = model.classes_ if hasattr(model, "classes_") else model[-1].classes_
    cm = confusion_matrix(y_test, preds, labels=classes)
    sns.heatmap(cm, annot=True, fmt="d", xticklabels=classes, yticklabels=classes)
    plt.title(f"Confusion Matrix - {name}")
    plt.tight_layout()
    plt.savefig(f"confusion_matrix_{name}.png")
    plt.clf()

# 4. اختيار الأفضل: بنقارن دقة الموديلين، ونحفظ الموديل الأذكى عشان نستخدمه في السيرفر الحي
best_model = rf_grid.best_estimator_ if rf_grid.best_score_ >= svm_grid.best_score_ else svm_grid.best_estimator_
joblib.dump(best_model, "models/occupancy_classifier.joblib")
print("تم حفظ أفضل نموذج (غالباً الـ Random Forest بسبب تفوقه في البيانات اللي زي دي)")