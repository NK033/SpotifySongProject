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
  onSendMessage, // นี่คือฟังก์ชัน sendMessageToBackend
  suggestedPrompts // <-- รับ Prompts แบบ Dynamic
}) {
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  // (แก้ไข) ส่ง `prompt` เข้าไปใน `onSendMessage` โดยตรงเพื่อแก้บั๊ก
  const handlePromptClick = (prompt) => {
    onUserInputChange({ target: { value: prompt } }); // 1. ตั้งค่าในช่องพิมพ์ (เพื่อ UX)
    onSendMessage(prompt); // 2. ส่งข้อความไปเลยทันที
  };

  return (
    <div className="flex flex-col flex-1 bg-[var(--bg-primary)] transition-colors duration-300 overflow-hidden">
      
      <div className="flex-shrink-0 p-4 border-b border-[var(--border-color)] flex justify-between items-center bg-[var(--bg-secondary)] md:hidden">
        <h1 className="text-[var(--text-primary)] text-lg font-semibold">AI Playlist Chatbot</h1>
        <button onClick={onOpenSidebar} className="text-gray-400 hover:text-white transition-colors">
          <i className="fas fa-bars"></i>
        </button>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-4">
        {chatHistory.map((item) => (
          <ChatMessage
            key={item.id} // ใช้ ID ที่ unique
            item={item}
            onFeedback={onFeedback}
            onShowDetails={onShowDetails}
            onPin={onPin}
            onSummarize={onSummarize}
          />
        ))}
        <div ref={chatEndRef} />
      </div>

      {currentRecommendedSongs.length > 0 && (
        <div className="p-4 pt-0 text-center">
          <button onClick={onCreatePlaylist} className="bg-gradient-to-r from-green-500 to-blue-500 text-white font-semibold py-2 px-6 rounded-full hover:opacity-90 transition-opacity">
            <i className="fas fa-plus mr-2"></i> สร้าง Playlist นี้ใน Spotify
          </button>
        </div>
      )}

      {/* แสดงปุ่มลัด เมื่อยังไม่เริ่มแชท (หรือแชทว่าง) */}
      {chatHistory.length <= 1 && (
        <SuggestedPrompts 
          prompts={suggestedPrompts} // <-- ส่ง Prompts แบบ Dynamic
          onPromptClick={handlePromptClick} 
        />
      )}

      <div className="p-4 md:p-8 flex-shrink-0">
        <div className="relative flex items-center">
          <input
            type="text"
            value={userInput}
            onChange={onUserInputChange}
            // เรียก onSendMessage โดยไม่ส่งอาร์กิวเมนต์ (มันจะไปดึงจาก userInput state)
            onKeyPress={(e) => e.key === 'Enter' && onSendMessage()} 
            placeholder="พิมพ์ข้อความของคุณ..."
            className="w-full p-4 pl-6 pr-16 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-full focus:outline-none focus:ring-2 focus:ring-green-500 transition-colors duration-300 text-[var(--text-primary)]"
          />
          <button 
            onClick={() => onSendMessage()} // เรียก onSendMessage โดยไม่ส่งอาร์กิวเมนต์
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