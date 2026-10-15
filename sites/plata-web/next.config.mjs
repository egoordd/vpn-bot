/** @type {import('next').NextConfig} */
// Статичный сайт Plata VPN: `next build` кладёт готовые страницы в out/, их отдаёт nginx.
const nextConfig = {
  output: "export",
  trailingSlash: true,
  reactStrictMode: true,
  poweredByHeader: false,
  images: { unoptimized: true },
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
