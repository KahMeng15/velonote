import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load .env files for the current mode so we can read VITE_API_URL at config time
  const env = loadEnv(mode, process.cwd(), '')
  const apiUrl = env.VITE_API_URL || 'http://localhost:8000'

  return {
    plugins: [react()],
    logLevel: 'warn',
    server: {
      host: true,
      port: 5173,
      watch: {
        usePolling: true,
      },
      hmr: { log: false },
      proxy: {
        '/api': {
          target: apiUrl,
          changeOrigin: true,
          ws: true,
          rewrite: (path) => path.replace(/^\/api/, '')
        },
        '/ws': {
          target: apiUrl,
          ws: true,
        }
      }
    }
  }
})
