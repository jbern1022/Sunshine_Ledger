/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // No page uses next/image, so the /_next/image optimizer endpoint only
  // adds attack surface (it decodes untrusted image formats via sharp; see
  // the Next.js AVIF RCE advisory, 2026-09). Turning optimization off makes
  // that endpoint inert.
  images: { unoptimized: true },
  // Dev server may be accessed via a LAN IP rather than localhost (e.g. a
  // docker host). Set DEV_ORIGIN_HOST in .env to silence the cross-origin
  // dev warning; harmless if unset.
  allowedDevOrigins: process.env.DEV_ORIGIN_HOST ? [process.env.DEV_ORIGIN_HOST] : [],
};

export default nextConfig;
