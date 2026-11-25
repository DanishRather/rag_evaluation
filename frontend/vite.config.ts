/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 27464,
    proxy: {
      "/api": "http://127.0.0.1:27463",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
    fileParallelism: false,
    poolOptions: {
      threads: { singleThread: true },
    },
  },
});
