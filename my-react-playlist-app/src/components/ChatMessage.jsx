import React from 'react';
import SongCard from './SongCard';

function ChatMessage({ item, onFeedback, onShowDetails, onPin }) {
  const { isUser, message, songs, recommendationText } = item;

  return (
    <div className={`flex items-start mb-4 ${isUser ? 'justify-end' : ''}`}>
      {!isUser && <div className="w-10 h-10 rounded-full flex-shrink-0 mr-3"><i className="fas fa-robot text-4xl text-green-500"></i></div>}
      <div className="flex-1">
        <div className={`${isUser ? 'bg-green-500 text-white rounded-tr-none' : 'bg-[var(--chat-bubble-ai)] rounded-tl-none'} p-4 rounded-xl max-w-xl shadow`}>
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
          {songs && songs.length > 0 && !isUser && (
            <div className="mt-3 pt-3 border-t border-gray-500 border-opacity-50">
              <button onClick={() => onPin(songs, recommendationText)} className="pin-playlist-btn text-xs py-1 px-3 rounded-full bg-blue-600 hover:bg-blue-700 text-white transition">
                <i className="fas fa-thumbtack mr-1"></i> Pin Playlist นี้ไว้
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ChatMessage;