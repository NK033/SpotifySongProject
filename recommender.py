# recommender.py (V13.3 - Genre-Based Guardrail)
import asyncio
import spotipy
import logging
import re  
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
from lastfm_api import get_similar_tracks, get_chart_top_tracks, get_global_top_tracks, get_artist_top_tracks
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
async def _determine_language_guardrail(sp_client: spotipy.Spotify, seed_tracks: list[dict]) -> str | None:
    """
    (V2 - Genre-Based) วิเคราะห์เพลง Seed ทั้งหมดเพื่อหาว่ามีภาษาใดเด่นชัด (เกิน 80%) หรือไม่
    """
    logging.info("--- 🛡️ Analyzing Language Profile for Guardrail (V2 - Genre-Based) ---")
    
    # 1. รวบรวม Artist IDs ทั้งหมดจาก Seed Tracks
    artist_ids = {track['artists'][0]['id'] for track in seed_tracks if track and track.get('artists')}
    if not artist_ids:
        logging.info("No artists found in seeds. Guardrail disabled.")
        return None

    # 2. ดึงข้อมูลศิลปินทั้งหมดในครั้งเดียว (Batch Request)
    artist_id_list = list(artist_ids)
    artist_genres_map = {}
    
    for i in range(0, len(artist_id_list), 50): # API Spotify จำกัดครั้งละ 50
        batch_ids = artist_id_list[i:i+50]
        try:
            # ใช้ asyncio.to_thread เพราะ spotipy.artists ยังไม่รองรับ async
            artist_results = await asyncio.to_thread(sp_client.artists, artists=batch_ids)
            if artist_results and artist_results.get('artists'):
                for artist in artist_results['artists']:
                    if artist: 
                        artist_genres_map[artist['id']] = artist.get('genres', [])
        except Exception as e:
            logging.error(f"Error batch fetching artist genres: {e}")

    logging.info(f"Successfully fetched genres for {len(artist_genres_map)} artists.")

    # 3. เริ่มนับคะแนนภาษา
    lang_counts = Counter()
    for track in seed_tracks:
        if not track or not track.get('artists'): 
            continue
        
        track_name = track['name']
        artist = track['artists'][0]
        artist_id = artist['id']
        artist_name = artist['name']

        # 4. ตรวจสอบ (Priority 1: Check Genre)
        genres = artist_genres_map.get(artist_id, [])
        lang = _classify_lang_from_genres(genres)

        # 5. ตรวจสอบ (Priority 2: Fallback to character detection)
        if lang is None:
            lang = _detect_language_from_string(track_name, artist_name)
        
        lang_counts.update([lang])
            
    if not lang_counts:
        logging.info("No language data found after analysis. Guardrail disabled.")
        return None

    dominant_lang, count = lang_counts.most_common(1)[0]
    total = sum(lang_counts.values())
    percentage = (count / total) * 100

    logging.info(f"Language profile: {dict(lang_counts)}")

    # ตั้งเกณฑ์ (Threshold) ที่ 80%
    if percentage >= 80:
        logging.info(f"✅ Language Guardrail ENABLED: '{dominant_lang}' ({percentage:.0f}%)")
        return dominant_lang
    
    logging.info(f"User listens to multiple languages ({percentage:.0f}% dominant). Guardrail DISABLED.")
    return None


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

def calculate_mood_score(song_moods: list, user_profile: dict) -> float:
    """
    คำนวณคะแนนความเข้ากันได้ทางอารมณ์ระหว่างเพลงกับโปรไฟล์ของผู้ใช้
    """
    if not song_moods or not user_profile:
        return 0.0
    
    score = sum(user_profile.get(mood, 0) for mood in song_moods)
        
    return score / len(song_moods) if song_moods else 0.0

async def analyze_and_cache_song_moods(
    spotify_track: dict, 
    lang_hint: str | None = None  # <-- (ใหม่) รับ "คำใบ้" ด้านภาษา
) -> tuple[dict | None, bool]:
    """
    (V4 - Genre-Aware Smart Strategy)
    Dynamically chooses the best lyric provider based on the genre-derived lang_hint.
    """
    if not spotify_track or 'uri' not in spotify_track:
        return None, False

    # 1. ตรวจสอบ Cache ก่อน (เหมือนเดิม)
    cached_analysis = await get_song_analysis_from_db(spotify_track['uri'])
    if cached_analysis and 'predicted_moods' in cached_analysis:
        return cached_analysis['predicted_moods'], True

    artist_name = spotify_track.get('artists', [{}])[0].get('name', 'N/A')
    track_name = spotify_track.get('name', 'N/A')
    
    lyrics = None

    # --- (*** ใหม่: ตรรกะ V4 Smart Strategy ***) ---
    
    # 2. ใช้ "คำใบ้" (lang_hint) ที่ได้มาจาก Genre เพื่อเลือกแผน
    # (ถ้าไม่มีคำใบ้ ให้ default เป็น 'latin' -> Genius first)
    strategy = lang_hint if lang_hint else 'latin' 

    if strategy == 'latin':
        # Strategy 1: Latin (เพลงสากล) -> Genius ก่อน เพื่อความแม่นยำ
        logging.info(f"Lang '{strategy}' strategy for '{track_name}'. Trying Genius (Plan A)...")
        lyrics = await get_lyrics(artist_name, track_name)
        
        if not lyrics or len(lyrics) < 50:
            # Fallback (Plan B): ถ้า Genius เฟล, ค่อยเรียก Gemini
            logging.warning(f"Genius failed for '{track_name}'. Trying Gemini (Plan B)...")
            rescued_data = await rescue_lyrics_with_gemini([spotify_track])
            key = f"{artist_name} - {track_name}"
            if key in rescued_data and rescued_data[key]:
                lyrics = rescued_data[key]
    else:
        # Strategy 2: CJK, Thai (เพลงเอเชีย) -> Gemini ก่อน เพื่อโอกาสหาเจอ
        logging.info(f"Lang '{strategy}' strategy for '{track_name}'. Trying Gemini (Plan A)...")
        rescued_data = await rescue_lyrics_with_gemini([spotify_track])
        key = f"{artist_name} - {track_name}"
        
        if key in rescued_data and rescued_data[key]:
            lyrics = rescued_data[key]
        else:
            # Fallback (Plan B): ถ้า Gemini เฟล, ค่อยลอง Genius (เผื่อฟลุค)
            logging.warning(f"Gemini failed for '{track_name}'. Trying Genius (Plan B)...")
            lyrics = await get_lyrics(artist_name, track_name)
    # --- (*** จบตรรกะ V4 ***) ---

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
async def get_intelligent_recommendations(
    sp_client: spotipy.Spotify, 
    user_id: str, 
    stylistic_profile: dict,
    emotional_profile: dict,
    user_message: str
) -> list[dict]:
    """
    (Hybrid V13.4 + V4 Lyric Strategy)
    """
    MINIMUM_PLAYLIST_SIZE = 10
    STRICT_SCORE_THRESHOLD = 0.45 
    LOOSE_SCORE_THRESHOLD = 0.25
    
    logging.info("--- Initializing Hybrid V13.4: Emotion-Aware Curation ---")

    # --- Part 1: Prepare Blacklist (เหมือนเดิม) ---
    top_tracks_list = await get_user_top_tracks(sp_client, limit=10)
    if not top_tracks_list:
        logging.warning("No top tracks found for user. Using Spotify's fallback recommendations directly.")
        return await get_fallback_recommendations(sp_client)
    user_seed_tracks = await get_seed_tracks(sp_client)
    guardrail_language = await _determine_language_guardrail(sp_client, user_seed_tracks)
    history_uris = await get_recommendation_history(user_id)
    existing_uris = {t['uri'] for t in user_seed_tracks}
    feedback_data = await get_user_feedback(user_id)
    disliked_uris = feedback_data.get('dislikes', set())
    blacklist_uris = existing_uris.union(history_uris).union(disliked_uris)

    # --- Part 2: Candidate Generation (เหมือนเดิม) ---
    candidate_tracks_info = []
    MIN_CANDIDATES = 30
    logging.info("Cascade Strategy 1: Attempting Gemini Seed Expansion (Emotion-Aware)...")
    gemini_candidates = await get_gemini_seed_expansion(top_tracks_list, user_message) 
    if gemini_candidates: 
        candidate_tracks_info.extend(gemini_candidates)
    if len(candidate_tracks_info) < MIN_CANDIDATES:
        logging.info("Cascade Strategy 2: Attempting Last.fm similar tracks...")
        try:
            lastfm_similar = await get_similar_tracks(top_tracks_list[0]['artists'][0]['name'], top_tracks_list[0]['name'], limit=30)
            if lastfm_similar: candidate_tracks_info.extend(lastfm_similar)
        except Exception as e: logging.error(f"Last.fm similar tracks failed: {e}")
    if len(candidate_tracks_info) < MIN_CANDIDATES:
        logging.info("Cascade Strategy 3: Attempting Last.fm artist top tracks...")
        try:
            top_artist_name = top_tracks_list[0]['artists'][0]['name']
            lastfm_artist_top = await get_artist_top_tracks(top_artist_name, limit=20)
            if lastfm_artist_top: candidate_tracks_info.extend(lastfm_artist_top)
        except Exception as e: logging.error(f"Last.fm artist top tracks failed: {e}")
    if len(candidate_tracks_info) < MIN_CANDIDATES:
        logging.info("Cascade Strategy 4: Attempting Last.fm Global Top Tracks...")
        try:
            lastfm_global_top = await get_global_top_tracks(limit=30)
            if lastfm_global_top: candidate_tracks_info.extend(lastfm_global_top)
        except Exception as e: logging.error(f"Last.fm global top tracks failed: {e}")
    if not candidate_tracks_info:
        logging.error("All candidate generation plans failed. Using Spotify's direct fallback.")
        return await get_fallback_recommendations(sp_client)
    unique_candidates = []
    seen_candidates = set()
    for track in candidate_tracks_info:
        key = (track.get('artist', '').casefold(), track.get('title', '').casefold())
        if key not in seen_candidates and key[0] and key[1]:
            unique_candidates.append(track)
            seen_candidates.add(key)
    candidate_tracks_info = unique_candidates
    logging.info(f"--- 🧬 Candidate Tracks ({len(candidate_tracks_info)}) ---")
    for i, track in enumerate(candidate_tracks_info):
        logging.info(f"  {i+1}. '{track.get('title')}' by {track.get('artist')}")
    # --- (จบ Part 2) ---

    
    # --- (*** แก้ไข: Part 3: Parallel Lyric Analysis ***) ---
    analysis_results = {}
    sem = asyncio.Semaphore(8)

    async def _analyze_single_track(track_info):
        await sem.acquire()
        try:
            query = f"track:{track_info.get('title')} artist:{track_info.get('artist')}"
            spotify_results = await search_spotify_songs(sp_client, query, limit=1)
            if not spotify_results: return
            spotify_track = spotify_results[0]
            
            # 1. คำนวณ "ภาษา" ที่แท้จริง (จาก Genre)
            lang = None
            track_name, artist = spotify_track.get('name', ''), spotify_track.get('artists', [{}])[0]
            artist_id, artist_name = artist.get('id'), artist.get('name', '')
            
            if artist_id:
                try:
                    # เรียก Spotify API เพื่อเอา Genre (เช่น 'j-pop')
                    artist_details = await asyncio.to_thread(sp_client.artist, artist_id=artist_id)
                    if artist_details: 
                        lang = _classify_lang_from_genres(artist_details.get('genres', []))
                except Exception: 
                    pass # (ถ้า error ก็ปล่อยไป)
            
            # ถ้าหา Genre ไม่เจอ, ค่อยใช้การเดาจากตัวอักษร
            if lang is None:
                lang = _detect_language_from_string(track_name, artist_name)
            
            # 2. ตรวจสอบ Guardrail (เหมือนเดิม)
            if guardrail_language and lang != guardrail_language:
                logging.warning(f"GUARDRAIL: Filtering out '{track_name}' (Lang: {lang}) - does not match user profile ({guardrail_language}).")
                return
            
            # 3. ตรวจสอบ Blacklist (เหมือนเดิม)
            if spotify_track['uri'] in blacklist_uris:
                return
            
            # 4. เรียกใช้ฟังก์ชันวิเคราะห์ โดยส่ง "คำใบ้" (lang) ที่เราเพิ่งหามาได้
            moods_tuple = await analyze_and_cache_song_moods(spotify_track, lang_hint=lang) 
            
            moods = moods_tuple[0] # (ดึงเฉพาะ dict ออกมา)
            
            if moods:
                analysis_results[spotify_track['uri']] = {"track_object": spotify_track, "moods": moods}
                
        except Exception as e:
            logging.error(f"Error analyzing track '{track_info.get('title')}': {e}", exc_info=False)
        finally:
            sem.release()

    analysis_tasks = [_analyze_single_track(info) for info in candidate_tracks_info]
    await asyncio.gather(*analysis_tasks)
    logging.info(f"Completed parallel analysis. Found lyrics for {len(analysis_results)} tracks.")
    # --- (จบ Part 3) ---

    
    # --- (*** แก้ไข: Part 4: Scoring Helpers ***) ---
    disliked_fingerprints = []
    for uri in disliked_uris:
        track_info = await get_spotify_track_data(sp_client, uri)
        if track_info:
            # (แก้) ส่ง lang_hint=None เพราะเราไม่รู้ภาษาล่วงหน้าสำหรับเพลงที่ dislike
            # (หรือไม่จำเป็นต้องคำนวณใหม่ เพราะมันซับซ้อนเกินไปสำหรับ dislike)
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

    # --- (Part 4.5: Two-Vector Scoring - เหมือนเดิม) ---
    logging.info("--- 📈 Scoring All Analyzed Candidates (V5 Two-Vector) ---")
    all_scored_candidates = []
    if not analysis_results:
        logging.warning("No candidates left after analysis (maybe Guardrail filtered all?). Returning fallback.")
        return await get_fallback_recommendations(sp_client)
    has_target_emotion = any(v > 0.1 for v in emotional_profile.values())
    if not has_target_emotion:
        logging.info("No specific emotion detected in request. Using Stylistic Profile only.")
    for uri, result in analysis_results.items():
        spotify_track = result["track_object"]
        song_fingerprint = result["moods"]
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
        final_score = (combined_mood_score * 0.8) + year_bonus - (dislike_penalty * 0.6)
        spotify_track['ai_analysis'] = {"mood_score": float(final_score)}
        all_scored_candidates.append(spotify_track)
    all_scored_candidates.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)
    logging.info(f"--- 📊 Candidate Scores ({len(all_scored_candidates)}) ---")
    for i, track in enumerate(all_scored_candidates):
        score = track['ai_analysis']['mood_score']
        logging.info(f"  {i+1}. (Score: {score:.4f}) '{track['name']}' by {track['artists'][0]['name']}")

    # --- (*** แก้ไข: Part 6: Filler Logic ***) ---
    logging.info(f"--- Starting Round 1: Strict Filtering (Threshold: {STRICT_SCORE_THRESHOLD}) ---")
    round_1_playlist = [
        track for track in all_scored_candidates 
        if track['ai_analysis']['mood_score'] >= STRICT_SCORE_THRESHOLD
    ]
    blacklist_uris.update([t['uri'] for t in round_1_playlist])
    logging.info(f"Round 1 completed. {len(round_1_playlist)} songs passed strict filtering.")
    final_playlist = round_1_playlist
    if len(final_playlist) < MINIMUM_PLAYLIST_SIZE:
        logging.warning(f"Playlist too short. Starting Round 2: Intelligent Filler (Threshold: {LOOSE_SCORE_THRESHOLD})")
        needed = MINIMUM_PLAYLIST_SIZE - len(final_playlist)
        filler_candidates_info = []
        try:
            lastfm_similar = await get_similar_tracks(top_tracks_list[0]['artists'][0]['name'], top_tracks_list[0]['name'], limit=20)
            if lastfm_similar: filler_candidates_info.extend(lastfm_similar)
        except Exception as e: logging.error(f"Filler: Last.fm similar tracks failed: {e}")
        if len(filler_candidates_info) < needed:
            try:
                gemini_seed_tracks = final_playlist[:5] if final_playlist else top_tracks_list[:5]
                gemini_candidates = await get_filler_tracks_with_lyrics(gemini_seed_tracks)
                if gemini_candidates: filler_candidates_info.extend(gemini_candidates)
            except Exception as e: logging.error(f"Filler: Gemini filler failed: {e}")
        if not filler_candidates_info:
            logging.warning("Round 2: No filler candidates found.")
        else:
            logging.info(f"Round 2: Found {len(filler_candidates_info)} new filler candidates. Scoring them...")
            round_2_songs = []
            async def _score_filler_track(track_info):
                await sem.acquire()
                try:
                    query = f"track:{track_info.get('track') or track_info.get('title')} artist:{track_info.get('artist')}"
                    spotify_results = await search_spotify_songs(sp_client, query, limit=1)
                    if not spotify_results: return
                    spotify_track = spotify_results[0]
                    
                    # (แก้) ต้องคำนวณ lang_hint สำหรับ Filler ด้วย
                    filler_lang_hint = None
                    filler_track_name = spotify_track.get('name', '')
                    filler_artist = spotify_track.get('artists', [{}])[0]
                    filler_artist_id = filler_artist.get('id')
                    filler_artist_name = filler_artist.get('name', '')

                    if filler_artist_id:
                        try:
                            f_artist_details = await asyncio.to_thread(sp_client.artist, artist_id=filler_artist_id)
                            if f_artist_details: filler_lang_hint = _classify_lang_from_genres(f_artist_details.get('genres', []))
                        except Exception: pass
                    if filler_lang_hint is None:
                        filler_lang_hint = _detect_language_from_string(filler_track_name, filler_artist_name)

                    if guardrail_language and filler_lang_hint != guardrail_language: return
                    if spotify_track['uri'] in blacklist_uris: return
                    
                    song_fingerprint = None
                    lyrics_summary = track_info.get("lyrics_summary")
                    if lyrics_summary:
                        song_fingerprint = predict_moods(lyrics_summary)
                    else:
                        # (แก้) ส่ง lang_hint ที่เพิ่งคำนวณไปให้
                        moods_tuple = await analyze_and_cache_song_moods(spotify_track, lang_hint=filler_lang_hint)
                        song_fingerprint = moods_tuple[0]
                        
                    if not song_fingerprint: return
                    
                    stylistic_score = calculate_cosine_similarity(stylistic_profile, song_fingerprint)
                    if has_target_emotion:
                        emotional_score = calculate_cosine_similarity(emotional_profile, song_fingerprint)
                        final_score = (emotional_score * 0.7) + (stylistic_score * 0.3)
                    else:
                        final_score = stylistic_score
                    spotify_track['ai_analysis'] = {"mood_score": float(final_score)}
                    if final_score >= LOOSE_SCORE_THRESHOLD:
                        round_2_songs.append(spotify_track)
                except Exception as e:
                    logging.error(f"Error scoring filler track '{track_info.get('title')}': {e}", exc_info=False)
                finally:
                    sem.release()
            filler_tasks = [_score_filler_track(info) for info in filler_candidates_info]
            await asyncio.gather(filler_tasks)
            logging.info(f"Round 2: {len(round_2_songs)} songs passed loose filtering.")
            final_playlist.extend(round_2_songs)

    # --- (Part 7: Finalizing - เหมือนเดิม) ---
    final_playlist.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)
    final_playlist = final_playlist[:15]
    if final_playlist:
        await save_recommendation_history(user_id, [t['uri'] for t in final_playlist])
    logging.info(f"--- ✅ Final Curated Playlist ({len(final_playlist)} Songs) ---")
    for i, track in enumerate(final_playlist[:10]):
        logging.info(f"  {i+1}. (Score: {track['ai_analysis']['mood_score']:.4f}) '{track['name']}' by {track['artists'][0]['name']}")
    return final_playlist

# (*** แก้ไข ***) เพิ่ม Log ในฟังก์ชันนี้
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

    # (*** LOGGING 4 ***) แสดง Seed Tracks ทั้งหมด
    logging.info("--- 🌱 Identifying Seed Tracks ---")
    
    logging.info(f"--- 🌙 User Recently Played Tracks ({len(recent_tracks)}) ---")
    if recent_tracks:
        for i, track in enumerate(recent_tracks):
            if track and track.get('name') and track.get('artists'):
                logging.info(f"  {i+1}. '{track['name']}' by {track['artists'][0]['name']}")
    else:
        logging.info("  (No liked tracks found)")

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
    # (*** จบ LOGGING 4 ***)

    all_seed_tracks = {}
    for track in top_tracks + liked_tracks + recent_tracks:
        if track and track.get('uri') and track['uri'] not in all_seed_tracks:
            all_seed_tracks[track['uri']] = track

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