<script setup>
import { ref, onMounted } from 'vue'
import Sidebar from './components/Sidebar.vue'
import ChatWindow from './components/ChatWindow.vue'
import SongDetailModal from './components/SongDetailModal.vue'

// ----- สถานะของแอป (State) -----
// ข้อมูลผู้ใช้
const userInfo = ref({
  displayName: 'User',
  avatar: 'https://placehold.co/100x100/1DB954/ffffff?text=U',
  isLoggedIn: false,
})
// ประวัติการแชททั้งหมด
const chatHistory = ref([
  {
    isUser: false,
    type: 'bot',
    content: 'สวัสดีครับ! ผมคือ AI ที่จะช่วยคุณสร้างเพลย์ลิสต์เพลง ลองพิมพ์บอกผมได้เลยครับ',
    songs: null,
  },
])
// เพลงที่แนะนำล่าสุด (สำหรับปุ่ม "สร้างเพลย์ลิสต์")
const currentRecommendedSongs = ref([])
// เพลงที่ถูกเลือกเพื่อแสดงใน Modal
const selectedSongForModal = ref(null)
const isModalVisible = ref(false)

// ----- ฟังก์ชันจัดการต่างๆ (Methods) -----

// จัดการการล็อกอิน
const handleLogin = () => {
  window.location.href = '/spotify_login'
}

// จัดการการล็อกเอาท์
const handleLogout = () => {
  localStorage.clear()
  updateLoginState()
  chatHistory.value.push({
    isUser: false,
    type: 'text',
    content: 'ออกจากระบบ Spotify แล้ว',
  })
}

// อัปเดตสถานะการล็อกอิน (เช็คจาก localStorage)
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

// รับข้อความใหม่จาก ChatWindow มาแสดงผล
const handleNewMessage = (message) => {
  chatHistory.value.push(message)
  if (message.songs) {
    currentRecommendedSongs.value = message.songs
  } else {
    // ถ้าเป็นข้อความธรรมดา ให้ล้างเพลงแนะนำชุดเก่าทิ้ง
    currentRecommendedSongs.value = []
  }
}

// เปิด Modal แสดงรายละเอียดเพลง
const handleShowDetails = (song) => {
  selectedSongForModal.value = song
  isModalVisible.value = true
}

// ปิด Modal
const handleCloseModal = () => {
  isModalVisible.value = false
  selectedSongForModal.value = null
}

// สร้าง Playlist ใน Spotify
const handleCreatePlaylist = async () => {
    if (currentRecommendedSongs.value.length === 0) return;
    const playlistName = `AI Playlist: ${new Date().toLocaleString('th-TH')}`;
    const trackUris = currentRecommendedSongs.value.map(s => s.uri);
    
    // (ส่วนนี้เหมือนใน index.html เดิม)
    try {
        const accessToken = localStorage.getItem('spotify_access_token');
        const response = await fetch('/create_playlist', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${accessToken}` },
            body: JSON.stringify({ playlist_name: playlistName, track_uris: trackUris })
        });
        if (!response.ok) throw new Error('Failed to create playlist');
        const result = await response.json();
        
        const successMessage = {
            isUser: false,
            type: 'html', // สร้าง type ใหม่เพื่อแสดงผลลิงก์ได้
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
    // ... (ส่วนจัดการ token เหมือนใน index.html เดิม) ...
    localStorage.setItem('spotify_access_token', accessToken)
    const expiresIn = urlParams.get('expires_in')
    const refreshToken = urlParams.get('refresh_token')
    const expiresAt = Date.now() + parseInt(expiresIn, 10) * 1000
    localStorage.setItem('spotify_expires_at', expiresAt)
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
</script>

<template>
  <div class="flex h-screen overflow-hidden bg-[var(--bg-primary)]">
    <Sidebar 
      :user-info="userInfo" 
      @login="handleLogin" 
      @logout="handleLogout" 
    />
    <ChatWindow
      :history="chatHistory"
      :recommended-songs="currentRecommendedSongs"
      @new-message="handleNewMessage"
      @show-details="handleShowDetails"
      @create-playlist="handleCreatePlaylist"
    />
    <SongDetailModal
      v-if="isModalVisible"
      :song="selectedSongForModal"
      @close="handleCloseModal"
    />
  </div>
</template>

<style>
/* นำ CSS ทั้งหมดจาก <style> ใน index.html เดิมมาวางที่นี่ 
  หรือจะย้ายไปไว้ใน src/assets/main.css ก็ได้ (แนะนำ)
*/
body { font-family: 'Sarabun', sans-serif; }
.dark-theme { --bg-primary: #0d1117; --bg-secondary: #1a202c; --text-primary: #e2e8f0; --border-color: #2d3748; --chat-bubble-ai: #2d3748; }
.light-theme { --bg-primary: #ffffff; --bg-secondary: #f3f4f6; --text-primary: #1f2937; --border-color: #d1d5db; --chat-bubble-ai: #e5e7eb; }
body { background-color: var(--bg-primary); color: var(--text-primary); }
.song-item-card { border-color: var(--border-color); }
/* ... (CSS ที่เหลือ) ... */
</style>