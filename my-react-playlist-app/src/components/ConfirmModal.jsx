import React from 'react';

function ConfirmModal({ isOpen, onClose, onConfirm, isLoading, playlistName }) {
  if (!isOpen) {
    return null;
  }

  // ปิด Modal เมื่อคลิกที่พื้นหลัง
  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget && !isLoading) {
      onClose();
    }
  };

  return (
    <div
      className="modal-overlay fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-[70] opacity-100"
      onClick={handleOverlayClick}
    >
      <div
        className="modal-content bg-[var(--bg-secondary)] rounded-lg shadow-xl w-full max-w-sm m-4 p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-xl font-bold mb-4 text-[var(--text-primary)]">ยืนยันการลบ</h3>
        <p className="text-sm mb-6 text-[var(--text-primary)] opacity-90">
          คุณแน่ใจหรือไม่ว่าต้องการลบเพลย์ลิสต์: <br />
          <span className="font-semibold text-red-400 truncate block mt-1">"{playlistName}"</span>
        </p>
        
        <div className="flex justify-end space-x-3">
          <button
            type="button"
            onClick={onClose}
            disabled={isLoading}
            className="py-2 px-5 rounded-full text-sm font-medium bg-gray-600 text-white hover:bg-gray-700 transition-colors disabled:opacity-50"
          >
            ยกเลิก
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className="py-2 px-5 rounded-full text-sm font-medium bg-red-600 text-white hover:bg-red-700 transition-colors disabled:opacity-50"
          >
            {isLoading ? (
              <>
                <i className="fas fa-spinner fa-spin mr-2"></i>
                กำลังลบ...
              </>
            ) : (
              'ลบ'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmModal;