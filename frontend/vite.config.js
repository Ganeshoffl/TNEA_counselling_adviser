import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// On GitHub Pages the site is served from /<repo-name>/, so asset and data URLs
// need that prefix. Locally, and when the FastAPI backend serves the built files,
// the app is at the origin root. BASE_PATH is set by the Pages workflow.
const base = process.env.BASE_PATH || '/'

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      // Only used if you choose to run the Python API alongside the dev server.
      // The UI itself no longer needs it: it runs the engine locally.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
