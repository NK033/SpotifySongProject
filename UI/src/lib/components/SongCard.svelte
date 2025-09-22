<script lang="ts">
    import { createEventDispatcher } from 'svelte';

    // รับข้อมูลเพลง (song object) เข้ามา
    export let song: any;

    const dispatch = createEventDispatcher();

    // แยกข้อมูลออกมาเพื่อความสะดวก
    const imageUrl = song.album?.images?.[0]?.url || 'https://placehold.co/100x100';
    const artistName = song.artists?.map((a: any) => a.name).join(', ') || 'ศิลปิน';
    const songName = song.name || 'เพลง';
    const spotifyUrl = song.external_urls?.spotify || '#';

    function showDetails() {
        // ส่ง event 'showDetails' กลับไปให้ +page.svelte พร้อมข้อมูลเพลง
        dispatch('showDetails', { song });
    }

    function sendFeedback(feedbackType: 'like' | 'dislike') {
        // ส่ง event 'feedback' กลับไปพร้อม uri และประเภทของ feedback
        dispatch('feedback', { uri: song.uri, feedback: feedbackType });
    }
</script>

<div class="p-3 rounded-lg border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 flex items-center space-x-3 mb-2 text-black dark:text-white">
    <img src={imageUrl} alt="Album Art" class="w-16 h-16 rounded-lg object-cover flex-shrink-0">
    
    <div class="flex-1 text-left min-w-0">
        <div class="font-semibold truncate">{songName}</div>
        <div class="text-sm opacity-80 truncate">{artistName}</div>
    </div>
    
    <div class="flex items-center space-x-2 flex-shrink-0">
        <button on:click={() => sendFeedback('like')} class="text-xl text-gray-400 hover:text-green-500 transition">👍</button>
        <button on:click={() => sendFeedback('dislike')} class="text-xl text-gray-400 hover:text-red-500 transition">👎</button>

        <button on:click={showDetails} class="text-sm py-2 px-3 rounded-full bg-gray-600 hover:bg-gray-700 text-white transition">
            <i class="fas fa-info-circle"></i>
        </button>

        <a href={spotifyUrl} target="_blank" class="flex-shrink-0 py-2 px-3 rounded-full bg-green-500 text-white hover:bg-green-600">
            <i class="fab fa-spotify"></i>
        </a>
    </div>
</div>