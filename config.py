# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """
    Class สำหรับเก็บค่า Configuration ทั้งหมดจาก Environment Variables
    """
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY")
    SPOTIPY_CLIENT_ID: str = os.getenv("SPOTIPY_CLIENT_ID")
    SPOTIPY_CLIENT_SECRET: str = os.getenv("SPOTIPY_CLIENT_SECRET")
    SPOTIPY_REDIRECT_URI: str = os.getenv("SPOTIPY_REDIRECT_URI")
    FRONTEND_APP_URL: str = os.getenv("FRONTEND_APP_URL")
    GENIUS_API_KEY: str = os.getenv("GENIUS_API_KEY") # เพิ่ม Genius API Key

    @classmethod
    def validate(cls):
        """ตรวจสอบว่า Environment Variables ที่จำเป็นถูกตั้งค่าหรือไม่"""
        if not cls.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        if not cls.SPOTIPY_CLIENT_ID or not cls.SPOTIPY_CLIENT_SECRET or not cls.SPOTIPY_REDIRECT_URI:
            raise ValueError("Spotify API credentials (SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI) not set.")
        if not cls.FRONTEND_APP_URL:
            raise ValueError("FRONTEND_APP_URL environment variable not set. Please set it to the full URL of your web_app_ui.html file.")
        if not cls.GENIUS_API_KEY: # เพิ่มการตรวจสอบ Genius API Key
            raise ValueError("GENIUS_API_KEY environment variable not set.")

# ตรวจสอบ Config เมื่อเริ่มต้นแอป
Config.validate()
