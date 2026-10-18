import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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

