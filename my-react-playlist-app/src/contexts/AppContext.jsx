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
  getFeedbackHistoryAPI,
  deleteFeedbackAPI,
  getFeedbackStatusAPI,
  BASE_URL 
} from '../api';

const AppContext = createContext();

// ✅ 1. สร้างข้อความต้อนรับเป็นตัวแปร (เพื่อให้เรียกใช้ซ้ำตอนกด Reset ได้)
const WELCOME_MESSAGE = [
  { 
    id: 'welcome-msg', 
    isUser: false, 
    message: "สวัสดีครับ! ผมคือ AI Music Assistant 🎵\nอยากให้ช่วยแนะนำเพลงแบบไหน หรือจัด Playlist อารมณ์ไหน บอกผมได้เลยครับ!" 
  }
];

export const AppProvider = ({ children }) => {
  // --- States ---
  const [sidebarOpen, setSidebarOpen] = useState(false);
  
  const [chatHistory, setChatHistory] = useState(() => {
    try {
      const saved = localStorage.getItem('chat_history');
      return saved ? JSON.parse(saved) : WELCOME_MESSAGE; // ✅ ใช้ตัวแปร
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

  // Feedback States
  const [isFeedbackModalOpen, setIsFeedbackModalOpen] = useState(false);
  const [feedbackHistory, setFeedbackHistory] = useState([]);
  const [userFeedbackMap, setUserFeedbackMap] = useState({});

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
        
        handleFetchUserProfile();
        fetchPinnedPlaylists();
        fetchUserFeedbackStatus(); 
    } else {
        const savedToken = localStorage.getItem('spotify_access_token');
        if (savedToken) {
            handleFetchUserProfile();
            fetchPinnedPlaylists();
            fetchUserFeedbackStatus();
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
  
  // ✅ 2. เพิ่มฟังก์ชันล้างแชท (ต้องมีอันนี้ ปุ่มถึงจะทำงาน!)
  const handleClearChat = () => {
    if (window.confirm("คุณต้องการลบประวัติการสนทนาทั้งหมดใช่หรือไม่?")) {
      setChatHistory(WELCOME_MESSAGE); // รีเซ็ตกลับไปเป็นข้อความต้อนรับ
      localStorage.removeItem('chat_history'); // ลบออกจาก LocalStorage
    }
  };

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

    if (!userInfo) {
        setTimeout(() => {
            const loginWarningMsg = {
                id: `sys-${Date.now()}`,
                isUser: false,
                message: "🔒 กรุณา **เข้าสู่ระบบ (Login)** ด้วย Spotify ก่อนเริ่มใช้งานครับ\n\n(กดปุ่ม ☰ มุมซ้ายบน หรือเปิด Sidebar เพื่อ Login ได้เลย!)"
            };
            setChatHistory(prev => [...prev, loginWarningMsg]);
        }, 500); 
        return;
    }

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

  const handleFeedback = async (uri, feedback) => {
    setUserFeedbackMap(prev => {
        const newMap = { ...prev };
        if (feedback === 'neutral') delete newMap[uri];
        else newMap[uri] = feedback; 
        return newMap;
    });

    try { 
        if (feedback === 'neutral') { await deleteFeedbackAPI(uri); } 
        else { await sendFeedbackAPI(uri, feedback); }
    } catch (error) { 
        console.error("Failed to update feedback", error); 
        fetchUserFeedbackStatus(); 
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
    if (typeof songs === 'string') { try { songs = JSON.parse(songs); } catch (e) { songs = []; } }
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

  const handleSpotifyLogin = () => { window.location.href = `${BASE_URL}/spotify_login`; };
  
  const handleSpotifyLogout = () => {
    localStorage.clear();
    setUserInfo(null);
    setPinnedPlaylists([]);
    setUserFeedbackMap({});
    window.location.href = '/';
  };

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
    setUserFeedbackMap(prev => {
        const next = { ...prev };
        if (newStatus === 'neutral') delete next[uri];
        else next[uri] = newStatus;
        return next;
    });
    setFeedbackHistory(prev => prev.map(item => {
        if (item.uri === uri) { return { ...item, feedback: newStatus }; }
        return item;
    }));
    try {
        if (newStatus === 'neutral') { await deleteFeedbackAPI(uri); } 
        else { await sendFeedbackAPI(uri, newStatus); }
    } catch (error) {
        console.error("Failed to update feedback", error);
        const data = await getFeedbackHistoryAPI();
        setFeedbackHistory(data);
    }
  };

  return (
    <AppContext.Provider value={{
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
      handleFeedback, 
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
      
      isFeedbackModalOpen, 
      setIsFeedbackModalOpen,
      handleOpenFeedbackModal,
      feedbackHistory,
      handleUpdateFeedbackHistory,
      userFeedbackMap,
      fetchUserFeedbackStatus,
      
      // ✅ 3. ส่งฟังก์ชันนี้ออกไปให้ Sidebar ใช้งาน
      handleClearChat 
    }}>
      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => useContext(AppContext);