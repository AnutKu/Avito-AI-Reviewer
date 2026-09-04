import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Дев-сервер обязан слушать все интерфейсы и принимать запросы с любым Host,
// иначе коллега с другой машины (по IP или сетевому имени) не подключится.
// Цели прокси при необходимости переопределяются переменными окружения —
// можно указать свой UI на общий backend, не трогая этот файл.
const apiTarget = process.env.API_PROXY_TARGET || 'http://localhost:8081'
const taskCreaterTarget = process.env.TASKCREATER_PROXY_TARGET || 'http://localhost:8082'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    port: 3000,
    allowedHosts: true,
    proxy: {
      '/api': apiTarget,
      '/health': apiTarget,
      '/task-creater': { target: taskCreaterTarget, rewrite: p => p.replace(/^\/task-creater/, '') },
    },
  },
})
