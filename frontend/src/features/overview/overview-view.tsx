'use client';

import Link from 'next/link';
import {
  ArrowRight,
  ArrowUpRight,
  CircleHelp,
  Clock3,
  Compass,
  FileCheck2,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { OpportunityRow } from '@/components/opportunity-row';
import type { Application, Dashboard, Opportunity, Profile, Source } from '@/lib/api-types';
import { routes } from '@/lib/routes';
import { ago } from '@/features/shared/format';

export function Overview({
  profile,
  dashboard,
  jobs,
  applications,
  sources,
  busy,
  stopped,
  onDiscover,
  onOpen,
  onSave,
}: {
  profile?: Profile;
  dashboard?: Dashboard;
  jobs: Opportunity[];
  applications: Application[];
  sources: Source[];
  busy: string;
  stopped: boolean;
  onDiscover: () => void;
  onOpen: (job: Opportunity) => void;
  onSave: (job: Opportunity) => void;
}) {
  const real = applications.filter((a) => !a.is_demo);
  const attention = real.filter((a) =>
    ['awaiting_review', 'needs_input', 'uncertain', 'failed'].includes(a.status),
  );
  const confirmed = real.filter((a) => !!a.confirmation_id).length;
  const verified = profile?.verified_fields || [];
  const profileReady = ['name', 'email', 'degree', 'university', 'skills'].every((k) => verified.includes(k));
  const enabled = sources.filter((s) => s.enabled && s.permitted);
  const issues = enabled.filter((s) => s.error);
  const deadlines = jobs
    .filter((j) => j.deadline && new Date(j.deadline).getTime() > Date.now())
    .sort((a, b) => String(a.deadline).localeCompare(String(b.deadline)))
    .slice(0, 3);
  return (
    <>
      <div className="page-title-row">
        <div>
          <p className="page-overline">YOUR WORKSPACE</p>
          <h1>
            {profile?.name ? `Good to see you, ${profile.name.split(' ')[0]}.` : 'A clearer next step.'}
          </h1>
          <p className="page-subtitle">A place to find what’s next. And follow it through.</p>
        </div>
        <Button onClick={onDiscover} disabled={!!busy || stopped}>
          <RefreshCw size={15} className={busy === 'discover' ? 'spin' : ''} />
          Find opportunities
        </Button>
      </div>
      <section className="overview-brief" aria-label="Your next steps">
        <div className="brief-intro">
          <span className="section-overline">THE NEXT SMALL STEP</span>
          <h2>
            {attention.length
              ? 'A few things need your eye.'
              : !profileReady
                ? 'Make your profile work for you.'
                : !jobs.length
                  ? 'Start with a promising opportunity.'
                  : 'Your search is taking shape.'}
          </h2>
          <p>
            {attention.length
              ? 'Review the prepared materials and open questions before anything leaves your workspace.'
              : !profileReady
                ? 'Verified skills and education make your matches—and your application drafts—more useful.'
                : !jobs.length
                  ? 'Connect a permitted source, then run discovery. Only real listings will appear here.'
                  : 'Save the roles that matter, check the requirements, and prepare when you’re ready.'}
          </p>
          <Link
            className="text-link"
            prefetch={false}
            href={attention.length ? routes.applications : !profileReady ? routes.profile : routes.discover}
          >
            {attention.length
              ? 'Review applications'
              : !profileReady
                ? 'Complete your profile'
                : 'Explore internships'}
            <ArrowRight size={15} />
          </Link>
        </div>
        <div className="brief-counts">
          <Link href={routes.applications} prefetch={false}>
            <CircleHelp size={17} />
            <strong>{attention.length}</strong>
            <span>to review</span>
          </Link>
          <Link href={routes.applications} prefetch={false}>
            <FileCheck2 size={17} />
            <strong>{confirmed}</strong>
            <span>with confirmation</span>
          </Link>
          <Link href={routes.sources} prefetch={false}>
            <Compass size={17} />
            <strong>{enabled.length}</strong>
            <span>enabled sources</span>
          </Link>
        </div>
      </section>
      <div className="overview-layout">
        <section className="overview-opportunities">
          <div className="section-heading">
            <div>
              <h2>Recently discovered</h2>
              <p>Fresh possibilities. Eligibility stays in view.</p>
            </div>
            <Link href={routes.discover} prefetch={false} className="text-link">
              Explore
              <ArrowUpRight size={15} />
            </Link>
          </div>
          <div className="panel opportunity-results">
            {jobs.length ? (
              jobs.map((job) => (
                <OpportunityRow
                  key={job.id}
                  job={job}
                  onClick={() => onOpen(job)}
                  onSave={() => onSave(job)}
                  saving={busy === `save-${job.id}`}
                  saveDisabled={!!busy}
                  compact
                />
              ))
            ) : (
              <div className="empty">
                <Compass size={25} />
                <h3>Your shortlist starts here</h3>
                <p>
                  Run discovery from your permitted sources. We’ll keep the listings, evidence and deadlines
                  together.
                </p>
                <Link href={routes.sources} prefetch={false} className="text-link">
                  Choose your sources
                  <ArrowRight size={14} />
                </Link>
              </div>
            )}
          </div>
        </section>
        <aside className="overview-aside">
          <section>
            <div className="section-heading">
              <h2>On your radar</h2>
              <Clock3 size={17} />
            </div>
            {deadlines.length ? (
              deadlines.map((job) => (
                <button key={job.id} className="deadline-item" onClick={() => onOpen(job)}>
                  <span className="deadline-date">
                    <strong>{new Date(job.deadline!).getDate()}</strong>
                    {new Date(job.deadline!).toLocaleDateString(undefined, { month: 'short' })}
                  </span>
                  <span>
                    <strong>{job.title}</strong>
                    <small>
                      {job.company} {job.is_demo && <span className="test-tag">LOCAL TEST</span>}
                    </small>
                  </span>
                  <ArrowUpRight size={14} />
                </button>
              ))
            ) : (
              <p className="quiet-copy">
                No known deadlines in the recent listings. Save an opportunity to keep it close.
              </p>
            )}
          </section>
          <section className="discovery-note">
            <div className="section-heading">
              <h2>Discovery status</h2>
              <span className={`status-dot ${dashboard?.worker?.status !== 'online' ? 'warning' : ''}`} />
            </div>
            <p>
              {stopped
                ? 'Activity is paused under your emergency stop.'
                : dashboard?.worker?.status === 'online'
                  ? 'A worker is connected to your queue.'
                  : dashboard?.worker?.status === 'offline'
                    ? 'Your worker is offline. Scheduled scans will continue when it reconnects.'
                    : 'Worker status has not been loaded.'}
            </p>
            {issues.length > 0 && (
              <p>
                {issues.length} {issues.length === 1 ? 'source needs' : 'sources need'} attention.
              </p>
            )}
            <Link href={routes.automation} prefetch={false} className="text-link">
              Automation center
              <ArrowRight size={14} />
            </Link>
          </section>
          <p className="aside-note">
            <ShieldCheck size={16} />A match score measures relevance. Your verified facts and explicit
            approval determine the next step.
          </p>
        </aside>
      </div>
      {!!dashboard?.recent_events?.length && (
        <section className="recent-activity">
          <div className="section-heading">
            <h2>Recent activity</h2>
            <Link href={routes.activity} prefetch={false} className="text-link">
              View log
              <ArrowRight size={14} />
            </Link>
          </div>
          {dashboard!.recent_events.slice(0, 3).map((event) => (
            <div key={event.id} className="activity-line">
              <span className="status-dot" />
              <p>{event.message}</p>
              <time dateTime={event.created_at}>{ago(event.created_at)}</time>
            </div>
          ))}
        </section>
      )}
    </>
  );
}
