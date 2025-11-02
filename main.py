# main.py (New Architecture)
import asyncio
import json
import os
import spotipy
import google.generativeai as genai
from fastapi import FastAPI, Header, HTTPException, Request, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.responses import RedirectResponse

from fastapi.staticfiles import StaticFiles
from typing import Annotated
import time
import logging
from recommender import get_intelligent_recommendations
from lastfm_api import get_chart_top_tracks
from fastapi import BackgroundTasks
from recommender import get_intelligent_recommendations, update_user_profile_background
from gemini_ai import get_song_analysis_details, summarize_playlist
from pydantic import BaseModel
from typing import List
from database import get_user_mood_profile, init_db, save_user_feedback, add_pinned_playlist, get_pinned_playlists_by_user
from models import ChatRequest, ChatResponse, FeedbackRequest, PinPlaylistRequest
from spotify_api import SPOTIFY_SCOPES, create_spotify_client, get_user_top_tracks
from models import UpdatePlaylistRequest


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
    
    # ลบค่า None ออกไปก่อนส่งให้ Spotipy <-- ต้องลบหรือยกเลิกโค้ดส่วนนี้!
    # token_info = {k: v for k, v in token_info.items() if v is not None} <--- ลบทิ้ง
    
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
            background_tasks.add_task(update_user_profile_background, temp_sp_client, user_id)
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
    details = await get_song_analysis_details(sp_client, song_uri)
    return details

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
        summary = await summarize_playlist(sp_client, req.song_uris)
        return {"summary": summary}
    except Exception as e:
        # Log a more detailed error if possible
        logging.error(f"Error in summarize_playlist_endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    
# --- Main Chat Endpoint (เวอร์ชันสมบูรณ์) ---
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    chat_request: ChatRequest, 
    background_tasks: BackgroundTasks, 
    sp_client: spotipy.Spotify = Depends(get_spotify_client)
):
    try:
        user_message = chat_request.message
        

        intent_model = genai.GenerativeModel("gemini-2.0-flash")
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

        

        if "get_recommendations" in intent:
            if not sp_client:
                return ChatResponse(response="คุณต้องเข้าสู่ระบบ Spotify ก่อนนะคะ ถึงจะแนะนำเพลงให้ได้ 😊")
            
            user_profile = await get_user_profile(sp_client)
            user_id = user_profile.get('id')

            # --- สั่งให้อัปเดตโปรไฟล์เบื้องหลัง (ย้ายมาทำก่อน) ---
            # เพื่อให้โปรไฟล์สดใหม่อยู่เสมอสำหรับการใช้งานครั้งถัดไป
            user_id = user_profile.get('id')
            if user_id and sp_client.auth_manager.cache_handler.get_cached_token():
                token_info_for_bg = sp_client.auth_manager.cache_handler.get_cached_token()
                background_tasks.add_task(update_user_profile_background, token_info_for_bg, user_id)
            # ------------------------------------

            logging.info("Executing intelligent recommendation path.")
            
            # --- (หัวใจของการแก้ไข) พยายามดึงโปรไฟล์ที่คำนวณไว้แล้วจาก DB ก่อน ---
            from database import get_user_mood_profile # Import เฉพาะจุด
            cached_mood_profile = await get_user_mood_profile(user_id)

            if not cached_mood_profile:
                logging.warning(f"No cached profile for {user_id}. Building for the first time...")
                # ถ้าไม่เจอจริงๆ (เช่น user ใหม่) ค่อยสร้างสดๆ เป็นครั้งแรก
                from recommender import build_user_mood_profile
                cached_mood_profile = await build_user_mood_profile(sp_client, user_id)
                if not cached_mood_profile:
                     return ChatResponse(response="ขออภัยค่ะ ฉันยังหาเพลงที่เหมาะกับคุณไม่เจอ ลองฟังเพลงใน Spotify เพิ่มอีกสักหน่อยนะคะ")

            # --- ส่งโปรไฟล์ที่ "เตรียมไว้แล้ว" เข้าไปในฟังก์ชันแนะนำเพลง ---
            # หมายเหตุ: เราอาจจะต้องไปแก้ get_intelligent_recommendations ให้รับ mood_profile เข้าไปด้วย
            recommended_songs = await get_intelligent_recommendations(sp_client, user_id, cached_mood_profile)


            if not recommended_songs:
                return ChatResponse(response="ขออภัยค่ะ ฉันยังไม่สามารถหาเพลงที่เหมาะกับคุณได้ในตอนนี้")

             # --- Prompt ใหม่: ปรับโทนให้ Professional ---
            presentation_model = genai.GenerativeModel("gemini-2.0-flash")
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
            
            presentation_model = genai.GenerativeModel("gemini-2.0-flash")
            songs_for_prompt = "\n".join([f"- {s['name']} by {s['artists'][0]['name']}" for s in chart_songs_on_spotify])
            presentation_prompt = f"นำเสนอรายการเพลงฮิตติดชาร์ตเหล่านี้ในภาษาที่เป็นกันเองและน่าสนใจ (ตอบเป็นภาษาไทย):\n\n{songs_for_prompt}"
            final_response = await presentation_model.generate_content_async(presentation_prompt)
            return ChatResponse(response=final_response.text, songs_found=chart_songs_on_spotify)

        # --- PATH 3: การใช้เครื่องมือ (Tool Usage) ---
        elif "use_a_tool" in intent:
            if not sp_client:
                return ChatResponse(response="คุณต้องเข้าสู่ระบบ Spotify ก่อน ถึงจะใช้เครื่องมือนี้ได้ค่ะ")

            logging.info("Executing tool usage path.")
            tool_model = genai.GenerativeModel("gemini-2.0-flash")
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
                "gemini-2.0-flash",
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

@app.get("/suggested_prompts")
async def get_suggested_prompts(sp_client: spotipy.Spotify = Depends(get_spotify_client)):
    try:
        user_profile = await get_user_profile(sp_client)
        user_id = user_profile.get('id')
    except HTTPException:
        # ถ้ายังไม่ล็อกอิน ให้ส่งค่า default กลับไป
        default_prompts = [
            '🎵 แนะนำเพลงสบายๆ',
            '📈 ขอเพลงฮิตติดชาร์ต',
            '🎧 หาเพลงเศร้าๆ',
            '🏃‍♂️ หาเพลงสำหรับวิ่ง'
        ]
        return JSONResponse({"prompts": default_prompts})

    prompts = []
    
    # 1. Prompt แนะนำเพลงส่วนตัว (ต้องมีเสมอ)
    prompts.append('🎵 แนะนำเพลงส่วนตัวให้หน่อย')
    prompts.append('📈 ขอเพลงฮิตติดชาร์ต')

    try:
        # 2. Prompt จากศิลปินโปรด
        top_tracks = await get_user_top_tracks(sp_client, limit=1)
        if top_tracks and top_tracks[0]['artists']:
            top_artist_name = top_tracks[0]['artists'][0]['name']
            prompts.append(f'🎧 หาเพลงสไตล์ {top_artist_name}')

        # 3. Prompt จากอารมณ์โปรด (จาก Mood Profile)
        mood_profile = await get_user_mood_profile(user_id)
        if mood_profile:
            # ค้นหาอารมณ์ที่มีค่าน้ำหนักสูงสุด (ไม่เอา neutral)
            mood_profile.pop('neutral', None) 
            top_mood = max(mood_profile, key=mood_profile.get)
            
            # แปลงชื่ออารมณ์เป็น Prompt ภาษาไทย
            mood_map = {
                'joy': '🎉 หาเพลงสนุกๆ',
                'excitement': '🔥 หาเพลงมันส์ๆ',
                'sadness': '😢 หาเพลงเศร้าๆ',
                'love': '❤️ หาเพลงรักโรแมนติก',
                'anger': '😡 หาเพลงดุๆ',
                'fear': '😱 หาเพลงแนวลึกลับ',
                'optimism': '✨ หาเพลงให้กำลังใจ'
            }
            if top_mood in mood_map:
                prompts.append(mood_map[top_mood])
            else:
                prompts.append('💖 หาเพลงตามอารมณ์ฉัน')

        # ทำให้เหลือไม่เกิน 4 prompts
        return JSONResponse({"prompts": prompts[:4]})
        
    except Exception as e:
        logging.error(f"Error generating dynamic prompts: {e}")
        # ถ้าเกิด Error ระหว่างหาข้อมูลส่วนตัว ก็ส่ง default กลับไป
        return JSONResponse({"prompts": [ '🎵 แนะนำเพลงส่วนตัวให้หน่อย', '📈 ขอเพลงฮิตติดชาร์ต' ]})
    

app.mount("/", StaticFiles(directory="my-react-playlist-app/dist", html=True), name="static-react-app")