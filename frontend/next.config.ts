import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    // A free host can take over a minute to wake; the default 30 s proxy timeout
    // turned that first question into a 500.
    proxyTimeout: 120_000,
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${(process.env.API_URL ?? "http://localhost:8000").replace(/\/$/, "")}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;

