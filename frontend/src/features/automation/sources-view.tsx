'use client';
import { useState } from 'react';
import dynamic from 'next/dynamic';
import { useInvalidation } from '@/features/workspace/provider';
const RegionalDiscovery = dynamic(() =>
  import('@/components/regional-discovery').then((m) => m.RegionalDiscovery),
);

import { Check, Plus, Radio, ShieldCheck, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { OpportunityImport } from '@/components/opportunity-import';

import { SourceManager } from '@/components/source-manager';

import { api } from '@/lib/api-client';
import type { LegacyItem as Item, Perform } from '@/lib/legacy-types';
import { url } from '@/features/shared/format';
import { Empty, Field, Modal, PageTitle } from '@/features/shared/primitives';
export function SourcesView({ sources, busy, perform }: { sources: Item[]; busy: string; perform: Perform }) {
  const invalidate = useInvalidation();
  const [coverage, setCoverage] = useState(false);
  const [open, setOpen] = useState(false);
  const [s, setS] = useState<Item>({
    kind: 'greenhouse',
    slug: '',
    company: '',
    url: '',
    permitted: false,
    enabled: true,
    interval_seconds: 1800,
  });
  const [editing, setEditing] = useState<string | null>(null);
  const [remove, setRemove] = useState<Item | null>(null);
  const edit = (source?: Item) => {
    setS(
      source || {
        kind: 'greenhouse',
        slug: '',
        company: '',
        url: '',
        permitted: false,
        enabled: true,
        interval_seconds: 1800,
      },
    );
    setEditing(source?.id || null);
    setOpen(true);
  };
  return (
    <>
      <PageTitle
        kicker="REAL SOURCES. PERMITTED ACCESS."
        title="Discovery sources"
        description="Use official public ATS APIs, permitted feeds, and authorized sources."
        action={
          <Button onClick={() => edit()}>
            <Plus size={16} />
            Add a source
          </Button>
        }
      />
      <div className="callout mb-6">
        <ShieldCheck size={20} />
        <div>
          <strong>Respect access rules at every step.</strong>
          <p>
            LinkedIn, Indeed, Internshala, and other restricted platforms require an authorized API or feed.
            CAPTCHA, authentication barriers, and blocked crawling are never bypassed. Enable a source only
            when your configured access method is permitted.
          </p>
        </div>
      </div>
      <OpportunityImport
        api={api}
        onImported={() => perform('import-refresh', async () => ({}), 'Opportunity references imported.')}
      />
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>
              Configured sources <span className="subtle-count">{sources.length}</span>
            </h2>
            <p>Incremental checks, cached responses, and source-specific scheduling.</p>
          </div>
        </div>
        {sources.length ? (
          <SourceManager
            sources={sources}
            busy={!!busy}
            onEdit={edit}
            onRemove={setRemove}
            onToggle={(source) =>
              perform(
                'source-toggle',
                () => api(`/sources/${source.id}`, 'PATCH', { enabled: !source.enabled }),
                'Source updated.',
              )
            }
          />
        ) : (
          <Empty
            icon={Radio}
            title="Add your first discovery source"
            action={
              <Button variant="outline" onClick={() => edit()}>
                <Plus size={15} />
                Configure a source
              </Button>
            }
          >
            Start with an employer’s public Greenhouse, Lever, or Ashby board. A source does not grant
            permission to submit applications.
          </Empty>
        )}
      </section>
      <details className="source-coverage" onToggle={(event) => setCoverage(event.currentTarget.open)}>
        <summary>Locations, source catalog & publisher review</summary>
        {coverage && (
          <RegionalDiscovery
            api={api}
            busy={!!busy}
            onChanged={async () => {
              await Promise.all([invalidate('source'), invalidate('profile')]);
            }}
          />
        )}
      </details>
      <div className="connector-support">
        <div>
          <strong>Public ATS discovery</strong>
          <p>Greenhouse · Lever · Ashby · SmartRecruiters</p>
        </div>
        <div>
          <strong>Configured permitted sources</strong>
          <p>Feeds · Official JSON-LD pages · Workday public boards</p>
        </div>
        <div>
          <strong>Authorized API required</strong>
          <p>Restricted job platforms · Search providers</p>
        </div>
      </div>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? 'Edit discovery source' : 'Add a discovery source'}
        eyebrow="PERMITTED ACCESS ONLY"
      >
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const payload = {
              kind: s.kind,
              slug: s.slug,
              company: s.company,
              url: s.url || undefined,
              permitted: s.permitted,
              enabled: s.enabled,
              interval_seconds: s.interval_seconds,
            };
            const r = await perform(
              'source-save',
              () => api(editing ? `/sources/${editing}` : '/sources', editing ? 'PATCH' : 'POST', payload),
              'Discovery source saved.',
            );
            if (r) setOpen(false);
          }}
        >
          <div className="form-grid">
            <Field label="Source type">
              <select value={s.kind} onChange={(e) => setS({ ...s, kind: e.target.value })}>
                {[
                  ['greenhouse', 'Greenhouse public API'],
                  ['lever', 'Lever public API'],
                  ['ashby', 'Ashby public API'],
                  ['smartrecruiters', 'SmartRecruiters public API'],
                  ['feed', 'Permitted RSS / Atom feed'],
                  ['html', 'Official JSON-LD career page'],
                  ['workday', 'Workday public board'],
                  ['search', 'Authorized search API'],
                  ['mlh', 'MLH official hackathon calendar'],
                  ['github_list', 'SimplifyJobs public link references'],
                  ['internscan', 'InternScan published feed'],
                  ['jobspy_feed', 'Authorized JobSpy export feed'],
                ].map(([v, label]) => (
                  <option key={v} value={v}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Company / source name">
              <input
                required
                value={s.company}
                onChange={(e) => setS({ ...s, company: e.target.value })}
                placeholder="Company name"
              />
            </Field>
            <Field label="Board slug" hint="The public board identifier, when applicable.">
              <input
                value={s.slug}
                onChange={(e) => setS({ ...s, slug: e.target.value })}
                placeholder="company-board"
              />
            </Field>
            <Field label="Check interval (seconds)" hint="Sources may enforce a stricter minimum.">
              <input
                required
                type="number"
                min={300}
                max={604800}
                value={s.interval_seconds}
                onChange={(e) => setS({ ...s, interval_seconds: Number(e.target.value) })}
              />
            </Field>
          </div>
          <Field label="Source URL" hint="Required for a feed, official page, or configured API source.">
            <input
              type="url"
              value={s.url || ''}
              onChange={(e) => setS({ ...s, url: e.target.value })}
              placeholder="https://…"
            />
          </Field>
          <label className="consent-box">
            <input
              type="checkbox"
              required
              checked={!!s.permitted}
              onChange={(e) => setS({ ...s, permitted: e.target.checked })}
            />
            <span>
              I confirm this public API, feed, or page permits this discovery access method. I will not use
              this source to bypass authentication, CAPTCHA, or platform restrictions.
            </span>
          </label>
          <label className="check-label mb-6">
            <input
              type="checkbox"
              checked={!!s.enabled}
              onChange={(e) => setS({ ...s, enabled: e.target.checked })}
            />
            Enable scheduled discovery
          </label>
          <Button className="w-full" type="submit" disabled={!!busy}>
            <Check size={16} />
            Save source
          </Button>
        </form>
      </Modal>
      <Modal
        open={!!remove}
        onClose={() => setRemove(null)}
        title="Remove discovery source?"
        eyebrow={remove?.company}
      >
        <p className="muted">
          This stops future checks for this source. This source’s discovered listings will leave your feed.
          Existing application records are preserved.
        </p>
        <div className="detail-actions">
          <Button variant="outline" onClick={() => setRemove(null)}>
            Keep source
          </Button>
          <Button
            variant="destructive"
            disabled={!!busy}
            onClick={async () => {
              const r = await perform(
                'source-remove',
                () => api(`/sources/${remove?.id}`, 'DELETE'),
                'Discovery source removed.',
              );
              if (r !== null) setRemove(null);
            }}
          >
            <Trash2 size={15} />
            Remove source
          </Button>
        </div>
      </Modal>
    </>
  );
}
