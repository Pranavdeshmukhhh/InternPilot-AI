import Link from 'next/link';
import { PublicShell } from '@/features/public/shell';
import { workspaceAvailable } from '@/features/public/site';
import { PublicDemo } from '@/features/public/demo';
export default function Page() {
  return (
    <PublicShell>
      <main id="public-main">
        <section className="public-hero">
          <div className="public-hero-copy">
            <span className="public-eyebrow">
              <span className="public-dot" /> FOR YOUR NEXT BEGINNING
            </span>
            <h1>
              Less searching.
              <br />
              More <em>direction.</em>
            </h1>
            <p>
              Internships, hackathons, and a clearer view of what fits. A thoughtful workspace for the
              search—and everything that comes after.
            </p>
            <div className="public-actions">
              <Link className="public-cta" href="/demo">
                Take a look inside <span aria-hidden="true">→</span>
              </Link>
              <Link
                className="public-secondary"
                href={workspaceAvailable ? '/register' : '/#how-it-works'}
                prefetch={false}
              >
                {workspaceAvailable ? 'Activate invitation' : 'How it works'}{' '}
                <span aria-hidden="true">→</span>
              </Link>
            </div>
            <span className="public-hero-note">
              Explore without an account. Your applications stay in your control.
            </span>
          </div>
          <aside className="public-field-note" aria-label="Product principle">
            <span className="public-eyebrow">A NOTE ON FINDING YOUR WAY</span>
            <div className="public-orbit" aria-hidden="true">
              <span>N</span>
              <svg viewBox="0 0 240 240">
                <circle cx="120" cy="120" r="91" />
                <circle cx="120" cy="120" r="64" />
                <path d="M120 17v206M17 120h206" />
                <path className="public-needle" d="m151 66-15 71-47 37 15-71z" />
              </svg>
            </div>
            <p>
              The right opportunity starts
              <br />
              with the right context.
            </p>
            <span className="public-note-rule">India · Remote · International</span>
          </aside>
        </section>
        <section className="public-preview" aria-labelledby="preview-title">
          <div className="public-section-heading">
            <h2 id="preview-title">A calmer way to move forward.</h2>
            <p>Try the filters. Open an example. See the reasoning.</p>
          </div>
          <PublicDemo compact workspaceAvailable={workspaceAvailable} />
        </section>
        <section id="how-it-works" className="public-method" aria-labelledby="method-title">
          <div>
            <span className="public-eyebrow">FROM POSSIBILITIES TO A PLAN</span>
            <h2 id="method-title">
              The search has enough
              <br />
              moving parts already.
            </h2>
          </div>
          <ol>
            <li>
              <span>01</span>
              <div>
                <h3>Discover with a little more focus.</h3>
                <p>
                  Bring permitted career feeds and student opportunities together. Start near Pune or Nagpur,
                  across India, or further afield.
                </p>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <h3>Understand the fit. See the gaps.</h3>
                <p>
                  Review skills, graduation requirements and location restrictions. Uncertain information
                  stays uncertain; a score never replaces eligibility.
                </p>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <h3>Keep your next steps together.</h3>
                <p>
                  Save promising roles, prepare documents from verified facts, and track your progress.
                  Uploads and outreach require your approval.
                </p>
              </div>
            </li>
          </ol>
        </section>
        <section className="public-principles">
          <div>
            <span className="public-eyebrow">BUILT WITH INTENTION</span>
            <h2>
              Useful assistance.
              <br />
              Clear boundaries.
            </h2>
          </div>
          <div>
            <p>
              No invented qualifications. No claims of guaranteed interviews. No automatic real-world
              submissions through unsupported forms.
            </p>
            <p>
              InternPilot is an independent product in controlled preview. Source coverage varies, and
              opportunities change. You can inspect the experience before sharing personal information.
            </p>
            <Link className="public-text-link" href="/privacy">
              How your information is handled <span aria-hidden="true">→</span>
            </Link>
          </div>
        </section>
        <section className="public-closing">
          <span className="public-eyebrow">YOUR NEXT CHAPTER</span>
          <h2>Start with a little clarity.</h2>
          <Link className="public-cta" href="/demo">
            Explore InternPilot <span aria-hidden="true">→</span>
          </Link>
          <p>No signup needed to take a look.</p>
        </section>
      </main>
    </PublicShell>
  );
}
