# recommender.py (Corrected Final Version)
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
    
    # This now calls the new, more effective "Lyric Finder" function
    rescued_lyrics_dict = await rescue_lyrics_with_gemini(failed_tracks)
    
    # This loop is now updated to handle the new output
    for track in failed_tracks:
        # Construct the key using the track name and artist name from the track object
        artist_name = track.get('artists', [{}])[0].get('name', 'N/A')
        track_name = track.get('name', 'N/A')
        key = f"{artist_name} - {track_name}" # Correct key format
        
        if key in rescued_lyrics_dict and rescued_lyrics_dict[key]:
            lyrics_found[track['uri']] = rescued_lyrics_dict[key]

    logging.info(f"Total lyrical content gathered for {len(lyrics_found)} tracks after rescue mission.")
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

async def analyze_and_cache_song_moods(spotify_track: dict) -> tuple[dict | None, bool]:
    """
    (V2 - With Rescue) If the primary API fails to find lyrics, this function will now
    call the Gemini rescue mission for a second attempt.
    """
    if not spotify_track or 'uri' not in spotify_track:
        return None, False

    # 1. Check the database cache first (most efficient)
    cached_analysis = await get_song_analysis_from_db(spotify_track['uri'])
    if cached_analysis and 'predicted_moods' in cached_analysis:
        return cached_analysis['predicted_moods'], True

    # 2. Try the primary lyrics API (Genius)
    artist_name = spotify_track.get('artists', [{}])[0].get('name', 'N/A')
    track_name = spotify_track.get('name', 'N/A')
    lyrics = await get_lyrics(artist_name, track_name)
    
    # 3. ⭐ NEW: If the primary API fails, activate the Gemini rescue mission
    if not lyrics or len(lyrics) < 50:
        logging.warning(f"Primary lyrics search failed for '{track_name}'. Activating Gemini Rescue.")
        
        # The rescue function expects a list, so we pass the single track in a list
        rescued_data = await rescue_lyrics_with_gemini([spotify_track])
        
        # Check if the rescue was successful
        key = f"{artist_name} - {track_name}" # Use the same key format
        if key in rescued_data and rescued_data[key]:
            lyrics = rescued_data[key]
        else:
            lyrics = None # Ensure lyrics is None if rescue also fails

    # 4. If we have lyrics (from either source), analyze and save them
    if lyrics and len(lyrics) > 50:
        moods = predict_moods(lyrics)
        await save_song_analysis_to_db(spotify_track, {"predicted_moods": moods})
        return moods, True
    
    # 5. If all attempts fail, return unsuccessful
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

async def get_intelligent_recommendations(sp_client: spotipy.Spotify, user_id: str, user_mood_profile: dict | None) -> list[dict]:
    """
    (Hybrid V12: The Accelerator & Finisher)
    Uses a multi-layered, parallelized system to generate, score, and finalize a high-quality playlist.
    """
    MINIMUM_PLAYLIST_SIZE = 10
    logging.info("--- Initializing Hybrid V12: The Accelerator & Finisher ---")

    # --- Part 1: Prepare Blacklist & User Taste Profile ---
    top_tracks = await get_user_top_tracks(sp_client, limit=10)
    if not top_tracks:
        logging.warning("No top tracks found for user. Using Spotify's fallback recommendations directly.")
        return await get_fallback_recommendations(sp_client)

    history_uris = await get_recommendation_history(user_id)
    user_seed_tracks = await get_seed_tracks(sp_client)
    existing_uris = {t['uri'] for t in user_seed_tracks}
    feedback_data = await get_user_feedback(user_id)
    disliked_uris = feedback_data.get('dislikes', set())
    blacklist_uris = existing_uris.union(history_uris).union(disliked_uris)

    # --- Part 2: The Candidate Generation Cascade ---
    candidate_tracks_info = []
    MIN_CANDIDATES = 20

    logging.info("Cascade Strategy 1: Attempting Gemini Seed Expansion...")
    gemini_candidates = await get_gemini_seed_expansion(top_tracks)
    if gemini_candidates:
        candidate_tracks_info.extend(gemini_candidates)

    if len(candidate_tracks_info) < MIN_CANDIDATES:
        logging.info("Cascade Strategy 2: Attempting Last.fm similar tracks...")
        try:
            lastfm_similar = await get_similar_tracks(top_tracks[0]['artists'][0]['name'], top_tracks[0]['name'], limit=20)
            if lastfm_similar:
                candidate_tracks_info.extend(lastfm_similar)
        except Exception as e:
            logging.error(f"Last.fm similar tracks failed: {e}")

    if len(candidate_tracks_info) < MIN_CANDIDATES:
        logging.info("Cascade Strategy 3: Attempting Last.fm artist top tracks...")
        try:
            top_artist_name = top_tracks[0]['artists'][0]['name']
            lastfm_artist_top = await get_artist_top_tracks(top_artist_name, limit=10)
            if lastfm_artist_top:
                candidate_tracks_info.extend(lastfm_artist_top)
        except Exception as e:
            logging.error(f"Last.fm artist top tracks failed: {e}")

    if not candidate_tracks_info:
        logging.error("All candidate generation plans failed. Using Spotify's direct fallback.")
        return await get_fallback_recommendations(sp_client)
    
    logging.info(f"Cascade generated a total of {len(candidate_tracks_info)} candidates.")

    # --- Part 3: Parallel Lyric Analysis & Scoring Pre-computation ---
    analysis_results = {}
    async def _analyze_single_track(track_info):
        query = f"track:{track_info.get('title')} artist:{track_info.get('artist')}"
        spotify_results = await search_spotify_songs(sp_client, query, limit=1)
        if not spotify_results: return
        spotify_track = spotify_results[0]
        
        # --- THIS IS THE FIX ---
        # It now calls the robust function that includes the Gemini rescue logic
        moods, success = await analyze_and_cache_song_moods(spotify_track) 
        
        if success and moods:
            analysis_results[spotify_track['uri']] = {"track_object": spotify_track, "moods": moods}

    analysis_tasks = [_analyze_single_track(info) for info in candidate_tracks_info]
    await asyncio.gather(*analysis_tasks)
    logging.info(f"Completed parallel analysis. Found lyrics for {len(analysis_results)} tracks.")

    # --- Part 4: Scoring (Fast-pass) ---
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

    playlist_with_scores = []
    for uri, result in analysis_results.items():
        spotify_track = result["track_object"]
        song_fingerprint = result["moods"]
        if spotify_track['uri'] in blacklist_uris: continue

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
        playlist_with_scores.append(spotify_track)

    playlist_with_scores.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)

    # --- Part 5: Emergency Filler Step ---
    if len(playlist_with_scores) < MINIMUM_PLAYLIST_SIZE:
        logging.warning(f"Playlist is too short ({len(playlist_with_scores)}). Activating emergency filler...")
        existing_tracks_for_prompt = playlist_with_scores[:9]
        filler_candidates = await get_filler_tracks_with_lyrics(existing_tracks_for_prompt)
        
        if filler_candidates:
            filler_with_scores = []
            for candidate in filler_candidates:
                query = f"track:{candidate['track']} artist:{candidate['artist']}"
                spotify_results = await search_spotify_songs(sp_client, query, limit=1)
                if not spotify_results or spotify_results[0]['uri'] in blacklist_uris: continue
                
                spotify_track = spotify_results[0]
                lyrics_summary = candidate.get("lyrics_summary")
                if lyrics_summary and user_mood_profile:
                    song_fingerprint = predict_moods(lyrics_summary)
                    mood_score = calculate_cosine_similarity(user_mood_profile, song_fingerprint)
                    spotify_track['ai_analysis'] = {"mood_score": float(mood_score)}
                    filler_with_scores.append(spotify_track)

            filler_with_scores.sort(key=lambda x: x['ai_analysis']['mood_score'], reverse=True)
            needed = MINIMUM_PLAYLIST_SIZE - len(playlist_with_scores)
            playlist_with_scores.extend(filler_with_scores[:needed])
            logging.info(f"Added {len(filler_with_scores[:needed])} filler tracks.")

    # --- Part 6: Finalizing the Playlist ---
    final_playlist = playlist_with_scores[:15]
    if final_playlist:
        await save_recommendation_history(user_id, [t['uri'] for t in final_playlist])
    
    logging.info("--- Final Playlist (Top 5) ---")
    for track in final_playlist[:5]:
        logging.info(f"  - '{track['name']}' Score: {track['ai_analysis']['mood_score']:.4f}")
        
    return final_playlist

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

async def update_user_profile_background(token_info: dict, user_id: str):
    """
    (V3 - Safe & Correct) Creates its own isolated Spotify client from token info
    to prevent coroutine and attribute errors.
    """
    logging.info(f"BACKGROUND TASK: Received request for user {user_id}...")
    try:
        # It now builds its own, safe client object for use in the background.
        bg_sp_client = create_spotify_client(token_info)

        # The rest of the function now uses this safe 'bg_sp_client'
        profile_data = await get_user_mood_profile_with_timestamp(user_id)
        if profile_data:
            last_updated_str = profile_data['timestamp']
            last_updated_dt = datetime.strptime(last_updated_str, '%Y-%m-%d %H:%M:%S')

            if datetime.now() - last_updated_dt < timedelta(hours=1):
                logging.info(f"BACKGROUND TASK: Profile for {user_id} is recent. Skipping update.")
                return

        logging.info(f"BACKGROUND TASK: Profile is old or non-existent. Starting analysis for user {user_id}...")
        # It passes the safe client to the next function
        new_profile = await build_user_mood_profile(bg_sp_client, user_id)
        if new_profile:
            await save_user_mood_profile(user_id, new_profile)
            logging.info(f"BACKGROUND TASK: Profile for {user_id} successfully updated.")

    except Exception as e:
        logging.error(f"BACKGROUND TASK: An error occurred for user {user_id}: {e}", exc_info=True)