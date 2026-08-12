import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发期 Vite dev server 代理 /api 到 FastAPI (端口 8000)
// 生产期由 FastAPI StaticFiles 托管 dist, 同源无需代理
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: true,
    proxy: {
      "/api": "http://127.0.0.1:8010",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
