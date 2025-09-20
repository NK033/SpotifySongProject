# recommender.py (Upgraded with Caching, Background Updates, and Bulletproof Fallbacks)
import asyncio
import spotipy
import logging
from collections import Counter

# Import local modules
from spotify_api import get_user_top_tracks, search_spotify_songs, get_user_profile
from lastfm_api import get_similar_tracks, get_chart_top_tracks, get_global_top_tracks
from genius_api import get_lyrics
from custom_model import predict_moods
from database import get_song_analysis_from_db, save_song_analysis_to_db, get_user_mood_profile, save_user_mood_profile

async def build_user_mood_profile(sp_client: spotipy.Spotify) -> dict:
    """
    วิเคราะห์เพลง Top Tracks ของผู้ใช้เพื่อสร้าง "โปรไฟล์อารมณ์เพลง"
    """
    logging.info("Building user mood profile...")
    top_tracks = await get_user_top_tracks(sp_client, limit=20)
    if not top_tracks:
        logging.warning("User has no top tracks to build mood profile.")
        return {}

    all_moods = []
    # วิเคราะห์เพลง 5 อันดับแรกเพื่อความรวดเร็ว
    for track in top_tracks[:5]:
        lyrics = await get_lyrics(track['artists'][0]['name'], track['name'])
        if lyrics:
            predicted = predict_moods(lyrics)
            all_moods.extend(predicted)
        await asyncio.sleep(0.2) # หน่วงเวลาเล็กน้อย

    if not all_moods:
        logging.warning("Could not determine any moods from user's top tracks.")
        return {}

    # คำนวณสัดส่วนของแต่ละอารมณ์
    mood_counts = Counter(all_moods)
    total_moods = len(all_moods)
    mood_profile = {mood: count / total_moods for mood, count in mood_counts.items()}
    
    logging.info(f"User mood profile created: {mood_profile}")
    return mood_profile

def calculate_mood_score(song_moods: list, user_profile: dict) -> float:
    """
    คำนวณคะแนนความเข้ากันได้ทางอารมณ์ระหว่างเพลงกับโปรไฟล์ของผู้ใช้
    """
    if not song_moods or not user_profile:
        return 0.0
    
    score = sum(user_profile.get(mood, 0) for mood in song_moods)
        
    return score / len(song_moods) if song_moods else 0.0

async def analyze_and_cache_song(spotify_track: dict) -> dict:
    """
    วิเคราะห์เพลงที่ยังไม่มีใน Cache และบันทึกลงฐานข้อมูล
    """
    analysis = {"predicted_moods": []} # default
    lyrics = await get_lyrics(spotify_track['artists'][0]['name'], spotify_track['name'])
    if lyrics:
        moods = predict_moods(lyrics)
        analysis["predicted_moods"] = moods
    
    analysis_to_save = {"lyrical_analysis": analysis}
    await save_song_analysis_to_db(spotify_track, analysis_to_save)
    return analysis

async def get_intelligent_recommendations(sp_client: spotipy.Spotify, user_id: str) -> list[dict]:
    """
    กระบวนการแนะนำเพลงอัจฉริยะที่ใช้ Cache และมีแผนสำรองขั้นสุดยอด
    """
    # --- 1. ดึงโปรไฟล์ล่าสุดจาก Cache ---
    user_mood_profile = await get_user_mood_profile(user_id)
    if not user_mood_profile:
        logging.info(f"No cached profile for {user_id}. Building for the first time.")
        user_mood_profile = await build_user_mood_profile(sp_client)
        if user_mood_profile:
            await save_user_mood_profile(user_id, user_mood_profile)

    # --- 2. เริ่มกระบวนการหาเพลงแนะนำ ---
    top_tracks = await get_user_top_tracks(sp_client, limit=5)
    candidate_tracks_info = []
    
    # แผนหลัก: Last.fm Similar Tracks
    if top_tracks:
        tasks = [get_similar_tracks(t['artists'][0]['name'], t['name'], limit=7) for t in top_tracks[:3]]
        results = await asyncio.gather(*tasks)
        seen_tracks = set()
        for track_list in results:
            for track_info in track_list:
                track_key = (track_info['artist'], track_info['title'])
                if track_key not in seen_tracks:
                    candidate_tracks_info.append(track_info)
                    seen_tracks.add(track_key)
        logging.info(f"Plan A (Last.fm Similar) found {len(candidate_tracks_info)} candidates.")

    # แผนสำรอง #1: Last.fm Top Chart ตามประเทศ
    if not candidate_tracks_info:
        logging.warning("Plan A failed. Executing Fallback #1: Last.fm Country Chart.")
        user_physical_country = (await get_user_profile(sp_client)).get("country", "US")
        candidate_tracks_info = await get_chart_top_tracks(user_physical_country)

    # แผนสำรองสุดท้าย #2: Global Top Chart (รับประกันว่าสำเร็จ)
    if not candidate_tracks_info:
        logging.warning("Fallback #1 failed. Executing Ultimate Fallback: Global Top Tracks.")
        candidate_tracks_info = await get_global_top_tracks()

    if not candidate_tracks_info:
        logging.error("All recommendation plans have failed catastrophically.")
        return []

    # --- 3. วิเคราะห์และจัดลำดับเท่าที่จำเป็น (Just-in-Time Analysis) ---
    logging.info(f"Got {len(candidate_tracks_info)} candidates. Performing Just-in-Time analysis.")
    ranked_candidates = []
    top_track_uris = {t['uri'] for t in top_tracks} if top_tracks else set()

    # สร้าง Task list สำหรับค้นหาและวิเคราะห์เพลงพร้อมๆ กัน
    tasks = []
    for track_info in candidate_tracks_info:
        query = f"track:{track_info['title']} artist:{track_info['artist']}"
        spotify_results = await search_spotify_songs(sp_client, query, limit=1)
        
        if not spotify_results or spotify_results[0]['uri'] in top_track_uris:
            continue

        spotify_track = spotify_results[0]
        
        # ตรวจสอบ Cache
        cached_analysis = await get_song_analysis_from_db(spotify_track['uri'])
        
        song_moods = []
        if cached_analysis and 'lyrical_analysis' in cached_analysis:
            song_moods = cached_analysis['lyrical_analysis'].get('predicted_moods', [])
        else:
            new_analysis = await analyze_and_cache_song(spotify_track)
            song_moods = new_analysis.get('predicted_moods', [])
        
        score = calculate_mood_score(song_moods, user_mood_profile)
        spotify_track['ai_analysis'] = {"mood_score": score, "predicted_moods": song_moods}
        ranked_candidates.append(spotify_track)

    ranked_candidates.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)
    
    logging.info(f"Found and ranked {len(ranked_candidates)} final tracks.")
    return ranked_candidates[:10]

async def update_user_profile_background(sp_client: spotipy.Spotify, user_id: str):
    """
    ฟังก์ชันสำหรับ Background Task เพื่ออัปเดตโปรไฟล์ผู้ใช้
    """
    logging.info(f"BACKGROUND TASK: Updating mood profile for user {user_id}...")
    new_profile = await build_user_mood_profile(sp_client)
    if new_profile:
        await save_user_mood_profile(user_id, new_profile)
        logging.info(f"BACKGROUND TASK: Profile for {user_id} successfully updated.")