import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

declare const process: { env: Record<string, string | undefined> }; // Node global; no @types/node in this package

// Phase 1: the build output is static files that nginx serves. No Node process runs in production
// (CLAUDE.md memory budget: the static frontend is ~15 MB, a Node server would be far more).
export default defineConfig({
  plugins: [react()],
  // The 3D hall chunk (three.js, ~290 kB gzipped) loads only on the seat page (FR-ADR-074 5); the limit says so.
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1200 },
  // `npm run dev` only: /api goes to the local compose API, as the ALB (AWS) and the rewrite rule (Render) do. Not under
  // node --test (it sets NODE_TEST_CONTEXT): the render harness boots this config in-process and the proxy stalls it.
  ...(process.env.NODE_TEST_CONTEXT ? {} : { server: { proxy: { "/api": "http://localhost:8000", "/health": "http://localhost:8000" } } }),
});
