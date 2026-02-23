# groq_ai.py (Optimized & Patched: Custom Model + Whitelist Fix)
import logging
import json
import asyncio
import re
import spotipy
from groq import AsyncGroq
from fastapi import HTTPException, status
from typing import Any, Optional, List, Dict
from ddgs import DDGS # ✅ Optimized: Use new package name

# Import Local Modules
from config import Config
from database import save_song_analysis_to_db, get_song_analysis_from_db
from spotify_api import get_spotify_track_data
from custom_model import predict_moods
from genius_api import get_lyrics # ✅ Added: Needed for primary lyrics

# --- 1. Setup Groq Client & Models ---
if not Config.GROQ_API_KEY:
    logging.warning("⚠️ GROQ_API_KEY is missing. AI features will fail.")

groq_client = AsyncGroq(api_key=Config.GROQ_API_KEY)

# SMART_MODEL: For Logic, JSON, Search
SMART_MODEL = "openai/gpt-oss-120b" 

# FAST_MODEL: For Creative writing, Summaries
FAST_MODEL = "llama-3.3-70b-versatile"

# 🔥 [RESTORED] GROQ_TOOLS (Essential for main.py)
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
    Real web search using DuckDuckGo.
    """
    try:
        logging.info(f"🔎 Searching Web for: {query}")
        results = DDGS().text(query, max_results=3) # ✅ Optimized: ddgs
        if not results:
            return "No results found."
        
        summary = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
        return summary
    except Exception as e:
        return f"Search failed: {e}"

# --- 3. Robust Helpers ---
def _clean_lyrics(text: str) -> str:
    """
    Cleaner + Flattening:
    1. Remove tags [Intro], [Verse]
    2. Remove markdown
    3. Flatten all newlines to single spaces
    """
    if not text: return ""
    text = re.sub(r'\[.*?\]', ' ', text)
    text = re.sub(r'\(.*?\)', ' ', text)
    text = re.sub(r'^```(lyrics|json)?', '', text, flags=re.MULTILINE)
    text = re.sub(r'```$', '', text, flags=re.MULTILINE)
    
    # 🔥 Flatten Newlines
    text = text.replace('\\n', ' ').replace('\n', ' ').replace('\r', ' ')
    text = re.sub(r'\s+', ' ', text) # ลดช่องว่างซ้ำ
    return text.strip()

def _sanitize_json_string(json_str: str) -> str:
    """Clean JSON string."""
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
    messages: List[Dict], 
    json_mode: bool = False, 
    reasoning: bool = False,
    temperature: float = 0.7,
    allow_search: bool = False
) -> str:
    """
    Central API Wrapper with Whitelist Sanitation & Tool Loop.
    """
    try:
        # 1. Define Tools
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Find lyrics, song info, or facts from the internet.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The search keywords"}
                        },
                        "required": ["query"],
                    },
                },
            }
        ] if allow_search else None

        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if json_mode and not tools:
            params["response_format"] = {"type": "json_object"}
        
        if tools: 
            params["tools"] = tools
            params["tool_choice"] = "auto"
        else:
            params["tool_choice"] = "none"

        # Reasoning effort (Only for 120b)
        if reasoning and "gpt-oss-120b" in model:
            params["reasoning_effort"] = "medium"
            params["temperature"] = 1.0 

        # --- Round 1: Initial Request ---
        response = await groq_client.chat.completions.create(**params)
        response_message = response.choices[0].message
        
        # 2. Check for Tool Calls
        tool_calls = response_message.tool_calls
        
        if tool_calls:
            # ✅ FIX: Whitelist Sanitation (Prevents 120b -> 70b crashes)
            response_dict = response_message.model_dump()
            SAFE_KEYS = ["role", "content", "tool_calls", "tool_call_id", "name"]
            clean_message = {k: v for k, v in response_dict.items() if k in SAFE_KEYS}
            
            messages.append(clean_message) 
            
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                
                if function_name == "search_web":
                    tool_output = await asyncio.to_thread(search_web, **function_args)
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": "search_web",
                        "content": tool_output,
                    })
            
            # --- Round 2: Final Response Generation ---
            # Switch to Fast Model (Llama 3) for stability
            params_round_2 = {
                "model": FAST_MODEL,
                "messages": messages,
                "temperature": 0.6,
            }

            if json_mode:
                params_round_2["response_format"] = {"type": "json_object"}

            messages.append({
                "role": "system",
                "content": "Search is complete. Use the provided results to answer immediately. Do not search again."
            })
            
            final_response = await groq_client.chat.completions.create(**params_round_2)
            return final_response.choices[0].message.content
            
        else:
            return response_message.content

    except Exception as e:
        logging.error(f"❌ Groq API Call Failed ({model}): {e}", exc_info=True)
        return ""

# --- 4. Core Functions ---

async def analyze_and_store_song_analysis_groq(spotify_track_data: dict) -> dict:
    """
    Analyzes a song: Lyrics -> Score -> Description -> Save.
    """
    artist = spotify_track_data.get('artists', [{}])[0].get('name', 'N/A')
    title = spotify_track_data.get('name', 'N/A')
    album = spotify_track_data.get('album', {}).get('name', 'N/A')
    
    # ✅ 1. Get Lyrics (Genius -> Rescue)
    lyrics = await get_lyrics(artist, title)
    
    if not lyrics:
        rescued_data = await rescue_lyrics_with_groq([spotify_track_data])
        key = f"{artist} - {title}"
        lyrics = rescued_data.get(key, "")

    # ✅ 2. Score Moods (Local AI)
    mood_scores = {}
    if lyrics and len(lyrics) > 50:
        try:
            mood_scores = await asyncio.to_thread(predict_moods, lyrics)
        except Exception as e:
            logging.error(f"Mood prediction failed: {e}")

    # 3. Describe (Groq AI)
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
        content = await _call_groq_api(FAST_MODEL, [{"role": "user", "content": prompt}], allow_search=False)
        
        # ✅ 4. Save Everything
        combined_analysis = { 
            "Details": content,
            "predicted_moods": mood_scores,
            "lyrics": lyrics
        } 
        await save_song_analysis_to_db(spotify_track_data, combined_analysis)
        return combined_analysis
    except Exception:
        return { "Details": "ไม่สามารถวิเคราะห์เพลงได้ในขณะนี้ (AI Busy)" }

async def get_song_analysis_details_groq(sp_client: spotipy.Spotify, song_uri: str) -> dict:
    analysis_data = await get_song_analysis_from_db(song_uri)
    if analysis_data and 'Details' in analysis_data:
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
    Rescue lyrics AND Normalize to English.

    NOTE:
    - Uses web search tool for retrieval (allow_search=True)
    - DOES NOT use json_mode to avoid Groq tool-call validation issues (e.g. model attempting to call a non-existent tool like "JSON")
    """
    if not failed_tracks:
        return {}

    logging.info(f"--- Groq Lyric Rescue: Processing {len(failed_tracks)} tracks ---")
    all_lyrics: dict[str, str] = {}

    for t in failed_tracks:
        artist = t['artists'][0]['name']
        title = t['name']

        # Skip tracks that almost certainly have no lyrics
        low_title = (title or "").lower()
        if any(k in low_title for k in ["instrumental", "karaoke", "off vocal", "inst.", "inst ver", "instrumental ver"]):
            continue

        # Prompt: return plain text only (fast + robust)
        prompt = f"""Task: Find the lyrics for \"{title}\" by \"{artist}\".

CRITICAL INSTRUCTION (DATA NORMALIZATION):
To ensure compatibility with our Emotion Analysis Engine, you MUST normalize the lyrics to ENGLISH.

Rules:
1. If the song is already in English -> return original lyrics.
2. If the song is NOT English (e.g., Japanese, Thai) -> return ENGLISH TRANSLATION.
3. ❌ NO ROMAJI.
4. If you cannot find lyrics, return exactly: NO_LYRICS
5. Return ONLY the lyrics text (no JSON, no explanations)."""

        try:
            content = await _call_groq_api(
                SMART_MODEL,
                [{"role": "user", "content": prompt}],
                json_mode=False,
                allow_search=True
            )

            if not content:
                continue

            text = content.strip()

            # If the model still returns JSON, try to parse it safely.
            if text.startswith("{") and "lyrics" in text:
                try:
                    data = json.loads(_sanitize_json_string(text))
                    text = (data.get("lyrics") or "").strip()
                except Exception:
                    pass

            if text == "NO_LYRICS":
                continue

            cleaned_lyrics = _clean_lyrics(text)

            if cleaned_lyrics and len(cleaned_lyrics) > 20:
                key = f"{artist} - {title}"
                all_lyrics[key] = cleaned_lyrics
                logging.info(f"✅ Rescue & Normalize Success: {title}")

        except Exception as e:
            logging.error(f"Rescue failed for {title}: {e}")

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


# --- Flexible Recommendation Router (LLM) ---
EMOTION_LABELS_28 = [
    "admiration", "amusement", "anger", "annoyance", "approval", "caring",
    "confusion", "curiosity", "desire", "disappointment", "disapproval", "disgust",
    "embarrassment", "excitement", "fear", "gratitude", "grief", "joy", "love",
    "nervousness", "optimism", "pride", "realization", "relief", "remorse",
    "sadness", "surprise", "neutral",
]

def emotions_top3_to_profile(emotions: list[dict]) -> dict:
    """Convert top-3 emotions list into a full 28-dim emotion profile dict."""
    profile = {k: 0.0 for k in EMOTION_LABELS_28}
    if not emotions:
        profile["neutral"] = 1.0
        return profile

    # Normalize / clamp weights
    cleaned = []
    for e in emotions[:3]:
        label = str(e.get("label", "")).strip().casefold()
        if label not in profile:
            continue
        try:
            w = float(e.get("weight", 0.0))
        except Exception:
            w = 0.0
        w = max(0.0, min(1.0, w))
        cleaned.append((label, w))

    if not cleaned:
        profile["neutral"] = 1.0
        return profile

    s = sum(w for _, w in cleaned)
    if s <= 0:
        profile["neutral"] = 1.0
        return profile

    for label, w in cleaned:
        profile[label] = w / s

    return profile

async def route_recommendation_request_groq(user_message: str) -> dict:
    """Routes recommendation requests into artist/mood/general and returns top-3 emotions.

    Output JSON schema:
    {
      "route": "artist" | "mood" | "general",
      "artist_name": str | null,
      "artist_mode": "strict" | "similar" | "mix",
      "emotions": [{"label": <one-of-28>, "weight": 0-1}, ... up to 3],
      "confidence": 0-1
    }
    """
    # Keep prompt short-ish but strict.
    labels = ", ".join(EMOTION_LABELS_28)
    prompt = f"""
You are a routing classifier for a music recommendation app.

User message: "{user_message}"

Task:
1) Decide route:
- "artist": user explicitly asks for songs OF a singer/band (e.g., Thai: "เพลงของ X", "แนะนำเพลงของ X").
- "mood": user asks by mood/activity/vibe (e.g., "เศร้าๆ", "ขับรถชิลๆ", "อ่านหนังสือ").
- "general": broad request without clear artist/mood (e.g., "แนะนำเพลง").
2) If route is "artist", extract artist_name if present.
3) Decide artist_mode:
- "strict": if message implies songs OF the artist (Thai: "ของ", "จาก", "เพลงของ")
- "similar": if message implies style/similar (Thai: "สไตล์", "แนว", "คล้าย")
- "mix": if unclear.
4) Choose TOP 3 emotions from this fixed list ONLY:
[{labels}]
Return each with a weight (0..1). If uncertain, include "neutral".
5) Provide confidence (0..1).

Rules:
- Output JSON ONLY, no extra text.
- Do NOT invent new emotion labels.
- emotions must be an array length 3 (pad with neutral if needed).
"""

    try:
        content = await _call_groq_api(
            FAST_MODEL,
            [{"role": "user", "content": prompt}],
            json_mode=True,
            temperature=0.0,
            allow_search=False
        )
        data = json.loads(_sanitize_json_string(content))

        # Defensive cleanup
        route = str(data.get("route", "general")).strip().casefold()
        if route not in {"artist", "mood", "general"}:
            route = "general"

        artist_name = data.get("artist_name")
        if artist_name is not None:
            artist_name = str(artist_name).strip()
            if not artist_name:
                artist_name = None

        artist_mode = str(data.get("artist_mode", "mix")).strip().casefold()
        if artist_mode not in {"strict", "similar", "mix"}:
            artist_mode = "mix"

        emotions = data.get("emotions", [])
        if not isinstance(emotions, list):
            emotions = []

        # Ensure 3 emotions
        cleaned = []
        for e in emotions:
            if not isinstance(e, dict):
                continue
            label = str(e.get("label", "")).strip().casefold()
            if label not in EMOTION_LABELS_28:
                continue
            try:
                w = float(e.get("weight", 0.0))
            except Exception:
                w = 0.0
            w = max(0.0, min(1.0, w))
            cleaned.append({"label": label, "weight": w})
            if len(cleaned) >= 3:
                break
        while len(cleaned) < 3:
            cleaned.append({"label": "neutral", "weight": 1.0})

        try:
            conf = float(data.get("confidence", 0.5))
        except Exception:
            conf = 0.5
        conf = max(0.0, min(1.0, conf))

        return {
            "route": route,
            "artist_name": artist_name,
            "artist_mode": artist_mode,
            "emotions": cleaned,
            "confidence": conf
        }
    except Exception as e:
        logging.error(f"route_recommendation_request_groq failed: {e}")
        return {
            "route": "general",
            "artist_name": None,
            "artist_mode": "mix",
            "emotions": [{"label": "neutral", "weight": 1.0}] * 3,
            "confidence": 0.0
        }

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