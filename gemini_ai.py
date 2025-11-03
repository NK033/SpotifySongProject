# gemini_ai.py (FIXED V4 - Added "No Duplicates" instruction)
import logging
import google.generativeai as genai
import json
import asyncio
import spotipy
from fastapi import HTTPException, status
import re 
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

# --- [ ฟังก์ชันฆ่าเชื้อ JSON ] ---
def _sanitize_json_string(json_str: str) -> str:
    """
    พยายามแก้ไขอักขระ \ (backslash) ที่ผิดพลาดซึ่ง Gemini สร้างขึ้น
    """
    try:
        return re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', json_str)
    except Exception:
        return json_str
# --- [ จบฟังก์ชันใหม่ ] ---


async def analyze_and_store_song_analysis(spotify_track_data: dict) -> dict:
    logging.info(f"Generating NEW Gemini analysis for '{spotify_track_data.get('name')}'...")
    artist_name = spotify_track_data.get('artists', [{}])[0].get('name', 'N/A')
    song_title = spotify_track_data.get('name', 'N/A')
    album_name = spotify_track_data.get('album', {}).get('name', 'N/A')
    release_year = spotify_track_data.get('album', {}).get('release_date', '----')[:4]
    
    # *** 1. ลบการเรียก predict_moods และ moods_text ออกไปทั้งหมด ***
    
    # *** 2. สร้าง Prompt ใหม่ตามที่คุณต้องการ ***
    prompt_content = f"""
    คุณเป็นนักวิจารณ์ดนตรี AI โปรดเขียนคำอธิบายสั้นๆ (ไม่เกิน 3-4 ประโยค) สำหรับเพลงนี้:

    - ชื่อเพลง: {song_title}
    - ศิลปิน: {artist_name}
    - อัลบั้ม: {album_name}
    - ปีที่ปล่อย: {release_year}

    **คำสั่ง:**
    1.  นี่เป็นเพลงแนวไหน? (เช่น J-Pop, Rock, Ballad)
    2.  เพลงนี้มาจากอัลบั้ม, อนิเมะ, หรือภาพยนตร์อะไรหรือไม่? (ถ้ามีข้อมูล)
    3.  อธิบายลักษณะเด่นของเพลง (เช่น "เป็นเพลงชิลๆ", "เพลงเศร้าที่ทรงพลัง", "เพลงจังหวะสนุกสนาน")
    
    โปรดเขียนพรรณนาให้น่าฟังและกระชับ จบใน 1 ย่อหน้า
    """
    
    try:
        response = await TEXT_MODEL.generate_content_async(prompt_content)
        
        # *** 3. บันทึกเฉพาะ gemini_analysis เท่านั้น ***
        # เราจะไม่บันทึก "predicted_moods" ที่มีปัญหาอีกต่อไป
        combined_analysis = { "gemini_analysis": response.text }
        
        await save_song_analysis_to_db(spotify_track_data, combined_analysis)
        return combined_analysis
    except Exception as e:
        logging.error(f"Error calling Gemini API for new song analysis: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error analyzing song with Gemini API.")

async def get_song_analysis_details(sp_client: spotipy.Spotify, song_uri: str) -> dict:
    
    # 1. พยายามดึงข้อมูลจาก Cache (ฐานข้อมูล) ก่อน
    analysis_data = await get_song_analysis_from_db(song_uri)
    
    # 2. [จุดแก้ไขที่สำคัญ] 
    # ตรวจสอบว่าข้อมูลมีอยู่ และ "สมบูรณ์" (มี key 'gemini_analysis') หรือไม่
    if analysis_data and 'gemini_analysis' in analysis_data:
        logging.info(f"Cache HIT (Complete) for {song_uri}")
        return analysis_data

    # 3. ถ้า Cache ไม่มี หรือ "ไม่สมบูรณ์" (เช่น มีแต่ predicted_moods)
    # ให้ทำการสร้างข้อมูลวิเคราะห์ใหม่ทั้งหมด
    logging.info(f"Cache MISS or Incomplete for {song_uri}. Generating new analysis...")
    try:
        # ดึงข้อมูลเพลงล่าสุดจาก Spotify
        spotify_track_data = await get_spotify_track_data(sp_client, song_uri)
        
        # เรียกใช้ฟังก์ชัน analyze_and_store_song_analysis (ที่เราแก้ไขไปก่อนหน้า)
        # เพื่อสร้างคำอธิบายจาก Gemini และบันทึกลง Cache
        return await analyze_and_store_song_analysis(spotify_track_data)
        
    except Exception as e:
        logging.error(f"Failed to get song details for URI {song_uri}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get song details: {e}")

async def summarize_playlist(
    sp_client: spotipy.Spotify, 
    final_song_uris: list[str], 
    seed_tracks: list[dict]
) -> str:
    
    # 1. ดึงข้อมูล analysis ของ Final Playlist (เหมือนเดิม)
    tasks = [get_song_analysis_details(sp_client, uri) for uri in final_song_uris]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 2. แปลงข้อมูล Seed Tracks และ Final Tracks ให้เป็นข้อความ
    seed_track_list_str = "\n".join([f"- {t['name']} by {t['artists'][0]['name']}" for t in seed_tracks if t and t.get('name') and t.get('artists')])
    
    final_track_list = []
    for res in results:
        if not isinstance(res, Exception) and res.get('spotify_track_object'):
            track = res['spotify_track_object']
            final_track_list.append(f"- {track['name']} by {track['artists'][0]['name']}")
    final_track_list_str = "\n".join(final_track_list)

    # 3. สร้าง Prompt ใหม่ตามที่คุณต้องการ
    prompt = f"""
    คุณเป็นภัณฑารักษ์ดนตรี (Music Curator) ผู้เชี่ยวชาญ
    นี่คือข้อมูล 2 ส่วนที่ใช้ในการวิเคราะห์:

    **ส่วนที่ 1: เพลงตั้งต้น (Seed Tracks) จากผู้ใช้**
    (นี่คือเพลงที่แสดงถึงรสนิยมดั้งเดิมของผู้ใช้)
    {seed_track_list_str}

    **ส่วนที่ 2: เพลย์ลิสต์ที่ AI แนะนำ (Final Playlist)**
    (นี่คือเพลงที่ AI เลือกมาให้)
    {final_track_list_str}

    **คำสั่งของคุณ (สำคัญมาก):**
    โปรดเขียนบทสรุปเพลย์ลิสต์นี้โดยตอบคำถาม 2 ข้อต่อไปนี้:
    
    1.  **เพลย์ลิสต์นี้เหมาะกับผู้ใช้ยังไง?** (อธิบายว่าเพลงใน Final Playlist มันเชื่อมโยงกับ Seed Tracks ของผู้ใช้อย่างไร เช่น "จากที่คุณชอบเพลง J-Pop ที่มีจังหวะ ... AI จึงได้เลือก...")
    2.  **นี่คือเพลย์ลิสต์แบบไหน?** (ตั้งชื่อธีม หรืออธิบายภาพรวมของเพลย์ลิสต์นี้ เช่น "เพลย์ลิสต์สำหรับฟังตอนขับรถ", "รวมเพลงอนิเมะจังหวะมันส์ๆ", "เพลงชิลๆ สำหรับวันพักผ่อน")

    โปรดตอบเป็นภาษาไทยที่อ่านง่ายและลื่นไหล
    """

    try:
        response = await TEXT_MODEL.generate_content_async(prompt)
        return response.text
    except Exception as e:
        logging.error(f"Error calling Gemini API for playlist summary: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error summarizing playlist.")


async def get_gemini_seed_expansion(top_tracks: list[dict], user_message: str) -> list[dict]:
    # (ฟังก์ชันนี้ **ต้อง** แก้ไข)
    if not top_tracks:
        return []
    logging.info(f"Starting Gemini Seed Expansion (V3 - Lyrics-Rich) for request: '{user_message}'")

    seed_data = []
    for track in top_tracks:
        if track and track.get('name') and track.get('artists'):
            seed_data.append({
                "artist": track['artists'][0]['name'],
                "title": track['name']
            })

    generic_requests_th = ["แนะนำเพลง", "เพลงแนะนำ", "ขอเพลงหน่อย", "หาเพลง"]
    generic_requests_en = ["recommend", "suggest", "find me songs"]
    is_generic_request = False
    msg_lower = user_message.lower()
    if len(msg_lower) < 25:
        if any(keyword in msg_lower for keyword in generic_requests_th + generic_requests_en):
            is_generic_request = True
    theme_context = ""
    if is_generic_request or user_message == "🎵 แนะนำเพลงส่วนตัวให้หน่อย":
        theme_context = "The user has made a general request. Focus ONLY on their listening style."
    else:
        theme_context = f"IMPORTANT: The user has a specific request right now. They want songs that fit this theme: '{user_message}'. The suggestions MUST match this theme."

    prompt = f"""
    You are an AI music expert.
    
    1. Analyze the user's top tracks (Core Style): {json.dumps(seed_data)}
    2. Analyze the user's current request (Theme): {theme_context}

    3. Suggest 20 new songs that match BOTH the core style AND the theme.
    
    4. FOR EACH SONG, you MUST provide a "lyrics_summary" or "reasoning" (in English or Thai) that explains WHY this song fits the theme.
       (e.g., "A chill, introspective song about driving alone," "Lyrically, this song is about sadness and longing.")
    
    Return ONLY a valid JSON list of objects.
    Example: [
        {{"artist": "Artist Name", "title": "Song Title", "lyrics_summary": "Reasoning why this song fits..."}},
        ...
    ]
    """
    
    try:
        response = await JSON_MODEL.generate_content_async(prompt)
        json_text = response.text.strip()
        
        json_match = re.search(r'\[.*\]', json_text, re.DOTALL) 
        if not json_match:
            logging.error(f"Gemini (Lyrics-Rich) returned no JSON List. Raw: {json_text}")
            return []
            
        # --- [ FIX: ใช้ Sanitizer ] ---
        sanitized_json_string = _sanitize_json_string(json_match.group(0))
        json_data = json.loads(sanitized_json_string)
        # --- [ จบ FIX ] ---
        
        if isinstance(json_data, list):
            valid_candidates = [
                track for track in json_data 
                if track.get("artist") and track.get("title") and track.get("lyrics_summary")
            ]
            logging.info(f"Gemini (Lyrics-Rich) successful. Found {len(valid_candidates)} valid candidates.")
            return valid_candidates
        else:
            logging.error(f"Gemini (Lyrics-Rich) returned unexpected JSON format.")
            return []

    except Exception as e:
        logging.error(f"Error in get_gemini_seed_expansion (Lyrics-Rich): {e}", exc_info=True)
        return []

async def rescue_lyrics_with_gemini(failed_tracks: list[dict]) -> dict:
    if not failed_tracks: 
        return {}
    logging.info(f"--- Activating Gemini Lyric Finder (Rate-Limit Proof V4) for {len(failed_tracks)} tracks... ---")
    BATCH_SIZE = 5
    
    # --- [ THE FIX (User Request) ] ---
    # ลองที่ 7 วินาที (จากเดิม 5 วินาที)
    DELAY_BETWEEN_BATCHES = 7
    # --- [ END FIX ] ---
    
    all_rescued_data = {}
    
    total_batches = (len(failed_tracks) + BATCH_SIZE - 1) // BATCH_SIZE
    
    for i in range(0, len(failed_tracks), BATCH_SIZE):
        batch_tracks = failed_tracks[i:i + BATCH_SIZE]
        current_batch_num = (i // BATCH_SIZE) + 1
        logging.info(f"--- Processing batch {current_batch_num}/{total_batches} ---")

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
            response = await JSON_MODEL.generate_content_async(prompt)
            json_text = response.text.strip() 

            json_match = re.search(r'\{.*\S.*\}', json_text, re.DOTALL)
            
            if not json_match:
                logging.error(f"❌ Gemini (Lyric Finder) returned no JSON object. Raw: {json_text}")
                continue 

            sanitized_json_string = _sanitize_json_string(json_match.group(0))
            api_response_data = json.loads(sanitized_json_string)

            if isinstance(api_response_data, dict):
                for track_id, lyrics in api_response_data.items():
                    if track_id in id_to_key_map:
                        artist_track_key = id_to_key_map[track_id]
                        all_rescued_data[artist_track_key] = lyrics
            else:
                logging.error(f"❌ Gemini API returned a {type(api_response_data)} instead of a dict for this batch.")

        except Exception as e:
            # เราจะ log error ไว้ แต่จะปล่อยให้มันทำงาน batch ต่อไป (เผื่อ batch หน้าสำเร็จ)
            logging.error(f"❌ Error during Gemini Lyric Finder batch: {e}", exc_info=True)
            pass 

        if i + BATCH_SIZE < len(failed_tracks):
            logging.info(f"--- Waiting {DELAY_BETWEEN_BATCHES}s before next batch... ---")
            await asyncio.sleep(DELAY_BETWEEN_BATCHES)

    found_count = sum(1 for lyric in all_rescued_data.values() if lyric)
    logging.info(f"✅ Gemini Lyric Finder (V4) retrieved lyrics for {found_count}/{len(failed_tracks)} tracks total.")
    return all_rescued_data
    
# --- [ นี่คือฟังก์ชันที่แก้ไข ] ---
async def get_filler_tracks_with_lyrics(existing_tracks: list[dict], lang_guardrail: str) -> list[dict]:
    """
    (V8.2 - Language Aware & No Duplicates)
    """
    if not existing_tracks: return []
    logging.info("--- Activating Gemini Playlist Filler (V8.2)... ---")
    track_list_str = "\n".join([f"- '{t['name']}' by {t['artists'][0]['name']}" for t in existing_tracks])
    
    prompt = f"""
    This playlist is too short. Here are the songs already in it (or that we are using as seeds):
    {track_list_str}

    **CRITICAL INSTRUCTION 1 (LANGUAGE):**
    All recommended songs MUST be in the same language as the seed tracks.
    The required language code is: '{lang_guardrail}'.
    (Example: 'cjk' means Japanese/Korean, 'latin' means English/Spanish, 'th' means Thai).
    DO NOT suggest songs in other languages.
    
    **CRITICAL INSTRUCTION 2 (NO DUPLICATES):**
    DO NOT recommend the songs listed above. You must find NEW, SIMILAR songs.

    Recommend up to 20 new songs that match the genre, language, and emotional vibe.
    
    **Response Format Requirement (Crucial):**
    - Respond with a JSON object containing a single key "filler_tracks".
    - The value must be a list of objects, each with three keys: "artist", "track", and "lyrics_summary".
    - "lyrics_summary" should be a concise, one-sentence summary of the song's lyrical theme.
    """
    try:
        response = await JSON_MODEL.generate_content_async(prompt)
        json_text = response.text.strip() 

        json_match = re.search(r'\{.*\S.*\}', json_text, re.DOTALL)
        
        if not json_match:
            logging.error(f"❌ Gemini (Filler) returned no JSON object. Raw: {json_text}")
            return []

        sanitized_json_string = _sanitize_json_string(json_match.group(0))
        data = json.loads(sanitized_json_string)
        
        filler_tracks = data.get("filler_tracks", [])
        logging.info(f"✅ Gemini Filler (V8.2) found {len(filler_tracks)} emergency candidates.")
        return filler_tracks
    except Exception as e:
        logging.error(f"❌ Error during Gemini Filler mission: {e}", exc_info=True)
        return []
# --- [ จบฟังก์ชันที่แก้ไข ] ---

async def get_emotional_profile_from_gemini(user_message: str) -> dict:
    # (ฟังก์ชันนี้ **ต้อง** แก้ไข)
    logging.info(f"Using Gemini to translate abstract request: '{user_message}'")
    
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
            return {}
            
        # --- [ FIX: ใช้ Sanitizer ] ---
        sanitized_json_string = _sanitize_json_string(json_match.group(0))
        json_data = json.loads(sanitized_json_string)
        # --- [ จบ FIX ] ---
        
        if isinstance(json_data, dict):
            logging.info(f"Gemini (Translator) successful. Profile: {json_data}")
            return json_data
        else:
            logging.error(f"Gemini (Translator) returned unexpected format.")
            return {}

    except Exception as e:
        logging.error(f"Error in get_emotional_profile_from_gemini: {e}", exc_info=True)
        return {}