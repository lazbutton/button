import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  base: "./",
  optimizeDeps: {
    exclude: ["mpg123-decoder", "@wasm-audio-decoders/common"],
  },
  server: {
    port: 5175,
    strictPort: true,
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: process.env.AUTOMATE_PROXY || "http://127.0.0.1:6811",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/library": {
        target: process.env.CATALOG_PROXY || "http://127.0.0.1:30127",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/library/, ""),
      },
      "/tus": {
        target: process.env.TUSD_PROXY || "http://127.0.0.1:8080",
        changeOrigin: false,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq, req) => {
            if (req.headers.host) proxyReq.setHeader("X-Forwarded-Host", req.headers.host);
            proxyReq.setHeader("X-Forwarded-Proto", "http");
          });
        },
      },
    },
  },
  preview: {
    port: 5175,
    strictPort: true,
    host: "127.0.0.1",
  },
});
