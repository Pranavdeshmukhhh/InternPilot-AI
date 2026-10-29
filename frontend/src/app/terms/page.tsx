import type { Metadata } from 'next';
import { PublicShell } from '@/features/public/shell';
import Link from 'next/link';
export const metadata: Metadata = { title: 'Terms & conditions' };
const sections = [
  ['access', 'Private workspace access'],
  ['information', 'Accurate information'],
  ['opportunities', 'Opportunity information'],
  ['approval', 'Your approval'],
  ['limits', 'Service limits'],
  ['support', 'Operator & support'],
];
export default function Terms() {
  return (
    <PublicShell>
      <main id="public-main" className="public-legal">
        <header className="legal-intro">
          <span className="public-eyebrow">TERMS & CONDITIONS · 29 OCTOBER 2026</span>
          <h1>
            A little clarity.
            <br />
            <em>Before you begin.</em>
          </h1>
          <p className="legal-summary">Public to explore. Private by invitation. Always in your control.</p>
          <p className="legal-disclosure">
            InternPilot AI is an independent opportunity-discovery and application-management tool in
            controlled preview. These product-use terms require operator review and identification before a
            commercial or public-account launch; they are not a claim of legal clearance in any jurisdiction.
          </p>
        </header>
        <div className="terms-layout">
          <nav className="legal-index" aria-label="Terms sections">
            <span className="public-eyebrow">ON THIS PAGE</span>
            <ol>
              {sections.map(([id, label], index) => (
                <li key={id}>
                  <a href={`#${id}`}>
                    <span aria-hidden="true">0{index + 1}</span>
                    {label}
                  </a>
                </li>
              ))}
            </ol>
          </nav>
          <div className="legal-body">
            <section id="access" tabIndex={-1}>
              <h2>Private workspace access</h2>
              <p>
                The landing page and demo are public. Account workspaces are invitation-only. The owner
                authorizes an email address, and the invitation can expire or be revoked. Choose your own
                password and keep your invitation private.
              </p>
              <p>
                The owner can suspend account access and revoke sessions. The public preview does not host the
                account backend or accept passwords; use the workspace address supplied with your invitation.
              </p>
            </section>
            <section id="information" tabIndex={-1}>
              <h2>Use accurate information</h2>
              <p>
                Provide only information and documents you have the right to use. Verify candidate facts
                before using them in an application. Do not fabricate qualifications, impersonate others,
                collect credentials, send unsolicited bulk messages or bypass website restrictions.
              </p>
            </section>
            <section id="opportunities" tabIndex={-1}>
              <h2>Opportunities can change</h2>
              <p>
                Eligibility explanations and relevance scores are assistance, not employer decisions.
                Deadlines, compensation, availability and requirements can change. Confirm material details on
                the original employer or organizer page. InternPilot does not guarantee interviews,
                employment, prizes or complete source coverage.
              </p>
            </section>
            <section id="approval" tabIndex={-1}>
              <h2>You control external actions</h2>
              <p>
                Review application materials, recipient details and permissions before approving an upload or
                message. A prepared application is not a submitted application. General real-world automatic
                submission is not supported by the shipped adapters. CAPTCHA, MFA, legal and unsupported
                questions require human intervention.
              </p>
            </section>
            <section id="limits" tabIndex={-1}>
              <h2>Service limits</h2>
              <p>
                Providers, source access rules and technical limits may interrupt discovery or delivery. Keep
                copies of important documents and confirmations. The public demonstration is read only and
                fictional; no listed example represents an available position or an affiliation with an
                employer.
              </p>
            </section>
            <section id="support" tabIndex={-1}>
              <h2>Operator and support</h2>
              <p>
                The deployment operator must provide an identity, contact channel, applicable policies and any
                pricing before collecting public registrations or payments. This build does not offer a paid
                plan or promise a service-level guarantee. See Contact for the channel configured on this
                deployment.
              </p>
              <p>
                <Link href="/privacy">Read the privacy policy →</Link>
                <br />
                <Link href="/contact">Contact the operator →</Link>
              </p>
            </section>
          </div>
        </div>
      </main>
    </PublicShell>
  );
}
