import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Phase 1: the build output is static files that nginx serves. No Node process runs in production
// (CLAUDE.md memory budget: the static frontend is ~15 MB, a Node server would be far more).
export default defineConfig({
  plugins: [react()],
  // The 3D hall chunk (three.js, ~290 kB gzipped) loads only on the seat page (FR-ADR-074 5); the limit says so.
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1200 },
});
