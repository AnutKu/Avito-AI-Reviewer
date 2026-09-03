import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8081',
      '/health': 'http://localhost:8081',
      '/task-creater': { target: 'http://localhost:8082', rewrite: p => p.replace(/^\/task-creater/, '') },
    },
  },
})
