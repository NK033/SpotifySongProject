import React, { createContext, useState, useContext, useEffect } from 'react';
import * as api from '../api';

// Create the context
const AppContext = createContext();

// Create a custom hook to easily access the context
export const useAppContext = () => {
  return useContext(AppContext);
};

// Create the provider component that will wrap our app
export const AppProvider = ({ children }) => {
  // --- State Management ---
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [chatHistory, setChatHistory] = useState([
    {
      isUser: false,
      message: 'สวัสดีครับ! ผมคือ AI ที่จะช่วยคุณค้นหา วิเคราะห์ และสร้างเพลย์ลิสต์เพลง ลองพิมพ์บอกผมได้เลยครับ',
      songs: null,
      recommendationText: ''
    }
  ]);
  const [userInput, setUserInput] = useState('');
  const [isFetching, setIsFetching] = useState(false);
  const [currentTheme, setCurrentTheme] = useState(localStorage.getItem('theme') || 'dark');
  const [currentRecommendedSongs, setCurrentRecommendedSongs] = useState([]);
  const [pinnedPlaylists, setPinnedPlaylists] = useState([]);
  const [showSongModal, setShowSongModal] = useState(false);
  const [modalSong, setModalSong] = useState(null);
  const [modalAnalysis, setModalAnalysis] = useState('');
  const [userInfo, setUserInfo] = useState({
    displayName: 'User',
    avatar: 'https://placehold.co/100x100/1DB954/ffffff?text=U',
    isLoggedIn: false,
  });

  // --- Helper Functions ---
  const addMessageToHistory = (message, isUser, songs = null, recommendationText = '') => {
    setChatHistory(prev => [...prev, { message, isUser, songs, recommendationText }]);
  };

  // --- Core Logic Functions ---
  const handleSpotifyLogin = () => { window.location.href = '/spotify_login'; };

  const handleSpotifyLogout = () => {
    localStorage.clear();
    updateUIForLoginState();
    setPinnedPlaylists([]);
    addMessageToHistory('ออกจากระบบ Spotify แล้ว', false);
  };

  const updateUIForLoginState = () => {
    const displayName = localStorage.getItem('spotify_display_name');
    const avatar = localStorage.getItem('spotify_avatar');
    const isLoggedIn = !!localStorage.getItem('spotify_access_token') && !!displayName;
    setUserInfo({ displayName: displayName || 'User', avatar: avatar || 'https://placehold.co/100x100/1DB954/ffffff?text=U', isLoggedIn });
  };
  
  const sendMessageToBackend = async () => {
    if (isFetching || userInput.trim() === '') return;
    const userMessage = userInput.trim();
    addMessageToHistory(userMessage, true);
    setUserInput('');
    setIsFetching(true);
    setCurrentRecommendedSongs([]);

    try {
      const data = await api.postChatMessage(userMessage);
      const songs = (data.songs_found && data.songs_found.length > 0) ? data.songs_found : [];
      addMessageToHistory(data.response || '', false, songs, data.response);
      if (songs.length > 0) {
        setCurrentRecommendedSongs(songs);
      }
    } catch (error) {
      addMessageToHistory(`ขออภัยค่ะ เกิดข้อผิดพลาด: ${error.message}`, false);
    } finally {
      setIsFetching(false);
    }
  };
  
  const handleCreatePlaylist = async () => {
    if (currentRecommendedSongs.length === 0) return;
    const playlistName = `AI Playlist: ${new Date().toLocaleString('th-TH')}`;
    const trackUris = currentRecommendedSongs.map(s => s.uri);
    setIsFetching(true);
    try {
        const result = await api.createSpotifyPlaylist(playlistName, trackUris);
        const successMessage = `สร้างเพลย์ลิสต์ '${playlistName}' ให้เรียบร้อยแล้วครับ! <a href="${result.playlist_info.external_urls.spotify}" target="_blank" class="inline-block mt-2 text-sm py-2 px-4 rounded-full bg-green-500 text-white hover:bg-green-600"><i class="fab fa-spotify mr-2"></i> เปิดใน Spotify</a>`;
        addMessageToHistory(successMessage, false);
    } catch (error) {
        addMessageToHistory('ขออภัยครับ เกิดข้อผิดพลาดในการสร้างเพลย์ลิสต์', false);
    } finally {
        setIsFetching(false);
    }
  };

  const handleShowDetails = async (song) => {
    setModalSong(song);
    setModalAnalysis('<p>กำลังโหลดการวิเคราะห์...</p>');
    setShowSongModal(true);
    try {
      const details = await api.fetchSongDetails(song.uri);
      const analysisHtml = details.gemini_analysis.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
      setModalAnalysis(analysisHtml);
    } catch (error) {
      setModalAnalysis('<p>ไม่สามารถโหลดข้อมูลการวิเคราะห์ได้</p>');
    }
  };

  const handleFeedback = async (trackUri, feedback) => {
     try {
        await api.sendFeedback(trackUri, feedback);
    } catch (error) {
        addMessageToHistory('กรุณาเข้าสู่ระบบ Spotify ก่อนให้ Feedback ครับ', false);
    }
  };

  const handlePinClick = async (songs, recText) => {
    try {
        const playlistName = `AI Playlist - ${new Date().toLocaleTimeString('th-TH')}`;
        await api.pinPlaylist(playlistName, songs, recText);
        await fetchAndRenderPinnedPlaylists();
    } catch (error) {
        alert('เกิดข้อผิดพลาดในการ Pin เพลย์ลิสต์');
    }
  };

  // --- NEW FUNCTION ---
  const handleDeletePinnedPlaylist = async (pinId) => {
    try {
      await api.deletePinnedPlaylist(pinId);
      await fetchAndRenderPinnedPlaylists(); // Refresh the list
    } catch (error) {
      console.error("Delete Pin Error:", error);
      alert('เกิดข้อผิดพลาดในการลบเพลย์ลิสต์');
    }
  };

  // --- NEW FUNCTION ---
  const handleUpdatePlaylistName = async (pinId, newName, songs) => {
    try {
      await api.updatePinnedPlaylist(pinId, newName, songs);
      await fetchAndRenderPinnedPlaylists(); // Refresh the list
    } catch (error) {
      console.error("Update Pin Error:", error);
      alert('เกิดข้อผิดพลาดในการอัปเดตชื่อเพลย์ลิสต์');
    }
  };

  const fetchAndRenderPinnedPlaylists = async () => {
    try {
      const data = await api.fetchPinnedPlaylists();
      setPinnedPlaylists(data);
    } catch (error) {
       // Ignore error if not logged in
    }
  };

  // --- UPDATED FUNCTION ---
  // Now finds by pin_id instead of index
  const displayPlaylistFromHistory = (pinId) => {
    const historyItem = pinnedPlaylists.find(p => p.pin_id === pinId);
    if (!historyItem) return;
    addMessageToHistory(historyItem.recommendationText, false, historyItem.songs, historyItem.recommendationText);
    setCurrentRecommendedSongs(historyItem.songs);
  };

  const handleToggleTheme = () => {
      const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
      setCurrentTheme(newTheme);
      localStorage.setItem('theme', newTheme);
  };

  // --- Effects ---
  useEffect(() => {
    document.body.className = `${currentTheme}-theme transition-colors duration-300`;
  }, [currentTheme]);

  useEffect(() => {
    const initializeApp = async () => {
      const urlParams = new URLSearchParams(window.location.search);
      const accessToken = urlParams.get('access_token');

      if (accessToken) {
        const expiresIn = urlParams.get('expires_in');
        const refreshToken = urlParams.get('refresh_token');
        const expiresAt = Date.now() + (parseInt(expiresIn, 10) * 1000);
        localStorage.setItem('spotify_access_token', accessToken);
        localStorage.setItem('spotify_expires_at', expiresAt);
        if (refreshToken) localStorage.setItem('spotify_refresh_token', refreshToken);
        window.history.replaceState({}, document.title, "/");

        try {
          const profile = await api.fetchUserProfile();
          localStorage.setItem('spotify_display_name', profile.display_name);
          if (profile.images && profile.images.length > 0) {
            localStorage.setItem('spotify_avatar', profile.images[0].url);
          }
          addMessageToHistory('เข้าสู่ระบบ Spotify สำเร็จแล้ว!', false);
          fetchAndRenderPinnedPlaylists();
        } catch (error) {
           handleSpotifyLogout();
        }
      } else if (localStorage.getItem('spotify_access_token')) {
        fetchAndRenderPinnedPlaylists();
      }
      updateUIForLoginState();
    };
    initializeApp();
  }, []);

  // The value that will be available to all consumer components
  const value = {
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
    handleDeletePinnedPlaylist, // <-- ADD THIS
    handleUpdatePlaylistName,  // <-- ADD THIS
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
};