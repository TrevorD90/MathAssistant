/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { cpSync, existsSync } from "node:fs";
import { resolve } from "node:path";

// MathLive loads its math fonts at runtime from `fontsDirectory`. Copy them into
// the build so nothing is fetched from a CDN (spec: bundle everything).
function copyMathliveFonts(): Plugin {
  return {
    name: "copy-mathlive-fonts",
    apply: "build",
    writeBundle(options) {
      const src = resolve(__dirname, "node_modules/mathlive/fonts");
      const dest = resolve(options.dir ?? "dist", "mathlive-fonts");
      if (existsSync(src)) cpSync(src, dest, { recursive: true });
    },
  };
}

export default defineConfig({
  plugins: [react(), copyMathliveFonts()],
  base: "/",
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false, chunkSizeWarningLimit: 2000 }, // local app: one bundle is fine
  server: {
    // `npm run dev` hot-reload mode (optional): start the backend with
    // MATHASSISTANT_PORT=8765, then open http://localhost:5173/#token=<token
    // printed by the backend>. The proxy rewrites Host and drops Origin so the
    // backend's local-only checks pass for this trusted dev proxy.
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${process.env.MATHASSISTANT_PORT ?? "8765"}`,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (req) => req.removeHeader("origin"));
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
