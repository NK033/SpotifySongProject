# main.py (New Architecture)
import asyncio
import json
import os
import spotipy
import google.generativeai as genai
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.responses import RedirectResponse
from typing import Annotated
import time
import logging
from recommender import get_intelligent_recommendations
from lastfm_api import get_chart_top_tracks
from fastapi import BackgroundTasks
from recommender import get_intelligent_recommendations, update_user_profile_background
from gemini_ai import get_song_analysis_details
from pydantic import BaseModel
from typing import List
from database import init_db, save_user_feedback, add_pinned_playlist, get_pinned_playlists_by_user
from models import ChatRequest, ChatResponse, FeedbackRequest, PinPlaylistRequest



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
from database import init_db
from models import ChatRequest, ChatResponse
from spotify_api import (
    create_spotify_client, 
    get_spotify_auth_url, 
    get_spotify_token, 
    get_user_profile,
    create_spotify_playlist,
    search_spotify_songs
)
# --- นี่คือหัวใจใหม่ของเรา ---
from recommender import get_intelligent_recommendations

# --- Setup ---
Config.validate()
genai.configure(api_key=Config.GEMINI_API_KEY)
app = FastAPI()

# --- Model ใหม่สำหรับ Request สร้าง Playlist ---
class CreatePlaylistRequest(BaseModel):
    playlist_name: str
    track_uris: List[str]

# --- Middleware, Frontend, DB init ---
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=FileResponse)
async def read_index(): return "index.html"

@app.on_event("startup")
async def startup_event(): await init_db()

# --- Auth Endpoints (เหมือนเดิม) ---
@app.get("/spotify_login")
async def spotify_login_endpoint(): return RedirectResponse(await get_spotify_auth_url())

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
            background_tasks.add_task(update_user_profile_background, temp_sp_client, user_id)
        # --- จบส่วนการทำงานเบื้องหลัง ---

        # ส่งผู้ใช้กลับไปที่หน้าแอปหลักพร้อม token (เหมือนเดิม)
        redirect_url = f"{Config.FRONTEND_APP_URL}?access_token={tokens['access_token']}&refresh_token={tokens.get('refresh_token', '')}&expires_in={tokens['expires_in']}"
        return RedirectResponse(redirect_url)
        
    except Exception as e:
        logging.error(f"ERROR in callback: {e}")
        return RedirectResponse(f"/?error=spotify_auth_failed")


@app.get("/me")
async def get_current_user_profile(authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split("Bearer ")[1]
    sp_client = spotipy.Spotify(auth=token)
    profile_data = await get_user_profile(sp_client)
    if not profile_data: raise HTTPException(status_code=404, detail="Could not fetch user profile")
    return profile_data

@app.post("/create_playlist")
async def create_playlist_endpoint(req: CreatePlaylistRequest, authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split("Bearer ")[1]
    sp_client = create_spotify_client({"access_token": token})
    
    try:
        playlist = await create_spotify_playlist(sp_client, req.playlist_name, req.track_uris)
        return {"playlist_info": playlist}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Endpoint ใหม่สำหรับดึงรายละเอียดเพลง ---
@app.get("/song_details/{song_uri}")
async def song_details_endpoint(song_uri: str, authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split("Bearer ")[1]

    # ฟังก์ชันนี้ถูกย้ายไป gemini_ai.py แล้ว
    details = await get_song_analysis_details(token, song_uri)
    return details

# --- Endpoint ใหม่สำหรับบันทึก Feedback ---
@app.post("/feedback")
async def save_feedback_endpoint(req: FeedbackRequest, authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401, detail="Invalid authorization header")
    
    token = authorization.split("Bearer ")[1]
    sp_client = create_spotify_client({"access_token": token})

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
async def get_pinned_playlists_endpoint(authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split("Bearer ")[1]
    sp_client = create_spotify_client({"access_token": token})
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
async def pin_playlist_endpoint(req: PinPlaylistRequest, authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split("Bearer ")[1]
    sp_client = create_spotify_client({"access_token": token})
    try:
        user_profile = await get_user_profile(sp_client)
        user_id = user_profile.get('id')
        if not user_id:
            raise HTTPException(status_code=404, detail="Could not find user.")
        
        await add_pinned_playlist(user_id, req.playlist_name, req.songs, req.recommendation_text)
        return {"status": "success", "message": "Playlist pinned successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Main Chat Endpoint (เวอร์ชันสมบูรณ์) ---
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(chat_request: ChatRequest, background_tasks: BackgroundTasks): # <-- เพิ่ม background_tasks
    try:
        user_message = chat_request.message
        token = chat_request.spotify_access_token

        intent_model = genai.GenerativeModel("gemini-1.5-flash")
        # --- Prompt ที่อัปเดตแล้วเพื่อแยกแยะเจตนา ---
        intent_prompt = f"""Analyze the user's request. What is the user's primary intent?
        Choose ONE of the following options:
        1. "get_recommendations": For PERSONALIZED suggestions based on the user's taste.
        2. "get_top_charts": If the user specifically asks for generic popular, trending, hit, or chart-topping songs.
        3. "use_a_tool": For specific actions like creating a named playlist with specific songs.
        4. "chat": For general conversation.

        User's request: "{user_message}" """
        intent_response = await intent_model.generate_content_async(intent_prompt)
        intent = intent_response.text.strip().casefold()
        logging.info(f"User Intent Classified as: '{intent}'")

        # สร้าง sp_client ไว้ล่วงหน้าหากมีการ login
        sp_client = None
        if token:
            sp_client = create_spotify_client({
                "access_token": token,
                "refresh_token": chat_request.spotify_refresh_token,
                "scope": "user-read-private playlist-modify-public", # เพิ่ม scope ที่จำเป็น
                "expires_at": chat_request.expires_at or 0
            })

       # --- PATH 1: ระบบแนะนำเพลงอัจฉริยะ (Personalized) ---
        if "get_recommendations" in intent:
            if not sp_client:
                return ChatResponse(response="คุณต้องเข้าสู่ระบบ Spotify ก่อนนะคะ ถึงจะแนะนำเพลงให้ได้ 😊")
            
            user_profile = await get_user_profile(sp_client)
            user_id = user_profile.get('id')

            logging.info("Executing intelligent recommendation path.")
            recommended_songs = await get_intelligent_recommendations(sp_client, user_id)

            # --- สั่งให้อัปเดตโปรไฟล์เบื้องหลัง! ---
            if user_id:
                background_tasks.add_task(update_user_profile_background, sp_client, user_id)
            # ------------------------------------

            if not recommended_songs:
                return ChatResponse(response="ขออภัยค่ะ ฉันยังไม่สามารถหาเพลงที่เหมาะกับคุณได้ในตอนนี้")

             # --- Prompt ใหม่: ปรับโทนให้ Professional ---
            presentation_model = genai.GenerativeModel("gemini-1.5-flash")
            song_titles = ", ".join([f"'{s['name']}'" for s in recommended_songs])
            
            presentation_prompt = f"""
            As an AI Musicologist, your task is to present a recommended playlist to the user.
            
            The playlist is based on the user's listening habits and contains the following tracks: {song_titles}.
            
            Instructions:
            1.  Start with a concise, professional opening.
            2.  Briefly summarize the overall mood or theme of the playlist (e.g., "upbeat and energetic," "introspective and melancholic," "a mix of modern rock and classic indie").
            3.  Conclude by inviting the user to explore the songs further using the "Details" button for each track.
            4.  Keep the entire response to a maximum of 3-4 sentences.
            5.  Respond in Thai only.
            """
            final_response = await presentation_model.generate_content_async(presentation_prompt)
            return ChatResponse(response=final_response.text, songs_found=recommended_songs)

        # --- PATH 2: ขอเพลงฮิตติดชาร์ต (Top Charts) ---
        elif "get_top_charts" in intent:
            if not sp_client:
                return ChatResponse(response="คุณต้องเข้าสู่ระบบ Spotify ก่อนนะคะ ถึงจะสร้างเพลย์ลิสต์ได้ 😊")
            
            logging.info("Executing top charts path.")
            user_profile = await get_user_profile(sp_client)
            user_country = user_profile.get("country", "US")
            
            chart_tracks_info = await get_chart_top_tracks(user_country)

            if not chart_tracks_info:
                return ChatResponse(response="ขออภัยค่ะ ตอนนี้ฉันไม่สามารถดึงข้อมูลเพลงฮิตได้")
            
            chart_songs_on_spotify = []
            for track_info in chart_tracks_info:
                query = f"track:{track_info['title']} artist:{track_info['artist']}"
                spotify_results = await search_spotify_songs(sp_client, query, limit=1)
                if spotify_results:
                    chart_songs_on_spotify.append(spotify_results[0])
            
            presentation_model = genai.GenerativeModel("gemini-1.5-flash")
            songs_for_prompt = "\n".join([f"- {s['name']} by {s['artists'][0]['name']}" for s in chart_songs_on_spotify])
            presentation_prompt = f"นำเสนอรายการเพลงฮิตติดชาร์ตเหล่านี้ในภาษาที่เป็นกันเองและน่าสนใจ (ตอบเป็นภาษาไทย):\n\n{songs_for_prompt}"
            final_response = await presentation_model.generate_content_async(presentation_prompt)
            return ChatResponse(response=final_response.text, songs_found=chart_songs_on_spotify)

        # --- PATH 3: การใช้เครื่องมือ (Tool Usage) ---
        elif "use_a_tool" in intent:
            if not sp_client:
                return ChatResponse(response="คุณต้องเข้าสู่ระบบ Spotify ก่อน ถึงจะใช้เครื่องมือนี้ได้ค่ะ")

            logging.info("Executing tool usage path.")
            tool_model = genai.GenerativeModel("gemini-1.5-flash")
            available_tools = [search_spotify_songs, create_spotify_playlist]
            
            prompt_context = "[System Context]\nThe user is logged in.\n[/System Context]\n\n"
            tool_prompt = f'{prompt_context}User\'s request: "{user_message}"'
            tool_response = await tool_model.generate_content_async(tool_prompt, tools=available_tools)
            
            response_payload = {}
            
            if (tool_response.candidates and tool_response.candidates[0].content.parts[0].function_call):
                function_call = tool_response.candidates[0].content.parts[0].function_call
                tool_name, tool_args = function_call.name, {k: v for k, v in function_call.args.items()}
                logging.info(f"AI requested to call tool '{tool_name}' with args: {tool_args}")
                
                if tool_name == "search_spotify_songs":
                    result = await search_spotify_songs(sp_client, **tool_args)
                    response_payload = {"response": "นี่คือผลการค้นหาค่ะ", "songs_found": result}
                elif tool_name == "create_spotify_playlist":
                    result = await create_spotify_playlist(sp_client, **tool_args)
                    response_payload = {"response": f"สร้างเพลย์ลิสต์ '{result['name']}' ให้เรียบร้อยแล้วค่ะ", "playlist_info": result}
            else:
                response_payload = {"response": tool_response.text or "ขออภัยค่ะ ฉันไม่เข้าใจคำสั่ง ลองระบุให้ชัดเจนขึ้นนะคะ"}
            
            return ChatResponse(**response_payload)

        # --- PATH 4: การสนทนาทั่วไป (General Chat) ---
        else:
            logging.info("Executing general chat path.")
            chat_model = genai.GenerativeModel(
                "gemini-1.5-flash",
                system_instruction="You are a friendly AI music assistant. Your primary conversational language is Thai. Write all explanations and conversational parts in Thai. However, you MUST use the original language for proper nouns like song titles and artist names (e.g., 'Butter' by BTS, 'ดีใจด้วยนะ' by อิ้งค์ วรันธร). Do not translate these proper nouns.",
            )
            chat_response = await chat_model.generate_content_async(user_message)

            if not chat_response.text:
                logging.error("Gemini response was empty or blocked.")
                return ChatResponse(response="ขออภัยค่ะ ตอนนี้ AI ไม่สามารถสร้างคำตอบได้ ลองใหม่อีกครั้งนะคะ")

            return ChatResponse(response=chat_response.text)
            
    except Exception as e:
        logging.critical(f"!!! An unhandled exception occurred in chat_endpoint: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")