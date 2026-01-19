// src/components/ChatWindow.jsx
import React, { useRef, useEffect } from 'react';
import ChatMessage from './ChatMessage';
import SuggestedPrompts from './SuggestedPrompts'; 

function ChatWindow({
  chatHistory,
  onFeedback,
  onShowDetails,
  onPin,
  onSummarize, 
  onOpenSidebar,
  currentRecommendedSongs,
  onCreatePlaylist,
  userInput,
  onUserInputChange,
  onSendMessage, 
  suggestedPrompts 
}) {
  const chatEndRef = useRef(null);

  useEffect(() => {
    const timeoutId = setTimeout(() => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, 100);
    return () => clearTimeout(timeoutId);
  }, [chatHistory]);

  const handlePromptClick = (promptObj) => {
    onUserInputChange({ target: { value: promptObj.prompt } }); 
    onSendMessage(promptObj.prompt, promptObj.intent); 
  };

  return (
    <div className="flex flex-col flex-1 bg-[var(--bg-primary)] transition-colors duration-300 overflow-hidden">
      
      <div className="flex-shrink-0 p-4 border-b border-[var(--border-color)] flex justify-between items-center bg-[var(--bg-secondary)] md:hidden">
        <h1 className="text-[var(--text-primary)] text-lg font-semibold">AI Playlist Chatbot</h1>
        {/* ✅ FIX: ปุ่ม Hamburger Menu (เปลี่ยน text-gray-400 เป็น text-secondary) */}
        <button onClick={onOpenSidebar} className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">
          <i className="fas fa-bars"></i>
        </button>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-4">
        {chatHistory.map((item) => (
          <ChatMessage
            key={item.id} 
            item={item}
            onFeedback={onFeedback}
            onShowDetails={onShowDetails}
            onPin={onPin}
            onSummarize={onSummarize}
            onCreatePlaylist={onCreatePlaylist}
          />
        ))}
        <div ref={chatEndRef} />
      </div>

      {chatHistory.length <= 1 && (
        <SuggestedPrompts 
          prompts={suggestedPrompts} 
          onPromptClick={handlePromptClick} 
        />
      )}

      <div className="p-4 md:p-8 flex-shrink-0">
        <div className="relative flex items-center">
          <input
            type="text"
            value={userInput}
            onChange={onUserInputChange}
            onKeyPress={(e) => e.key === 'Enter' && onSendMessage(userInput, null)} 
            placeholder="พิมพ์ข้อความของคุณ..."
            className="w-full p-4 pl-6 pr-16 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-full focus:outline-none focus:ring-2 focus:ring-green-500 transition-colors duration-300 text-[var(--text-primary)]"
          />
          <button 
            onClick={() => onSendMessage(userInput, null)} 
            className="absolute right-2 text-white bg-gradient-to-r from-green-500 to-blue-500 rounded-full h-10 w-10 flex items-center justify-center hover:opacity-90 transition-opacity"
          >
            <i className="fas fa-paper-plane"></i>
          </button>
        </div>
      </div>
    </div>
  );
}

export default ChatWindow;