'use client';

import {
  ArrowRight,
  Bookmark,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  ExternalLink,
  FilePlus2,
  LoaderCircle,
  MapPin,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

import type { Opportunity, Policy, Application } from '@/lib/api-types';

import { timestamp, clean, url, human } from '@/features/shared/format';
import { sourceLabel } from '@/components/opportunity-row';
import { Status } from '@/features/shared/primitives';
export function JobDetail({
  job: j,
  policy,
  busy,
  prepare,
  generate,
  applications,
  onSave,
}: {
  job: Opportunity;
  policy: Partial<Policy>;
  busy: string;
  prepare: (j: Opportunity) => Promise<unknown>;
  generate: (j: Opportunity, kind: string) => Promise<unknown>;
  applications: Application[];
  onSave: () => void;
}) {
  const app = applications.find((a) => a.opportunity_id === j.id);
  return (
    <>
      {j.is_demo && <span className="test-tag">LOCAL TEST</span>}
      <div className="detail-summary">
        <div>
          <Status value={j.eligibility || 'review'} />
          {j.status && <Status value={j.status} />}
          <span className="opportunity-kind">
            {j.opportunity_type === 'hackathon' ? 'Hackathon' : 'Internship'}
          </span>
          <span className="detail-location">
            <MapPin size={14} />
            {j.location || 'Location unspecified'}
          </span>
        </div>
        <div className="detail-score">
          <strong>{j.score ?? '—'}</strong>
          <span>/ 100 match</span>
        </div>
      </div>
      <div className="detail-facts">
        <div>
          <span>Discovered</span>
          <strong>{timestamp(j.first_discovered_at || j.first_discovered)}</strong>
        </div>
        <div>
          <span>Published</span>
          <strong>{j.published_at ? timestamp(j.published_at) : 'Not disclosed'}</strong>
        </div>
        <div>
          <span>Last verified</span>
          <strong>{timestamp(j.last_verified_at || j.last_verified)}</strong>
        </div>
        <div>
          <span>Deadline</span>
          <strong>{j.deadline ? timestamp(j.deadline) : 'Not disclosed'}</strong>
        </div>
        <div>
          <span>Compensation</span>
          <strong>{j.compensation || 'Not disclosed'}</strong>
        </div>
        <div>
          <span>Source</span>
          <strong>{j.source || j.source_kind || 'Not disclosed'}</strong>
        </div>
      </div>
      {(j.reasons || []).length > 0 && (
        <section className="detail-section">
          <h3>Why this match?</h3>
          <ul className="reason-list">
            {(j.reasons || []).map((r: string, i: number) => (
              <li key={i}>
                <CircleHelp size={15} />
                <span>{typeof r === 'string' ? r : JSON.stringify(r)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      <section className="detail-section">
        <h3>Verified requirements</h3>
        {(j.verified || []).length ? (
          <ul className="reason-list good-reasons">
            {(j.verified || []).map((r: string, i: number) => (
              <li key={i}>
                <CheckCircle2 size={15} />
                <span>{typeof r === 'string' ? r : JSON.stringify(r)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No explicit requirements have been verified for this listing.</p>
        )}
        {(j.inferred || []).length > 0 && (
          <div className="callout">
            <CircleHelp size={17} />
            <div>
              <strong>Unverified or inferred</strong>
              {(j.inferred || []).map((r: string, i: number) => (
                <p key={i}>{typeof r === 'string' ? r : JSON.stringify(r)}</p>
              ))}
            </div>
          </div>
        )}
      </section>
      {(j.skills || []).length > 0 && (
        <section className="detail-section">
          <h3>Skills in this opportunity</h3>
          <div className="skill-tags">
            {(j.skills || []).map((s: string) => (
              <span key={s} className={(j.skill_overlap || []).includes(s) ? 'matched' : ''}>
                {(j.skill_overlap || []).includes(s) && <Check size={12} />}
                {s}
              </span>
            ))}
          </div>
        </section>
      )}
      {(j.missing_skills || []).length > 0 && (
        <section className="detail-section">
          <h3>Skills to build</h3>
          <div className="skill-tags">
            {(j.missing_skills || []).map((skill: string) => (
              <span key={skill}>{skill}</span>
            ))}
          </div>
        </section>
      )}
      {typeof j.recommended_action === 'string' && (
        <div className="callout mt-6">
          <BookOpen size={18} />
          <div>
            <strong>Suggested next step</strong>
            <p>{j.recommended_action}</p>
            {typeof j.deadline_urgency === 'string' && <p>Deadline: {human(j.deadline_urgency)}</p>}
          </div>
        </div>
      )}
      <section className="detail-section">
        <h3>{j.opportunity_type === 'hackathon' ? 'About the challenge' : 'About the role'}</h3>
        <p className="job-description">
          {clean(j.description) || 'No role description was provided by the source.'}
        </p>
      </section>
      {j.llm_analysis && (
        <details className="requirements-details">
          <summary>
            AI advisory analysis · unverified
            <ChevronDown size={14} />
          </summary>
          <div className="callout">
            <CircleHelp size={16} />
            <p>
              These model suggestions are unverified. They cannot override explicit requirements, candidate
              facts, or submission policies.
            </p>
          </div>
          <pre>{JSON.stringify(j.llm_analysis, null, 2)}</pre>
        </details>
      )}
      {j.requirements && (
        <details className="requirements-details">
          <summary>
            Inspect extracted requirement evidence
            <ChevronDown size={14} />
          </summary>
          <pre>{JSON.stringify(j.requirements, null, 2)}</pre>
        </details>
      )}
      <div className="detail-actions">
        <Button variant="outline" disabled={!!busy} onClick={onSave}>
          <Bookmark size={15} fill={j.saved ? 'currentColor' : 'none'} />
          {j.saved ? 'Saved opportunity' : 'Save opportunity'}
        </Button>
        {url(j.url) && (
          <Button variant="outline" asChild>
            <a href={url(j.url)} target="_blank" rel="noopener noreferrer">
              {sourceLabel(j) === 'Official listing' ? 'Official listing' : 'Open source page'}
              <ExternalLink size={14} />
            </a>
          </Button>
        )}
        <Button variant="outline" disabled={!!busy} onClick={() => generate(j, 'resume')}>
          <FilePlus2 size={15} />
          Tailor resume
        </Button>
        <Button variant="outline" disabled={!!busy} onClick={() => generate(j, 'cover_letter')}>
          Cover letter
        </Button>
        <Button
          disabled={
            !!busy ||
            !!app ||
            j.eligibility === 'ineligible' ||
            ['closed', 'expired'].includes(j.status || '') ||
            policy.emergency_stop ||
            policy.mode === 'discovery'
          }
          onClick={() => prepare(j)}
        >
          {busy === `prepare-${j.id}` ? (
            <LoaderCircle size={15} className="spin" />
          ) : (
            <ArrowRight size={15} />
          )}
          {app ? 'Already in applications' : 'Prepare draft application'}
        </Button>
      </div>
      {policy.mode === 'discovery' && (
        <p className="footnote">Enable Assisted Apply in Application policies to prepare an application.</p>
      )}
      <p className="footnote">
        Creating drafts does not upload documents or submit an application. External uploads need your
        approval for this application; final submission is completed on the official website.
      </p>
    </>
  );
}
