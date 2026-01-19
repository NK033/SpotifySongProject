import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite' // <--- บรรทัดนี้คือพระเอกที่หายไป!

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
     // <--- เมื่อมีบรรทัดบนแล้ว บรรทัดนี้จะทำงานได้
  ],
  server: {
    proxy: {
      '/chat': 'http://localhost:8000',
      '/spotify_login': 'http://localhost:8000',
      '/callback': 'http://localhost:8000',
      '/me': 'http://localhost:8000',
      '/create_playlist': 'http://localhost:8000',
      '/song_details': 'http://localhost:8000',
      '/feedback': 'http://localhost:8000',
      '/pinned_playlists': 'http://localhost:8000',
      '/pin_playlist': 'http://localhost:8000',
      '/summarize_playlist': 'http://localhost:8000',
    }
  }
})