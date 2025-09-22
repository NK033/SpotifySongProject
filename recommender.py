# recommender.py (Upgraded with Caching, Background Updates, and Bulletproof Fallbacks)
import asyncio
import spotipy
import logging
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
    get_user_feedback
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
    print_track_list("Your Liked (Saved) Tracks", liked_tracks)
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
    (เวอร์ชันคุมโทนด้วย Mood) แนะนำเพลงโดยยึด "อารมณ์หลัก" ของผู้ใช้เป็นศูนย์กลาง
    """
    # 1. สร้างโปรไฟล์อารมณ์ของผู้ใช้
    user_mood_profile = await get_user_mood_profile(user_id)
    if not user_mood_profile:
        user_mood_profile = await build_user_mood_profile(sp_client)
        if not user_mood_profile:
            logging.warning("Could not build mood profile. Cannot provide personalized recommendations.")
            # ในสถานการณ์จริง ส่วนนี้ควรไปดึงเพลงฮิตติดชาร์ตมาแสดงแทน
            return []

    # 2. ค้นหา "อารมณ์หลัก" (Dominant Mood) ของผู้ใช้
    if not user_mood_profile:
        dominant_mood = None
    else:
        dominant_mood = max(user_mood_profile, key=user_mood_profile.get)
    
    print("\n========== AI LOG: DOMINANT USER MOOD ==========")
    print(f"  User's dominant mood for this playlist is: {str(dominant_mood).upper()}")
    print("=============================================\n")

    # 3. ค้นหาเพลงตัวเลือกจาก Last.fm (พร้อมแผนสำรอง)
    seed_tracks_list = await get_seed_tracks(sp_client)
    candidate_tracks_info = []
    seen_tracks = set()

    # --- แผน A: หาเพลงคล้ายกันจากเพลงของผู้ใช้ ---
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
    
    # --- แผน B: หาเพลงฮิตจากศิลปินโปรดของผู้ใช้ ---
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

    # --- แผน C: ใช้เพลงฮิตติดชาร์ตประเทศ ---
    if not candidate_tracks_info:
        logging.warning("Fallback #1 failed. Executing Ultimate Fallback: Country Chart.")
        user_physical_country = (await get_user_profile(sp_client)).get("country", "US")
        candidate_tracks_info = await get_chart_top_tracks(user_physical_country)

    if not candidate_tracks_info:
        logging.error("All recommendation plans have failed.")
        return []

    # 4. วิเคราะห์, ให้คะแนน, และ "จัดกลุ่มตามโทน"
    logging.info(f"Got {len(candidate_tracks_info)} candidates. Performing Vibe-aware analysis.")
    
    primary_vibe_songs = []
    secondary_vibe_songs = []
    
    existing_uris = {t['uri'] for t in seed_tracks_list}
    recommended_uris = set()

    for track_info in candidate_tracks_info:
        query = f"track:{track_info['title']} artist:{track_info['artist']}"
        spotify_results = await search_spotify_songs(sp_client, query, limit=1)
        
        if not spotify_results: continue
        spotify_track = spotify_results[0]
        track_uri = spotify_track['uri']
        if track_uri in existing_uris or track_uri in recommended_uris: continue

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

    # 5. จัดลำดับและรวมเพลย์ลิสต์ (ย้ายออกมานอก loop)
    primary_vibe_songs.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)
    secondary_vibe_songs.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)

    final_playlist = primary_vibe_songs + secondary_vibe_songs
    
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
    ฟังก์ชันสำหรับ Background Task เพื่ออัปเดตโปรไฟล์ผู้ใช้
    """
    logging.info(f"BACKGROUND TASK: Updating mood profile for user {user_id}...")
    new_profile = await build_user_mood_profile(sp_client)
    if new_profile:
        await save_user_mood_profile(user_id, new_profile)
        logging.info(f"BACKGROUND TASK: Profile for {user_id} successfully updated.")