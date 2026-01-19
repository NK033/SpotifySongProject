import React, { useState } from 'react';

const PinModal = ({ isOpen, onClose, onConfirm, isLoading }) => {
  const [playlistName, setPlaylistName] = useState('My AI Playlist');

  if (!isOpen) return null;

  const handleSubmit = (e) => {
    e.preventDefault();
    onConfirm(playlistName);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 backdrop-blur-sm p-4">
      <div className="bg-[var(--bg-secondary)] rounded-2xl shadow-xl w-full max-w-md border border-[var(--border-color)] transform transition-all scale-100">
        <div className="p-6">
          <h3 className="text-xl font-bold text-[var(--text-primary)] mb-4 flex items-center">
            <i className="fas fa-thumbtack text-green-500 mr-2"></i>
            ปักหมุด Playlist นี้
          </h3>
          
          <p className="text-[var(--text-secondary)] mb-4 text-sm">
            ตั้งชื่อ Playlist ของคุณเพื่อเก็บไว้ดูภายหลัง
          </p>

          <form onSubmit={handleSubmit}>
            <input
              type="text"
              value={playlistName}
              onChange={(e) => setPlaylistName(e.target.value)}
              className="w-full bg-[var(--bg-primary)] text-[var(--text-primary)] border border-[var(--border-color)] rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-green-500 mb-6"
              placeholder="ชื่อ Playlist..."
              autoFocus
            />

            <div className="flex justify-end space-x-3">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-lg text-[var(--text-secondary)] hover:bg-[var(--bg-primary)] transition-colors"
                disabled={isLoading}
              >
                ยกเลิก
              </button>
              <button
                type="submit"
                className="px-4 py-2 rounded-lg bg-green-500 text-white hover:bg-green-600 transition-colors flex items-center"
                disabled={isLoading}
              >
                {isLoading ? (
                  <><i className="fas fa-spinner fa-spin mr-2"></i> กำลังบันทึก...</>
                ) : (
                  'ยืนยัน'
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default PinModal;