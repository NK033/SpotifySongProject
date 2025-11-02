import React from 'react';

function SuggestedPrompts({ prompts, onPromptClick }) {
  
  // ถ้าไม่มี prompts หรือเป็น array ว่าง ก็ไม่ต้องแสดงอะไรเลย
  if (!prompts || prompts.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap gap-2 justify-center p-4">
      {prompts.map((prompt) => (
        <button
          key={prompt} // ใช้ prompt เป็น key
          className="suggested-prompt-btn" // (ใช้ class จาก index.css)
          onClick={() => onPromptClick(prompt)}
        >
          {prompt}
        </button>
      ))}
    </div>
  );
}

export default SuggestedPrompts;