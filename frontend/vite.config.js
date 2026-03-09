import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  define: {
    // Makes VITE_API_BASE available at build time
  },
  server: {
    port: 5173,
  },
  build: {
    outDir: 'dist',
  }
})
