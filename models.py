# models.py
from pydantic import BaseModel
from typing import List, Dict, Optional

class ChatRequest(BaseModel):
    """
    Model สำหรับ Request ที่เข้ามายัง /chat endpoint
    """
    message: str
    spotify_access_token: Optional[str] = None
    spotify_refresh_token: Optional[str] = None # <-- เพิ่มบรรทัดนี้
    expires_at: Optional[int] = None # <-- เพิ่มบรรทัดนี้
 

class ChatResponse(BaseModel):
    """
    Model สำหรับ Response ที่ส่งกลับจาก /chat endpoint
    """
    response: str
    songs_found: Optional[List[Dict]] = None 
    playlist_info: Optional[Dict] = None 
    new_spotify_token_info: Optional[Dict] = None # <-- เพิ่มบรรทัดนี้
    artist_list: Optional[List[str]] = None 
    song_detail: Optional[Dict] = None 
