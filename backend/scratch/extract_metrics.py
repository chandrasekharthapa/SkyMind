
import pickle
import os

MODEL_PATH = "backend/ml/models/global_model.pkl"

if os.path.exists(MODEL_PATH):
    with open(MODEL_PATH, "rb") as f:
        data = pickle.load(f)
        metrics = data.get("metrics", {})
        print("METRICS_START")
        for k, v in metrics.items():
            print(f"{k}: {v}")
        print("METRICS_END")
else:
    print("Model not found")
