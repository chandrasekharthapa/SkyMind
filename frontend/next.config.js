/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "images.unsplash.com" },
      { protocol: "https", hostname: "upload.wikimedia.org" },
      { protocol: "https", hostname: "content.airhex.com" },
      { protocol: "https", hostname: "img.logo.dev" },
      { protocol: "https", hostname: "logo.clearbit.com" },
    ],
  },
  env: {
    // Both keys resolve to the same value — legacy + new code both work
    NEXT_PUBLIC_API_BASE_URL:
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000",
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL ||
      process.env.NEXT_PUBLIC_API_BASE_URL ||
      "http://localhost:8000",
  },
  // The build used to pass with `typescript.ignoreBuildErrors: true` and
  // `eslint.ignoreDuringBuilds: true`, annotated "CI handles them separately"
  // — which was not true: the only workflow ran the data pipeline. TypeScript
  // is now enforced here (tsc --noEmit is clean), and both a typecheck and a
  // lint step run in .github/workflows/ci.yaml. Lint stays out of the build so
  // a style finding cannot block a deploy, but it is a blocking CI gate.
  typescript: {
    ignoreBuildErrors: false,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  // Security headers for production
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
