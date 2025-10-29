# recommender.py (Corrected Final Version)
import asyncio
import spotipy
import logging
from datetime import datetime, timedelta
from collections import Counter
import numpy as np
import random
from gemini_ai import rescue_lyrics_with_gemini
# Import local modules
from spotify_api import get_user_profile, get_user_top_tracks, get_user_recently_played_tracks, get_user_saved_tracks, search_spotify_songs, get_spotify_track_data
from lastfm_api import get_similar_tracks, get_chart_top_tracks, get_global_top_tracks, get_artist_top_tracks
from genius_api import get_lyrics
from custom_model import predict_moods
from database import (
    get_song_analysis_from_db, save_song_analysis_to_db, get_user_mood_profile, 
    save_user_mood_profile, save_recommendation_history, get_recommendation_history,
    get_user_feedback, get_user_mood_profile_with_timestamp
)
from gemini_ai import get_gemini_seed_expansion

# (ส่วน build_user_mood_profile, calculate_mood_score, analyze_and_cache_song เหมือนเดิม)
async def build_user_mood_profile(sp_client: spotipy.Spotify, user_id: str) -> dict:
    """
    (Hybrid V7) สร้าง "พิมพ์เขียวอารมณ์ต้นแบบ" (Target Emotional Fingerprint)
    """
    logging.info("--- Building Target Emotional Fingerprint (Hybrid V7) ---")

    seed_tracks_list = await get_seed_tracks(sp_client)
    if not seed_tracks_list:
        logging.warning("User has no tracks. Cannot build mood profile.")
        return {}

    lyrics_found = {}
    failed_tracks = []

    async def get_initial_lyrics(track):
        try:
            if track and 'name' in track and 'artists' in track and track['artists']:
                lyrics = await get_lyrics(track['artists'][0]['name'], track['name'])
                if lyrics:
                    lyrics_found[track['uri']] = lyrics
                else:
                    failed_tracks.append(track)
        except Exception:
            failed_tracks.append(track)

    await asyncio.gather(*[get_initial_lyrics(track) for track in seed_tracks_list[:15]])
    rescued_lyrics_dict = await rescue_lyrics_with_gemini(failed_tracks)
    
    # แปลง rescued_lyrics_dict ให้มี key เป็น track uri
    for track in failed_tracks:
        key = f"{track['name']} - {track['artists'][0]['name']}"
        if key in rescued_lyrics_dict:
            lyrics_found[track['uri']] = rescued_lyrics_dict[key]

    logging.info(f"Gathered lyrical content for {len(lyrics_found)} tracks.")
    if not lyrics_found:
        return {}
        
    # วิเคราะห์ "ลายนิ้วมือ" ของแต่ละเพลง
    all_fingerprints = [predict_moods(content) for content in lyrics_found.values() if content]
    
    if not all_fingerprints:
        return {}

    # หาค่าเฉลี่ยของ "ลายนิ้วมือ" ทั้งหมดเพื่อสร้าง "พิมพ์เขียวต้นแบบ"
    avg_fingerprint = {}
    labels = all_fingerprints[0].keys()
    for label in labels:
        avg_score = sum(fp.get(label, 0.0) for fp in all_fingerprints) / len(all_fingerprints)
        avg_fingerprint[label] = avg_score
    
    logging.info("✅ Target Emotional Fingerprint created.")
    return avg_fingerprint

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

# --- (แก้ไข) เพิ่ม Helper Function ที่ขาดหายไป ---
async def analyze_and_cache_song_moods(spotify_track: dict) -> tuple[list, bool]:
    """
    Helper function ที่รวมการเช็ค Cache และการวิเคราะห์ Mood ไว้ด้วยกัน
    Returns: (list_of_moods, success_boolean)
    """
    # ตรวจสอบว่ามีข้อมูลเพลงหรือไม่
    if not spotify_track or 'uri' not in spotify_track:
        return [], False

    cached_analysis = await get_song_analysis_from_db(spotify_track['uri'])
    # ตรวจสอบโครงสร้างของ cache ให้ถูกต้อง
    if cached_analysis and 'predicted_moods' in cached_analysis:
        return cached_analysis['predicted_moods'], True

    lyrics = await get_lyrics(spotify_track['artists'][0]['name'], spotify_track['name'])
    if lyrics and len(lyrics) > 50:
        moods = predict_moods(lyrics)
        # บันทึกผลลง DB สำหรับการใช้งานครั้งต่อไป
        analysis_to_save = {"predicted_moods": moods}
        await save_song_analysis_to_db(spotify_track, analysis_to_save)
        return moods, True
        
    return [], False
# --- จบส่วนแก้ไข ---

def calculate_cosine_similarity(profile1: dict, profile2: dict) -> float:
    """
    เปรียบเทียบ "ลายนิ้วมือทางอารมณ์" สองชุดว่ามีความคล้ายกันแค่ไหน
    """
    if not profile1 or not profile2:
        return 0.0
    
    # ดึงเฉพาะ key ที่มีร่วมกันและเรียงลำดับให้ตรงกัน
    labels = sorted(list(profile1.keys()))
    vec1 = np.array([profile1.get(label, 0.0) for label in labels])
    vec2 = np.array([profile2.get(label, 0.0) for label in labels])

    # คำนวณ Cosine Similarity
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
        
    return dot_product / (norm1 * norm2)



# (นำโค้ดนี้ไปวางทับฟังก์ชัน get_intelligent_recommendations เดิมใน recommender.py)

async def get_intelligent_recommendations(sp_client: spotipy.Spotify, user_id: str, user_mood_profile: dict | None) -> list[dict]:
    """
    (Hybrid V7: The Analyst & The Conductor)
    Gemini analyzes taste to generate candidates, Custom Model scores and ranks them based on emotional fingerprint.
    """
    logging.info("--- Initializing Hybrid V7: The Analyst & The Conductor ---")

    # --- ส่วนที่ 1: "The Analyst" (Gemini) - วิเคราะห์เพลงโปรดและแนะนำ "ตัวเลือก" ---
    top_tracks = await get_user_top_tracks(sp_client, limit=10)
    if not top_tracks:
        logging.error("No top tracks found for user. Aborting.")
        return []
        
    candidate_tracks_info = await get_gemini_seed_expansion(top_tracks)
    
    # --- แผนสำรอง: ถ้า Gemini ล่ม ให้ใช้ Last.fm แทน ---
    if not candidate_tracks_info:
        logging.warning("Gemini failed to generate candidates. Using Last.fm as fallback.")
        lastfm_candidates = await get_similar_tracks(top_tracks[0]['artists'][0]['name'], top_tracks[0]['name'], limit=30)
        candidate_tracks_info = lastfm_candidates
    
    if not candidate_tracks_info:
        logging.error("All candidate generation plans failed. Aborting.")
        return []

    print(f"\n=============== 🌐 AI LOG: TOTAL CANDIDATES ({len(candidate_tracks_info)}) ===============")
    for i, track in enumerate(candidate_tracks_info[:20]):
        print(f"  {i+1}. '{track['title']}' by {track['artist']}")
    print("=================================================================\n")

    # --- ส่วนที่ 2: "The Judge" (Scoring) - ให้คะแนนและจัดลำดับ ---
    logging.info("Scoring and Ranking candidates...")
    
    # เตรียม Blacklist (เหมือนเดิม)
    user_seed_tracks = await get_seed_tracks(sp_client)
    history_uris = await get_recommendation_history(user_id)
    existing_uris = {t['uri'] for t in user_seed_tracks}
    feedback_data = await get_user_feedback(user_id)
    disliked_uris = feedback_data.get('dislikes', set())
    blacklist_uris = existing_uris.union(history_uris).union(disliked_uris)

    playlist_with_scores = []
    
    async def score_track(track_info):
        # ค้นหาเพลงบน Spotify
        query = f"track:{track_info['title']} artist:{track_info['artist']}"
        spotify_results = await search_spotify_songs(sp_client, query, limit=1)
        if not spotify_results: return None
        
        spotify_track = spotify_results[0]
        track_uri = spotify_track['uri']
        
        # กรองด้วย Blacklist พื้นฐาน
        if track_uri in blacklist_uris:
            return None
            
        # ดึงเนื้อเพลง (ใช้หน่วยกู้ภัยถ้าจำเป็น)
        lyrics, success = await analyze_and_cache_song_moods(spotify_track)
        if not success or not lyrics: 
            # ถ้าไม่มีเนื้อเพลงเลย ก็ไม่สามารถให้คะแนนได้
            spotify_track['ai_analysis'] = {"mood_score": 0.0} # ให้คะแนนเป็น 0
            return spotify_track

        # "The Conductor" สร้าง "ลายนิ้วมือ" ของเพลงนี้
        song_fingerprint = predict_moods(lyrics)
        
        # "The Judge" เปรียบเทียบ "ลายนิ้วมือ" กับ "พิมพ์เขียวต้นแบบ" ของผู้ใช้
        score = 0
        if user_mood_profile:
             score = calculate_cosine_similarity(user_mood_profile, song_fingerprint)
        
        spotify_track['ai_analysis'] = {"mood_score": score}
        return spotify_track

    # รันการให้คะแนนทั้งหมดพร้อมๆ กัน
    scoring_tasks = [score_track(info) for info in candidate_tracks_info]
    results = await asyncio.gather(*scoring_tasks)
    
    # คัดเฉพาะเพลงที่ผ่านเข้ารอบ (ไม่เป็น None)
    playlist_with_scores = [track for track in results if track]

    print(f"\n=============== ✅ AI LOG: SCORING COMPLETE ✅ ===============")
    print(f"  - Started with: {len(candidate_tracks_info)} candidates")
    print(f"  - Kept: {len(playlist_with_scores)} tracks after basic filtering")
    print(f"===========================================================\n")

    # --- ส่วนที่ 3: The Finale - จัดลำดับและนำเสนอ ---
    
    # จัดลำดับเพลงทั้งหมดตาม "คะแนน" จากมากไปน้อย
    playlist_with_scores.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)

    print("\n=============== 🏆 AI LOG: TOP 5 RANKED SONGS 🏆 ===============")
    for i, track in enumerate(playlist_with_scores[:5]):
        score = track['ai_analysis']['mood_score']
        print(f"  {i+1}. '{track['name']}' - Score: {score:.4f}")
    print("===========================================================\n")

    final_playlist = playlist_with_scores
    final_playlist_uris = [track['uri'] for track in final_playlist]
    
    if final_playlist_uris:
        await save_recommendation_history(user_id, final_playlist_uris)
    
    return final_playlist[:15]


async def get_seed_tracks(sp_client: spotipy.Spotify) -> list[dict]:
    """
    รวบรวมเพลงเมล็ดพันธุ์จาก Top Tracks, Saved Tracks, และ Recently Played
    """
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

    try:
        profile_data = await get_user_mood_profile_with_timestamp(user_id)
        if profile_data:
            last_updated_str = profile_data['timestamp']
            last_updated_dt = datetime.strptime(last_updated_str, '%Y-%m-%d %H:%M:%S')

            if datetime.now() - last_updated_dt < timedelta(hours=1):
                logging.info(f"BACKGROUND TASK: Profile for {user_id} is recent. Skipping update.")
                return
    except Exception as e:
        logging.error(f"BACKGROUND TASK: Error checking profile timestamp for {user_id}: {e}")
    
    logging.info(f"BACKGROUND TASK: Profile is old or non-existent. Starting analysis for user {user_id}...")
    new_profile = await build_user_mood_profile(sp_client, user_id)
    if new_profile:
        await save_user_mood_profile(user_id, new_profile)
        logging.info(f"BACKGROUND TASK: Profile for {user_id} successfully updated.")

