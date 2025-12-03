import React from 'react';
import '../App.css'; // ต้องมั่นใจว่า import App.css เข้ามา

function SuggestedPrompts({ prompts, onPromptClick }) {
  
  if (!prompts || prompts.length === 0) {
    return null;
  }

  return (
    // เปลี่ยนจาก flex... เป็นชื่อ class ปกติ
    <div className="suggested-prompts-container">
      {prompts.map((promptObj, index) => {
        const label = promptObj.prompt || "ตัวเลือก";
        return (
          <button
            key={`${label}-${index}`}
            // เปลี่ยน class ให้เป็นชื่อที่เราจะไปเขียน CSS
            className="suggested-prompt-btn"
            onClick={() => onPromptClick(promptObj)}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

export default SuggestedPrompts;