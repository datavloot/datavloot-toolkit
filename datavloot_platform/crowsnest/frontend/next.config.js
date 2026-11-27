/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
  webpack(config, { webpack }) {
    // Monaco is bundled (lib/monaco.js). Its CSS, JSON, HTML and TypeScript
    // language services each start a worker of several MB that the SQL editor
    // never uses: swap their registration for an empty module so webpack does
    // not build those workers into static/.
    config.plugins.push(
      new webpack.NormalModuleReplacementPlugin(
        /monaco-editor[\\/]esm[\\/]vs[\\/]languages[\\/]features[\\/](css|html|json|typescript)[\\/]register\.js$/,
        require.resolve('./lib/empty.js'),
      ),
    );
    // Monaco points at its editor worker with `new URL(..., import.meta.url)`
    // as a fallback for when MonacoEnvironment.getWorker is not set. Webpack
    // would copy that raw ES module into static/media/, where the minifier
    // fails on it. getWorker is set, so inline the unused fallback instead.
    config.module.rules.push({
      test: /monaco-editor[\\/].*editorWebWorkerMain\.js$/,
      dependency: 'url',
      // 'asset' with an always-true condition, not 'asset/inline': Next sets
      // a filename for 'asset' generators, which 'asset/inline' rejects.
      type: 'asset',
      parser: { dataUrlCondition: () => true },
    });
    return config;
  },
  // In dev mode, proxy /api to the FastAPI backend on :8080
  ...(process.env.NODE_ENV === 'development' && {
    output: undefined,
    async rewrites() {
      return [
        {
          source: '/api/:path*',
          destination: 'http://localhost:8080/api/:path*',
        },
      ];
    },
  }),
};

module.exports = nextConfig;
