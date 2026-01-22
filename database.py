# database.py (Cleaned Version)
import mysql.connector
import asyncio
import json
import logging
from config import Config

# 1. Create a Global Pool Variable
db_pool = None

def get_db_connection():
    global db_pool
    
    # 2. Initialize the pool only once
    if db_pool is None:
        try:
            db_pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="spotify_pool",
                pool_size=10,  # Keep 10 connections ready
                pool_reset_session=True,
                host=Config.DB_HOST,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                database=Config.DB_NAME
            )
            print("✅ Database Connection Pool Created")
        except mysql.connector.Error as e:
            print(f"❌ Error creating pool: {e}")
            raise e

    # 3. Get a connection from the pool
    try:
        return db_pool.get_connection()
    except Exception as e:
        print(f"❌ Failed to get connection from pool: {e}")
        raise e

# Helper for dictionary cursor
def get_cursor(conn):
    return conn.cursor(dictionary=True)

async def init_db():
    def setup_tables():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            
            # 1. Song Analyses (เก็บข้อมูลเพลง, เนื้อเพลง, และผลวิเคราะห์อารมณ์)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS song_analyses (
                    spotify_uri VARCHAR(255) PRIMARY KEY,
                    title VARCHAR(255),
                    artist VARCHAR(255),
                    album VARCHAR(255),
                    image_url VARCHAR(500),      -- For Images
                    lyrics LONGTEXT,             -- Cached Lyrics
                    language VARCHAR(10),        -- Language Code
                    mood_scores JSON,            -- ✅ THE CUSTOM MODEL SCORE
                    analysis_json LONGTEXT,      -- Groq Description
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)
            
            # 2. User Mood Profiles (เก็บโปรไฟล์อารมณ์ของผู้ใช้)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_mood_profiles (
                    user_id VARCHAR(255) PRIMARY KEY,
                    profile_json LONGTEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)

            # 3. Recommendation History (เก็บประวัติการแนะนำเพื่อไม่ให้ซ้ำ)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recommendation_history (
                    user_id VARCHAR(255) NOT NULL,
                    track_uri VARCHAR(255) NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, track_uri)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)

            # 4. User Feedback (เก็บ Like/Dislike)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_feedback (
                    user_id VARCHAR(255) NOT NULL,
                    track_uri VARCHAR(255) NOT NULL,
                    feedback VARCHAR(50) NOT NULL, 
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, track_uri)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)

            # 5. Pinned Playlists (เก็บเพลย์ลิสต์ที่ปักหมุด)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pinned_playlists (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    playlist_name VARCHAR(255) NOT NULL,
                    songs_json LONGTEXT NOT NULL,
                    recommendation_text TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
            """)

            conn.commit()
            print(f"✅ MySQL Database '{Config.DB_NAME}' initialized.")
        except mysql.connector.Error as err:
            print(f"❌ DB Init Error: {err}")
        finally:
            conn.close()
    await asyncio.to_thread(setup_tables)

async def get_song_analysis_from_db(spotify_uri: str) -> dict | None:
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = get_cursor(conn)
            cursor.execute("SELECT analysis_json, mood_scores, lyrics FROM song_analyses WHERE spotify_uri = %s", (spotify_uri,))
            row = cursor.fetchone()
            if row:
                # Merge fields for the app
                data = json.loads(row['analysis_json'])
                if row['mood_scores']:
                    data['predicted_moods'] = json.loads(row['mood_scores'])
                if row['lyrics']:
                    data['lyrics'] = row['lyrics']
                return data
            return None
        finally:
            conn.close()
    return await asyncio.to_thread(db_operation)

async def save_song_analysis_to_db(spotify_track_data: dict, analysis_data: dict):
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            spotify_uri = spotify_track_data.get('uri')
            
            # Extract specific fields
            lyrics = analysis_data.get('lyrics', None)
            mood_scores = json.dumps(analysis_data.get('predicted_moods', {}), ensure_ascii=False)
            
            # Remove them from the main analysis_json to avoid redundancy
            clean_analysis = analysis_data.copy()
            clean_analysis.pop('lyrics', None)
            clean_analysis.pop('predicted_moods', None)
            
            cursor.execute(
                """REPLACE INTO song_analyses 
                   (spotify_uri, title, artist, album, lyrics, mood_scores, analysis_json) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (spotify_uri, 
                 spotify_track_data.get('name'), 
                 spotify_track_data.get('artists', [{}])[0].get('name'), 
                 spotify_track_data.get('album', {}).get('name'),
                 lyrics,
                 mood_scores,
                 json.dumps(clean_analysis, ensure_ascii=False))
            )
            conn.commit()
        finally:
            conn.close()
    await asyncio.to_thread(db_operation)

async def save_user_mood_profile(user_id: str, profile_data: dict):
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "REPLACE INTO user_mood_profiles (user_id, profile_json) VALUES (%s, %s)",
                (user_id, json.dumps(profile_data, ensure_ascii=False))
            )
            conn.commit()
        finally:
            conn.close()
    await asyncio.to_thread(db_operation)

async def get_user_mood_profile(user_id: str) -> dict | None:
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = get_cursor(conn)
            cursor.execute("SELECT profile_json FROM user_mood_profiles WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            return json.loads(row['profile_json']) if row else None
        finally:
            conn.close()
    return await asyncio.to_thread(db_operation)

async def save_recommendation_history(user_id: str, track_uris: list[str]):
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            data_to_insert = [(user_id, uri) for uri in track_uris]
            cursor.executemany(
                "INSERT IGNORE INTO recommendation_history (user_id, track_uri) VALUES (%s, %s)",
                data_to_insert
            )
            conn.commit()
        finally:
            conn.close()
    await asyncio.to_thread(db_operation)

async def get_recommendation_history(user_id: str) -> set[str]:
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = get_cursor(conn)
            cursor.execute("SELECT track_uri FROM recommendation_history WHERE user_id = %s", (user_id,))
            rows = cursor.fetchall()
            return {row['track_uri'] for row in rows}
        finally:
            conn.close()
    return await asyncio.to_thread(db_operation)

async def save_user_feedback(user_id: str, track_uri: str, feedback: str):
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "REPLACE INTO user_feedback (user_id, track_uri, feedback) VALUES (%s, %s, %s)",
                (user_id, track_uri, feedback)
            )
            conn.commit()
        finally:
            conn.close()
    await asyncio.to_thread(db_operation)

async def get_user_feedback(user_id: str) -> dict:
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = get_cursor(conn)
            cursor.execute("SELECT track_uri, feedback FROM user_feedback WHERE user_id = %s", (user_id,))
            rows = cursor.fetchall()
            feedback_data = {
                'likes': {row['track_uri'] for row in rows if row['feedback'] == 'like'},
                'dislikes': {row['track_uri'] for row in rows if row['feedback'] == 'dislike'}
            }
            return feedback_data
        finally:
            conn.close()
    return await asyncio.to_thread(db_operation)

async def get_user_mood_profile_with_timestamp(user_id: str) -> dict | None:
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = get_cursor(conn)
            cursor.execute("SELECT profile_json, timestamp FROM user_mood_profiles WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "profile": json.loads(row['profile_json']),
                "timestamp": row['timestamp']
            }
        finally:
            conn.close()
    return await asyncio.to_thread(db_operation)

async def add_pinned_playlist(user_id: str, playlist_name: str, songs_data: list, recommendation_text: str):
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO pinned_playlists (user_id, playlist_name, songs_json, recommendation_text)
                   VALUES (%s, %s, %s, %s)""",
                (user_id, playlist_name, json.dumps(songs_data, ensure_ascii=False), recommendation_text)
            )
            conn.commit()
        finally:
            conn.close()
    await asyncio.to_thread(db_operation)

async def get_pinned_playlists_by_user(user_id: str) -> list:
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                "SELECT id, playlist_name, songs_json, recommendation_text, timestamp FROM pinned_playlists WHERE user_id = %s ORDER BY timestamp DESC",
                (user_id,)
            )
            rows = cursor.fetchall()
            playlists = []
            for row in rows:
                playlists.append({
                    "pin_id": row['id'],
                    "name": row['playlist_name'],
                    "songs": json.loads(row['songs_json']),
                    "recommendationText": row['recommendation_text'],
                    "timestamp": row['timestamp']
                })
            return playlists
        finally:
            conn.close()
    return await asyncio.to_thread(db_operation)

async def delete_pinned_playlist(pin_id: int, user_id: str):
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM pinned_playlists WHERE id = %s AND user_id = %s",
                (pin_id, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    return await asyncio.to_thread(db_operation)

async def update_pinned_playlist(pin_id: int, user_id: str, new_name: str, new_songs_json: str):
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE pinned_playlists 
                   SET playlist_name = %s, songs_json = %s, timestamp = CURRENT_TIMESTAMP
                   WHERE id = %s AND user_id = %s""",
                (new_name, new_songs_json, pin_id, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    return await asyncio.to_thread(db_operation)

async def get_all_analyzed_tracks() -> list[dict]:
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = get_cursor(conn)
            # ✅ Updated to read from mood_scores column
            cursor.execute("SELECT spotify_uri, mood_scores FROM song_analyses")
            rows = cursor.fetchall()
            results = []
            for row in rows:
                if row['mood_scores']:
                    try:
                        results.append({
                            'uri': row['spotify_uri'],
                            'moods': json.loads(row['mood_scores'])
                        })
                    except: continue
            return results
        finally:
            conn.close()
    return await asyncio.to_thread(db_operation)

async def get_user_feedback_list(user_id: str) -> list:
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = get_cursor(conn)
            cursor.execute(
                "SELECT track_uri, feedback, timestamp FROM user_feedback WHERE user_id = %s ORDER BY timestamp DESC",
                (user_id,)
            )
            return cursor.fetchall()
        finally:
            conn.close()
    return await asyncio.to_thread(db_operation)

# ✅ NEW: Delete feedback (remove like/dislike)
async def delete_user_feedback(user_id: str, track_uri: str):
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM user_feedback WHERE user_id = %s AND track_uri = %s",
                (user_id, track_uri)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    return await asyncio.to_thread(db_operation)