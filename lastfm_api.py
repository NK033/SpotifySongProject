# lastfm_api.py (Upgraded with Country Code Mapping and Global Chart)
import httpx
from config import Config
import logging

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

async def get_similar_tracks(artist: str, track: str, limit: int = 15) -> list[dict]:
    """
    ดึงรายชื่อเพลงที่คล้ายกันจาก Last.fm API
    """
    if not Config.LASTFM_API_KEY:
        logging.warning("Last.fm API Key is not configured. Skipping similar track search.")
        return []
    
    params = {
        "method": "track.getsimilar",
        "artist": artist,
        "track": track,
        "api_key": Config.LASTFM_API_KEY,
        "format": "json",
        "limit": limit
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(LASTFM_BASE_URL, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            
            if "similartracks" in data and "track" in data["similartracks"]:
                tracks = data["similartracks"]["track"]
                return [{"artist": t["artist"]["name"], "title": t["name"]} for t in tracks]
            return []
    except Exception as e:
        logging.error(f"Error in get_similar_tracks: {e}")
        return []

async def get_chart_top_tracks(country_code: str, limit: int = 20) -> list[dict]:
    """
    ดึงเพลง Top Chart ประจำประเทศ (แก้ไขให้ใช้ชื่อเต็ม)
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

async def get_global_top_tracks(limit: int = 20) -> list[dict]:
    """
    แผนสำรองสุดท้าย: ดึงเพลง Top Chart ระดับโลกจาก Last.fm (ไม่ต้องระบุประเทศ)
    """
    if not Config.LASTFM_API_KEY:
        logging.warning("Last.fm API Key is not configured. Skipping global chart search.")
        return []
        
    params = {
        "method": "chart.gettoptracks",
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
            return []
    except Exception as e:
        logging.error(f"Error in get_global_top_tracks: {e}")
        return []