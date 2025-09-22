<script lang="ts">
    import { afterUpdate } from 'svelte';
    
    // 1. นำเข้า SongCard component
    import SongCard from './SongCard.svelte'; 

    // 2. กำหนด Type ของ message แต่ละอัน
    type Message = {
        isUser: boolean;
        html: string;
        songs?: any[]; // 'songs' อาจจะมีหรือไม่มีก็ได้ และเป็น array
    };

    // 3. รับ messages array เข้ามาแสดงผล
    export let messages: Message[] = [];
    let chatContainer: HTMLElement;

    // 4. ฟังก์ชันสำหรับเลื่อนหน้าจอลงมาล่างสุดอัตโนมัติเมื่อมีข้อความใหม่
    afterUpdate(() => {
        if (chatContainer) {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
    });
</script>

<div bind:this={chatContainer} class="flex-1 overflow-y-auto p-4 md:p-8 space-y-4">
    {#each messages as message}
        <div class="flex items-start {message.isUser ? 'justify-end' : ''}">
            
            {#if !message.isUser}
                <div class="w-10 h-10 rounded-full flex-shrink-0 mr-3">
                    <i class="fas fa-robot text-4xl text-green-500"></i>
                </div>
            {/if}

            <div class="flex-1">
                <div class="p-3 rounded-xl max-w-lg shadow 
                    {message.isUser 
                        ? 'bg-green-500 text-white rounded-tr-none' 
                        : 'bg-gray-200 dark:bg-gray-700 text-black dark:text-white rounded-tl-none'}
                ">
                    {@html message.html}
                    
                    {#if message.songs && message.songs.length > 0}
                        <div class="mt-4">
                            {#each message.songs as song}
                                <SongCard {song} on:showDetails on:feedback />
                            {/each}
                        </div>
                    {/if}
                </div>
            </div>

        </div>
    {/each}
</div>