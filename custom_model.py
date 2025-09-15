# custom_model.py
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import os

# --- การตั้งค่า ---
# ระบุตำแหน่งของโมเดลที่เราเทรนเสร็จแล้ว
MODEL_PATH = os.path.join(os.path.dirname(__file__), "Tune", "my-awesome-lyrics-emotion-model")
# ...
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print(f"Initializing custom model from '{MODEL_PATH}' on device '{DEVICE}'...")

# --- โหลด Tokenizer และ Model ที่ผ่านการ Fine-tune ---
# เราโหลดแค่ครั้งเดียวตอนเริ่มต้น เพื่อให้พร้อมใช้งานตลอดเวลา
try:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH).to(DEVICE)
    print("✅ Custom model loaded successfully!")
except Exception as e:
    print(f"❌ Error loading custom model: {e}")
    tokenizer = None
    model = None

def predict_moods(lyrics: str):
    """
    วิเคราะห์อารมณ์จากเนื้อเพลงโดยใช้โมเดลที่เรา Fine-tune เอง
    """
    if not model or not tokenizer:
        return []

    # 1. Tokenize เนื้อเพลง
    inputs = tokenizer(lyrics, return_tensors="pt", truncation=True, padding=True, max_length=512).to(DEVICE)

    # 2. ทำการทายผล
    with torch.no_grad():
        logits = model(**inputs).logits

    # 3. แปลงผลลัพธ์เป็นความน่าจะเป็น และเลือก Label ที่มีความมั่นใจสูง
    probabilities = torch.sigmoid(logits).squeeze().cpu().numpy()
    threshold = 0.5 # กำหนดเกณฑ์ความมั่นใจ
    
    moods = []
    for i, prob in enumerate(probabilities):
        if prob > threshold:
            moods.append(model.config.id2label[i])
            
    return moods