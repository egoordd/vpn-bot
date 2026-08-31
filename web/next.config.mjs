/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Type-safety is enforced via `tsc`/build. ESLint is intentionally not run
  // during build here (no eslintrc committed yet); wire eslint-config-next and
  // flip this off when the lint config lands.
  eslint: { ignoreDuringBuilds: true },
  async headers() {
    // Content-Security-Policy: 'unsafe-inline' is required for the inline theme
    // script + Next's inline styles; everything else is locked to same-origin.
    // fonts are self-hosted (next/font). Upgrade script-src to a nonce (via
    // middleware) to drop 'unsafe-inline' when there's time.
    const csp = [
      "default-src 'self'",
      "base-uri 'self'",
      "frame-ancestors 'none'",
      "object-src 'none'",
      "form-action 'self'",
      "img-src 'self' data: https:",
      "font-src 'self' data:",
      "style-src 'self' 'unsafe-inline'",
      // No third-party script or frame: signing in with Telegram is a plain
      // navigation to oauth.telegram.org and back, so their widget script —
      // which needs 'unsafe-eval' and was silently blocked here — is gone.
      "script-src 'self' 'unsafe-inline'",
      "frame-src 'none'",
      "connect-src 'self'",
      "manifest-src 'self'",
    ].join("; ");
    const securityHeaders = [
      { key: "Content-Security-Policy", value: csp },
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
