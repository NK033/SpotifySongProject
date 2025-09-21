<script setup>
defineProps(['userInfo'])
const emit = defineEmits(['login', 'logout'])
</script>

<template>
  <div class="fixed z-50 top-0 left-0 h-full w-64 bg-[var(--bg-secondary)] transform transition-transform duration-300 ease-in-out md:static md:translate-x-0 md:w-64">
    <div class="flex flex-col h-full p-4">
      <div class="flex items-center space-x-2 pb-4 border-b border-[var(--border-color)]">
        <i class="fas fa-robot text-green-400"></i>
        <h2 class="text-[var(--text-primary)] text-lg font-semibold">AI Playlist</h2>
      </div>
      <div class="mt-4 flex flex-col items-center">
        <img :src="userInfo.avatar" alt="User Avatar" class="w-16 h-16 rounded-full mb-2" />
        <span class="text-lg font-medium text-[var(--text-primary)] break-words w-full text-center">{{ userInfo.displayName }}</span>
        <button v-if="!userInfo.isLoggedIn" @click="emit('login')" class="mt-4 w-full py-2 px-4 rounded-full font-medium transition-colors bg-green-500 text-white hover:bg-green-600">
          <i class="fab fa-spotify mr-2"></i> เข้าสู่ระบบด้วย Spotify
        </button>
        <button v-else @click="emit('logout')" class="mt-2 w-full py-2 px-4 rounded-full font-medium transition-colors bg-red-500 text-white hover:bg-red-600">
          <i class="fas fa-sign-out-alt mr-2"></i> ออกจากระบบ Spotify
        </button>
      </div>
      <div class="flex-grow"></div>
    </div>
  </div>
</template>