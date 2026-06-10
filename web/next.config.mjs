/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Type-safety is enforced via `tsc`/build. ESLint is intentionally not run
  // during build here (no eslintrc committed yet); wire eslint-config-next and
  // flip this off when the lint config lands.
  eslint: { ignoreDuringBuilds: true },
  async headers() {
    // Baseline security headers. The production CSP is intentionally strict;
    // tighten connect-src to the real billing API origin when wired.
    const securityHeaders = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      {
        key: "Permissions-Policy",
        value: "camera=(), microphone=(), geolocation=()",
      },
      {
        key: "Strict-Transport-Security",
        value: "max-age=31536000; includeSubDomains; preload",
      },
    ];
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
