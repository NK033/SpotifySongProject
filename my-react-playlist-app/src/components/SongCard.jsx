import React from 'react';

function SongCard({ song, onFeedback, onShowDetails }) {
  const imageUrl = song.album?.images?.[0]?.url || 'https://placehold.co/100x100';
  const artistName = song.artists?.map(a => a.name).join(', ') || 'ศิลปิน';

  return (
    <div className="song-item-card p-3 rounded-lg border flex items-center space-x-3 mb-2">
      <img src={imageUrl} className="w-16 h-16 rounded-lg object-cover" alt={`${song.name} album art`} />
      <div className="flex-1 text-left">
        <div className="font-semibold">{song.name}</div>
        <div className="text-sm opacity-80">{artistName}</div>
      </div>
      <button onClick={() => onFeedback(song.uri, 'like')} className="feedback-btn text-xl text-gray-400 hover:text-green-500 transition">👍</button>
      <button onClick={() => onFeedback(song.uri, 'dislike')} className="feedback-btn text-xl text-gray-400 hover:text-red-500 transition">👎</button>
      <button onClick={() => onShowDetails(song)} className="show-details-btn text-sm py-2 px-4 rounded-full bg-gray-600 hover:bg-gray-700 transition">
        <i className="fas fa-info-circle"></i>
      </button>
      <a href={song.external_urls?.spotify || '#'} target="_blank" rel="noopener noreferrer" className="flex-shrink-0 py-2 px-4 rounded-full bg-green-500 text-white hover:bg-green-600">
        <i className="fab fa-spotify"></i>
      </a>
    </div>
  );
}

export default SongCard;