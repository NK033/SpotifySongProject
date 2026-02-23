# run_finetune.py (Final Corrected Version)
import torch
from datasets import load_dataset, concatenate_datasets
from transformers import AutoTokenizer, AutoModelForSequenceClassification, TrainingArguments, Trainer
import ast
import numpy as np
import os
import random

# --- คำแนะนำสำคัญก่อนรัน ---
# ก่อนรันไฟล์นี้ ให้เปิด Terminal และตั้งค่า Timeout สำหรับการดาวน์โหลดก่อน
# สำหรับ Windows (Command Prompt): set HF_HUB_DOWNLOAD_TIMEOUT=120
# สำหรับ Windows (PowerShell):   $env:HF_HUB_DOWNLOAD_TIMEOUT=120
# -----------------------------

def check_environment():
    """ตรวจสอบความพร้อมของ GPU และ PyTorch"""
    print("--- Environment Check ---")
    if torch.cuda.is_available():
        print(f"✅ GPU is available: {torch.cuda.get_device_name(0)}")
    else:
        print("❌ WARNING: GPU not available. Training will run on CPU and will be very slow.")
    print("-" * 25)

def run_finetune():
    """
    กระบวนการทั้งหมดตั้งแต่โหลดข้อมูลไปจนถึงการ Fine-tuning โมเดลเวอร์ชันอัปเกรด
    """
    # === 1. โหลดข้อมูลจากทุกแหล่ง ===
    print("\n--- 1. Loading ALL Datasets ---")
    print("Loading Original Lyrics Dataset...")
    lyrics_dataset_full = load_dataset("manoh2f2/tsterbak-lyrics-dataset-with-emotions")
    
    print("Loading Multilingual GoEmotions Dataset...")
    go_emotions_dataset = load_dataset("AnasAlokla/multilingual_go_emotions")

    lyrics_dataset_split = lyrics_dataset_full['train'].train_test_split(test_size=0.1)
    print("✅ Lyrics dataset manually split into train and test sets.")

    # === 2. โหลด Tokenizer ===
    print("\n--- 2. Loading Tokenizer ---")
    model_name = "xlm-roberta-base"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    
    # === 3. สร้าง Master Label Set โดยกำหนดค่าโดยตรง ===
    print("\n--- 3. Preparing Master Labels ---")
    master_labels = [
        'admiration', 'amusement', 'anger', 'annoyance', 'approval', 'caring', 
        'confusion', 'curiosity', 'desire', 'disappointment', 'disapproval', 
        'disgust', 'embarrassment', 'excitement', 'fear', 'gratitude', 'grief', 
        'joy', 'love', 'nervousness', 'optimism', 'pride', 'realization', 
        'relief', 'remorse', 'sadness', 'surprise', 'neutral'
    ]
    
    label2id = {label: i for i, label in enumerate(master_labels)}
    id2label = {i: label for i, label in enumerate(master_labels)}
    num_labels = len(master_labels)
    
    print(f"✅ Master labels created with {num_labels} unique emotions.")

    # === 4. สร้าง Preprocessing Functions สำหรับแต่ละ Dataset ===
    print("\n--- 4. Creating Preprocessing Functions ---")

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
                except:
                    pass
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
            except (ValueError, SyntaxError):
                pass
            final_labels.append(label_vector)
            
        tokenized_inputs["labels"] = final_labels
        return tokenized_inputs
        
    def log_random_examples(dataset, name, num_examples=3):
        print(f"\n--[{name} Examples]--")
        indices = random.sample(range(len(dataset)), num_examples)
        
        for i, idx in enumerate(indices):
            example = dataset[idx]
            input_ids = example['input_ids']
            label_vector = example['labels']
            
            decoded_text = tokenizer.decode(input_ids, skip_special_tokens=True)
            active_emotions = [id2label[j] for j, value in enumerate(label_vector) if value == 1.0]
            
            print(f"\n[Example {i+1}]")
            print(f"  Decoded Text: {decoded_text[:200]}...")
            print(f"  Emotion Vector: {np.array(label_vector, dtype=int)}")
            print(f"  Mapped Emotions: {active_emotions}")

    # === 5. ทำการ Preprocess และรวม Dataset ===
    print("\n--- 5. Processing and Merging Datasets ---")
    
    print("Processing original lyrics dataset...")
    processed_lyrics_dataset = lyrics_dataset_split.map(
        preprocess_lyrics_dataset, 
        batched=True, 
        remove_columns=lyrics_dataset_split['train'].column_names
    )

    print("Processing multilingual go_emotions dataset...")
    processed_goemotions_dataset = go_emotions_dataset.map(
        preprocess_goemotions_dataset, 
        batched=True, 
        remove_columns=go_emotions_dataset['train'].column_names
    )
    
    print("\n--- 🧐 LOG 1: Inspecting PRE-MERGE Data 🧐 ---")
    log_random_examples(processed_lyrics_dataset['train'], "Lyrics Dataset (Train)")
    log_random_examples(processed_goemotions_dataset['train'], "GoEmotions Dataset (Train)")

    print("\nCombining all datasets...")
    final_train_dataset = concatenate_datasets([
        processed_lyrics_dataset['train'], 
        processed_goemotions_dataset['train']
    ]).shuffle(seed=42)

    final_test_dataset = concatenate_datasets([
        processed_lyrics_dataset['test'],
        processed_goemotions_dataset['test']
    ]).shuffle(seed=42)

    print(f"✅ Datasets merged! Total training examples: {len(final_train_dataset)}, Total testing examples: {len(final_test_dataset)}")
    
    print("\n--- 🧐 LOG 2: Inspecting POST-MERGE Data 🧐 ---")
    log_random_examples(final_train_dataset, "Final Merged Dataset (Train)")

    # === 6. โหลด Model พร้อม Master Labels Config ===
    print("\n--- 6. Loading the Pre-trained Model with New Config ---")
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, 
        problem_type="multi_label_classification",
        num_labels=num_labels,
        id2label=id2label,
        label2id=label2id,
    )
    print(f"✅ Model '{model_name}' loaded successfully!")

    # === 7. กำหนด Training Arguments ที่ดีขึ้น ===
    print("\n--- 7. Defining Upgraded Training Arguments ---")
    model_output_dir = "my-awesome-multilingual-emotion-model-final"

    args = TrainingArguments(
        output_dir=model_output_dir,
        learning_rate=2e-5,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        gradient_accumulation_steps=2,
        fp16=True if torch.cuda.is_available() else False,
        num_train_epochs=3,
        weight_decay=0.01,
        eval_strategy="steps", # <-- (HOTFIX) แก้ไขกลับเป็นชื่อที่ถูกต้อง
        eval_steps=1000,
        save_strategy="steps",
        save_steps=1000,
        load_best_model_at_end=True,
        push_to_hub=False,
    )
    print("✅ Training arguments defined.")

    # === 8. สร้าง Trainer ด้วยข้อมูลชุดใหม่ ===
    print("\n--- 8. Initializing Trainer with Merged Datasets ---")
    trainer = Trainer(
        model,
        args,
        train_dataset=final_train_dataset,
        eval_dataset=final_test_dataset,
        tokenizer=tokenizer,
    )
    print("✅ Trainer initialized. Ready for robust fine-tuning!")
    
    # === 9. เริ่มการ Fine-tuning! ===
    print("\n--- 9. Starting Fine-Tuning ---")
    print("This will take significantly longer due to more data. This is a good time for a break! ☕🎬")
    trainer.train()

    print("\n🎉🎉🎉 Fine-tuning complete! You've built a more powerful and versatile model! 🎉🎉🎉")
    
    # === 10. บันทึกโมเดลสุดท้าย ===
    print("\n--- 10. Saving the final model ---")
    trainer.save_model(model_output_dir)
    print(f"Model saved to '{model_output_dir}'")

if __name__ == "__main__":
    check_environment()
    run_finetune()