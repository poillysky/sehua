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
    ],
    // 前进/后退短时复用客户端 RSC 缓存，减轻「返回厂牌页又卡一下」
    staleTimes: {
      dynamic: 30,
      static: 180,
    },
  },
  ...(isDockerBuild && {
    eslint: { ignoreDuringBuilds: true },
    typescript: { ignoreBuildErrors: true },
  }),
  async redirects() {
    return [
      // 旧论坛 fid → 有码/无码番号导航
      { source: "/b/36", destination: "/b/mk-uncensored", permanent: false },
      { source: "/b/36/:path*", destination: "/b/mk-uncensored", permanent: false },
      { source: "/b/37", destination: "/b/mk-censored", permanent: false },
      { source: "/b/37/:path*", destination: "/b/mk-censored", permanent: false },
      { source: "/b/104", destination: "/b/mk-censored", permanent: false },
      { source: "/b/104/:path*", destination: "/b/mk-censored", permanent: false },
      { source: "/b/103", destination: "/c/1", permanent: false },
      { source: "/b/103/:path*", destination: "/c/1", permanent: false },
      { source: "/b/107", destination: "/c/1", permanent: false },
      { source: "/b/107/:path*", destination: "/c/1", permanent: false },
      { source: "/b/39", destination: "/c/1", permanent: false },
      { source: "/b/39/:path*", destination: "/c/1", permanent: false },
      { source: "/b/151", destination: "/c/1", permanent: false },
      { source: "/b/151/:path*", destination: "/c/1", permanent: false },
      { source: "/b/160", destination: "/c/1", permanent: false },
      { source: "/b/160/:path*", destination: "/c/1", permanent: false },
    ];
  },
  async rewrites() {
    const scrapeOrigin = (
      process.env.SCRAPE_ORIGIN ||
      process.env.COVER_ORIGIN ||
      "http://127.0.0.1:9209"
    ).replace(/\/$/, "");
    return [
      {
        source: "/covers/:path*",
        destination: `${scrapeOrigin}/covers/:path*`,
      },
    ];
  },
}

module.exports = withNextIntl(nextConfig);
