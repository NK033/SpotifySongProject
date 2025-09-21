<script setup>
// รับข้อมูลเพลง (song) และส่ง event (emit) เมื่อมีการกดปุ่ม
defineProps(['song'])
const emit = defineEmits(['showDetails', 'feedback'])

// แปลงข้อมูล artist ให้อ่านง่าย
const artistName = props.song.artists?.map(a => a.name).join(', ') || 'ศิลปิน'
</script>

<template>
  <div class="song-item-card p-3 rounded-lg border flex items-center space-x-3 mb-2">
    <img :src="song.album?.images?.[0]?.url || 'https://placehold.co/100x100'" class="w-16 h-16 rounded-lg object-cover">
    <div class="flex-1 text-left">
        <div class="font-semibold">{{ song.name }}</div>
        <div class="text-sm opacity-80">{{ artistName }}</div>
    </div>
    
    <button @click="emit('feedback', song.uri, 'like')" class="feedback-btn text-xl text-gray-400 hover:text-green-500 transition">👍</button>
    <button @click="emit('feedback', song.uri, 'dislike')" class="feedback-btn text-xl text-gray-400 hover:text-red-500 transition">👎</button>

    <button @click="emit('showDetails', song)" class="text-sm py-2 px-4 rounded-full bg-gray-600 hover:bg-gray-700 transition">
        <i class="fas fa-info-circle"></i>
    </button>
    <a :href="song.external_urls?.spotify" target="_blank" class="flex-shrink-0 py-2 px-4 rounded-full bg-green-500 text-white hover:bg-green-600">
        <i class="fab fa-spotify"></i>
    </a>
  </div>
</template>