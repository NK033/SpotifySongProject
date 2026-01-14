# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """
    Configuration loaded from Environment Variables
    """
    SPOTIPY_CLIENT_ID: str = os.getenv("SPOTIPY_CLIENT_ID")
    SPOTIPY_CLIENT_SECRET: str = os.getenv("SPOTIPY_CLIENT_SECRET")
    SPOTIPY_REDIRECT_URI: str = os.getenv("SPOTIPY_REDIRECT_URI")
    FRONTEND_APP_URL: str = os.getenv("FRONTEND_APP_URL")
    GENIUS_API_KEY: str = os.getenv("GENIUS_API_KEY")
    LASTFM_API_KEY: str = os.getenv("lastfm_api_key")
    LASTFM_API_SECRET: str = os.getenv("lastfm_api_key_secret")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY")
    
    # --- New Database Config (XAMPP/MySQL) ---
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "") # Default XAMPP password is empty
    DB_NAME: str = os.getenv("DB_NAME", "spotify_project_db")

    @classmethod
    def validate(cls):
        """Check for required environment variables."""
        if not cls.GROQ_API_KEY:
             raise ValueError("GROQ_API_KEY environment variable not set.")
        if not cls.SPOTIPY_CLIENT_ID or not cls.SPOTIPY_CLIENT_SECRET:
            raise ValueError("Spotify credentials not set.")
        # Ensure DB config is present (defaults handle local XAMPP, but good to check)
        if not cls.DB_HOST or not cls.DB_NAME:
            raise ValueError("Database configuration (DB_HOST, DB_NAME) is missing.")

Config.validate()