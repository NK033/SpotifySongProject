import React from 'react';

function SongDetailModal({ song, analysis, onClose }) {
  if (!song) return null;

  const imageUrl = song.album?.images?.[0]?.url || 'https://placehold.co/100x100';
  const artistName = song.artists?.map(a => a.name).join(', ') || 'Artist';

  // -----------------------------------------------------------------
  // ✅ จุดที่แก้ไข: ดึงเฉพาะเนื้อหาจาก groq_analysis ออกมาแสดง
  // -----------------------------------------------------------------
  let content = "กำลังโหลดข้อมูล...";
  
  if (analysis) {
      if (typeof analysis === 'string') {
          content = analysis;
      } else if (typeof analysis === 'object') {
          // ✅ เรียงลำดับความสำคัญ: ลองหา groq_analysis ก่อนเพื่อนเลย
          content = analysis.groq_analysis || 
                    analysis.gemini_analysis || 
                    analysis.analysis || 
                    analysis.details || 
                    analysis.message || 
                    // ถ้าหาไม่เจอจริงๆ ค่อยแปลงเป็น JSON string (กันเหนียว)
                    JSON.stringify(analysis);
      }
  }

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
            <h3 className="text-xl font-bold text-[var(--text-primary)]">{song.name}</h3>
            <p className="text-md opacity-80 text-[var(--text-secondary)]">{artistName}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-2xl">&times;</button>
        </div>
        <hr className="border-[var(--border-color)] my-4" />
        
        {/* ส่วนแสดงเนื้อหา */}
        <div className="overflow-y-auto max-h-[60vh]">
            <p className="text-sm text-[var(--text-primary)] whitespace-pre-line leading-relaxed">
                {/* แสดงเฉพาะข้อความที่ดึงมาได้ */}
                {content}
            </p>
        </div>
      </div>
    </div>
  );
}

export default SongDetailModal;