import type { Metadata } from 'next';
import Link from 'next/link';
import { PublicShell } from '@/features/public/shell';
export const metadata: Metadata = { title: 'Contact' };
export default function Contact() {
  const value = process.env.PUBLIC_CONTACT_EMAIL || '';
  const email = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(value) ? value : null;
  return (
    <PublicShell>
      <main id="public-main" className="public-prose">
        <span className="public-eyebrow">LET’S KEEP IT CLEAR</span>
        <h1>
          Questions, feedback,
          <br />
          or a privacy request?
        </h1>
        {email ? (
          <>
            <p>
              Contact the operator of this InternPilot deployment. Please avoid including passwords, access
              tokens or sensitive documents in your first message.
            </p>
            <p>
              <a href={`mailto:${email}`}>{email} ↗</a>
            </p>
          </>
        ) : (
          <>
            <p>
              A public support address has not been configured for this preview. If you were invited
              privately, use the channel through which you received your invitation.
            </p>
            <p>
              Public account launch is pending operator identity and contact setup. You can explore the
              read-only demo without sharing personal information.
            </p>
          </>
        )}
        <Link href="/demo">Return to the demo →</Link>
      </main>
    </PublicShell>
  );
}
