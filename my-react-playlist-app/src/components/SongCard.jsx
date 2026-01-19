import React, { useState } from 'react';

function SongCard({ song, onFeedback, onShowDetails }) {
  // ✅ 1. Extract Data อย่างระมัดระวัง (เหมือนเดิม)
  const albumName = song.album?.name || 'Unknown Album';
  const artistName = song.artists?.map(a => a.name).join(', ') || song.artist || 'Unknown Artist';
  const imageUrl = song.album?.images?.[0]?.url || song.image_url || 'https://placehold.co/100x100';
  const releaseDate = song.album?.release_date || song.release_date || 'N/A';
  const popularity = song.popularity || 0;

  // ✅ 2. State & Toggle Logic (เหมือนเดิม)
  const [feedbackStatus, setFeedbackStatus] = useState(null);

  const handleToggleFeedback = (type) => {
    let newStatus = null;
    if (feedbackStatus === type) {
      newStatus = null;
    } else {
      newStatus = type;
    }
    setFeedbackStatus(newStatus);

    if (newStatus) {
      onFeedback(song.uri, newStatus);
    }
  };

  return (
    <div className="bg-[var(--bg-secondary)] p-3 rounded-lg flex items-center space-x-3 mb-2 hover:bg-[var(--bg-hover)] transition-colors relative group song-card-animation shadow-sm border border-[var(--border-color)] border-opacity-50">
      
      {/* รูปปก */}
      <img src={imageUrl} alt={song.name} className="w-14 h-14 rounded-md object-cover shadow-sm flex-shrink-0" />
      
      {/* ข้อมูลเพลง */}
      <div className="flex-1 min-w-0">
        <h4 className="text-[var(--text-primary)] font-medium truncate text-base">{song.name}</h4>
        <p className="text-[var(--text-secondary)] text-sm truncate">{artistName}</p>
        
        <div className="flex items-center text-xs text-[var(--text-muted)] mt-1 space-x-2">
          <span className="truncate max-w-[120px]" title={albumName}>
            <i className="fas fa-compact-disc mr-1"></i>{albumName}
          </span>
          <span className="hidden sm:inline">•</span>
          <span className="hidden sm:inline">{releaseDate.split('-')[0]}</span>
        </div>
      </div>

      {/* ✅ 3. ส่วนปุ่ม Action ด้านขวา (เรียงต่อกันเลย) */}
      <div className="flex items-center space-x-2 flex-shrink-0 ml-2">
        
        {/* กลุ่มปุ่ม Like/Dislike (แบบ Toggle) */}
        <div className="flex space-x-1 mr-1">
          <button 
            onClick={() => handleToggleFeedback('like')}
            className={`p-1.5 rounded-full transition-all duration-200 
              ${feedbackStatus === 'like' 
                ? 'text-green-500 bg-green-500/10 scale-110' 
                : 'text-gray-400 hover:text-green-500 hover:bg-gray-500/10'
              } active:scale-95`}
            title="Like"
          >
            <i className={`${feedbackStatus === 'like' ? 'fas' : 'far'} fa-thumbs-up text-lg`}></i>
          </button>

          <button 
            onClick={() => handleToggleFeedback('dislike')}
            className={`p-1.5 rounded-full transition-all duration-200 
              ${feedbackStatus === 'dislike' 
                ? 'text-red-500 bg-red-500/10 scale-110' 
                : 'text-gray-400 hover:text-red-500 hover:bg-gray-500/10'
              } active:scale-95`}
            title="Dislike"
          >
            <i className={`${feedbackStatus === 'dislike' ? 'fas' : 'far'} fa-thumbs-down text-lg mt-0.5`}></i>
          </button>
        </div>

        {/* ✅ 4. ปุ่ม Details แบบเดิม (Visible Button) */}
        <button 
          onClick={() => onShowDetails(song)} 
          className="flex items-center justify-center py-1.5 px-3 rounded-full bg-gray-600 hover:bg-gray-700 text-white transition text-xs shadow-sm whitespace-nowrap"
          title="ดูรายละเอียด"
        >
          <i className="fas fa-info-circle sm:mr-1"></i> 
          <span className="hidden sm:inline">Details</span> {/* ซ่อน Text บนจอมือถือเล็กๆ เพื่อประหยัดที่ */}
        </button>

      </div>

      {/* HOT Label */}
      {popularity > 85 && (
        <div className="absolute top-0 left-0 mt-1 ml-1 pointer-events-none">
          <span className="bg-gradient-to-r from-yellow-400 to-orange-500 text-white text-[9px] font-bold px-1.5 py-0.5 rounded-full shadow-sm flex items-center">
            <i className="fas fa-fire mr-0.5"></i> HOT
          </span>
        </div>
      )}
    </div>
  );
}

export default SongCard;