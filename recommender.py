# recommender.py (Corrected Final Version - V13.2 Clean Logging)
import asyncio
import spotipy
import logging
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

async def analyze_and_cache_song_moods(spotify_track: dict) -> tuple[dict | None, bool]:
    """
    (V2 - With Rescue) If the primary API fails to find lyrics, this function will now
    call the Gemini rescue mission for a second attempt.
    """
    if not spotify_track or 'uri' not in spotify_track:
        return None, False

    cached_analysis = await get_song_analysis_from_db(spotify_track['uri'])
    if cached_analysis and 'predicted_moods' in cached_analysis:
        return cached_analysis['predicted_moods'], True

    artist_name = spotify_track.get('artists', [{}])[0].get('name', 'N/A')
    track_name = spotify_track.get('name', 'N/A')
    lyrics = await get_lyrics(artist_name, track_name)
    
    if not lyrics or len(lyrics) < 50:
        logging.warning(f"Primary lyrics search failed for '{track_name}'. Activating Gemini Rescue.")
        
        rescued_data = await rescue_lyrics_with_gemini([spotify_track])
        
        key = f"{artist_name} - {track_name}"
        if key in rescued_data and rescued_data[key]:
            lyrics = rescued_data[key]
        else:
            lyrics = None

    if lyrics and len(lyrics) > 50:
        moods = predict_moods(lyrics)
        if moods:
            await save_song_analysis_to_db(spotify_track, {"predicted_moods": moods})
            return moods, True
    
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
async def get_intelligent_recommendations(sp_client: spotipy.Spotify, user_id: str, user_mood_profile: dict | None) -> list[dict]:
    """
    (Hybrid V13.2: Multi-Round Curation w/ Clean Logging)
    """
    MINIMUM_PLAYLIST_SIZE = 10
    STRICT_SCORE_THRESHOLD = 0.45 
    LOOSE_SCORE_THRESHOLD = 0.25
    
    logging.info("--- Initializing Hybrid V13.2: Multi-Round Curation ---")

    # --- Part 1: Prepare Blacklist & User Taste Profile ---
    top_tracks_list = await get_user_top_tracks(sp_client, limit=10) # (เก็บลิสต์ไว้ใช้)
    if not top_tracks_list:
        logging.warning("No top tracks found for user. Using Spotify's fallback recommendations directly.")
        return await get_fallback_recommendations(sp_client)

    # (*** แก้ไข ***) ย้าย get_seed_tracks มาเรียกตรงนี้เพื่อ log
    # (ฟังก์ชัน get_seed_tracks ถูกแก้ไขให้ log ภายในตัวมันเองแล้ว)
    user_seed_tracks = await get_seed_tracks(sp_client)
    
    history_uris = await get_recommendation_history(user_id)
    existing_uris = {t['uri'] for t in user_seed_tracks}
    feedback_data = await get_user_feedback(user_id)
    disliked_uris = feedback_data.get('dislikes', set())
    blacklist_uris = existing_uris.union(history_uris).union(disliked_uris)

    # --- Part 2: The Candidate Generation Cascade (Target: 30+) ---
    candidate_tracks_info = []
    MIN_CANDIDATES = 30

    logging.info("Cascade Strategy 1: Attempting Gemini Seed Expansion...")
    gemini_candidates = await get_gemini_seed_expansion(top_tracks_list)
    if gemini_candidates:
        candidate_tracks_info.extend(gemini_candidates)

    if len(candidate_tracks_info) < MIN_CANDIDATES:
        logging.info("Cascade Strategy 2: Attempting Last.fm similar tracks...")
        try:
            lastfm_similar = await get_similar_tracks(top_tracks_list[0]['artists'][0]['name'], top_tracks_list[0]['name'], limit=30)
            if lastfm_similar:
                candidate_tracks_info.extend(lastfm_similar)
        except Exception as e:
            logging.error(f"Last.fm similar tracks failed: {e}")

    if len(candidate_tracks_info) < MIN_CANDIDATES:
        logging.info("Cascade Strategy 3: Attempting Last.fm artist top tracks...")
        try:
            top_artist_name = top_tracks_list[0]['artists'][0]['name']
            lastfm_artist_top = await get_artist_top_tracks(top_artist_name, limit=20)
            if lastfm_artist_top:
                candidate_tracks_info.extend(lastfm_artist_top)
        except Exception as e:
            logging.error(f"Last.fm artist top tracks failed: {e}")

    if len(candidate_tracks_info) < MIN_CANDIDATES:
        logging.info("Cascade Strategy 4: Attempting Last.fm Global Top Tracks...")
        try:
            lastfm_global_top = await get_global_top_tracks(limit=30)
            if lastfm_global_top:
                candidate_tracks_info.extend(lastfm_global_top)
        except Exception as e:
            logging.error(f"Last.fm global top tracks failed: {e}")

    if not candidate_tracks_info:
        logging.error("All candidate generation plans failed. Using Spotify's direct fallback.")
        return await get_fallback_recommendations(sp_client)
    
    # Deduplication
    unique_candidates = []
    seen_candidates = set()
    for track in candidate_tracks_info:
        key = (track.get('artist', '').casefold(), track.get('title', '').casefold())
        if key not in seen_candidates and key[0] and key[1]:
            unique_candidates.append(track)
            seen_candidates.add(key)
    
    candidate_tracks_info = unique_candidates
    
    # (*** LOGGING 1 ***) แสดงรายชื่อผู้สมัครทั้งหมด
    logging.info(f"--- 🧬 Candidate Tracks ({len(candidate_tracks_info)}) ---")
    for i, track in enumerate(candidate_tracks_info):
        logging.info(f"  {i+1}. '{track.get('title')}' by {track.get('artist')}")
    # (*** จบ LOGGING 1 ***)

    # --- Part 3: Parallel Lyric Analysis (Pre-computation) ---
    analysis_results = {}
    sem = asyncio.Semaphore(8)

    async def _analyze_single_track(track_info):
        await sem.acquire()
        try:
            query = f"track:{track_info.get('title')} artist:{track_info.get('artist')}"
            spotify_results = await search_spotify_songs(sp_client, query, limit=1)
            if not spotify_results: return
            spotify_track = spotify_results[0]
            
            if spotify_track['uri'] in blacklist_uris:
                return

            moods, success = await analyze_and_cache_song_moods(spotify_track) 
            
            if success and moods:
                analysis_results[spotify_track['uri']] = {"track_object": spotify_track, "moods": moods}
        except Exception as e:
            logging.error(f"Error analyzing track '{track_info.get('title')}': {e}", exc_info=False) # (ลดความรกของ log)
        finally:
            sem.release()

    analysis_tasks = [_analyze_single_track(info) for info in candidate_tracks_info]
    await asyncio.gather(*analysis_tasks)
    logging.info(f"Completed parallel analysis. Found lyrics for {len(analysis_results)} tracks.")

    # --- Part 4: Scoring Helpers (Dislikes & Year Bonus) ---
    disliked_fingerprints = []
    for uri in disliked_uris:
        track_info = await get_spotify_track_data(sp_client, uri)
        if track_info:
            song_fingerprint, success = await analyze_and_cache_song_moods(track_info)
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

    # (*** แก้ไข ***) ย้ายการคำนวณคะแนนทั้งหมดมาไว้ที่ Part 4.5
    # --- Part 4.5: Scoring All Candidates ---
    logging.info("--- 📈 Scoring All Analyzed Candidates ---")
    all_scored_candidates = []
    
    for uri, result in analysis_results.items():
        spotify_track = result["track_object"]
        song_fingerprint = result["moods"]

        mood_score = calculate_cosine_similarity(user_mood_profile, song_fingerprint)
        
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

        final_score = (mood_score * 0.8) + year_bonus - (dislike_penalty * 0.6)
        spotify_track['ai_analysis'] = {"mood_score": float(final_score)}
        all_scored_candidates.append(spotify_track)

    # เรียงลำดับทั้งหมด
    all_scored_candidates.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)

    # (*** LOGGING 2 ***) แสดงคะแนนของผู้สมัครทั้งหมด
    logging.info(f"--- 📊 Candidate Scores ({len(all_scored_candidates)}) ---")
    for i, track in enumerate(all_scored_candidates):
        score = track['ai_analysis']['mood_score']
        logging.info(f"  {i+1}. (Score: {score:.4f}) '{track['name']}' by {track['artists'][0]['name']}")
    # (*** จบ LOGGING 2 ***)

    # --- Part 5: Round 1 (Strict Curation) ---
    logging.info(f"--- Starting Round 1: Strict Filtering (Threshold: {STRICT_SCORE_THRESHOLD}) ---")
    
    # (*** แก้ไข ***) เปลี่ยนจากการคำนวณ เป็นการกรอง (filter) จากลิสต์ที่คำนวณไว้แล้ว
    round_1_playlist = [
        track for track in all_scored_candidates 
        if track['ai_analysis']['mood_score'] >= STRICT_SCORE_THRESHOLD
    ]
        
    blacklist_uris.update([t['uri'] for t in round_1_playlist])
    logging.info(f"Round 1 completed. {len(round_1_playlist)} songs passed strict filtering.")

    # --- Part 6: Round 2 (Intelligent Filling) ---
    final_playlist = round_1_playlist
    
    if len(final_playlist) < MINIMUM_PLAYLIST_SIZE:
        logging.warning(f"Playlist too short. Starting Round 2: Intelligent Filler (Threshold: {LOOSE_SCORE_THRESHOLD})")
        needed = MINIMUM_PLAYLIST_SIZE - len(final_playlist)

        filler_candidates_info = []
        try:
            lastfm_similar = await get_similar_tracks(top_tracks_list[0]['artists'][0]['name'], top_tracks_list[0]['name'], limit=20)
            if lastfm_similar:
                filler_candidates_info.extend(lastfm_similar)
        except Exception as e:
            logging.error(f"Filler: Last.fm similar tracks failed: {e}")

        if len(filler_candidates_info) < needed:
            try:
                gemini_seed_tracks = final_playlist[:5] if final_playlist else top_tracks_list[:5]
                gemini_candidates = await get_filler_tracks_with_lyrics(gemini_seed_tracks)
                if gemini_candidates:
                    filler_candidates_info.extend(gemini_candidates)
            except Exception as e:
                 logging.error(f"Filler: Gemini filler failed: {e}")

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
                    if spotify_track['uri'] in blacklist_uris:
                        return

                    song_fingerprint = None
                    lyrics_summary = track_info.get("lyrics_summary")
                    if lyrics_summary:
                        song_fingerprint = predict_moods(lyrics_summary)
                    else:
                        moods, success = await analyze_and_cache_song_moods(spotify_track)
                        if success:
                            song_fingerprint = moods

                    if not song_fingerprint:
                        return
                    
                    mood_score = calculate_cosine_similarity(user_mood_profile, song_fingerprint)
                    final_score = mood_score

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

    # --- Part 7: Finalizing the Playlist ---
    final_playlist.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)
    final_playlist = final_playlist[:15]
    
    if final_playlist:
        await save_recommendation_history(user_id, [t['uri'] for t in final_playlist])
    
    # (*** LOGGING 3 ***) แสดง 10 อันดับแรกของ Playlist สุดท้าย
    logging.info(f"--- ✅ Final Curated Playlist ({len(final_playlist)} Songs) ---")
    for i, track in enumerate(final_playlist[:10]): # แสดง 10 อันดับแรก
        logging.info(f"  {i+1}. (Score: {track['ai_analysis']['mood_score']:.4f}) '{track['name']}' by {track['artists'][0]['name']}")
    # (*** จบ LOGGING 3 ***)
        
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
        logging.info("  (No recent tracks found)")

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