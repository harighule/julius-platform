/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    passWithNoTests: true,
  },
  server: {
    port: 5173,
    host: true,
    allowedHosts: ['localhost', 'wrq6fkgromi2h46cgrdwcid4mcsbtxqghquq2kohze2vfn542csg66id.onion'],
    proxy: {
      // ✅ ALL /api/* requests go directly to backend – NO rewrite, NO stripping
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // Keep /auth as fallback (if frontend ever calls /auth directly)
      '/auth': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/status': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/veil': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
