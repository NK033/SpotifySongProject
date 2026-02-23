// src/components/ChatMessage.jsx
import React from 'react';
import SongCard from './SongCard';

function ChatMessage({ item, onFeedback, onShowDetails, onPin, onSummarize, onCreatePlaylist }) {
  const { isUser, message, songs, recommendationText, playlistName } = item;

  return (
    <div className={`flex items-start mb-4 ${isUser ? 'justify-end' : ''}`}>
      
      {/* ✅ AVATAR AI FIX: 
         - มือถือ: w-8 h-8 (เล็กลง) 
         - จอใหญ่: md:w-10 md:h-10 (เท่าเดิม)
         - ไอคอน: text-2xl (มือถือ) -> md:text-3xl (จอใหญ่)
      */}
      {!isUser && (
        <div className="w-8 h-8 md:w-10 md:h-10 rounded-full flex-shrink-0 mr-2 md:mr-3 flex items-center justify-center">
          <i className="fas fa-robot text-2xl md:text-3xl text-green-500"></i>
        </div>
      )}

      <div className={`flex-1 ${isUser ? 'flex justify-end' : ''}`}> {/* เพิ่ม Flex container เพื่อคุม max-width ฝั่ง User ได้ง่ายขึ้น */}
        
        <div 
          className={`${
            isUser 
              ? 'user-chat-bubble text-white rounded-tr-none' 
              : 'bg-[var(--chat-bubble-ai)] rounded-tl-none'
          } p-3 md:p-4 rounded-xl shadow 
          
          /* ✅ CHAT BUBBLE SIZE: ปรับให้กว้างเกือบเต็มจอในมือถือ (85%) แต่ไม่เกิน 2xl ในคอม */
          max-w-[85vw] md:max-w-xl`}
        >
          {/* ส่วนข้อความ */}
          <p className="text-sm md:text-base whitespace-pre-wrap leading-relaxed" dangerouslySetInnerHTML={{ __html: message }}></p>
          
          {/* ปุ่ม Action (Pin / Create) */}
          {songs && songs.length > 0 && !isUser && (
            <div className="mt-3 mb-3 pb-3 border-b border-gray-500 border-opacity-30 flex flex-wrap gap-2">
              <button 
                onClick={() => onPin(songs, recommendationText)} 
                className="pin-playlist-btn text-xs py-1.5 px-3 rounded-full bg-blue-600 hover:bg-blue-700 text-white transition flex items-center"
              >
                <i className="fas fa-thumbtack mr-1.5"></i> Pin
              </button>

              <button 
                onClick={() => onCreatePlaylist(songs, playlistName)} 
                className="create-playlist-btn text-xs py-1.5 px-3 rounded-full bg-green-600 hover:bg-green-700 text-white transition flex items-center"
              >
                <i className="fab fa-spotify mr-1.5"></i> Create on Spotify
              </button>
            </div>
          )}

          {/* รายการเพลง */}
          {songs && (
            <div className="mt-2 space-y-2">
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