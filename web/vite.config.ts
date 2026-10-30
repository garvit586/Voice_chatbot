import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // ws: true is required for the voice WebSocket; without it the upgrade hangs.
      '/api': { target: 'http://localhost:8000', ws: true },
      '/healthz': 'http://localhost:8000',
    },
  },
})
