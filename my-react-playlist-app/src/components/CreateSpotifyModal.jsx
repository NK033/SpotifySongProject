import React, { useEffect, useRef, useState } from 'react';

function CreateSpotifyModal({ isOpen, onClose, onConfirm, isLoading }) {
  const [playlistName, setPlaylistName] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setPlaylistName('');
      setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = playlistName.trim();
    if (!trimmed || isLoading) return;
    onConfirm(trimmed);
  };

  return (
    <div
      className="modal-overlay fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-[70] opacity-100"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isLoading) onClose();
      }}
    >
      <div
        className="modal-content bg-[var(--bg-secondary)] rounded-lg shadow-xl w-full max-w-sm m-4 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <form onSubmit={handleSubmit}>
          <h3 className="text-xl font-bold mb-4 text-[var(--text-primary)]">ตั้งชื่อ Playlist</h3>
          <p className="text-sm mb-4 text-[var(--text-primary)] opacity-80">
            กรุณาใส่ชื่อ Playlist ก่อนสร้างบน Spotify
          </p>

          <input
            ref={inputRef}
            type="text"
            value={playlistName}
            onChange={(e) => setPlaylistName(e.target.value)}
            className="w-full p-3 rounded-md bg-[var(--bg-primary)] border border-[var(--border-color)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-green-500"
            placeholder="เช่น เพลงฟังชิลตอนทำงาน"
            disabled={isLoading}
          />

          <div className="flex justify-end space-x-3 mt-6">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="py-2 px-5 rounded-full text-sm font-medium bg-gray-600 text-white hover:bg-gray-700 transition-colors disabled:opacity-50"
            >
              ยกเลิก
            </button>
            <button
              type="submit"
              disabled={isLoading || !playlistName.trim()}
              className="py-2 px-5 rounded-full text-sm font-medium bg-green-500 text-white hover:bg-green-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <>
                  <i className="fas fa-spinner fa-spin mr-2"></i>
                  กำลังสร้าง...
                </>
              ) : (
                'สร้าง Playlist'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default CreateSpotifyModal;
