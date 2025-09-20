# update_model.py (Metadata & Lyrics ONLY Version - Faster & Resilient)
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import pandas as pd
import os
import asyncio
from tqdm import tqdm
import string

from config import Config
from genius_api import get_lyrics
from custom_model import predict_moods

# --- การตั้งค่า ---
ARCHIVE_DIR = "archive"
ARTIFACTS_DIR = os.path.join(ARCHIVE_DIR, "ml_artifacts")
RAW_DATASET_PATH = os.path.join(ARCHIVE_DIR, "spotify_tracks_raw.csv")
FINAL_DATASET_PATH = os.path.join(ARTIFACTS_DIR, "final_dataset.csv") # <-- เปลี่ยนชื่อไฟล์ให้ชัดเจน
BATCH_SIZE = 100 # <-- เพิ่ม Batch Size ได้ เพราะทำงานเร็วขึ้น

async def update_dataset():
    print("--- 🚀 Starting Metadata & Lyrics Dataset Creation ---")
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)

    # 1. เชื่อมต่อ Spotify และโหลดข้อมูลเก่า
    auth_manager = SpotifyClientCredentials(client_id=Config.SPOTIPY_CLIENT_ID, client_secret=Config.SPOTIPY_CLIENT_SECRET)
    sp_client = spotipy.Spotify(auth_manager=auth_manager)
    
    if os.path.exists(RAW_DATASET_PATH):
        df_existing = pd.read_csv(RAW_DATASET_PATH)
        existing_ids = set(df_existing['id'])
    else:
        df_existing = pd.DataFrame()
        existing_ids = set()
    print(f"Loaded {len(existing_ids)} existing tracks.")

    # 2. ค้นหาเพลงใหม่ (เหมือนเดิม)
    genre_queries = ["Thai Pop", "T-Pop", "Thai Indie", "Pop", "Rock", "Hip-Hop", "R&B", "J-Pop", "J-Rock", "K-Pop", "Anime", "Sad Songs", "Happy Hits"]
    alphabet_queries = list(string.ascii_lowercase)
    all_search_queries = genre_queries + alphabet_queries
    
    new_tracks = {}
    for query in tqdm(all_search_queries, desc="Searching Playlists"):
        try:
            results = sp_client.search(q=query, type='playlist', limit=10)
            if not results or not results['playlists']['items']: continue
            for playlist in results['playlists']['items']:
                if not playlist: continue
                try:
                    tracks = sp_client.playlist_items(playlist['id'], limit=50)
                    for item in tracks['items']:
                        track = item.get('track')
                        if track and track.get('id') and track.get('id') not in existing_ids:
                            new_tracks[track['id']] = track
                except Exception: continue
        except Exception: continue

    if not new_tracks:
        print("--- No new tracks found. Exiting. ---")
        return
    print(f"Found {len(new_tracks)} new tracks.")

    # 3. สกัด Feature (เฉพาะ Metadata และ Lyrics) และบันทึกแบบ Batch
    batch_rows = []
    track_items = list(new_tracks.items())
    
    for track_id, track_data in tqdm(track_items, desc="Extracting Features"):
        row = {'id': track_id, 'name': track_data['name'], 
               'popularity': track_data['popularity'],
               'artist_name': track_data['artists'][0]['name'], 
               'artist_id': track_data['artists'][0]['id']}
        
        try:
            artist_info = sp_client.artist(track_data['artists'][0]['id'])
            row['artist_genres'] = ",".join(artist_info.get('genres', []))
        except Exception: 
            row['artist_genres'] = ""

        lyrics = await get_lyrics(row['artist_name'], row['name'])
        known_moods = ['sadness', 'joy', 'love', 'anger', 'fear', 'surprise']
        if lyrics:
            moods = predict_moods(lyrics)
            for mood in known_moods: row[f'lyric_{mood}'] = 1 if mood in moods else 0
        else:
            for mood in known_moods: row[f'lyric_{mood}'] = 0
        
        batch_rows.append(row)
        
        if len(batch_rows) >= BATCH_SIZE:
            df_batch = pd.DataFrame(batch_rows)
            df_batch.to_csv(RAW_DATASET_PATH, mode='a', header=not os.path.exists(RAW_DATASET_PATH), index=False)
            batch_rows = []

    if batch_rows:
        df_batch = pd.DataFrame(batch_rows)
        df_batch.to_csv(RAW_DATASET_PATH, mode='a', header=not os.path.exists(RAW_DATASET_PATH), index=False)

    print("--- Raw data collection complete. Now processing final dataset. ---")

    # 4. สร้าง Final Dataset
    df_raw = pd.read_csv(RAW_DATASET_PATH)
    df_final = df_raw.copy()
    
    if 'artist_genres' in df_final.columns:
        df_final['artist_genres'] = df_final['artist_genres'].fillna('')
        df_final = pd.concat([df_final.drop('artist_genres', axis=1), 
                              df_final['artist_genres'].str.get_dummies(sep=',').add_prefix('genre_')], axis=1)

    df_final.to_csv(FINAL_DATASET_PATH, index=False)
    print(f"✅ Final dataset created at {FINAL_DATASET_PATH}")
    print("--- You can now run train_similarity_model.py ---")

if __name__ == "__main__":
    asyncio.run(update_dataset())