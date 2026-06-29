"""Train value model from dataset CSV.

Usage:
    python experiments/web/train_value_model.py experiments/web/value_dataset.csv
"""
import csv
import json
import os
import pickle
import sys

def load_dataset(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def train(dataset_path, model_dir="experiments/agents/raging_bolt"):
    rows = load_dataset(dataset_path)
    if len(rows) < 20:
        print("WARNING: only %d rows, model may be unreliable" % len(rows))
        if len(rows) < 5:
            print("ERROR: too few rows to train")
            return None

    label_col = "result_win"
    skip_cols = {"result_win", "final_turn", "final_prize_diff", "turn",
                 "my_active_id", "opp_active_id"}

    feature_names = [k for k in rows[0].keys() if k not in skip_cols]
    X = []
    y = []
    for row in rows:
        x = []
        for k in feature_names:
            try:
                x.append(float(row[k]))
            except (ValueError, KeyError):
                x.append(0.0)
        X.append(x)
        y.append(float(row[label_col]))

    try:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score, roc_auc_score, log_loss
    except ImportError:
        print("ERROR: sklearn not installed. pip install scikit-learn")
        return None

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = GradientBoostingClassifier(
        n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]
    acc = accuracy_score(y_test, y_pred)
    try:
        auc = roc_auc_score(y_test, y_proba)
    except ValueError:
        auc = 0.0
    ll = log_loss(y_test, y_proba)

    win_avg = sum(p for p, t in zip(y_proba, y_test) if t == 1) / max(1, sum(1 for t in y_test if t == 1))
    loss_avg = sum(p for p, t in zip(y_proba, y_test) if t == 0) / max(1, sum(1 for t in y_test if t == 0))

    importances = sorted(zip(feature_names, model.feature_importances_),
                          key=lambda x: -x[1])

    print("=== Model Performance ===")
    print("Train: %d, Test: %d" % (len(X_train), len(X_test)))
    print("Accuracy: %.3f" % acc)
    print("ROC AUC: %.3f" % auc)
    print("Log Loss: %.3f" % ll)
    print("Win avg pred: %.3f" % win_avg)
    print("Loss avg pred: %.3f" % loss_avg)
    print("\nTop features:")
    for name, imp in importances[:10]:
        print("  %-30s %.4f" % (name, imp))

    model_path = os.path.join(model_dir, "value_model.pkl")
    meta_path = os.path.join(model_dir, "value_model_meta.json")

    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    meta = {
        "feature_names": feature_names,
        "accuracy": round(acc, 4),
        "roc_auc": round(auc, 4),
        "log_loss": round(ll, 4),
        "win_avg_pred": round(win_avg, 4),
        "loss_avg_pred": round(loss_avg, 4),
        "train_size": len(X_train),
        "test_size": len(X_test),
        "top_features": [(n, round(i, 4)) for n, i in importances[:15]],
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print("\nSaved: %s, %s" % (model_path, meta_path))
    return model_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python train_value_model.py <dataset.csv>")
        sys.exit(1)
    train(sys.argv[1])


if __name__ == "__main__":
    main()
