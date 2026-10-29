'use client';
import { Bookmark, CalendarClock, ChevronRight, LoaderCircle, MapPin, ShieldCheck } from 'lucide-react';
import { usePathname, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import type { Opportunity } from '@/lib/api-types';
function closing(value: string | null | undefined) {
  if (!value) return '';
  const date = new Date(value.length === 10 ? value + 'T12:00:00' : value);
  return Number.isNaN(date.getTime())
    ? 'Check closing date'
    : `Closes ${date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}`;
}
export function sourceLabel(job: Opportunity) {
  if (job.is_demo) return 'Local test';
  if (
    ['reference_only', 'unverified'].includes(job.verification_status || '') ||
    ['internscan', 'github_list', 'jobspy_feed', 'search'].includes(job.source || '')
  )
    return 'Reference · verify source';
  return ['greenhouse', 'lever', 'ashby', 'smartrecruiters', 'workday'].includes(job.source || '') ||
    job.verification_status === 'official_metadata_verified'
    ? 'Official listing'
    : 'Source recorded';
}
export function OpportunityRow({
  job,
  onClick,
  onSave,
  saving,
  saveDisabled,
  compact,
}: {
  job: Opportunity;
  onClick: () => void;
  onSave?: () => void;
  saving?: boolean;
  saveDisabled?: boolean;
  compact?: boolean;
}) {
  const pathname = usePathname();
  const search = useSearchParams();
  const params = new URLSearchParams(search.toString());
  params.set('opportunity', job.id);
  const company = job.company || 'Employer not verified';
  const initials = company
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase();
  const label = sourceLabel(job);
  const eligibility =
    job.eligibility === 'eligible'
      ? 'Eligible'
      : job.eligibility === 'ineligible'
        ? 'Ineligible'
        : 'Review needed';
  const score = typeof job.score === 'number' && Number.isFinite(job.score) ? Math.round(job.score) : null;
  const checked = job.last_verified ? new Date(job.last_verified) : null;
  const days = checked ? Math.floor((Date.now() - checked.getTime()) / 86400000) : null;
  return (
    <article className={`job-card-wrap studio-opportunity ${compact ? 'compact-wrap' : ''}`}>
      <Link
        prefetch={false}
        href={`${pathname}?${params}`}
        className={`job-card ${compact ? 'compact' : ''}`}
        aria-label={`View ${job.title} at ${company}`}
        onClick={(event) => {
          if (!event.metaKey && !event.ctrlKey && !event.shiftKey && event.button === 0) {
            event.preventDefault();
            onClick();
          }
        }}
      >
        <span className="company-mark" aria-hidden="true">
          {initials || '—'}
        </span>
        <div className="job-content">
          <div className="company-line">
            <span>{company}</span>
            {job.is_demo && <span className="test-tag">LOCAL TEST</span>}
          </div>
          <h3>{job.title}</h3>
          <div className="job-meta">
            <span>
              <MapPin size={13} aria-hidden="true" />
              {job.location || 'Location not specified'}
            </span>
            {job.remote && <span>Remote</span>}
            {job.compensation && <span>{job.compensation}</span>}
            {job.deadline && (
              <span className="row-deadline">
                <CalendarClock size={13} aria-hidden="true" />
                {closing(job.deadline)}
              </span>
            )}
          </div>
          <div className="row-bottom">
            <span className={`row-eligibility ${job.eligibility || 'review'}`}>
              <span aria-hidden="true" />
              {eligibility}
            </span>
            <span className="row-provenance">
              <ShieldCheck size={12} aria-hidden="true" />
              {label}
              {days !== null && days >= 0
                ? ` · checked ${days === 0 ? 'today' : days === 1 ? 'yesterday' : `${days}d ago`}`
                : ''}
            </span>
            {['closed', 'expired', 'unverified'].includes(job.status || '') && (
              <span className="row-source-status">{job.status}</span>
            )}
          </div>
        </div>
        <div
          className="job-match"
          aria-label={score === null ? 'Match not computed' : `${score} out of 100 relevance, ${eligibility}`}
        >
          <strong>{score ?? '—'}</strong>
          <span>match</span>
        </div>
        <ChevronRight className="row-chevron" size={16} aria-hidden="true" />
      </Link>
      {onSave && (
        <button
          className={`bookmark-button ${job.saved ? 'is-saved' : ''}`}
          aria-label={`${job.saved ? 'Unsave' : 'Save'} ${job.title}`}
          aria-pressed={!!job.saved}
          disabled={saving || saveDisabled}
          onClick={onSave}
        >
          {saving ? (
            <LoaderCircle className="spin" size={17} />
          ) : (
            <Bookmark size={17} fill={job.saved ? 'currentColor' : 'none'} />
          )}
        </button>
      )}
    </article>
  );
}
