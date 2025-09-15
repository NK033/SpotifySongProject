import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import pandas as pd
import os
import time
import asyncio
import sys

# เพิ่ม Path ของโฟลเดอร์ archive เข้าไปใน sys.path
# เพื่อให้ Python สามารถหาไฟล์ train_model และ spotify_api เจอ
sys.path.append(os.path.join(os.path.dirname(__file__), 'archive'))

# Import สิ่งที่จำเป็นจากโปรเจกต์ของเรา
from config import Config
from archive.train import train_recommendation_model # แก้ไข: ชื่อไฟล์คือ train_model.py
from spotify_api import get_audio_features_for_tracks

# --- การตั้งค่า ---
# กำหนด Path ไปยังโฟลเดอร์ archive
ARCHIVE_DIR = "archive"
DATASET_PATH = os.path.join(ARCHIVE_DIR, "dataset.csv") # แก้ไข: ชื่อไฟล์คือ tracks.csv
ARTIFACTS_DIR = os.path.join(ARCHIVE_DIR, "ml_artifacts")
DATASET_DF_PATH = os.path.join(ARTIFACTS_DIR, "processed_dataset.joblib")


async def update_dataset_and_retrain():
    """
    สคริปต์หลักสำหรับหาเพลงใหม่, อัปเดต Dataset, และเทรนโมเดลใหม่
    """
    print("--- 🤖 เริ่มกระบวนการอัปเดตโมเดลอัตโนมัติ ---")

    # --- 1. เชื่อมต่อ Spotify ด้วย Client Credentials ---
    try:
        print("กำลังเชื่อมต่อกับ Spotify...")
        auth_manager = SpotifyClientCredentials(
            client_id=Config.SPOTIPY_CLIENT_ID,
            client_secret=Config.SPOTIPY_CLIENT_SECRET
        )
        sp_client = spotipy.Spotify(auth_manager=auth_manager)
        print("เชื่อมต่อสำเร็จ!")
    except Exception as e:
        print(f"!!! Error: ไม่สามารถเชื่อมต่อ Spotify ได้: {e}")
        return

    # --- 2. โหลด Dataset ที่มีอยู่ ---
    print("กำลังโหลด Dataset ที่มีอยู่...")
    if os.path.exists(DATASET_PATH):
        df_existing = pd.read_csv(DATASET_PATH)
        existing_ids = set(df_existing['track_id'])
        print(f"พบเพลงใน Dataset เดิม {len(existing_ids)} เพลง")
    else:
        print(f"!!! Warning: ไม่พบไฟล์ Dataset เดิม จะทำการสร้างใหม่")
        df_existing = pd.DataFrame()
        existing_ids = set()

    # --- 3. หาเพลงใหม่จาก Category 'toplists' (วิธีที่เสถียรกว่า) ---
    print("กำลังค้นหาเพลงใหม่จากหมวดหมู่ 'toplists'...")
    new_tracks_to_process = []
    try:
        # ดึงเพลย์ลิสต์จากหมวดหมู่ 'toplists' ซึ่งมีความน่าเชื่อถือสูง
        category_playlists = sp_client.category_playlists(category_id='toplists', country='US', limit=5)
        for item in category_playlists['playlists']['items']:
            if not item: continue
            playlist_id = item['id']
            tracks = sp_client.playlist_items(playlist_id, limit=20)
            for track_item in tracks['items']:
                track = track_item.get('track')
                if track and track.get('id') and track['id'] not in existing_ids:
                    new_tracks_to_process.append(track)
                    existing_ids.add(track['id'])
        print(f"พบเพลงใหม่ (เมล็ดพันธุ์) ที่ยังไม่มีใน Dataset จำนวน {len(new_tracks_to_process)} เพลง")
    except Exception as e:
        print(f"!!! Error: ไม่สามารถดึงเพลงจาก Category Playlists ได้: {e}")
        if not new_tracks_to_process:
            print("--- ไม่พบเพลงใหมที่จะอัปเดต สิ้นสุดการทำงาน ---")
            return
            
    # --- 4. เก็บข้อมูล Audio Features และจัดรูปแบบ ---
    if not new_tracks_to_process:
        print("--- ไม่มีเพลงใหม่ที่จะประมวลผล สิ้นสุดการทำงาน ---")
        return
        
    print("กำลังดึงข้อมูล Audio Features ของเพลงใหม่...")
    new_track_ids = [track['id'] for track in new_tracks_to_process]
    
    audio_features_list = await get_audio_features_for_tracks(sp_client, new_track_ids)

    new_rows = []
    features_map = {f['id']: f for f in audio_features_list if f}
    
    for track in new_tracks_to_process:
        features = features_map.get(track['id'])
        if not features: continue
        
        try:
            artist_info = sp_client.artist(track['artists'][0]['uri'])
            genre = artist_info['genres'][0] if artist_info['genres'] else 'unknown'
        except:
            genre = 'unknown'

        new_rows.append({
            'track_id': track['id'],
            'artists': ', '.join([artist['name'] for artist in track['artists']]),
            'album_name': track['album']['name'],
            'track_name': track['name'],
            'popularity': track['popularity'],
            'duration_ms': track['duration_ms'],
            'explicit': track['explicit'],
            'danceability': features.get('danceability'),
            'energy': features.get('energy'),
            'key': features.get('key'),
            'loudness': features.get('loudness'),
            'mode': features.get('mode'),
            'speechiness': features.get('speechiness'),
            'acousticness': features.get('acousticness'),
            'instrumentalness': features.get('instrumentalness'),
            'liveness': features.get('liveness'),
            'valence': features.get('valence'),
            'tempo': features.get('tempo'),
            'time_signature': features.get('time_signature'),
            'track_genre': genre
        })

    if not new_rows:
        print("--- ไม่สามารถประมวลผลเพลงใหม่ได้ สิ้นสุดการทำงาน ---")
        return

    # --- 5. อัปเดตไฟล์ CSV ---
    print(f"กำลังเพิ่มเพลงใหม่ {len(new_rows)} เพลงลงใน {DATASET_PATH}...")
    df_new = pd.DataFrame(new_rows)
    df_updated = pd.concat([df_existing, df_new], ignore_index=True)
    df_updated.to_csv(DATASET_PATH, index=False)
    print("อัปเดตไฟล์ CSV สำเร็จ!")

    # --- 6. สั่งเทรนโมเดลใหม่อีกครั้ง ---
    print("\n--- 🚀 กำลังเริ่มเทรนโมเดลใหม่ด้วย Dataset ที่อัปเดตแล้ว ---")
    train_recommendation_model()

    print("\n--- ✅ อัปเดตและเทรนโมเดลใหม่สำเร็จ! ---")


if __name__ == "__main__":
    asyncio.run(update_dataset_and_retrain())