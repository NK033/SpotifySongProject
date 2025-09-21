# recommender.py (Upgraded with Caching, Background Updates, and Bulletproof Fallbacks)
import asyncio
import spotipy
import logging
from collections import Counter
import random
# Import local modules
from spotify_api import get_user_profile, get_user_top_tracks, get_user_recently_played_tracks, get_user_saved_tracks, search_spotify_songs
from lastfm_api import get_similar_tracks, get_chart_top_tracks, get_global_top_tracks, get_artist_top_tracks
from genius_api import get_lyrics
from custom_model import predict_moods
from database import get_song_analysis_from_db, save_song_analysis_to_db, get_user_mood_profile, save_user_mood_profile

async def build_user_mood_profile(sp_client: spotipy.Spotify) -> dict:
    """
    (เวอร์ชัน Ultimate) วิเคราะห์เพลงจาก Top Tracks, ที่ฟังล่าสุด, และที่กดไลค์
    """
    logging.info("Building comprehensive user mood profile...")

    # 1. ดึงเพลงจากทั้ง 3 แหล่งพร้อมกัน
    tasks = [
        get_user_top_tracks(sp_client, limit=10),
        get_user_saved_tracks(sp_client, limit=10),
        get_user_recently_played_tracks(sp_client, limit=5)
    ]
    results = await asyncio.gather(*tasks)
    top_tracks, liked_tracks, recent_tracks = results

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
    
    # 2. รวมเพลงและคัดเพลงซ้ำออก
    all_seed_tracks = {}
    for track in top_tracks + liked_tracks + recent_tracks:
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
    (เวอร์ชัน Last.fm ที่ดีที่สุด) กระบวนการแนะนำเพลงที่ยึดตามโปรไฟล์ของผู้ใช้
    """
    # 1. สร้างโปรไฟล์อารมณ์ของผู้ใช้
    user_mood_profile = await get_user_mood_profile(user_id)
    if not user_mood_profile:
        # หากยังไม่มีโปรไฟล์ ให้สร้างขึ้นมาก่อน
        user_mood_profile = await build_user_mood_profile(sp_client)
        if not user_mood_profile:
            logging.warning("Could not build mood profile. Cannot provide personalized recommendations.")
            # ถ้ายังสร้างไม่ได้จริงๆ ค่อยใช้แผนสำรอง
            fallback_tracks_info = await get_chart_top_tracks("Thailand") 
            # (ในสถานการณ์จริงควรนำ fallback_tracks_info ไป search spotify ต่อ)
            return []

    # 2. รวบรวม "เมล็ดพันธุ์" เพลงทั้งหมด
    seed_tracks_list = await get_seed_tracks(sp_client)

    candidate_tracks_info = []
    seen_tracks = set()

    # --- 3. แผน A: หาเพลงคล้ายกันจากเพลงของผู้ใช้ ---
    if seed_tracks_list:
        logging.info("Executing NEW Plan A: Last.fm Similar Tracks from ALL user's seed tracks.")
        tasks = [get_similar_tracks(t['artists'][0]['name'], t['name'], limit=7) for t in seed_tracks_list[:5]]
        results = await asyncio.gather(*tasks)
        for track_list in results:
            for track_info in track_list:
                track_key = (track_info['artist'], track_info['title'])
                if track_key not in seen_tracks:
                    candidate_tracks_info.append(track_info)
                    seen_tracks.add(track_key)
        logging.info(f"Plan A (Last.fm Similar) found {len(candidate_tracks_info)} candidates.")

    # --- 4. แผน B: หาเพลงฮิตจากศิลปินโปรดของผู้ใช้ ---
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

    # --- 5. แผน C: ใช้เพลงฮิตติดชาร์ตประเทศ ---
    if not candidate_tracks_info:
        logging.warning("Fallback #1 failed. Executing Ultimate Fallback: Country Chart.")
        user_physical_country = (await get_user_profile(sp_client)).get("country", "US")
        candidate_tracks_info = await get_chart_top_tracks(user_physical_country)

    if not candidate_tracks_info:
        logging.error("All recommendation plans have failed.")
        return []

    # --- 6. นำผลลัพธ์ไปค้นหาและให้คะแนน (ฉบับแก้ไข) ---
    logging.info(f"Got {len(candidate_tracks_info)} candidates. Performing Just-in-Time analysis.")
    
    ranked_candidates = []
    # สร้าง list ของ URI เพลงที่เรามีอยู่แล้ว เพื่อไม่ให้แนะนำเพลงซ้ำ
    existing_uris = {t['uri'] for t in seed_tracks_list}

    for track_info in candidate_tracks_info:
        query = f"track:{track_info['title']} artist:{track_info['artist']}"
        spotify_results = await search_spotify_songs(sp_client, query, limit=1)
        
        # ตรวจสอบว่าเจอเพลงใน Spotify และไม่ใช่เพลงที่ผู้ใช้มีอยู่แล้ว
        if not spotify_results or spotify_results[0]['uri'] in existing_uris:
            continue

        spotify_track = spotify_results[0]
        
        # ส่วนของการวิเคราะห์และให้คะแนน (ส่วนนี้ถูกต้องอยู่แล้ว)
        cached_analysis = await get_song_analysis_from_db(spotify_track['uri'])
        song_moods = []
        if cached_analysis and 'lyrical_analysis' in cached_analysis and 'predicted_moods' in cached_analysis['lyrical_analysis']:
            song_moods = cached_analysis['lyrical_analysis']['predicted_moods']
        else:
            # analyze_and_cache_song เป็นฟังก์ชันสมมติที่ต้องมีในโค้ดของคุณ
            new_analysis = await analyze_and_cache_song(spotify_track)
            song_moods = new_analysis.get('predicted_moods', [])
        
        score = calculate_mood_score(song_moods, user_mood_profile)
        print(f"  -> Scoring '{spotify_track['name']}': Moods={song_moods}, Final Score={score:.2f}")

        spotify_track['ai_analysis'] = {"mood_score": score, "predicted_moods": song_moods}
        ranked_candidates.append(spotify_track)

    ranked_candidates.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)
    
    logging.info(f"Found and ranked {len(ranked_candidates)} final tracks.")
    return ranked_candidates[:15]

# --- 7. เพิ่มฟังก์ชัน helper นี้เข้าไปใน recommender.py เพื่อดึงเพลงเมล็ดพันธุ์ ---
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