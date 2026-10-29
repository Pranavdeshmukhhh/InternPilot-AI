'use client';
import { useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import dynamic from 'next/dynamic';
const DemoDetail = dynamic(() => import('./demo-detail'), {
  ssr: false,
  loading: () => <p role="status">Opening example…</p>,
});

export type Example = {
  id: string;
  title: string;
  company: string;
  region: string;
  place: string;
  kind: string;
  skills: string[];
  eligibility: string;
  reason: string;
  state: string;
};
// Fictional examples only: never mixed into the catalog, never sent to an API.
const examples: Example[] = [
  {
    id: 'systems',
    title: 'Software Engineering Intern',
    company: 'Example Systems',
    region: 'India',
    place: 'Pune, India',
    kind: 'Internship',
    skills: ['Python', 'SQL'],
    eligibility: 'Potential fit',
    reason:
      'This fictional role accepts undergraduates graduating in 2029. A Python project would be relevant. Work authorization and availability still need review.',
    state: 'Shortlisted',
  },
  {
    id: 'cloud',
    title: 'Cloud Platform Intern',
    company: 'Example Cloud Lab',
    region: 'India',
    place: 'Nagpur, India',
    kind: 'Internship',
    skills: ['Linux', 'Cloud'],
    eligibility: 'Review required',
    reason:
      'The example does not specify graduation years or compensation. Missing requirements are unknown, not assumed eligible.',
    state: 'Researching',
  },
  {
    id: 'research',
    title: 'Machine Learning Research Intern',
    company: 'Example Research Studio',
    region: 'International',
    place: 'Berlin, Germany',
    kind: 'Internship',
    skills: ['Python', 'PyTorch'],
    eligibility: 'Eligibility concern',
    reason:
      'This example requires EU work authorization. Being an Indian student alone does not establish that authorization. A high skill overlap cannot override it.',
    state: 'Needs review',
  },
  {
    id: 'remote',
    title: 'Web Development Intern',
    company: 'Example Product Collective',
    region: 'Remote',
    place: 'Remote · India',
    kind: 'Internship',
    skills: ['TypeScript', 'React'],
    eligibility: 'Potential fit',
    reason:
      'The fictional description accepts students based in India. The example candidate has a verified TypeScript project; dates and hours still need review.',
    state: 'Shortlisted',
  },
  {
    id: 'hackathon',
    title: 'Build for Better Cities',
    company: 'Example Student Collective',
    region: 'India',
    place: 'Pune · Hybrid',
    kind: 'Hackathon',
    skills: ['Web', 'Open innovation'],
    eligibility: 'Review required',
    reason:
      'A fictional student hackathon. Team size and current registration availability need verification. No prize or deadline is invented.',
    state: 'Researching',
  },
];
export function PublicDemo({
  compact = false,
  workspaceAvailable = true,
}: {
  compact?: boolean;
  workspaceAvailable?: boolean;
}) {
  const lastTrigger = useRef<HTMLButtonElement | null>(null);
  const [query, setQuery] = useState('');
  const [region, setRegion] = useState('All locations');
  const [kind, setKind] = useState('All opportunities');
  const [selected, setSelected] = useState<Example | null>(null);
  const [tab, setTab] = useState<'explore' | 'pipeline'>('explore');
  const rows = useMemo(
    () =>
      examples.filter(
        (r) =>
          (region === 'All locations' || r.region === region) &&
          (kind === 'All opportunities' || r.kind === kind) &&
          `${r.title} ${r.company} ${r.place} ${r.skills.join(' ')}`
            .toLowerCase()
            .includes(query.toLowerCase()),
      ),
    [query, region, kind],
  );
  return (
    <section className="public-product" aria-label="Interactive synthetic product demonstration">
      <div className="demo-toolbar">
        <div className="demo-tabs" aria-label="Demo views">
          <button aria-pressed={tab === 'explore'} onClick={() => setTab('explore')}>
            Discover
          </button>
          <button aria-pressed={tab === 'pipeline'} onClick={() => setTab('pipeline')}>
            Application notebook
          </button>
        </div>
        <span className="demo-label">Synthetic demo · Read only</span>
      </div>
      <div className="demo-body">
        <div className="demo-heading">
          <div>
            <span className="public-eyebrow">YOUR OPPORTUNITY NOTEBOOK</span>
            <h2>{tab === 'explore' ? 'Find a promising next step.' : 'Keep the next step in sight.'}</h2>
          </div>
          <span className="demo-count">
            {tab === 'explore' ? rows.length : examples.length} fictional examples
          </span>
        </div>
        {tab === 'explore' ? (
          <>
            <div className="demo-filters">
              <label>
                <span className="sr-only">Search demo opportunities</span>
                <input
                  aria-label="Search demo opportunities"
                  type="search"
                  placeholder="Search roles, skills or cities"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </label>
              <label>
                <span className="sr-only">Demo location</span>
                <select aria-label="Demo location" value={region} onChange={(e) => setRegion(e.target.value)}>
                  {['All locations', 'India', 'Remote', 'International'].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </label>
              <label>
                <span className="sr-only">Demo opportunity type</span>
                <select
                  aria-label="Demo opportunity type"
                  value={kind}
                  onChange={(e) => setKind(e.target.value)}
                >
                  {['All opportunities', 'Internship', 'Hackathon'].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </label>
            </div>
            <p className="sr-only" role="status">
              {rows.length} matching demo opportunities
            </p>
            <div className="demo-rows">
              {rows.slice(0, compact ? 3 : rows.length).map((r) => (
                <button
                  key={r.id}
                  className="demo-row"
                  onClick={(event) => {
                    lastTrigger.current = event.currentTarget;
                    setSelected(r);
                  }}
                >
                  <span className="demo-monogram" aria-hidden="true">
                    {r.company.split(' ')[1][0]}
                  </span>
                  <span className="demo-role">
                    <small>
                      {r.company} · {r.kind}
                    </small>
                    <strong>{r.title}</strong>
                    <span>
                      {r.place} <span aria-hidden="true">·</span> {r.skills.join(' / ')}
                    </span>
                  </span>
                  <span className={`demo-fit ${r.eligibility === 'Eligibility concern' ? 'concern' : ''}`}>
                    {r.eligibility}
                  </span>
                  <span aria-hidden="true">→</span>
                </button>
              ))}
              {!rows.length && (
                <div className="demo-empty">
                  <h3>No examples match yet.</h3>
                  <p>Try another location or reset your search.</p>
                  <button
                    className="public-text-button"
                    onClick={() => {
                      setQuery('');
                      setRegion('All locations');
                      setKind('All opportunities');
                    }}
                  >
                    Reset filters
                  </button>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="demo-pipeline">
            {['Researching', 'Shortlisted', 'Needs review'].map((state) => (
              <section key={state}>
                <h3>{state}</h3>
                {examples
                  .filter((r) => r.state === state)
                  .map((r) => (
                    <button
                      key={r.id}
                      onClick={(event) => {
                        lastTrigger.current = event.currentTarget;
                        setSelected(r);
                      }}
                    >
                      <small>{r.company}</small>
                      <strong>{r.title}</strong>
                      <span>Fictional record · No application submitted</span>
                    </button>
                  ))}
              </section>
            ))}
          </div>
        )}
        <div className="demo-note">
          <span>
            Illustrative data, not live openings. No accounts, documents or applications are accessed.
          </span>
          {compact ? (
            <Link href="/demo">
              Open the full demo <span aria-hidden="true">→</span>
            </Link>
          ) : (
            <Link href={workspaceAvailable ? '/register' : '/'} prefetch={false}>
              {workspaceAvailable ? 'Create your own workspace' : 'About this product preview'}{' '}
              <span aria-hidden="true">→</span>
            </Link>
          )}
        </div>
      </div>
      {selected && (
        <DemoDetail
          row={selected}
          workspaceAvailable={workspaceAvailable}
          onClose={() => setSelected(null)}
          returnFocus={() => lastTrigger.current?.focus()}
        />
      )}
    </section>
  );
}
