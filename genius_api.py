# genius_api.py
import httpx
import re
from bs4 import BeautifulSoup
from fastapi import HTTPException, status
from config import Config

BASE_URL = "https://api.genius.com"

async def get_song_id(artist_name: str, song_title: str) -> int | None:
    """
    ค้นหา ID เพลงจาก Genius API
    """
    search_url = f"{BASE_URL}/search"
    # --- MODIFIED: แก้ชื่อตัวแปรให้ถูกต้อง ---
    headers = {"Authorization": f"Bearer {Config.GENIUS_API_KEY}"}
    params = {"q": f"{song_title} {artist_name}"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url, headers=headers, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            for hit in data["response"]["hits"]:
                # ปรับปรุงการเปรียบเทียบชื่อศิลปินให้แม่นยำขึ้น
                if artist_name.lower() in hit["result"]["primary_artist"]["name"].lower():
                    return hit["result"]["id"]
            return None
    except httpx.HTTPStatusError as e:
        print(f"Genius API HTTP error searching for lyrics: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        print(f"Error searching for lyrics: {e}")
        return None

async def get_lyrics_by_id(song_id: int) -> str | None:
    """
    ดึงเนื้อเพลงจาก URL ของเพลงใน Genius
    """
    if not song_id:
        return None

    url = f"{BASE_URL}/songs/{song_id}"
    # --- MODIFIED: แก้ชื่อตัวแปรให้ถูกต้อง ---
    headers = {"Authorization": f"Bearer {Config.GENIUS_API_KEY}"}

    try:
        async with httpx.AsyncClient() as client:
            # ... (ส่วนที่เหลือของฟังก์ชันนี้เหมือนเดิม) ...
            response = await client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            path = data["response"]["song"]["path"]
            
            lyrics_url = f"https://genius.com{path}"
            print(f"DEBUG: กำลังดึงเนื้อเพลงจาก URL: {lyrics_url}")
            
            html_response = await client.get(lyrics_url, follow_redirects=True, timeout=15.0)
            html_response.raise_for_status()
            
            soup = BeautifulSoup(html_response.text, "html.parser")
            lyrics = soup.find("div", class_=lambda value: value and value.startswith("Lyrics__Container"))

            if not lyrics:
                lyrics = soup.find("div", class_="lyrics")
            
            if lyrics:
                text = lyrics.get_text(separator="\n").strip()
                text = re.sub(r'\[.*?\]', '', text)
                return text.strip()
            
            return None
            
    except httpx.HTTPStatusError as e:
        print(f"Genius API HTTP error fetching lyrics: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        print(f"Error fetching lyrics: {e}")
        return None

async def get_lyrics(artist_name: str, song_title: str) -> str | None:
    """
    ฟังก์ชันหลักในการดึงเนื้อเพลง
    """
    # --- MODIFIED: แก้ชื่อตัวแปรให้ถูกต้อง ---
    if not Config.GENIUS_API_KEY:
        print("Warning: GENIUS_API_KEY is not set. Skipping lyrical analysis.")
        return None

    song_id = await get_song_id(artist_name, song_title)
    if song_id:
        lyrics = await get_lyrics_by_id(song_id)
        if lyrics and len(lyrics) > 50:
            return lyrics

    return None