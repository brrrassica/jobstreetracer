import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Served from https://brrrassica.github.io/jobstreetracer/
export default defineConfig({
  base: "/jobstreetracer/",
  plugins: [react()],
  build: {
    target: "es2022",
    outDir: "dist",
    sourcemap: false,
  },
});
