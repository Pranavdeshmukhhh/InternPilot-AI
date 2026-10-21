import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'InternPilot AI · Your next beginning', description: 'Discover opportunities. Apply with confidence. A private, local-first internship workspace.' };
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
