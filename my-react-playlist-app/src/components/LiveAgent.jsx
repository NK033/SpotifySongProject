// src/components/LiveAgent.jsx
import React, { useState, useEffect } from 'react';
import '../App.css'; 

const LiveAgent = ({ onSendMessage }) => {
  const [status, setStatus] = useState(null);
  const [isVisible, setIsVisible] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  // API URL
  const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  // ✅ FIX 1: Safe Permission Request (Checks if "Notification" exists first)
  useEffect(() => {
    if ("Notification" in window && Notification.permission !== "granted") {
      Notification.requestPermission();
    }
  }, []);

  // ✅ FIX 2: Safe Notification Sending (Prevents crash on Android)
  const sendSystemNotification = (data) => {
    if ("Notification" in window && Notification.permission === "granted" && document.hidden) {
      try {
        new Notification(`🎵 Now Playing: ${data.name}`, {
          body: `${data.notification}`,
          icon: data.cover,
          silent: false 
        });
      } catch (e) {
        console.log("Notification failed safely:", e);
      }
    }
  };

  const getHeaders = () => {
    const accessToken = localStorage.getItem('spotify_access_token');
    const refreshToken = localStorage.getItem('spotify_refresh_token');
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
        const response = await fetch(`${API_BASE_URL}/api/live-status`, {
          method: 'GET',
          headers: headers 
        });

        if (response.ok) {
          const data = await response.json();
          
          if (data.is_playing && data.name !== status?.name) {
            console.log("🎵 LiveAgent: New song detected:", data.name);
            setStatus(data);
            setIsVisible(true);
            sendSystemNotification(data); 

          } else if (!data.is_playing) {
            if (isVisible) {
                setStatus(null);
                setIsVisible(false);
                setIsExpanded(false);
            }
          }
        }
      } catch (error) {}
    };

    checkLiveStatus();
    const intervalId = setInterval(checkLiveStatus, 5000); 
    return () => clearInterval(intervalId);
  }, [status, isVisible]);

  useEffect(() => {
    if (isVisible && !isHovered && !isExpanded) {
      const timer = setTimeout(() => {
        setIsVisible(false);
      }, 15000);
      return () => clearTimeout(timer);
    }
  }, [isVisible, isHovered, status, isExpanded]);

  const handleArrangePlaylist = async (e) => {
    e.stopPropagation(); 
    if (!status) return;
    const prompt = `ช่วยจัด Playlist ต่อเนื่องจากเพลง "${status.name}" ของ "${status.artist}" ให้หน่อย`;
    try {
        onSendMessage(prompt, 'get_recommendations');
        setIsVisible(false);
    } catch (e) {
        console.error("❌ LiveAgent Error:", e);
    }
  };

  if (!status || !status.is_playing) return null;

  return (
    <>
      {/* ✅ CSS สำหรับ Sound Wave Animation */}
      <style>{`
        @keyframes sound-wave {
          0% { height: 3px; }
          50% { height: 10px; }
          100% { height: 3px; }
        }
        .bar {
          width: 3px;
          background-color: #1db954;
          border-radius: 2px;
          animation: sound-wave 0.8s infinite ease-in-out;
        }
        .bar:nth-child(2) { animation-delay: 0.1s; }
        .bar:nth-child(3) { animation-delay: 0.2s; }
        .bar:nth-child(4) { animation-delay: 0.3s; }
      `}</style>

      <div 
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onClick={() => setIsExpanded(!isExpanded)}
        className={`
          fixed z-[100] transition-all duration-500 cubic-bezier(0.175, 0.885, 0.32, 1.275)
          
          /* Glassmorphism & Border */
          bg-black/80 backdrop-blur-xl border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.5)]
          overflow-hidden cursor-pointer
          
          /* --- Mobile Style --- */
          bottom-24 left-4 right-4 
          ${isExpanded 
            ? 'h-auto rounded-3xl flex-col p-5 gap-4 items-start ring-1 ring-[#1db954]/50' 
            : 'h-16 rounded-full flex-row items-center px-2 pr-4 gap-3 hover:scale-[1.02] active:scale-95'
          }
          
          /* --- Desktop Style --- */
          md:bottom-6 md:right-6 md:left-auto md:w-80 md:h-auto md:rounded-2xl md:flex-col md:items-stretch md:p-5 md:gap-4 md:cursor-default

          /* Visibility Animation */
          ${isVisible ? 'translate-y-0 opacity-100' : 'translate-y-24 opacity-0 pointer-events-none'}
        `}
      >
        {/* Close Button (Desktop Only) */}
        <div 
          onClick={(e) => { e.stopPropagation(); setIsVisible(false); }}
          className="hidden md:block absolute top-3 right-3 cursor-pointer text-white/40 hover:text-white transition-colors"
        >
          <i className="fas fa-times"></i>
        </div>

        {/* Content Container */}
        <div className={`flex items-center gap-3 md:gap-4 flex-1 min-w-0 w-full`}>
          
          {/* Cover Image (Vinyl Style) */}
          <div className={`relative flex-shrink-0 ${isExpanded ? 'w-16 h-16' : 'w-11 h-11'} md:w-16 md:h-16 transition-all duration-500`}>
             <img 
                src={status.cover} 
                alt="cover" 
                className={`w-full h-full rounded-full object-cover shadow-lg border-2 border-[#1db954]/30 animate-[spin_8s_linear_infinite]`} 
             />
             {/* Center Dot for Vinyl look */}
             <div className="absolute inset-0 m-auto w-2 h-2 bg-black rounded-full border border-gray-700"></div>
          </div>
          
          {/* Text Info */}
          <div className="flex-1 min-w-0 flex flex-col justify-center">
              {/* Sound Wave Indicator (Visible when Collapsed or Desktop) */}
              <div className={`flex items-center gap-1 mb-1 ${isExpanded ? 'hidden' : 'flex'}`}>
                 <div className="bar h-2"></div>
                 <div className="bar h-3"></div>
                 <div className="bar h-2"></div>
                 <span className="text-[10px] font-bold text-[#1db954] tracking-widest uppercase ml-1">Live</span>
              </div>

              <div className={`text-white font-bold leading-tight truncate ${isExpanded ? 'text-lg' : 'text-xs'} md:text-base`}>
                {status.name}
              </div>
              <div className={`text-white/60 truncate ${isExpanded ? 'text-sm' : 'text-[10px]'} md:text-sm`}>
                {status.artist}
              </div>
          </div>

          {/* Action Button (Collapsed Mode: Mini Magic Wand) */}
          {!isExpanded && (
            <button
               onClick={handleArrangePlaylist}
               className="md:hidden w-8 h-8 rounded-full bg-[#1db954]/20 text-[#1db954] flex items-center justify-center hover:bg-[#1db954] hover:text-white transition-colors"
            >
               <i className="fas fa-magic text-xs"></i>
            </button>
          )}

          {/* Chevron Icon (Mobile) */}
          <div className={`md:hidden text-white/30 transition-transform duration-300 ${isExpanded ? 'rotate-180' : 'rotate-0'}`}>
              <i className="fas fa-chevron-up"></i>
          </div>
        </div>
        
        {/* Expanded Content (Button only, mobile-style) */}
        <div className={`
          w-full flex flex-col gap-3 transition-all duration-500
          ${isExpanded ? 'opacity-100 max-h-96' : 'opacity-0 max-h-0 hidden md:flex md:opacity-100 md:max-h-96'}
        `}>
          {/* Full Action Button */}
          <button 
            onClick={handleArrangePlaylist}
            className="w-full py-3 bg-gradient-to-r from-[#1db954] to-[#1aa34a] hover:brightness-110 text-white font-bold rounded-xl text-sm shadow-lg shadow-green-900/20 active:scale-95 transition-all flex items-center justify-center gap-2"
          >
            <i className="fas fa-magic"></i>
            <span>Create Playlist from this</span>
          </button>
        </div>
      </div>
    </>
  );
};

export default LiveAgent;