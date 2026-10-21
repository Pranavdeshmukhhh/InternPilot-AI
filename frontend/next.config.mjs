const config = {
  output: 'standalone',
  poweredByHeader: false,
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${process.env.INTERNAL_API_URL || 'http://127.0.0.1:8000'}/api/:path*` }];
  },
  async headers() {
    return [{ source: '/:path*', headers: [
      { key: 'X-Content-Type-Options', value: 'nosniff' },
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
      { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' }
      ,...(process.env.PUBLIC_HTTPS === 'true' ? [{ key: 'Strict-Transport-Security', value: 'max-age=31536000' }] : [])
    ] }];
  }
};
export default config;
