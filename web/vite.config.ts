import { defineConfig } from 'vite';

const BACKEND_ORIGIN = process.env.MYT_BACKEND_ORIGIN || 'http://127.0.0.1:8001';

export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: BACKEND_ORIGIN,
        changeOrigin: true,
      },
      '/health': {
        target: BACKEND_ORIGIN,
        changeOrigin: true,
      },
      '/ws': {
        target: BACKEND_ORIGIN.replace('http://', 'ws://').replace('https://', 'wss://'),
        ws: true,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});

