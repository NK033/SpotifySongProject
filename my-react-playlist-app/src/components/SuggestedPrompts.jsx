import React from 'react';
import '../App.css'; // import ไฟล์ CSS เดิมตามที่คุณต้องการ

function SuggestedPrompts({ prompts, onPromptClick }) {
  
  // 1. Guard Clause: เช็คความปลอดภัยเพิ่มว่าต้องเป็น Array เท่านั้น
  if (!prompts || !Array.isArray(prompts) || prompts.length === 0) {
    return null;
  }

  return (
    <div className="suggested-prompts-container">
      {/* (Optional) ถ้าอยากให้มีหัวข้อสวยๆ ใส่ตรงนี้ได้ครับ ถ้าไม่เอาลบออกได้ */}
      <h3 style={{ fontSize: '0.9rem', color: '#666', marginBottom: '10px', width: '100%', textAlign: 'center' }}>
        ✨ ลองถามแบบนี้ดูสิ
      </h3>

      <div className="suggested-prompts-list">
        {prompts.map((item, index) => {
          // 2. Logic อัจฉริยะ: รองรับทั้งแบบ String ธรรมดา และแบบ Object
          // ถ้า item เป็น string ให้ใช้เลย, ถ้าเป็น object ให้ดึง key .prompt
          const label = typeof item === 'string' ? item : (item?.prompt || null);

          // 3. ถ้าหาข้อความไม่เจอ ให้ข้ามไปเลย (ไม่แสดงปุ่ม "ตัวเลือก" ให้รกตา)
          if (!label) return null;

          return (
            <button
              key={`${label}-${index}`}
              className="suggested-prompt-btn"
              onClick={() => onPromptClick(label)} // ส่งเฉพาะข้อความกลับไป
            >
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default SuggestedPrompts;