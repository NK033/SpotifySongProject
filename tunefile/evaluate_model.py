# evaluate_model.py
import torch
from datasets import load_dataset, concatenate_datasets
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments
import ast
import numpy as np
from sklearn.metrics import f1_score, roc_auc_score, accuracy_score
from transformers import EvalPrediction

def evaluate_model():
    """
    โหลดโมเดลที่ Fine-tune เสร็จแล้วและทำการประเมินผลกับ Test Set
    """
    # --- 1. กำหนดค่าพื้นฐาน ---
    print("\n--- 1. Setting up configuration ---")
    # ชี้ไปยังโฟลเดอร์ที่เก็บโมเดลที่เทรนเสร็จแล้ว
    model_path = "my-awesome-multilingual-emotion-model-final" 
    tokenizer_name = "xlm-roberta-base"
    
    # === 2. โหลด Tokenizer และ Model ที่เทรนเสร็จแล้ว ===
    print(f"\n--- 2. Loading fine-tuned model from '{model_path}' ---")
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_path)
    
    # === 3. เตรียม Master Labels (ต้องเหมือนกับตอนที่เทรน) ===
    print("\n--- 3. Preparing Master Labels ---")
    master_labels = [
        'admiration', 'amusement', 'anger', 'annoyance', 'approval', 'caring', 
        'confusion', 'curiosity', 'desire', 'disappointment', 'disapproval', 
        'disgust', 'embarrassment', 'excitement', 'fear', 'gratitude', 'grief', 
        'joy', 'love', 'nervousness', 'optimism', 'pride', 'realization', 
        'relief', 'remorse', 'sadness', 'surprise', 'neutral'
    ]
    label2id = {label: i for i, label in enumerate(master_labels)}
    num_labels = len(master_labels)
    
    # === 4. เตรียม Test Dataset (ใช้โค้ดเดิมเพื่อความถูกต้อง 100%) ===
    # เราต้องมั่นใจว่าข้อมูลทดสอบถูกเตรียมด้วยวิธีเดียวกับตอนที่เทรน
    print("\n--- 4. Preparing Test Datasets ---")
    lyrics_dataset_full = load_dataset("manoh2f2/tsterbak-lyrics-dataset-with-emotions")
    go_emotions_dataset = load_dataset("AnasAlokla/multilingual_go_emotions")
    lyrics_dataset_split = lyrics_dataset_full['train'].train_test_split(test_size=0.1, seed=42) # ใช้ seed เดิม

    def preprocess_lyrics_dataset(examples):
        cleaned_lyrics = [text.replace("_x000D_", "\n") if text is not None else "" for text in examples["seq"]]
        tokenized_inputs = tokenizer(cleaned_lyrics, truncation=True, padding="max_length", max_length=512)
        labels = []
        for emotions_str in examples["emotions"]:
            label_vector = np.zeros(num_labels, dtype=np.float32)
            if emotions_str:
                try:
                    emotions_list = ast.literal_eval(emotions_str)
                    for emotion in emotions_list:
                        if emotion in label2id:
                            label_vector[label2id[emotion]] = 1.0
                except: pass
            labels.append(label_vector)
        tokenized_inputs["labels"] = labels
        return tokenized_inputs

    def preprocess_goemotions_dataset(examples):
        cleaned_text = [text if text is not None else "" for text in examples["text"]]
        tokenized_inputs = tokenizer(cleaned_text, truncation=True, padding="max_length", max_length=512)
        final_labels = []
        for label_string in examples["labels"]:
            label_vector = np.zeros(num_labels, dtype=np.float32)
            try:
                label_indices = ast.literal_eval(label_string)
                for index in label_indices:
                    label_vector[index] = 1.0
            except (ValueError, SyntaxError): pass
            final_labels.append(label_vector)
        tokenized_inputs["labels"] = final_labels
        return tokenized_inputs

    processed_lyrics_test = lyrics_dataset_split['test'].map(preprocess_lyrics_dataset, batched=True, remove_columns=lyrics_dataset_split['test'].column_names)
    processed_goemotions_test = go_emotions_dataset['test'].map(preprocess_goemotions_dataset, batched=True, remove_columns=go_emotions_dataset['test'].column_names)
    
    final_test_dataset = concatenate_datasets([processed_lyrics_test, processed_goemotions_test])
    print(f"✅ Final test dataset ready with {len(final_test_dataset)} examples.")

    # === 5. สร้างฟังก์ชันสำหรับคำนวณ Metrics ===
    def compute_metrics(p: EvalPrediction):
        sigmoid = torch.nn.Sigmoid()
        probs = sigmoid(torch.Tensor(p.predictions))
        y_pred = np.zeros(p.label_ids.shape)
        y_pred[np.where(probs > 0.5)] = 1
        
        f1_micro_average = f1_score(y_true=p.label_ids, y_pred=y_pred, average='micro')
        roc_auc = roc_auc_score(y_true=p.label_ids, y_score=y_pred, average='micro')
        accuracy = accuracy_score(y_true=p.label_ids, y_pred=y_pred)
        
        metrics = {'f1': f1_micro_average, 'roc_auc': roc_auc, 'accuracy': accuracy}
        return metrics

    # === 6. สร้าง Trainer เฉพาะกิจสำหรับการ Evaluate ===
    print("\n--- 5. Initializing Trainer for evaluation ---")
    # เรายังต้องใช้ TrainingArguments แต่ไม่ต้องตั้งค่าอะไรเกี่ยวกับการเทรนเลย
    args = TrainingArguments(
        output_dir="temp_eval_results", # สร้างโฟลเดอร์ชั่วคราว
        per_device_eval_batch_size=32, # เพิ่ม batch size ตอน evaluate เพื่อให้เร็วขึ้นได้
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=args,
        eval_dataset=final_test_dataset,
        tokenizer=tokenizer,
        compute_metrics=compute_metrics
    )
    print("✅ Trainer initialized.")

    # === 7. เริ่มการประเมินผล! ===
    print("\n--- 6. Running Final Evaluation ---")
    eval_results = trainer.evaluate()
    
    print("\n\n==============================================")
    print("          Final Model Evaluation          ")
    print("==============================================")
    for key, value in eval_results.items():
        print(f"{key.replace('_', ' ').title():<25}: {value:.4f}")
    print("==============================================")


if __name__ == "__main__":
    evaluate_model()