import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    host: true,
    watch: {
      usePolling: true,
      interval: 300,
    },
    allowedHosts: [
      '.ngrok-free.dev'
    ],
    hmr: {
      clientPort: 443
    },
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET || "http://orchestrator:8000",
        changeOrigin: true,
        // Injected server-side so the API key never reaches the browser bundle.
        headers: process.env.API_ACCESS_KEY ? { "X-API-Key": process.env.API_ACCESS_KEY } : {},
      },
    },
  },
});
