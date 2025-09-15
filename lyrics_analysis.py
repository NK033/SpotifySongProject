# lyrics_analysis.py
from transformers import pipeline

# --- MODIFIED ---
# โหลดโมเดลสำหรับ Summarization และ Sentiment Analysis
# ใช้โมเดล multilingual เพื่อให้รองรับเนื้อเพลงภาษาไทยได้ดีขึ้น
print("กำลังโหลดโมเดล BERT สำหรับวิเคราะห์เนื้อเพลง...")
summarizer = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6")
sentiment_analyzer = pipeline("sentiment-analysis", model="cardiffnlp/twitter-xlm-roberta-base-sentiment")

print("โหลดโมเดล BERT เรียบร้อยแล้ว")

def analyze_lyrics(lyrics: str) -> dict:
    """
    วิเคราะห์เนื้อเพลงด้วยโมเดล BERT
    - สรุปเนื้อเพลง (Summarization)
    - วิเคราะห์อารมณ์ (Sentiment Analysis)
    """
    if not lyrics:
        return {"summary": "ไม่พบเนื้อเพลง", "sentiment": "ไม่สามารถวิเคราะห์ได้"}

    # --- ADDED: Sentiment Analysis ---
    # วิเคราะห์อารมณ์จากเนื้อเพลง (จำกัดความยาวเพื่อประสิทธิภาพ)
    try:
        sentiment_result = sentiment_analyzer(lyrics[:512]) # โมเดลส่วนใหญ่มี giới hạn token ที่ 512
        sentiment = sentiment_result[0]['label'].capitalize()
    except Exception as e:
        print(f"Error during sentiment analysis: {e}")
        sentiment = "ไม่สามารถวิเคราะห์ได้"

    # --- MODIFIED: Summarization ---
    summary_text = "เนื้อเพลงสั้นเกินไปสำหรับการสรุป"
    if len(lyrics.split()) > 50:
        try:
            # จำกัดความยาวของเนื้อเพลงเพื่อป้องกัน token limit
            text_to_summarize = lyrics[:2000]
            summary = summarizer(text_to_summarize, max_length=150, min_length=50, do_sample=False)
            summary_text = summary[0]['summary_text']
        except Exception as e:
            print(f"Error during summarization: {e}")
            summary_text = "เกิดข้อผิดพลาดในการสรุปเนื้อเพลง"
            
    # --- MODIFIED: Return both results ---
    return {
        "summary": summary_text,
        "sentiment": sentiment
    }