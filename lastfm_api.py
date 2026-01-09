# lastfm_api.py (Cleaned)
import httpx # type: ignore
from config import Config
import logging
import asyncio

LASTFM_BASE_URL = "http://ws.audioscrobbler.com/2.0/"

# พจนานุกรมสำหรับแปลงรหัสประเทศ 2 ตัวอักษร (ISO) เป็นชื่อเต็มที่ Last.fm เข้าใจ
COUNTRY_CODE_MAP = {
    "TH": "Thailand",
    "JP": "Japan",
    "KR": "Korea, Republic of",
    "US": "United States",
    "GB": "United Kingdom",
    # สามารถเพิ่มประเทศอื่นๆ ที่ต้องการได้ที่นี่
}

async def get_chart_top_tracks(country_code: str, limit: int = 20) -> list[dict]:
    """
    ดึงเพลง Top Chart ประจำประเทศ (แก้ไขให้ใช้ชื่อเต็ม)
    (This function IS USED by main.py)
    """
    if not Config.LASTFM_API_KEY:
        logging.warning("Last.fm API Key is not configured. Skipping country chart search.")
        return []
    
    # แปลงรหัสประเทศ 2 ตัวอักษรเป็นชื่อเต็มก่อนส่งไป Last.fm
    country_full_name = COUNTRY_CODE_MAP.get(country_code, country_code)

    params = {
        "method": "geo.gettoptracks",
        "country": country_full_name,
        "api_key": Config.LASTFM_API_KEY,
        "format": "json",
        "limit": limit
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(LASTFM_BASE_URL, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            if "tracks" in data and "track" in data["tracks"]:
                tracks = data["tracks"]["track"]
                return [{"artist": t["artist"]["name"], "title": t["name"]} for t in tracks]
            
            logging.warning(f"No chart tracks found on Last.fm for country '{country_full_name}'. Response: {data}")
            return []
    except Exception as e:
        logging.error(f"Error in get_chart_top_tracks for {country_full_name}: {e}")
        return []

async def get_similar_artists_lastfm(artist: str, limit: int = 5) -> list[str]:
    """หาชื่อศิลปินที่คล้ายกัน (Neighbors)"""
    if not Config.LASTFM_API_KEY: return []
    params = {"method": "artist.getsimilar", "artist": artist, "api_key": Config.LASTFM_API_KEY, "format": "json", "limit": limit, "autocorrect": 1}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(LASTFM_BASE_URL, params=params, timeout=10.0)
            data = response.json()
            if "similarartists" in data and "artist" in data["similarartists"]:
                artists = data["similarartists"]["artist"]
                if isinstance(artists, dict): artists = [artists]
                # คืนค่าเฉพาะชื่อศิลปิน
                return [a["name"] for a in artists if "name" in a]
            return []
    except Exception as e:
        logging.error(f"Error getting similar artists for {artist}: {e}")
        return []

async def get_artist_top_tracks_lastfm(artist: str, limit: int = 5) -> list[dict]:
    """ดึงเพลงดังของศิลปิน (ใช้เป็น Fallback หรือตัวเสริม)"""
    if not Config.LASTFM_API_KEY: return []
    params = {"method": "artist.gettoptracks", "artist": artist, "api_key": Config.LASTFM_API_KEY, "format": "json", "limit": limit, "autocorrect": 1}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(LASTFM_BASE_URL, params=params, timeout=10.0)
            data = response.json()
            if "toptracks" in data and "track" in data["toptracks"]:
                tracks = data["toptracks"]["track"]
                if isinstance(tracks, dict): tracks = [tracks]
                return [{"artist": artist, "title": t["name"]} for t in tracks if "name" in t]
            return []
    except Exception as e:
        logging.error(f"Error getting top tracks for {artist}: {e}")
        return []

async def get_similar_tracks_lastfm(artist: str, track: str, limit: int = 20) -> list[dict]:
    """หาเพลงที่คล้ายกับเพลงนี้ (Direct Similarity)"""
    if not Config.LASTFM_API_KEY: return []
    params = {"method": "track.getsimilar", "artist": artist, "track": track, "api_key": Config.LASTFM_API_KEY, "format": "json", "limit": limit, "autocorrect": 1}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(LASTFM_BASE_URL, params=params, timeout=10.0)
            data = response.json()
            if "similartracks" in data and "track" in data["similartracks"]:
                tracks = data["similartracks"]["track"]
                if isinstance(tracks, dict): tracks = [tracks]
                return [{"artist": t["artist"]["name"], "title": t["name"]} for t in tracks if "name" in t and "artist" in t]
            return []
    except Exception as e:
        logging.error(f"Error getting similar tracks for {track}: {e}")
        return []