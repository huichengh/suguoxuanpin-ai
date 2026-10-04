import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    // ECharts 体积较大，单独拆包，避免首屏 JS 过大
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          echarts: ['echarts', 'echarts-for-react'],
        },
      },
    },
  },
  server: {
    // 5173 端口常被占用，改用 5174；strictPort 保证端口冲突时直接报错而非静默换端口
    port: 5174,
    strictPort: true,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8123',
        changeOrigin: true,
      },
    },
  },
})
