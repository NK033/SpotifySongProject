# recommender.py (V19 - Cleaned & BugFixed)
import asyncio
import spotipy
import logging
import re
from gemini_ai import preload_gemini_details
from datetime import datetime, timedelta
from collections import Counter  
import numpy as np
import random
from spotify_api import create_spotify_client, get_fallback_recommendations
from gemini_ai import rescue_lyrics_with_gemini, get_filler_tracks_with_lyrics
# Import local modules
from spotify_api import (
    get_user_profile, get_user_top_tracks, get_user_recently_played_tracks, 
    get_user_saved_tracks, search_spotify_songs, get_spotify_track_data
)
# --- [DELETED] Unused lastfm_api import ---
from genius_api import get_lyrics
from custom_model import predict_moods
from database import (
    get_song_analysis_from_db, save_song_analysis_to_db, get_user_mood_profile, 
    save_user_mood_profile, save_recommendation_history, get_recommendation_history,
    get_user_feedback, get_user_mood_profile_with_timestamp
)
from gemini_ai import get_gemini_seed_expansion

# --- (Helper 1: ตรวจจับภาษาจากตัวอักษร - ใช้เป็นแผนสำรอง) ---
def _detect_language_from_string(track_name: str, artist_name: str) -> str:
    """
    (Fallback) ตรวจจับกลุ่มภาษาของเพลงจาก "ตัวอักษร"
    """
    text_to_check = f"{track_name} {artist_name}"
    
    # ตรวจหาอักขระ CJK (จีน, ญี่ปุ่น, เกาหลี)
    if re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]', text_to_check):
        return 'cjk'
    
    # ตรวจหาอักขระไทย
    if re.search(r'[\u0e00-\u0e7f]', text_to_check):
        return 'th'
        
    return 'latin'

# --- (*** ใหม่: Helper สำหรับวิเคราะห์อารมณ์จากคำขอ ***) ---
async def get_mood_profile_from_message(user_message: str) -> dict:
    """
    วิเคราะห์ "เฉพาะ" ข้อความคำขอของผู้ใช้ เพื่อสร้างโปรไฟล์อารมณ์เป้าหมาย
    """
    logging.info(f"Deriving target emotion from request: '{user_message}'")
    try:
        # ใช้ predict_moods จาก custom_model (เร็วและทำงานแบบ local)
        # (เราใช้ to_thread เพราะ predict_moods (ที่ใช้ model.predict) ไม่ใช่ async)
        moods = await asyncio.to_thread(predict_moods, user_message)
        
        if not moods:
            logging.warning("Could not derive moods from request, returning empty dict.")
            return {}
            
        logging.info(f"Derived request moods: {moods}")
        return moods
        
    except Exception as e:
        logging.error(f"Failed to predict moods from user message: {e}")
        return {}

# --- (*** ใหม่: Helper 2: ตรวจจับภาษาจาก Genre ***) ---
def _classify_lang_from_genres(genres: list[str]) -> str | None:
    """
    (Primary) ตรวจจับกลุ่มภาษาจาก List of Genres ของศิลปิน
    """
    if not genres: 
        return None
        
    genres_str = " ".join(genres).lower()
    
    # ตรวจสอบ CJK (ญี่ปุ่น) ก่อน
    if any(g in genres_str for g in ['j-pop', 'j-rock', 'anime', 'j-idol', 'japanese', 'j-metal', 'vocaloid', 'touhou']):
        return 'cjk'
    
    # ตรวจสอบ เกาหลี
    if any(g in genres_str for g in ['k-pop', 'k-rock', 'k-indie', 'korean']):
        return 'korean'
        
    # ตรวจสอบ ไทย
    if any(g in genres_str for g in ['thai', 't-pop', 'luk-thung', 'molam']):
        return 'th'
        
    # ถ้าไม่เจอ Genre ที่ระบุ ให้คืนค่า None (จะไปเข้าแผนสำรอง)
    return None

# --- (*** อัปเกรด: Helper 3: วิเคราะห์ภาษาหลักโดยใช้ Genre ***) ---
async def _determine_language_guardrail(sp_client: spotipy.Spotify, seed_tracks: list[dict]) -> tuple[str | None, str | None]:
    """
    (V3 - Dual Return) วิเคราะห์โปรไฟล์ภาษา
    คืนค่า 2 ค่า:
    1. guardrail_lang: ภาษาที่จะใช้ "กรอง" อย่างเข้มงวด (ถ้า > 70%)
    2. dominant_lang: ภาษาหลักของผู้ใช้ (สำหรับ "สั่ง" AI)
    """
    logging.info("--- 🛡️ Analyzing Language Profile for Guardrail (V3 - Dual Return) ---")
    
    artist_ids = {track['artists'][0]['id'] for track in seed_tracks if track and track.get('artists')}
    if not artist_ids:
        logging.info("No artists found in seeds. Guardrail disabled.")
        return None, None # <--- คืนค่า tuple (2 ค่า)

    artist_id_list = list(artist_ids)
    artist_genres_map = {}
    
    for i in range(0, len(artist_id_list), 50): 
        batch_ids = artist_id_list[i:i+50]
        try:
            artist_results = await asyncio.to_thread(sp_client.artists, artists=batch_ids)
            if artist_results and artist_results.get('artists'):
                for artist in artist_results['artists']:
                    if artist: 
                        artist_genres_map[artist['id']] = artist.get('genres', [])
        except Exception as e:
            logging.error(f"Error batch fetching artist genres: {e}")
    logging.info(f"Successfully fetched genres for {len(artist_genres_map)} artists.")

    lang_counts = Counter()
    for track in seed_tracks:
        if not track or not track.get('artists'): 
            continue
        
        track_name = track['name']
        artist = track['artists'][0]
        artist_id = artist['id']
        artist_name = artist['name']

        genres = artist_genres_map.get(artist_id, [])
        lang = _classify_lang_from_genres(genres)

        if lang is None:
            lang = _detect_language_from_string(track_name, artist_name)
        
        lang_counts.update([lang])
            
    if not lang_counts:
        logging.info("No language data found after analysis. Guardrail disabled.")
        return None, None # <--- คืนค่า tuple (2 ค่า)

    dominant_lang, count = lang_counts.most_common(1)[0]
    total = sum(lang_counts.values())
    percentage = (count / total) * 100

    logging.info(f"Language profile: {dict(lang_counts)}")
    
    guardrail_lang = None
    if percentage >= 70: # เกณฑ์ 70% (ถูกต้องแล้ว)
        logging.info(f"✅ Language Guardrail (Filter) ENABLED: '{dominant_lang}' ({percentage:.0f}%)")
        guardrail_lang = dominant_lang
    else:
        logging.info(f"User listens to multiple languages ({percentage:.0f}% dominant). Guardrail (Filter) DISABLED.")
    
    # dominant_lang คือภาษาหลักเสมอ (ตราบใดที่มันไม่ None)
    logging.info(f"User's Dominant Language (for Prompting) is: '{dominant_lang}'")
    return guardrail_lang, dominant_lang


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

    sem = asyncio.Semaphore(8) # จำกัด 8 connections พร้อมกัน

    async def get_initial_lyrics(track):
        await sem.acquire()
        try:
            if track and 'name' in track and 'artists' in track and track['artists']:
                lyrics = await get_lyrics(track['artists'][0]['name'], track['name'])
                if lyrics:
                    lyrics_found[track['uri']] = lyrics
                else:
                    failed_tracks.append(track)
        except Exception:
            failed_tracks.append(track)
        finally:
            sem.release()

    await asyncio.gather(*[get_initial_lyrics(track) for track in seed_tracks_list[:15]])
    
    rescued_lyrics_dict = await rescue_lyrics_with_gemini(failed_tracks)
    
    for track in failed_tracks:
        artist_name = track.get('artists', [{}])[0].get('name', 'N/A')
        track_name = track.get('name', 'N/A')
        key = f"{artist_name} - {track_name}"
        
        if key in rescued_lyrics_dict and rescued_lyrics_dict[key]:
            lyrics_found[track['uri']] = rescued_lyrics_dict[key]

    logging.info(f"Total lyrical content gathered for {len(lyrics_found)} tracks after rescue mission.")
    if not lyrics_found:
        return {}
        
    all_fingerprints = [predict_moods(content) for content in lyrics_found.values() if content]
    
    if not all_fingerprints:
        return {}

    avg_fingerprint = {}
    if not all_fingerprints[0]:
        return {}
        
    labels = all_fingerprints[0].keys()
    for label in labels:
        avg_score = sum(fp.get(label, 0.0) for fp in all_fingerprints) / len(all_fingerprints)
        avg_fingerprint[label] = avg_score
    
    logging.info("✅ Target Emotional Fingerprint created.")
    return avg_fingerprint

# --- [DELETED] Unused calculate_mood_score function ---

async def analyze_and_cache_song_moods(
    spotify_track: dict, 
    lang_hint: str | None = None,
    use_gemini: bool = True,
    _cleaned_artist_name: str | None = None # <-- [FIX] เพิ่ม Parameter ใหม่
) -> tuple[dict | None, bool]:
    """
    (V5 - Genre-Aware Smart Strategy)
    """
    if not spotify_track or 'uri' not in spotify_track:
        return None, False

    # 1. ตรวจสอบ Cache ก่อน (เหมือนเดิม)
    cached_analysis = await get_song_analysis_from_db(spotify_track['uri'])
    if cached_analysis and 'predicted_moods' in cached_analysis:
        return cached_analysis['predicted_moods'], True

    # --- [FIX: THE "CV" FIX] ---
    # ถ้าเราได้ชื่อที่สะอาดมาแล้ว (จาก _analyze_with_genius_only) ให้ใช้ชื่อนั้น
    # แต่ถ้าถูกเรียกจากที่อื่น ให้ใช้ชื่อเดิมจาก track object
    artist_name = _cleaned_artist_name if _cleaned_artist_name else spotify_track.get('artists', [{}])[0].get('name', 'N/A')
    # --- [END CV FIX] ---
    
    track_name = spotify_track.get('name', 'N/A')
    
    lyrics = None

    # --- (ตรรกะ V5 - Gemini Switch) ---
    strategy = lang_hint if lang_hint else 'latin' 
    
    if not use_gemini:
        # ** STRATEGY 0: "Genius-Only" Mode (use_gemini=False) **
        logging.info(f"Genius-Only strategy for '{track_name}'.")
        # เราส่ง artist_name ที่สะอาดแล้วไปให้ get_lyrics
        lyrics = await get_lyrics(artist_name, track_name)
    
    elif strategy == 'latin':
        # Strategy 1: Latin -> Genius ก่อน
        logging.info(f"Lang '{strategy}' strategy for '{track_name}'. Trying Genius (Plan A)...")
        lyrics = await get_lyrics(artist_name, track_name)
        
        if (not lyrics or len(lyrics) < 50) and use_gemini:
            logging.warning(f"Genius failed for '{track_name}'. Trying Gemini (Plan B)...")
            rescued_data = await rescue_lyrics_with_gemini([spotify_track])
            key = f"{artist_name} - {track_name}" # (Gemini rescue ยังอาจจะใช้ชื่อไม่สะอาด แต่นั่นคือ Plan B)
            if key in rescued_data and rescued_data[key]:
                lyrics = rescued_data[key]
    else:
        # Strategy 2: CJK, Thai -> Gemini ก่อน
        logging.info(f"Lang '{strategy}' strategy for '{track_name}'. Trying Gemini (Plan A)...")
        rescued_data = await rescue_lyrics_with_gemini([spotify_track])
        key = f"{artist_name} - {track_name}"
        
        if key in rescued_data and rescued_data[key]:
            lyrics = rescued_data[key]
        else:
            logging.warning(f"Gemini failed for '{track_name}'. Trying Genius (Plan B)...")
            lyrics = await get_lyrics(artist_name, track_name)
    # --- (จบตรรกะ V5) ---

    # 3. ประมวลผลเนื้อเพลงที่หามาได้ (เหมือนเดิม)
    if lyrics and len(lyrics) > 50:
        moods = predict_moods(lyrics)
        if moods:
            await save_song_analysis_to_db(spotify_track, {"predicted_moods": moods})
            return moods, True
    
    # 4. ถ้าล้มเหลวทั้งหมด
    logging.warning(f"All lyric strategies failed for '{track_name}'.")
    return None, False

def calculate_cosine_similarity(profile1: dict, profile2: dict) -> float:
    if not profile1 or not profile2: return 0.0
    labels = sorted(list(profile1.keys()))
    vec1 = np.array([profile1.get(label, 0.0) for label in labels])
    vec2 = np.array([profile2.get(label, 0.0) for label in labels])
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0: return 0.0
    return dot_product / (norm1 * norm2)

# --- (*** นี่คือฟังก์ชันที่อัปเกรดตาม Workflow ของคุณ ***) ---
# --- (*** นี่คือฟังก์ชันฉบับเต็มที่คุณขอ ***) ---
# --- (*** นี่คือฟังก์ชันที่อัปเกรดตาม Workflow ของคุณ ***) ---
# --- (*** นี่คือฟังก์ชันฉบับเต็มที่คุณขอ ***) ---
# (นี่คือโค้ดเต็มของ get_intelligent_recommendations ใน recommender.py)
# (*** V19: แก้ไข Bug การสร้าง Candidate - ใช้ Gemini Expansion ***)
async def get_intelligent_recommendations(
    sp_client: spotipy.Spotify, 
    user_id: str, 
    stylistic_profile: dict,
    emotional_profile: dict,
    user_message: str
) -> list[dict]:
    """
    (Hybrid V19 - Gemini-Expansion-Based Discovery)
    """
    # --- Constants ---
    MINIMUM_PLAYLIST_SIZE = 10
    STRICT_SCORE_THRESHOLD = 0.45 
    LOOSE_SCORE_THRESHOLD = 0.25
    MAX_FILLER_ITERATIONS = 3 

    logging.info("--- Initializing V19: Iterative Curation Loop (Gemini Expansion & Batch Lyrics) ---")

    # ==========================================
    # [NUCLEAR FIX] COLD START DETECTION V2.0
    # ==========================================
    
    logging.info("🔍 Starting Cold Start Detection...")
    
    # Step 1: Gather seed tracks
    try:
        user_seed_tracks = await get_seed_tracks(sp_client)
    except Exception as e:
        logging.error(f"❌ Failed to get seed tracks: {e}")
        user_seed_tracks = []
    
    # Step 2: Count the tracks explicitly
    seed_count = 0
    if user_seed_tracks is not None:
        seed_count = len(user_seed_tracks)
    
    logging.info(f"📊 Seed Track Count: {seed_count}")
    
    # Step 3: Explicit boolean check
    is_cold_start = False
    
    if seed_count == 0:
        is_cold_start = True
        logging.warning("⚠️ COLD START TYPE A: Zero seed tracks found")
    elif seed_count < 3:
        is_cold_start = True
        logging.warning(f"⚠️ COLD START TYPE B: Insufficient data ({seed_count} tracks < 3 minimum)")
    else:
        logging.info(f"✅ Sufficient data found: {seed_count} seed tracks")
    
    # Step 4: Execute fallback if cold start detected
    if is_cold_start is True:
        logging.warning("🚨 ACTIVATING FALLBACK SYSTEM...")
        
        try:
            fallback_tracks = await get_fallback_recommendations(sp_client)
            
            # Verify fallback actually returned data
            if fallback_tracks and len(fallback_tracks) > 0:
                logging.info(f"✅ Fallback successful: {len(fallback_tracks)} tracks returned")
                return fallback_tracks
            else:
                logging.error("❌ Fallback returned empty list")
                return []
                
        except Exception as e:
            logging.error(f"❌ Fallback system crashed: {e}")
            return []
    
    # ==========================================
    # [END NUCLEAR FIX]
    # ==========================================
    
    guardrail_language, dominant_language_for_prompting = await _determine_language_guardrail(sp_client, user_seed_tracks)
    
    history_uris = await get_recommendation_history(user_id)
    existing_uris = {t['uri'] for t in user_seed_tracks}
    feedback_data = await get_user_feedback(user_id)
    disliked_uris = feedback_data.get('dislikes', set())
    
    master_blacklist = existing_uris.union(history_uris).union(disliked_uris)
    logging.info(f"Master blacklist initialized with {len(master_blacklist)} URIs (Existing + History + Dislikes).")


    # (Part 2: Candidate Generation)
    # --- [FIX V19: แทนที่ V16 Search Logic ด้วย Gemini Expansion] ---
    candidate_tracks_info = []
            
    logging.info(f"--- 🧬 Calling Gemini Seed Expansion ---")
    
    # เราใช้ user_seed_tracks (ซึ่งรวม Top+Recent+Liked) เพื่อให้ Gemini มี context ที่ดีที่สุด
    gemini_candidates = await get_gemini_seed_expansion(user_seed_tracks, user_message)

    if not gemini_candidates:
        logging.error("Gemini Seed Expansion found 0 candidates. Using fallback.")
        return await get_fallback_recommendations(sp_client)

    # แปลงผลลัพธ์จาก Gemini ให้อยู่ใน format ที่ V17/V18 คาดหวัง
    for track in gemini_candidates:
        candidate_tracks_info.append({
            "artist": track.get('artist'),
            "title": track.get('title'),
            "spotify_track_object": None  # <-- ตั้งเป็น None เพื่อให้ logic ด้านล่างไป search หา
        })
    # --- [END FIX V19] ---
    
    logging.info(f"--- 🧬 Candidate Tracks (Total: {len(candidate_tracks_info)}) ---")
    
    
    # --- ( Part 3: Parallel Lyric Analysis ) ---
    analysis_results = {}
    tracks_failed_genius = [] 
    sem = asyncio.Semaphore(10)

    async def _analyze_with_genius_only(track_info, blacklist_to_use):
        """
        (V18 Logic - ถูกเรียกโดย V19)
        """
        await sem.acquire()
        try:
            spotify_track = track_info.get("spotify_track_object")
            
            # --- [FIX V19: ค้นหา Track Object ถ้ามันไม่มี (มาจาก Gemini)] ---
            if not spotify_track:
                title = track_info.get('title', '')
                artist = track_info.get('artist', '')

                # 1. แผน A: ค้นหาแบบเจาะจง (Strict Search)
                query = f"track:{title} artist:{artist}"
                spotify_results = await search_spotify_songs(sp_client, query, limit=1)
                
                # 2. แผน B: ถ้าไม่เจอ ให้ค้นหาแบบกว้าง (Loose Search)
                if not spotify_results:
                    logging.info(f"Strict search failed for '{title}'. Trying loose search...")
                    # เอาชื่อเพลงกับศิลปินมาต่อกันเลย ให้ Spotify ช่วยเดา
                    loose_query = f"{title} {artist}"
                    spotify_results = await search_spotify_songs(sp_client, loose_query, limit=1)

                if not spotify_results: 
                    logging.warning(f"Could not find Spotify track for: {title} by {artist} (Both Strict & Loose search failed)")
                    return # ยอมแพ้จริงๆ
                
                spotify_track = spotify_results[0]
            # --- [END FIX V19] ---
            
            if spotify_track['uri'] in blacklist_to_use:
                return
            
            track_name, artist = spotify_track.get('name', ''), spotify_track.get('artists', [{}])[0]
            artist_id, artist_name = artist.get('id'), artist.get('name', '')
            
            # --- [FIX: THE "CV" FIX] ---
            if '(CV:' in artist_name:
                artist_name = artist_name.split('(CV:')[0].strip()
            # --- [END CV FIX] ---
            
            # --- [BOOSTER LOGIC - PART 1A] ---
            artist_genre_lang = None
            if artist_id:
                try:
                    artist_details = await asyncio.to_thread(sp_client.artist, artist_id=artist_id)
                    if artist_details: 
                        artist_genre_lang = _classify_lang_from_genres(artist_details.get('genres', []))
                except Exception: 
                    pass 

            song_lang = artist_genre_lang
            if song_lang is None:
                song_lang = _detect_language_from_string(track_name, artist_name)
            
            if guardrail_language and song_lang != guardrail_language:
                logging.info(f"GUARDRAIL (Info): '{track_name}' (Lang: {song_lang}) mismatches profile. Will analyze anyway.")
            
            lang = song_lang
            # --- [END PART 1A] ---
            
            moods_tuple = await analyze_and_cache_song_moods(
                spotify_track, 
                lang_hint=lang, 
                use_gemini=False,
                _cleaned_artist_name=artist_name 
            )
            moods = moods_tuple[0] 

            if moods:
                # --- [BOOSTER LOGIC - PART 1B] ---
                analysis_results[spotify_track['uri']] = {
                    "track_object": spotify_track, 
                    "moods": moods,
                    "detected_lang": song_lang
                }
                # --- [END PART 1B] ---
                master_blacklist.add(spotify_track['uri']) 
            else:
                tracks_failed_genius.append(spotify_track) 

        except Exception as e:
            logging.error(f"Error in _analyze_with_genius_only '{track_info.get('title')}': {e}", exc_info=False)
        finally:
            sem.release()

    # (V17) Step 1: รัน Genius Plan A
    analysis_tasks_genius = [_analyze_with_genius_only(info, master_blacklist) for info in candidate_tracks_info]
    await asyncio.gather(*analysis_tasks_genius)
    
    logging.info(f"Genius (Plan A) complete. Found {len(analysis_results)} lyrics. Failed: {len(tracks_failed_genius)}")

    # (V17) Step 2: รัน Gemini Plan B (Batch Request)
    if tracks_failed_genius:
        logging.info(f"Calling Gemini (Plan B) in one batch for {len(tracks_failed_genius)} tracks...")
        try:
            rescued_lyrics_map = await rescue_lyrics_with_gemini(tracks_failed_genius)
            
            for spotify_track in tracks_failed_genius:
                artist_name = spotify_track.get('artists', [{}])[0].get('name', 'N/A')
                track_name = spotify_track.get('name', 'N/A')
                track_key = f"{artist_name} - {track_name}"
                lyrics = rescued_lyrics_map.get(track_key)
                
                if lyrics:
                    logging.info(f"Gemini (Plan B) rescued lyrics for '{track_name}'")
                    moods = await asyncio.to_thread(predict_moods, lyrics)
                else:
                    logging.warning(f"Failed to find lyrics for '{track_name}' (Genius & Gemini). Scoring as 'neutral'.")
                    moods = {'neutral': 1.0}
                
                analysis_results[spotify_track['uri']] = {"track_object": spotify_track, "moods": moods}
                master_blacklist.add(spotify_track['uri']) 

        except Exception as e:
            logging.error(f"Gemini (Plan B) batch request failed: {e}", exc_info=True)

    logging.info(f"Completed initial analysis. Found lyrics/data for {len(analysis_results)} tracks.")
    # --- [ จบ Part 3 ] ---

    
    # (Part 4: Scoring Helpers)
    disliked_fingerprints = []
    for uri in disliked_uris:
        track_info = await get_spotify_track_data(sp_client, uri)
        if track_info:
            song_fingerprint, success = await analyze_and_cache_song_moods(track_info, lang_hint=None) 
            if success and song_fingerprint:
                disliked_fingerprints.append(song_fingerprint)
                
    total_years, track_count = 0, 0
    for track in user_seed_tracks:
        try:
            if track and track.get('album') and track['album'].get('release_date'):
                total_years += int(track['album']['release_date'][:4])
                track_count += 1
        except (ValueError, KeyError, IndexError, TypeError): continue
    average_year = total_years / track_count if track_count > 0 else None

    # --- [FIX 2: BOOSTER LOGIC - APPLY SCORE] ---
    # (Part 5: Two-Vector Scoring)
    logging.info("--- 📈 Scoring All Analyzed Candidates (V5 Two-Vector) ---")
    all_scored_candidates = []
    if not analysis_results:
        logging.warning("No candidates left after analysis. Returning fallback.")
        return await get_fallback_recommendations(sp_client)
    
    has_target_emotion = any(v > 0.1 for v in emotional_profile.values())
    if not has_target_emotion:
        logging.info("No specific emotion detected in request. Using Stylistic Profile only.")

    for uri, result in analysis_results.items():
        spotify_track = result["track_object"]
        song_fingerprint = result["moods"]
        song_lang = result.get("detected_lang")

        stylistic_score = calculate_cosine_similarity(stylistic_profile, song_fingerprint)
        
        if has_target_emotion:
            emotional_score = calculate_cosine_similarity(emotional_profile, song_fingerprint)
            combined_mood_score = (emotional_score * 0.7) + (stylistic_score * 0.3)
        else:
            combined_mood_score = stylistic_score
        
        dislike_penalty = 0.0
        for disliked_fp in disliked_fingerprints:
            penalty_similarity = calculate_cosine_similarity(song_fingerprint, disliked_fp)
            if penalty_similarity > dislike_penalty:
                dislike_penalty = penalty_similarity
        
        year_bonus = 0.0
        if average_year:
            try:
                candidate_year = int(spotify_track['album']['release_date'][:4])
                year_difference = abs(candidate_year - average_year)
                if year_difference < 10:
                    year_bonus = 0.15 * (1 - (year_difference / 10))
            except (ValueError, KeyError, IndexError, TypeError):
                year_bonus = 0.0
        
        language_bonus = 0.0
        if guardrail_language:
            if song_lang == guardrail_language:
                language_bonus = 0.15 
            elif song_lang == 'latin':
                language_bonus = 0.0
        
        final_score = (combined_mood_score * 0.7) + language_bonus + (year_bonus * 0.8) - (dislike_penalty * 0.6)
        
        spotify_track['ai_analysis'] = {"mood_score": float(final_score), "lang_bonus": language_bonus}
        all_scored_candidates.append(spotify_track)
    # --- [END FIX 2] ---
    
    all_scored_candidates.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)
    
    # (Part 6: Iterative Filler Loop)
    logging.info(f"--- Starting Round 1: Strict Filtering (Threshold: {STRICT_SCORE_THRESHOLD}) ---")
    final_playlist = [
        track for track in all_scored_candidates 
        if track['ai_analysis']['mood_score'] >= STRICT_SCORE_THRESHOLD
    ]
    logging.info(f"Round 1 completed. {len(final_playlist)} songs passed strict filtering.")
    
    current_iteration = 0
    while len(final_playlist) < MINIMUM_PLAYLIST_SIZE and current_iteration < MAX_FILLER_ITERATIONS:
        current_iteration += 1
        needed = MINIMUM_PLAYLIST_SIZE - len(final_playlist)
        logging.warning(f"Playlist too short. Starting Filler Iteration {current_iteration}/{MAX_FILLER_ITERATIONS}. Need {needed} more.")

        seed_source_list = await get_user_top_tracks(sp_client, limit=10)
        num_seeds_to_pick = min(len(seed_source_list), 5)
        seed_tracks_for_filler = random.sample(seed_source_list, num_seeds_to_pick)
        logging.info(f"Using RANDOMIZED Top-Tracks seeds for filler: {[t['name'] for t in seed_tracks_for_filler]}")

        filler_candidates_info = []
        try:
            # --- [FIX V19: ใช้ Gemini Filler แทนการ search] ---
            logging.info(f"Filler Iteration {current_iteration}: Calling Gemini Filler...")
            # ใช้ dominant_language_for_prompting เพื่อบอก AI ว่าจะเอาเพลงภาษาอะไร
            lang_code_for_prompt = dominant_language_for_prompting if dominant_language_for_prompting else 'latin'
            
            filler_gemini_results = await get_filler_tracks_with_lyrics(
                seed_tracks_for_filler,
                lang_code_for_prompt
            )

            if filler_gemini_results:
                for track in filler_gemini_results:
                    filler_candidates_info.append({
                        "artist": track.get('artist'),
                        "title": track.get('track'), # Key ใน filler คือ 'track'
                        "spotify_track_object": None 
                    })
            # --- [END FIX V19] ---
            
        except Exception as e: 
            logging.error(f"Filler Iteration {current_iteration}: Gemini Filler strategy failed: {e}")

        if not filler_candidates_info:
            logging.error(f"Filler Iteration {current_iteration}: No new candidates found. Stopping loop.")
            break 

        # (Filler Loop)
        analysis_results.clear()
        tracks_failed_genius_filler = []
        
        filler_genius_tasks = [_analyze_with_genius_only(info, master_blacklist) for info in filler_candidates_info]
        await asyncio.gather(*filler_genius_tasks)

        logging.info(f"Filler Iteration {current_iteration} (Plan A): Found {len(analysis_results)} lyrics. Failed: {len(tracks_failed_genius_filler)}")
        
        if tracks_failed_genius_filler:
            logging.info(f"Calling Gemini (Plan B) in one batch for {len(tracks_failed_genius_filler)} filler tracks...")
            try:
                rescued_lyrics_map_filler = await rescue_lyrics_with_gemini(tracks_failed_genius_filler)
                
                for spotify_track in tracks_failed_genius_filler:
                    artist_name = spotify_track.get('artists', [{}])[0].get('name', 'N/A')
                    track_name = spotify_track.get('name', 'N/A')
                    track_key = f"{artist_name} - {track_name}"
                    lyrics = rescued_lyrics_map_filler.get(track_key)
                    moods = await asyncio.to_thread(predict_moods, lyrics) if lyrics else {'neutral': 1.0}
                    
                    analysis_results[spotify_track['uri']] = {"track_object": spotify_track, "moods": moods}
                    master_blacklist.add(spotify_track['uri'])
            except Exception as e:
                logging.error(f"Gemini (Plan B) filler batch failed: {e}", exc_info=True)

        new_filler_songs = []
        for uri, result in analysis_results.items():
            spotify_track = result["track_object"]
            song_fingerprint = result["moods"]

            stylistic_score = calculate_cosine_similarity(stylistic_profile, song_fingerprint)
            if has_target_emotion:
                emotional_score = calculate_cosine_similarity(emotional_profile, song_fingerprint)
                final_score = (emotional_score * 0.7) + (stylistic_score * 0.3)
            else:
                final_score = stylistic_score
            
            spotify_track['ai_analysis'] = {"mood_score": float(final_score)}

            if final_score >= LOOSE_SCORE_THRESHOLD:
                new_filler_songs.append(spotify_track)

        if not new_filler_songs:
            logging.warning(f"Filler Iteration {current_iteration}: No new songs passed loose filter. Stopping.")
            break 

        new_filler_songs.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)
        final_playlist.extend(new_filler_songs)
        logging.info(f"Filler Iteration {current_iteration}: Added {len(new_filler_songs)}. Total now: {len(final_playlist)}")
    
    # (Part 7: Finalizing)
    if not final_playlist:
        logging.error("All recommendation iterations failed. Returning final fallback.")
        return await get_fallback_recommendations(sp_client)

    final_playlist.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)
    final_playlist = final_playlist[:15] 
    
    if final_playlist:
        await save_recommendation_history(user_id, [t['uri'] for t in final_playlist])
    
    logging.info(f"--- ✅ Final Curated Playlist ({len(final_playlist)} Songs) ---")
    for i, track in enumerate(final_playlist[:10]):
        logging.info(f"  {i+1}. (Score: {track['ai_analysis']['mood_score']:.4f}) '{track['name']}' by {track['artists'][0]['name']}")

# 🔥 NEW: auto preload song details
    await preload_gemini_details(sp_client, final_playlist)

    return final_playlist

# (*** แก้ไข ***) เพิ่ม Log ในฟังก์ชันนี้
# ================================================
# ✅ PATCH: Auto-Fallback Cold Start (V3 - Kantapong Fix)
# ================================================
import logging
import asyncio
import random
from spotify_api import (
    get_user_top_tracks,
    get_user_saved_tracks,
    get_user_recently_played_tracks,
    get_fallback_recommendations  # ✅ ต้องแน่ใจว่ามี import นี้
)

async def get_seed_tracks(sp_client: spotipy.Spotify) -> list[dict]:
    """
    รวบรวมเพลงเมล็ดพันธุ์จาก Top Tracks, Saved Tracks, และ Recently Played
    (V3 - Auto Fallback: ถ้าไม่มีเพลงเลย จะดึง Fallback จากระบบอัตโนมัติ)
    """
    tasks = [
        get_user_top_tracks(sp_client, limit=10),
        get_user_saved_tracks(sp_client, limit=10),
        get_user_recently_played_tracks(sp_client, limit=5)
    ]
    results = await asyncio.gather(*tasks)
    top_tracks, liked_tracks, recent_tracks = results

    logging.info("--- 🌱 Identifying Seed Tracks ---")

    logging.info(f"--- 🌙 User Recently Played Tracks ({len(recent_tracks)}) ---")
    if recent_tracks:
        for i, track in enumerate(recent_tracks):
            if track and track.get('name') and track.get('artists'):
                logging.info(f"  {i+1}. '{track['name']}' by {track['artists'][0]['name']}")
    else:
        logging.info("  (No recently played tracks found)")

    logging.info(f"--- 🏆 User Top Tracks ({len(top_tracks)}) ---")
    if top_tracks:
        for i, track in enumerate(top_tracks):
            if track and track.get('name') and track.get('artists'):
                logging.info(f"  {i+1}. '{track['name']}' by {track['artists'][0]['name']}")
    else:
        logging.info("  (No top tracks found)")

    logging.info(f"--- ❤️ User Liked Tracks ({len(liked_tracks)}) ---")
    if liked_tracks:
        for i, track in enumerate(liked_tracks):
            if track and track.get('name') and track.get('artists'):
                logging.info(f"  {i+1}. '{track['name']}' by {track['artists'][0]['name']}")
    else:
        logging.info("  (No liked tracks found)")

    # รวมทั้งหมด (ป้องกันซ้ำ)
    all_seed_tracks = {}
    for track in top_tracks + liked_tracks + recent_tracks:
        if track and track.get('uri') and track['uri'] not in all_seed_tracks:
            all_seed_tracks[track['uri']] = track

    # ✅ ถ้าไม่มี seed tracks เลย → ใช้ fallback จาก spotify_api
    if not all_seed_tracks:
        logging.warning("⚠️ No seed tracks found. Using fallback recommendations as seed source.")
        try:
            fallback_tracks = await get_fallback_recommendations(sp_client)
            if fallback_tracks and len(fallback_tracks) > 0:
                for track in fallback_tracks:
                    if track and track.get('uri') and track['uri'] not in all_seed_tracks:
                        all_seed_tracks[track['uri']] = track
                logging.info(f"✅ Fallback seeding success: {len(all_seed_tracks)} tracks used.")
            else:
                logging.error("❌ Fallback returned empty list (no seed candidates).")
        except Exception as e:
            logging.error(f"❌ Failed to fetch fallback seeds: {e}", exc_info=True)

    logging.info(f"📊 Final Seed Track Count: {len(all_seed_tracks)}")
    return list(all_seed_tracks.values())


async def update_user_profile_background(token_info: dict, user_id: str):
    """
    (V3 - Safe & Correct) Creates its own isolated Spotify client from token info
    to prevent coroutine and attribute errors.
    """
    logging.info(f"BACKGROUND TASK: Received request for user {user_id}...")
    try:
        bg_sp_client = create_spotify_client(token_info)

        profile_data = await get_user_mood_profile_with_timestamp(user_id)
        if profile_data:
            last_updated_str = profile_data['timestamp']
            last_updated_dt = datetime.strptime(last_updated_str, '%Y-%m-%d %H:%M:%S')

            if datetime.now() - last_updated_dt < timedelta(hours=1):
                logging.info(f"BACKGROUND TASK: Profile for {user_id} is recent. Skipping update.")
                return

        logging.info(f"BACKGROUND TASK: Profile is old or non-existent. Starting analysis for user {user_id}...")
        new_profile = await build_user_mood_profile(bg_sp_client, user_id)
        if new_profile:
            await save_user_mood_profile(user_id, new_profile)
            logging.info(f"BACKGROUND TASK: Profile for {user_id} successfully updated.")

    except Exception as e:
        logging.error(f"BACKGROUND TASK: An error occurred for user {user_id}: {e}", exc_info=True)