# gemini_ai.py
import google.generativeai as genai
import json
from fastapi import HTTPException, status
import asyncio
import spotipy
from config import Config
from database import save_song_analysis_to_db, get_song_analysis_from_db
from genius_api import get_lyrics
from custom_model import predict_moods

# ตั้งค่า Gemini API


async def analyze_and_store_song_analysis(spotify_track_data: dict) -> dict:
    """
    (เวอร์ชันใหม่) วิเคราะห์ข้อมูลเพลงด้วย Gemini โดยใช้ข้อมูลอารมณ์จากโมเดลที่เรา Fine-tune
    """
    print(f"Analyzing '{spotify_track_data.get('name')}' with Gemini, powered by our custom model...")
    
    artist_name = spotify_track_data.get('artists', [{}])[0].get('name', 'N/A')
    song_title = spotify_track_data.get('name', 'N/A')
    
    # --- (เปลี่ยนแปลง) วิเคราะห์อารมณ์ด้วยโมเดลของเรา ---
    # 1. ดึงเนื้อเพลง
    lyrics = await get_lyrics(artist_name, song_title)
    
    # 2. ให้โมเดลผู้เชี่ยวชาญของเราวิเคราะห์
    predicted_moods = []
    if lyrics:
        predicted_moods = predict_moods(lyrics) # ['sadness', 'love', 'remorse']
    
    # แปลง List ของอารมณ์ให้เป็น String ที่อ่านง่ายสำหรับ Prompt
    moods_text = ", ".join(predicted_moods) if predicted_moods else "ไม่สามารถระบุได้"
    
    # --- (เปลี่ยนแปลง) อัปเกรด Prompt ให้ใช้ข้อมูลจากโมเดลของเรา ---
    prompt_content = f"""
    คุณเป็นนักวิเคราะห์ดนตรีมืออาชีพ โปรดวิเคราะห์เพลงต่อไปนี้อย่างละเอียดและให้ข้อมูลเชิงลึก
    ชื่อเพลง: {song_title}
    ศิลปิน: {artist_name}

    นี่คือข้อมูลสำคัญที่ได้จากการวิเคราะห์เนื้อเพลงด้วยโมเดล AI เฉพาะทางของเรา:
    - **อารมณ์หลักที่ตรวจพบ (Main Emotions): {moods_text}**

    จากข้อมูลข้างต้น โปรดวิเคราะห์เพลงนี้ให้ครอบคลุมหัวข้อต่อไปนี้:
    1.  **แนวเพลง (Genre):** ระบุแนวเพลงหลักและแนวเพลงย่อย
    2.  **อารมณ์และบรรยากาศ (Mood & Vibe):** อธิบายว่าเพลงนี้ให้อารมณ์แบบใด โดยอ้างอิงจาก "อารมณ์หลักที่ตรวจพบ" ข้างต้น
    3.  **การวิเคราะห์เนื้อเพลง (Lyrical Analysis):** อธิบายความหมายโดยรวมของเนื้อเพลง และความสัมพันธ์กับอารมณ์ที่ตรวจพบ
    4.  **เครื่องดนตรี (Instrumentation):** ระบุเครื่องดนตรีที่โดดเด่น
    
    โปรดตอบกลับเป็นภาษาไทยเท่านั้น และจัดรูปแบบให้อ่านง่าย
    """
    
    # 3. ให้ Gemini วิเคราะห์และเขียนบทวิจารณ์
    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction="คุณคือผู้ช่วยและนักวิจารณ์ดนตรีที่เชี่ยวชาญ สามารถวิเคราะห์เพลงได้อย่างแม่นยำและเขียนอธิบายได้อย่างเป็นธรรมชาติ"
    )
    
    try:
        response = model.generate_content(prompt_content)
        analysis_text = response.text
        
        # สร้างโครงสร้างข้อมูลที่จะบันทึกลง Database
        # เราจะเปลี่ยน lyrical_analysis เป็น predicted_moods เพื่อให้สื่อความหมายตรงตัว
        combined_analysis = {
            "gemini_analysis": analysis_text,
            "predicted_moods": predicted_moods # บันทึกผลจากโมเดลของเราโดยตรง
        }
        
        await save_song_analysis_to_db(spotify_track_data, combined_analysis)
        
        return combined_analysis

    except Exception as e:
        print(f"Error calling Gemini API for song analysis: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error analyzing song with Gemini API.")

async def get_song_analysis_details(sp_client: spotipy.Spotify, song_uri: str) -> dict:
    """
    ดึงข้อมูลการวิเคราะห์เพลงจาก DB หรือวิเคราะห์ใหม่ถ้ายังไม่มี
    """
    analysis_data = await get_song_analysis_from_db(song_uri)
    if analysis_data:
        return analysis_data
        
    from spotify_api import get_spotify_track_data
    
    try:
        # เราต้องส่ง sp_client เข้าไปในฟังก์ชันด้วย
        spotify_track_data = await get_spotify_track_data(sp_client, song_uri)
        return await analyze_and_store_song_analysis(spotify_track_data)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get song details: {e}")

async def summarize_playlist(user_spotify_access_token: str, song_uris: list[str]) -> str:
    """
    ให้ Gemini สรุปภาพรวมของ Playlist จากข้อมูลการวิเคราะห์เพลง
    """
    if not user_spotify_access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Spotify access token is required for summarizing playlist.")

    all_song_analyses = []
    for uri in song_uris:
        try:
            analysis = await get_song_analysis_details(user_spotify_access_token, uri)
            all_song_analyses.append(analysis)
        except HTTPException as e:
            print(f"Warning: Could not get analysis for URI {uri}: {e.detail}")

    if not all_song_analyses:
        return "ไม่สามารถสรุปเพลย์ลิสต์ได้ในขณะนี้"

    # สร้าง prompt สำหรับสรุปเพลย์ลิสต์
    prompt = "โปรดสรุปภาพรวมของเพลย์ลิสต์นี้จากข้อมูลการวิเคราะห์เพลงต่อไปนี้:\n\n"
    for i, analysis in enumerate(all_song_analyses):
        prompt += f"--- เพลงที่ {i+1}: ---\n"
        # ใช้เฉพาะการวิเคราะห์ของ Gemini เพื่อการสรุปภาพรวมของเพลย์ลิสต์
        prompt += analysis.get('gemini_analysis', 'ไม่มีข้อมูลการวิเคราะห์') + "\n\n"
    prompt += "โปรดสรุปเป็นภาษาไทยอย่างละเอียด โดยเน้นแนวเพลง อารมณ์ เครื่องดนตรี และลักษณะเด่นของเพลย์ลิสต์นี้โดยรวม"

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction="คุณคือผู้ช่วยที่เชี่ยวชาญด้านดนตรีไทยและสากล"
    )

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error calling Gemini API for playlist summary: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error summarizing playlist.")

async def get_gemini_seed_expansion(top_tracks: list[dict]) -> list[dict]:
    """
    (V3) ให้ Gemini วิเคราะห์ "ภาษา" และ "แนวเพลง" และบังคับให้ยึดตามนั้น
    """
    print("--- Executing Plan B: Gemini-Powered Seed Expansion (V3 - Strict Prompt) ---")
    
    track_list_str = "\n".join([f"- '{track['name']}' by {track['artists'][0]['name']}" for track in top_tracks[:10]])
    
    prompt = f"""
    You are a World-class Musicologist. Your task is to analyze a user's favorite songs and recommend new music.

    **User's Favorite Songs:**
    {track_list_str}

    **Your mission, in two steps:**
    
    **Step 1: Analysis**
    First, analyze the list above and determine the user's primary listening language and primary genre.

    **Step 2: Recommendation**
    Based *only* on the language and genre you identified in Step 1, recommend 10 other artists and tracks.
    - **Crucial Rule:** The recommended tracks **MUST** be in the same primary language you identified. For example, if the user listens to Thai music, you must recommend other Thai music. Do not recommend international artists.
    - Focus on artists that have a similar style or belong to the same music scene.

    **Response format requirement:**
    - You **MUST** respond with a perfectly structured JSON object and nothing else.
    - The JSON structure must be: {{"recommendations": [{{"artist": "artist_name", "track": "track_name"}}]}}
    """

    model = genai.GenerativeModel(
        'gemini-2.0-flash',
        generation_config={"response_mime_type": "application/json"}
    )
    
    try:
        response = await model.generate_content_async(prompt)
        data = json.loads(response.text)
        
        gemini_recommendations = [
            {"artist": item["artist"], "title": item["track"]} 
            for item in data.get("recommendations", [])
        ]
        
        print(f"✅ Gemini V3 dynamically analyzed language/genre and found {len(gemini_recommendations)} new seed tracks.")
        return gemini_recommendations
        
    except Exception as e:
        print(f"❌ Error during Gemini Seed Expansion: {e}")
        return []
    
async def rescue_lyrics_with_gemini(failed_tracks: list[dict]) -> dict:
    """
    (หน่วยกู้ภัย) รับรายชื่อเพลงที่หาเนื้อเพลงไม่เจอ แล้วให้ Gemini ช่วยสรุปใจความสำคัญ
    เพื่อนำไปใช้ในการวิเคราะห์อารมณ์ต่อไป
    """
    if not failed_tracks:
        return {}

    print(f"\n--- 🆘 Activating Gemini Rescuer for {len(failed_tracks)} tracks... ---")

    # สร้าง "รายการเป้าหมาย" ที่ชัดเจนสำหรับ Gemini
    track_list_str = "\n".join([f"- \"{track['name']}\" by {track['artists'][0]['name']}" for track in failed_tracks])

    prompt = f"""
    คุณคือผู้ช่วยวิเคราะห์ดนตรีที่มีความสามารถในการค้นหาข้อมูลสูงมาก
    สำหรับรายชื่อเพลงต่อไปนี้ ฉันไม่สามารถหาเนื้อเพลงเต็มๆ ได้:
    {track_list_str}

    **ภารกิจของคุณคือ:**
    1.  สำหรับแต่ละเพลงในรายการ โปรดช่วยค้นหาและ **"สรุปใจความสำคัญของเนื้อเพลง"** ที่สื่อถึงอารมณ์ให้ได้สั้นที่สุด (ประมาณ 1-2 ประโยค) โดยใช้ Token ให้น้อยที่สุดเท่าที่เป็นไปได้
    2.  หากไม่พบเนื้อเพลงจริงๆ หรือเป็นเพลงบรรเลง ให้ตอบกลับเป็น "Instrumental"

    **เงื่อนไขการตอบกลับ (สำคัญที่สุด):**
    - ต้องตอบกลับมาเป็น JSON object ที่สมบูรณ์แบบเท่านั้น
    - โครงสร้างของ JSON ต้องเป็น dictionary ที่มี key เป็น "ชื่อเพลง - ชื่อศิลปิน" และ value เป็น "บทสรุปเนื้อเพลง"
    - ตัวอย่าง: {{"เพลง A - ศิลปิน X": "เกี่ยวกับความรักที่ไม่สมหวัง", "เพลง B - ศิลปิน Y": "Instrumental"}}
    """
    
    model = genai.GenerativeModel(
        'gemini-2.0-flash',
        generation_config={"response_mime_type": "application/json"}
    )

    try:
        response = await model.generate_content_async(prompt)
        rescued_data = json.loads(response.text)
        print(f"✅ Gemini Rescuer successfully summarized {len(rescued_data)} tracks.")
        return rescued_data
    except Exception as e:
        print(f"❌ Error during Gemini Rescue mission: {e}")
        return {}