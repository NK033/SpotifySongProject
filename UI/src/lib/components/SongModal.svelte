<script lang="ts">
    import { createEventDispatcher } from 'svelte';

    export let selectedSong: any | null = null;
    export let analysisContent = '<p>กำลังโหลดการวิเคราะห์...</p>';

    const dispatch = createEventDispatcher();

    function closeModal() {
        dispatch('closeModal');
    }

    function handleKeydown(event: KeyboardEvent) {
        if (event.key === 'Escape') {
            closeModal();
        }
    }
</script>

{#if selectedSong}
<div 
    class="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-[70]"
    on:click|self={closeModal}
    on:keydown={handleKeydown}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
>
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-md p-6">
        <div class="flex items-start space-x-4">
            <img src={selectedSong.album?.images?.[0]?.url} alt="Album Art" class="w-24 h-24 rounded-lg object-cover">
            <div class="flex-1">
                <h3 class="text-xl font-bold">{selectedSong.name}</h3>
                <p class="text-md opacity-80">{selectedSong.artists?.map((a:any) => a.name).join(', ')}</p>
            </div>
            <button on:click={closeModal} class="text-gray-400 hover:text-white text-2xl">&times;</button>
        </div>
        <hr class="border-gray-200 dark:border-gray-700 my-4">
        <div class="text-sm prose max-w-none text-black dark:text-white">
            {@html analysisContent}
        </div>
    </div>
</div>
{/if}