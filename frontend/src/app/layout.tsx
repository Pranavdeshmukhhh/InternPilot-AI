import type { Metadata } from 'next';
import './globals.css';
import './studio.css';
export const metadata: Metadata = { title: 'InternPilot · Opportunity notebook', description: 'Keep internships, hackathons, saved opportunities and applications together.' };
// Apply a saved preference before the first paint. New workspaces start light;
// system appearance is an explicit choice, never an inferred default.
const themeBootstrap = `(function(){var theme='light';try{var saved=localStorage.getItem('internpilot-theme');if(saved==='light'||saved==='dark'||saved==='system')theme=saved;}catch(e){}var resolved=theme==='system'?(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):theme;document.documentElement.dataset.theme=resolved;document.documentElement.style.colorScheme=resolved;})();`;
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" data-theme="light" suppressHydrationWarning><head><script dangerouslySetInnerHTML={{ __html: themeBootstrap }} /></head><body>{children}</body></html>;
}
