# groq_ai.py (Replacement for gemini_ai.py - Enhanced & Robust)
import logging
import json
import asyncio
import re
import spotipy
from groq import AsyncGroq
from fastapi import HTTPException, status
from typing import List, Dict, Any, Optional

# Import Local Modules
from config import Config
from database import save_song_analysis_to_db, get_song_analysis_from_db
from spotify_api import get_spotify_track_data
from custom_model import predict_moods

# --- 1. Setup Groq Client & Models ---
# ตรวจสอบ Key ก่อนเริ่มทำงาน
if not Config.GROQ_API_KEY:
    logging.warning("⚠️ GROQ_API_KEY is missing. AI features will fail.")

groq_client = AsyncGroq(api_key=Config.GROQ_API_KEY)

# โมเดลสำหรับงาน "คิดวิเคราะห์" (Logic, JSON, Search)
# ใช้ openai/gpt-oss-120b ตามที่คุณต้องการ (รองรับ reasoning_effort)
SMART_MODEL = "openai/gpt-oss-120b"

# โมเดลสำหรับงาน "งานเขียน/Creative" (Summarize, Description)
# Llama 3.3 70B เร็ว, เสถียร, และเขียนไทยได้ดี
FAST_MODEL = "llama-3.3-70b-versatile"

GROQ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_spotify_songs",
            "description": "Search for songs on Spotify.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query e.g. 'artist:BTS track:Butter'"},
                    "limit": {"type": "integer", "description": "Number of results (default 5)"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_spotify_playlist",
            "description": "Create a new Spotify playlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "playlist_name": {"type": "string", "description": "Name for the playlist"},
                    "track_uris": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of Spotify track URIs"}
                },
                "required": ["playlist_name", "track_uris"]
            }
        }
    }
]

# --- 2. Robust Helpers ---

def _sanitize_json_string(json_str: str) -> str:
    """ทำความสะอาด String ให้เป็น JSON ที่ถูกต้องที่สุด"""
    try:
        # 1. หา JSON Object หรือ Array ที่ซ่อนอยู่ใน Text (เช่น AI เผลอพูดนำหน้า)
        # หา [...] หรือ {...} ที่ดูสมเหตุสมผลที่สุด
        json_match = re.search(r'(\{.*\}|\[.*\])', json_str, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)

        # 2. ลบ Markdown Code Blocks
        json_str = re.sub(r'^```(json)?', '', json_str, flags=re.MULTILINE)
        json_str = re.sub(r'```$', '', json_str, flags=re.MULTILINE)
        
        # 3. แก้ Backslash ที่ผิดปกติ (Common AI artifact)
        json_str = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', json_str)
        
        # 4. ลบ Control Characters
        json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
        
        return json_str.strip()
    except Exception as e:
        logging.error(f"JSON Sanitization failed: {e}")
        return json_str

async def _call_groq_api(
    model: str, 
    messages: List[Dict], 
    json_mode: bool = False, 
    reasoning: bool = False,
    temperature: float = 0.7
) -> str:
    """Wrapper กลางสำหรับการเรียก API เพื่อจัดการ Error และ Config ในที่เดียว"""
    try:
        # เตรียม params พื้นฐาน
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        # เพิ่ม JSON Mode ถ้าจำเป็น
        if json_mode:
            params["response_format"] = {"type": "json_object"}
        
        # เพิ่ม Reasoning Effort เฉพาะรุ่นที่รองรับ (gpt-oss-120b)
        if reasoning and "gpt-oss-120b" in model:
            params["reasoning_effort"] = "medium"
            # ปกติ Reasoning model มักจะบังคับ temperature=1 หรือไม่ให้ตั้ง
            # แต่ถ้าใส่ไปแล้วไม่ error ก็คงไว้ (ปรับตาม document ล่าสุด)
            params["temperature"] = 1.0 

        completion = await groq_client.chat.completions.create(**params)
        return completion.choices[0].message.content

    except Exception as e:
        logging.error(f"❌ Groq API Call Failed ({model}): {e}", exc_info=True)
        raise e  # โยน Error ออกไปให้ฟังก์ชันแม่จัดการ

# --- 3. Core Functions (Migrated & Improved) ---

async def analyze_and_store_song_analysis_groq(spotify_track_data: dict) -> dict:
    """วิเคราะห์เพลง (แทนที่ฟังก์ชันเดิม)"""
    artist = spotify_track_data.get('artists', [{}])[0].get('name', 'N/A')
    title = spotify_track_data.get('name', 'N/A')
    album = spotify_track_data.get('album', {}).get('name', 'N/A')
    
    # ใช้ FAST_MODEL เพราะต้องการคำบรรยายที่สละสลวยและรวดเร็ว
    prompt = f"""
    Analyze this song for a music app user:
    Song: {title}
    Artist: {artist}
    Album: {album}

    Output Requirement:
    Write a short, engaging description in Thai (3-4 sentences).
    Cover: Genre, Mood/Vibe, and any interesting trivia (e.g. if it's an OST).
    Do NOT use bullet points. Write as a single paragraph.
    """

    try:
        content = await _call_groq_api(FAST_MODEL, [{"role": "user", "content": prompt}])
        combined_analysis = { "gemini_analysis": content } # Keep key 'gemini_analysis' for DB compatibility
        await save_song_analysis_to_db(spotify_track_data, combined_analysis)
        return combined_analysis
    except Exception:
        return { "gemini_analysis": "ไม่สามารถวิเคราะห์เพลงได้ในขณะนี้ (AI Busy)" }

async def get_song_analysis_details_groq(sp_client: spotipy.Spotify, song_uri: str) -> dict:
    """ดึงข้อมูลวิเคราะห์ (Cache -> Groq)"""
    # 1. Check Cache
    analysis_data = await get_song_analysis_from_db(song_uri)
    if analysis_data and 'gemini_analysis' in analysis_data:
        return analysis_data

    # 2. Fetch & Analyze
    try:
        spotify_track_data = await get_spotify_track_data(sp_client, song_uri)
        return await analyze_and_store_song_analysis_groq(spotify_track_data)
    except Exception as e:
        logging.error(f"Failed to get details for {song_uri}: {e}")
        return {}

async def summarize_playlist_groq(sp_client: spotipy.Spotify, final_song_uris: list[str], seed_tracks: list[dict]) -> str:
    """สรุปเพลย์ลิสต์ (รักษา Logic การ Preload เพื่อความเร็ว)"""
    
    # 1. Preload ข้อมูลเพลง (Parallel)
    await preload_groq_details(sp_client, [{"uri": uri} for uri in final_song_uris])
    
    # 2. เตรียมข้อมูลสำหรับ Prompt (จำกัดจำนวนเพื่อประหยัด Token)
    seed_info = "\n".join([f"- {t['name']} ({t['artists'][0]['name']})" for t in seed_tracks[:5]])
    
    # ดึงชื่อเพลงปลายทาง (พยายามดึงจาก DB ก่อน ถ้าไม่มีค่อยดึงสด)
    final_tracks_info = []
    for uri in final_song_uris[:15]:
        data = await get_song_analysis_from_db(uri)
        if data and 'gemini_analysis' in data:
            # สมมติว่าเก็บชื่อไว้ หรือดึงจาก cache
            # เพื่อความชัวร์ ดึงสดจาก Spotify object ที่ cache ไว้ใน DB (ถ้ามี) หรือข้ามไปดึงใหม่
            pass 
        
    # ดึงชื่อเพลงแบบเร็วๆ สำหรับ Prompt
    tracks_objs = []
    for uri in final_song_uris[:15]:
        try:
            t = await get_spotify_track_data(sp_client, uri)
            tracks_objs.append(f"- {t['name']} ({t['artists'][0]['name']})")
        except: continue
    final_str = "\n".join(tracks_objs)

    prompt = f"""
    Act as a Music Curator. Summarize this generated playlist in Thai.
    
    User's Taste (Seeds):
    {seed_info}
    
    Selected Playlist:
    {final_str}
    
    Task:
    1. Define the Theme of this playlist.
    2. Explain why it fits the user's taste.
    3. Write a short, inviting intro (2-3 sentences).
    """

    try:
        return await _call_groq_api(FAST_MODEL, [{"role": "user", "content": prompt}], temperature=0.7)
    except Exception:
        return "เพลย์ลิสต์คัดสรรพิเศษสำหรับคุณ หวังว่าจะถูกใจนะครับ!"

async def get_seed_expansion_groq(top_tracks: list[dict], user_message: str) -> list[dict]:
    """หาเพลงใหม่จาก Niche (ใช้ SMART_MODEL + Reasoning)"""
    if not top_tracks: return []
    
    seed_str = json.dumps([{"artist": t['artists'][0]['name'], "title": t['name']} for t in top_tracks[:15]], ensure_ascii=False)
    
    prompt = f"""
    Analyze these seed tracks: {seed_str}
    User Context: "{user_message}"

    Goal: Suggest 20 NEW songs that fit the user's specific "Niche" (e.g. Anime OST, City Pop, T-Pop) and the Context.
    
    Constraints:
    1. Output JSON ONLY. Format: list of objects with "artist", "title", "reason".
    2. Do NOT suggest songs present in the seed list.
    3. Reason must be in Thai or English.
    """

    try:
        content = await _call_groq_api(SMART_MODEL, [{"role": "user", "content": prompt}], json_mode=True, reasoning=True)
        data = json.loads(_sanitize_json_string(content))
        
        # Robust parsing: จัดการกรณี AI ตอบ key ซ้อน
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list): return v
        return data if isinstance(data, list) else []

    except Exception as e:
        logging.error(f"Seed Expansion Failed: {e}")
        return []

async def rescue_lyrics_with_groq(failed_tracks: list[dict]) -> dict:
    """กู้เนื้อเพลง (Batch Processing)"""
    if not failed_tracks: return {}
    
    logging.info(f"--- Groq Lyric Rescue: Processing {len(failed_tracks)} tracks ---")
    BATCH_SIZE = 5 # ทำทีละ 5 เพลงเพื่อความแม่นยำ
    all_lyrics = {}

    for i in range(0, len(failed_tracks), BATCH_SIZE):
        batch = failed_tracks[i:i+BATCH_SIZE]
        
        tracks_input = []
        for idx, t in enumerate(batch):
            key_id = f"t{idx}" # ใช้ ID สั้นๆ ประหยัด Token
            tracks_input.append({
                "id": key_id,
                "artist": t['artists'][0]['name'],
                "title": t['name']
            })

        prompt = f"""
        Fetch lyrics for these songs: {json.dumps(tracks_input, ensure_ascii=False)}
        
        Output JSON Object: Keys are "id", Values are "lyrics_text".
        Use \\n for newlines. Return empty string if not found.
        """

        try:
            content = await _call_groq_api(SMART_MODEL, [{"role": "user", "content": prompt}], json_mode=True, reasoning=True)
            data = json.loads(_sanitize_json_string(content))
            
            # Map กลับเป็น Key เดิม (Artist - Title)
            for idx, t in enumerate(batch):
                key_id = f"t{idx}"
                if data.get(key_id):
                    real_key = f"{t['artists'][0]['name']} - {t['name']}"
                    all_lyrics[real_key] = data[key_id]
        
        except Exception as e:
            logging.error(f"Lyric Rescue Batch Failed: {e}")
            # Continue to next batch without crashing

    return all_lyrics

async def get_filler_tracks_groq(existing_tracks: list[dict], lang_guardrail: str) -> list[dict]:
    """หาเพลงเติมเต็ม (Filler)"""
    seed_str = "\n".join([f"- {t['name']} ({t['artists'][0]['name']})" for t in existing_tracks[:10]])
    
    prompt = f"""
    Playlist needs more songs. Seeds:
    {seed_str}
    
    Task: Suggest 15 NEW songs.
    Constraints:
    1. Language Code: '{lang_guardrail}' (Match this language strict).
    2. Vibe: Match the seed tracks.
    3. Output JSON: {{ "filler_tracks": [ {{ "artist": "...", "track": "...", "reason": "..." }} ] }}
    """

    try:
        content = await _call_groq_api(SMART_MODEL, [{"role": "user", "content": prompt}], json_mode=True, reasoning=True)
        data = json.loads(_sanitize_json_string(content))
        return data.get("filler_tracks", [])
    except Exception:
        return []

async def get_emotional_profile_from_groq(user_message: str) -> dict:
    """แปลความต้องการเป็นอารมณ์ (ใช้ FAST_MODEL เพื่อความเร็ว)"""
    prompt = f"""
    Analyze request: "{user_message}"
    Map to emotions (0.0-1.0): [joy, sadness, anger, fear, excitement, love, optimism, neutral]
    Output JSON ONLY: {{ "joy": 0.5, ... }}
    """
    try:
        content = await _call_groq_api(FAST_MODEL, [{"role": "user", "content": prompt}], json_mode=True, temperature=0.2)
        return json.loads(_sanitize_json_string(content))
    except Exception:
        return {}

async def preload_groq_details(sp_client: spotipy.Spotify, tracks: list[dict]):
    """โหลดข้อมูลล่วงหน้า (Fire-and-forget logic)"""
    if not tracks: return
    try:
        # ใช้ gather เพื่อโหลดพร้อมกัน
        tasks = [get_song_analysis_details_groq(sp_client, t['uri']) for t in tracks if t.get('uri')]
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logging.error(f"Preload failed: {e}")