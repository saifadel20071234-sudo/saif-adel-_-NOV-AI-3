import pandas as pd, joblib
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.metrics import classification_report, confusion_matrix
import matplotlib.pyplot as plt
import seaborn as sns

df = pd.read_parquet("features_rssi_labeled.parquet")
X = df[["mean", "std", "min", "max", "range", "mean_abs_diff"]]
y = df["label"]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

# --- Random Forest (على كامل البيانات) ---
rf = RandomForestClassifier(random_state=42)
rf_grid = GridSearchCV(rf, {"n_estimators": [100, 200], "max_depth": [5, 10, None]}, cv=5, n_jobs=-1)
rf_grid.fit(X_train, y_train)

# --- SVM: يشتغل على sample صغير لأنه O(n²) ومش بيتناسب مع datasets كبيرة ---
SVM_MAX_SAMPLES = 5000
if len(X_train) > SVM_MAX_SAMPLES:
    X_svm, _, y_svm, _ = train_test_split(
        X_train, y_train, train_size=SVM_MAX_SAMPLES, stratify=y_train, random_state=42
    )
    print(f"SVM: يتدرب على {SVM_MAX_SAMPLES:,} عينة (من {len(X_train):,}) لتسريع التدريب")
else:
    X_svm, y_svm = X_train, y_train

svm_pipe = Pipeline([("scaler", StandardScaler()), ("svc", SVC(kernel="rbf"))])
svm_grid = GridSearchCV(svm_pipe, {"svc__C": [1, 10], "svc__gamma": ["scale", "auto"]}, cv=3)
svm_grid.fit(X_svm, y_svm)

for name, model in [("RandomForest", rf_grid.best_estimator_), ("SVM", svm_grid.best_estimator_)]:
    preds = model.predict(X_test)
    print(f"\n=== {name} ===")
    print(classification_report(y_test, preds))
    # استخراج classes_ بشكل صحيح من داخل الـ Pipeline لو موجود
    classes = model.classes_ if hasattr(model, "classes_") else model[-1].classes_
    cm = confusion_matrix(y_test, preds, labels=classes)
    sns.heatmap(cm, annot=True, fmt="d", xticklabels=classes, yticklabels=classes)
    plt.title(f"Confusion Matrix - {name}")
    plt.tight_layout()
    plt.savefig(f"confusion_matrix_{name}.png")
    plt.clf()

best_model = rf_grid.best_estimator_ if rf_grid.best_score_ >= svm_grid.best_score_ else svm_grid.best_estimator_
joblib.dump(best_model, "models/occupancy_classifier.joblib")
print("تم حفظ أفضل نموذج")