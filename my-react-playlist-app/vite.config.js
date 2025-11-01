import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // This tells Vite to forward any API requests (like /chat, /me, etc.)
      // to your FastAPI backend running on port 8000.
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