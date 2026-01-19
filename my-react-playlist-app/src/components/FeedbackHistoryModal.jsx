// src/components/FeedbackHistoryModal.jsx
import React, { useState } from 'react';
import { useAppContext } from '../contexts/AppContext';

function FeedbackHistoryModal() {
  const { 
    isFeedbackModalOpen, 
    setIsFeedbackModalOpen, 
    feedbackHistory,
    handleUpdateFeedbackHistory
  } = useAppContext();

  const [filter, setFilter] = useState('all'); // 'all', 'like', 'dislike', 'neutral'
  const [searchTerm, setSearchTerm] = useState(''); // ✅ Search State

  if (!isFeedbackModalOpen) return null;

  // Filter Logic
  const filteredHistory = feedbackHistory.filter(item => {
    const matchesFilter = filter === 'all' ? true : item.feedback === filter;
    const matchesSearch = item.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
                          item.artist.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div 
        className="absolute inset-0 bg-black opacity-60 modal-overlay"
        onClick={() => setIsFeedbackModalOpen(false)}
      ></div>
      
      <div className="bg-[var(--bg-secondary)] w-full max-w-2xl rounded-2xl shadow-2xl z-10 flex flex-col max-h-[85vh] modal-content border border-[var(--border-color)]">
        
        {/* Header */}
        <div className="p-6 pb-4 border-b border-[var(--border-color)] bg-[var(--bg-primary)] rounded-t-2xl">
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2 className="text-xl font-bold text-[var(--text-primary)] flex items-center">
                <i className="fas fa-history mr-2 text-[var(--accent-color)]"></i> 
                Feedback History
              </h2>
              <p className="text-sm text-[var(--text-secondary)] mt-1">
                จัดการประวัติการให้คะแนนเพลงของคุณ
              </p>
            </div>
            <button 
              onClick={() => setIsFeedbackModalOpen(false)}
              className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            >
              <i className="fas fa-times text-xl"></i>
            </button>
          </div>

          {/* ✅ Search Bar */}
          <div className="relative">
            <input 
                type="text" 
                placeholder="ค้นหาเพลง หรือ ศิลปิน..." 
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full p-2 pl-9 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-lg text-sm text-[var(--text-primary)] focus:outline-none focus:border-[var(--gradient-start)]"
            />
            <i className="fas fa-search absolute left-3 top-2.5 text-[var(--text-secondary)] text-xs"></i>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex px-4 pt-2 space-x-2 border-b border-[var(--border-color)] bg-[var(--bg-secondary)] overflow-x-auto">
            {['all', 'like', 'dislike', 'neutral'].map(type => (
                <button 
                    key={type}
                    onClick={() => setFilter(type)}
                    className={`pb-3 px-3 text-sm font-medium transition-colors relative whitespace-nowrap 
                        ${filter === type ? getTabColor(type) : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}`}
                >
                    {getTabLabel(type)}
                    {filter === type && <div className={`absolute bottom-0 left-0 w-full h-0.5 rounded-t-full ${getTabUnderlineColor(type)}`}></div>}
                </button>
            ))}
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {filteredHistory.length === 0 ? (
                <div className="text-center py-12 text-[var(--text-muted)]">
                    <i className="far fa-folder-open text-4xl mb-3 opacity-50"></i>
                    <p>ไม่พบเพลงในหมวดนี้</p>
                </div>
            ) : (
                filteredHistory.map((item) => (
                    <div key={item.uri} className="flex items-center justify-between p-3 rounded-xl bg-[var(--bg-glass)] hover:bg-[var(--bg-hover)] transition-colors group">
                        <div className="flex items-center space-x-3 overflow-hidden">
                            <img 
                                src={item.image_url || 'https://placehold.co/50x50'} 
                                alt={item.name} 
                                className="w-12 h-12 rounded-lg object-cover shadow-sm flex-shrink-0"
                            />
                            <div className="min-w-0">
                                <h4 className="text-[var(--text-primary)] font-medium truncate text-sm">{item.name}</h4>
                                <p className="text-[var(--text-secondary)] text-xs truncate">{item.artist}</p>
                            </div>
                        </div>

                        <div className="flex items-center space-x-2 flex-shrink-0 ml-3">
                             {/* Like Button */}
                             <button 
                                onClick={() => handleUpdateFeedbackHistory(item.uri, item.feedback === 'like' ? 'neutral' : 'like')}
                                className={`p-2 rounded-full transition-all ${
                                    item.feedback === 'like' 
                                    ? 'bg-green-500/10 text-green-500' 
                                    : 'text-[var(--text-muted)] hover:bg-green-500/10 hover:text-green-500'
                                }`}
                                title="Like"
                             >
                                <i className={`${item.feedback === 'like' ? 'fas' : 'far'} fa-thumbs-up`}></i>
                             </button>

                             {/* Dislike Button */}
                             <button 
                                onClick={() => handleUpdateFeedbackHistory(item.uri, item.feedback === 'dislike' ? 'neutral' : 'dislike')}
                                className={`p-2 rounded-full transition-all ${
                                    item.feedback === 'dislike' 
                                    ? 'bg-red-500/10 text-red-500' 
                                    : 'text-[var(--text-muted)] hover:bg-red-500/10 hover:text-red-500'
                                }`}
                                title="Dislike"
                             >
                                <i className={`${item.feedback === 'dislike' ? 'fas' : 'far'} fa-thumbs-down`}></i>
                             </button>
                        </div>
                    </div>
                ))
            )}
        </div>

      </div>
    </div>
  );
}

// Helpers for styling
function getTabLabel(type) {
    switch(type) {
        case 'all': return 'ทั้งหมด';
        case 'like': return 'Liked';
        case 'dislike': return 'Disliked';
        case 'neutral': return 'Neutral';
        default: return type;
    }
}

function getTabColor(type) {
    switch(type) {
        case 'like': return 'text-green-500';
        case 'dislike': return 'text-red-500';
        case 'neutral': return 'text-gray-400';
        default: return 'text-[var(--gradient-start)]';
    }
}

function getTabUnderlineColor(type) {
    switch(type) {
        case 'like': return 'bg-green-500';
        case 'dislike': return 'bg-red-500';
        case 'neutral': return 'bg-gray-400';
        default: return 'bg-[var(--gradient-start)]';
    }
}

export default FeedbackHistoryModal;