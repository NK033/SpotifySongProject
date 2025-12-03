# spotify_api.py (ฉบับแก้ไขสมบูรณ์ - เอา API ที่ถูกแบนออกทั้งหมด)
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import MemoryCacheHandler 
from fastapi import HTTPException, status
import asyncio
import random
import time
import logging # (เพิ่ม logging)

from config import Config

SPOTIFY_SCOPES = "user-read-private user-read-email playlist-modify-public playlist-modify-private user-library-read user-top-read user-read-recently-played user-read-currently-playing"

# --- ฟังก์ชันจัดการการยืนันตัวตน ---

async def get_spotify_auth_url() -> str:
    """สร้าง URL สำหรับให้ผู้ใช้ล็อกอิน Spotify"""
    auth_manager = SpotifyOAuth(
        client_id=Config.SPOTIPY_CLIENT_ID, 
        client_secret=Config.SPOTIPY_CLIENT_SECRET, 
        redirect_uri=Config.SPOTIPY_REDIRECT_URI, 
        scope=SPOTIFY_SCOPES,
        cache_handler=MemoryCacheHandler(),
        show_dialog=True
    )
    auth_url = await asyncio.to_thread(auth_manager.get_authorize_url)
    return auth_url

async def get_spotify_token(code: str) -> dict:
    """แลกเปลี่ยน code ที่ได้หลังล็อกอินเป็น Access Token และ Refresh Token"""
    auth_manager = SpotifyOAuth(
        client_id=Config.SPOTIPY_CLIENT_ID, 
        client_secret=Config.SPOTIPY_CLIENT_SECRET, 
        redirect_uri=Config.SPOTIPY_REDIRECT_URI, 
        scope=SPOTIFY_SCOPES,
        cache_handler=MemoryCacheHandler()
    )
    try:
        token_info = await asyncio.to_thread(auth_manager.get_access_token, code=code, check_cache=False)
        return token_info
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to get Spotify access token: {e}")

# --- ฟังก์ชันสร้างไคลเอนต์อัจฉริยะ ---

# --- [NEW FUNCTION] Auto preloading song details with Gemini ---
# --- [NEW FUNCTION] Auto preloading song details with Gemini ---
async def preload_gemini_details(sp_client: spotipy.Spotify, tracks: list[dict]):
    """
    โหลดรายละเอียดเพลง (Gemini analysis) แบบอัตโนมัติให้ทุกเพลงใน background
    ใช้ asyncio.gather เพื่อรันพร้อมกัน (batch-safe)
    """
    if not tracks:
        return

    logging.info(f"🚀 Auto-preloading Gemini Details for {len(tracks)} tracks...")

    tasks = []
    for t in tracks:
        if t and t.get("uri"):
            tasks.append(get_song_analysis_details(sp_client, t["uri"]))

    try:
        # รันพร้อมกันแบบไม่ block ฟังก์ชันหลัก
        await asyncio.gather(*tasks, return_exceptions=True)
        logging.info("✅ All Gemini details preloaded successfully.")
    except Exception as e:
        logging.error(f"❌ Error during Gemini auto-preload: {e}", exc_info=True)

def get_current_playing_track(sp):
    """
    ดึงข้อมูลเพลงที่กำลังเล่นอยู่ (Metadata เท่านั้น ไม่มีการวิเคราะห์ Audio Features)
    คืนค่า: Dict ข้อมูลเพลง หรือ None ถ้าไม่ได้เล่นเพลงอยู่
    """
    try:
        # เรียก API ของ Spotify เพื่อดู Status ปัจจุบัน
        current = sp.current_user_playing_track()
        
        # ถ้าไม่มีเพลงเล่นอยู่ หรือ User กด Pause
        if not current or not current['is_playing']:
            return None

        item = current['item']
        # ป้องกันกรณีเป็น Podcast หรือ Local file ที่ไม่มี URI
        if not item or 'uri' not in item: 
            return None

        # คัดมาเฉพาะข้อมูลที่จำเป็น
        return {
            "is_playing": True,
            "spotify_uri": item['uri'],
            "name": item['name'],
            "artist": item['artists'][0]['name'],
            "album": item['album']['name'],
            "cover": item['album']['images'][0]['url'] if item['album']['images'] else None,
            "progress_ms": current['progress_ms'] # เผื่อใช้คำนวณว่าฟังจบหรือยัง
        }
    except Exception as e:
        print(f"Error getting current track: {e}")
        return None
def create_spotify_client(token_info: dict) -> spotipy.Spotify:
    """
    (V-Final) สร้าง Spotipy client และแก้ปัญหา Proxy/ConnectionError
    """
    cache_handler = MemoryCacheHandler(token_info=token_info)

    auth_manager = SpotifyOAuth(
        client_id=Config.SPOTIPY_CLIENT_ID,
        client_secret=Config.SPOTIPY_CLIENT_SECRET,
        redirect_uri=Config.SPOTIPY_REDIRECT_URI,
        scope=SPOTIFY_SCOPES,
        cache_handler=cache_handler
    )
    
    # --- [ FIX ที่ถูกต้อง: แก้ 404 และ TypeError ] ---
    proxies_config = {"http": None, "https": None}
    sp_client = spotipy.Spotify(auth_manager=auth_manager, proxies=proxies_config)
    # --- [ จบ FIX ] ---
    
    return sp_client

# --- ฟังก์ชันที่เรียกใช้ Spotify API (ที่ปลอดภัย) ---

async def search_spotify_songs(sp_client: spotipy.Spotify, query: str, limit: int = 5) -> list[dict]:
    results = await asyncio.to_thread(sp_client.search, q=query, type='track', limit=int(limit))
    return results['tracks']['items']

async def create_spotify_playlist(sp_client: spotipy.Spotify, playlist_name: str, track_uris: list[str]) -> dict:
    user_id = (await asyncio.to_thread(sp_client.me))['id']
    playlist = await asyncio.to_thread(sp_client.user_playlist_create, user=user_id, name=playlist_name, public=True)
    if track_uris:
        for i in range(0, len(track_uris), 100):
            chunk = track_uris[i:i+100]
            await asyncio.to_thread(sp_client.playlist_add_items, playlist_id=playlist['id'], items=chunk)
    return playlist

async def get_user_top_tracks(sp_client: spotipy.Spotify, limit: int = 5) -> list[dict]:
    results = await asyncio.to_thread(sp_client.current_user_top_tracks, limit=int(limit), time_range='long_term')
    return results['items']

async def get_user_saved_tracks_uris(sp_client: spotipy.Spotify) -> set[str]:
    saved_tracks_uris = set()
    results = await asyncio.to_thread(sp_client.current_user_saved_tracks, limit=50)
    while results:
        for item in results['items']:
            if item and item.get('track'):
                saved_tracks_uris.add(item['track']['uri'])
        if results['next']:
            results = await asyncio.to_thread(sp_client.next, results)
        else:
            results = None
    return saved_tracks_uris

async def get_user_profile(sp_client: spotipy.Spotify) -> dict:
    return await asyncio.to_thread(sp_client.current_user)

async def get_spotify_track_data(sp_client: spotipy.Spotify, track_uri: str) -> dict:
    return await asyncio.to_thread(sp_client.track, track_id=track_uri)

async def get_user_recently_played_tracks(sp_client: spotipy.Spotify, limit: int = 12) -> list[dict]:
    """ดึงข้อมูลเพลงที่ผู้ใช้ฟังล่าสุด (Recently Played)"""
    results = await asyncio.to_thread(sp_client.current_user_recently_played, limit=limit)
    return [item['track'] for item in results['items'] if item and item.get('track')]

async def get_user_saved_tracks(sp_client: spotipy.Spotify, limit: int = 8) -> list[dict]:
    """
    (เวอร์ชันใหม่) ดึงข้อมูลเพลงที่ผู้ใช้กดไลค์ (Saved Tracks) โดยการสุ่ม
    """
    try:
        first_page = await asyncio.to_thread(sp_client.current_user_saved_tracks, limit=1)
        total_saved_tracks = first_page['total']
        if total_saved_tracks == 0:
            return []

        max_offset = max(0, total_saved_tracks - limit)
        random_offset = random.randint(0, max_offset)

        results = await asyncio.to_thread(
            sp_client.current_user_saved_tracks, 
            limit=limit, 
            offset=random_offset
        )
        return [item['track'] for item in results['items'] if item and item.get('track')]

    except Exception as e:
        logging.error(f"  -> Could not fetch random saved tracks: {e}")
        results = await asyncio.to_thread(sp_client.current_user_saved_tracks, limit=limit)
        return [item['track'] for item in results['items'] if item and item.get('track')]


# --- [ แก้ไขใหม่ทั้งหมด ] ---
async def get_fallback_recommendations(sp_client: spotipy.Spotify) -> list[dict]:
    """
    (V-Final, Dynamic Fallback)
    ระบบแนะนำเพลงสำรองที่ "เป็นกลาง" และ "พยายาม" อิงจาก User ก่อน
    โดยใช้เฉพาะ API ที่ 'ปลอดภัย' (search, top_artists)
    """
    logging.warning("--- Fallback activated. All intelligent systems failed. ---")

    # --- Tier 1 (ใหม่): พยายามค้นหาจาก Top Artist ของ User ---
    # นี่คือวิธีที่ดีที่สุดที่จะ "เป็นกลาง" แต่ยังคง "เป็นส่วนตัว"
    logging.info("Attempting Tier 1 (Fallback): Search by User's Top Artist...")
    try:
        # 1. ดึง Top Artist (API นี้ยังใช้ได้)
        top_artists = await asyncio.to_thread(sp_client.current_user_top_artists, limit=1)
        
        if top_artists and top_artists['items']:
            artist_name = top_artists['items'][0]['name']
            logging.info(f"User's Top Artist is '{artist_name}'. Using as search query.")
            
            # 2. เอาชื่อศิลปินไปค้นหาเพลง (API นี้ยังใช้ได้)
            results = await asyncio.to_thread(
                sp_client.search, 
                q=artist_name, 
                type='track', 
                limit=15
            )
            
            if results and results['tracks']['items']:
                logging.info("✅ Tier 1 (Fallback) successful.")
                return results['tracks']['items'][:10]
        else:
            logging.info("User has no Top Artist. Skipping Tier 1.")
            
    except Exception as e:
        logging.error(f"Tier 1 (Fallback) failed: {e}")


    # --- Tier 2 (ใหม่): ไม้ตายสุดท้าย (ถ้า Tier 1 ล่ม) ---
    # ใช้คำค้นหา "ทั่วไป" (Generic) ที่ไม่เอนเอียงไปทางภาษาใด
    logging.info("Attempting Tier 2 (Fallback): Search for 'Global Top Hits'...")
    try:
        results = await asyncio.to_thread(
            sp_client.search, 
            q='Global Top Hits', # (ใช้ 'Global Top Hits' จะเป็นกลางที่สุด)
            type='track', 
            limit=15
        )
        if results and results['tracks']['items']:
            logging.info("✅ Tier 2 (Fallback) successful.")
            return results['tracks']['items'][:10]
    except Exception as e:
        logging.error(f"Tier 2 (Fallback) failed: {e}")

    logging.error("All fallback plans failed. Returning empty list.")
    return []

