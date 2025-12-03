import React, { useState, useEffect } from 'react';
import '../App.css'; 

const LiveAgent = () => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [isVisible, setIsVisible] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  // --- 1. เพิ่มฟังก์ชันขออนุญาตแจ้งเตือน ---
  useEffect(() => {
    if (Notification.permission !== "granted") {
      Notification.requestPermission();
    }
  }, []);

  // --- 2. ฟังก์ชันส่งแจ้งเตือน (System Notification) ---
  const sendSystemNotification = (data) => {
    // เช็คว่า User อนุญาตไหม และหน้าเว็บถูกพับอยู่หรือเปล่า (document.hidden)
    if (Notification.permission === "granted" && document.hidden) {
      new Notification(`🎵 Now Playing: ${data.name}`, {
        body: `AI: "${data.notification}"`, // ข้อความจาก AI
        icon: data.cover, // รูปปกเพลง
        silent: false // ให้มีเสียงเตือน default ของวินโดวส์
      });
    }
  };

  const getHeaders = () => {
    const accessToken = localStorage.getItem('spotify_access_token') || localStorage.getItem('access_token');
    const refreshToken = localStorage.getItem('spotify_refresh_token') || localStorage.getItem('refresh_token');
    if (!accessToken) return null;

    const headers = {
      'Authorization': `Bearer ${accessToken}`,
      'Content-Type': 'application/json'
    };

    if (refreshToken) headers['X-Refresh-Token'] = refreshToken;
    return headers;
  };

  useEffect(() => {
    const checkLiveStatus = async () => {
      const headers = getHeaders();
      if (!headers) return; 

      try {
        const response = await fetch('http://localhost:8000/api/live-status', {
          method: 'GET',
          headers: headers 
        });

        if (response.ok) {
          const data = await response.json();
          
          if (data.is_playing && data.name !== status?.name) {
            console.log("🎵 New song detected:", data.name);
            setStatus(data);
            setIsVisible(true);
            
            // --- 3. เรียกใช้ฟังก์ชันแจ้งเตือนตรงนี้ ---
            sendSystemNotification(data); 

          } else if (!data.is_playing) {
            setStatus(null);
            setIsVisible(false);
          }
        }
      } catch (error) {
        console.error("Agent checking failed:", error);
      }
    };

    checkLiveStatus();
    const intervalId = setInterval(checkLiveStatus, 30000); 
    return () => clearInterval(intervalId);
  }, [status]);

  // ... (ส่วน useEffect Auto-Close และ handleArrangePlaylist เหมือนเดิม) ...
  // ... (ส่วน useEffect Auto-Close เหมือนเดิม) ...
  useEffect(() => {
    if (isVisible && !loading && !isHovered) {
      const timer = setTimeout(() => {
        setIsVisible(false);
      }, 15000);
      return () => clearTimeout(timer);
    }
  }, [isVisible, loading, isHovered, status]);

  const handleArrangePlaylist = async () => {
    if (!status) return;
    setLoading(true);
    
    const prompt = `ช่วยจัด Playlist ต่อเนื่องจากเพลง "${status.name}" ของ "${status.artist}" ให้หน่อย เอาแนว "${status.mood_data ? Object.keys(status.mood_data)[0] : 'คล้ายๆ กัน'}"`;
    
    try {
        const headers = getHeaders(); 
        await fetch('http://localhost:8000/chat', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({ message: prompt })
        });
        alert("AI กำลังจัด Playlist ให้ครับ! (ดูผลลัพธ์ในหน้า Chat)");
        setLoading(false);
        setIsVisible(false);
    } catch (e) {
        alert("เกิดข้อผิดพลาดในการสั่งงาน AI");
        setLoading(false);
    }
  };

  if (!status || !status.is_playing || !isVisible) return null;

  return (
     // ... (ส่วน JSX แสดงผลหน้าเว็บ เหมือนเดิมทุกประการ) ...
    <div 
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        position: 'fixed', bottom: '20px', right: '20px', 
        backgroundColor: '#1e1e1e', padding: '15px', borderRadius: '12px',
        border: '1px solid #1db954', boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        maxWidth: '320px', zIndex: 9999, color: 'white', fontFamily: 'sans-serif',
        transition: 'opacity 0.5s ease-in-out, transform 0.5s ease-in-out',
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? 'translateY(0)' : 'translateY(20px)',
        cursor: 'default'
      }}
    >
      <div 
        onClick={(e) => { e.stopPropagation(); setIsVisible(false); }}
        style={{
          position: 'absolute', top: '5px', right: '10px', 
          cursor: 'pointer', color: '#b3b3b3', fontSize: '18px'
        }}
      >
        &times;
      </div>

      <div style={{display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '12px'}}>
        <img src={status.cover} alt="cover" style={{width: '60px', height: '60px', borderRadius: '8px', objectFit: 'cover'}} />
        <div style={{overflow: 'hidden'}}>
            <div style={{fontSize: '10px', textTransform: 'uppercase', color: '#1db954', letterSpacing: '1px', fontWeight: 'bold'}}>Now Listening</div>
            <div style={{fontWeight: 'bold', fontSize: '14px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>{status.name}</div>
            <div style={{fontSize: '12px', color: '#b3b3b3'}}>{status.artist}</div>
        </div>
      </div>
      
      <div style={{
          backgroundColor: '#2a2a2a', padding: '10px', borderRadius: '8px', 
          fontSize: '13px', lineHeight: '1.4', marginBottom: '12px', borderLeft: '3px solid #1db954'
      }}>
        🤖 <b>AI Agent:</b> <br/> "{status.notification}"
      </div>

      <button 
        onClick={handleArrangePlaylist}
        disabled={loading}
        style={{
          width: '100%', padding: '10px', backgroundColor: loading ? '#555' : '#1db954', 
          border: 'none', borderRadius: '30px', color: 'white', fontWeight: 'bold', 
          cursor: loading ? 'not-allowed' : 'pointer', transition: 'transform 0.1s',
          fontSize: '13px'
      }}>
        {loading ? 'Thinking...' : '✨ Create this Playlist!'}
      </button>
    </div>
  );
};

export default LiveAgent;