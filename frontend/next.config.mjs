/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Dev server may be accessed via a LAN IP rather than localhost (e.g. a
  // docker host). Set DEV_ORIGIN_HOST in .env to silence the cross-origin
  // dev warning; harmless if unset.
  allowedDevOrigins: process.env.DEV_ORIGIN_HOST ? [process.env.DEV_ORIGIN_HOST] : [],
};

export default nextConfig;
