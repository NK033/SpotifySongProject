import spotipy
from config import Config
from genius_api import get_lyrics
from custom_model import predict_moods
import asyncio

def normalize_genre(genre_string: str) -> str:
    """ทำให้ชื่อแนวเพลงเป็นมาตรฐานเพื่อการเปรียบเทียบ (ตัวเล็ก, ไม่มีขีด, ไม่มีเว้นวรรค)"""
    return genre_string.lower().replace("-", "").replace(" ", "")

async def batch_verify_songs(
    candidate_songs: list[dict],
    expected_genre: str,
    expected_moods: list[str],
    sp_client: spotipy.Spotify  # <-- แก้ไข argument ตรงนี้
) -> list[dict]:
    """
    ตรวจสอบรายชื่อเพลงทั้งหมดในครั้งเดียวเพื่อลด API calls
    """
    print(f"Batch verifying {len(candidate_songs)} songs for genre '{expected_genre}' and moods '{expected_moods}'...")
    
    if not candidate_songs:
        return []

    # ไม่ต้องสร้าง sp ใหม่อีกต่อไป เพราะเราใช้ sp_client ที่มีความสามารถในการต่ออายุ Token
    
    # --- Step 1: ตรวจสอบ Genre ทั้งหมดในครั้งเดียว ---
    
    unique_artist_names = list(set([song['artists'][0]['name'] for song in candidate_songs if song and song.get('artists')]))

    artist_genre_map = {}
    print(f"Fetching genre data for {len(unique_artist_names)} unique artists...")
    for artist_name in unique_artist_names:
        try:
            # ใช้ sp_client ที่รับเข้ามา
            results = await asyncio.to_thread(sp_client.search, q=f"artist:{artist_name}", type="artist", limit=1)
            if results['artists']['items']:
                artist_info = results['artists']['items'][0]
                artist_genre_map[artist_name] = artist_info.get('genres', [])
        except Exception as e:
            print(f"Could not fetch info for artist {artist_name}: {e}")

    normalized_expected_genre = normalize_genre(expected_genre)
    
    genre_verified_songs = []
    for song in candidate_songs:
        if not song or not song.get('artists'):
            continue
        artist_name = song['artists'][0]['name']
        artist_genres = artist_genre_map.get(artist_name, [])
        
        # เปรียบเทียบแนวเพลงที่ผ่านการ normalize แล้ว
        if any(normalized_expected_genre in normalize_genre(g) for g in artist_genres):
            genre_verified_songs.append(song)

    print(f"✅ Found {len(genre_verified_songs)} songs with matching genre.")
    
    if not genre_verified_songs or not expected_moods:
        return genre_verified_songs

    # --- Step 2: ตรวจสอบ Mood (เหมือนเดิม) ---
    print(f"Verifying moods for {len(genre_verified_songs)} remaining songs...")
    final_verified_songs = []
    tasks = []
    for song in genre_verified_songs:
        try:
            artist_name = song['artists'][0]['name']
            song_name = song['name']

            lyrics = await get_lyrics(artist_name, song_name)
            if not lyrics:
                # ถ้าไม่ต้องการ Mood ก็ให้ผ่านเลย
                if not expected_moods: 
                    final_verified_songs.append(song)
                continue
            
            predicted_moods = predict_moods(lyrics)
            # ตรวจสอบว่า Mood ที่ทำนายได้ ตรงกับ Mood ที่คาดหวังหรือไม่
            if any(mood.lower() in [p.lower() for p in predicted_moods] for mood in expected_moods):
                print(f"  -> '{song_name}' passed mood check: {predicted_moods}")
                final_verified_songs.append(song)
        except Exception as e:
            print(f"  -> Error verifying mood for '{song.get('name', 'Unknown Song')}': {e}")
    
    print(f"✅ Found {len(final_verified_songs)} songs with matching genre and mood.")
    return final_verified_songs