// src/components/SongCard.jsx
import React from 'react';
import { useAppContext } from '../contexts/AppContext';

function SongCard({ song, onShowDetails, onRemoveSong }) {
  const { userFeedbackMap, handleFeedback } = useAppContext();

  const albumName = song.album?.name || 'Unknown Album';
  const artistName = song.artists?.map(a => a.name).join(', ') || song.artist || 'Unknown Artist';
  const imageUrl = song.album?.images?.[0]?.url || song.image_url || 'https://placehold.co/100x100';
  const releaseDate = song.album?.release_date || song.release_date || 'N/A';
  const popularity = song.popularity || 0;

  const currentStatus = userFeedbackMap[song.uri] || null;

  const handleToggleFeedback = (type) => {
    let newStatus = null;
    if (currentStatus === type) {
      newStatus = 'neutral'; 
    } else {
      newStatus = type;
    }
    handleFeedback(song.uri, newStatus);
  };

  return (
    <div className="bg-[var(--bg-secondary)] p-2 md:p-3 rounded-lg flex items-center space-x-2 md:space-x-3 mb-2 hover:bg-[var(--bg-hover)] transition-colors relative group song-card-animation shadow-sm border border-[var(--border-color)] border-opacity-50">
      
      {/* รูปปก: ลดขนาดลงในมือถือ (w-12) และใหญ่ขึ้นในจอคอม (md:w-14) */}
      <img src={imageUrl} alt={song.name} className="w-12 h-12 md:w-14 md:h-14 rounded-md object-cover shadow-sm flex-shrink-0" />
      
      <div className="flex-1 min-w-0">
        {/* ชื่อเพลง: ใช้ break-words และ leading-tight เพื่อให้แสดงชื่อยาวๆ ได้โดยไม่ตกขอบ */}
        <h4 className="text-[var(--text-primary)] font-medium text-sm md:text-base leading-tight break-words pr-1">
          {song.name}
        </h4>
        <p className="text-[var(--text-secondary)] text-xs truncate mt-0.5">{artistName}</p>
        
        <div className="flex items-center text-xs text-[var(--text-muted)] mt-1 space-x-2">
          {/* ชื่ออัลบั้ม: ซ่อนในมือถือ (hidden) แสดงเฉพาะจอ md ขึ้นไป */}
          <span className="hidden md:flex items-center truncate max-w-[120px]" title={albumName}>
            <i className="fas fa-compact-disc mr-1"></i>{albumName}
          </span>
          {/* ขีดคั่น: ซ่อนในมือถือ */}
          <span className="hidden md:inline">•</span>
          <span>{releaseDate.split('-')[0]}</span>
        </div>
      </div>

      {/* ส่วนปุ่มกด: ปรับขนาดให้กดง่าย แต่ไม่กินที่ */}
      <div className="flex items-center space-x-1 flex-shrink-0 ml-1">
        <div className="flex space-x-1 mr-1">
          {/* ปุ่ม Like */}
          <button 
            onClick={() => handleToggleFeedback('like')}
            className={`p-2 rounded-full transition-all duration-200 
              ${currentStatus === 'like' 
                ? 'text-green-500 bg-green-500/10' 
                : 'text-[var(--text-muted)] hover:text-green-500 hover:bg-gray-500/10' 
              }`}
            title="Like"
          >
            <i className={`${currentStatus === 'like' ? 'fas' : 'far'} fa-thumbs-up text-base md:text-lg`}></i>
          </button>

          {/* ปุ่ม Dislike */}
          <button 
            onClick={() => handleToggleFeedback('dislike')}
            className={`p-2 rounded-full transition-all duration-200 
              ${currentStatus === 'dislike' 
                ? 'text-red-500 bg-red-500/10' 
                : 'text-[var(--text-muted)] hover:text-red-500 hover:bg-gray-500/10' 
              }`}
            title="Dislike"
          >
            <i className={`${currentStatus === 'dislike' ? 'fas' : 'far'} fa-thumbs-down text-base md:text-lg mt-0.5`}></i>
          </button>
        </div>

        <button
          onClick={() => onRemoveSong?.(song.uri)}
          className="flex items-center justify-center w-8 h-8 md:w-auto md:h-auto md:py-1.5 md:px-3 rounded-full bg-red-600 hover:bg-red-700 text-white transition text-xs shadow-sm"
          title="ลบเพลงออกจากรายการ"
        >
          <i className="fas fa-trash md:mr-1"></i>
          <span className="hidden md:inline">Delete</span>
        </button>

        {/* ปุ่ม Details: ซ่อน Text เหลือแต่ Icon ในมือถือ */}
        <button 
          onClick={() => onShowDetails(song)} 
          className="flex items-center justify-center w-8 h-8 md:w-auto md:h-auto md:py-1.5 md:px-3 rounded-full bg-gray-600 hover:bg-gray-700 text-white transition text-xs shadow-sm"
          title="ดูรายละเอียด"
        >
          <i className="fas fa-info-circle md:mr-1"></i> 
          <span className="hidden md:inline">Details</span>
        </button>
      </div>

      {popularity > 85 && (
        <div className="absolute top-0 left-0 mt-1 ml-1 pointer-events-none">
          <span className="bg-gradient-to-r from-yellow-400 to-orange-500 text-white text-[8px] md:text-[9px] font-bold px-1.5 py-0.5 rounded-full shadow-sm flex items-center">
            <i className="fas fa-fire mr-0.5"></i> HOT
          </span>
        </div>
      )}
    </div>
  );
}

export default SongCard;