<script lang="ts">
    import { onMount } from 'svelte';

    //--- ตัวแปรสำหรับเก็บข้อมูลผู้ใช้ ---
    let isLoggedIn = false;
    let displayName = 'User';
    let avatarUrl = 'https://placehold.co/100x100/1DB954/ffffff?text=U';

    //--- ตัวแปรสำหรับสลับธีม ---
    let currentTheme = 'dark';
    let themeIconClass = 'fas fa-sun';
    let themeText = 'โหมดกลางวัน';

    // onMount คือฟังก์ชันที่จะรันแค่ครั้งเดียวหลังจากที่ Component ถูกสร้างเสร็จ
    // เหมาะสำหรับการดึงข้อมูลเริ่มต้น เช่น เช็คว่าผู้ใช้ล็อกอินอยู่หรือไม่
    onMount(() => {
        // ลองดึงข้อมูลจาก localStorage
        const storedToken = localStorage.getItem('spotify_access_token');
        const storedName = localStorage.getItem('spotify_display_name');
        const storedAvatar = localStorage.getItem('spotify_avatar');
        
        if (storedToken && storedName) {
            isLoggedIn = true;
            displayName = storedName;
            avatarUrl = storedAvatar || avatarUrl;
        }

        // ตั้งค่าธีมเริ่มต้น
        const storedTheme = localStorage.getItem('theme') || 'dark';
        applyTheme(storedTheme);
    });

    function handleLogin() {
        // **สำคัญ:** แก้ URL ให้ชี้ไปที่ FastAPI ของคุณ
        window.location.href = 'http://127.0.0.1:8000/spotify_login';
    }

    function handleLogout() {
        localStorage.clear();
        // รีโหลดหน้าเพื่อให้ UI อัปเดต
        window.location.reload();
    }
    
    function applyTheme(theme: string) {
        currentTheme = theme;
        if (theme === 'light') {
            document.documentElement.classList.remove('dark');
            themeIconClass = 'fas fa-moon';
            themeText = 'โหมดกลางคืน';
        } else {
            document.documentElement.classList.add('dark');
            themeIconClass = 'fas fa-sun';
            themeText = 'โหมดกลางวัน';
        }
        localStorage.setItem('theme', theme);
    }

    function toggleTheme() {
        applyTheme(currentTheme === 'dark' ? 'light' : 'dark');
    }

</script>

<div class="fixed z-50 top-0 left-0 h-full w-64 bg-gray-100 dark:bg-gray-800 md:static transform transition-transform duration-300 ease-in-out">
    <div class="flex flex-col h-full p-4">
        <div class="flex items-center justify-between pb-4 border-b border-gray-300 dark:border-gray-700">
            <div class="flex items-center space-x-2">
                <i class="fas fa-robot text-green-400"></i>
                <h2 class="text-gray-900 dark:text-white text-lg font-semibold">AI Playlist</h2>
            </div>
        </div>

        <div class="mt-4 flex flex-col items-center">
            <img src={avatarUrl} alt="User Avatar" class="w-16 h-16 rounded-full mb-2">
            <span class="text-lg font-medium text-gray-900 dark:text-white break-words w-full text-center">{displayName}</span>

            {#if isLoggedIn}
                <button on:click={handleLogout} class="mt-2 w-full py-2 px-4 rounded-full font-medium transition-colors bg-red-500 text-white hover:bg-red-600">
                    <i class="fas fa-sign-out-alt mr-2"></i> ออกจากระบบ Spotify
                </button>
            {:else}
                <button on:click={handleLogin} class="mt-4 w-full py-2 px-4 rounded-full font-medium transition-colors bg-green-500 text-white hover:bg-green-600">
                    <i class="fab fa-spotify mr-2"></i> เข้าสู่ระบบด้วย Spotify
                </button>
            {/if}
        </div>

        <div class="flex-grow"></div>

        <div class="mt-4 pt-4 border-t border-gray-300 dark:border-gray-700">
            <button on:click={toggleTheme} class="w-full flex items-center justify-between py-2 px-4 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors">
                <span><i class="{themeIconClass} mr-2"></i> {themeText}</span>
            </button>
        </div>
    </div>
</div>