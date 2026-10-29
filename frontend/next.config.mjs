let apiOrigin;
try {
  const url=new URL(process.env.INTERNAL_API_URL || 'http://127.0.0.1:8000');
  if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.pathname!=='/'||url.search||url.hash)throw new Error();
  apiOrigin=url.origin;
} catch { throw new Error('INTERNAL_API_URL must be an HTTP(S) origin without credentials, path, query or fragment'); }
if(Object.keys(process.env).some(name=>name.startsWith('NEXT_PUBLIC_')&&/(SECRET|TOKEN|PASSWORD|(?:^|_)KEY(?:_|$))/.test(name)))
  throw new Error('Credentials must remain server-side; remove credential-like NEXT_PUBLIC variables');
const config = {
  output: 'standalone',
  poweredByHeader: false,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${apiOrigin}/api/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          {
            key: 'Content-Security-Policy',
            value: `default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'${process.env.NODE_ENV === 'development' ? " 'unsafe-eval'" : ''}`,
          },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
          ...(process.env.PUBLIC_HTTPS === 'true'
            ? [{ key: 'Strict-Transport-Security', value: 'max-age=31536000' }]
            : []),
        ],
      },
    ];
  },
};
export default config;
