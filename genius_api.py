# genius_api.py (Upgraded for better Thai song detection)
import httpx
import re
from bs4 import BeautifulSoup
from fastapi import HTTPException, status
from config import Config

BASE_URL = "https://api.genius.com"

# --- (ใหม่) ฟังก์ชันสำหรับทำความสะอาดชื่อเพลง ---
def _clean_search_query(title: str) -> str:
    """ลบส่วนเกินในชื่อเพลง เช่น (with...), - From..., etc."""
    # ลบข้อความในวงเล็บทั้งหมด
    title = re.sub(r'\(.*?\)', '', title)
    # ลบข้อความหลังเครื่องหมาย -
    title = title.split('-')[0]
    return title.strip()

async def get_song_id(artist_name: str, song_title: str) -> int | None:
    """
    (เวอร์ชันอัปเกรด) ค้นหา ID เพลงจาก Genius API ด้วยวิธีที่ฉลาดขึ้น
    """
    search_url = f"{BASE_URL}/search"
    headers = {"Authorization": f"Bearer {Config.GENIUS_API_KEY}"}
    
    # --- 1. ทำความสะอาด "เบาะแส" ก่อน ---
    cleaned_title = _clean_search_query(song_title)
    
    # --- 2. สร้างรายการคำค้นหา (จะลองค้นหา 2 แบบ) ---
    search_queries = [
        f"{cleaned_title} {artist_name}", # แบบที่ 1: ชื่อเพลง + ศิลปิน (ดีที่สุด)
        cleaned_title                    # แบบที่ 2: ชื่อเพลงอย่างเดียว (แผนสำรอง)
    ]

    try:
        async with httpx.AsyncClient() as client:
            # วนลูปตามคำค้นหาที่เราเตรียมไว้
            for query in search_queries:
                print(f"Searching Genius with query: '{query}'")
                params = {"q": query}
                response = await client.get(search_url, headers=headers, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()

                for hit in data["response"]["hits"]:
                    result_artist = hit["result"]["primary_artist"]["name"]
                    
                    # --- 3. ตรวจสอบชื่อศิลปินให้ยืดหยุ่นขึ้น ---
                    # เช็คว่าชื่อศิลปินของเราอยู่ในผลลัพธ์ หรือชื่อในผลลัพธ์อยู่ในชื่อของเรา
                    # และเพิ่ม .casefold() เพื่อจัดการกับตัวพิมพ์เล็ก/ใหญ่ได้ดีกว่า .lower()
                    if artist_name.casefold() in result_artist.casefold() or result_artist.casefold() in artist_name.casefold():
                        print(f"✅ Found potential match: '{hit['result']['full_title']}'")
                        return hit["result"]["id"]
            
            # ถ้าวนลูปจนครบแล้วยังไม่เจอ ก็คืนค่า None
            print(f"❌ No Genius match found for '{song_title}' by '{artist_name}'")
            return None

    except httpx.HTTPStatusError as e:
        print(f"Genius API HTTP error searching for lyrics: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        print(f"Error searching for lyrics: {e}")
        return None

# (ฟังก์ชัน get_lyrics_by_id และ get_lyrics ไม่ต้องแก้ไข)
async def get_lyrics_by_id(song_id: int) -> str | None:
    """
    ดึงเนื้อเพลงจาก URL ของเพลงใน Genius
    """
    if not song_id:
        return None

    url = f"{BASE_URL}/songs/{song_id}"
    headers = {"Authorization": f"Bearer {Config.GENIUS_API_KEY}"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            path = data["response"]["song"]["path"]
            
            lyrics_url = f"https://genius.com{path}"
            print(f"DEBUG: Fetching lyrics from URL: {lyrics_url}")
            
            html_response = await client.get(lyrics_url, follow_redirects=True, timeout=15.0)
            html_response.raise_for_status()
            
            soup = BeautifulSoup(html_response.text, "html.parser")
            lyrics_container = soup.find("div", class_=lambda value: value and value.startswith("Lyrics__Container"))

            if not lyrics_container:
                # Fallback สำหรับโครงสร้างเว็บแบบเก่า
                lyrics_container = soup.find("div", class_="lyrics")
            
            if lyrics_container:
                # ใช้ .get_text(separator='\n') เพื่อรักษาระยะห่างระหว่างบรรทัด
                text = lyrics_container.get_text(separator="\n").strip()
                # ลบ [Chorus], [Verse] etc.
                text = re.sub(r'\[.*?\]', '', text)
                # ลบบรรทัดว่างที่อาจเกิดขึ้นหลังจากการลบ
                text = "\n".join(line for line in text.split('\n') if line.strip())
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
    if not Config.GENIUS_API_KEY:
        print("Warning: GENIUS_API_KEY is not set. Skipping lyrical analysis.")
        return None

    song_id = await get_song_id(artist_name, song_title)
    if song_id:
        lyrics = await get_lyrics_by_id(song_id)
        if lyrics and len(lyrics) > 50: # กรองเนื้อเพลงที่สั้นหรือผิดปกติออก
            return lyrics

    return None