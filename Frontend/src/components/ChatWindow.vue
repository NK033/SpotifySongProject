<script setup>
import { ref, nextTick } from 'vue'
import SongCard from './SongCard.vue'

const props = defineProps(['history', 'recommendedSongs'])
const emit = defineEmits(['newMessage', 'showDetails', 'createPlaylist'])

const userInput = ref('')
const isFetching = ref(false)
const chatHistoryElem = ref(null)

const scrollToBottom = () => {
  nextTick(() => {
    if (chatHistoryElem.value) {
      chatHistoryElem.value.scrollTop = chatHistoryElem.value.scrollHeight
    }
  })
}

const sendMessage = async () => {
  if (isFetching.value || userInput.value.trim() === '') return
  const userMessage = userInput.value.trim()
  emit('newMessage', { isUser: true, type: 'text', content: userMessage })
  userInput.value = ''
  isFetching.value = true
  scrollToBottom()

  const requestBody = {
    message: userMessage,
    spotify_access_token: localStorage.getItem('spotify_access_token'),
    // ... (ส่ง token อื่นๆ)
  }

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    })
    if (!response.ok) throw new Error('Server error')
    const data = await response.json()
    
    emit('newMessage', {
      isUser: false,
      type: 'bot',
      content: data.response,
      songs: data.songs_found || null,
    })
    scrollToBottom()

  } catch (error) {
    emit('newMessage', {
      isUser: false,
      type: 'text',
      content: `ขออภัยค่ะ เกิดข้อผิดพลาด: ${error.message}`,
    })
    scrollToBottom()
  } finally {
    isFetching.value = false
  }
}
</script>

<template>
  <div class="flex flex-col flex-1 bg-[var(--bg-primary)] transition-colors duration-300 overflow-hidden">
    <div ref="chatHistoryElem" class="flex-1 overflow-y-auto p-4 md:p-8 space-y-4">
      <div v-for="(msg, index) in history" :key="index" class="flex items-start" :class="{ 'justify-end': msg.isUser }">
        <div v-if="!msg.isUser" class="w-10 h-10 rounded-full flex-shrink-0 mr-3">
          <i class="fas fa-robot text-4xl text-green-500"></i>
        </div>
        <div class="flex-1">
          <div
            class="p-4 rounded-xl max-w-xl shadow"
            :class="{
              'bg-green-500 text-white rounded-tr-none': msg.isUser,
              'bg-[var(--chat-bubble-ai)] rounded-tl-none': !msg.isUser,
            }"
          >
            <p class="text-sm whitespace-pre-wrap">{{ msg.content }}</p>
            <div v-if="msg.songs" class="mt-4">
              <SongCard v-for="song in msg.songs" :key="song.uri" :song="song" @show-details="emit('showDetails', song)" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="recommendedSongs.length > 0" class="p-4 pt-0 text-center">
      <button @click="emit('createPlaylist')" class="bg-blue-600 text-white font-semibold py-2 px-6 rounded-full hover:bg-blue-700 transition-colors">
        <i class="fas fa-plus mr-2"></i> สร้าง Playlist นี้ใน Spotify
      </button>
    </div>

    <div class="p-4 md:p-8 flex-shrink-0">
      <div class="relative flex items-center">
        <input
          v-model="userInput"
          @keypress.enter="sendMessage"
          type="text"
          placeholder="พิมพ์ข้อความของคุณ..."
          class="w-full p-4 pl-4 pr-16 bg-[var(--bg-secondary)] border border-[var(--border-color)] rounded-full focus:outline-none focus:ring-2 focus:ring-green-500"
        />
        <button @click="sendMessage" class="absolute right-2 text-white bg-green-500 rounded-full h-10 w-10 flex items-center justify-center hover:bg-green-600">
          <i class="fas fa-paper-plane"></i>
        </button>
      </div>
    </div>
  </div>
</template>