# main.py (Final Hybrid Recommender System - User's Structure with Added Try/Except)
import asyncio
import json
import random
import traceback
import spotipy
from spotify_api import SPOTIFY_SCOPES, create_spotify_client, get_fallback_recommendations
import google.generativeai as genai
import numpy as np
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.responses import RedirectResponse
from typing import Annotated
import time
import logging
logging.basicConfig()
logging.getLogger('spotipy').setLevel(logging.DEBUG)
from fastapi import BackgroundTasks
from background_tasks import analyze_user_taste_profile_background
from database import get_user_mood_profile
# Local Imports
from config import Config
from database import cache_plan, get_cached_plan, init_db
from genre_maps import ARTIST_POOL_BY_LANG, DISCOVERY_SEEDS_BY_COUNTRY
from models import ChatRequest, ChatResponse
from spotify_api import (
    create_spotify_playlist,
    get_audio_features_for_tracks,
    get_spotify_auth_url,
    get_spotify_recommendations_for_discovery,
    get_spotify_token,
    get_user_profile,
    get_user_saved_tracks_uris,
    get_user_top_tracks,
    search_spotify_songs,
)
from verifier import batch_verify_songs

# --- Setup ---
Config.validate()
genai.configure(api_key=Config.GEMINI_API_KEY)
app = FastAPI()


# --- Middleware, Frontend, DB init ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=FileResponse)
async def read_index():
    return "index.html"


@app.on_event("startup")
async def startup_event():
    await init_db()


# --- Auth Endpoints ---
@app.get("/spotify_login")
async def spotify_login_endpoint():
    return RedirectResponse(await get_spotify_auth_url())


@app.get("/callback")
async def spotify_callback_endpoint(request: Request, code: str):
    try:
        tokens = await get_spotify_token(code)
        # Redirect ไปหน้าเว็บหลัก พร้อม access_token ใน query string
        redirect_url = f"{Config.FRONTEND_APP_URL}?access_token={tokens['access_token']}&refresh_token={tokens.get('refresh_token', '')}&expires_in={tokens['expires_in']}"
        return RedirectResponse(redirect_url)
    except Exception as e:
        print(f"ERROR in callback: {e}")
        return RedirectResponse(f"/?error=spotify_auth_failed")


@app.get("/me")
async def get_current_user_profile(authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split("Bearer ")[1]

    # --- ส่วนที่แก้ไข ---
    # 1. สร้าง Spotipy client จาก token ที่ได้รับมา
    sp_client = spotipy.Spotify(auth=token)
    
    # 2. ส่ง sp_client ทั้งอ็อบเจกต์เข้าไปในฟังก์ชัน ไม่ใช่แค่ token string
    profile_data = await get_user_profile(sp_client)
    # -------------------

    if not profile_data:
        raise HTTPException(
            status_code=404, detail="Could not fetch user profile from Spotify"
        )
    return profile_data


# --- Helper Functions for Recommender ---
def calculate_cosine_similarity(vec1, vec2):
    if vec1 is None or vec2 is None:
        return 0.0
    vec1, vec2 = np.array(vec1), np.array(vec2)
    norm_product = np.linalg.norm(vec1) * np.linalg.norm(vec2)
    if norm_product == 0:
        return 0.0
    return np.dot(vec1, vec2) / norm_product


async def build_user_taste_profile(sp_client: spotipy.Spotify):
    """
    สร้างโปรไฟล์รสนิยมของผู้ใช้ (เวอร์ชัน Workaround: ไม่เรียกใช้ audio-features)
    """
    # พยายามดึง Top tracks เพื่อตรวจสอบว่าผู้ใช้มีประวัติการฟังหรือไม่
    top_tracks = await get_user_top_tracks(sp_client, limit=50)
    if not top_tracks:
        print("User has no top tracks, returning None for taste profile.")
        return None
    
    # เนื่องจากบัญชีนี้มีปัญหาในการเรียก audio-features
    # เราจะคืนค่า None ไปเสมอ เพื่อให้ระบบหลักเข้าสู่ Fallback System ที่แข็งแกร่งกว่าแทน
    print("Skipping audio-features due to account restrictions. Returning None for taste profile.")
    return None

    

# --- Main Chat Endpoint ---
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(chat_request: ChatRequest, background_tasks: BackgroundTasks):
    
    try:
        user_message = chat_request.message
        token = chat_request.spotify_access_token

        # === STAGE 0: Intent Classification ===
        print("Stage 0: Classifying user intent...")
        intent_model = genai.GenerativeModel("gemini-1.5-flash")
        intent_prompt = f"""
        Analyze the user's request. What is the user's primary intent?
        Choose ONE of the following three options:
        1. "get_recommendations": If the user is asking for music suggestions, discovery, or recommendations.
        2. "use_a_tool": If the user is asking for a specific action like creating a playlist.
        3. "chat": For all other cases, like greetings, questions about you, or general conversation.

        Respond with ONLY one of these three strings.
        User's request: "{user_message}"
        """
        intent_response = await intent_model.generate_content_async(intent_prompt)
        intent = intent_response.text.strip()
        print(f"AI Intent: {intent}")
        
         # === PATH 1: Personalized Recommendation (ใช้ Fallback System ใหม่) ===
        if "get_recommendations" in intent:
            if not token:
                return ChatResponse(response="คุณต้องเข้าสู่ระบบ Spotify ก่อนนะคะ ถึงจะแนะนำเพลงให้ได้ 😊")

            try:
                # สร้าง Spotipy client และ User ID
                token_info = {
                    "access_token": token,
                    "refresh_token": chat_request.spotify_refresh_token,
                    "scope": SPOTIFY_SCOPES,
                    "expires_at": chat_request.expires_at / 1000 if chat_request.expires_at else 0
                }
                sp_client = create_spotify_client(token_info)
                user_profile_data = await get_user_profile(sp_client)
                user_id = user_profile_data.get('id')

                if not user_id:
                    return ChatResponse(response="ขออภัยค่ะ ไม่สามารถดึงข้อมูล User ID ของคุณจาก Spotify ได้")

                # ตรวจสอบว่ามี Mood Profile อยู่ในฐานข้อมูลแล้วหรือยัง
                mood_profile = await get_user_mood_profile(user_id)

                if mood_profile:
                    print(f"User profile found for {user_id}, using mood-based ranking.")
                    # TODO: ในอนาคต เราจะใส่ Logic การจัดอันดับเพลงโดยใช้ mood_profile ที่ตรงนี้
                    pass
                else:
                    print(f"User profile not found for {user_id}. Triggering background analysis.")
                    background_tasks.add_task(analyze_user_taste_profile_background, sp_client, user_id)
                
                # --- ส่วนที่แก้ไข: เรียกใช้ระบบ Fallback ใหม่ ---
                print("   --> Using smart fallback recommendation system...")
                recommended_songs = await get_fallback_recommendations(sp_client) 
                
                if not recommended_songs:
                    return ChatResponse(response="ขออภัยค่ะ มีปัญหาในการดึงเพลงแนะนำในขณะนี้ ลองใหม่อีกครั้งนะคะ")

                # --- ส่วนการนำเสนอผลลัพธ์ ---
                presentation_model = genai.GenerativeModel("gemini-1.5-flash")
                songs_for_prompt = "\n".join([f"- {s['name']} by {s['artists'][0]['name']}" for s in recommended_songs])
                presentation_prompt = f"The user asked for a general recommendation. You found these songs: {songs_for_prompt}. Present them in a friendly way in Thai. If a background task was started, you can also mention that you are analyzing their taste for next time."
                final_response = await presentation_model.generate_content_async(presentation_prompt)
                
                # ตรวจสอบว่ามีการ Refresh Token หรือไม่ก่อนส่ง Response
                new_token_info = sp_client.auth_manager.get_cached_token()
                if new_token_info and new_token_info.get("access_token") != token:
                    return ChatResponse(response=final_response.text, songs_found=recommended_songs, new_spotify_token_info=new_token_info)
                else:
                    return ChatResponse(response=final_response.text, songs_found=recommended_songs)

            except spotipy.exceptions.SpotifyException as e:
                if e.http_status in [401, 403]:
                    return ChatResponse(response="การเชื่อมต่อกับ Spotify ของคุณหมดอายุแล้ว 🕒 กรุณาลองออกจากระบบและเข้าสู่ระบบใหม่อีกครั้งครับ")
                else:
                    print(f"An unexpected Spotify error occurred: {e}")
                    return ChatResponse(response="ขออภัยค่ะ มีปัญหาในการเชื่อมต่อกับ Spotify")
                    # -------------------


        # === PATH 2: Tool Usage ===
        elif "use_a_tool" in intent:
            print("Executing: Specific Tool Usage Path")
            if not token:
                return ChatResponse(response="คุณต้องเข้าสู่ระบบ Spotify ก่อน ถึงจะใช้เครื่องมือนี้ได้ค่ะ")

            token_info = {
                "access_token": token,
                "refresh_token": chat_request.spotify_refresh_token,
                "scope": SPOTIFY_SCOPES,
                "expires_at": int(time.time()) 
            }

            try:
                sp_client = create_spotify_client(token_info)
                
                tool_model = genai.GenerativeModel("gemini-1.5-flash")
                available_tools = [search_spotify_songs, create_spotify_playlist]
                prompt_context = "[System Context]\nThe user is logged in.\n[/System Context]\n\n"
                tool_prompt = f'{prompt_context}User\'s request: "{user_message}"'
                tool_response = await tool_model.generate_content_async(tool_prompt, tools=available_tools)
                
                response_payload = {}
                
                if (tool_response.candidates and tool_response.candidates[0].content.parts[0].function_call):
                    function_call = tool_response.candidates[0].content.parts[0].function_call
                    tool_name, tool_args = function_call.name, {k: v for k, v in function_call.args.items()}
                    
                    if tool_name == "search_spotify_songs":
                        result = await search_spotify_songs(sp_client, **tool_args)
                        response_payload = {"response": "นี่คือผลการค้นหาค่ะ", "songs_found": result}
                    elif tool_name == "create_spotify_playlist":
                        result = await create_spotify_playlist(sp_client, **tool_args)
                        response_payload = {"response": f"สร้างเพลย์ลิสต์ '{result['name']}' ให้เรียบร้อยแล้วค่ะ", "playlist_info": result}
                else:
                    response_payload = {"response": tool_response.text or "ขออภัยค่ะ ฉันไม่เข้าใจคำสั่ง ลองระบุให้ชัดเจนขึ้นนะคะ"}

                new_token_info = sp_client.auth_manager.get_cached_token()
                if new_token_info and new_token_info.get("access_token") != token:
                    print("Token was refreshed, sending new token info to frontend.")
                    response_payload["new_spotify_token_info"] = new_token_info

                return ChatResponse(**response_payload)

            except spotipy.exceptions.SpotifyException as e:
                if e.http_status in [401, 403]:
                    return ChatResponse(response="การเชื่อมต่อกับ Spotify ของคุณหมดอายุแล้ว 🕒 กรุณาลองออกจากระบบและเข้าสู่ระบบใหมอีกครั้งครับ")
                else:
                    # --- ส่วนที่แก้ไข ---
                    # 1. พิมพ์ Error ที่แท้จริงออกมาใน Terminal
                    print(f"An unexpected Spotify error occurred: {e}") 
                    # 2. ตอบกลับผู้ใช้ด้วยข้อความเดิม
                    return ChatResponse(response="ขออภัยค่ะ มีปัญหาในการเชื่อมต่อกับ Spotify")
                    # -------------------

        # === PATH 3: General Chat ===
        else:  # This now correctly handles greetings and other chat
            print("Executing: General Chat Path")
            chat_model = genai.GenerativeModel(
                "gemini-1.5-flash",
                system_instruction="You are a friendly AI music assistant. Your primary conversational language is Thai. Write all explanations and conversational parts in Thai. However, you MUST use the original language for proper nouns like song titles and artist names (e.g., 'Butter' by BTS, 'ดีใจด้วยนะ' by อิ้งค์ วรันธร). Do not translate these proper nouns.",
            )
            chat_response = await chat_model.generate_content_async(user_message)

            if not chat_response.text:
                print("ERROR: Gemini response was empty or blocked.")
                try:
                    if chat_response.candidates[0].finish_reason.name == "SAFETY":
                        print("Reason: Blocked by safety filter.")
                        return ChatResponse(
                            response="ขออภัยค่ะ คำตอบที่ AI สร้างขึ้นถูกบล็อกโดยระบบความปลอดภัย"
                        )
                except (IndexError, AttributeError):
                    pass

                return ChatResponse(
                    response="ขออภัยค่ะ ตอนนี้ AI ไม่สามารถสร้างคำตอบได้ ลองใหม่อีกครั้งนะคะ"
                )

            return ChatResponse(response=chat_response.text)

    except Exception as e:
        print(f"!!! An unhandled exception occurred: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="An internal server error occurred.")