import React from 'react';
import { useAppContext } from './contexts/AppContext';
import Sidebar from './components/Sidebar';
import ChatWindow from './components/ChatWindow';
import LoadingOverlay from './components/LoadingOverlay';
import SongDetailModal from './components/SongDetailModal';

function App() {
  const {
    sidebarOpen, setSidebarOpen,
    chatHistory,
    userInput, setUserInput,
    isFetching,
    currentTheme, handleToggleTheme,
    currentRecommendedSongs,
    pinnedPlaylists,
    showSongModal, setShowSongModal,
    modalSong,
    modalAnalysis,
    userInfo,
    handleSpotifyLogin,
    handleSpotifyLogout,
    sendMessageToBackend,
    handleCreatePlaylist,
    handleShowDetails,
    handleFeedback,
    handlePinClick,
    displayPlaylistFromHistory,
    handleDeletePinnedPlaylist, // <-- Get new function from context
    handleUpdatePlaylistName   // <-- Get new function from context
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
        onDeletePinned={handleDeletePinnedPlaylist} // <-- Pass prop to Sidebar
        onUpdatePinned={handleUpdatePlaylistName}   // <-- Pass prop to Sidebar
        currentTheme={currentTheme}
        onToggleTheme={handleToggleTheme}
      />
      <ChatWindow
        chatHistory={chatHistory}
        onFeedback={handleFeedback}
        onShowDetails={handleShowDetails}
        onPin={handlePinClick}
        onOpenSidebar={() => setSidebarOpen(true)}
        currentRecommendedSongs={currentRecommendedSongs}
        onCreatePlaylist={handleCreatePlaylist}
        userInput={userInput}
        onUserInputChange={(e) => setUserInput(e.target.value)}
        onSendMessage={sendMessageToBackend}
      />
      {isFetching && <LoadingOverlay />}
      {showSongModal && (
        <SongDetailModal
          song={modalSong}
          analysis={modalAnalysis}
          onClose={() => setShowSongModal(false)}
        />
      )}
    </div>
  );
}

export default App;