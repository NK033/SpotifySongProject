import { ref, onMounted } from 'vue'

// สร้าง Type เพื่อให้ TypeScript ช่วยตรวจสอบข้อมูล
interface UserInfo {
  displayName: string;
  avatar: string;
  isLoggedIn: boolean;
}

interface ChatMessage {
  isUser: boolean;
  type: 'text' | 'bot' | 'html';
  content: string;
  songs?: any[] | null;
}

// ฟังก์ชันนี้จะเก็บ State และ Method ทั้งหมด
export function useChat() {
  // ----- สถานะของแอป (State) -----
  const userInfo = ref<UserInfo>({
    displayName: 'User',
    avatar: 'https://placehold.co/100x100/1DB954/ffffff?text=U',
    isLoggedIn: false,
  })
  const chatHistory = ref<ChatMessage[]>([
    {
      isUser: false,
      type: 'bot',
      content: 'สวัสดีครับ! ผมคือ AI ที่จะช่วยคุณสร้างเพลย์ลิสต์เพลง ลองพิมพ์บอกผมได้เลยครับ',
      songs: null,
    },
  ])
  const currentRecommendedSongs = ref<any[]>([])
  const selectedSongForModal = ref<any | null>(null)
  const isModalVisible = ref(false)

  // ----- ฟังก์ชันจัดการต่างๆ (Methods) -----
  const handleLogin = () => {
    window.location.href = '/spotify_login'
  }

  const handleLogout = () => {
    localStorage.clear()
    updateLoginState()
    chatHistory.value.push({
      isUser: false,
      type: 'text',
      content: 'ออกจากระบบ Spotify แล้ว',
    })
  }

  const updateLoginState = () => {
    const displayName = localStorage.getItem('spotify_display_name')
    const avatar = localStorage.getItem('spotify_avatar')
    const isLoggedIn = !!localStorage.getItem('spotify_access_token') && !!displayName

    userInfo.value = { 
      displayName: displayName || 'User', 
      avatar: avatar || 'https://placehold.co/100x100/1DB954/ffffff?text=U', 
      isLoggedIn 
    }
  }

  const handleNewMessage = (message: ChatMessage) => {
    chatHistory.value.push(message)
    if (message.songs) {
      currentRecommendedSongs.value = message.songs
    } else {
      currentRecommendedSongs.value = []
    }
  }

  const handleShowDetails = (song: any) => {
    selectedSongForModal.value = song
    isModalVisible.value = true
  }

  const handleCloseModal = () => {
    isModalVisible.value = false
    selectedSongForModal.value = null
  }

  const handleCreatePlaylist = async () => {
    if (currentRecommendedSongs.value.length === 0) return;
    const playlistName = `AI Playlist: ${new Date().toLocaleString('th-TH')}`;
    const trackUris = currentRecommendedSongs.value.map(s => s.uri);
    
    try {
        const accessToken = localStorage.getItem('spotify_access_token');
        const response = await fetch('/create_playlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` },
            body: JSON.stringify({ playlist_name: playlistName, track_uris: trackUris })
        });
        if (!response.ok) throw new Error('Failed to create playlist');
        const result = await response.json();
        
        const successMessage: ChatMessage = {
            isUser: false,
            type: 'html',
            content: `<p class="text-sm">สร้างเพลย์ลิสต์ '${playlistName}' ให้เรียบร้อยแล้วครับ!</p>
                      <a href="${result.playlist_info.external_urls.spotify}" target="_blank" class="inline-block mt-2 text-sm py-2 px-4 rounded-full bg-green-500 text-white hover:bg-green-600">
                          <i class="fab fa-spotify mr-2"></i> เปิดใน Spotify
                      </a>`
        };
        chatHistory.value.push(successMessage);
    } catch (error) {
        chatHistory.value.push({ isUser: false, type: 'text', content: 'ขออภัยครับ เกิดข้อผิดพลาดในการสร้างเพลย์ลิสต์' });
    }
  }

  // โค้ดที่ทำงานครั้งแรกเมื่อเปิดหน้าเว็บ
  onMounted(async () => {
    const urlParams = new URLSearchParams(window.location.search)
    const accessToken = urlParams.get('access_token')
    if (accessToken) {
      localStorage.setItem('spotify_access_token', accessToken)
      const expiresIn = urlParams.get('expires_in')
      const refreshToken = urlParams.get('refresh_token')
      
      // --- ✨ แก้ไขตรงนี้ --- ✨
      // ถ้า expiresIn เป็น null ให้ใช้ '3600' (1 ชั่วโมง) เป็นค่าเริ่มต้น
      const expiresAt = Date.now() + (parseInt(expiresIn || '3600', 10) * 1000)
      
      localStorage.setItem('spotify_expires_at', expiresAt.toString())
      if (refreshToken) localStorage.setItem('spotify_refresh_token', refreshToken)
      window.history.replaceState({}, document.title, '/')
      
      try {
        const response = await fetch('/me', { headers: { Authorization: `Bearer ${accessToken}` } })
        if (!response.ok) throw new Error('Failed to fetch profile')
        const profile = await response.json()
        localStorage.setItem('spotify_display_name', profile.display_name)
        if (profile.images && profile.images.length > 0) {
          localStorage.setItem('spotify_avatar', profile.images[0].url)
        }
        chatHistory.value.push({ isUser: false, type: 'text', content: 'เข้าสู่ระบบ Spotify สำเร็จแล้ว!' })
      } catch (error) {
        handleLogout()
      }
    }
    updateLoginState()
  })

  // ส่งทุกอย่างที่จำเป็นกลับไปให้ App.vue ใช้
  return {
    userInfo,
    chatHistory,
    currentRecommendedSongs,
    selectedSongForModal,
    isModalVisible,
    handleLogin,
    handleLogout,
    handleNewMessage,
    handleShowDetails,
    handleCloseModal,
    handleCreatePlaylist,
  }
}

