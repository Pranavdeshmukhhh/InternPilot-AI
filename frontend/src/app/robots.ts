export const dynamic = 'force-static';
import type { MetadataRoute } from 'next';
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: ['/', '/demo', '/privacy', '/terms', '/contact'],
        disallow: [
          '/api/',
          '/login',
          '/register',
          '/overview',
          '/explore/',
          '/saved',
          '/applications',
          '/documents',
          '/outreach',
          '/automation',
          '/notifications',
          '/settings/',
          '/owner',
        ],
      },
    ],
  };
}
