# background_tasks.py
import spotipy
from collections import Counter
import asyncio

# Import ฟังก์ชันที่จำเป็นจากไฟล์อื่นๆ
from spotify_api import get_user_top_tracks
from database import get_song_analysis_from_db, save_song_analysis_to_db, save_user_mood_profile
from genius_api import get_lyrics
from custom_model import predict_moods

async def analyze_user_taste_profile_background(sp_client: spotipy.Spotify, user_id: str):
    """
    タスクที่ทำงานเบื้องหลังเพื่อวิเคราะห์รสนิยมเพลงของผู้ใช้
    """
    print(f"BACKGROUND TASK: Starting taste profile analysis for user {user_id}...")
    
    # 1. ดึงเพลง Top Tracks ของผู้ใช้ (เราจะวิเคราะห์ 20 เพลงแรกเพื่อความรวดเร็ว)
    top_tracks = await get_user_top_tracks(sp_client, limit=20)
    if not top_tracks:
        print(f"BACKGROUND TASK: No top tracks found for user {user_id}. Exiting.")
        return

    all_moods = []
    
    # 2. วนลูปเพื่อวิเคราะห์แต่ละเพลง
    for track in top_tracks:
        uri = track['uri']
        song_name = track['name']
        artist_name = track['artists'][0]['name']
        print(f"BACKGROUND TASK: Analyzing '{song_name}'...")

        # 3. ตรวจสอบ Cache ส่วนกลางก่อน (กลยุทธ์ที่ 3)
        analysis = await get_song_analysis_from_db(uri)
        
        if analysis and "lyrical_analysis" in analysis and "predicted_moods" in analysis["lyrical_analysis"]:
             # ถ้าเจอใน Cache ก็ใช้ข้อมูลเก่าได้เลย
            predicted_moods = analysis["lyrical_analysis"]["predicted_moods"]
            print(f"  -> Found in cache. Moods: {predicted_moods}")
        else:
            # ถ้าไม่เจอใน Cache ก็วิเคราะห์ใหม่
            lyrics = await get_lyrics(artist_name, song_name)
            if lyrics:
                predicted_moods = predict_moods(lyrics)
                print(f"  -> Analyzed new. Moods: {predicted_moods}")
                # หมายเหตุ: เราควรจะอัปเดต song_analyses ด้วย แต่เพื่อความเรียบง่ายจะข้ามไปก่อน
            else:
                predicted_moods = []

        all_moods.extend(predicted_moods)
        await asyncio.sleep(1) # หน่วงเวลาเล็กน้อยเพื่อลดภาระ

    # 4. สรุปผลและสร้าง Mood Profile
    if not all_moods:
        print(f"BACKGROUND TASK: Could not determine any moods for user {user_id}.")
        return

    mood_counts = Counter(all_moods)
    total_moods = len(all_moods)
    mood_profile = {mood: count / total_moods for mood, count in mood_counts.items()}
    
    print(f"BACKGROUND TASK: Analysis complete for user {user_id}. Profile: {mood_profile}")

    # 5. บันทึกโปรไฟล์ลงฐานข้อมูล
    await save_user_mood_profile(user_id, mood_profile)