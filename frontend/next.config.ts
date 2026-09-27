import type { NextConfig } from "next";

// The browser talks to its own origin; Next proxies /api to the backend.
// No CORS in production, and the backend URL never reaches the client bundle.
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const config: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default config;
