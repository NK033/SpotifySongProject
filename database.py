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