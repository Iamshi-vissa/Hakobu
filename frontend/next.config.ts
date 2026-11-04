import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  experimental: {
    // Tree-shake icon/animation barrels so only used exports ship.
    optimizePackageImports: ["lucide-react", "@hugeicons/core-free-icons", "motion"],
  },
};

export default nextConfig;
