// src/App.jsx
import React from 'react';
import { useAppContext } from './contexts/AppContext';
import Sidebar from './components/Sidebar';
import ChatWindow from './components/ChatWindow';
import LoadingOverlay from './components/LoadingOverlay';
import SongDetailModal from './components/SongDetailModal';
import RenameModal from './components/RenameModal';
import ConfirmModal from './components/ConfirmModal';
import LiveAgent from './components/LiveAgent';
import PinModal from './components/PinModal'; 
import FeedbackHistoryModal from './components/FeedbackHistoryModal';

function App() {
  const {
    sidebarOpen, setSidebarOpen,
    chatHistory,
    userInput, setUserInput,
    isFetching,
    currentTheme, handleToggleTheme,
    currentRecommendedSongs,
    pinnedPlaylists,
    userInfo, // ✅ เราจะส่งตัวนี้ไป
    handleSpotifyLogin,
    handleSpotifyLogout,
    sendMessageToBackend,
    handleCreatePlaylist,
    handleShowDetails,
    handleFeedback,
    handlePinClick,
    
    isPinModalOpen, 
    setIsPinModalOpen,
    handleSubmitPin,

    displayPlaylistFromHistory,
    handleSummarizePlaylist,
    suggestedPrompts,
    
    handleDeletePinnedPlaylist,
    isRenameModalOpen,
    isSubmitting,
    playlistToRename,
    handleOpenRenameModal,
    handleCloseRenameModal,
    handleSubmitRename,
    isConfirmModalOpen,
    playlistToDelete,
    handleCloseConfirmModal,
    handleSubmitDelete,
    showSongModal, setShowSongModal,
    modalSong,
    modalAnalysis,
  } = useAppContext();

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg-primary)]">
      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        userInfo={userInfo}
        onLogin={handleSpotifyLogin}
        onLogout={handleSpotifyLogout}
        pinnedPlaylists={pinnedPlaylists}
        onSelectPinned={displayPlaylistFromHistory}
        onDeletePinned={handleDeletePinnedPlaylist}
        onUpdatePinned={handleOpenRenameModal} 
        currentTheme={currentTheme}
        onToggleTheme={handleToggleTheme}
      />
      
      <ChatWindow
        userInfo={userInfo} // ✅ เพิ่มบรรทัดนี้: ส่งสถานะ Login ไปให้ ChatWindow รู้
        chatHistory={chatHistory}
        onFeedback={handleFeedback}
        onShowDetails={handleShowDetails}
        onPin={handlePinClick}
        onSummarize={handleSummarizePlaylist}
        onOpenSidebar={() => setSidebarOpen(true)}
        currentRecommendedSongs={currentRecommendedSongs}
        onCreatePlaylist={handleCreatePlaylist}
        userInput={userInput}
        onUserInputChange={(e) => setUserInput(e.target.value)}
        onSendMessage={sendMessageToBackend}
        suggestedPrompts={suggestedPrompts}
      />
      
      {/* --- Modals --- */}
      <ConfirmModal
        isOpen={isConfirmModalOpen}
        playlistName={playlistToDelete?.name || ''}
        onClose={handleCloseConfirmModal}
        onConfirm={handleSubmitDelete}
        isLoading={isSubmitting}
      />
      
      <RenameModal
        isOpen={isRenameModalOpen}
        currentName={playlistToRename?.name || ''}
        onClose={handleCloseRenameModal}
        onRename={handleSubmitRename}
        isLoading={isSubmitting}
      />

      <PinModal
        isOpen={isPinModalOpen}
        onClose={() => setIsPinModalOpen(false)}
        onConfirm={handleSubmitPin}
        isLoading={isSubmitting}
      />

      <FeedbackHistoryModal />
      
      {(isFetching || isSubmitting) && <LoadingOverlay />}

      {showSongModal && (
        <SongDetailModal
          song={modalSong}
          analysis={modalAnalysis}
          onClose={() => setShowSongModal(false)}
        />
      )}
      
      <LiveAgent onSendMessage={sendMessageToBackend} />
    </div>
  );
}

export default App;