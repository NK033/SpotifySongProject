<script setup>
import { ref, onMounted } from 'vue'

// รับข้อมูลเพลง (song) และส่ง event (emit) เมื่อกดปิด
const props = defineProps(['song'])
const emit = defineEmits(['close'])

const analysisContent = ref('<p>กำลังโหลดการวิเคราะห์...</p>')

// เมื่อ Component ถูกสร้างขึ้นมา ให้ดึงข้อมูลการวิเคราะห์ทันที
onMounted(async () => {
    const accessToken = localStorage.getItem('spotify_access_token');
    if (!accessToken || !props.song?.uri) {
        analysisContent.value = '<p>ไม่สามารถโหลดข้อมูลได้</p>';
        return;
    }

    try {
        const response = await fetch(`/song_details/${encodeURIComponent(props.song.uri)}`, {
            headers: { 'Authorization': `Bearer ${accessToken}` }
        });
        if (!response.ok) throw new Error('Failed to fetch details');
        const details = await response.json();
        // จัดรูปแบบ HTML ให้น่าอ่าน
        const analysisHtml = details.gemini_analysis.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
        analysisContent.value = analysisHtml;
    } catch (error) {
        analysisContent.value = '<p>ขออภัยค่ะ ไม่สามารถโหลดข้อมูลการวิเคราะห์ได้</p>';
    }
});
</script>

<template>
  <div @click.self="emit('close')" class="modal-overlay fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-[70]">
    <div class="modal-content bg-[var(--bg-secondary)] rounded-lg shadow-xl w-full max-w-md p-6">
        <div class="flex items-start space-x-4">
            <img :src="song.album?.images?.[0]?.url" alt="Album Art" class="w-24 h-24 rounded-lg object-cover">
            <div class="flex-1">
                <h3 class="text-xl font-bold">{{ song.name }}</h3>
                <p class="text-md opacity-80">{{ song.artists?.map(a => a.name).join(', ') }}</p>
            </div>
            <button @click="emit('close')" class="text-gray-400 hover:text-white text-2xl">&times;</button>
        </div>
        <hr class="border-[var(--border-color)] my-4">
        <div v-html="analysisContent" class="text-sm prose max-w-none text-[var(--text-primary)] max-h-60 overflow-y-auto"></div>
    </div>
  </div>
</template>