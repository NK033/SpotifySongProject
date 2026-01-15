# main.py (New Architecture)
import asyncio
import json
import os
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
from recommender import get_intelligent_recommendations, get_mood_profile_from_message
from lastfm_api import get_chart_top_tracks
from fastapi import BackgroundTasks
from recommender import get_intelligent_recommendations, update_user_profile_background
from gemini_ai import get_song_analysis_details, summarize_playlist,get_emotional_profile_from_gemini,get_gemini_seed_expansion
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
    get_song_analysis_details_groq, summarize_playlist_groq, get_emotional_profile_from_groq
)
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
from database import add_pinned_playlist, get_pinned_playlists_by_user, get_user_mood_profile, init_db, save_user_feedback
# (ลบ ChatRequest, ChatResponse ออกจากบรรทัดนี้ เพราะย้ายไปข้างบนแล้ว)
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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

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

    token_info = {
        "access_token": access_token,
        "expires_at": int(x_expires_at) if x_expires_at else 0,
        "scope": SPOTIFY_SCOPES
    }
    

    if x_refresh_token:
        token_info["refresh_token"] = x_refresh_token
    
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
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    chat_request: ChatRequest, 
    background_tasks: BackgroundTasks, 
    sp_client: spotipy.Spotify = Depends(get_spotify_client)
):
    global IS_SYSTEM_BUSY

    try:
        user_message = chat_request.message
        
        # --- (ส่วน Intent Classification - แปลงเป็น Groq) ---
        intent = ""
        if chat_request.intent:
            intent = chat_request.intent.strip().casefold()
            logging.info(f"User Intent (from Frontend): '{intent}'")
        else:
            # ใช้ Groq วิเคราะห์ Intent (แทน gemini-3-pro-preview)
            intent_prompt = f"""Analyze the user's request. What is the user's primary intent?
            Choose ONE of the following options:
            1. "get_recommendations": For PERSONALIZED suggestions based on the user's taste.
            2. "get_top_charts": If the user specifically asks for generic popular, trending, hit, or chart-topping songs.
            3. "use_a_tool": For specific actions like creating a named playlist with specific songs.
            4. "chat": For general conversation.
            User's request: "{user_message}" 
            Reply ONLY with the number (1, 2, 3, or 4)."""
            
            # ใช้ FAST_MODEL เพื่อความรวดเร็วในการเช็ค
            intent_completion = await groq_client.chat.completions.create(
                model=FAST_MODEL,
                messages=[{"role": "user", "content": intent_prompt}],
                max_tokens=10,
                temperature=0.0
            )
            intent_text = intent_completion.choices[0].message.content.strip()
            logging.info(f"User Intent (Classified by AI): '{intent_text}'")

            intent_map = {
                "1": "get_recommendations",
                "2": "get_top_charts",
                "3": "use_a_tool",
                "4": "chat"
            }
            # พยายามแมพตัวเลข ถ้าแมพไม่ได้ให้ลองดู string
            if intent_text in intent_map:
                intent = intent_map[intent_text]
            else:
                # Fallback matching
                if "recommend" in intent_text.lower(): intent = "get_recommendations"
                elif "chart" in intent_text.lower(): intent = "get_top_charts"
                elif "tool" in intent_text.lower(): intent = "use_a_tool"
                else: intent = "chat"
                
            logging.info(f"AI Translated intent to: '{intent}'")
        # --- (จบ Intent Classification) ---
        

        # --- (Path 1: Get Recommendations - คง Logic เดิม เปลี่ยนแค่ตัววิเคราะห์) ---
        if "get_recommendations" in intent:
            if not sp_client:
                return ChatResponse(response="คุณต้องเข้าสู่ระบบ Spotify ก่อนนะคะ ถึงจะแนะนำเพลงให้ได้ 😊")
            
            user_profile = await get_user_profile(sp_client)
            user_id = user_profile.get('id')

            IS_SYSTEM_BUSY = True
            try:
                # Only try this if the client actually has an auth manager (which it usually doesn't here)
                if hasattr(sp_client, "auth_manager") and sp_client.auth_manager:
                    token_info_for_bg = sp_client.auth_manager.cache_handler.get_cached_token()
                    background_tasks.add_task(update_user_profile_background, token_info_for_bg, user_id)
            except Exception as e:
                logging.warning(f"Skipping background profile update in chat: {e}")

                logging.info("Executing intelligent recommendation path (V7 - Generic Bypass).") 
                
                historical_profile = await get_user_mood_profile(user_id)
                if not historical_profile:
                    logging.warning(f"No cached profile for {user_id}. Building for the first time...")
                    from recommender import build_user_mood_profile
                    historical_profile = await build_user_mood_profile(sp_client, user_id)
                    if not historical_profile:
                        return ChatResponse(response="ขออภัยค่ะ ฉันยังหาเพลงที่เหมาะกับคุณไม่เจอ ลองฟังเพลงใน Spotify เพิ่มอีกสักหน่อยนะคะ")

                # --- ตรรกะ "Bypass" (ใช้ Groq แทน) ---
                generic_prompts = ["🎵 แนะนำเพลงส่วนตัวให้หน่อย", "แนะนำเพลง", "เพลงแนะนำ", "ขอเพลงหน่อย", "หาเพลง"]
                emotional_profile = {} 
                
                if user_message in generic_prompts:
                    logging.info(f"Generic request detected. Using PURE User Taste Profile.")
                else:
                    logging.info(f"Specific request detected. Analyzing request emotion...")
                    # ✅ เปลี่ยนตรงนี้: ใช้ Groq วิเคราะห์อารมณ์แทน
                    emotional_profile = await get_emotional_profile_from_groq(user_message)
                
                # --- เรียก Recommender ---
                recommended_songs = await get_intelligent_recommendations(
                    sp_client, user_id, 
                    historical_profile, 
                    emotional_profile, 
                    user_message
                )

                if not recommended_songs:
                    return ChatResponse(response="ขออภัยค่ะ ฉันยังไม่สามารถหาเพลงที่เหมาะกับคุณได้ในตอนนี้")

                # --- Presentation (ใช้ Groq เขียนคำโปรย) ---
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
                # ✅ ใช้ Groq (FAST_MODEL) เขียนคำตอบ
                final_response = await groq_client.chat.completions.create(
                    model=FAST_MODEL,
                    messages=[{"role": "user", "content": presentation_prompt}]
                )
                return ChatResponse(response=final_response.choices[0].message.content, songs_found=recommended_songs)
            
            finally:
                IS_SYSTEM_BUSY = False
        

        # --- (Path 2: Top Charts - คง Logic เดิม เปลี่ยนแค่ Presentation) ---
        elif "get_top_charts" in intent:
            if not sp_client:
                return ChatResponse(response="คุณต้องเข้าสู่ระบบ Spotify ก่อนนะคะ ถึงจะดูชาร์ตได้ 😊")
            logging.info("Executing top charts path.")
            
            # (Logic เดิมของคุณ)
            user_profile = await get_user_profile(sp_client)
            user_country = user_profile.get("country", "US")
            
            # ต้องมั่นใจว่า function นี้มีอยู่ (ถ้าไม่มีในไฟล์นี้ ต้อง import มา)
            # จากบริบทไฟล์เก่าคุณน่าจะมี function นี้อยู่แล้ว
            chart_tracks_info = await get_chart_top_tracks(user_country) 
            
            if not chart_tracks_info:
                return ChatResponse(response="ขออภัยค่ะ ตอนนี้ฉันไม่สามารถดึงข้อมูลเพลงฮิตได้")
            
            chart_songs_on_spotify = []
            for track_info in chart_tracks_info:
                query = f"track:{track_info['title']} artist:{track_info['artist']}"
                spotify_results = await search_spotify_songs(sp_client, query, limit=1)
                if spotify_results:
                    chart_songs_on_spotify.append(spotify_results[0])
            
            # ✅ ใช้ Groq เขียนคำโปรย
            songs_for_prompt = "\n".join([f"- {s['name']} by {s['artists'][0]['name']}" for s in chart_songs_on_spotify])
            presentation_prompt = f"นำเสนอรายการเพลงฮิตติดชาร์ตเหล่านี้ในภาษาที่เป็นกันเองและน่าสนใจ (ตอบเป็นภาษาไทย):\n\n{songs_for_prompt}"
            
            final_response = await groq_client.chat.completions.create(
                model=FAST_MODEL,
                messages=[{"role": "user", "content": presentation_prompt}]
            )
            return ChatResponse(response=final_response.choices[0].message.content, songs_found=chart_songs_on_spotify)


        # --- (Path 3: Tool Usage - คง Logic เดิม แต่เปลี่ยนวิธีเรียก Tool) ---
        elif "use_a_tool" in intent:
            if not sp_client:
                return ChatResponse(response="คุณต้องเข้าสู่ระบบ Spotify ก่อน ถึงจะใช้เครื่องมือนี้ได้ค่ะ")
                
            logging.info("Executing tool usage path (Groq Version).")
            
            # ✅ ใช้ Groq พร้อม Tools (ดึง GROQ_TOOLS ที่ import มา)
            tool_completion = await groq_client.chat.completions.create(
                model=SMART_MODEL, # ใช้ตัวฉลาดสำหรับเรียก Tool
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
        
        # --- (Path 4: Chat - เหมือนเดิม) ---
        if "chat" in intent:
            logging.info("Executing general chat path.")
            
            # ✅ ใช้ Groq คุยเล่น
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
        
        # 3. ถ้าเป็นเพลงใหม่ -> ดึงเนื้อเพลง + วิเคราะห์โมเดล
        lyrics = await genius_api.get_lyrics(track_info['name'], track_info['artist'])
        
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
    try:
        user_profile = await get_user_profile(sp_client)
        user_id = user_profile.get('id')
    except HTTPException:
        # ถ้ายังไม่ล็อกอิน ให้ส่งค่า default กลับไป
        default_prompts = [
            {'prompt': '🎵 แนะนำเพลงสบายๆ', 'intent': 'get_recommendations'},
            {'prompt': '📈 ขอเพลงฮิตติดชาร์ต', 'intent': 'get_top_charts'},
            {'prompt': '🎧 หาเพลงเศร้าๆ', 'intent': 'get_recommendations'},
            {'prompt': '🏃‍♂️ หาเพลงสำหรับวิ่ง', 'intent': 'get_recommendations'}
        ]
        return JSONResponse({"prompts": default_prompts})

    prompts = []
    
    # 1. Prompt แนะนำเพลงส่วนตัว (ต้องมีเสมอ)
    prompts.append({'prompt': '🎵 แนะนำเพลงส่วนตัวให้หน่อย', 'intent': 'get_recommendations'})
    prompts.append({'prompt': '📈 ขอเพลงฮิตติดชาร์ต', 'intent': 'get_top_charts'})

    try:
        # 2. Prompt จากศิลปินโปรด
        top_tracks = await get_user_top_tracks(sp_client, limit=1)
        if top_tracks and top_tracks[0]['artists']:
            top_artist_name = top_tracks[0]['artists'][0]['name']
            # (เพิ่ม intent ให้ path นี้ด้วย)
            prompts.append({'prompt': f'🎧 หาเพลงสไตล์ {top_artist_name}', 'intent': 'get_recommendations'})

        # 3. Prompt จากอารมณ์โปรด (จาก Mood Profile)
        mood_profile = await get_user_mood_profile(user_id)
        if mood_profile:
            # ค้นหาอารมณ์ที่มีค่าน้ำหนักสูงสุด (ไม่เอา neutral)
            mood_profile.pop('neutral', None) 
            top_mood = max(mood_profile, key=mood_profile.get)
            
            # แปลงชื่ออารมณ์เป็น Prompt ภาษาไทย
            mood_map = {
                'joy': {'prompt': '🎉 หาเพลงสนุกๆ', 'intent': 'get_recommendations'},
                'excitement': {'prompt': '🔥 หาเพลงมันส์ๆ', 'intent': 'get_recommendations'},
                'sadness': {'prompt': '😢 หาเพลงเศร้าๆ', 'intent': 'get_recommendations'},
                'love': {'prompt': '❤️ หาเพลงรักโรแมนติก', 'intent': 'get_recommendations'},
                'anger': {'prompt': '😡 หาเพลงดุๆ', 'intent': 'get_recommendations'},
                'fear': {'prompt': '😱 หาเพลงแนวลึกลับ', 'intent': 'get_recommendations'},
                'optimism': {'prompt': '✨ หาเพลงให้กำลังใจ', 'intent': 'get_recommendations'}
            }
            if top_mood in mood_map:
                prompts.append(mood_map[top_mood])
            else:
                prompts.append({'prompt': '💖 หาเพลงตามอารมณ์ฉัน', 'intent': 'get_recommendations'})

        # ทำให้เหลือไม่เกิน 4 prompts
        return JSONResponse({"prompts": prompts[:4]})
        
    except Exception as e:
        logging.error(f"Error generating dynamic prompts: {e}")
        # ถ้าเกิด Error ระหว่างหาข้อมูลส่วนตัว ก็ส่ง default กลับไป
        return JSONResponse({"prompts": [ 
            {'prompt': '🎵 แนะนำเพลงส่วนตัวให้หน่อย', 'intent': 'get_recommendations'}, 
            {'prompt': '📈 ขอเพลงฮิตติดชาร์ต', 'intent': 'get_top_charts'} 
        ]})
    

app.mount("/", StaticFiles(directory="my-react-playlist-app/dist", html=True), name="static-react-app")

