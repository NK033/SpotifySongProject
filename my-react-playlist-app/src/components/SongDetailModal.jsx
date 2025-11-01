import React from 'react';

function SongDetailModal({ song, analysis, onClose }) {
  if (!song) return null;

  const imageUrl = song.album?.images?.[0]?.url || 'https://placehold.co/100x100';
  const artistName = song.artists?.map(a => a.name).join(', ') || 'Artist';

  return (
    <div
      className="modal-overlay fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-[70] opacity-100"
      onClick={onClose}
    >
      <div
        className="modal-content bg-[var(--bg-secondary)] rounded-lg shadow-xl w-full max-w-md p-6 transform scale-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start space-x-4">
          <img src={imageUrl} alt="Album Art" className="w-24 h-24 rounded-lg object-cover" />
          <div className="flex-1">
            <h3 className="text-xl font-bold">{song.name}</h3>
            <p className="text-md opacity-80">{artistName}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-2xl">&times;</button>
        </div>
        <hr className="border-[var(--border-color)] my-4" />
        <div
          className="text-sm prose max-w-none text-[var(--text-primary)]"
          dangerouslySetInnerHTML={{ __html: analysis }}
        >
        </div>
      </div>
    </div>
  );
}

export default SongDetailModal;