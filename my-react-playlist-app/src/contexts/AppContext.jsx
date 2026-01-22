// src/contexts/AppContext.jsx
import React, { createContext, useState, useContext, useEffect } from 'react';
import { 
  fetchUserProfile, 
  sendMessageToChatbot, 
  createPlaylistAPI, 
  getSongDetailsAPI, 
  sendFeedbackAPI, 
  pinPlaylistAPI,
  deletePinnedPlaylistAPI,
  updatePinnedPlaylistAPI,
  summarizePlaylistAPI,
  getSuggestedPromptsAPI,
  getPinnedPlaylistsAPI,
  // ✅ Import NEW functions
  getFeedbackHistoryAPI,
  deleteFeedbackAPI,
  getFeedbackStatusAPI,
  BASE_URL // ✅ FIX 1: Import the IP Address from api.js
} from '../api';

const AppContext = createContext();

export const AppProvider = ({ children }) => {
  // --- Original States ---
  const [sidebarOpen, setSidebarOpen] = useState(false);
  
  const [chatHistory, setChatHistory] = useState(() => {
    try {
      const saved = localStorage.getItem('chat_history');
      return saved ? JSON.parse(saved) : [
        { 
          id: 'welcome-msg', 
          isUser: false, 
          message: "สวัสดีครับ! ผมคือ AI Music Assistant 🎵\nอยากให้ช่วยแนะนำเพลงแบบไหน หรือจัด Playlist อารมณ์ไหน บอกผมได้เลยครับ!" 
        }
      ];
    } catch (e) {
      console.error("Error parsing chat history", e);
      return [];
    }
  });

  const [userInput, setUserInput] = useState('');
  const [isFetching, setIsFetching] = useState(false);
  const [currentTheme, setCurrentTheme] = useState('dark');
  const [currentRecommendedSongs, setCurrentRecommendedSongs] = useState([]);
  const [userInfo, setUserInfo] = useState(null);
  const [pinnedPlaylists, setPinnedPlaylists] = useState([]);
  
  // Modal States
  const [isRenameModalOpen, setIsRenameModalOpen] = useState(false);
  const [isPinModalOpen, setIsPinModalOpen] = useState(false); 
  const [songsToPin, setSongsToPin] = useState([]); 
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [playlistToRename, setPlaylistToRename] = useState(null);
  const [isConfirmModalOpen, setIsConfirmModalOpen] = useState(false);
  const [playlistToDelete, setPlaylistToDelete] = useState(null);
  const [showSongModal, setShowSongModal] = useState(false);
  const [modalSong, setModalSong] = useState(null);
  const [modalAnalysis, setModalAnalysis] = useState(null);
  const [suggestedPrompts, setSuggestedPrompts] = useState([]);

  // ✅ NEW States for Feedback History & Status
  const [isFeedbackModalOpen, setIsFeedbackModalOpen] = useState(false);
  const [feedbackHistory, setFeedbackHistory] = useState([]);
  const [userFeedbackMap, setUserFeedbackMap] = useState({}); // Stores { uri: 'like'/'dislike' }

  // --- Effects ---
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const accessToken = params.get('access_token');
    const refreshToken = params.get('refresh_token');
    const expiresAt = params.get('expires_at');

    if (accessToken) {
        localStorage.setItem('spotify_access_token', accessToken);
        if (refreshToken) localStorage.setItem('spotify_refresh_token', refreshToken);
        if (expiresAt) localStorage.setItem('spotify_expires_at', expiresAt);
        window.history.replaceState({}, document.title, "/");
        
        // Initial Data Load
        handleFetchUserProfile();
        fetchPinnedPlaylists();
        fetchUserFeedbackStatus(); // ✅ Load Likes/Dislikes
    } else {
        const savedToken = localStorage.getItem('spotify_access_token');
        if (savedToken) {
            handleFetchUserProfile();
            fetchPinnedPlaylists();
            fetchUserFeedbackStatus(); // ✅ Load Likes/Dislikes
        }
    }
    fetchSuggestedPrompts();
  }, []);

  useEffect(() => {
    localStorage.setItem('chat_history', JSON.stringify(chatHistory));
  }, [chatHistory]);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', currentTheme);
  }, [currentTheme]);

  // --- Actions ---
  const handleFetchUserProfile = async () => {
    try {
      const data = await fetchUserProfile();
      setUserInfo(data);
    } catch (error) {
      console.error("Failed to fetch user profile", error);
    }
  };

  const fetchPinnedPlaylists = async () => {
    const token = localStorage.getItem('spotify_access_token');
    if (!token) return;
    try {
      const playlists = await getPinnedPlaylistsAPI(); 
      setPinnedPlaylists(playlists);
    } catch (error) {
      console.error("Failed to fetch pinned playlists", error);
    }
  };

  // ✅ NEW: Fetch all feedback status
  const fetchUserFeedbackStatus = async () => {
    try {
        const data = await getFeedbackStatusAPI();
        const map = {};
        if (data.likes) data.likes.forEach(uri => map[uri] = 'like');
        if (data.dislikes) data.dislikes.forEach(uri => map[uri] = 'dislike');
        setUserFeedbackMap(map);
    } catch (error) {
        console.error("Failed to sync feedback status", error);
    }
  };

  const fetchSuggestedPrompts = async () => {
    try {
        const data = await getSuggestedPromptsAPI();
        if (data && data.prompts) setSuggestedPrompts(data.prompts);
    } catch (error) {
        console.error("Failed to fetch prompts", error);
    }
  };

  const sendMessageToBackend = async (messageOverride = null, intentOverride = null) => {
    const messageToSend = messageOverride || userInput;
    if (!messageToSend.trim()) return;

    if (!messageOverride) setUserInput('');

    const userMsgId = `user-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const newUserMsg = { id: userMsgId, isUser: true, message: messageToSend };
    
    setChatHistory(prev => [...prev, newUserMsg]);
    setIsFetching(true); 

    try {
      const data = await sendMessageToChatbot(messageToSend, intentOverride);
      const aiMsgId = `ai-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      const responseText = data.response || "จัดให้ตามคำขอครับ! (AI ไม่ได้ส่งข้อความตอบกลับ)";

      const newAiMsg = { 
        id: aiMsgId, 
        isUser: false, 
        message: responseText, 
        songs: data.songs_found || [],
        recommendationText: responseText 
      };
      setChatHistory(prev => [...prev, newAiMsg]);

      if (data.songs_found && data.songs_found.length > 0) {
        setCurrentRecommendedSongs(data.songs_found);
      }
    } catch (error) {
      const errorMsg = { id: `err-${Date.now()}`, isUser: false, message: "ขออภัยครับ เกิดข้อผิดพลาดในการเชื่อมต่อกับเซิร์ฟเวอร์" };
      setChatHistory(prev => [...prev, errorMsg]);
    } finally {
      setIsFetching(false);
    }
  };

  const handleCreatePlaylist = async (songs = []) => {
    const targetSongs = (Array.isArray(songs) && songs.length > 0) ? songs : currentRecommendedSongs;

    if (!targetSongs || targetSongs.length === 0) return;
    
    const trackUris = targetSongs.map(song => song.uri);
    setIsFetching(true);
    try {
      await createPlaylistAPI("AI Recommended Playlist", trackUris);
      alert("Playlist created successfully on Spotify!");
    } catch (error) {
      alert("Failed to create playlist.");
    } finally {
      setIsFetching(false);
    }
  };

  const handleShowDetails = async (song) => {
    setIsFetching(true);
    try {
      const details = await getSongDetailsAPI(song.uri);
      setModalSong(song);
      setModalAnalysis(details);
      setShowSongModal(true);
    } catch (error) {
      console.error("Failed to fetch song details", error);
    } finally {
      setIsFetching(false);
    }
  };

  // ✅ UPDATE: Handle Feedback (Toggle logic: Like -> Neutral (Delete) -> Dislike)
  const handleFeedback = async (uri, feedback) => {
    // 1. Optimistic Update (Map)
    setUserFeedbackMap(prev => {
        const newMap = { ...prev };
        if (feedback === 'neutral') delete newMap[uri]; // Remove from map
        else newMap[uri] = feedback; 
        return newMap;
    });

    // 2. Call API
    try { 
        if (feedback === 'neutral') {
             await deleteFeedbackAPI(uri); // Call Delete Endpoint
        } else {
             await sendFeedbackAPI(uri, feedback); 
        }
    } catch (error) { 
        console.error("Failed to update feedback", error); 
        fetchUserFeedbackStatus(); // Revert on error
    }
  };

  const handlePinClick = (songs, text) => {
    setSongsToPin(songs);
    setIsPinModalOpen(true); 
  };

  const handleSubmitPin = async (name) => {
    if (name && songsToPin.length > 0) {
        setIsSubmitting(true);
        try {
            await pinPlaylistAPI(name, songsToPin, "Pinned from chat");
            await fetchPinnedPlaylists();
            setIsPinModalOpen(false);
            setSongsToPin([]);
        } catch (error) {
            alert("Failed to pin playlist.");
        } finally {
            setIsSubmitting(false);
        }
    }
  };

  const displayPlaylistFromHistory = (playlist) => {
    let songs = playlist.songs;
    if (typeof songs === 'string') {
        try { songs = JSON.parse(songs); } catch (e) { songs = []; }
    }
    if (!Array.isArray(songs)) songs = [];

    const aiMsg = {
      id: `history-${Date.now()}`,
      isUser: false,
      message: `นี่คือ Playlist ที่คุณปักหมุดไว้: **${playlist.name}**\n${playlist.recommendation_text || ''}`,
      songs: songs, 
      recommendationText: playlist.recommendation_text
    };
    
    setChatHistory(prev => [...prev, aiMsg]);
    setCurrentRecommendedSongs(songs);
    if (window.innerWidth < 768) setSidebarOpen(false);
  };

  const handleDeletePinnedPlaylist = async (pinId) => {
    setPlaylistToDelete({ id: pinId });
    setIsConfirmModalOpen(true);
  };

  const handleSubmitDelete = async () => {
    if (playlistToDelete) {
      setIsSubmitting(true);
      try {
        await deletePinnedPlaylistAPI(playlistToDelete.id);
        await fetchPinnedPlaylists();
        setIsConfirmModalOpen(false);
        setPlaylistToDelete(null);
      } catch (error) {
        alert("Failed to delete playlist");
      } finally {
        setIsSubmitting(false);
      }
    }
  };

  const handleOpenRenameModal = (playlist) => {
    setPlaylistToRename(playlist);
    setIsRenameModalOpen(true);
  };

  const handleCloseRenameModal = () => {
    setIsRenameModalOpen(false);
    setPlaylistToRename(null);
  };

  const handleSubmitRename = async (newName) => {
    if (playlistToRename && newName) {
      setIsSubmitting(true);
      try {
        await updatePinnedPlaylistAPI(playlistToRename.id, newName, playlistToRename.songs);
        await fetchPinnedPlaylists();
        handleCloseRenameModal();
      } catch (error) {
        alert("Failed to rename playlist");
      } finally {
        setIsSubmitting(false);
      }
    }
  };

  const handleCloseConfirmModal = () => {
    setIsConfirmModalOpen(false);
    setPlaylistToDelete(null);
  };

  const handleSummarizePlaylist = async (songs) => {
    setIsFetching(true);
    try {
        const songUris = songs.map(s => s.uri);
        const data = await summarizePlaylistAPI(songUris);
        const summaryMsg = {
            id: `summary-${Date.now()}`,
            isUser: false,
            message: `📊 **สรุปภาพรวม Playlist:**\n\n${data.summary}`
        };
        setChatHistory(prev => [...prev, summaryMsg]);
    } catch (error) {
        console.error("Summarize failed", error);
        alert("เกิดข้อผิดพลาดในการสรุป Playlist");
    } finally {
        setIsFetching(false);
    }
  };
  
  const handleToggleTheme = () => {
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    setCurrentTheme(newTheme);
    document.documentElement.setAttribute('data-theme', newTheme);
  };

  // ✅ FIX 2: Use the real IP address for Login
  const handleSpotifyLogin = () => { 
      window.location.href = `${BASE_URL}/spotify_login`; 
  };
  
  const handleSpotifyLogout = () => {
    localStorage.clear();
    setUserInfo(null);
    setPinnedPlaylists([]);
    setUserFeedbackMap({});
    window.location.href = '/';
  };

  // ✅ NEW: Logic for Feedback History Modal
  const handleOpenFeedbackModal = async () => {
    setIsFeedbackModalOpen(true);
    setIsFetching(true);
    try {
        const data = await getFeedbackHistoryAPI();
        setFeedbackHistory(data);
    } catch (error) {
        console.error("Failed to fetch feedback history", error);
    } finally {
        setIsFetching(false);
    }
  };

  const handleUpdateFeedbackHistory = async (uri, newStatus) => {
    // Sync with global Map
    setUserFeedbackMap(prev => {
        const next = { ...prev };
        if (newStatus === 'neutral') delete next[uri];
        else next[uri] = newStatus;
        return next;
    });

    // Sync with History List
    setFeedbackHistory(prev => prev.map(item => {
        if (item.uri === uri) {
            return { ...item, feedback: newStatus };
        }
        return item;
    }));

    try {
        if (newStatus === 'neutral') {
            await deleteFeedbackAPI(uri);
        } else {
            await sendFeedbackAPI(uri, newStatus);
        }
    } catch (error) {
        console.error("Failed to update feedback", error);
        // Reload if error
        const data = await getFeedbackHistoryAPI();
        setFeedbackHistory(data);
    }
  };

  return (
    <AppContext.Provider value={{
      // Original Values
      sidebarOpen, setSidebarOpen,
      chatHistory, setChatHistory,
      userInput, setUserInput,
      isFetching, setIsFetching,
      currentTheme, setCurrentTheme,
      currentRecommendedSongs,
      userInfo,
      pinnedPlaylists,
      sendMessageToBackend,
      handleCreatePlaylist,
      handleSpotifyLogin,
      handleSpotifyLogout,
      handleShowDetails,
      handleFeedback, // Updated version
      handlePinClick,
      handleSubmitPin,
      isPinModalOpen,
      setIsPinModalOpen,
      displayPlaylistFromHistory,
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
      handleSummarizePlaylist,
      handleToggleTheme,
      suggestedPrompts,
      
      // ✅ New Feedback Values
      isFeedbackModalOpen, 
      setIsFeedbackModalOpen,
      handleOpenFeedbackModal,
      feedbackHistory,
      handleUpdateFeedbackHistory,
      userFeedbackMap,
      fetchUserFeedbackStatus
    }}>
      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => useContext(AppContext);