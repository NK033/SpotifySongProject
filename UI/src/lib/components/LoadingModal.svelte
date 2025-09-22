<script>
    // 'export' คือการบอกว่า Component นี้สามารถรับค่าจากข้างนอกได้
    // ในที่นี้คือรับค่า 'isFetching' ที่เป็น true/false เพื่อบอกว่าให้แสดงหรือไม่แสดง
    export let isFetching = false;
</script>

{#if isFetching}
    <div class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60]">
        <div class="flex flex-col items-center p-6 rounded-lg bg-gray-800 text-white shadow-lg">
            <div class="animate-spin rounded-full h-12 w-12 border-4 border-green-500 border-t-transparent"></div>
            <p class="mt-4 text-sm font-medium">กำลังโหลด...</p>
        </div>
    </div>
{/if}