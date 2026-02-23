# genius_api.py (Upgraded for better Thai song detection)
import httpx
import re
from bs4 import BeautifulSoup
from fastapi import HTTPException, status
from config import Config

BASE_URL = "https://api.genius.com"


def _strip_genius_header_noise(text: str) -> str:
    """
    Remove common non-lyric headers that are embedded in Genius page text.
    """
    if not text:
        return ""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned_lines = []
    header_phase = True

    for line in lines:
        is_short_latin_label = bool(re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ'’\- ]{1,30}", line)) and len(line.split()) <= 3

        # Remove section labels we never want in final lyrics
        if re.fullmatch(r"\[.*?\]", line):
            continue

        if header_phase:
            normalized = line.casefold()
            looks_like_header = (
                re.search(r"\bcontributors?\b", line, flags=re.IGNORECASE)
                or re.search(r"\btranslations?\b", line, flags=re.IGNORECASE)
                or re.search(r"\bromanization\b", line, flags=re.IGNORECASE)
                or re.search(r"\blyrics\b", line, flags=re.IGNORECASE)
                or normalized in {"english", "read more"}
                or (len(line.split()) >= 6 and re.search(r"\b(is|was|are|were)\b", line, flags=re.IGNORECASE))
                or is_short_latin_label  # usually language pills like "Türkçe"
            )

            # Skip description / editorial text before real lyrics begin
            if looks_like_header:
                continue

            header_phase = False

        cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines)

    # Drop accidental remnants such as "123 Contributors" that may appear mid-text.
    cleaned_text = re.sub(r"(?im)^\s*\d+\s+contributors?\s*$", "", cleaned_text)
    cleaned_text = re.sub(r"(?im)^\s*(translations?|romanization|read more|english)\s*$", "", cleaned_text)
    cleaned_text = re.sub(r"(?im)^\s*.*\blyrics\b\s*$", "", cleaned_text)

    # Normalize blank lines after removals
    cleaned_text = "\n".join(line for line in cleaned_text.splitlines() if line.strip())
    return cleaned_text.strip()

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

            # Genius รุ่นใหม่: เนื้อเพลงอยู่ในหลาย div ที่มี data-lyrics-container="true"
            lyrics_blocks = soup.select('div[data-lyrics-container="true"]')
            if lyrics_blocks:
                text = "\n".join(block.get_text(separator="\n", strip=True) for block in lyrics_blocks)
                text = _strip_genius_header_noise(text)
                if text:
                    return text

            # Fallback โครงสร้างคลาสเดิม
            lyrics_container = soup.find("div", class_=lambda value: value and value.startswith("Lyrics__Container"))

            if not lyrics_container:
                # Fallback สำหรับโครงสร้างเว็บแบบเก่า
                lyrics_container = soup.find("div", class_="lyrics")

            if lyrics_container:
                text = lyrics_container.get_text(separator="\n").strip()
                text = _strip_genius_header_noise(text)
                if text:
                    return text
            
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
