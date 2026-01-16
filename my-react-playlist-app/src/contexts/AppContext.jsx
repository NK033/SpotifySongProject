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
  getSuggestedPromptsAPI 
} from '../api';

const AppContext = createContext();

export const AppProvider = ({ children }) => {
  // --- States ---
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [chatHistory, setChatHistory] = useState([
    { 
      id: 1, 
      isUser: false, 
      message: "สวัสดีครับ! ผมคือ AI Music Assistant 🎵\nอยากให้ช่วยแนะนำเพลงแบบไหน หรือจัด Playlist อารมณ์ไหน บอกผมได้เลยครับ!" 
    }
  ]);
  const [userInput, setUserInput] = useState('');
  const [isFetching, setIsFetching] = useState(false); // ควบคุม Loading Overlay
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
      const playlists = await import('../api').then(module => module.getPinnedPlaylistsAPI());
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

  // ✅✅✅ แก้ไขฟังก์ชันนี้ (หัวใจสำคัญ) ✅✅✅
  // รองรับ messageOverride และ intentOverride เพื่อให้ LiveAgent สั่งงานได้
  const sendMessageToBackend = async (messageOverride = null, intentOverride = null) => {
    
    // 1. ตัดสินใจว่าจะใช้ข้อความจากไหน (จาก LiveAgent หรือจากช่องพิมพ์ปกติ)
    const messageToSend = messageOverride || userInput;
    
    if (!messageToSend.trim()) return;

    // 2. เคลียร์ช่องพิมพ์ (ถ้าเป็นการพิมพ์ปกติ)
    if (!messageOverride) {
        setUserInput('');
    }

    // 3. เพิ่มข้อความ User ลงใน Chat History ทันที (เพื่อให้เห็นว่าสั่งแล้ว)
    const newUserMsg = { id: Date.now(), isUser: true, message: messageToSend };
    setChatHistory(prev => [...prev, newUserMsg]);

    // 4. เปิด Loading Overlay (เพื่อให้รู้ว่ากำลังทำงาน)
    setIsFetching(true); 

    try {
      // 5. ส่งไป Backend
      const data = await sendMessageToChatbot(messageToSend, intentOverride);
      
      // 6. เพิ่มคำตอบ AI ลง Chat History
      const newAiMsg = { 
        id: Date.now() + 1, 
        isUser: false, 
        message: data.response, 
        songs: data.songs_found || [],
        recommendationText: data.response 
      };
      setChatHistory(prev => [...prev, newAiMsg]);

      // 7. อัปเดตเพลงแนะนำล่าสุด (ถ้ามี)
      if (data.songs_found && data.songs_found.length > 0) {
        setCurrentRecommendedSongs(data.songs_found);
      }

    } catch (error) {
      console.error("Error sending message:", error);
      const errorMsg = { id: Date.now() + 2, isUser: false, message: "ขออภัยครับ เกิดข้อผิดพลาดในการเชื่อมต่อกับเซิร์ฟเวอร์" };
      setChatHistory(prev => [...prev, errorMsg]);
    } finally {
      // 8. ปิด Loading Overlay
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
      console.log(`Feedback sent for ${uri}: ${feedback}`);
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
      id: Date.now(),
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
            id: Date.now(),
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
      isFetching, setIsFetching, // ส่งตัวนี้ออกไป
      currentTheme, setCurrentTheme,
      currentRecommendedSongs,
      userInfo,
      pinnedPlaylists,
      sendMessageToBackend, // ✅ ฟังก์ชันที่แก้แล้ว
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