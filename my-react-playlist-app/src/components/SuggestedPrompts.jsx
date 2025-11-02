import React from 'react';

function SuggestedPrompts({ prompts, onPromptClick }) {
  
  if (!prompts || prompts.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-2 justify-center p-4">
      {/* (*** แก้ไข: เปลี่ยน 'prompt' เป็น 'promptObj' ***) */}
      {prompts.map((promptObj) => ( 
        // (*** แก้ไข: ใช้ .prompt เป็น key ***)
        <button
          key={promptObj.prompt}
          className="suggested-prompt-btn"
          onClick={() => onPromptClick(promptObj)}
        >
          {promptObj.prompt} {/* (*** แก้ไข: แสดงข้อความจาก .prompt ***) */}
        </button>
      ))}
    </div>
  );
}

export default SuggestedPrompts;