import asyncio
import sys
import json
import re

# Import modules จากโปรเจกต์ของคุณ
from config import Config
from groq_ai import groq_client, FAST_MODEL, rescue_lyrics_with_groq, get_emotional_profile_from_groq
from custom_model import predict_moods

# ==========================================
# 🛠️ Helper Functions
# ==========================================
async def classify_intent(user_message: str) -> str:
    """จำลอง Logic การจำแนกเจตนา (Intent Classification)"""
    try:
        completion = await groq_client.chat.completions.create(
            model=FAST_MODEL,
            messages=[{"role": "user", "content": f"Classify intent (get_recommendations, get_top_charts, use_a_tool, chat) for: '{user_message}'. Reply ONLY the intent."}],
            max_tokens=10, temperature=0.0
        )
        return completion.choices[0].message.content.strip()
    except: return "chat"

# ==========================================
# 🧪 TEST 4.2.2: Complex Query Analysis
# ==========================================
async def test_complex_query():
    print("\n" + "="*50)
    print("🧪 TEST 4.2.2: Complex Query Analysis (Vector Generation)")
    print("="*50)
    
    query = "ขอเพลงร็อคหนักๆ เอาไว้ฟังตอนออกกำลังกาย"
    print(f"🔹 Analyzing Complex Input: '{query}'")
    
    # เรียกใช้ฟังก์ชันแปลงข้อความ -> Vector
    profile = await get_emotional_profile_from_groq(query)
    
    if profile:
        print(f"   -> Generated Emotional Profile (Vector):")
        print(f"      {profile}")
        
        # ตรวจสอบว่ามีค่า excitement สูงตามคาดหรือไม่
        if profile.get('excitement', 0) > 0.5:
            print("   -> Result: ✅ PASS (Successfully captured high excitement)")
        else:
            print("   -> Result: ⚠️ WARNING (Excitement value is low)")
    else:
        print("   -> Result: ❌ FAILED (No vector generated)")

# ==========================================
# 🧪 TEST 4.2.3: Distinct Emotion Classification
# ==========================================
def test_lyric_emotion():
    print("\n" + "="*50)
    print("🧪 TEST 4.2.3: Distinct Emotion Classification (Lyrics Analysis)")
    print("="*50)
    
    # ชุดข้อมูลทดสอบ 5 อารมณ์หลัก (รวมถึง Ring of Fortune ท่อน Chorus)
    lyrics_samples = [
        # 1. JOY
        ("Pharrell Williams - Happy", 
         "Clap along if you feel like a room without a roof, because I'm happy"),
        
        # 2. ANGER
        ("Linkin Park - One Step Closer", 
         "Shut up when I'm talking to you! Shut up! I'm about to break!"),
        
        # 3. LOVE
        ("Nont Tanont - โต๊ะริม (Melt)", 
         "เธอยิ้มทีเล่นเอาโลกทั้งใบหยุดหมุนไปชั่วขณะ หัวใจฉันเต้นแรงจนแทบระเบิด"),
        
        # 4. OPTIMISM
        ("Bodyslam - แสงสุดท้าย", 
         "จะไม่ยอมแพ้พ่าย แม้ต้องเจ็บเจียนตาย จะข้ามไปให้ถึงแสงสุดท้ายด้วยศรัทธา"),
        
        # 5. NOSTALGIA (ท่อนฮุค)
        ("Eri Sasaki - Ring of Fortune (Plastic Memories ED)", 
         "光を集めて 夜空の彼方へ サヨナラの想い出を 瞳にたたえて (Gathering light... memories of goodbye) 君のことをずっと探してる (Searching for you all along)")
    ]
    
    for artist_track, lyrics in lyrics_samples:
        print(f"\n🎵 Song: {artist_track}")
        
        # เรียก Model จริง (XLM-R)
        result_moods = predict_moods(lyrics)
        
        # เรียงลำดับและแสดงผล
        sorted_moods = sorted(result_moods.items(), key=lambda x: x[1], reverse=True)
        top_mood = sorted_moods[0]
        second_mood = sorted_moods[1]
        
        print(f"   -> Top Mood:   '{top_mood[0]}' ({top_mood[1]:.4f})")
        print(f"   -> Second Mood: '{second_mood[0]}' ({second_mood[1]:.4f})")

# ==========================================
# 🧪 TEST 4.2.4: Rescue Mode & Normalization Pipeline
# ==========================================
async def test_rescue_pipeline():
    print("\n" + "="*50)
    print("🧪 TEST 4.2.4: Rescue Mode & Normalization Pipeline")
    print("="*50)
    
    # ใช้เพลงญี่ปุ่นทดสอบระบบ (สมมติว่าไม่มีใน DB)
    track_name = '君の知らない物語'
    artist_name = 'Supercell'
    fake_tracks = [{'name': track_name, 'artists': [{'name': artist_name}]}]
    
    print(f"🔹 Attempting to rescue lyrics for: {track_name} by {artist_name}")
    
    # 1. เรียกใช้ฟังก์ชันกู้คืน (ต้องผ่าน _clean_lyrics ข้างในมาแล้ว)
    rescued_data = await rescue_lyrics_with_groq(fake_tracks)
    
    if rescued_data:
        print("   -> ✅ Rescue Successful!")
        
        # ดึงเนื้อเพลงออกมา
        lyrics_text = list(rescued_data.values())[0]
        
        # 2. ตรวจสอบคุณภาพการ Normalize (Cleaning Check)
        print(f"\n   [Normalization Verification]")
        print(f"   -> Snippet: {lyrics_text[:80]}...")
        
        # เช็คว่าไม่มีตัวอักษรขยะ (Newlines หรือ Tags)
        has_newline = "\n" in lyrics_text
        has_tags = "[" in lyrics_text or "]" in lyrics_text
        
        if not has_newline and not has_tags:
            print("   -> Status: ✅ PASS (Text is flatted & cleaned)")
        else:
            print(f"   -> Status: ⚠️ WARNING (Found artifacts: Newline={has_newline}, Tags={has_tags})")

        # 3. ตรวจสอบการนำไปใช้งานจริง (Usability Check)
        print(f"\n   [Model Usability Verification]")
        moods = predict_moods(lyrics_text)
        top_mood = max(moods, key=moods.get)
        confidence = moods[top_mood]
        
        print(f"   -> XLM-R Prediction: '{top_mood}' (Confidence: {confidence:.4f})")
        
        if confidence > 0.4:
             print("   -> Result: ✅ PIPELINE COMPLETE (Rescued lyrics are usable)")
        else:
             print("   -> Result: ⚠️ Low Confidence (Model might be unsure)")

    else:
        print("   -> ⚠️ Rescue returned empty (Search failed or API limit)")

# ==========================================
# 🧪 TEST 4.2.5: Cross-lingual Normalization
# ==========================================
async def test_normalization_process():
    print("\n" + "="*50)
    print("🧪 TEST 4.2.5: Cross-lingual Normalization")
    print("="*50)
    
    print(f"🎯 Goal: Verify that different languages map to similar Emotional Vectors.\n")
    
    # ตัดภาษาไทยออก เหลือแค่ Japanese vs English
    test_inputs = [
        ("Japanese", "彼氏と別れた。心が痛い。泣きたい。"),
        ("English", "I just broke up with my boyfriend. I feel terrible.")
    ]

    for lang, text in test_inputs:
        print(f"🔹 Input ({lang}): '{text}'")
        profile = await get_emotional_profile_from_groq(text)
        
        if profile:
            # เรียงลำดับเอาค่ามากสุด 3 อันดับแรก
            top_emotions = sorted(profile.items(), key=lambda x: x[1], reverse=True)[:3]
            print(f"   -> Normalized Vector: {top_emotions}")
        else:
            print("   -> ❌ Failed to normalize")
        print("-" * 30)
# ==========================================
# 🚀 MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    if not Config.GROQ_API_KEY:
        print("❌ Error: GROQ_API_KEY missing in Config")
        sys.exit(1)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Run all tests sequentially
        loop.run_until_complete(test_complex_query())       # 4.2.2
        
        test_lyric_emotion()                                # 4.2.3 (Sync function)
        
        loop.run_until_complete(test_rescue_pipeline())     # 4.2.4
        
        loop.run_until_complete(test_normalization_process()) # 4.2.5
        
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user.")
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
    finally:
        loop.close()
    
    print("\n✅ All Evaluations Complete.")