import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // This project lives inside a larger, non-git parent directory; pin the
  // Turbopack workspace root so it doesn't warn about an unrelated
  // package-lock.json one level up.
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
