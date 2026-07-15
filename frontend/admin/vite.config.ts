import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 8081,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/static': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8080', changeOrigin: true },
      // 勿用 '/parse' 前缀，会误拦截前端路由 /parse-test
      '/parse/thread': { target: 'http://127.0.0.1:8080', changeOrigin: true },
    },
  },
})
