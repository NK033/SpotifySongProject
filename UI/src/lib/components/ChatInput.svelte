<script lang="ts">
    import { createEventDispatcher } from 'svelte';

    let inputValue = '';
    const dispatch = createEventDispatcher();

    function sendMessage() {
        if (inputValue.trim() === '') return;
        
        // ส่ง event ชื่อ 'sendMessage' ออกไปให้ +page.svelte พร้อมกับข้อความ
        dispatch('sendMessage', { message: inputValue });

        inputValue = ''; // ล้างช่องพิมพ์
    }
</script>

<div class="p-4 md:p-8 flex-shrink-0">
    <div class="relative flex items-center">
        <input 
            type="text" 
            bind:value={inputValue}
            on:keypress={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="พิมพ์ข้อความของคุณ..." 
            class="w-full p-4 pl-4 pr-16 bg-gray-200 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-full focus:outline-none focus:ring-2 focus:ring-green-500 transition-colors duration-300 text-black dark:text-white">
        
        <button 
            on:click={sendMessage}
            class="absolute right-2 text-white bg-green-500 rounded-full h-10 w-10 flex items-center justify-center hover:bg-green-600 transition-colors duration-300">
            <i class="fas fa-paper-plane"></i>
        </button>
    </div>
</div>