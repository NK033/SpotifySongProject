// src/components/ChatMessage.jsx
import React from 'react';
import SongCard from './SongCard';

function ChatMessage({ item, onFeedback, onShowDetails, onPin, onSummarize, onCreatePlaylist }) {
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
          {/* 1. ส่วนข้อความ */}
          <p className="text-sm whitespace-pre-wrap" dangerouslySetInnerHTML={{ __html: message }}></p>
          
          {/* 2. ✅ MOVED: ย้ายปุ่ม Action มาไว้ตรงนี้ (ใต้ข้อความ - บนเพลง) */}
          {songs && songs.length > 0 && !isUser && (
            <div className="mt-3 mb-3 pb-3 border-b border-gray-500 border-opacity-50 flex flex-wrap gap-2">
              {/* ปุ่ม Pin */}
              <button 
                onClick={() => onPin(songs, recommendationText)} 
                className="pin-playlist-btn text-xs py-1 px-3 rounded-full bg-blue-600 hover:bg-blue-700 text-white transition flex items-center"
              >
                <i className="fas fa-thumbtack mr-1"></i> Pin
              </button>

              {/* ปุ่ม Create on Spotify */}
              <button 
                onClick={() => onCreatePlaylist(songs)} 
                className="create-playlist-btn text-xs py-1 px-3 rounded-full bg-green-600 hover:bg-green-700 text-white transition flex items-center"
              >
                <i className="fab fa-spotify mr-1"></i> Create on Spotify
              </button>
            </div>
          )}

          {/* 3. ส่วนรายการเพลง */}
          {songs && (
            <div className="mt-2"> {/* ปรับ margin-top ให้น้อยลงนิดหน่อยเพราะมีเส้นคั่นด้านบนแล้ว */}
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
          
        </div>
      </div>
    </div>
  );
}

export default ChatMessage;