# train_similarity_model.py
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
import joblib
import os

ARTIFACTS_DIR = os.path.join("archive", "ml_artifacts")
DATASET_PATH = os.path.join(ARTIFACTS_DIR, "hybrid_features_dataset.csv")
MODEL_PATH = os.path.join(ARTIFACTS_DIR, "similarity_model.joblib")
SCALER_PATH = os.path.join(ARTIFACTS_DIR, "scaler.joblib")
DATASET_DF_PATH = os.path.join(ARTIFACTS_DIR, "processed_dataset.joblib")

def train_model():
    """
    เทรนโมเดล NearestNeighbors จาก Dataset ที่เราสร้างขึ้น
    """
    print("--- 🧠 Starting Model Training ---")
    if not os.path.exists(DATASET_PATH):
        print(f"!!! ERROR: Dataset not found at {DATASET_PATH}. Please run update_model.py first.")
        return

    # 1. โหลดข้อมูล
    print(f"Loading dataset from {DATASET_PATH}...")
    df = pd.read_csv(DATASET_PATH)
    
    # 2. เลือกเฉพาะคอลัมน์ที่เป็น Feature ตัวเลข
    feature_cols = df.select_dtypes(include=np.number).columns.tolist()
    # เอาคอลัมน์ที่ไม่ใช่ Feature ออก
    feature_cols.remove('popularity') 
    feature_cols.remove('duration_ms')
    
    print(f"Using {len(feature_cols)} features for training.")
    X = df[feature_cols].fillna(0) # เติมค่าว่างด้วย 0

    # 3. ทำ Feature Scaling (สำคัญมากสำหรับ KNN)
    print("Applying StandardScaler to features...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 4. สร้างและเทรนโมเดล
    print("Training NearestNeighbors model (k=10)...")
    # เราจะหาเพลงที่คล้ายที่สุด 10 อันดับ
    model = NearestNeighbors(n_neighbors=10, algorithm='brute', metric='cosine')
    model.fit(X_scaled)

    # 5. บันทึกโมเดล, Scaler, และ DataFrame
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    joblib.dump(df, DATASET_DF_PATH) # บันทึก DataFrame ทั้งหมดไว้ใช้ตอนแนะนำเพลง
    
    print(f"✅ Model saved to {MODEL_PATH}")
    print(f"✅ Scaler saved to {SCALER_PATH}")
    print(f"✅ Processed DataFrame saved to {DATASET_DF_PATH}")
    print("--- Training Complete! ---")

if __name__ == "__main__":
    import numpy as np
    train_model()