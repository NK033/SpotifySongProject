# gemini_ai.py
import google.generativeai as genai
import json
from fastapi import HTTPException, status
import asyncio

from config import Config
from database import save_song_analysis_to_db, get_song_analysis_from_db
from genius_api import get_lyrics
from lyrics_analysis import analyze_lyrics

# ตั้งค่า Gemini API


async def analyze_and_store_song_analysis(spotify_track_data: dict) -> dict:
    """
    วิเคราะห์ข้อมูลเพลงจาก Spotify, เนื้อเพลงจาก Genius ด้วย Gemini และบันทึกผลลัพธ์ลงในฐานข้อมูล
    """
    print(f"กำลังวิเคราะห์เพลง '{spotify_track_data.get('name')}' ด้วย Gemini...")
    
    # 1. ดึงและวิเคราะห์เนื้อเพลง
    artist_name = spotify_track_data.get('artists', [{}])[0].get('name', 'ไม่ระบุ')
    song_title = spotify_track_data.get('name', 'ไม่ระบุ')
    lyrics = await get_lyrics(artist_name, song_title)
    
    lyrical_analysis_result = {}
    if lyrics:
        lyrical_analysis_result = analyze_lyrics(lyrics)
        print("DEBUG: วิเคราะห์เนื้อเพลงด้วย BERT เรียบร้อยแล้ว")
    
      # 2. เตรียม Prompt สำหรับ Gemini โดยรวมการวิเคราะห์เนื้อเพลงเข้าไป
    prompt_content = f"""
    คุณเป็นนักวิเคราะห์ดนตรีมืออาชีพ โปรดวิเคราะห์เพลงต่อไปนี้อย่างละเอียดและให้ข้อมูลเชิงลึกเกี่ยวกับเพลงนี้
    โดยครอบคลุมหัวข้อต่อไปนี้:
    ชื่อเพลง: {song_title}
    ศิลปิน: {artist_name}
    อัลบั้ม: {spotify_track_data.get('album', {}).get('name', 'ไม่ระบุ')}
    URL ของเพลง (ถ้ามี): {spotify_track_data.get('external_urls', {}).get('spotify', 'ไม่มี')}

    1.  **แนวเพลง (Genre):** ระบุแนวเพลงหลักและแนวเพลงย่อยที่เป็นไปได้ พร้อมเหตุผลสนับสนุน
    2.  **อารมณ์และบรรยากาศ (Mood & Vibe):** อธิบายว่าเพลงนี้ให้อารมณ์แบบใด และเหมาะกับช่วงเวลาไหน
    3.  **เครื่องดนตรี (Instrumentation):** ระบุเครื่องดนตรีหลักที่โดดเด่นในเพลง
    4.  **การวิเคราะห์โครงสร้างเพลง (Song Structure):** อธิบายท่อนต่างๆ (Verse, Chorus, Bridge) และการเรียบเรียง
    5.  **การวิเคราะห์เนื้อเพลง (Lyrical Analysis):**
        - นี่คือสรุปเนื้อเพลงที่ได้จากการวิเคราะห์ด้วยโมเดล BERT: {lyrical_analysis_result.get('summary', 'N/A')}
        - **ผลการวิเคราะห์อารมณ์จากเนื้อเพลง (BERT): {lyrical_analysis_result.get('sentiment', 'N/A')}** # <-- ADDED
        - โปรดอธิบายความหมายโดยรวมของเนื้อเพลง และความสัมพันธ์กับอารมณ์ของเพลง โดยอ้างอิงจากข้อมูลวิเคราะห์ข้างต้น

    โปรดตอบกลับเป็นภาษาไทยเท่านั้น และจัดรูปแบบให้อ่านง่าย
    """
    
     # 3. ให้ Gemini วิเคราะห์ข้อมูล
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        # --- MODIFIED: ปรับ System Instruction ให้เป็นกลาง ไม่จำกัดแนวเพลง ---
        system_instruction="คุณคือผู้ช่วยและนักวิเคราะห์ดนตรีที่เชี่ยวชาญด้านดนตรีไทยและสากลทุกแนวเพลง คุณสามารถวิเคราะห์เพลงได้อย่างแม่นยำและตอบกลับได้อย่างเป็นธรรมชาติ"
    )
    
    try:
        response = model.generate_content(prompt_content)
        analysis_text = response.text
        
        # สร้างโครงสร้างการตอบกลับที่รวมเนื้อเพลงและผลการวิเคราะห์เนื้อเพลง
        combined_analysis = {
            "gemini_analysis": analysis_text,
            "lyrical_analysis": lyrical_analysis_result
        }
        
        await save_song_analysis_to_db(spotify_track_data, combined_analysis)
        
        return combined_analysis

    except Exception as e:
        print(f"Error calling Gemini API for song analysis: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error analyzing song with Gemini API.")

async def get_song_analysis_details(user_spotify_access_token: str, song_uri: str) -> dict:
    """
    ดึงข้อมูลการวิเคราะห์เพลงจาก DB หรือวิเคราะห์ใหม่ถ้ายังไม่มี
    """
    analysis_data = await get_song_analysis_from_db(song_uri)
    if analysis_data:
        return analysis_data
        
    from spotify_api import get_spotify_track_data # นำเข้าที่นี่เพื่อป้องกัน circular import
    
    try:
        spotify_track_data = await get_spotify_track_data(user_spotify_access_token, song_uri)
        return await analyze_and_store_song_analysis(spotify_track_data)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get song details: {e}")

async def summarize_playlist(user_spotify_access_token: str, song_uris: list[str]) -> str:
    """
    ให้ Gemini สรุปภาพรวมของ Playlist จากข้อมูลการวิเคราะห์เพลง
    """
    if not user_spotify_access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Spotify access token is required for summarizing playlist.")

    all_song_analyses = []
    for uri in song_uris:
        try:
            analysis = await get_song_analysis_details(user_spotify_access_token, uri)
            all_song_analyses.append(analysis)
        except HTTPException as e:
            print(f"Warning: Could not get analysis for URI {uri}: {e.detail}")

    if not all_song_analyses:
        return "ไม่สามารถสรุปเพลย์ลิสต์ได้ในขณะนี้"

    # สร้าง prompt สำหรับสรุปเพลย์ลิสต์
    prompt = "โปรดสรุปภาพรวมของเพลย์ลิสต์นี้จากข้อมูลการวิเคราะห์เพลงต่อไปนี้:\n\n"
    for i, analysis in enumerate(all_song_analyses):
        prompt += f"--- เพลงที่ {i+1}: ---\n"
        # ใช้เฉพาะการวิเคราะห์ของ Gemini เพื่อการสรุปภาพรวมของเพลย์ลิสต์
        prompt += analysis.get('gemini_analysis', 'ไม่มีข้อมูลการวิเคราะห์') + "\n\n"
    prompt += "โปรดสรุปเป็นภาษาไทยอย่างละเอียด โดยเน้นแนวเพลง อารมณ์ เครื่องดนตรี และลักษณะเด่นของเพลย์ลิสต์นี้โดยรวม"

    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction="คุณคือผู้ช่วยที่เชี่ยวชาญด้านดนตรีไทยและสากล"
    )

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error calling Gemini API for playlist summary: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error summarizing playlist.")
