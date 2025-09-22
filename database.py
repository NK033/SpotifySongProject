# database.py
import sqlite3
import asyncio
import os
import json

DATABASE_FILE = "song_analyses.db"

def get_db_connection():
    """
    สร้างและคืนค่าการเชื่อมต่อฐานข้อมูล SQLite
    """
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

async def init_db():
    """
    เริ่มต้นฐานข้อมูล: สร้างตารางที่จำเป็นทั้งหมดหากยังไม่มี
    """
    def setup_tables():
        # การทำงานทั้งหมด (เปิด, สั่งงาน, ปิด) เกิดขึ้นในฟังก์ชันนี้
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # 1. ตารางสำหรับเก็บผลวิเคราะห์เพลง (Song Analyses)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS song_analyses (
                    spotify_uri TEXT PRIMARY KEY,
                    title TEXT,
                    artist TEXT,
                    album TEXT,
                    analysis_json TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 2. ตารางสำหรับ Cache แผนของ AI (AI Plans)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_plans (
                    genre TEXT PRIMARY KEY,
                    artists_json TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 3. ตารางสำหรับเก็บแนวเพลง (Self-Learning)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS genres (
                    name TEXT PRIMARY KEY
                )
            """)
            # 4. ตารางสำหรับเก็บศิลปินและเชื่อมกับแนวเพลง (Self-Learning)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS artists (
                    name TEXT PRIMARY KEY,
                    genre TEXT,
                    FOREIGN KEY (genre) REFERENCES genres (name)
                )
            """)
            # 5. ตารางสำหรับเก็บชื่อพ้องของแนวเพลง
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS genre_aliases (
                    alias TEXT PRIMARY KEY,
                    canonical_name TEXT,
                    FOREIGN KEY (canonical_name) REFERENCES genres (name)
                )
            """)
            # 6. ตารางสำหรับเก็บโปรไฟล์อารมณ์ของผู้ใช้
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_mood_profiles (
                    user_id TEXT PRIMARY KEY,
                    profile_json TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 7. (ใหม่) ตารางสำหรับเก็บประวัติเพลงที่เคยแนะนำ
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS recommendation_history (
                    user_id TEXT NOT NULL,
                    track_uri TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, track_uri)
                )
            """)
             # 8. (ใหม่) ตารางสำหรับเก็บ Feedback ของผู้ใช้
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_feedback (
                    user_id TEXT NOT NULL,
                    track_uri TEXT NOT NULL,
                    feedback TEXT NOT NULL, -- 'like' or 'dislike'
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, track_uri)
                )
            """)
             # 9. (ใหม่) ตารางสำหรับเก็บ Feedback ของผู้ใช้
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_feedback (
                    user_id TEXT NOT NULL,
                    track_uri TEXT NOT NULL,
                    feedback TEXT NOT NULL, -- 'like' or 'dislike'
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, track_uri)
                )
            """)

            # --- 10. (ใหม่) ตารางสำหรับเก็บเพลย์ลิสต์ที่ Pin ไว้ ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pinned_playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    playlist_name TEXT NOT NULL,
                    songs_json TEXT NOT NULL,
                    recommendation_text TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)               
            conn.commit()
        finally:
            conn.close()
            
    await asyncio.to_thread(setup_tables)
    print(f"ฐานข้อมูล SQLite '{DATABASE_FILE}' พร้อมสำหรับระบบ Self-Learning แล้ว")

async def get_song_analysis_from_db(spotify_uri: str) -> dict | None:
    """ดึงข้อมูลการวิเคราะห์เพลงจากฐานข้อมูลด้วย spotify_uri"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            row = cursor.execute("SELECT analysis_json FROM song_analyses WHERE spotify_uri = ?", (spotify_uri,)).fetchone()
            return json.loads(row['analysis_json']) if row else None
        finally:
            conn.close()
            
    return await asyncio.to_thread(db_operation)

async def save_song_analysis_to_db(spotify_track_data: dict, analysis_data: dict):
    """บันทึกข้อมูลการวิเคราะห์เพลงลงในฐานข้อมูล"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            spotify_uri = spotify_track_data.get('uri')
            cursor.execute(
                """INSERT OR REPLACE INTO song_analyses (spotify_uri, title, artist, album, analysis_json) 
                   VALUES (?, ?, ?, ?, ?)""",
                (spotify_uri, 
                 spotify_track_data.get('name'), 
                 spotify_track_data.get('artists', [{}])[0].get('name'), 
                 spotify_track_data.get('album', {}).get('name'),
                 json.dumps(analysis_data, ensure_ascii=False))
            )
            conn.commit()
        finally:
            conn.close()

    await asyncio.to_thread(db_operation)

async def get_cached_plan(genre: str) -> list | None:
    """ดึงแผนการ (รายชื่อศิลปิน) ที่เคยบันทึกไว้จากฐานข้อมูล"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            row = cursor.execute("SELECT artists_json FROM ai_plans WHERE genre = ?", (genre,)).fetchone()
            return json.loads(row['artists_json']) if row else None
        finally:
            conn.close()
            
    return await asyncio.to_thread(db_operation)

async def cache_plan(genre: str, artist_list: list):
    """บันทึกแผนการใหม่ (รายชื่อศิลปิน) ลงฐานข้อมูล"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO ai_plans (genre, artists_json) VALUES (?, ?)",
                (genre, json.dumps(artist_list, ensure_ascii=False))
            )
            conn.commit()
        finally:
            conn.close()
            
    return await asyncio.to_thread(db_operation)

async def get_artists_by_genre(genre: str) -> list[str]:
    """ดึงรายชื่อศิลปินจากฐานข้อมูลตามแนวเพลง"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            rows = cursor.execute("SELECT name FROM artists WHERE genre = ?", (genre,)).fetchall()
            return [row['name'] for row in rows]
        finally:
            conn.close()
            
    return await asyncio.to_thread(db_operation)

async def add_new_genre_and_artists(genre: str, artist_list: list[str]):
    """บันทึกแนวเพลงและศิลปินใหม่ๆ ลงฐานข้อมูล"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO genres (name) VALUES (?)", (genre,))
            for artist in artist_list:
                cursor.execute("INSERT OR IGNORE INTO artists (name, genre) VALUES (?, ?)", (artist, genre))
            conn.commit()
        finally:
            conn.close()
            
    await asyncio.to_thread(db_operation)

async def save_user_mood_profile(user_id: str, profile_data: dict):
    """บันทึกโปรไฟล์อารมณ์ของผู้ใช้ลงฐานข้อมูล"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO user_mood_profiles (user_id, profile_json) VALUES (?, ?)",
                (user_id, json.dumps(profile_data, ensure_ascii=False))
            )
            conn.commit()
        finally:
            conn.close()
    await asyncio.to_thread(db_operation)

async def get_user_mood_profile(user_id: str) -> dict | None:
    """ดึงโปรไฟล์อารมณ์ของผู้ใช้จากฐานข้อมูล"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            row = cursor.execute("SELECT profile_json FROM user_mood_profiles WHERE user_id = ?", (user_id,)).fetchone()
            return json.loads(row['profile_json']) if row else None
        finally:
            conn.close()
    return await asyncio.to_thread(db_operation)

async def save_recommendation_history(user_id: str, track_uris: list[str]):
    """บันทึกประวัติเพลงที่แนะนำให้ผู้ใช้"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # เตรียมข้อมูลเป็น list of tuples
            data_to_insert = [(user_id, uri) for uri in track_uris]
            # ใช้ INSERT OR IGNORE เพื่อป้องกัน error หากพยายามบันทึกเพลงซ้ำ
            cursor.executemany(
                "INSERT OR IGNORE INTO recommendation_history (user_id, track_uri) VALUES (?, ?)",
                data_to_insert
            )
            conn.commit()
        finally:
            conn.close()
    await asyncio.to_thread(db_operation)

async def get_recommendation_history(user_id: str) -> set[str]:
    """ดึงประวัติเพลงที่เคยแนะนำทั้งหมดของผู้ใช้ในรูปแบบ set เพื่อความรวดเร็ว"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            rows = cursor.execute("SELECT track_uri FROM recommendation_history WHERE user_id = ?", (user_id,)).fetchall()
            # คืนค่าเป็น set ของ track_uri
            return {row['track_uri'] for row in rows}
        finally:
            conn.close()
    return await asyncio.to_thread(db_operation)

async def save_user_feedback(user_id: str, track_uri: str, feedback: str):
    """บันทึก Feedback (like/dislike) ของผู้ใช้ลงฐานข้อมูล"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            # ใช้ INSERT OR REPLACE เพื่อให้ Feedback ใหม่ทับของเก่าเสมอ
            # เช่น หากเคย dislike แล้วมากด like, สถานะจะเปลี่ยนเป็น like
            cursor.execute(
                "INSERT OR REPLACE INTO user_feedback (user_id, track_uri, feedback) VALUES (?, ?, ?)",
                (user_id, track_uri, feedback)
            )
            conn.commit()
        finally:
            conn.close()
    await asyncio.to_thread(db_operation)

async def get_user_feedback(user_id: str) -> dict:
    """ดึงข้อมูล Feedback ทั้งหมดของผู้ใช้ แยกเป็น 'likes' และ 'dislikes'"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            rows = cursor.execute("SELECT track_uri, feedback FROM user_feedback WHERE user_id = ?", (user_id,)).fetchall()
            feedback_data = {
                'likes': {row['track_uri'] for row in rows if row['feedback'] == 'like'},
                'dislikes': {row['track_uri'] for row in rows if row['feedback'] == 'dislike'}
            }
            return feedback_data
        finally:
            conn.close()
    return await asyncio.to_thread(db_operation)

async def get_user_mood_profile_with_timestamp(user_id: str) -> dict | None:
    """ดึงโปรไฟล์อารมณ์ของผู้ใช้จากฐานข้อมูล พร้อมกับ timestamp"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            row = cursor.execute("SELECT profile_json, timestamp FROM user_mood_profiles WHERE user_id = ?", (user_id,)).fetchone()
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
    """บันทึกเพลย์ลิสต์ที่ผู้ใช้ Pin ไว้ลงฐานข้อมูล"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO pinned_playlists (user_id, playlist_name, songs_json, recommendation_text)
                   VALUES (?, ?, ?, ?)""",
                (user_id, playlist_name, json.dumps(songs_data, ensure_ascii=False), recommendation_text)
            )
            conn.commit()
        finally:
            conn.close()
    await asyncio.to_thread(db_operation)

async def get_pinned_playlists_by_user(user_id: str) -> list:
    """ดึงข้อมูลเพลย์ลิสต์ที่ผู้ใช้เคย Pin ไว้ทั้งหมด"""
    def db_operation():
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            rows = cursor.execute(
                "SELECT id, playlist_name, songs_json, recommendation_text, timestamp FROM pinned_playlists WHERE user_id = ? ORDER BY timestamp DESC",
                (user_id,)
            ).fetchall()
            
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