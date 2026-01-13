# groq_ai.py (Final Fixed: Solved Error 400 Conflict)
import logging
import json
import asyncio
import re
import spotipy
from groq import AsyncGroq
from fastapi import HTTPException, status
from typing import Any, Optional
from duckduckgo_search import DDGS # 🔥 Required: pip install duckduckgo-search

# Import Local Modules
from config import Config
from database import save_song_analysis_to_db, get_song_analysis_from_db
from spotify_api import get_spotify_track_data
from custom_model import predict_moods

# --- 1. Setup Groq Client & Models ---
if not Config.GROQ_API_KEY:
    logging.warning("⚠️ GROQ_API_KEY is missing. AI features will fail.")

groq_client = AsyncGroq(api_key=Config.GROQ_API_KEY)

# SMART_MODEL: สำหรับงาน Logic, JSON, Search
SMART_MODEL = "openai/gpt-oss-120b" 

# FAST_MODEL: สำหรับงานเขียน Creative, สรุปความ
FAST_MODEL = "llama-3.3-70b-versatile"

# 🔥 [RESTORED] GROQ_TOOLS (จำเป็นสำหรับการ Import จากไฟล์อื่น)
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

# --- 2. The Search Tool Function ---
def search_web(query: str) -> str:
    """
    Real web search using DuckDuckGo (Free, No API Key required).
    """
    try:
        logging.info(f"🔎 Searching Web for: {query}")
        # max_results=3 เพียงพอสำหรับเนื้อเพลง/ข้อมูลทั่วไป
        results = DDGS().text(query, max_results=3)
        if not results:
            return "No results found."
        
        # รวมผลลัพธ์เป็น Text เดียวเพื่อให้ AI อ่าน
        summary = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
        return summary
    except Exception as e:
        return f"Search failed: {e}"

# --- 3. Robust Helpers ---

def _sanitize_json_string(json_str: str) -> str:
    """ทำความสะอาด String ให้เป็น JSON ที่ถูกต้องที่สุด"""
    try:
        json_match = re.search(r'(\{.*\}|\[.*\])', json_str, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)

        json_str = re.sub(r'^```(json)?', '', json_str, flags=re.MULTILINE)
        json_str = re.sub(r'```$', '', json_str, flags=re.MULTILINE)
        json_str = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', json_str)
        json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
        
        return json_str.strip()
    except Exception as e:
        logging.error(f"JSON Sanitization failed: {e}")
        return json_str

async def _call_groq_api(
    model: str, 
    messages: list[dict], 
    json_mode: bool = False, 
    reasoning: bool = False,
    temperature: float = 0.7,
    allow_search: bool = False # 🔥 New flag: อนุญาตให้ค้นหาหรือไม่?
) -> str:
    """
    Central API Wrapper with Tool Execution Loop support.
    """
    try:
        # 1. Define Tools (Only if search is allowed)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Find lyrics, song info, or facts from the internet.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The search keywords (e.g. 'Song Name lyrics')"}
                        },
                        "required": ["query"],
                    },
                },
            }
        ] if allow_search else None

        # Prepare base parameters
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        # 🔥 FIX ERROR 400: Groq ไม่อนุญาตให้ใช้ json_mode พร้อมกับ tools
        # ถ้ามี tools เราจะปิด json_mode (แล้วใช้ Prompt บังคับเอา)
        if json_mode and not tools:
            params["response_format"] = {"type": "json_object"}
        
        # Configure Tools
        if tools: 
            params["tools"] = tools
            params["tool_choice"] = "auto" # Let AI decide
        else:
            params["tool_choice"] = "none" # Explicitly disable tools

        # Reasoning Effort (Specific to gpt-oss-120b)
        if reasoning and "gpt-oss-120b" in model:
            params["reasoning_effort"] = "medium"
            params["temperature"] = 1.0 

        # --- Round 1: Initial Request ---
        response = await groq_client.chat.completions.create(**params)
        response_message = response.choices[0].message
        
        # 2. Check for Tool Calls
        tool_calls = response_message.tool_calls
        
        if tool_calls:
            # AI wants to use a tool -> Execute the tool loop
            messages.append(response_message) # Append the AI's intent to history
            
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                if function_name == "search_web":
                    # Execute search (run in thread to avoid blocking async loop)
                    tool_output = await asyncio.to_thread(search_web, **function_args)
                    
                    # Append result to messages
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": "search_web",
                        "content": tool_output,
                    })
            
            # --- Round 2: Final Response Generation ---
            # Send the search results back to AI for the final answer
            # Force tool_choice="none" to prevent infinite loops
            params["messages"] = messages
            params["tool_choice"] = "none" 
            
            # Note: แม้รอบนี้เราจะปิด Tool แต่เราจะไม่เปิด JSON mode กลับมา
            # เพื่อความปลอดภัยและหลีกเลี่ยง Error เดิมซ้ำ
            
            final_response = await groq_client.chat.completions.create(**params)
            return final_response.choices[0].message.content
            
        else:
            # No tool used, return the answer directly
            return response_message.content

    except Exception as e:
        logging.error(f"❌ Groq API Call Failed ({model}): {e}", exc_info=True)
        # Return empty string to prevent app crash
        return ""

# --- 4. Core Functions (Updated for Search) ---

async def analyze_and_store_song_analysis_groq(spotify_track_data: dict) -> dict:
    """Analyzes a song description (No search needed)."""
    artist = spotify_track_data.get('artists', [{}])[0].get('name', 'N/A')
    title = spotify_track_data.get('name', 'N/A')
    album = spotify_track_data.get('album', {}).get('name', 'N/A')
    
    prompt = f"""
    Analyze this song for a music app user:
    Song: {title}
    Artist: {artist}
    Album: {album}

    Output Requirement:
    Write a short, engaging description in Thai (3-4 sentences).
    Cover: Genre, Mood/Vibe, and any interesting trivia.
    Do NOT use bullet points. Write as a single paragraph.
    """

    try:
        # Use FAST_MODEL, No Search needed
        content = await _call_groq_api(FAST_MODEL, [{"role": "user", "content": prompt}], allow_search=False)
        combined_analysis = { "gemini_analysis": content } 
        await save_song_analysis_to_db(spotify_track_data, combined_analysis)
        return combined_analysis
    except Exception:
        return { "gemini_analysis": "ไม่สามารถวิเคราะห์เพลงได้ในขณะนี้ (AI Busy)" }

async def get_song_analysis_details_groq(sp_client: spotipy.Spotify, song_uri: str) -> dict:
    analysis_data = await get_song_analysis_from_db(song_uri)
    if analysis_data and 'gemini_analysis' in analysis_data:
        return analysis_data

    try:
        spotify_track_data = await get_spotify_track_data(sp_client, song_uri)
        return await analyze_and_store_song_analysis_groq(spotify_track_data)
    except Exception as e:
        logging.error(f"Failed to get details for {song_uri}: {e}")
        return {}

async def summarize_playlist_groq(sp_client: spotipy.Spotify, final_song_uris: list[str], seed_tracks: list[dict]) -> str:
    """Summarizes the playlist (No search needed)."""
    await preload_groq_details(sp_client, [{"uri": uri} for uri in final_song_uris])
    
    seed_info = "\n".join([f"- {t['name']} ({t['artists'][0]['name']})" for t in seed_tracks[:5]])
    
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
        return await _call_groq_api(FAST_MODEL, [{"role": "user", "content": prompt}], temperature=0.7, allow_search=False)
    except Exception:
        return "เพลย์ลิสต์คัดสรรพิเศษสำหรับคุณ หวังว่าจะถูกใจนะครับ!"

async def get_seed_expansion_groq(top_tracks: list[dict], user_message: str) -> list[dict]:
    """Expands seed tracks (No search needed, relies on AI knowledge)."""
    if not top_tracks: return []
    
    seed_str = json.dumps([{"artist": t['artists'][0]['name'], "title": t['name']} for t in top_tracks[:15]], ensure_ascii=False)
    
    prompt = f"""
    Analyze these seed tracks: {seed_str}
    User Context: "{user_message}"

    Goal: Suggest 20 NEW songs(Do not repeat the song) that fit the user's specific "Niche" and Context.
    
    Constraints:
    1. Output JSON ONLY. Format: list of objects with "artist", "title", "reason".
    2. Do NOT suggest songs present in the seed list.
    """

    try:
        # allow_search=False: rely on internal knowledge base
        content = await _call_groq_api(SMART_MODEL, [{"role": "user", "content": prompt}], json_mode=True, reasoning=True, allow_search=False)
        data = json.loads(_sanitize_json_string(content))
        
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list): return v
        return data if isinstance(data, list) else []

    except Exception as e:
        logging.error(f"Seed Expansion Failed: {e}")
        return []

async def rescue_lyrics_with_groq(failed_tracks: list[dict]) -> dict:
    """
    Attempts to fetch lyrics. 
    🔥 ENABLED SEARCH here to find accurate lyrics from the web.
    """
    if not failed_tracks: return {}
    
    logging.info(f"--- Groq Lyric Rescue (with Search): Processing {len(failed_tracks)} tracks ---")
    
    # Process one by one to ensure search accuracy and context
    all_lyrics = {}
    
    for t in failed_tracks:
        artist = t['artists'][0]['name']
        title = t['name']
        
        prompt = f"""
        Find the lyrics for: "{title}" by "{artist}".
        Search the web if you don't know the lyrics internally.
        
        Output JSON ONLY: {{ "lyrics": "..." }}
        If absolutely not found even after searching, return empty string in JSON.
        """
        
        try:
            # 🔥 Allow search is TRUE here!
            content = await _call_groq_api(
                SMART_MODEL, 
                [{"role": "user", "content": prompt}], 
                json_mode=True, 
                allow_search=True 
            )
            
            data = json.loads(_sanitize_json_string(content))
            lyrics = data.get("lyrics", "")
            
            if lyrics and len(lyrics) > 50:
                key = f"{artist} - {title}"
                all_lyrics[key] = lyrics
                logging.info(f"✅ Found lyrics for {title} via Web Search")
            
        except Exception as e:
            logging.error(f"Lyric search failed for {title}: {e}")
            # Skip to next song

    return all_lyrics

async def get_filler_tracks_groq(existing_tracks: list[dict], lang_guardrail: str) -> list[dict]:
    """Finds filler tracks (No search needed)."""
    seed_str = "\n".join([f"- {t['name']} ({t['artists'][0]['name']})" for t in existing_tracks[:10]])
    
    prompt = f"""
    Playlist needs more songs. Seeds:
    {seed_str}
    
    Task: Suggest 15 NEW songs.
    Constraints:
    1. Language Code: '{lang_guardrail}' (Match strict).
    2. Output JSON: {{ "filler_tracks": [ {{ "artist": "...", "track": "...", "reason": "..." }} ] }}
    """

    try:
        content = await _call_groq_api(SMART_MODEL, [{"role": "user", "content": prompt}], json_mode=True, reasoning=True, allow_search=False)
        data = json.loads(_sanitize_json_string(content))
        return data.get("filler_tracks", [])
    except Exception:
        return []

async def get_emotional_profile_from_groq(user_message: str) -> dict:
    """Analyzes user sentiment (No search needed)."""
    prompt = f"""
    Analyze request: "{user_message}"
    Map to emotions (0.0-1.0): [joy, sadness, anger, fear, excitement, love, optimism, neutral]
    Output JSON ONLY: {{ "joy": 0.5, ... }}
    """
    try:
        content = await _call_groq_api(FAST_MODEL, [{"role": "user", "content": prompt}], json_mode=True, temperature=0.2, allow_search=False)
        return json.loads(_sanitize_json_string(content))
    except Exception:
        return {}

async def preload_groq_details(sp_client: spotipy.Spotify, tracks: list[dict]):
    """Preloads song analysis (Parallel)."""
    if not tracks: return
    try:
        tasks = [get_song_analysis_details_groq(sp_client, t['uri']) for t in tracks if t.get('uri')]
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logging.error(f"Preload failed: {e}")

async def translate_lyrics_to_english_groq(lyrics: str, artist: str, track: str) -> str:
    """Universal Translator (No search needed)."""
    short_lyrics = lyrics[:1000]

    prompt = f"""
    Act as a professional translator for music lyrics.
    Target: Translate the following lyrics into English.
    Song: "{track}" by "{artist}"
    Input:
    {short_lyrics}
    
    Rules:
    1. Translate to English if not already.
    2. OUTPUT ONLY THE ENGLISH LYRICS.
    """

    try:
        translated_text = await _call_groq_api(
            FAST_MODEL, 
            [{"role": "user", "content": prompt}], 
            temperature=0.3,
            allow_search=False
        )
        return translated_text.strip()
    except Exception as e:
        logging.error(f"Universal Translation failed for {track}: {e}")
        return lyrics