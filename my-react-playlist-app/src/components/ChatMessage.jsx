import React from 'react';
import SongCard from './SongCard';

// (*** แก้ไข ***) เพิ่ม props `onSummarize` และ `item` เข้ามา
function ChatMessage({ item, onFeedback, onShowDetails, onPin, onSummarize }) {
  const { isUser, message, songs, recommendationText } = item;

  return (
    <div className={`flex items-start mb-4 ${isUser ? 'justify-end' : ''}`}>
      {!isUser && <div className="w-10 h-10 rounded-full flex-shrink-0 mr-3"><i className="fas fa-robot text-4xl text-green-500"></i></div>}
      <div className="flex-1">
        
        <div 
          className={`${
            isUser 
              ? 'user-chat-bubble text-white rounded-tr-none' 
              : 'bg-[var(--chat-bubble-ai)] rounded-tl-none'
          } p-4 rounded-xl max-w-xl shadow`}
        >
          <p className="text-sm whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: message }}></p>
          {songs && (
            <div className="mt-4">
              {songs.map((song, sIndex) => (
                <SongCard
                  key={sIndex}
                  song={song}
                  onFeedback={onFeedback}
                  onShowDetails={onShowDetails}
                />
              ))}
            </div>
          )}

          {/* (*** แก้ไข ***) เพิ่มปุ่ม "สรุป" (Summarize) ข้างๆ ปุ่ม Pin */}
          {songs && songs.length > 0 && !isUser && (
            <div className="mt-3 pt-3 border-t border-gray-500 border-opacity-50 flex space-x-2">
              <button 
                onClick={() => onPin(songs, recommendationText)} 
                className="pin-playlist-btn text-xs py-1 px-3 rounded-full bg-blue-600 hover:bg-blue-700 text-white transition"
              >
                <i className="fas fa-thumbtack mr-1"></i> Pin Playlist
              </button>
              
              {/* ปุ่มใหม่สำหรับ Summarize */}
              <button 
                onClick={() => onSummarize(item)} // ส่ง "item" ทั้งหมดไป
                className="text-xs py-1 px-3 rounded-full bg-purple-600 hover:bg-purple-700 text-white transition"
              >
                <i className="fas fa-magic mr-1"></i> สรุป (AI)
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ChatMessage;