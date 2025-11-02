import React, { useState, useEffect, useRef } from 'react';

function RenameModal({ isOpen, currentName, onClose, onRename, isLoading }) {
  const [newName, setNewName] = useState('');
  const inputRef = useRef(null);

  // เมื่อ Modal เปิด หรือชื่อปัจจุบันเปลี่ยน ให้ตั้งค่า state ภายใน
  useEffect(() => {
    if (currentName) {
      setNewName(currentName);
    }
  }, [currentName]);

  // เมื่อ Modal เปิด (isOpen) ให้ focus ที่ input
  useEffect(() => {
    if (isOpen) {
      // ใช้ setTimeout เพื่อให้แน่ใจว่า input พร้อมที่จะ focus
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.focus();
          inputRef.current.select(); // เลือกข้อความทั้งหมด
        }
      }, 100); // 100ms delay
    }
  }, [isOpen]);

  if (!isOpen) {
    return null;
  }

  const handleSubmit = (e) => {
    e.preventDefault();
    if (newName.trim() && newName.trim() !== currentName && !isLoading) {
      onRename(newName.trim());
    }
  };

  // ปิด Modal เมื่อคลิกที่พื้นหลัง
  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) {
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
        <form onSubmit={handleSubmit}>
          <h3 className="text-xl font-bold mb-4 text-[var(--text-primary)]">เปลี่ยนชื่อเพลย์ลิสต์</h3>
          <p className="text-sm mb-1 text-[var(--text-primary)] opacity-80">ป้อนชื่อใหม่สำหรับ:</p>
          <p className="text-sm font-semibold mb-4 text-[var(--text-primary)] truncate">"{currentName}"</p>
          
          <input
            ref={inputRef}
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="w-full p-3 rounded-md bg-[var(--bg-primary)] border border-[var(--border-color)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-green-500"
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
              disabled={isLoading || !newName.trim() || newName.trim() === currentName}
              className="py-2 px-5 rounded-full text-sm font-medium bg-green-500 text-white hover:bg-green-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <>
                  <i className="fas fa-spinner fa-spin mr-2"></i>
                  กำลังบันทึก...
                </>
              ) : (
                'บันทึก'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default RenameModal;