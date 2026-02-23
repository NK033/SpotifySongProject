# main.py (New Architecture)
import asyncio
import json
import re
import os
import random
import spotipy
import google.generativeai as genai
# (*** เพิ่ม 1: Import Tool และ FunctionCallable ***)
from google.generativeai.types import Tool, FunctionDeclaration
from groq import AsyncGroq
from fastapi import FastAPI, Header, HTTPException, Request, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.responses import RedirectResponse
import custom_model
from groq import AsyncGroq
from fastapi.staticfiles import StaticFiles
from typing import Annotated
import time
import logging
from collections import Counter
from recommender import get_intelligent_recommendations, get_mood_profile_from_message
from lastfm_api import get_chart_top_tracks, get_artist_top_tracks_lastfm, get_similar_artists_lastfm
from fastapi import BackgroundTasks
from recommender import get_intelligent_recommendations, update_user_profile_background
from pydantic import BaseModel
from typing import List
import database
import genius_api
# (*** แก้ไข: Import ChatRequest จาก models ที่อัปเดตแล้ว ***)
from models import ChatRequest, ChatResponse, FeedbackRequest, PinPlaylistRequest, UpdatePlaylistRequest
from spotify_api import SPOTIFY_SCOPES, create_spotify_client, get_user_top_tracks, get_current_playing_track
from groq_ai import (
    groq_client, SMART_MODEL, FAST_MODEL, 
    GROQ_TOOLS,  # สำคัญ! ต้องมีตัวนี้
    get_song_analysis_details_groq, summarize_playlist_groq, get_emotional_profile_from_groq,
    rescue_lyrics_with_groq # ✅ Added rescue function
, analyze_mood_intent_from_message_groq, emotions_top3_to_profile)
IS_SYSTEM_BUSY = False

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logging.getLogger('spotipy').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# --- Local Imports ---
from config import Config
from database import add_pinned_playlist, get_pinned_playlists_by_user, get_user_mood_profile, init_db, save_user_feedback, get_user_feedback_list, delete_user_feedback,get_user_feedback    # <--- NEW

from spotify_api import (
    create_spotify_client, 
    get_spotify_auth_url, 
    get_spotify_token, 
    get_user_profile,
    create_spotify_playlist,
    search_spotify_songs
)
# --- นี่คือหัวใจใหม่ของเรา ---
from recommender import (
    get_intelligent_recommendations, 
    update_user_profile_background, 
    get_mood_profile_from_message  # (Helper ที่เราเพิ่มใน recommender.py)
)

# --- Setup ---
Config.validate()
app = FastAPI()

# --- Model ใหม่สำหรับ Request สร้าง Playlist ---   
class CreatePlaylistRequest(BaseModel):
    playlist_name: str
    track_uris: List[str]

# --- Model ใหม่สำหรับ Request สรุป Playlist ---
class SummarizePlaylistRequest(BaseModel):
    song_uris: List[str]

# --- Middleware, Frontend, DB init ---
# main.py
app.add_middleware(
    CORSMiddleware,
    # allow_origins=["*"],  # ❌ Don't use "*" with credentials=True, it fails
    allow_origin_regex="https?://.*",  # ✅ This allows http://localhost, http://10.31..., everything!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event(): await init_db()

# --- Auth Endpoints (เหมือนเดิม) ---
@app.get("/spotify_login")
async def spotify_login_endpoint(): return RedirectResponse(await get_spotify_auth_url())

async def get_spotify_client(
    authorization: Annotated[str | None, Header()] = None,
    x_refresh_token: Annotated[str | None, Header(alias="X-Refresh-Token")] = None,
    x_expires_at: Annotated[str | None, Header(alias="X-Expires-At")] = None,
) -> spotipy.Spotify:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    access_token = authorization.split("Bearer ")[1]

    # ✅ 1. Check if token is expired manually to prevent crash
    now = int(time.time())
    expires_at = int(x_expires_at) if x_expires_at else 0
    
    # If expired and NO refresh token -> Reject immediately (Don't let Spotipy crash)
    if (expires_at - 60 < now) and not x_refresh_token:
        raise HTTPException(status_code=401, detail="Token expired and no refresh token provided.")

    token_info = {
        "access_token": access_token,
        "expires_at": expires_at,
        "scope": SPOTIFY_SCOPES
    }

    # ✅ 2. Always ensure the key exists (even if None) to satisfy Spotipy
    token_info["refresh_token"] = x_refresh_token if x_refresh_token else None
    
    if not token_info.get("access_token"):
         raise HTTPException(status_code=401, detail="Missing access token.")

    return create_spotify_client(token_info)


@app.get("/callback")   
# --- 1. เพิ่ม background_tasks เข้าไปในฟังก์ชัน ---
async def spotify_callback_endpoint(request: Request, code: str, background_tasks: BackgroundTasks):
    try:
        tokens = await get_spotify_token(code)
        
        # --- 2. เพิ่มส่วนการทำงานเบื้องหลัง ---
        # สร้าง client ชั่วคราวเพื่อดึง user_id
        temp_sp_client = create_spotify_client(tokens)
        user_profile = await get_user_profile(temp_sp_client)
        user_id = user_profile.get('id')

        if user_id:
            # สั่งให้เริ่มวิเคราะห์โปรไฟล์ของผู้ใช้คนนี้ทันทีในเบื้องหลัง
            logging.info(f"User {user_id} logged in. Triggering background profile analysis.")
            # แก้เป็น: ส่ง tokens (ที่เป็น dict) เข้าไปแทน
            background_tasks.add_task(update_user_profile_background, tokens, user_id)
        # --- จบส่วนการทำงานเบื้องหลัง ---

        # ส่งผู้ใช้กลับไปที่หน้าแอปหลักพร้อม token (เหมือนเดิม)
        redirect_url = f"{Config.FRONTEND_APP_URL}?access_token={tokens['access_token']}&refresh_token={tokens.get('refresh_token', '')}&expires_in={tokens['expires_in']}"
        return RedirectResponse(redirect_url)
        
    except Exception as e:
        logging.error(f"ERROR in callback: {e}")
        return RedirectResponse(f"/?error=spotify_auth_failed")


@app.get("/me")
async def get_current_user_profile(sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    # สังเกตว่าเราลบโค้ดที่จัดการกับ Header และสร้าง sp_client ออกไปทั้งหมด
    # เพราะ FastAPI และ get_spotify_client จัดการให้เราแล้ว
    profile_data = await get_user_profile(sp_client)
    if not profile_data: 
        raise HTTPException(status_code=404, detail="Could not fetch user profile")
    return profile_data

@app.post("/create_playlist")
async def create_playlist_endpoint(req: CreatePlaylistRequest, sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    # สังเกตว่าเราเปลี่ยน `authorization` เป็น `sp_client` ที่ได้จาก Depends
    try:
        playlist = await create_spotify_playlist(sp_client, req.playlist_name, req.track_uris)
        return {"playlist_info": playlist}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/feedback/status")
async def get_feedback_status_endpoint(sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    try:
        user_profile = await get_user_profile(sp_client)
        user_id = user_profile.get('id')
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Returns {'likes': [uri1, uri2], 'dislikes': [uri3]}
        return await get_user_feedback(user_id) 
    except Exception as e:
        logging.error(f"Error fetching feedback status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/feedback/history")
async def get_feedback_history_endpoint(sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    try:
        user_profile = await get_user_profile(sp_client)
        user_id = user_profile.get('id')
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")

        # 1. Get feedback from DB
        raw_feedback = await get_user_feedback_list(user_id)
        
        if not raw_feedback:
            return []

        # 2. Extract URIs to fetch details
        track_uris = [item['track_uri'] for item in raw_feedback]
        
        # 3. Fetch track details from Spotify (Batch request)
        # Split into chunks of 50 (Spotify API limit)
        tracks_details = {}
        for i in range(0, len(track_uris), 50):
            chunk = track_uris[i:i + 50]
            # Handle "spotify:track:ID" format
            clean_ids = [uri.split(":")[-1] for uri in chunk]
            try:
                response = sp_client.tracks(clean_ids)
                for track in response['tracks']:
                    if track:
                        tracks_details[track['uri']] = track
            except Exception as e:
                logging.error(f"Error fetching tracks from Spotify: {e}")

        # 4. Combine DB data with Spotify Details
        enriched_history = []
        for item in raw_feedback:
            uri = item['track_uri']
            track_info = tracks_details.get(uri)
            
            if track_info:
                enriched_history.append({
                    "uri": uri,
                    "name": track_info['name'],
                    "artist": track_info['artists'][0]['name'],
                    "album": track_info['album']['name'],
                    "image_url": track_info['album']['images'][0]['url'] if track_info['album']['images'] else None,
                    "feedback": item['feedback'], # 'like' or 'dislike'
                    "timestamp": item['timestamp']
                })
            else:
                # Fallback if Spotify fails or track not found
                enriched_history.append({
                    "uri": uri,
                    "name": "Unknown Track",
                    "artist": "Unknown Artist",
                    "feedback": item['feedback'],
                    "timestamp": item['timestamp']
                })

        return enriched_history

    except Exception as e:
        logging.error(f"Error fetching feedback history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# --- ✅ NEW: Endpoint to delete feedback ---
@app.delete("/feedback/{track_uri}")
async def delete_feedback_endpoint(track_uri: str, sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    try:
        user_profile = await get_user_profile(sp_client)
        user_id = user_profile.get('id')
        
        # In case URI is passed with colons, we might need to handle it, 
        # but usually fastapi handles path params as strings fine.
        # Just ensure we use the full URI as stored in DB.
        # If client sends "spotify:track:..." it might be tricky in URL path.
        # Ideally, pass it as query param or body, but let's assume simple string for now.
        # Better safety: Use Query param if URI contains special chars.
        pass
    except Exception as e:
        pass
    
    # Let's rewrite this to be safer with URIs using Query Parameter or Body
    return {"error": "Use DELETE /feedback with query param or body"}

@app.delete("/feedback")
async def delete_feedback_query_endpoint(track_uri: str, sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    try:
        user_profile = await get_user_profile(sp_client)
        user_id = user_profile.get('id')
        
        await delete_user_feedback(user_id, track_uri)
        return {"status": "success", "message": "Feedback removed"}
    except Exception as e:
        logging.error(f"Error removing feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Endpoint ใหม่สำหรับดึงรายละเอียดเพลง ---
@app.get("/song_details/{song_uri}")
async def song_details_endpoint(song_uri: str, sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    # ตอนนี้เราส่ง sp_client ทั้ง object ไปเลย ไม่ใช่แค่ token string
    return await get_song_analysis_details_groq(sp_client, song_uri)

# --- Endpoint ใหม่สำหรับบันทึก Feedback ---
@app.post("/feedback")
async def save_feedback_endpoint(req: FeedbackRequest, sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    try:
        # ดึงโปรไฟล์เพื่อเอา user_id
        user_profile = await get_user_profile(sp_client)
        user_id = user_profile.get('id')

        if not user_id:
            raise HTTPException(status_code=404, detail="Could not find user.")

        # บันทึก Feedback ลงฐานข้อมูล
        await save_user_feedback(user_id, req.track_uri, req.feedback)
        
        logging.info(f"Feedback saved for user {user_id}: Track {req.track_uri} -> {req.feedback}")
        
        return {"status": "success", "message": "Feedback received"}

    except Exception as e:
        logging.error(f"Error saving feedback: {e}")
        raise HTTPException(status_code=500, detail="Could not save feedback.")

# --- Endpoint ใหม่สำหรับจัดการเพลย์ลิสต์ที่ปักหมุด ---
@app.get("/pinned_playlists")
async def get_pinned_playlists_endpoint(sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    try:
        user_profile = await get_user_profile(sp_client)
        user_id = user_profile.get('id')
        if not user_id:
            raise HTTPException(status_code=404, detail="Could not find user.")
        
        pinned_playlists = await get_pinned_playlists_by_user(user_id)
        return pinned_playlists
    except Exception as e:
        logging.error(f"ERROR fetching pinned playlists: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# --- Endpoint ใหม่สำหรับปักหมุดเพลย์ลิสต์ ---
@app.post("/pin_playlist")
async def pin_playlist_endpoint(req: PinPlaylistRequest, sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    try:
        user_profile = await get_user_profile(sp_client)
        user_id = user_profile.get('id')
        if not user_id:
            raise HTTPException(status_code=404, detail="Could not find user.")
        
        await add_pinned_playlist(user_id, req.playlist_name, req.songs, req.recommendation_text)
        return {"status": "success", "message": "Playlist pinned successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Endpoint ใหม่สำหรับสรุป Playlist ---
@app.post("/summarize_playlist")
async def summarize_playlist_endpoint(req: SummarizePlaylistRequest, sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    try:
        summary = await summarize_playlist_groq(sp_client, req.song_uris, [])
        return {"summary": summary}
    except Exception as e:
        # Log a more detailed error if possible
        logging.error(f"Error in summarize_playlist_endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    
# --- Main Chat Endpoint (เวอร์ชันสมบูรณ์) ---
# (*** นี่คือฟังก์ชันที่แก้ไข ***)
# --- (*** 2. แก้ไขฟังก์ชันนี้: ***) ---


def _infer_track_country_code(track: dict) -> str | None:
    """Infer likely song country from visible script in title/artist (lightweight heuristic)."""
    if not isinstance(track, dict):
        return None

    artists = track.get("artists") or []
    artist_name = artists[0].get("name", "") if artists and isinstance(artists[0], dict) else ""
    text = f"{track.get('name', '')} {artist_name}"

    if re.search(r"[฀-๿]", text):
        return "TH"
    if re.search(r"[가-힯]", text):
        return "KR"
    if re.search(r"[぀-ヿ一-鿿]", text):
        return "JP"
    return None


async def _resolve_chart_country_strategy(sp_client: spotipy.Spotify, user_country: str) -> tuple[str, str, dict]:
    """
    Decide chart source based on user listening history:
    1) If one inferred country > 70% => use that country chart
    2) If mixed listening => use global charts
    3) If no history signal => use account country chart
    """
    try:
        top_tracks = await get_user_top_tracks(sp_client, limit=50)
    except Exception as e:
        logging.warning(f"Could not fetch top tracks for chart strategy: {e}")
        return "account_country", (user_country or "US"), {}

    if not top_tracks:
        return "account_country", (user_country or "US"), {}

    counts = Counter()
    for track in top_tracks:
        cc = _infer_track_country_code(track)
        if cc:
            counts.update([cc])

    if not counts:
        return "account_country", (user_country or "US"), {}

    dominant_country, dominant_count = counts.most_common(1)[0]
    total_classified = sum(counts.values())
    dominant_ratio = (dominant_count / total_classified) if total_classified else 0.0

    if dominant_ratio >= 0.70:
        return "dominant_country", dominant_country, {"counts": dict(counts), "dominant_ratio": dominant_ratio}

    return "global", "GLOBAL", {"counts": dict(counts), "dominant_ratio": dominant_ratio}


async def _fetch_global_chart_tracks(sp_client: spotipy.Spotify, limit: int = 20) -> list[dict]:
    global_queries = [
        "Global Top Hits",
        "Top 50 Global",
        "Viral Hits Global"
    ]
    songs = []
    seen = set()
    for q in global_queries:
        results = await search_spotify_songs(sp_client, q, limit=limit)
        for song in results or []:
            uri = song.get("uri")
            if uri and uri not in seen:
                seen.add(uri)
                songs.append(song)
            if len(songs) >= limit:
                return songs
    return songs

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    chat_request: ChatRequest, 
    background_tasks: BackgroundTasks, 
    sp_client: spotipy.Spotify = Depends(get_spotify_client)
):
    global IS_SYSTEM_BUSY

    try:
        user_message = chat_request.message
        logging.info(f"📩 Chat Endpoint Received: '{user_message}'")
        
        # --- Intent Classification ---
        intent = ""
        if chat_request.intent:
            intent = chat_request.intent.strip().casefold()
            logging.info(f"🎯 Intent (from Frontend): '{intent}'")
        else:
            intent_prompt = f"""Analyze the user's request. What is the user's primary intent?
            Choose ONE of the following options:
            1. "get_recommendations": For PERSONALIZED suggestions based on the user's taste.
            2. "get_top_charts": If the user specifically asks for generic popular, trending, hit, or chart-topping songs.
            3. "use_a_tool": For specific actions like creating a named playlist with specific songs.
            4. "chat": For general conversation.
            User's request: "{user_message}" 
            Reply ONLY with the number (1, 2, 3, or 4)."""
            
            intent_completion = await groq_client.chat.completions.create(
                model=FAST_MODEL,
                messages=[{"role": "user", "content": intent_prompt}],
                max_tokens=10,
                temperature=0.0
            )
            intent_text = intent_completion.choices[0].message.content.strip()
            logging.info(f"🤖 Intent (Classified by AI): '{intent_text}'")

            intent_map = {"1": "get_recommendations", "2": "get_top_charts", "3": "use_a_tool", "4": "chat"}
            if intent_text in intent_map:
                intent = intent_map[intent_text]
            else:
                if "recommend" in intent_text.lower(): intent = "get_recommendations"
                elif "chart" in intent_text.lower(): intent = "get_top_charts"
                elif "tool" in intent_text.lower(): intent = "use_a_tool"
                else: intent = "chat"
                
        # --- Path 1: Get Recommendations ---
        if "get_recommendations" in intent:
            logging.info("🚀 Starting Recommendation Flow...")
            if not sp_client:
                return ChatResponse(response="คุณต้องเข้าสู่ระบบ Spotify ก่อนนะคะ ถึงจะแนะนำเพลงให้ได้ 😊")
            
            user_profile = await get_user_profile(sp_client)
            user_id = user_profile.get('id')

            IS_SYSTEM_BUSY = True # <--- Set BUSY
            try:
                # Artist-only request path (Last.fm only; avoid Spotify search endpoint)
                artist_only_match = re.search(r"หาเพลงของ\s+(.+)", user_message, flags=re.IGNORECASE)
                if artist_only_match:
                    artist_query_raw = artist_only_match.group(1).strip()
                    artist_query_basic = re.sub(r"^(ศิลปิน|artist)\s+", "", artist_query_raw, flags=re.IGNORECASE).strip(" '\".,!?()[]{}")

                    artist_query_llm = artist_query_basic
                    try:
                        normalize_prompt = (
                            "Normalize this artist name so it can be searched on Last.fm.\n"
                            "Keep only the artist name, no extra words.\n"
                            "Prefer official Latin/English name if commonly used.\n"
                            "Return JSON only in this exact format: {\"artist\":\"...\"}\n\n"
                            f"Input: {artist_query_raw}"
                        )
                        normalize_completion = await groq_client.chat.completions.create(
                            model=FAST_MODEL,
                            messages=[{"role": "user", "content": normalize_prompt}]
                        )
                        normalize_text = (normalize_completion.choices[0].message.content or "").strip()
                        json_match = re.search(r"\{.*\}", normalize_text, flags=re.DOTALL)
                        if json_match:
                            parsed = json.loads(json_match.group(0))
                            normalized = (parsed.get("artist") or "").strip()
                            if normalized:
                                artist_query_llm = normalized
                    except Exception as e:
                        logging.warning(f"Artist normalization via LLM failed, fallback to basic clean: {e}")

                    lookup_candidates = []
                    for q in [artist_query_llm, artist_query_basic, artist_query_raw]:
                        q = (q or "").strip()
                        if q and q not in lookup_candidates:
                            lookup_candidates.append(q)

                    logging.info(f"🎯 Artist-only request detected: raw='{artist_query_raw}' | candidates={lookup_candidates}")

                    artist_tracks = []
                    resolved_artist = lookup_candidates[0] if lookup_candidates else artist_query_raw
                    query_used = resolved_artist
                    for q in lookup_candidates:
                        candidate_tracks = await get_artist_top_tracks_lastfm(q, limit=12)
                        if candidate_tracks:
                            artist_tracks = candidate_tracks
                            resolved_artist = q
                            query_used = q
                            break

                    if not artist_tracks:
                        similar_artists = await get_similar_artists_lastfm(query_used, limit=5)
                        for candidate_artist in similar_artists:
                            candidate_tracks = await get_artist_top_tracks_lastfm(candidate_artist, limit=12)
                            if candidate_tracks:
                                artist_tracks = candidate_tracks
                                resolved_artist = candidate_artist
                                break

                    if not artist_tracks:
                        return ChatResponse(
                            response=(
                                f"ขออภัยค่ะ ตอนนี้ยังหาเพลงของ '{artist_query_raw_raw}' จาก Last.fm ไม่เจอเลย "
                                "ลองพิมพ์ชื่อศิลปินเป็นอังกฤษ หรือระบุชื่อศิลปินอีกคนได้เลยนะคะ"
                            )
                        )

                    songs_from_lastfm_on_spotify = []
                    seen_track_uris = set()
                    for track_info in artist_tracks:
                        track_title = (track_info.get("title") or "").strip()
                        if not track_title:
                            continue

                        query = f"track:{track_title} artist:{resolved_artist}"
                        spotify_results = await search_spotify_songs(sp_client, query, limit=1)
                        if not spotify_results:
                            fallback_query = f"{track_title} {resolved_artist}"
                            spotify_results = await search_spotify_songs(sp_client, fallback_query, limit=1)

                        if spotify_results:
                            song_payload = dict(spotify_results[0])
                            song_payload["source"] = "lastfm_artist_top_tracks"
                            if song_payload.get("uri") and song_payload["uri"] not in seen_track_uris:
                                seen_track_uris.add(song_payload["uri"])
                                songs_from_lastfm_on_spotify.append(song_payload)

                        if len(songs_from_lastfm_on_spotify) >= 12:
                            break

                    if not songs_from_lastfm_on_spotify:
                        return ChatResponse(
                            response=(
                                f"เจอเพลงของ '{resolved_artist}' บน Last.fm แล้ว แต่ยังแมตช์เป็นเพลงใน Spotify ไม่ได้ตอนนี้ "
                                "ลองพิมพ์ชื่อศิลปิน/เพลงที่เฉพาะเจาะจงขึ้นอีกนิดนะคะ"
                            )
                        )

                    if resolved_artist != artist_query_raw:
                        response_msg = (
                            f"หา '{artist_query_raw}' ตรง ๆ ไม่เจอ เลยดึงเพลงของศิลปินใกล้เคียง '{resolved_artist}' มาแนะนำให้ค่ะ"
                        )
                    else:
                        response_msg = f"ได้เลยค่ะ นี่คือเพลงของ {resolved_artist} ที่เราแนะนำ"

                    return ChatResponse(response=response_msg, songs_found=songs_from_lastfm_on_spotify)

                try:
                    if hasattr(sp_client, "auth_manager") and sp_client.auth_manager:
                        token_info_for_bg = sp_client.auth_manager.cache_handler.get_cached_token()
                        background_tasks.add_task(update_user_profile_background, token_info_for_bg, user_id)
                except Exception as e:
                    logging.warning(f"Skipping background profile update in chat: {e}")

                logging.info(f"👤 User: {user_id}. Executing intelligent recommender...") 
                
                historical_profile = await get_user_mood_profile(user_id)
                if not historical_profile:
                    logging.warning(f"No cached profile for {user_id}. Building for the first time...")
                    from recommender import build_user_mood_profile
                    historical_profile = await build_user_mood_profile(sp_client, user_id)
                    if not historical_profile:
                        # Cold start: no history/profile yet -> suggest top charts
                        logging.warning("Cold start detected: user has little or no listening history. Suggesting top charts...")
                        user_profile = await get_user_profile(sp_client)
                        user_country = user_profile.get("country", "US")

                        # Try to infer preferred chart country from seed tracks language (if any)
                        try:
                            from recommender import get_seed_tracks
                            seed_tracks = await get_seed_tracks(sp_client)
                        except Exception:
                            seed_tracks = []

                        jp_re = re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF]")
                        jp_hits = 0
                        total_hits = 0
                        for t in (seed_tracks or []):
                            s = f"{t.get('name','')} {t.get('artists',[{}])[0].get('name','')}" if isinstance(t.get('artists'), list) and t.get('artists') else f"{t.get('name','')}"
                            total_hits += max(1, len(s))
                            jp_hits += len(jp_re.findall(s))
                        chart_country = "JP" if (total_hits > 0 and (jp_hits / total_hits) > 0.02) else user_country

                        chart_tracks_info = await get_chart_top_tracks(chart_country, limit=20)
                        chart_songs_on_spotify = []
                        for track_info in (chart_tracks_info or []):
                            query = f"track:{track_info['title']} artist:{track_info['artist']}"
                            spotify_results = await search_spotify_songs(sp_client, query, limit=1)
                            if spotify_results:
                                chart_songs_on_spotify.append(spotify_results[0])

                        if not chart_songs_on_spotify:
                            return ChatResponse(response="ดูเหมือนบัญชีนี้ยังมีประวัติการฟังไม่มาก เลยยังจับรสนิยมได้ไม่ชัด ลองฟังเพลงใน Spotify เพิ่มอีกสักหน่อย แล้วค่อยกลับมาขอแนะนำเพลงได้")

                        msg = (
                            "ดูเหมือนบัญชีนี้ยังมีประวัติการฟังไม่มาก เลยยังจับรสนิยมได้ไม่ชัด "
                            "ลองเริ่มจากเพลงฮิตช่วงนี้ก่อนดีไหม ถ้าชอบแนวไหนบอกได้ แล้วจะปรับให้เข้ากับรสนิยมมากขึ้น"
                        )
                        return ChatResponse(response=msg, songs_found=chart_songs_on_spotify)


                # Analyze Intent Mood (LLM, 28 emotions)
                def _topk(profile: dict, k: int = 5):
                    try:
                        return sorted([(k, float(v or 0.0)) for k, v in (profile or {}).items()], key=lambda x: x[1], reverse=True)[:k]
                    except Exception:
                        return []

                emotional_profile = {}
                intent_mood = {"is_specific": False, "emotions": [], "confidence": 0.0}

                # Always ask the router for non-artist requests; fall back to PURE taste if confidence is low
                intent_mood = await analyze_mood_intent_from_message_groq(user_message)
                intent_top = [(e.get("label"), e.get("weight")) for e in (intent_mood.get("emotions") or [])]
                logging.info(f"🎭 Intent Mood (top3): {intent_top} | is_specific={intent_mood.get('is_specific')} | conf={intent_mood.get('confidence')}")
                logging.info(f"🧠 User Taste (top): {_topk(historical_profile, 5)}")

                if intent_mood.get("is_specific") and float(intent_mood.get("confidence", 0.0) or 0.0) >= 0.55:
                    emotional_profile = emotions_top3_to_profile(intent_mood.get("emotions") or [])
                    logging.info("Specific request detected (LLM). Using blended mood/taste downstream (80/20).")
                else:
                    logging.info("Generic request detected (LLM). Using PURE User Taste Profile.")


                # --- CALL RECOMMENDER ---                # --- CALL RECOMMENDER ---
                logging.info("Calling get_intelligent_recommendations...")
                recommended_songs = await get_intelligent_recommendations(
                    sp_client, user_id, 
                    historical_profile, 
                    emotional_profile, 
                    user_message
                )

                if not recommended_songs:
                    logging.error("❌ Recommender returned EMPTY list!")
                    return ChatResponse(response="ขออภัยค่ะ ฉันยังไม่สามารถหาเพลงที่เหมาะกับคุณได้ในตอนนี้ (AI คืนค่าว่าง)")
                
                logging.info(f"✅ Recommender returned {len(recommended_songs)} songs.")

                # Presentation
                song_titles = ", ".join([f"'{s['name']}'" for s in recommended_songs])
                presentation_prompt = f"""
                As an AI Musicologist, present this playlist based on request: "{user_message}"
                Songs: {song_titles}.
                Instructions:
                1. Brief mood summary.
                2. Invite user to explore.
                3. Max 3-4 sentences.
                4. Respond in Thai only.
                """
                
                final_response = await groq_client.chat.completions.create(
                    model=FAST_MODEL,
                    messages=[{"role": "user", "content": presentation_prompt}]
                )
                return ChatResponse(response=final_response.choices[0].message.content, songs_found=recommended_songs)
            
            except Exception as e:
                logging.error(f"❌ Critical Error in Recommendation Path: {e}", exc_info=True)
                return ChatResponse(response="เกิดข้อผิดพลาดในการประมวลผลคำแนะนำเพลงค่ะ โปรดลองใหม่อีกครั้ง")
            
            finally:
                logging.info("🏁 Recommendation Flow Finished. Releasing Busy State.")
                IS_SYSTEM_BUSY = False # <--- Release BUSY
        

        # --- Path 2: Top Charts ---
        elif "get_top_charts" in intent:
            if not sp_client:
                return ChatResponse(response="คุณต้องเข้าสู่ระบบ Spotify ก่อนนะคะ ถึงจะดูชาร์ตได้ 😊")
            logging.info("Executing top charts path.")

            user_profile = await get_user_profile(sp_client)
            user_country = user_profile.get("country", "US")

            strategy, target_country, stats = await _resolve_chart_country_strategy(sp_client, user_country)
            logging.info(f"Top charts strategy={strategy}, target={target_country}, stats={stats}")

            chart_songs_on_spotify = []
            if strategy in ("dominant_country", "account_country"):
                chart_tracks_info = await get_chart_top_tracks(target_country)
                for track_info in chart_tracks_info or []:
                    query = f"track:{track_info['title']} artist:{track_info['artist']}"
                    spotify_results = await search_spotify_songs(sp_client, query, limit=1)
                    if spotify_results:
                        chart_songs_on_spotify.append(spotify_results[0])
            else:
                chart_songs_on_spotify = await _fetch_global_chart_tracks(sp_client, limit=20)

            if not chart_songs_on_spotify and strategy != "global":
                # Fallback to global when country chart retrieval/search fails
                chart_songs_on_spotify = await _fetch_global_chart_tracks(sp_client, limit=20)
                strategy = "global"

            if not chart_songs_on_spotify:
                return ChatResponse(response="ขออภัยค่ะ ตอนนี้ฉันไม่สามารถดึงข้อมูลเพลงฮิตได้")

            for track_info in chart_tracks_info:
                query = f"track:{track_info['title']} artist:{track_info['artist']}"
                spotify_results = await search_spotify_songs(sp_client, query, limit=1)
                if spotify_results:
                    song_payload = dict(spotify_results[0])
                    song_payload["is_top_chart"] = True
                    chart_songs_on_spotify.append(song_payload)
            
            songs_for_prompt = "\n".join([f"- {s['name']} by {s['artists'][0]['name']}" for s in chart_songs_on_spotify])
            presentation_prompt = f"""
            คุณคือผู้ช่วยแนะนำเพลง
            ช่วยสรุปรายการเพลงฮิตติดชาร์ตด้านล่างให้กระชับและอ่านง่าย (ตอบเป็นภาษาไทย)

            ข้อกำหนด:
            1) ยาวไม่เกิน 2 ประโยค
            2) ห้ามไล่รายชื่อเพลงทีละเพลง
            3) เน้นภาพรวมของบรรยากาศ/แนวเพลงและเหตุผลสั้น ๆ ว่าทำไมชาร์ตนี้น่าสนใจ
            4) ใช้น้ำเสียงเป็นกันเอง

            รายการเพลง:
            {songs_for_prompt}
            """
            
            final_response = await groq_client.chat.completions.create(
                model=FAST_MODEL,
                messages=[{"role": "user", "content": presentation_prompt}]
            )
            return ChatResponse(response=final_response.choices[0].message.content, songs_found=chart_songs_on_spotify)


        # --- Path 3: Tool Usage ---
        elif "use_a_tool" in intent:
            if not sp_client:
                return ChatResponse(response="คุณต้องเข้าสู่ระบบ Spotify ก่อน ถึงจะใช้เครื่องมือนี้ได้ค่ะ")
                
            logging.info("Executing tool usage path (Groq Version).")
            
            tool_completion = await groq_client.chat.completions.create(
                model=SMART_MODEL,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Use the available tools to help the user."},
                    {"role": "user", "content": user_message}
                ],
                tools=GROQ_TOOLS,
                tool_choice="auto",
                temperature=0.3
            )
            
            response_message = tool_completion.choices[0].message
            tool_calls = response_message.tool_calls
                    
            if tool_calls:
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)
                    logging.info(f"AI requested to call tool '{func_name}' with args: {func_args}")
                            
                    if func_name == "search_spotify_songs":
                        result = await search_spotify_songs(sp_client, **func_args)
                        return ChatResponse(response="นี่คือผลการค้นหาค่ะ", songs_found=result)
                    elif func_name == "create_spotify_playlist":
                        result = await create_spotify_playlist(sp_client, **func_args)
                        return ChatResponse(response=f"สร้างเพลย์ลิสต์ '{result['name']}' ให้เรียบร้อยแล้วค่ะ", playlist_info=result)
                    else:
                        logging.warning(f"AI called an unknown tool: {func_name}. Falling back to chat.")
                        intent = "chat"
            else:
                logging.warning(f"AI failed to call a tool for: '{user_message}'. Falling back to chat.")
                intent = "chat"
        
        # --- Path 4: Chat ---
        if "chat" in intent:
            logging.info("Executing general chat path.")
            
            chat_completion = await groq_client.chat.completions.create(
                model=FAST_MODEL,
                messages=[
                    {"role": "system", "content": "You are a friendly AI music assistant. Your primary conversational language is Thai. Write all explanations and conversational parts in Thai. However, you MUST use the original language for proper nouns like song titles and artist names. Do not translate these proper nouns."},
                    {"role": "user", "content": user_message}
                ]
            )

            if not chat_completion.choices[0].message.content:
                logging.error("Groq response was empty.")
                return ChatResponse(response="ขออภัยค่ะ ตอนนี้ AI ไม่สามารถสร้างคำตอบได้ ลองใหม่อีกครั้งนะคะ")

            return ChatResponse(response=chat_completion.choices[0].message.content)
    

    except Exception as e:
        logging.critical(f"!!! An unhandled exception occurred in chat_endpoint: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
    
# --- NEW ENDPOINT: To delete a pinned playlist ---
@app.delete("/pinned_playlists/{pin_id}")
async def delete_pinned_playlist_endpoint(pin_id: int, sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    try:
        user_profile = await get_user_profile(sp_client)
        user_id = user_profile.get('id')
        if not user_id:
            raise HTTPException(status_code=404, detail="Could not find user.")
        
        from database import delete_pinned_playlist # Import locally to avoid circular dependency issues
        
        success = await delete_pinned_playlist(pin_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Playlist not found or you do not have permission to delete it.")
            
        return {"status": "success", "message": "Playlist deleted successfully."}
    except Exception as e:
        logging.error(f"ERROR deleting pinned playlist: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def get_mood_notification_text(fingerprint: dict):
    """แปลงค่าอารมณ์จากตัวเลข เป็นข้อความ Notification ที่น่าสนใจ"""
    # เรียงลำดับอารมณ์จากมากไปน้อย
    sorted_emotions = sorted(fingerprint.items(), key=lambda x: x[1], reverse=True)
    
    if not sorted_emotions:
        return "🎵 เพลงนี้น่าสนใจดีนะครับ! ฟังเพลินๆ เลย"

    dominant_emotion, score = sorted_emotions[0]
    
    # Mapping อารมณ์ -> ข้อความเชิญชวน (Notification Text)
    # ตรงนี้คือ Rule-based ไม่เสีย Token Gemini
    responses = {
        'joy': "🔥 เพลงนี้เอเนอร์จี้ดีมาก! ดูคุณกำลังแฮปปี้นะ ให้ผมจัด Playlist สายปาร์ตี้ต่อเลยไหม?",
        'sadness': "💧 เพลงเศร้าจัง... ถ้าอยากระบาย ผมหาเพลงแนวอกหักมารอไว้แล้วนะ หรือจะให้ฮีลใจดี?",
        'anger': "💢 ดุดันมาก! ถ้าอยากระเบิดอารมณ์ต่อ เดี๋ยวผมจัดสายร็อคหนักๆ ให้ครับ",
        'love': "💖 อินเลิฟอยู่แน่ๆ เพลงหวานเจี๊ยบเลย สนใจ Playlist เพลงรักเพิ่มไหม?",
        'excitement': "🤩 จังหวะนี้ต้องไปให้สุด! ผมมีเพลง Hype กว่านี้แนะนำ สนใจไหม?",
        'neutral': "🌿 ฟังชิลๆ สบายๆ ดีครับ ถ้าอยากฟังยาวๆ เดี๋ยวผมจัด Playlist แนวนี้รอไว้นะ",
        'admiration': "✨ เพลงนี้ความหมายดีจังครับ ฟังแล้วรู้สึกมีกำลังใจขึ้นมาเลย",
        'fear': "😨 บรรยากาศดูหลอนๆ นะครับ... ไหวไหม? ให้เปลี่ยนแนวไหมครับ?",
        'amusement': "😄 เพลงสนุกดีนะครับ! ฟังแล้วอารมณ์ดีเลย"
    }
    
    # คืนค่าข้อความตามอารมณ์ (ถ้าไม่มีใน list ให้ใช้ default)
    return responses.get(dominant_emotion, f"เพลงนี้ให้อารมณ์ {dominant_emotion} สินะครับ น่าสนใจมาก! ลองฟังแนวนี้ต่อไหม?")

   # 2. API Endpoint หลัก (The Brain)
@app.get("/api/live-status")
async def get_live_status(sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    """
    API นี้จะถูก Frontend เรียกทุก 5 วินาที เพื่อเช็คว่าต้องเด้ง Notification ไหม
    """

    global IS_SYSTEM_BUSY # <--- 1. เรียกใช้ตัวแปร Global
    
    # ✅ 2. เช็คก่อนเลยว่ายุ่งอยู่ไหม
    if IS_SYSTEM_BUSY:
        # ถ้ากำลังยุ่ง ให้ส่งค่าว่างๆ กลับไปเลย (Frontend จะได้ไม่กวน)
        return {"is_playing": False}
    
    # 1. เช็คสถานะ Spotify (ใช้ sp_client ที่ Login แล้ว)
    # เราใช้ asyncio.to_thread เพื่อไม่ให้ Server ค้างตอนรอ Spotify ตอบกลับ
    track_info = await asyncio.to_thread(get_current_playing_track, sp_client)
    
    if not track_info:
        return {"is_playing": False}

    uri = track_info['spotify_uri']
    
    # 2. เช็ค Cache ใน Database ก่อน (เพื่อความเร็ว & ประหยัด)
    cached_analysis = await database.get_song_analysis_from_db(uri)
    
    emotional_fingerprint = {}
    
    if cached_analysis and 'mood' in cached_analysis:
        print(f"✨ Cache Hit: {track_info['name']}")
        emotional_fingerprint = cached_analysis['mood']
    else:
        print(f"🔍 Analyzing New Track: {track_info['name']}")
        
        # 3. ถ้าเป็นเพลงใหม่ -> ดึงเนื้อเพลง (Genius -> Rescue)
        lyrics = await genius_api.get_lyrics(track_info['name'], track_info['artist'])
        
        # ✅ NEW: Fallback with Groq Rescue
        if not lyrics:
            print(f"⚠️ Genius failed for '{track_info['name']}'. Attempting Groq Rescue...")
            try:
                # Construct track object compatible with rescue_lyrics_with_groq
                rescue_payload = [{
                    'name': track_info['name'],
                    'artists': [{'name': track_info['artist']}]
                }]
                rescued_data = await rescue_lyrics_with_groq(rescue_payload)
                
                # Key format matches groq_ai.py logic: f"{artist} - {title}"
                key = f"{track_info['artist']} - {track_info['name']}"
                lyrics = rescued_data.get(key)
                if lyrics:
                    print(f"✅ Groq Rescue Success for '{track_info['name']}'")
            except Exception as e:
                logging.error(f"Groq Rescue failed: {e}")

        if lyrics:
            # ใช้ Model ของคุณวิเคราะห์ (ไม่เสีย Token)
            # NEW (Good): Non-blocking
            emotional_fingerprint = await asyncio.to_thread(custom_model.predict_moods, lyrics)
            
            # บันทึกผลลง Database
            analysis_data = {
                "mood": emotional_fingerprint,
                "lyrics_snippet": lyrics[:100] + "..."
            }
            mock_track_data = {
                'uri': uri, 
                'name': track_info['name'], 
                'artists': [{'name': track_info['artist']}], 
                'album': {'name': track_info['album']}
            }
            await database.save_song_analysis_to_db(mock_track_data, analysis_data)
        else:
            # กรณีหาเนื้อเพลงไม่เจอ
            return {
                **track_info,
                "notification": "เพลงนี้เพราะดีครับ! เสียดายผมแกะเนื้อไม่ออก แต่ถ้าชอบแนวนี้ เดี๋ยวผมจัดให้ตามชื่อศิลปินเลย!"
            }

    # 4. สร้างข้อความ Notification
    noti_text = get_mood_notification_text(emotional_fingerprint)

    # ส่งข้อมูลกลับไปให้ Frontend
    return {
        "is_playing": True,
        "track_id": uri,
        "name": track_info['name'],
        "artist": track_info['artist'],
        "cover": track_info['cover'],
        "notification": noti_text, 
        "mood_data": emotional_fingerprint 
    }

# --- NEW ENDPOINT: To update (rename or change songs) a pinned playlist ---
@app.put("/pinned_playlists/{pin_id}")
async def update_pinned_playlist_endpoint(pin_id: int, req: UpdatePlaylistRequest, sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    try:
        user_profile = await get_user_profile(sp_client)
        user_id = user_profile.get('id')
        if not user_id:
            raise HTTPException(status_code=404, detail="Could not find user.")
        
        from database import update_pinned_playlist # Import locally
        import json

        songs_as_json_string = json.dumps(req.songs, ensure_ascii=False)
        
        success = await update_pinned_playlist(pin_id, user_id, req.playlist_name, songs_as_json_string)
        if not success:
            raise HTTPException(status_code=404, detail="Playlist not found or you do not have permission to edit it.")

        return {"status": "success", "message": "Playlist updated successfully."}
    except Exception as e:
        logging.error(f"ERROR updating pinned playlist: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# --- (*** แก้ไข: Endpoint นี้ต้องคืนค่าเป็น Object ***) ---
@app.get("/suggested_prompts")
async def get_suggested_prompts(sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    # fixed prompts ที่ต้องมีเสมอ
    fixed_prompts = [
        {'prompt': '🎵 แนะนำเพลงส่วนตัวให้หน่อย', 'intent': 'get_recommendations'},
        {'prompt': '📈 ขอเพลงฮิตติดชาร์ต', 'intent': 'get_top_charts'}
    ]

    # fallback สำหรับผู้ใช้ที่ยังไม่ล็อกอิน/ข้อมูลไม่พอ
    guest_pool = [
        {'prompt': '🎧 หาเพลงเศร้าๆ', 'intent': 'get_recommendations'},
        {'prompt': '🏃‍♂️ หาเพลงสำหรับวิ่ง', 'intent': 'get_recommendations'},
        {'prompt': '🔥 หาเพลงมันส์ๆ', 'intent': 'get_recommendations'},
        {'prompt': '✨ หาเพลงให้กำลังใจ', 'intent': 'get_recommendations'}
    ]

    try:
        user_profile = await get_user_profile(sp_client)
        user_id = user_profile.get('id')
    except HTTPException:
        return JSONResponse({"prompts": fixed_prompts + random.sample(guest_pool, k=2)})

    try:
        # 1) "หาเพลงของ artist" ต้องมีเสมอ (เมื่อ login)
        top_tracks = await get_user_top_tracks(sp_client, limit=20)
        artist_names = []
        seen = set()
        for track in top_tracks or []:
            for artist in track.get('artists', []):
                name = artist.get('name')
                if name and name not in seen:
                    seen.add(name)
                    artist_names.append(name)

        random.shuffle(artist_names)
        if artist_names:
            always_artist_prompt = {
                'prompt': f'🎧 หาเพลงของ {artist_names[0]}',
                'intent': 'get_recommendations'
            }
        else:
            always_artist_prompt = {
                'prompt': '🎧 หาเพลงของศิลปินที่ฉันชอบ',
                'intent': 'get_recommendations'
            }

        # 2) ช่อง dynamic อีก 1 อัน: สุ่มจาก mood top1-3 + fallback pool
        dynamic_candidates = []

        mood_profile = await get_user_mood_profile(user_id)
        if mood_profile:
            filtered = {k: v for k, v in mood_profile.items() if k != 'neutral'}
            mood_map = {
                'joy': {'prompt': '🎉 หาเพลงสนุกๆ', 'intent': 'get_recommendations'},
                'excitement': {'prompt': '🔥 หาเพลงมันส์ๆ', 'intent': 'get_recommendations'},
                'sadness': {'prompt': '😢 หาเพลงเศร้าๆ', 'intent': 'get_recommendations'},
                'love': {'prompt': '❤️ หาเพลงรักโรแมนติก', 'intent': 'get_recommendations'},
                'anger': {'prompt': '😡 หาเพลงดุๆ', 'intent': 'get_recommendations'},
                'optimism': {'prompt': '✨ หาเพลงให้กำลังใจ', 'intent': 'get_recommendations'}
            }

            ranked_moods = sorted(filtered.items(), key=lambda x: x[1], reverse=True)[:3]
            mood_prompts = [mood_map[m] for m, _ in ranked_moods if m in mood_map]
            dynamic_candidates.extend(mood_prompts)

        fallback_dynamic_pool = [
            {'prompt': '🌙 หาเพลงฟังก่อนนอน', 'intent': 'get_recommendations'},
            {'prompt': '☕ หาเพลงชิลๆ ระหว่างทำงาน', 'intent': 'get_recommendations'},
            {'prompt': '🚗 หาเพลงเปิดตอนขับรถ', 'intent': 'get_recommendations'},
            {'prompt': '💪 หาเพลงเพิ่มพลัง', 'intent': 'get_recommendations'}
        ]
        dynamic_candidates.extend(fallback_dynamic_pool)

        # dedupe + กันชน prompt ซ้ำ
        unique_candidates = []
        used = {always_artist_prompt['prompt']}
        for item in dynamic_candidates:
            label = item.get('prompt')
            if label and label not in used:
                used.add(label)
                unique_candidates.append(item)

        random.shuffle(unique_candidates)
        extra_prompt = unique_candidates[0] if unique_candidates else random.choice(guest_pool)

        return JSONResponse({"prompts": fixed_prompts + [always_artist_prompt, extra_prompt]})

    except Exception as e:
        logging.error(f"Error generating dynamic prompts: {e}")
        return JSONResponse({"prompts": fixed_prompts + random.sample(guest_pool, k=2)})


app.mount("/", StaticFiles(directory="my-react-playlist-app/dist", html=True), name="static-react-app")
