import type { Metadata } from 'next';
import './globals.css';
import './human.css';
export const metadata: Metadata = { title: 'InternPilot · Opportunity notebook', description: 'Keep internships, hackathons, saved opportunities and applications together.' };
export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
