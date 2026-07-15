const createNextIntlPlugin = require('next-intl/plugin');

const withNextIntl = createNextIntlPlugin('./i18n');

const mode = process.env.BUILD_MODE ?? 'standalone';
console.log("[Next] build mode:", mode);

const isDockerBuild = process.env.DOCKER_BUILD === '1';

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: mode,
  experimental: {
    serverComponentsExternalPackages: [
      '@node-rs/jieba'
    ]
  },
  ...(isDockerBuild && {
    eslint: { ignoreDuringBuilds: true },
    typescript: { ignoreBuildErrors: true },
  }),
}

module.exports = withNextIntl(nextConfig);
