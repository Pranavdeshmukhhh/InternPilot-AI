import Link from 'next/link';
import { ThemeToggle } from '@/components/theme-toggle';
import { BrandMark } from './brand';
import './public.css';
export function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="public-site">
      <a className="public-skip" href="#public-main">
        Skip to content
      </a>
      <header className="public-nav">
        <Link className="public-brand" href="/" aria-label="InternPilot AI home">
          <BrandMark />
          <span>
            InternPilot <small>AI</small>
          </span>
        </Link>
        <nav aria-label="Public navigation">
          <Link href="/demo">Explore demo</Link>
          <Link href="/login" prefetch={false} className="public-login">
            Sign in <span aria-hidden="true">→</span>
          </Link>
          <ThemeToggle />
        </nav>
      </header>
      {children}
      <footer className="public-footer">
        <Link className="public-brand" href="/">
          <BrandMark size={26} />
          <span>InternPilot AI</span>
        </Link>
        <p>A little more direction. A clearer next step.</p>
        <nav aria-label="Footer">
          <Link href="/demo">Demo</Link>
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
          <Link href="/contact">Contact</Link>
          <a href="/third-party-notices.txt">Open-source notices</a>
        </nav>
        <span className="public-footnote">
          Independent product. No employer affiliation. Applications stay in your control.
        </span>
      </footer>
    </div>
  );
}
