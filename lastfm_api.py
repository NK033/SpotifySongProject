# lastfm_api.py (Cleaned)
import httpx # type: ignore
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

