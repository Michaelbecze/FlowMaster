import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies API/WebSocket calls to the Gateway (single frontend entry point
// per contracts/gateway-routing.md); the frontend never addresses a backend service directly.
//
// The proxy target is resolved by this Node process, which runs *inside* the frontend
// container under docker-compose — "localhost" there is the frontend container itself,
// not the gateway container, so it must be the "gateway" service name in that topology.
// VITE_GATEWAY_URL (set in infra/docker-compose.yml) carries the container-network
// address; running the dev server directly on the host falls back to localhost.
const gatewayTarget = process.env.VITE_GATEWAY_URL ?? "http://localhost:8080";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api/v1": {
        target: gatewayTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
