import type { Metadata } from 'next';
import Link from 'next/link';
import { PublicShell } from '@/features/public/shell';
export const metadata: Metadata = { title: 'Privacy' };
export default function Privacy() {
  return (
    <PublicShell>
      <main id="public-main" className="public-prose">
        <span className="public-eyebrow">PRODUCT INFORMATION · 29 OCTOBER 2026</span>
        <h1>Your information deserves context, too.</h1>
        <p>
          This notice describes the current InternPilot AI application. It is an independent controlled
          preview. The operator must publish their identity and support channel before accepting public
          registrations.
        </p>
        <h2>Exploring without an account</h2>
        <p>
          The landing page and read-only demo do not access candidate accounts or request personal
          information. The demo uses fictional examples. Theme preference may be stored locally. This build
          does not add advertising trackers or transmit its local performance events to an analytics service.
          Hosting providers may retain ordinary access and error logs.
        </p>
        <h2>Information in a workspace</h2>
        <p>
          Accounts store a sign-in email and salted password hash. Candidate profiles, uploaded documents,
          generated documents, application information and connected-service tokens are stored to provide the
          workflows you choose. Sensitive candidate fields and document contents are encrypted at rest; this
          is not end-to-end encryption.
        </p>
        <h2>Who can access it</h2>
        <p>
          Records are scoped to your account. Authorized operators can administer the service; the owner
          console permits audited sensitive access after password reauthentication, purpose and consent
          checks. It does not retrieve your password. Shared public opportunity facts are separate from
          personal profiles and application records.
        </p>
        <h2>Optional providers and external actions</h2>
        <p>
          Configured search and AI providers may process discovery queries or opportunity text. Connecting
          Gmail grants the requested OAuth permissions and stores encrypted tokens. Uploads, submissions and
          outgoing messages require the relevant explicit approval. Review each provider’s terms before
          connecting it. Unsupported actions remain manual.
        </p>
        <h2>Retention, deletion and requests</h2>
        <p>
          Documents and account history remain until the operator removes them under their retention policy.
          There is no automatic account-deletion workflow in this release. Request access, correction,
          deletion or disconnection through the operator’s contact channel; backup retention may delay
          permanent erasure. Do not upload sensitive information to a preview whose operator/contact details
          are not configured.
        </p>
        <p>
          <Link href="/contact">Contact and privacy requests →</Link>
        </p>
      </main>
    </PublicShell>
  );
}
