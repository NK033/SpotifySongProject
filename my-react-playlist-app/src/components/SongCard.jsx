// src/components/SongCard.jsx
import React from 'react';
import { useAppContext } from '../contexts/AppContext';

function SongCard({ song, onShowDetails }) {
  const { userFeedbackMap, handleFeedback } = useAppContext();

  const albumName = song.album?.name || 'Unknown Album';
  const artistName = song.artists?.map(a => a.name).join(', ') || song.artist || 'Unknown Artist';
  const imageUrl = song.album?.images?.[0]?.url || song.image_url || 'https://placehold.co/100x100';
  const releaseDate = song.album?.release_date || song.release_date || 'N/A';
  const popularity = song.popularity || 0;

  const currentStatus = userFeedbackMap[song.uri] || null;

  const handleToggleFeedback = (type) => {
    let newStatus = null;
    
    // Toggle Logic
    if (currentStatus === type) {
      // ✅ FIX: If pressing the same button, set to 'neutral' instead of removing
      newStatus = 'neutral'; 
    } else {
      newStatus = type;
    }

    handleFeedback(song.uri, newStatus);
  };

  return (
    <div className="bg-[var(--bg-secondary)] p-3 rounded-lg flex items-center space-x-3 mb-2 hover:bg-[var(--bg-hover)] transition-colors relative group song-card-animation shadow-sm border border-[var(--border-color)] border-opacity-50">
      
      <img src={imageUrl} alt={song.name} className="w-14 h-14 rounded-md object-cover shadow-sm flex-shrink-0" />
      
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

      <div className="flex items-center space-x-2 flex-shrink-0 ml-2">
        
        <div className="flex space-x-1 mr-1">
          {/* Like Button */}
          <button 
            onClick={() => handleToggleFeedback('like')}
            className={`p-1.5 rounded-full transition-all duration-200 
              ${currentStatus === 'like' 
                ? 'text-green-500 bg-green-500/10 scale-110' 
                : 'text-[var(--text-muted)] hover:text-green-500 hover:bg-gray-500/10' 
              } active:scale-95`}
            title="Like"
          >
            <i className={`${currentStatus === 'like' ? 'fas' : 'far'} fa-thumbs-up text-lg`}></i>
          </button>

          {/* Dislike Button */}
          <button 
            onClick={() => handleToggleFeedback('dislike')}
            className={`p-1.5 rounded-full transition-all duration-200 
              ${currentStatus === 'dislike' 
                ? 'text-red-500 bg-red-500/10 scale-110' 
                : 'text-[var(--text-muted)] hover:text-red-500 hover:bg-gray-500/10' 
              } active:scale-95`}
            title="Dislike"
          >
            <i className={`${currentStatus === 'dislike' ? 'fas' : 'far'} fa-thumbs-down text-lg mt-0.5`}></i>
          </button>
        </div>

        <button 
          onClick={() => onShowDetails(song)} 
          className="flex items-center justify-center py-1.5 px-3 rounded-full bg-gray-600 hover:bg-gray-700 text-white transition text-xs shadow-sm whitespace-nowrap"
          title="ดูรายละเอียด"
        >
          <i className="fas fa-info-circle sm:mr-1"></i> 
          <span className="hidden sm:inline">Details</span>
        </button>

      </div>

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