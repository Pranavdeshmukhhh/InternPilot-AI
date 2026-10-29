import type { Metadata } from 'next';
import './globals.css';
import '@/styles/tokens.css';
import { PerformanceObserver } from '@/features/workspace/performance';
import { siteOrigin } from '@/features/public/site';
export const metadata: Metadata = {
  metadataBase: siteOrigin,
  title: { default: 'InternPilot AI — A clearer next step.', template: '%s · InternPilot AI' },
  description:
    'Find your direction. Discover internships and hackathons, understand eligibility, and keep your applications moving.',
  openGraph: {
    title: 'InternPilot AI — A clearer next step.',
    description: 'Opportunities, context, and a place to keep it all.',
    type: 'website',
    ...(siteOrigin ? { images: [{ url: '/social-preview.png', width: 1200, height: 630 }] } : {}),
  },
  twitter: { card: 'summary_large_image', ...(siteOrigin ? { images: ['/social-preview.png'] } : {}) },
  icons: { icon: '/icon.svg', apple: '/apple-icon.png' },
};
// Apply a saved preference before the first paint. New workspaces start light;
// system appearance is an explicit choice, never an inferred default.
const themeBootstrap = `(function(){var theme='light';try{var saved=localStorage.getItem('internpilot-theme');if(saved==='light'||saved==='dark'||saved==='system')theme=saved;}catch(e){}var resolved=theme==='system'?(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):theme;document.documentElement.dataset.theme=resolved;document.documentElement.style.colorScheme=resolved;})();`;
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrap }} />
      </head>
      <body>
        <>
          <PerformanceObserver />
          {children}
        </>
      </body>
    </html>
  );
}
