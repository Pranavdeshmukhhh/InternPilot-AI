'use client';

import { Bookmark, CalendarClock, ChevronRight, LoaderCircle, MapPin } from 'lucide-react';

type Opportunity = Record<string, any>;
type Props = { job: Opportunity; onClick: () => void; onSave?: () => void; saving?: boolean; saveDisabled?: boolean; compact?: boolean };

function closing(value: unknown) {
  if (!value) return 'Deadline not disclosed';
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? 'Check deadline on source' : `Closes ${date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}`;
}

export function OpportunityRow({ job, onClick, onSave, saving, saveDisabled, compact }: Props) {
  const company = String(job.company || 'Employer not verified');
  const initials = company.split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase();
  const eligibility = job.eligibility === 'eligible' ? 'Eligible' : job.eligibility === 'ineligible' ? 'Ineligible' : 'Review eligibility';
  const score = typeof job.score === 'number' && Number.isFinite(job.score) ? Math.round(job.score) : null;
  return <div className={`job-card-wrap studio-opportunity ${compact ? 'compact-wrap' : ''}`}>
    <button className={`job-card ${compact ? 'compact' : ''}`} onClick={onClick} aria-label={`View ${job.title} at ${company}`}>
      <span className="company-mark" aria-hidden="true">{initials || '—'}</span>
      <div className="job-content">
        <div className="company-line"><span>{company}</span>{job.is_demo && <span className="test-tag">LOCAL TEST</span>}{job.published_at && Date.now() - new Date(job.published_at).getTime() >= 0 && Date.now() - new Date(job.published_at).getTime() < 86400000 && <span className="new-tag">New</span>}</div>
        <h3>{job.title}</h3>
        <div className="job-meta"><span><MapPin size={13} />{job.location || 'Location not specified'}</span>{job.remote && <span>Remote</span>}{job.opportunity_type === 'hackathon' && <span>Hackathon</span>}{!compact && <span className="row-deadline"><CalendarClock size={13} />{closing(job.deadline)}</span>}</div>
        {!compact && <div className="row-bottom"><span className={`row-eligibility ${job.eligibility === 'eligible' ? 'eligible' : job.eligibility === 'ineligible' ? 'ineligible' : ''}`}><span />{eligibility}</span>{job.status && ['closed', 'expired', 'unverified'].includes(job.status) && <span className="row-source-status">{String(job.status).replaceAll('_', ' ')}</span>}{(job.skills || []).slice(0, 3).map((skill: string) => <span className="row-skill" key={skill}>{skill}</span>)}</div>}
      </div>
      <div className="job-match"><div className="score"><span>{score ?? '—'}</span><small>match</small></div>{compact && <small className="compact-eligibility">{eligibility}</small>}</div>
      <ChevronRight className="row-chevron" size={17} aria-hidden="true" />
    </button>
    {onSave && <button className={`bookmark-button ${job.saved ? 'is-saved' : ''}`} aria-label={`${job.saved ? 'Unsave' : 'Save'} ${job.title}`} aria-pressed={!!job.saved} disabled={saving || saveDisabled} onClick={onSave}>{saving ? <LoaderCircle size={17} className="spin" /> : <Bookmark size={17} fill={job.saved ? 'currentColor' : 'none'} />}</button>}
  </div>;
}
