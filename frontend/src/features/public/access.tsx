import Link from 'next/link';
import { PublicShell } from './shell';
import { workspaceOrigin } from './site';
export default function PublicAccess() {
  return (
    <PublicShell>
      <main id="public-main" className="public-prose public-access">
        <span className="public-eyebrow">BY INVITATION</span>
        <h1>
          Your private
          <br />
          <em>opportunity workspace.</em>
        </h1>
        <p>
          Only people invited by the owner can create an account. Your invitation is tied to your email
          address, and you choose your own password.
        </p>
        {workspaceOrigin ? (
          <a className="public-cta" href={`${workspaceOrigin.origin}/login`} target="_top">
            Continue to workspace →
          </a>
        ) : (
          <div className="access-status" role="note">
            <h2>Account sign-in is not available on this preview.</h2>
            <p>
              The account backend has not been deployed on this host. Use the private workspace address
              supplied by the owner. This page does not collect your email or password.
            </p>
          </div>
        )}
        <p>The landing page and demo stay public. No invitation is needed to explore them.</p>
        <Link className="public-text-link" href="/demo">
          Explore the public demo →
        </Link>
        <p>
          <Link href="/contact">Invitation or access questions →</Link>
        </p>
      </main>
    </PublicShell>
  );
}
