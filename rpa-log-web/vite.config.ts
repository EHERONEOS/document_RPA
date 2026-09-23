import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// T0.3：dev 代理 /api → 合并后的唯一后台 queue_control_platform 8766
export default defineConfig({
  plugins: [react()],
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
