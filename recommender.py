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
from collections import defaultdict
from lastfm_api import get_similar_tracks_lastfm, get_similar_artists_lastfm, get_artist_top_tracks_lastfm
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
    get_user_feedback, get_user_mood_profile_with_timestamp,get_all_analyzed_tracks
)
from gemini_ai import get_gemini_seed_expansion
from groq_ai import (
    preload_groq_details, 
    rescue_lyrics_with_groq, 
    get_filler_tracks_groq, 
    get_seed_expansion_groq,
    get_emotional_profile_from_groq,
    translate_lyrics_to_english_groq
)

async def find_best_matches_from_db(
    sp_client: spotipy.Spotify,
    target_profile: dict, 
    blacklist_uris: set, 
    limit: int = 5
) -> list[dict]:
    """
    (Strategy A) ค้นหาเพลงจาก Database ของเราเอง
    """
    logging.info(f"--- 🏠 Searching Internal Database for matches (Limit: {limit}) ---")
    all_analyzed = await get_all_analyzed_tracks()
    if not all_analyzed: return []

    candidates = []
    for item in all_analyzed:
        uri = item['uri']
        if uri in blacklist_uris: continue
            
        score = calculate_cosine_similarity(target_profile, item['moods'])
        candidates.append((uri, score))
    
    candidates.sort(key=lambda x: x[1], reverse=True)
    top_candidates = candidates[:limit]
    
    if not top_candidates: return []

    top_uris = [c[0] for c in top_candidates]
    try:
        spotify_results = await asyncio.to_thread(sp_client.tracks, top_uris)
        valid_tracks = [t for t in spotify_results.get('tracks', []) if t]
        return valid_tracks
    except Exception:
        return []
    

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
    
    rescued_lyrics_dict = await rescue_lyrics_with_groq(failed_tracks)
    
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
            rescued_data = await rescue_lyrics_with_groq([spotify_track])
            key = f"{artist_name} - {track_name}" # (Gemini rescue ยังอาจจะใช้ชื่อไม่สะอาด แต่นั่นคือ Plan B)
            if key in rescued_data and rescued_data[key]:
                lyrics = rescued_data[key]
    else:
        # Strategy 2: CJK, Thai -> Gemini ก่อน
        logging.info(f"Lang '{strategy}' strategy for '{track_name}'. Trying Gemini (Plan A)...")
        rescued_data = await rescue_lyrics_with_groq([spotify_track])
        key = f"{artist_name} - {track_name}"
        
        if key in rescued_data and rescued_data[key]:
            lyrics = rescued_data[key]
        else:
            logging.warning(f"Gemini failed for '{track_name}'. Trying Genius (Plan B)...")
            lyrics = await get_lyrics(artist_name, track_name)
    # --- (จบตรรกะ V5) ---

    # 3. ประมวลผลเนื้อเพลงที่หามาได้ (เหมือนเดิม)
    if lyrics and len(lyrics) > 50:
        try:
            # ส่งเนื้อเพลงไปให้ Groq แปลเป็นอังกฤษก่อนเสมอ (ไม่ว่าเป็นไทย/ญี่ปุ่น/Romaji)
            # โมเดลจะได้เข้าใจได้แม่นยำที่สุด
            logging.info(f"🌍 Translating lyrics for '{track_name}' to English context...")
            lyrics = await translate_lyrics_to_english_groq(lyrics, artist_name, track_name)
        except Exception as e:
            logging.error(f"❌ Translation failed (Using original lyrics): {e}")
            
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

# (นี่คือโค้ดเต็มของ get_intelligent_recommendations ใน recommender.py)
# In recommender.py

async def get_intelligent_recommendations(
    sp_client: spotipy.Spotify, 
    user_id: str, 
    stylistic_profile: dict,
    emotional_profile: dict,
    user_message: str
) -> list[dict]:
    """
    (Hybrid V22 - High Volume & Strict Guardrails)
    """
    # --- Constants ---
    MINIMUM_PLAYLIST_SIZE = 10
    STRICT_SCORE_THRESHOLD = 0.40 # Reduced slightly to allow more valid songs
    LOOSE_SCORE_THRESHOLD = 0.20
    ANALYSIS_LIMIT = 60  # ✅ INCREASED from 30 to 60 to prevent running out of songs

    logging.info("--- Initializing V22: High Volume & Strict Analysis ---")

    # ==========================================
    # 1. COLD START & PREPARATION
    # ==========================================
    try:
        user_seed_tracks = await get_seed_tracks(sp_client)
    except Exception as e:
        logging.error(f"❌ Failed to get seed tracks: {e}")
        user_seed_tracks = []
    
    if not user_seed_tracks or len(user_seed_tracks) < 3:
        logging.warning("🚨 COLD START DETECTED: Activating Fallback...")
        return await get_fallback_recommendations(sp_client)

    guardrail_language, dominant_language_for_prompting = await _determine_language_guardrail(sp_client, user_seed_tracks)
    
    history_uris = await get_recommendation_history(user_id)
    existing_uris = {t['uri'] for t in user_seed_tracks}
    feedback_data = await get_user_feedback(user_id)
    disliked_uris = feedback_data.get('dislikes', set())
    
    master_blacklist = existing_uris.union(history_uris).union(disliked_uris)

    # =========================================================
    # (Part 2: Candidate Generation)
    # =========================================================
    candidate_tracks_info = []

    # --- Strategy A: Internal DB (10 Songs) ---
    # Increased internal matches to rely more on what we know works
    target_fingerprint = emotional_profile if any(v > 0.1 for v in emotional_profile.values()) else stylistic_profile
    internal_tracks = await find_best_matches_from_db(sp_client, target_fingerprint, master_blacklist, limit=10)
    
    for track in internal_tracks:
        candidate_tracks_info.append({
            "artist": track['artists'][0]['name'],
            "title": track['name'],
            "spotify_track_object": track
        })
        master_blacklist.add(track['uri'])
    
    # --- Strategy B: Last.fm Cooperative ---
    artist_groups = defaultdict(list)
    for track in user_seed_tracks:
        if track.get('artists'):
            name = track['artists'][0]['name']
            artist_groups[name].append(track)

    selected_seeds = []
    MAX_PER_ARTIST = 3 
    for artist, tracks in artist_groups.items():
        if len(tracks) <= MAX_PER_ARTIST:
            selected_seeds.extend(tracks)
        else:
            selected_seeds.extend(random.sample(tracks, MAX_PER_ARTIST))
    
    if len(selected_seeds) > 15: selected_seeds = random.sample(selected_seeds, 15)

    async def fetch_cooperative_candidates(seed_track):
        artist = seed_track['artists'][0]['name']
        title = seed_track['name']
        
        # neighbors
        neighbors = await get_similar_artists_lastfm(artist, limit=10)
        allowed_artists = set([n.lower() for n in neighbors])
        allowed_artists.add(artist.lower()) 

        # similar tracks (Increased limit to 60 to get more variety)
        raw_similar_tracks = await get_similar_tracks_lastfm(artist, title, limit=60)
        
        filtered = []
        for t in raw_similar_tracks:
            if t['artist'].lower() in allowed_artists:
                filtered.append(t)
        
        if not filtered and neighbors:
            top_neighbor = neighbors[0]
            backup = await get_artist_top_tracks_lastfm(top_neighbor, limit=5)
            filtered.extend(backup)
        return filtered

    expansion_tasks = [fetch_cooperative_candidates(seed) for seed in selected_seeds]
    results_lists = await asyncio.gather(*expansion_tasks)
    
    raw_candidates = []
    for sublist in results_lists: raw_candidates.extend(sublist)
    
    # Deduplicate
    seen_keys = set()
    unique_candidates = []
    for c in raw_candidates:
        key = f"{c['artist']}:{c['title']}".lower()
        if key not in seen_keys:
            unique_candidates.append(c)
            seen_keys.add(key)
            
    random.shuffle(unique_candidates)
    
    # ✅ FIX 1: INCREASED ANALYSIS LIMIT
    for track in unique_candidates[:ANALYSIS_LIMIT]:
        candidate_tracks_info.append({
            "artist": track['artist'],
            "title": track['title'],
            "spotify_track_object": None 
        })

    logging.info(f"--- 🧬 Candidates for Analysis: {len(candidate_tracks_info)} ---")

    # =========================================================
    # (Part 3: Analysis Loop - Strict V22)
    # =========================================================
    analysis_results = {}
    tracks_failed_genius = [] 
    sem = asyncio.Semaphore(12) # Increased concurrency slightly

    async def _analyze_with_strict_filters(track_info, blacklist_to_use):
        await sem.acquire()
        try:
            spotify_track = track_info.get("spotify_track_object")
            
            if not spotify_track:
                title = track_info.get('title', '')
                artist = track_info.get('artist', '')
                query = f"track:{title} artist:{artist}"
                spotify_results = await search_spotify_songs(sp_client, query, limit=1)
                
                if not spotify_results: return 
                spotify_track = spotify_results[0]
            
            if spotify_track['uri'] in blacklist_to_use: return
            
            track_name = spotify_track.get('name', '')
            artist_obj = spotify_track.get('artists', [{}])[0]
            artist_name = artist_obj.get('name', '')
            artist_id = artist_obj.get('id')
            
            if '(CV:' in artist_name:
                artist_name = artist_name.split('(CV:')[0].strip()
            
            # --- Genre Lang Detect ---
            artist_genre_lang = None
            if artist_id:
                try:
                    artist_details = await asyncio.to_thread(sp_client.artist, artist_id=artist_id)
                    if artist_details: 
                        artist_genre_lang = _classify_lang_from_genres(artist_details.get('genres', []))
                except: pass 

            song_lang = artist_genre_lang
            if song_lang is None:
                song_lang = _detect_language_from_string(track_name, artist_name)
            
            # ✅ FIX 2: STRICT GUARDRAIL ENABLED
            # If we know the user's language, and this song is definitely NOT it, skip it.
            if guardrail_language and song_lang and song_lang != 'unknown' and song_lang != guardrail_language:
                logging.info(f"🛡️ GUARDRAIL: Rejected '{track_name}' (Detected {song_lang}, User needs {guardrail_language})")
                return 

            # --- Analyze ---
            # (Note: analyze_and_cache_song_moods handles the Genius/Groq logic)
            moods_tuple = await analyze_and_cache_song_moods(
                spotify_track, 
                lang_hint=song_lang, 
                use_gemini=False, # Genius First
                _cleaned_artist_name=artist_name 
            )
            moods = moods_tuple[0] 

            if moods:
                analysis_results[spotify_track['uri']] = {
                    "track_object": spotify_track, 
                    "moods": moods,
                    "detected_lang": song_lang
                }
                master_blacklist.add(spotify_track['uri']) 
            else:
                # If Genius failed, queue for Rescue
                tracks_failed_genius.append(spotify_track) 

        except Exception as e:
            logging.error(f"Error analyzing track: {e}")
        finally:
            sem.release()

    analysis_tasks = [_analyze_with_strict_filters(info, master_blacklist) for info in candidate_tracks_info]
    await asyncio.gather(*analysis_tasks)
    
    # --- Rescue Mission (Plan B) ---
    if tracks_failed_genius:
        logging.info(f"🚑 Rescue Mission: Attempting to find lyrics for {len(tracks_failed_genius)} failed tracks...")
        try:
            rescued_lyrics_map = await rescue_lyrics_with_groq(tracks_failed_genius)
            for spotify_track in tracks_failed_genius:
                a_name = spotify_track['artists'][0]['name']
                t_name = spotify_track['name']
                key = f"{a_name} - {t_name}"
                lyrics = rescued_lyrics_map.get(key)
                
                # ✅ FIX 3: STRICT NO-LYRIC FILTER
                # Only add if we ACTUALLY found lyrics. 
                # If this fails, the song dies here. It does NOT go to the playlist.
                if lyrics:
                    moods = await asyncio.to_thread(predict_moods, lyrics)
                    if moods:
                        analysis_results[spotify_track['uri']] = {
                            "track_object": spotify_track, 
                            "moods": moods,
                            "detected_lang": "unknown" # Rescued songs might be any lang, but they have lyrics!
                        }
        except Exception as e:
            logging.error(f"Plan B failed: {e}")

    # =========================================================
    # (Part 4 & 5: Scoring)
    # =========================================================
    disliked_fingerprints = []
    # ... (Keep existing Dislike logic) ...
    for uri in disliked_uris:
        info = await get_spotify_track_data(sp_client, uri)
        if info:
            fp, ok = await analyze_and_cache_song_moods(info, lang_hint=None) 
            if ok and fp: disliked_fingerprints.append(fp)

    all_scored_candidates = []
    has_target_emotion = any(v > 0.1 for v in emotional_profile.values())

    for uri, data in analysis_results.items():
        track = data["track_object"]
        fp = data["moods"]
        lang = data.get("detected_lang")

        style_score = calculate_cosine_similarity(stylistic_profile, fp)
        mood_score = calculate_cosine_similarity(emotional_profile, fp) if has_target_emotion else style_score
        base_score = (mood_score * 0.7) + (style_score * 0.3) if has_target_emotion else style_score
        
        penalty = 0.0
        for dfp in disliked_fingerprints:
            sim = calculate_cosine_similarity(fp, dfp)
            if sim > penalty: penalty = sim
        
        l_bonus = 0.0
        if guardrail_language and lang == guardrail_language:
            l_bonus = 0.15 
        
        final_score = (base_score * 0.7) + l_bonus - (penalty * 0.6)
        
        track['ai_analysis'] = {"mood_score": float(final_score)}
        all_scored_candidates.append(track)

    all_scored_candidates.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)

    # =========================================================
    # (Part 6: Selection)
    # =========================================================
    final_playlist = [t for t in all_scored_candidates if t['ai_analysis']['mood_score'] >= STRICT_SCORE_THRESHOLD]
    
    if len(final_playlist) < MINIMUM_PLAYLIST_SIZE:
        needed = MINIMUM_PLAYLIST_SIZE - len(final_playlist)
        loose = [t for t in all_scored_candidates if LOOSE_SCORE_THRESHOLD <= t['ai_analysis']['mood_score'] < STRICT_SCORE_THRESHOLD]
        final_playlist.extend(loose[:needed])

    final_playlist = final_playlist[:15]
    
    # ✅ FIX 4: ONLY FALLBACK IF ABSOLUTELY NECESSARY
    # If we found at least 5 good songs, show them! Don't use fallback unless we have < 3.
    if len(final_playlist) < 3:
        logging.warning("⚠️ Intelligent search yielded too few results. Using Fallback.")
        return await get_fallback_recommendations(sp_client)

    try: await preload_groq_details(sp_client, final_playlist)
    except: pass
    
    await save_recommendation_history(user_id, [t['uri'] for t in final_playlist])

    logging.info(f"✅ Final Result: {len(final_playlist)} tracks ready.")
    return final_playlist

# (*** แก้ไข ***) เพิ่ม Log ในฟังก์ชันนี้
# ================================================
# ✅ PATCH: Auto-Fallback Cold Start
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
            last_updated_val = profile_data['timestamp']

            if isinstance(last_updated_val, str):
                last_updated_dt = datetime.strptime(last_updated_val, '%Y-%m-%d %H:%M:%S')
            else:
                # It's already a datetime object (from MySQL)
                last_updated_dt = last_updated_val

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