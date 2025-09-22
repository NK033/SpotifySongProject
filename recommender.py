# recommender.py (Upgraded with Caching, Background Updates, and Bulletproof Fallbacks)
import asyncio
import spotipy
import logging
from datetime import datetime, timedelta, timezone
from collections import Counter
import random
# Import local modules
from spotify_api import get_user_profile, get_user_top_tracks, get_user_recently_played_tracks, get_user_saved_tracks, search_spotify_songs,get_spotify_track_data
from lastfm_api import get_similar_tracks, get_chart_top_tracks, get_global_top_tracks, get_artist_top_tracks
from genius_api import get_lyrics
from custom_model import predict_moods
from database import (
    get_song_analysis_from_db, save_song_analysis_to_db, get_user_mood_profile, 
    save_user_mood_profile, save_recommendation_history, get_recommendation_history,
    get_user_feedback,get_user_mood_profile_with_timestamp
)

async def build_user_mood_profile(sp_client: spotipy.Spotify, user_id: str) -> dict:
    """
    (เวอร์ชันเรียนรู้ได้) วิเคราะห์เพลงโดยให้น้ำหนักกับเพลงที่ผู้ใช้เคย 'Like'
    """
    logging.info("Building learning user mood profile...")

    # 1. ดึง Feedback และเพลงจากแหล่งต่างๆ
    feedback_data = await get_user_feedback(user_id)
    liked_uris = feedback_data.get('likes', set())

    tasks = [
        get_user_top_tracks(sp_client, limit=10),
        get_user_saved_tracks(sp_client, limit=10),
        get_user_recently_played_tracks(sp_client, limit=5)
    ]
    results = await asyncio.gather(*tasks)
    top_tracks, saved_tracks, recent_tracks = results

    # --- LOG เวอร์ชันใหม่ที่สวยงามและอ่านง่าย ---
    print("\n=============== AI LOG: GATHERING SEED TRACKS ===============")
    
    def print_track_list(title, tracks):
        print(f"\n--- {title} ({len(tracks)} tracks) ---")
        if not tracks:
            print("  (None found)")
            return
        for i, track in enumerate(tracks):
            print(f"  {i+1}. '{track['name']}' by {track['artists'][0]['name']}")

    print_track_list("Your Top Tracks (Long Term)", top_tracks)
    print_track_list("Your Liked (Saved) Tracks", saved_tracks)
    print_track_list("Your Recently Played Tracks", recent_tracks)
    
    # 2. รวมเพลง โดยนำเพลงที่เคย 'Like' เข้ามาด้วย
    all_seed_tracks = {}
    
    # เพิ่มเพลงที่เคย Like เข้ามาก่อน (อาจจะต้องดึงข้อมูลเพลงเต็มๆ)
    if liked_uris:
        liked_track_data = await asyncio.gather(*[get_spotify_track_data(sp_client, uri) for uri in liked_uris])
        for track in liked_track_data:
            if track and track.get('uri'):
                all_seed_tracks[track['uri']] = track

    for track in top_tracks + saved_tracks + recent_tracks:
        if track and track.get('uri') and track['uri'] not in all_seed_tracks:
            all_seed_tracks[track['uri']] = track

    seed_tracks_list = list(all_seed_tracks.values())
    
    print("\n-------------------------------------------------------------")
    print(f"Total unique tracks for analysis: {len(seed_tracks_list)}")
    print("=============================================================\n")
    # --- จบส่วน Log ---

    if not seed_tracks_list:
        logging.warning("User has no tracks from any source to build mood profile.")
        return {}

    # 3. วิเคราะห์อารมณ์จากเพลง (ส่วนนี้เหมือนเดิม)
    all_moods = []
    analysis_tasks = []
    for track in seed_tracks_list[:12]:
        async def analyze_single_track(t):
            lyrics = await get_lyrics(t['artists'][0]['name'], t['name'])
            if lyrics:
                predicted = predict_moods(lyrics)
                print(f"  -> Analyzing '{t['name']}': Predicted moods = {predicted}")
                return predicted
            else:
                print(f"  -> Analyzing '{t['name']}': Lyrics not found, skipping.")
                return []
        analysis_tasks.append(analyze_single_track(track))
    
    mood_results = await asyncio.gather(*analysis_tasks)
    for moods in mood_results:
        all_moods.extend(moods)

    if not all_moods:
        logging.warning("Could not determine any moods from user's combined tracks.")
        return {}

    # 4. สร้างโปรไฟล์สรุป (เหมือนเดิม)
    mood_counts = Counter(all_moods)
    total_moods = len(all_moods)
    mood_profile = {mood: count / total_moods for mood, count in mood_counts.items()}
    
    print("\n========== AI LOG: FINAL MOOD PROFILE (Ultimate) ==========")
    for mood, percentage in mood_profile.items():
        print(f"  - {mood.capitalize()}: {percentage:.0%}")
    print("===========================================================\n")

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
    (เวอร์ชันอัปเกรด) แนะนำเพลงโดยยึด "อารมณ์หลัก" และ "Feedback" ของผู้ใช้เป็นศูนย์กลาง
    """
    # 1. สร้างโปรไฟล์อารมณ์ของผู้ใช้ (เหมือนเดิม)
    user_mood_profile = await get_user_mood_profile(user_id)
    if not user_mood_profile:
        user_mood_profile = await build_user_mood_profile(sp_client, user_id)
        if not user_mood_profile:
            logging.warning("Could not build mood profile. Cannot provide personalized recommendations.")
            return []

    # 2. ค้นหา "อารมณ์หลัก" (Dominant Mood) ของผู้ใช้ (เหมือนเดิม)
    dominant_mood = max(user_mood_profile, key=user_mood_profile.get) if user_mood_profile else None
    
    print("\n========== AI LOG: DOMINANT USER MOOD ==========")
    print(f"  User's dominant mood for this playlist is: {str(dominant_mood).upper()}")
    print("=============================================\n")

    # 3. ค้นหาเพลงตัวเลือกจาก Last.fm (เหมือนเดิม)
    seed_tracks_list = await get_seed_tracks(sp_client)
    candidate_tracks_info = []
    seen_tracks = set()

    # ... (ส่วนของ Plan A, B, C ในการหาเพลงเหมือนเดิม) ...
    if seed_tracks_list:
        logging.info("Executing Plan A: Last.fm Similar Tracks from user's seed tracks.")
        tasks = [get_similar_tracks(t['artists'][0]['name'], t['name'], limit=7) for t in seed_tracks_list[:5]]
        results = await asyncio.gather(*tasks)
        for track_list in results:
            for track_info in track_list:
                track_key = (track_info['artist'], track_info['title'])
                if track_key not in seen_tracks:
                    candidate_tracks_info.append(track_info)
                    seen_tracks.add(track_key)
    
    if not candidate_tracks_info and seed_tracks_list:
        logging.warning("Plan A failed. Executing Fallback #1: Last.fm Artist's Top Tracks.")
        artist_names = list(set(track['artists'][0]['name'] for track in seed_tracks_list))
        tasks = [get_artist_top_tracks(name, limit=5) for name in artist_names[:3]]
        results = await asyncio.gather(*tasks)
        for track_list in results:
            for track_info in track_list:
                track_key = (track_info['artist'], track_info['title'])
                if track_key not in seen_tracks:
                    candidate_tracks_info.append(track_info)
                    seen_tracks.add(track_key)

    if not candidate_tracks_info:
        logging.warning("Fallback #1 failed. Executing Ultimate Fallback: Country Chart.")
        user_profile = await get_user_profile(sp_client)
        user_physical_country = user_profile.get("country", "US")
        candidate_tracks_info = await get_chart_top_tracks(user_physical_country)

    if not candidate_tracks_info:
        logging.error("All recommendation plans have failed.")
        return []

    # --- 4. (ส่วนที่อัปเกรด) สร้าง Blacklist จากประวัติและ Feedback ---
    logging.info(f"Got {len(candidate_tracks_info)} candidates. Performing Vibe-aware analysis.")
    
    # ดึงประวัติเพลงที่เคยแนะนำและเพลงที่ผู้ใช้ฟังอยู่แล้ว
    history_uris = await get_recommendation_history(user_id)
    existing_uris = {t['uri'] for t in seed_tracks_list}
    
    # ดึง Feedback ของผู้ใช้
    feedback_data = await get_user_feedback(user_id)
    disliked_uris = feedback_data.get('dislikes', set())

    # รวมทุกอย่างเข้าเป็น Blacklist เดียว!
    blacklist_uris = existing_uris.union(history_uris).union(disliked_uris)
    logging.info(f"Total tracks in blacklist (history + dislikes): {len(blacklist_uris)}")


    # --- 5. วิเคราะห์, ให้คะแนน, และ "จัดกลุ่มตามโทน" (แก้ไขเล็กน้อย) ---
    primary_vibe_songs = []
    secondary_vibe_songs = []
    
    recommended_uris = set() # กันเพลงซ้ำในรอบเดียวกัน

    for track_info in candidate_tracks_info:
        query = f"track:{track_info['title']} artist:{track_info['artist']}"
        spotify_results = await search_spotify_songs(sp_client, query, limit=1)
        
        if not spotify_results: continue
        spotify_track = spotify_results[0]
        track_uri = spotify_track['uri']
        
        # --- ใช้ Blacklist ที่อัปเกรดแล้วในการกรอง ---
        if track_uri in blacklist_uris or track_uri in recommended_uris: 
            continue

        cached_analysis = await get_song_analysis_from_db(track_uri)
        song_moods = []
        if cached_analysis and 'lyrical_analysis' in cached_analysis and 'predicted_moods' in cached_analysis['lyrical_analysis']:
            song_moods = cached_analysis['lyrical_analysis']['predicted_moods']
        else:
            new_analysis = await analyze_and_cache_song(spotify_track)
            song_moods = new_analysis.get('predicted_moods', [])
        
        score = calculate_mood_score(song_moods, user_mood_profile)
        spotify_track['ai_analysis'] = {"mood_score": score, "predicted_moods": song_moods}
        
        if dominant_mood and dominant_mood in song_moods:
            primary_vibe_songs.append(spotify_track)
        else:
            secondary_vibe_songs.append(spotify_track)
        
        recommended_uris.add(track_uri)

    # 6. จัดลำดับและรวมเพลย์ลิสต์ (เหมือนเดิม)
    primary_vibe_songs.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)
    secondary_vibe_songs.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)

    final_playlist = primary_vibe_songs + secondary_vibe_songs
    final_playlist_uris = [track['uri'] for track in final_playlist]
    
    # --- 7. (ส่วนที่เพิ่มเข้ามา) บันทึกประวัติเพลงที่แนะนำในรอบนี้ ---
    if final_playlist_uris:
        await save_recommendation_history(user_id, final_playlist_uris)
        logging.info(f"Saved {len(final_playlist_uris)} recommended tracks to history for user {user_id}.")
    
    logging.info(f"Found {len(final_playlist)} final tracks. Primary vibe songs: {len(primary_vibe_songs)}")
    return final_playlist[:15]

# --- พิ่มฟังก์ชัน helper นี้เข้าไปใน recommender.py เพื่อดึงเพลงเมล็ดพันธุ์ ---
# (ฟังก์ชันนี้เป็นการนำ logic จาก build_user_mood_profile มาใช้ซ้ำ)
async def get_seed_tracks(sp_client: spotipy.Spotify) -> list[dict]:
    """
    รวบรวมเพลงเมล็ดพันธุ์จาก Top Tracks, Saved Tracks, และ Recently Played
    """
    # (คุณต้อง import get_user_top_tracks, get_user_saved_tracks, get_user_recently_played_tracks ด้วย)
    from spotify_api import get_user_top_tracks, get_user_saved_tracks, get_user_recently_played_tracks
    
    tasks = [
        get_user_top_tracks(sp_client, limit=10),
        get_user_saved_tracks(sp_client, limit=10),
        get_user_recently_played_tracks(sp_client, limit=5)
    ]
    results = await asyncio.gather(*tasks)
    top_tracks, liked_tracks, recent_tracks = results

    all_seed_tracks = {}
    for track in top_tracks + liked_tracks + recent_tracks:
        if track and track.get('uri') and track['uri'] not in all_seed_tracks:
            all_seed_tracks[track['uri']] = track

    return list(all_seed_tracks.values())

async def update_user_profile_background(sp_client: spotipy.Spotify, user_id: str):
    """
    (เวอร์ชันฉลาด) ฟังก์ชันสำหรับ Background Task ที่จะเช็คเวลาก่อนอัปเดต
    """
    logging.info(f"BACKGROUND TASK: Received request to update profile for user {user_id}...")

    # --- ตรรกะใหม่: เช็คว่าเพิ่งอัปเดตไปหรือยัง ---
    try:
        profile_data = await get_user_mood_profile_with_timestamp(user_id)
        if profile_data:
            # แปลง timestamp (string) จาก DB กลับเป็น datetime object
            last_updated_str = profile_data['timestamp']
            last_updated_dt = datetime.strptime(last_updated_str, '%Y-%m-%d %H:%M:%S')

            # กำหนดว่าถ้าอัปเดตไปภายใน 1 ชั่วโมงล่าสุด จะไม่ทำซ้ำ
            if datetime.now() - last_updated_dt < timedelta(hours=1):
                logging.info(f"BACKGROUND TASK: Profile for {user_id} is recent. Skipping update.")
                return # ออกจากฟังก์ชันทันที
    except Exception as e:
        logging.error(f"BACKGROUND TASK: Error checking profile timestamp for {user_id}: {e}")
        # ถ้าเช็คไม่ได้ ก็ปล่อยให้ทำต่อไปเพื่อความปลอดภัย
    
    # --- ถ้าผ่านเงื่อนไขมาได้ ค่อยเริ่มทำงานหนัก ---
    logging.info(f"BACKGROUND TASK: Profile is old or non-existent. Starting analysis for user {user_id}...")
    new_profile = await build_user_mood_profile(sp_client, user_id)
    if new_profile:
        await save_user_mood_profile(user_id, new_profile)
        logging.info(f"BACKGROUND TASK: Profile for {user_id} successfully updated.")