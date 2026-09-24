/// <reference types="vitest/config" />
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// The build is ONE self-contained index.html so pywebview can load it via file://
// without starting an HTTP server (BUILD.md §4.3, D6).
export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  build: { outDir: "../src/evra/ui/web", emptyOutDir: true },
  server: { host: "127.0.0.1", port: 5173, strictPort: true },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"] },
});
