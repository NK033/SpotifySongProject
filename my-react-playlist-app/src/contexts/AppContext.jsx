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
  getPinnedPlaylistsAPI // ✅ เพิ่มตรงนี้: นำเข้ามาให้ครบ จะได้ไม่ต้องสร้าง Helper function
} from '../api';

const AppContext = createContext();

export const AppProvider = ({ children }) => {
  // --- States ---
  const [sidebarOpen, setSidebarOpen] = useState(false);
  
  // ✅ FIX 1: Load from LocalStorage (Auto-Restore)
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
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [playlistToRename, setPlaylistToRename] = useState(null);
  const [isConfirmModalOpen, setIsConfirmModalOpen] = useState(false);
  const [playlistToDelete, setPlaylistToDelete] = useState(null);
  const [showSongModal, setShowSongModal] = useState(false);
  const [modalSong, setModalSong] = useState(null);
  const [modalAnalysis, setModalAnalysis] = useState(null);
  const [suggestedPrompts, setSuggestedPrompts] = useState([]);

  // --- Effects ---
  useEffect(() => {
    const token = localStorage.getItem('spotify_access_token');
    if (token) {
      handleFetchUserProfile();
      fetchPinnedPlaylists();
      fetchSuggestedPrompts();
    }
  }, []);

  // ✅ FIX 2: Auto-Save to LocalStorage
  useEffect(() => {
    localStorage.setItem('chat_history', JSON.stringify(chatHistory));
  }, [chatHistory]);

  // ✅ FIX THEME: Apply theme class to body
  useEffect(() => {
    document.body.classList.remove('light-theme', 'dark-theme');
    document.body.classList.add(`${currentTheme}-theme`);
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
    if (!userInfo?.id) return;
    try {
      // ✅ เรียกใช้ function ที่ import มาได้โดยตรงเลย ไม่ต้องผ่าน Helper
      const playlists = await getPinnedPlaylistsAPI(); 
      setPinnedPlaylists(playlists);
    } catch (error) {
      console.error("Failed to fetch pinned playlists", error);
    }
  };

  const fetchSuggestedPrompts = async () => {
    try {
        const data = await getSuggestedPromptsAPI();
        if (data && data.prompts) {
            setSuggestedPrompts(data.prompts);
        }
    } catch (error) {
        console.error("Failed to fetch prompts", error);
    }
  };

  // ✅ FIX 3: Robust Send Message Function
  const sendMessageToBackend = async (messageOverride = null, intentOverride = null) => {
    const messageToSend = messageOverride || userInput;
    
    if (!messageToSend.trim()) return;

    if (!messageOverride) {
        setUserInput('');
    }

    const userMsgId = `user-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const newUserMsg = { id: userMsgId, isUser: true, message: messageToSend };
    
    setChatHistory(prev => [...prev, newUserMsg]);
    setIsFetching(true); 

    try {
      console.log(`🚀 Sending: "${messageToSend}" (Intent: ${intentOverride})`);
      const data = await sendMessageToChatbot(messageToSend, intentOverride);
      console.log("✅ Response:", data);

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
      console.error("Error sending message:", error);
      const errorMsg = { 
          id: `err-${Date.now()}`, 
          isUser: false, 
          message: "ขออภัยครับ เกิดข้อผิดพลาดในการเชื่อมต่อกับเซิร์ฟเวอร์" 
      };
      setChatHistory(prev => [...prev, errorMsg]);
    } finally {
      setIsFetching(false);
    }
  };

  const handleCreatePlaylist = async () => {
    if (currentRecommendedSongs.length === 0) return;
    const trackUris = currentRecommendedSongs.map(song => song.uri);
    setIsFetching(true);
    try {
      await createPlaylistAPI("AI Recommended Playlist", trackUris);
      alert("Playlist created successfully on Spotify!");
    } catch (error) {
      console.error("Failed to create playlist", error);
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
    try {
      await sendFeedbackAPI(uri, feedback);
    } catch (error) {
      console.error("Failed to send feedback", error);
    }
  };

  const handlePinClick = async (songs, text) => {
    const name = prompt("ตั้งชื่อ Playlist ที่จะปักหมุด:", "My AI Playlist");
    if (name) {
      setIsFetching(true);
      try {
        await pinPlaylistAPI(name, songs, text);
        fetchPinnedPlaylists();
      } catch (error) {
        alert("Failed to pin playlist.");
      } finally {
        setIsFetching(false);
      }
    }
  };

  const displayPlaylistFromHistory = (playlist) => {
    const aiMsg = {
      id: `history-${Date.now()}`,
      isUser: false,
      message: `นี่คือ Playlist ที่คุณปักหมุดไว้: **${playlist.name}**\n${playlist.recommendation_text || ''}`,
      songs: playlist.songs,
      recommendationText: playlist.recommendation_text
    };
    setChatHistory(prev => [...prev, aiMsg]);
    setCurrentRecommendedSongs(playlist.songs);
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
    setCurrentTheme(prev => (prev === 'light' ? 'dark' : 'light'));
  };

  const handleSpotifyLogin = () => { window.location.href = 'http://localhost:8000/spotify_login'; };
  const handleSpotifyLogout = () => {
    localStorage.clear();
    setUserInfo(null);
    setPinnedPlaylists([]);
    window.location.href = '/';
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
      suggestedPrompts
    }}>
      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => useContext(AppContext);