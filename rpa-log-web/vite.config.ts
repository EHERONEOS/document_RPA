import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// T0.3：dev 代理 /api → 合并后的唯一后台 queue_control_platform 8766
export default defineConfig({
  plugins: [react()],
  // 构建产物直接落在后端部署包内；拷贝 queue_control_platform 即包含前端静态资源。
  build: {
    outDir: '../queue_control_platform/dist',
    // outDir 位于前端项目外时 Vite 默认不清理，显式清理可避免残留旧 hash 资源。
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8766',
        changeOrigin: true,
      },
      '/files': {
        target: 'http://127.0.0.1:8766',
        changeOrigin: true,
      },
    },
  },
});
