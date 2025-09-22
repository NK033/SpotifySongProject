<script lang="ts">
    import { onMount } from 'svelte';
    import Sidebar from '$lib/components/Sidebar.svelte';
    import LoadingModal from '$lib/components/LoadingModal.svelte';
    import ChatHistory from '$lib/components/ChatHistory.svelte';
    import ChatInput from '$lib/components/ChatInput.svelte';
    import SongModal from '$lib/components/SongModal.svelte';

    

    //--- กำหนด Type ของ Message ---
    type Message = {
        isUser: boolean;
        html: string;
        songs?: any[]; 
    };

    //--- State หลักของแอปพลิเคชัน ---
    let isFetching = false;
    let selectedSong: any | null = null;
    let analysisContent = '';
    let messages: Message[] = [
    
        {
            isUser: false,
            html: '<p class="text-sm">สวัสดีครับ! ผมคือ AI ที่จะช่วยคุณค้นหา วิเคราะห์ และสร้างเพลย์ลิสต์เพลง ลองพิมพ์บอกผมได้เลยครับ</p>'
        }
    ];

    //--- ฟังก์ชันหลัก: รับข้อความจาก ChatInput แล้วส่งไป Backend ---
    async function handleSendMessage(event: CustomEvent<{ message: string }>) {
        const userMessage = event.detail.message;

        // 1. เพิ่มข้อความของผู้ใช้เข้าไปใน State ทันที
        messages = [...messages, { isUser: true, html: userMessage }];
        
        // 2. แสดงหน้าต่าง Loading
        isFetching = true;

        // 3. เตรียมข้อมูลที่จะส่งไป FastAPI
        const requestBody = {
            message: userMessage,
            spotify_access_token: localStorage.getItem('spotify_access_token'),
            spotify_refresh_token: localStorage.getItem('spotify_refresh_token'),
            expires_at: parseInt(localStorage.getItem('spotify_expires_at') || '0', 10)
        };

        try {
            // 4. ส่ง Request ไปยัง FastAPI
            // **สำคัญ:** แก้ URL ให้ถูกต้องถ้าจำเป็น
            const response = await fetch('http://127.0.0.1:8000/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Server error');
            }

            const data = await response.json();

            // 5. เพิ่มคำตอบของ AI เข้าไปใน State
            messages = [...messages, { 
                isUser: false, 
                html: data.response, 
                songs: data.songs_found 
            }];

        } catch (error) {
            const errorMessage = (error instanceof Error) ? error.message : 'An unknown error occurred.';
            messages = [...messages, { 
                isUser: false, 
                html: `<p class="text-sm text-red-500">ขออภัยค่ะ เกิดข้อผิดพลาด: ${errorMessage}</p>`
            }];
        } finally {
            // 6. ซ่อนหน้าต่าง Loading
            isFetching = false;
        }
    }

    // --- 3. สร้างฟังก์ชันสำหรับจัดการ Modal ---
    async function handleShowDetails(event: CustomEvent<{ song: any }>) {
        selectedSong = event.detail.song;
        analysisContent = '<p>กำลังโหลดการวิเคราะห์...</p>'; // Reset content

        try {
            const accessToken = localStorage.getItem('spotify_access_token');
            const response = await fetch(`http://127.0.0.1:8000/song_details/${encodeURIComponent(selectedSong.uri)}`, {
                headers: { 'Authorization': `Bearer ${accessToken}` }
            });
            if (!response.ok) throw new Error('Failed to fetch details');
            const details = await response.json();
            analysisContent = details.gemini_analysis.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
        } catch (error) {
            analysisContent = '<p class="text-red-500">ไม่สามารถโหลดข้อมูลการวิเคราะห์ได้</p>';
        }
    }

    // --- 4. สร้างฟังก์ชันสำหรับจัดการ Feedback ---
    async function handleFeedback(event: CustomEvent<{ uri: string, feedback: string }>) {
        const { uri, feedback } = event.detail;
        const accessToken = localStorage.getItem('spotify_access_token');
        
        // (เพิ่ม Logic การส่ง feedback ไป backend ที่นี่ถ้าต้องการ)
        console.log(`Feedback for ${uri}: ${feedback}`);
        
        // แจ้งผู้ใช้ (ตัวอย่าง)
        messages = [...messages, {
            isUser: false,
            html: `<p class="text-sm">ขอบคุณสำหรับ Feedback ครับ!</p>`
        }];
    }

    //--- จัดการ Callback จาก Spotify ---
    onMount(() => {
        const urlParams = new URLSearchParams(window.location.search);
        const accessToken = urlParams.get('access_token');

        if (accessToken) {
            const expiresIn = urlParams.get('expires_in');
            const refreshToken = urlParams.get('refresh_token');
            const expiresAt = Date.now() + (parseInt(expiresIn || '0', 10) * 1000);
            
            localStorage.setItem('spotify_access_token', accessToken);
            localStorage.setItem('spotify_expires_at', expiresAt.toString());
            if (refreshToken) {
                localStorage.setItem('spotify_refresh_token', refreshToken);
            }

            // ดึงข้อมูลโปรไฟล์หลัง Login
            fetch('http://127.0.0.1:8000/me', { headers: { 'Authorization': `Bearer ${accessToken}` }})
                .then(res => res.json())
                .then(profile => {
                    localStorage.setItem('spotify_display_name', profile.display_name);
                    if (profile.images && profile.images.length > 0) {
                        localStorage.setItem('spotify_avatar', profile.images[0].url);
                    }
                    // ลบ parameter ออกจาก URL แล้วรีโหลดหน้า
                    window.history.replaceState({}, document.title, "/");
                    window.location.reload(); 
                });
        }
    });

</script>

<div class="flex flex-col flex-1 overflow-hidden">
    <ChatHistory 
        {messages} 
        on:showDetails={handleShowDetails} 
        on:feedback={handleFeedback}
    />
    <ChatInput on:sendMessage={handleSendMessage} />
</div>
<SongModal {selectedSong} {analysisContent} on:closeModal={() => selectedSong = null} />

<LoadingModal {isFetching} />