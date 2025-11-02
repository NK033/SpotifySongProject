# gemini_ai.py
import logging
import google.generativeai as genai
import json
import asyncio
import spotipy
from fastapi import HTTPException, status
from sympy import re
from database import save_song_analysis_to_db, get_song_analysis_from_db
from genius_api import get_lyrics
from custom_model import predict_moods
from spotify_api import get_spotify_track_data

# === Centralized Model Configuration ===
TEXT_MODEL = genai.GenerativeModel(
    'gemini-2.0-flash',
    system_instruction="คุณคือผู้ช่วยและนักวิจารณ์ดนตรีที่เชี่ยวชาญ สามารถวิเคราะห์เพลงได้อย่างแม่นยำและเขียนอธิบายได้อย่างเป็นธรรมชาติ"
)

JSON_MODEL = genai.GenerativeModel(
    'gemini-2.0-flash',
    generation_config={"response_mime_type": "application/json"}
)
# =======================================

async def analyze_and_store_song_analysis(spotify_track_data: dict) -> dict:
    """
    (V-Final) วิเคราะห์เพลงด้วย Gemini และให้ 'บทสรุปที่กระชับ' แทนการวิเคราะห์ยาวๆ
    """
    logging.info(f"Analyzing '{spotify_track_data.get('name')}' for a concise summary...")
    artist_name = spotify_track_data.get('artists', [{}])[0].get('name', 'N/A')
    song_title = spotify_track_data.get('name', 'N/A')
    
    lyrics = await get_lyrics(artist_name, song_title)
    predicted_moods = predict_moods(lyrics) if lyrics else []
    moods_text = ", ".join(predicted_moods) if predicted_moods else "ไม่สามารถระบุได้"
    
    prompt_content = f"""
    คุณเป็นนักวิเคราะห์ดนตรีมืออาชีพ โปรด "สรุปภาพรวม" ของเพลงต่อไปนี้ให้กระชับและเข้าใจง่าย

    - ชื่อเพลง: {song_title}
    - ศิลปิน: {artist_name}
    - อารมณ์หลักที่ตรวจพบจากเนื้อเพลง: {moods_text}

    **คำสั่ง:**
    โปรดเขียนสรุปเพลงนี้ใน **1 ย่อหน้าที่อ่านง่าย (ประมาณ 4-5 ประโยค)** โดยให้ครอบคลุมถึง แนวเพลง, อารมณ์โดยรวม, และลักษณะเด่นของดนตรีหรือเนื้อหา ไม่ต้องแยกเป็นข้อๆ
    """
    
    try:
        response = await TEXT_MODEL.generate_content_async(prompt_content)
        combined_analysis = { "gemini_analysis": response.text, "predicted_moods": predicted_moods }
        await save_song_analysis_to_db(spotify_track_data, combined_analysis)
        return combined_analysis
    except Exception as e:
        logging.error(f"Error calling Gemini API for song analysis: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error analyzing song with Gemini API.")

async def get_song_analysis_details(sp_client: spotipy.Spotify, song_uri: str) -> dict:
    """
    ดึงข้อมูลการวิเคราะห์เพลงจาก DB หรือวิเคราะห์ใหม่ถ้ายังไม่มี
    """
    analysis_data = await get_song_analysis_from_db(song_uri)
    if analysis_data:
        return analysis_data
    try:
        spotify_track_data = await get_spotify_track_data(sp_client, song_uri)
        return await analyze_and_store_song_analysis(spotify_track_data)
    except Exception as e:
        logging.error(f"Failed to get song details for URI {song_uri}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get song details: {e}")

async def summarize_playlist(sp_client: spotipy.Spotify, song_uris: list[str]) -> str:
    """
    (V-Final) ให้ Gemini สรุปภาพรวมของ Playlist อย่างชาญฉลาด
    """
    tasks = [get_song_analysis_details(sp_client, uri) for uri in song_uris]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_analyses = [res for res in results if not isinstance(res, Exception)]

    prompt = "นี่คือข้อมูลการวิเคราะห์ของแต่ละเพลงในเพลย์ลิสต์:\n\n"
    for i, analysis in enumerate(valid_analyses):
        prompt += f"--- เพลงที่ {i+1} ---\n{analysis.get('gemini_analysis', 'ไม่มีข้อมูล')}\n\n"
    
    prompt += """
    **คำสั่งของคุณ:**
    ในฐานะ 'ภัณฑารักษ์ดนตรี' (Music Curator) มืออาชีพ โปรดเขียนบทสรุปสำหรับเพลย์ลิสต์นี้
    
    **ห้ามทำ:** อย่าแค่สรุปว่าเพลย์ลิสต์นี้มีแนวเพลงหรืออารมณ์อะไรบ้าง
    
    **สิ่งที่ต้องทำ:**
    1.  อธิบายว่า **ทำไม** เพลงเหล่านี้ถึงถูกจัดมาอยู่ด้วยกัน
    2.  ค้นหา **"ธีมที่เชื่อมโยง" (Unifying Theme)** หรือ **"DNA ทางดนตรี" (Musical DNA)** ที่เป็นหัวใจหลักของเพลย์ลิสต์นี้
    3.  อธิบายธีมนั้นให้ผู้ฟังเข้าใจอย่างชัดเจน (ตัวอย่างเช่น: "นี่คือเพลย์ลิสต์ที่รวมเพลง J-Pop Rock ที่มีพลังสูง โดดเด่นด้วยจังหวะที่หนักแน่นและเสียงร้องหญิงที่ทรงพลัง")
    
    โปรดตอบเป็นภาษาไทยที่อ่านง่ายและลื่นไหล
    """

    try:
        response = await TEXT_MODEL.generate_content_async(prompt)
        return response.text
    except Exception as e:
        logging.error(f"Error calling Gemini API for playlist summary: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error summarizing playlist.")

async def get_gemini_seed_expansion(top_tracks: list[dict], user_message: str) -> list[dict]:
    """
    (V2 - Emotion-Aware) ขยายฐานเพลงโดยอิงจาก "สไตล์" (top_tracks) 
    และ "ธีมคำขอ" (user_message)
    """
    if not top_tracks:
        return []

    logging.info(f"Starting Gemini Seed Expansion (Emotion-Aware) for request: '{user_message}'")

    seed_data = []
    for track in top_tracks:
        if track and track.get('name') and track.get('artists'):
            seed_data.append({
                "artist": track['artists'][0]['name'],
                "title": track['name']
            })

    # --- (ใหม่: สร้าง "ธีม" จากคำขอ) ---
    # เราจะตรวจสอบว่าคำขอเป็นคำขอทั่วไปหรือไม่
    generic_requests_th = ["แนะนำเพลง", "เพลงแนะนำ", "ขอเพลงหน่อย", "หาเพลง"]
    generic_requests_en = ["recommend", "suggest", "find me songs"]
    
    is_generic_request = False
    msg_lower = user_message.lower()
    
    # ตรวจสอบว่าเป็นประโยคทั่วไปสั้นๆ หรือไม่
    if len(msg_lower) < 25:
        if any(keyword in msg_lower for keyword in generic_requests_th + generic_requests_en):
            is_generic_request = True

    theme_context = ""
    if is_generic_request or user_message == "🎵 แนะนำเพลงส่วนตัวให้หน่อย":
        theme_context = "The user has made a general request. Focus ONLY on their listening style."
    else:
        # ถ้าไม่ใช่คำขอทั่วไป ให้ถือว่ามี "ธีม" (เช่น "เพลงเศร้า", "เพลงตอนวิ่ง")
        theme_context = f"IMPORTANT: The user has a specific request right now. They want songs that fit this theme: '{user_message}'. The suggestions MUST match this theme."
    # --- (จบส่วนใหม่) ---

    prompt = f"""
    You are an AI music expert.
    
    1. Analyze the user's top tracks to understand their core listening style (e.g., genres, artists, language like J-Pop, K-Pop, etc.).
       User's Top Tracks (Core Style): {json.dumps(seed_data)}
    
    2. Read the user's current request to understand their desired theme or mood.
       User's Current Request (Theme): {theme_context}

    3. Suggest 20 new songs. The songs MUST match the user's core style (from step 1) AND their current request/theme (from step 2).
       (For example, if style is 'J-Pop' and theme is 'sad', suggest 'Sad J-Pop songs'.)
    
    Return ONLY a valid JSON list of objects, where each object has "artist" and "title".
    Example: [{{"artist": "Artist Name", "title": "Song Title"}}, ...]
    """
    
    try:
        response = await JSON_MODEL.generate_content_async(prompt)
        # ... (ส่วนการ parse JSON เหมือนเดิม) ...
        json_text = response.text.strip()
        
        # ค้นหา [] หรือ {}
        json_match = re.search(r'\[.*\]|\{.*\}', json_text, re.DOTALL)
        if not json_match:
            logging.error(f"Gemini seed expansion returned no JSON. Raw: {json_text}")
            return []
            
        json_data = json.loads(json_match.group(0))
        
        # ตรวจสอบว่าผลลัพธ์เป็น List (ตามที่เราสั่ง) หรือไม่
        if isinstance(json_data, list):
            logging.info(f"Gemini Seed Expansion successful. Found {len(json_data)} candidates.")
            return json_data
        elif isinstance(json_data, dict) and "songs" in json_data and isinstance(json_data["songs"], list):
             logging.info(f"Gemini Seed Expansion successful (wrapped in object). Found {len(json_data['songs'])} candidates.")
             return json_data["songs"]
        else:
            logging.error(f"Gemini seed expansion returned unexpected JSON format.")
            return []

    except Exception as e:
        logging.error(f"Error in get_gemini_seed_expansion: {e}", exc_info=True)
        return []

async def rescue_lyrics_with_gemini(failed_tracks: list[dict]) -> dict:
    """
    (V4 - Rate Limit Proof) Finds lyrics in safe batches to prevent 429 errors.
    """
    if not failed_tracks: 
        return {}
        
    logging.info(f"--- Activating Gemini Lyric Finder (Rate-Limit Proof V4) for {len(failed_tracks)} tracks... ---")

    # --- THIS IS THE FIX ---
    # Define a safe batch size and a delay
    BATCH_SIZE = 5  # 5 requests per prompt is very safe
    DELAY_BETWEEN_BATCHES = 5  # 5 seconds delay
    
    all_rescued_data = {}
    
    # Process the failed tracks in small, safe batches
    for i in range(0, len(failed_tracks), BATCH_SIZE):
        batch_tracks = failed_tracks[i:i + BATCH_SIZE]
        logging.info(f"--- Processing batch {i//BATCH_SIZE + 1}/{len(failed_tracks)//BATCH_SIZE + 1} ---")

        # Step 1: Create a list of tracks with safe IDs and a map
        tracks_for_prompt = []
        id_to_key_map = {}
        
        for j, track in enumerate(batch_tracks):
            artist = track.get('artists', [{}])[0].get('name', 'N/A')
            title = track.get('name', 'N/A')
            track_key = f"{artist} - {title}"
            track_id = f"track_{j+1}"
            
            id_to_key_map[track_id] = track_key
            
            tracks_for_prompt.append({
                "id": track_id,
                "artist": artist,
                "track": title,
                "album": track.get('album', {}).get('name'),
                "release_year": track.get('album', {}).get('release_date', '----')[:4],
                "spotify_url": track.get('external_urls', {}).get('spotify')
            })

        # Step 2: Create the prompt for this batch
        prompt = f"""
        You are an expert, multilingual lyric search engine. Find the full, accurate lyrics for the songs in this JSON: {json.dumps(tracks_for_prompt, ensure_ascii=False)}.

        **Response Format Requirement (Crucial):**
        - You MUST respond with a perfectly structured JSON object.
        - The key for each entry must be the "id" from the input (e.g., "track_1", "track_2").
        - The value must be a single string containing the full lyrics, or "" if not found.
        - Do NOT summarize or translate.
        
        **Example Response:**
        {{
          "track_1": "Full lyrics for the first song...",
          "track_2": ""
        }}
        """
        
        try:
            # Step 3: Call the API for this batch
            response = await JSON_MODEL.generate_content_async(prompt)
            api_response_data = json.loads(response.text)

            # Step 4: Map the results back
            if isinstance(api_response_data, dict):
                for track_id, lyrics in api_response_data.items():
                    if track_id in id_to_key_map:
                        artist_track_key = id_to_key_map[track_id]
                        all_rescued_data[artist_track_key] = lyrics
            else:
                logging.error(f"❌ Gemini API returned a {type(api_response_data)} instead of a dict for this batch.")

        except Exception as e:
            logging.error(f"❌ Error during Gemini Lyric Finder batch: {e}", exc_info=True)
            # If one batch fails, log it and continue to the next
            pass 

        # Step 5: Wait before processing the next batch to avoid rate limits
        if i + BATCH_SIZE < len(failed_tracks):
            logging.info(f"--- Waiting {DELAY_BETWEEN_BATCHES}s before next batch... ---")
            await asyncio.sleep(DELAY_BETWEEN_BATCHES)

    # --- End of batch processing ---
    
    found_count = sum(1 for lyric in all_rescued_data.values() if lyric)
    logging.info(f"✅ Gemini Lyric Finder (V4) retrieved lyrics for {found_count}/{len(failed_tracks)} tracks total.")
    return all_rescued_data
    

async def get_filler_tracks_with_lyrics(existing_tracks: list[dict]) -> list[dict]:
    """
    (V8) Recommends songs to complete a short playlist.
    """
    if not existing_tracks: return []
    logging.info("--- Activating Gemini Playlist Filler... ---")
    track_list_str = "\n".join([f"- '{t['name']}' by {t['artists'][0]['name']}" for t in existing_tracks])

    prompt = f"""
    This playlist is too short:
    {track_list_str}
    Recommend up to 20 more songs that perfectly match the existing songs' genre, language, and emotional vibe.
    **Response Format Requirement (Crucial):**
    - Respond with a JSON object containing a single key "filler_tracks".
    - The value must be a list of objects, each with three keys: "artist", "track", and "lyrics_summary".
    - "lyrics_summary" should be a concise, one-sentence summary of the song's lyrical theme.
    """
    try:
        response = await JSON_MODEL.generate_content_async(prompt)
        data = json.loads(response.text)
        filler_tracks = data.get("filler_tracks", [])
        logging.info(f"✅ Gemini Filler found {len(filler_tracks)} emergency candidates.")
        return filler_tracks
    except Exception as e:
        logging.error(f"❌ Error during Gemini Filler mission: {e}", exc_info=True)
        return []

async def get_emotional_profile_from_gemini(user_message: str) -> dict:
    """
    (NEW) ใช้ Gemini (ตัวฉลาด) เพื่อ "แปล" คำขอนามธรรม
    ให้อยู่ใน 8 อารมณ์ที่โมเดล 'predict_moods' เข้าใจ
    """
    logging.info(f"Using Gemini to translate abstract request: '{user_message}'")
    
    # รายการอารมณ์ 8 อย่างที่โมเดล 'predict_moods' ของเรารู้จัก
    EMOTION_LABELS = "['joy', 'sadness', 'anger', 'fear', 'excitement', 'love', 'optimism', 'neutral']"

    prompt = f"""
    You are an AI psychologist. Your task is to analyze the user's abstract music request and translate it into a JSON mood profile based ONLY on the 8 available emotions.
    
    Available Emotions: {EMOTION_LABELS}

    User's Request: "{user_message}"

    Instructions:
    1.  Think about the dominant emotions in the user's scenario.
    2.  Assign scores (0.0 to 1.0) to the relevant emotions. The scores do not need to sum to 1.
    3.  Return ONLY the valid JSON object.

    Example 1:
    User's Request: "หาเพลงแบบขับรถตอนกลางคืน"
    Analysis: This implies a 'neutral' or slightly 'sadness' (introspective) or 'optimism' (hopeful) vibe.
    Result: {{"neutral": 0.7, "sadness": 0.3, "optimism": 0.2}}

    Example 2:
    User's Request: "เพลงอกหักแต่ยังมูฟออนไม่ได้"
    Analysis: This is high 'sadness' and high 'love' (still caring).
    Result: {{"sadness": 0.9, "love": 0.7}}
    
    Example 3:
    User's Request: "เพลงตอนกำลังจะชนะการแข่งขัน"
    Analysis: This is high 'excitement' and high 'joy'.
    Result: {{"excitement": 0.9, "joy": 0.8}}
    """
    
    try:
        response = await JSON_MODEL.generate_content_async(prompt)
        json_text = response.text.strip()
        
        json_match = re.search(r'\{.*\}', json_text, re.DOTALL)
        if not json_match:
            logging.error(f"Gemini (Translator) returned no JSON. Raw: {json_text}")
            return {} # คืนค่าว่างถ้าล้มเหลว
            
        json_data = json.loads(json_match.group(0))
        
        if isinstance(json_data, dict):
            logging.info(f"Gemini (Translator) successful. Profile: {json_data}")
            return json_data
        else:
            logging.error(f"Gemini (Translator) returned unexpected format.")
            return {}

    except Exception as e:
        logging.error(f"Error in get_emotional_profile_from_gemini: {e}", exc_info=True)
        return {}