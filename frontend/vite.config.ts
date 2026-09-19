import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies API/WebSocket calls to the Gateway (single frontend entry point
// per contracts/gateway-routing.md); the frontend never addresses a backend service directly.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api/v1": {
        target: "http://localhost:8080",
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
