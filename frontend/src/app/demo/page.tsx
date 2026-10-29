import type { Metadata } from 'next';
import { PublicShell } from '@/features/public/shell';
import { workspaceAvailable } from '@/features/public/site';
import { PublicDemo } from '@/features/public/demo';
export const metadata: Metadata = {
  title: 'Explore the demo',
  description: 'A read-only walkthrough using clearly labeled fictional opportunities. No signup required.',
};
export default function Demo() {
  return (
    <PublicShell>
      <main id="public-main" className="public-demo-page">
        <div className="public-section-heading">
          <div>
            <span className="public-eyebrow">A LOOK INSIDE</span>
            <h1>Meet your opportunity notebook.</h1>
          </div>
          <p>
            Search, filter, and open examples. This is a read-only demonstration with fictional organizations
            and opportunities—not a live job board.
          </p>
        </div>
        <PublicDemo workspaceAvailable={workspaceAvailable} />
        <p className="public-demo-disclaimer">
          Real workspaces use your verified profile and permitted discovery sources. Creating an account never
          submits an application.
        </p>
      </main>
    </PublicShell>
  );
}
