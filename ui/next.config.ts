import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://localhost:8000/api/:path*',
      },
    ];
  },
  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
        port: "8000",
        pathname: "/api/**",
      },
      {
        protocol: "http",
        hostname: "myserver",
        port: "9000",
        pathname: "/**",
      },
      {
        protocol: "http",
        hostname: "localhost",
        port: "9000",
        pathname: "/**",
      },
      // Allow backend URL from env
      ...(process.env.AI_BACKEND_URL
        ? [
          {
            protocol: new URL(process.env.AI_BACKEND_URL).protocol.replace(
              ":",
              ""
            ) as "http" | "https",
            hostname: new URL(process.env.AI_BACKEND_URL).hostname,
          },
        ]
        : []),
      // Development: picsum for mock thumbnails
      { protocol: "https", hostname: "picsum.photos" },
    ],
  },
  experimental: {
    // Enable server actions for future use
    serverActions: {
      allowedOrigins: ["localhost:3000"],
    },
  },
};

export default nextConfig;
