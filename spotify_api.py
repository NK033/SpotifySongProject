# spotify_api.py (เวอร์ชันแก้ไขแล้ว: audio_features ใช้ positional argument)
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import MemoryCacheHandler 
from fastapi import HTTPException, status
import asyncio
import random
import time

from config import Config



SPOTIFY_SCOPES = "user-read-private user-read-email playlist-modify-public playlist-modify-private user-library-read user-top-read user-read-recently-played"

# --- ฟังก์ชันจัดการการยืนยันตัวตน ---

async def get_spotify_auth_url() -> str:
    """สร้าง URL สำหรับให้ผู้ใช้ล็อกอิน Spotify"""
    auth_manager = SpotifyOAuth(
        client_id=Config.SPOTIPY_CLIENT_ID, 
        client_secret=Config.SPOTIPY_CLIENT_SECRET, 
        redirect_uri=Config.SPOTIPY_REDIRECT_URI, 
        scope=SPOTIFY_SCOPES,
        cache_handler=MemoryCacheHandler(),
        show_dialog=True  # <-- ให้ผู้ใช้เลือกบัญชีใหม่ทุกครั้ง
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

def create_spotify_client(token_info: dict) -> spotipy.Spotify:
    """
    สร้าง Spotipy client ที่มีความสามารถในการต่ออายุ Token อัตโนมัติ
    โดยใช้ MemoryCacheHandler ที่สร้างขึ้นใหม่สำหรับแต่ละ request
    """
    cache_handler = MemoryCacheHandler(token_info=token_info)

    auth_manager = SpotifyOAuth(
        client_id=Config.SPOTIPY_CLIENT_ID,
        client_secret=Config.SPOTIPY_CLIENT_SECRET,
        redirect_uri=Config.SPOTIPY_REDIRECT_URI,
        scope=SPOTIFY_SCOPES,
        cache_handler=cache_handler
    )
    sp_client = spotipy.Spotify(auth_manager=auth_manager)
    return sp_client

# --- ฟังก์ชันที่เรียกใช้ Spotify API ---

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

async def get_user_top_tracks(sp_client: spotipy.Spotify, limit: int = 20) -> list[dict]:
    results = await asyncio.to_thread(sp_client.current_user_top_tracks, limit=int(limit), time_range='medium_term')
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

async def get_audio_features_for_tracks(sp_client: spotipy.Spotify, track_ids: list[str]) -> list[dict]:
    if not track_ids: 
        return []
    features_list = []
    for i in range(0, len(track_ids), 100):
        batch = track_ids[i:i+100]
        # ✅ ใช้ positional argument แทน keyword เพื่อให้ Spotipy ส่ง token ถูกต้อง
        features = await asyncio.to_thread(sp_client.audio_features, batch)
        features_list.extend(features)
    return [f for f in features_list if f]

async def get_spotify_recommendations_for_discovery(sp_client: spotipy.Spotify, seed_genres: list[str]) -> list[dict]:
    if not seed_genres:
        return []
    num_seeds = min(len(seed_genres), 3)
    selected_seeds = random.sample(seed_genres, num_seeds)
    
    results = await asyncio.to_thread(
        sp_client.recommendations, 
        seed_genres=selected_seeds,
        limit=10
    )
    return results['tracks']

async def get_user_profile(sp_client: spotipy.Spotify) -> dict:
    return await asyncio.to_thread(sp_client.current_user)

async def get_spotify_track_data(sp_client: spotipy.Spotify, track_uri: str) -> dict:
    return await asyncio.to_thread(sp_client.track, track_id=track_uri)


# spotify_api.py (วางทับฟังก์ชันเดิม)


async def get_fallback_recommendations(sp_client: spotipy.Spotify) -> list[dict]:
    """
    ระบบแนะนำเพลงสำรองแบบขั้นบันไดที่แข็งแกร่งขึ้น (เวอร์ชันแก้ไขบั๊กสุดท้าย)
    """
    try:
        user_profile = await get_user_profile(sp_client)
        country_code = user_profile.get("country")
    except Exception as e:
        print(f"Could not fetch user profile for fallback, aborting. Error: {e}")
        return []

    # --- Tier 1, 2, 3 (เหมือนเดิม) ---
    print("Attempting Tier 1: Genre-based recommendations...")
    try:
        genre_seeds_map = {
            "TH": ['pop', 'indie', 'rock', 'hip-hop', 'r-n-b'],
            "JP": ['j-pop', 'j-rock', 'anime', 'pop', 'rock'],
            "KR": ['k-pop', 'k-rock', 'r-n-b', 'hip-hop', 'indie'],
            "US": ['pop', 'hip-hop', 'rock', 'r-n-b', 'country'],
            "default": ['pop', 'rock', 'electronic', 'hip-hop', 'indie']
        }
        seed_genres = genre_seeds_map.get(country_code, genre_seeds_map["default"])
        selected_seeds = random.sample(seed_genres, min(len(seed_genres), 3))
        results = await asyncio.to_thread(sp_client.recommendations, seed_genres=selected_seeds, limit=15)
        if results and results['tracks']:
            print("✅ Tier 1 successful.")
            return results['tracks'][:7]
    except Exception as e:
        print(f"Tier 1 failed: {e}")

    print("Attempting Tier 2: Artist-based recommendations...")
    try:
        top_artists = await asyncio.to_thread(sp_client.current_user_top_artists, limit=1)
        if top_artists and top_artists['items']:
            top_artist_id = top_artists['items'][0]['id']
            results = await asyncio.to_thread(sp_client.recommendations, seed_artists=[top_artist_id], limit=15)
            if results and results['tracks']:
                print("✅ Tier 2 successful.")
                return results['tracks'][:7]
    except Exception as e:
        print(f"Tier 2 failed: {e}")

    print("Attempting Tier 3: Featured Playlist recommendations...")
    try:
        featured_playlists = await asyncio.to_thread(sp_client.featured_playlists, country=country_code, limit=1)
        if featured_playlists and featured_playlists['playlists']['items'] and featured_playlists['playlists']['items'][0]:
            playlist_id = featured_playlists['playlists']['items'][0]['id']
            results = await asyncio.to_thread(sp_client.playlist_items, playlist_id=playlist_id, limit=15)
            if results and results['items']:
                print("✅ Tier 3 successful.")
                return [item['track'] for item in results['items'] if item and item.get('track')][:7]
    except Exception as e:
        print(f"Tier 3 failed: {e}")

    # --- Tier 4: ไม้ตายสุดท้าย (เพิ่มการตรวจสอบ None) ---
    print("Attempting Tier 4: Global Top 50 Playlist...")
    try:
        results = await asyncio.to_thread(sp_client.search, q='Top 50 - Global', type='playlist', limit=1)
        # --- บรรทัดที่แก้ไข ---
        if results and results['playlists']['items'] and results['playlists']['items'][0]:
            playlist_id = results['playlists']['items'][0]['id']
            playlist_tracks = await asyncio.to_thread(sp_client.playlist_items, playlist_id=playlist_id, limit=15)
            if playlist_tracks and playlist_tracks['items']:
                print("✅ Tier 4 successful.")
                return [item['track'] for item in playlist_tracks['items'] if item and item.get('track')][:7]
    except Exception as e:
        print(f"Tier 4 failed: {e}")

    return []

async def get_personalized_recommendations(sp_client: spotipy.Spotify, taste_profile: dict, limit: int = 10) -> list[dict]:
    """
    สร้างเพลงแนะนำส่วนตัวโดยอิงจากโปรไฟล์รสนิยมและเพลงโปรดของผู้ใช้
    """
    try:
        # 1. หา "เมล็ดพันธุ์" จากเพลงและศิลปินโปรดของผู้ใช้
        top_tracks = await get_user_top_tracks(sp_client, limit=5)
        top_artists = await asyncio.to_thread(sp_client.current_user_top_artists, limit=2)

        seed_track_ids = [track['id'] for track in top_tracks if track and track.get('id')]
        seed_artist_ids = [artist['id'] for artist in top_artists['items'] if artist and artist.get('id')]
        
        # Spotify อนุญาตให้ใช้ seed รวมกันได้ไม่เกิน 5 อย่าง
        # เราจะให้น้ำหนักกับเพลงมากกว่า
        final_seed_tracks = seed_track_ids[:3]
        final_seed_artists = seed_artist_ids[:2]

        if not final_seed_tracks and not final_seed_artists:
            print("  -> No seeds found for personalized recommendations.")
            return []

        # 2. สร้างพารามิเตอร์เป้าหมายจากโปรไฟล์รสนิยม
        target_params = {
            f"target_{key}": value for key, value in taste_profile.items()
        }

        # 3. เรียก API recommendations
        print(f"  -> Calling recommendations with seeds (tracks: {len(final_seed_tracks)}, artists: {len(final_seed_artists)}) and targets.")
        results = await asyncio.to_thread(
            sp_client.recommendations,
            seed_tracks=final_seed_tracks,
            seed_artists=final_seed_artists,
            limit=limit,
            **target_params
        )
        return results['tracks'] if results else []
        
    except Exception as e:
        print(f"  -> Error during personalized recommendation: {e}")
        return []