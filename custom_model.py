from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import os
import numpy as np

# --- การตั้งค่า ---
MODEL_PATH = os.path.join(os.path.dirname(__file__), "Tune", "my-awesome-multilingual-emotion-model-final")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print(f"Initializing custom model from '{MODEL_PATH}' on device '{DEVICE}'...")

try:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH).to(DEVICE)
    print("✅ Custom model loaded successfully!")
except Exception as e:
    print(f"❌ Error loading custom model: {e}")
    tokenizer = None
    model = None

def predict_moods(lyrics: str) -> dict:
    """
    (เวอร์ชันใหม่ - The Conductor)
    วิเคราะห์อารมณ์จากเนื้อเพลงและคืนค่าเป็น "Emotional Fingerprint"
    (Dictionary ที่มีครบทุกอารมณ์พร้อมค่าความน่าจะเป็น)
    """
    if not model or not tokenizer or not lyrics:
        # คืนค่า Fingerprint ว่างเปล่าถ้าไม่มีข้อมูล
        return {label: 0.0 for label in model.config.id2label.values()}

    # 1. Tokenize เนื้อเพลง
    inputs = tokenizer(lyrics, return_tensors="pt", truncation=True, padding=True, max_length=512).to(DEVICE)

    # 2. ทำการทายผล
    with torch.no_grad():
        logits = model(**inputs).logits

    # 3. แปลงผลลัพธ์ (logits) เป็นความน่าจะเป็น (probabilities)
    # ใช้ Sigmoid function เพราะเป็นงาน Multi-label classification
    sigmoid = torch.nn.Sigmoid()
    probabilities = sigmoid(logits).squeeze().cpu().numpy()
    
    # 4. สร้าง "Emotional Fingerprint" (Dictionary)
    # โดยจับคู่ชื่ออารมณ์กับค่าความน่าจะเป็นของมัน
    emotional_fingerprint = {model.config.id2label[i]: float(prob) for i, prob in enumerate(probabilities)}
            
    return emotional_fingerprint